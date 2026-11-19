"""Saved maps — the control plane for map DOCUMENTS (slice 014).

A map is a **stored record**: ``id``, ``name``, an opaque ``details`` document,
a caller-uploaded thumbnail and an ACL. The portal has **no** render / export /
rasterize endpoint, so nothing in this module draws a map: producing an image
or a PDF is the consuming agent's job (owner ruling 2026-11-19, D8).

Two rules follow and are deliberately visible in the signatures:

* ``details`` is passed through **unchanged** — never validated, normalized or
  re-serialized (the frontend owns the map grammar).
* thumbnails are **bytes the caller supplies**; reads are written to disk and
  answered as :class:`~geopack_sdk.models.ThumbnailFile` so no image ever rides
  inside a JSON payload.

REST API: ``/api/maps``
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import GeopackAPIError
from .models import MapDocument, MintedUrl, ThumbnailFile

#: Query keys the route parses as JSON arrays (controller does ``JSON.parse``).
_JSON_FILTERS = frozenset(
    {"organizationIds", "workgroupIds", "ownerIds", "keywords", "bbox"}
)


def _json_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for key, value in filters.items():
        if value is None:
            continue
        if key in _JSON_FILTERS and not isinstance(value, str):
            params[key] = json.dumps(value)
        else:
            params[key] = value
    return params


def _write_thumbnail(
    content: bytes, mime_type: str, save_path: Optional[str]
) -> ThumbnailFile:
    """Write thumbnail bytes to ``save_path`` (a file, a directory, or None).

    ``None`` writes a temp file — the caller gets the path back and owns it.
    """
    suffix = ".png" if "png" in (mime_type or "") else ".jpg"
    if save_path is None:
        target = os.path.join(
            tempfile.gettempdir(), f"geopack-thumb-{uuid.uuid4().hex}{suffix}"
        )
    elif os.path.isdir(save_path):
        target = os.path.join(save_path, f"geopack-thumb-{uuid.uuid4().hex}{suffix}")
    else:
        target = save_path

    with open(target, "wb") as fh:
        fh.write(content)

    return ThumbnailFile(
        savedPath=os.path.abspath(target),
        mimeType=mime_type or "application/octet-stream",
        sizeBytes=len(content),
    )


def _mime_type(response: Any) -> str:
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("Content-Type") if hasattr(headers, "get") else None
    return str(raw or "application/octet-stream").split(";")[0].strip()


def _fetch_bytes(client: Any, path: str, *, timeout: float = 60) -> Tuple[bytes, str]:
    """GET a byte lane with Bearer auth (thumbnails are not JSON)."""
    url = f"{client.base_url.rstrip('/')}{path}"
    token = getattr(getattr(client, "auth", None), "token", None)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.session.get(url, headers=headers, timeout=timeout)
    if response.status_code == 404:
        raise GeopackAPIError(404, f"Resource not found: {path}")
    if not getattr(response, "ok", False):
        raise GeopackAPIError.from_response(response)
    content = response.content
    if not content:
        raise GeopackAPIError(404, f"Empty response from {path}")
    return content, _mime_type(response)


def read_thumbnail(
    client: Any, path: str, save_path: Optional[str]
) -> ThumbnailFile:
    """Shared read side for both thumbnail managers (one byte lane each)."""
    content, mime_type = _fetch_bytes(client, path)
    return _write_thumbnail(content, mime_type, save_path)


def mint_url(client: Any, path: str) -> MintedUrl:
    """Mint a signed capability URL (Bearer-only endpoint, like slice 010)."""
    data = client.get(path)
    if not isinstance(data, dict) or not data.get("url"):
        raise GeopackAPIError(502, f"Invalid mint response from {path}")
    return MintedUrl(**data)


def acl_rows(data: Any) -> List[Dict[str, Any]]:
    """ACL answers are bare arrays; anything else is an empty list."""
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


class MapManager:
    """Saved map documents, thumbnails and ACLs.

    REST API:
        GET    /api/maps
        GET    /api/maps/statistics
        POST   /api/maps
        GET    /api/maps/:mapId
        PUT    /api/maps/:mapId
        DELETE /api/maps/:mapId                       (204)
        POST   /api/maps/:mapId/thumbnail             (multipart field ``thumbnail``)
        GET    /api/maps/:mapId/thumbnail/access-url  (bearer-only mint)
        GET    /api/maps/:mapId/thumbnail             (bytes)
        GET    /api/maps/:id/acl
        POST   /api/maps/:id/acl
        DELETE /api/maps/:id/acl/:aclId               (204)
    """

    def __init__(self, client):
        self.client = client

    def list(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters: Any,
    ) -> Dict[str, Any]:
        """Paginated map list: ``{maps, totalCount, totalPages, currentPage,
        itemsPerPage}``.

        Filters map to the controller's query parser: ``searchQuery``,
        ``orderBy``, ``orderDirection``, ``organizationIds``, ``workgroupIds``,
        ``ownerIds``, ``keywords``, ``startDate``, ``endDate``, ``bbox``. The
        five array-like filters are JSON-encoded here when passed as lists.
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(_json_filters(filters))
        response_data = self.client.get("/maps", params=params)
        return response_data if isinstance(response_data, dict) else {}

    def statistics(self) -> Dict[str, Any]:
        """Facet counts: ``{organizations, owners, workgroups, keywords,
        dateRange}`` — already scoped to what the caller may read."""
        response_data = self.client.get("/maps/statistics")
        return response_data if isinstance(response_data, dict) else {}

    def create(self, document: Dict[str, Any]) -> MapDocument:
        """Create a map from a caller-owned document (``name`` is required).

        ``document`` is stored verbatim (``details`` may carry layers/view).
        """
        if not isinstance(document, dict):
            raise ValueError("A map document must be a dict.")
        response_data = self.client.post("/maps", json=document)
        return MapDocument.from_api(response_data)

    def get(self, map_id: int) -> MapDocument:
        """One map by id (404 when missing or not accessible)."""
        response_data = self.client.get(f"/maps/{map_id}")
        return MapDocument.from_api(response_data)

    def update(self, map_id: int, document: Dict[str, Any]) -> MapDocument:
        """Patch the stored document (only the keys you pass are changed)."""
        if not isinstance(document, dict):
            raise ValueError("A map document must be a dict.")
        response_data = self.client.put(f"/maps/{map_id}", json=document)
        return MapDocument.from_api(response_data)

    def delete(self, map_id: int) -> None:
        """Delete a map (204). The thumbnail row goes with it."""
        self.client.delete(f"/maps/{map_id}")

    def upload_thumbnail(self, map_id: int, file_path: str) -> Dict[str, Any]:
        """Upload image bytes as the map thumbnail (multipart ``thumbnail``).

        The server re-encodes the image; this is an **upload**, never a
        request to generate one.
        """
        if not os.path.isfile(file_path):
            raise ValueError(f"Thumbnail file not found: {file_path}")
        with open(file_path, "rb") as handle:
            files = {
                "thumbnail": (
                    os.path.basename(file_path),
                    handle,
                    "application/octet-stream",
                )
            }
            response_data = self.client.post(
                f"/maps/{map_id}/thumbnail", files=files
            )
        return response_data if isinstance(response_data, dict) else {}

    def get_thumbnail(
        self, map_id: int, save_path: Optional[str] = None
    ) -> ThumbnailFile:
        """Download thumbnail bytes to disk (a path, a directory, or a temp file).

        Never returns image bytes inside a dict — callers read ``savedPath``.
        """
        return read_thumbnail(
            self.client, f"/maps/{map_id}/thumbnail", save_path
        )

    def get_thumbnail_access_url(self, map_id: int) -> MintedUrl:
        """Mint a temporary signed URL for the thumbnail (bearer-only).

        Treat it like a credential: do not log it and do not reuse it for
        another map.
        """
        return mint_url(self.client, f"/maps/{map_id}/thumbnail/access-url")

    def get_acls(self, map_id: int) -> List[Dict[str, Any]]:
        """ACL rows of one map (bare array, returned verbatim)."""
        response_data = self.client.get(f"/maps/{map_id}/acl")
        return acl_rows(response_data)

    def create_acls(
        self,
        map_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[Dict[str, Any]]:
        """Grant permissions (principals × permissions cartesian product).

        Requires ``map:share``. The owner's own permission cannot be denied
        (422 ``OWNER_PERMISSION_NOT_DENYABLE``).
        """
        if not principals or not permissions:
            raise ValueError("principals and permissions are required.")
        payload = {
            "principals": principals,
            "permissions": permissions,
            "effect": effect,
        }
        response_data = self.client.post(f"/maps/{map_id}/acl", json=payload)
        return acl_rows(response_data)

    def delete_acl(self, map_id: int, acl_id: int) -> None:
        """Revoke one ACL entry (204)."""
        self.client.delete(f"/maps/{map_id}/acl/{acl_id}")
