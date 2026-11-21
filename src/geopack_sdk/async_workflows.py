"""Async workflow definition manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .models import Workflow, WorkflowParameter
from .workflows import extract_workflow_params

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
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Workflow]:
        params = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if order_by:
            params["sortBy"] = order_by
        if order_direction:
            params["sortOrder"] = order_direction
        params.update(filters or {})
        if search_query:
            params["q"] = search_query

        response_data = await self.client.get(self.base_url, params=params)
        items = response_data.get("items", [])
        if isinstance(items, list):
            return [Workflow(**item) for item in items]
        return []

    async def iter_workflows(
        self,
        page_size: int = 50,
        search_query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ):
        """Iterate over all workflow definitions by auto-fetching successive pages asynchronously."""
        current_page = 1
        while True:
            items = await self.list(
                page=current_page,
                page_size=page_size,
                search_query=search_query,
                filters=filters,
            )
            if not items:
                break
            for item in items:
                yield item
            if len(items) < page_size:
                break
            current_page += 1

    async def get(self, workflow_id: int) -> Workflow:

        response_data = await self.client.get(f"{self.base_url}/{workflow_id}")
        return Workflow(**response_data)

    def extract_params(
        self, workflow: Union[Workflow, Dict[str, Any]]
    ) -> List[WorkflowParameter]:
        """Async twin of :meth:`WorkflowManager.extract_params`.

        Pure computation over the graph blob — there is no I/O, so this is
        deliberately **not** a coroutine: ``await`` it and you get a TypeError,
        which is the honest signal that nothing is waiting.
        """
        return extract_workflow_params(workflow)

    async def get_operations(self) -> List[Dict[str, Any]]:
        """Async twin of :meth:`WorkflowManager.get_operations`."""
        response = await self.client.get(f"{self.base_url}/operations")
        return response.get("items", [])

    async def create(self, payload: Dict[str, Any]) -> Workflow:
        """Async twin of :meth:`WorkflowManager.create`."""
        response_data = await self.client.post(self.base_url, json=payload)
        return Workflow(**response_data)

    async def update(self, workflow_id: int, payload: Dict[str, Any]) -> Workflow:
        """Async twin of :meth:`WorkflowManager.update`."""
        response_data = await self.client.put(
            f"{self.base_url}/{workflow_id}", json=payload
        )
        return Workflow(**response_data)

    async def delete(self, workflow_id: int, with_runs: bool = False) -> Dict[str, Any]:
        """Async twin of :meth:`WorkflowManager.delete` (run cascade opt-in)."""
        endpoint = f"{self.base_url}/{workflow_id}"
        if with_runs:
            response_data = await self.client.delete(
                endpoint, params={"withRuns": "true"}
            )
        else:
            response_data = await self.client.delete(endpoint)
        return response_data if isinstance(response_data, dict) else {}

    # --- Statistics, spec compilation and tool manifest (slice 015) ----------

    async def get_statistics(self) -> Dict[str, Any]:
        """Async twin of :meth:`WorkflowManager.get_statistics`."""
        response_data = await self.client.get(f"{self.base_url}/statistics")
        return response_data if isinstance(response_data, dict) else {}

    async def compile_spec(
        self,
        spec: Optional[Dict[str, Any]] = None,
        *,
        workflow_id: Optional[int] = None,
        budget_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Async twin of :meth:`WorkflowManager.compile_spec` (read-only)."""
        if (spec is None) == (workflow_id is None):
            raise ValueError("Provide exactly one of spec= or workflow_id=.")
        body: Dict[str, Any] = {}
        if spec is not None:
            body["spec"] = spec
        if workflow_id is not None:
            body["workflowId"] = int(workflow_id)
        if budget_chars is not None:
            body["budgetChars"] = int(budget_chars)
        response_data = await self.client.post(
            f"{self.base_url}/compile-spec", json=body
        )
        return response_data if isinstance(response_data, dict) else {}

    async def get_tool_manifest(self, workflow_id: int) -> Dict[str, Any]:
        """Async twin of :meth:`WorkflowManager.get_tool_manifest` (verbatim)."""
        response_data = await self.client.get(
            f"{self.base_url}/{workflow_id}/tool-manifest"
        )
        return response_data if isinstance(response_data, dict) else {}
