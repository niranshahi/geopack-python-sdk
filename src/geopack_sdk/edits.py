"""Edit documents (EditDoc): validate -> preview -> apply.

Editing is the only SDK surface that can destroy data (decision D14):

* ``mode`` defaults to ``validate`` and nothing here defaults to ``apply``;
* only the ENVELOPE is validated client-side (``version`` / ``editRef`` /
  ``mode`` / ``changes``). The change grammar belongs to
  ``docs/11-feature-plans/record-editing/000-edit-protocol-master-design.md``
  — changes travel as typed-but-permissive dicts so a server-side addition
  never needs an SDK release;
* ``editRef`` is the caller's idempotency/anchor. ``apply`` refuses a document
  without one instead of inventing it, because an auto-minted ref makes a
  retry look like a new edit.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

from .exceptions import EditDocumentVersionError
from .models import EditResult

#: EditDoc grammar versions this SDK speaks. A new server version is a MINOR
#: SDK event: widen this tuple explicitly (slice 012 maintenance note).
SUPPORTED_EDIT_DOCUMENT_VERSIONS = ("1.0",)
DEFAULT_EDIT_DOCUMENT_VERSION = "1.0"

#: The mode ladder. ``validate`` and ``preview`` never write.
EDIT_MODES = ("validate", "preview", "apply")
DEFAULT_EDIT_MODE = "validate"


def new_edit_ref() -> str:
    """A fresh uuid4 edit reference (idempotency/audit anchor)."""
    return str(uuid.uuid4())


def build_edit_document(
    changes: Iterable[Dict[str, Any]],
    *,
    edit_ref: Optional[str] = None,
    version: str = DEFAULT_EDIT_DOCUMENT_VERSION,
    mode: str = DEFAULT_EDIT_MODE,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an EditDoc envelope around ``changes``.

    ``edit_ref`` defaults to a fresh :func:`new_edit_ref`; pass your own to
    make a retry attributable to the original attempt. The document is a plain
    dict — the SDK never re-derives the change grammar.
    """
    if mode not in EDIT_MODES:
        raise ValueError(
            f"Unknown edit mode {mode!r}; expected one of {', '.join(EDIT_MODES)}."
        )
    if version not in SUPPORTED_EDIT_DOCUMENT_VERSIONS:
        raise EditDocumentVersionError(
            f"Unsupported edit document version {version!r}; "
            f"this SDK speaks {', '.join(SUPPORTED_EDIT_DOCUMENT_VERSIONS)}.",
            version=version,
        )

    document: Dict[str, Any] = {
        "version": version,
        "editRef": edit_ref or new_edit_ref(),
        "mode": mode,
        "changes": list(changes or []),
    }
    if options is not None:
        document["options"] = options
    return document


def _check_envelope(document: Dict[str, Any], mode: str) -> None:
    """Fail fast on the two things the server would reject as a 400."""
    version = document.get("version")
    if version not in SUPPORTED_EDIT_DOCUMENT_VERSIONS:
        raise EditDocumentVersionError(
            f"Unsupported edit document version {version!r}; "
            f"this SDK speaks {', '.join(SUPPORTED_EDIT_DOCUMENT_VERSIONS)}. "
            "Rebuild the document with build_edit_document().",
            version=version if isinstance(version, str) else None,
        )
    if mode == "apply" and not document.get("editRef"):
        raise ValueError(
            "An 'apply' edit document needs an editRef (its audit/idempotency "
            "anchor). Mint one with new_edit_ref() or build_edit_document()."
        )


class EditDocumentManager:
    """The edit-document ladder: ``validate`` -> ``preview`` -> ``apply``.

    Every method sends the SAME document; only ``mode`` differs, so a caller
    can preview exactly what it is about to apply.

    REST API: ``POST /api/datasets/{datasetId}/edits``
    """

    def __init__(self, client):
        self.client = client

    def submit(
        self,
        dataset_id: int,
        document: Dict[str, Any],
        *,
        mode: Optional[str] = None,
    ) -> EditResult:
        """Send ``document`` as-is, optionally overriding its ``mode``.

        ``mode=None`` keeps the document's own mode (``validate`` when it has
        none). Unknown modes and unknown versions are rejected before any
        network call.
        """
        if not isinstance(document, dict):
            raise TypeError("An edit document must be a dict.")

        payload: Dict[str, Any] = dict(document)
        if mode is not None:
            if mode not in EDIT_MODES:
                raise ValueError(
                    f"Unknown edit mode {mode!r}; "
                    f"expected one of {', '.join(EDIT_MODES)}."
                )
            payload["mode"] = mode
        payload.setdefault("mode", DEFAULT_EDIT_MODE)

        _check_envelope(payload, payload["mode"])

        response_data = self.client.post(
            f"/datasets/{dataset_id}/edits", json=payload
        )
        return EditResult(**(response_data or {}))

    def validate(
        self, dataset_id: int, document: Dict[str, Any]
    ) -> EditResult:
        """Plan the document without writing anything."""
        return self.submit(dataset_id, document, mode="validate")

    def preview(
        self, dataset_id: int, document: Dict[str, Any]
    ) -> EditResult:
        """Plan the document and return the simulated per-operation result."""
        return self.submit(dataset_id, document, mode="preview")

    def apply(self, dataset_id: int, document: Dict[str, Any]) -> EditResult:
        """Write the document in one transaction across related datasets.

        Requires an ``editRef``: it is the audit anchor and the only way a
        retry can be recognised as the same edit.
        """
        return self.submit(dataset_id, document, mode="apply")

    def supported_versions(self) -> List[str]:
        """The EditDoc grammar versions this SDK will send."""
        return list(SUPPORTED_EDIT_DOCUMENT_VERSIONS)
