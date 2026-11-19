"""Print layouts — a TEMPLATE REGISTRY, not a renderer (slice 014).

A layout record is a reusable template definition consumed by the **frontend**
renderer. The portal has no render / export endpoint (owner ruling 2026-11-19,
D8), so this manager reads and writes the definition **verbatim** and never
interprets it: no element model, no page-size maths, no legend assembly.

Wire quirks worth knowing:

* ``POST /:id/thumbnail`` takes JSON ``{thumbnailBase64}`` (no multipart) —
  this manager base64-encodes a local file for you, or accepts the payload.
* create answers only ``{id, createdAt, updatedAt}``; ``update`` answers
  ``{id, updated: true}`` and ``delete`` answers ``{id, deleted: true}``.
  Fetch the record to see the stored definition.
* list answers ``{items, total, totalPages, currentPage}`` with
  ``limit``/``offset`` (not page/pageSize).

REST API: ``/api/print-layouts``
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

from .maps import acl_rows, mint_url, read_thumbnail
from .models import MintedUrl, PrintLayout, ThumbnailFile


class PrintLayoutManager:
    """Print-layout template records, thumbnails and ACLs.

    REST API:
        GET    /api/print-layouts
        POST   /api/print-layouts
        GET    /api/print-layouts/:id
        PUT    /api/print-layouts/:id
        DELETE /api/print-layouts/:id                 (200 ``{id, deleted}``)
        POST   /api/print-layouts/:id/thumbnail       (JSON ``thumbnailBase64``)
        GET    /api/print-layouts/:id/thumbnail/access-url  (bearer-only)
        GET    /api/print-layouts/:id/thumbnail       (bytes)
        GET    /api/print-layouts/:id/acl
        POST   /api/print-layouts/:id/acl
        DELETE /api/print-layouts/:id/acl/:aclId      (204)
    """

    def __init__(self, client):
        self.client = client

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        **filters: Any,
    ) -> Dict[str, Any]:
        """Paginated layout list: ``{items, total, totalPages, currentPage}``.

        Filters: ``q``, ``orgId``, ``wgId``, ``ownerId``, ``isTemplate``,
        ``sortBy``, ``sortOrder``. The route uses ``limit``/``offset``, which
        this method derives from ``page``/``page_size``.
        """
        params: Dict[str, Any] = {
            "limit": page_size,
            "offset": max(page - 1, 0) * page_size,
        }
        for key, value in filters.items():
            if value is not None:
                params[key] = value
        response_data = self.client.get("/print-layouts", params=params)
        return response_data if isinstance(response_data, dict) else {}

    def get(self, layout_id: int) -> PrintLayout:
        """One layout with its stored ``layoutJson`` (opaque)."""
        response_data = self.client.get(f"/print-layouts/{layout_id}")
        return PrintLayout.from_api(response_data)

    def create(self, payload: Dict[str, Any]) -> PrintLayout:
        """Create a layout from a caller-owned definition.

        ``name`` defaults server-side to ``Untitled Print Layout``; useful keys
        are ``layoutJson``, ``workgroupId``, ``description``, ``tags``,
        ``isTemplate`` and ``isActive``. The answer is minimal (``id`` plus
        timestamps) — call :meth:`get` for the stored definition.
        """
        if not isinstance(payload, dict):
            raise ValueError("A print layout payload must be a dict.")
        response_data = self.client.post("/print-layouts", json=payload)
        return PrintLayout.from_api(response_data)

    def update(self, layout_id: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Patch the template; server-managed fields are ignored, not rejected.

        Answers ``{id, updated: true}``.
        """
        if not isinstance(patch, dict):
            raise ValueError("A print layout patch must be a dict.")
        response_data = self.client.put(f"/print-layouts/{layout_id}", json=patch)
        return response_data if isinstance(response_data, dict) else {}

    def delete(self, layout_id: int) -> Dict[str, Any]:
        """Delete the template record (``{id, deleted: true}``)."""
        response_data = self.client.delete(f"/print-layouts/{layout_id}")
        return response_data if isinstance(response_data, dict) else {}

    def upload_thumbnail(
        self,
        layout_id: int,
        file_path: Optional[str] = None,
        *,
        thumbnail_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Store thumbnail bytes (base64 over JSON — the route's only shape).

        Pass exactly one of ``file_path`` (encoded here) or an already-encoded
        ``thumbnail_base64``. The bytes are the caller's: the portal never
        draws a layout preview.
        """
        if (file_path is None) == (thumbnail_base64 is None):
            raise ValueError("Pass exactly one of file_path= or thumbnail_base64=.")

        if file_path is not None:
            if not os.path.isfile(file_path):
                raise ValueError(f"Thumbnail file not found: {file_path}")
            with open(file_path, "rb") as handle:
                thumbnail_base64 = base64.b64encode(handle.read()).decode("ascii")

        response_data = self.client.post(
            f"/print-layouts/{layout_id}/thumbnail",
            json={"thumbnailBase64": thumbnail_base64},
        )
        return response_data if isinstance(response_data, dict) else {}

    def get_thumbnail(
        self, layout_id: int, save_path: Optional[str] = None
    ) -> ThumbnailFile:
        """Download the stored thumbnail to disk (never into a JSON dict)."""
        return read_thumbnail(
            self.client, f"/print-layouts/{layout_id}/thumbnail", save_path
        )

    def get_thumbnail_access_url(self, layout_id: int) -> MintedUrl:
        """Mint a temporary signed URL for the thumbnail (bearer-only)."""
        return mint_url(
            self.client, f"/print-layouts/{layout_id}/thumbnail/access-url"
        )

    def get_acls(self, layout_id: int) -> List[Dict[str, Any]]:
        """ACL rows of one layout (bare array, returned verbatim)."""
        response_data = self.client.get(f"/print-layouts/{layout_id}/acl")
        return acl_rows(response_data)

    def create_acls(
        self,
        layout_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[Dict[str, Any]]:
        """Grant permissions on a layout (owner permission cannot be denied)."""
        if not principals or not permissions:
            raise ValueError("principals and permissions are required.")
        payload = {
            "principals": principals,
            "permissions": permissions,
            "effect": effect,
        }
        response_data = self.client.post(
            f"/print-layouts/{layout_id}/acl", json=payload
        )
        return acl_rows(response_data)

    def delete_acl(self, layout_id: int, acl_id: int) -> None:
        """Revoke one ACL entry (204)."""
        self.client.delete(f"/print-layouts/{layout_id}/acl/{acl_id}")
