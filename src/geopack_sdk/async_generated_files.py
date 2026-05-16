"""Async generated file manager (list; streaming download use sync client)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .models import GeneratedFileListResponse

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncGeneratedFileManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client
        self.base_url = "/generated-files"

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        search_query: Optional[str] = None,
        order_by: str = "createdAt",
        order_direction: str = "desc",
    ) -> GeneratedFileListResponse:
        params = {
            "page": page,
            "pageSize": page_size,
            "orderBy": order_by,
            "orderDirection": order_direction,
        }
        if search_query:
            params["searchQuery"] = search_query.strip()
        response_data = await self.client.get(self.base_url, params=params)
        return GeneratedFileListResponse(**response_data)

    async def delete(self, file_id: int) -> None:
        await self.client.delete(f"{self.base_url}/{file_id}")
