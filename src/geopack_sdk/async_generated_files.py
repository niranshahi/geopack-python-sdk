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

    async def iter_generated_files(
        self,
        page_size: int = 50,
        search_query: Optional[str] = None,
        order_by: str = "createdAt",
        order_direction: str = "desc",
    ):
        """Iterate over all generated files by auto-fetching successive pages asynchronously."""
        current_page = 1
        while True:
            resp = await self.list(
                page=current_page,
                page_size=page_size,
                search_query=search_query,
                order_by=order_by,
                order_direction=order_direction,
            )
            if not resp.items:
                break
            for item in resp.items:
                yield item
            if len(resp.items) < page_size:
                break
            current_page += 1

    async def delete(self, file_id: int) -> None:

        await self.client.delete(f"{self.base_url}/{file_id}")
