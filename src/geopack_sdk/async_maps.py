"""Async saved-map manager — thin twin of :mod:`geopack_sdk.maps` (D10).

Same stored-record boundary: a map is a document, a thumbnail and an ACL; the
portal never renders one. The byte lane is ``httpx`` here instead of
``requests``, so the download helpers are async by necessity — the *write* to
disk stays synchronous (thumbnails are small and the caller asked for a file).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import GeopackAPIError
from .maps import _json_filters, _mime_type, _write_thumbnail, acl_rows
from .models import MapDocument, MintedUrl, ThumbnailFile


async def _fetch_bytes(
    client: Any, path: str, *, timeout: float = 60
) -> Tuple[bytes, str]:
    """GET a byte lane with Bearer auth through the async session."""
    url = f"{client.base_url.rstrip('/')}{path}"
    token = getattr(getattr(client, "auth", None), "token", None)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.session.get(url, headers=headers, timeout=timeout)
    if response.status_code == 404:
        raise GeopackAPIError(404, f"Resource not found: {path}")
    if not getattr(response, "is_success", False):
        raise GeopackAPIError.from_httpx_response(response)
    content = response.content
    if not content:
        raise GeopackAPIError(404, f"Empty response from {path}")
    return bytes(content), _mime_type(response)


async def read_thumbnail_async(
    client: Any, path: str, save_path: Optional[str]
) -> ThumbnailFile:
    """Shared read side for both async thumbnail managers."""
    content, mime_type = await _fetch_bytes(client, path)
    return _write_thumbnail(content, mime_type, save_path)


class AsyncMapManager:
    """Saved map documents, thumbnails and ACLs (async twin)."""

    def __init__(self, client):
        self.client = client

    async def list(
        self, page: int = 1, page_size: int = 10, **filters: Any
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(_json_filters(filters))
        response_data = await self.client.get("/maps", params=params)
        return response_data if isinstance(response_data, dict) else {}

    async def statistics(self) -> Dict[str, Any]:
        response_data = await self.client.get("/maps/statistics")
        return response_data if isinstance(response_data, dict) else {}

    async def create(self, document: Dict[str, Any]) -> MapDocument:
        if not isinstance(document, dict):
            raise ValueError("A map document must be a dict.")
        response_data = await self.client.post("/maps", json=document)
        return MapDocument.from_api(response_data)

    async def get(self, map_id: int) -> MapDocument:
        response_data = await self.client.get(f"/maps/{map_id}")
        return MapDocument.from_api(response_data)

    async def update(self, map_id: int, document: Dict[str, Any]) -> MapDocument:
        if not isinstance(document, dict):
            raise ValueError("A map document must be a dict.")
        response_data = await self.client.put(f"/maps/{map_id}", json=document)
        return MapDocument.from_api(response_data)

    async def delete(self, map_id: int) -> None:
        await self.client.delete(f"/maps/{map_id}")

    async def upload_thumbnail(self, map_id: int, file_path: str) -> Dict[str, Any]:
        """Multipart upload — the async client's kwargs pass straight to httpx."""
        if not os.path.isfile(file_path):
            raise ValueError(f"Thumbnail file not found: {file_path}")
        with open(file_path, "rb") as handle:
            files = {
                "thumbnail": (
                    os.path.basename(file_path),
                    handle.read(),
                    "application/octet-stream",
                )
            }
        response_data = await self.client.post(
            f"/maps/{map_id}/thumbnail", files=files
        )
        return response_data if isinstance(response_data, dict) else {}

    async def get_thumbnail(
        self, map_id: int, save_path: Optional[str] = None
    ) -> ThumbnailFile:
        return await read_thumbnail_async(
            self.client, f"/maps/{map_id}/thumbnail", save_path
        )

    async def get_thumbnail_access_url(self, map_id: int) -> MintedUrl:
        data = await self.client.get(f"/maps/{map_id}/thumbnail/access-url")
        if not isinstance(data, dict) or not data.get("url"):
            raise GeopackAPIError(
                502, f"Invalid mint response for map {map_id} thumbnail"
            )
        return MintedUrl(**data)

    async def get_acls(self, map_id: int) -> List[Dict[str, Any]]:
        return acl_rows(await self.client.get(f"/maps/{map_id}/acl"))

    async def create_acls(
        self,
        map_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[Dict[str, Any]]:
        if not principals or not permissions:
            raise ValueError("principals and permissions are required.")
        payload = {
            "principals": principals,
            "permissions": permissions,
            "effect": effect,
        }
        return acl_rows(await self.client.post(f"/maps/{map_id}/acl", json=payload))

    async def delete_acl(self, map_id: int, acl_id: int) -> None:
        await self.client.delete(f"/maps/{map_id}/acl/{acl_id}")
