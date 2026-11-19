"""Async edit-document manager (``httpx``).

Mirrors :class:`geopack_sdk.edits.EditDocumentManager` one-for-one; the
envelope rules and the mode ladder are shared, never re-implemented.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .edits import (
    DEFAULT_EDIT_MODE,
    EDIT_MODES,
    SUPPORTED_EDIT_DOCUMENT_VERSIONS,
    _check_envelope,
)
from .models import EditResult


class AsyncEditDocumentManager:
    """Async twin of :class:`geopack_sdk.edits.EditDocumentManager`."""

    def __init__(self, client):
        self.client = client

    async def submit(
        self,
        dataset_id: int,
        document: Dict[str, Any],
        *,
        mode: Optional[str] = None,
    ) -> EditResult:
        """Send ``document`` as-is, optionally overriding its ``mode``."""
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

        response_data = await self.client.post(
            f"/datasets/{dataset_id}/edits", json=payload
        )
        return EditResult(**(response_data or {}))

    async def validate(
        self, dataset_id: int, document: Dict[str, Any]
    ) -> EditResult:
        """Plan the document without writing anything."""
        return await self.submit(dataset_id, document, mode="validate")

    async def preview(
        self, dataset_id: int, document: Dict[str, Any]
    ) -> EditResult:
        """Plan the document and return the simulated per-operation result."""
        return await self.submit(dataset_id, document, mode="preview")

    async def apply(
        self, dataset_id: int, document: Dict[str, Any]
    ) -> EditResult:
        """Write the document in one transaction across related datasets."""
        return await self.submit(dataset_id, document, mode="apply")

    def supported_versions(self) -> List[str]:
        """The EditDoc grammar versions this SDK will send."""
        return list(SUPPORTED_EDIT_DOCUMENT_VERSIONS)
