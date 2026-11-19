"""Async print-layout manager — thin twin of :mod:`geopack_sdk.print_layouts`."""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

from .async_maps import read_thumbnail_async
from .exceptions import GeopackAPIError
from .maps import acl_rows
from .models import MintedUrl, PrintLayout, ThumbnailFile


class AsyncPrintLayoutManager:
    """Print-layout template records, thumbnails and ACLs (async twin)."""

    def __init__(self, client):
        self.client = client

    async def list(
        self, page: int = 1, page_size: int = 20, **filters: Any
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "limit": page_size,
            "offset": max(page - 1, 0) * page_size,
        }
        for key, value in filters.items():
            if value is not None:
                params[key] = value
        response_data = await self.client.get("/print-layouts", params=params)
        return response_data if isinstance(response_data, dict) else {}

    async def get(self, layout_id: int) -> PrintLayout:
        response_data = await self.client.get(f"/print-layouts/{layout_id}")
        return PrintLayout.from_api(response_data)

    async def create(self, payload: Dict[str, Any]) -> PrintLayout:
        if not isinstance(payload, dict):
            raise ValueError("A print layout payload must be a dict.")
        response_data = await self.client.post("/print-layouts", json=payload)
        return PrintLayout.from_api(response_data)

    async def update(
        self, layout_id: int, patch: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("A print layout patch must be a dict.")
        response_data = await self.client.put(
            f"/print-layouts/{layout_id}", json=patch
        )
        return response_data if isinstance(response_data, dict) else {}

    async def delete(self, layout_id: int) -> Dict[str, Any]:
        response_data = await self.client.delete(f"/print-layouts/{layout_id}")
        return response_data if isinstance(response_data, dict) else {}

    async def upload_thumbnail(
        self,
        layout_id: int,
        file_path: Optional[str] = None,
        *,
        thumbnail_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """JSON base64 upload — same quirk as the sync manager."""
        if (file_path is None) == (thumbnail_base64 is None):
            raise ValueError("Pass exactly one of file_path= or thumbnail_base64=.")
        if file_path is not None:
            if not os.path.isfile(file_path):
                raise ValueError(f"Thumbnail file not found: {file_path}")
            with open(file_path, "rb") as handle:
                thumbnail_base64 = base64.b64encode(handle.read()).decode("ascii")
        response_data = await self.client.post(
            f"/print-layouts/{layout_id}/thumbnail",
            json={"thumbnailBase64": thumbnail_base64},
        )
        return response_data if isinstance(response_data, dict) else {}

    async def get_thumbnail(
        self, layout_id: int, save_path: Optional[str] = None
    ) -> ThumbnailFile:
        return await read_thumbnail_async(
            self.client, f"/print-layouts/{layout_id}/thumbnail", save_path
        )

    async def get_thumbnail_access_url(self, layout_id: int) -> MintedUrl:
        data = await self.client.get(
            f"/print-layouts/{layout_id}/thumbnail/access-url"
        )
        if not isinstance(data, dict) or not data.get("url"):
            raise GeopackAPIError(
                502, f"Invalid mint response for layout {layout_id} thumbnail"
            )
        return MintedUrl(**data)

    async def get_acls(self, layout_id: int) -> List[Dict[str, Any]]:
        return acl_rows(await self.client.get(f"/print-layouts/{layout_id}/acl"))

    async def create_acls(
        self,
        layout_id: int,
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
        return acl_rows(
            await self.client.post(f"/print-layouts/{layout_id}/acl", json=payload)
        )

    async def delete_acl(self, layout_id: int, acl_id: int) -> None:
        await self.client.delete(f"/print-layouts/{layout_id}/acl/{acl_id}")
