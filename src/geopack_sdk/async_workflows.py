"""Async workflow definition manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .models import Workflow

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncWorkflowManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client
        self.base_url = "/workflows"

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        search_query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Workflow]:
        params = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
            **(filters or {}),
        }
        if search_query:
            params["q"] = search_query

        response_data = await self.client.get(self.base_url, params=params)
        items = response_data.get("items", [])
        if isinstance(items, list):
            return [Workflow(**item) for item in items]
        return []

    async def get(self, workflow_id: int) -> Workflow:
        response_data = await self.client.get(f"{self.base_url}/{workflow_id}")
        return Workflow(**response_data)
