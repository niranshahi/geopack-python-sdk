"""Async workflow run manager."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .models import (
    Dataset,
    WorkflowRun,
    WorkflowRunArtifact,
    WorkflowRunListResponse,
    WorkflowRunSubmitResponse,
)

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncWorkflowRunManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client
        self.base_url = "/workflow-runs"

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> WorkflowRunListResponse:
        params = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
            **(filters or {}),
        }
        response_data = await self.client.get(self.base_url, params=params)
        return WorkflowRunListResponse(**response_data)

    async def iter_workflow_runs(
        self,
        page_size: int = 50,
        filters: Optional[Dict[str, Any]] = None,
    ):
        """Iterate over all workflow runs by auto-fetching successive pages asynchronously."""
        current_page = 1
        while True:
            resp = await self.list(
                page=current_page,
                page_size=page_size,
                filters=filters,
            )
            if not resp.items:
                break
            for item in resp.items:
                yield item
            if len(resp.items) < page_size:
                break
            current_page += 1

    async def get(self, run_id: int) -> WorkflowRun:

        response_data = await self.client.get(f"{self.base_url}/{run_id}")

        if "artifacts" not in response_data or not response_data["artifacts"]:
            try:
                art_resp = await self.client.get(
                    f"{self.base_url}/{run_id}/artifacts"
                )
                items = art_resp.get("items", [])
                if items:
                    response_data["artifacts"] = items
            except Exception:
                pass

        return WorkflowRun(**response_data)

    async def get_logs(self, run_id: int) -> Dict[str, Any]:
        run_data = await self.client.get(f"{self.base_url}/{run_id}")
        logs: Dict[str, Any] = {
            "workflowId": run_data.get("workflowId"),
            "status": run_data.get("status"),
            "startedAt": run_data.get("createdAt"),
            "finishedAt": run_data.get("updatedAt"),
        }
        if run_data.get("status") == "failed" and run_data.get("error"):
            logs["error"] = run_data.get("error")
        if run_data.get("stats"):
            logs["stats"] = run_data.get("stats")
        snapshot = run_data.get("graphSnapshot") or {}
        node_statuses = snapshot.get("nodeStatuses")
        if node_statuses:
            logs["nodeStatuses"] = node_statuses
        if run_data.get("results"):
            logs["results"] = run_data.get("results")
        return logs

    async def submit(
        self,
        workflow_id: int,
        params: Optional[Dict[str, Any]] = None,
        override_datastore_id: Optional[int] = None,
        wait: bool = True,
        polling_interval: int = 2,
    ) -> Union[WorkflowRun, WorkflowRunSubmitResponse]:
        payload: Dict[str, Any] = {
            "workflowId": workflow_id,
            "params": params or {},
        }
        if override_datastore_id:
            payload["overrideDataStoreId"] = override_datastore_id

        response_data = await self.client.post(self.base_url, json=payload)

        if not wait:
            return WorkflowRunSubmitResponse(**response_data)

        task_id = response_data.get("taskId")
        if not task_id:
            return WorkflowRunSubmitResponse(**response_data)

        await self.client.tasks.wait(
            task_id, interval=polling_interval, quiet=True
        )
        run_id = response_data.get("workflowRunId")
        return await self.get(run_id)

    async def cancel(self, run_id: int) -> bool:
        await self.client.post(f"{self.base_url}/{run_id}/cancel", json={})
        return True

    async def get_artifacts(self, run_id: int) -> List[WorkflowRunArtifact]:
        response = await self.client.get(f"{self.base_url}/{run_id}/artifacts")
        items = response.get("items", [])
        results: List[WorkflowRunArtifact] = []
        for item in items:
            data = item.get("data") or {}
            if isinstance(data, str):
                import json

                try:
                    data = json.loads(data)
                except Exception:
                    data = {}
            file_path = (
                item.get("pathOrUri")
                or data.get("pathOrUri")
                or data.get("path")
                or item.get("filePath")
            )
            dataset_id = data.get("datasetId") or item.get("datasetId")
            artifact_dict = {**item}
            if dataset_id:
                artifact_dict["datasetId"] = dataset_id
                artifact_dict["display_name"] = f"Dataset #{dataset_id}"
            elif file_path:
                artifact_dict["filePath"] = file_path
                artifact_dict["display_name"] = os.path.basename(file_path)
            else:
                artifact_dict["display_name"] = f"Artifact {item.get('id')}"
            results.append(WorkflowRunArtifact(**artifact_dict))
        return results

    async def convert_artifact_to_dataset(
        self,
        run_id: int,
        artifact_id: int,
        *,
        name: str,
        data_store_id: int,
        description: Optional[str] = None,
        add_to_map: bool = False,
    ) -> Dataset:
        """Convert a workflow run artifact into a portal dataset (async).

        REST API: ``POST /api/workflow-runs/:runId/artifacts/:artifactId/convert-to-dataset``
        """
        payload: Dict[str, Any] = {
            "name": name,
            "dataStoreId": data_store_id,
            "addToMap": add_to_map,
        }
        if description is not None:
            payload["description"] = description
        url = f"{self.base_url}/{run_id}/artifacts/{artifact_id}/convert-to-dataset"
        response_data = await self.client.post(url, json=payload)
        return Dataset(**response_data)
