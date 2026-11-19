"""Edit-document tool handler (validate -> preview -> apply).

The handler owns the *policy* half of the edit lane (slice 021 §1): the SDK's
``EditDocumentManager`` already refuses an unknown mode/version and an ``apply``
without ``editRef``, but a refusal has to name the candidates for a model to
recover, so every check here answers ``invalidArgs`` + a ``hint`` before any
network call.

``validate`` and ``preview`` never write. ``apply`` writes — the consent
sentence lives in the tool description, the mode gate lives here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from geopack_sdk import GeopackClient
from geopack_sdk.edits import (
    DEFAULT_EDIT_MODE,
    EDIT_MODES,
    SUPPORTED_EDIT_DOCUMENT_VERSIONS,
    new_edit_ref,
)
from geopack_sdk.exceptions import DatasetReadOnly, EditConflict


def _invalid_args(
    keys: list, message: str, hint: str, **extra: Any
) -> Dict[str, Any]:
    """Client-side validation refusal (never leaves the process)."""
    payload: Dict[str, Any] = {
        "error": True,
        "type": "invalid_args",
        "code": "INVALID_ARGS",
        "invalidArgs": keys,
        "message": message,
        "hint": hint,
    }
    payload.update(extra)
    return payload


def _mint_ref(document: Dict[str, Any], mode: str) -> Optional[Dict[str, Any]]:
    """Fill ``editRef`` for the dry-run modes; refuse to invent one for apply.

    An auto-minted ref on ``apply`` would make two retries look like two edits,
    so the caller must supply it (§1 rule 3). ``validate``/``preview`` are free
    to mint: nothing is written and the ref is what ties the three calls
    together.
    """
    if document.get("editRef"):
        return None
    if mode == "apply":
        return _invalid_args(
            ["editRef"],
            "An 'apply' edit document needs an editRef: it is the audit anchor and "
            "the only way a retry is recognised as the same edit.",
            "Run the same document with mode='validate' first (that call mints a ref "
            "and returns it), then send that editRef back when you apply.",
        )
    document["editRef"] = new_edit_ref()
    return None


def submit_edit_document(
    client: GeopackClient,
    dataset_id: int,
    document: Dict[str, Any],
    *,
    mode: str = DEFAULT_EDIT_MODE,
) -> Dict[str, Any]:
    """Send one EditDoc through the ladder; only ``apply`` writes.

    Returns the server payload verbatim plus ``mode`` and ``writesApplied``.
    A 423 answers ``DatasetReadOnly`` (the dataset is archived/locked) and a
    409 answers ``EditConflict`` with the server's ``issues`` — both are
    answers the model can act on, not opaque failures.
    """
    if not isinstance(document, dict):
        return _invalid_args(
            ["document"],
            "document must be an EditDoc envelope object.",
            "Send {version: '1.0', changes: [...]} — build it with "
            "geopack_sdk.edits.build_edit_document().",
        )

    effective_mode = (mode or DEFAULT_EDIT_MODE).strip().lower()
    if effective_mode not in EDIT_MODES:
        return _invalid_args(
            ["mode"],
            f"Unknown edit mode {mode!r}.",
            f"Use one of: {', '.join(EDIT_MODES)}. Start with 'validate'; "
            "'apply' writes records and needs explicit user consent.",
        )

    version = document.get("version")
    if version not in SUPPORTED_EDIT_DOCUMENT_VERSIONS:
        return _invalid_args(
            ["version"],
            f"Unsupported edit document version {version!r}.",
            f"This SDK speaks: {', '.join(SUPPORTED_EDIT_DOCUMENT_VERSIONS)}. "
            "Rebuild the document with build_edit_document().",
            supportedVersions=list(SUPPORTED_EDIT_DOCUMENT_VERSIONS),
        )

    changes = document.get("changes")
    if not isinstance(changes, list) or not changes:
        return _invalid_args(
            ["changes"],
            "changes must be a non-empty list of edit operations.",
            "Each entry is one operation from the portal's edit grammar "
            "(see the edit-protocol plan). The SDK does not re-derive it.",
        )

    clone = dict(document)
    refusal = _mint_ref(clone, effective_mode)
    if refusal is not None:
        return refusal

    try:
        result = client.edit_documents.submit(int(dataset_id), clone, mode=effective_mode)
    except DatasetReadOnly as exc:
        return {
            "error": True,
            "type": "DatasetReadOnly",
            "status_code": exc.status_code,
            "code": exc.code,
            "message": exc.message,
            "hint": (
                "This dataset is archived or locked against edits. Remove it (and "
                "anything that cascades to it) from the plan, or edit it in the portal."
            ),
        }
    except EditConflict as exc:
        return {
            "error": True,
            "type": "EditConflict",
            "status_code": exc.status_code,
            "code": exc.code,
            "message": exc.message,
            "issues": getattr(exc, "issues", None),
            "conflicts": getattr(exc, "conflicts", None),
            "editRef": getattr(exc, "edit_ref", None),
            "hint": (
                "The server rejected the plan per operation (issues above). Re-read the "
                "rows with geopack_sdk_query_dataset, rebuild the document, and re-run "
                "mode='validate' before applying."
            ),
        }

    payload = result.model_dump(by_alias=True, mode="json")
    payload.pop("raw", None)
    payload["mode"] = effective_mode
    payload["editRef"] = payload.get("editRef") or clone.get("editRef")
    payload["writesApplied"] = bool(payload.get("applied"))
    return payload
