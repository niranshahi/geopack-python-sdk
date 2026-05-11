import os
import time
from typing import Any, Dict, List, Optional, Union

class WorkflowRunManager:
    """Manager for Workflow Executions (Runs)."""

    def __init__(self, client):
        self.client = client
        self.base_url = "/workflow-runs"

    def list(
        self,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """List workflow runs.
        
        REST API: `GET /api/workflow-runs`
        """
        params = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
            **(filters or {})
        }
        response = self.client.get(self.base_url, params=params)
        return response.get("items", [])

    def get(self, run_id: int) -> Dict[str, Any]:
        """Get detailed status of a workflow run, including node-level progress.
        
        REST API: `GET /api/workflow-runs/:id`
        """
        return self.client.get(f"{self.base_url}/{run_id}")

    def get_artifacts(self, run_id: int) -> List[Dict[str, Any]]:
        """Get the list of artifacts produced by a workflow run."""
        response = self.client.get(f"{self.base_url}/{run_id}/artifacts")
        items = response.get("items", [])
        
        for item in items:
            # Frontend and API results may store path in data object or root
            data = item.get("data") or {}
            
            # Priority: pathOrUri (from terminal logs), path, or filePath
            file_path = item.get("pathOrUri") or data.get("pathOrUri") or \
                        data.get("path") or item.get("filePath")
            
            dataset_id = data.get("datasetId") or item.get("datasetId")
            
            if dataset_id:
                item["datasetId"] = dataset_id
                item["display_name"] = f"Dataset #{dataset_id}"
            elif file_path:
                item["filePath"] = file_path
                item["display_name"] = os.path.basename(file_path)
            else:
                item["display_name"] = f"Artifact {item.get('id')}"
                
        return items

    def get_logs(self, run_id: int) -> Dict[str, Any]:
        """Get execution logs, errors, and node-level statuses.
        
        This mimics the log construction logic in WorkflowRunViewerCore.vue.
        """
        run = self.get(run_id)
        logs = {
            "workflowId": run.get("workflowId"),
            "status": run.get("status"),
            "startedAt": run.get("createdAt"),
            "finishedAt": run.get("updatedAt"),
        }

        # Add error info if failed
        if run.get("status") == "failed" and run.get("error"):
            logs["error"] = run.get("error")

        # Add stats if available
        if run.get("stats"):
            logs["stats"] = run.get("stats")

        # Add node statuses from graphSnapshot
        snapshot = run.get("graphSnapshot") or {}
        node_statuses = snapshot.get("nodeStatuses")
        if node_statuses:
            logs["nodeStatuses"] = node_statuses

        # Add execution results (this contains the file paths shown in your screenshot)
        if run.get("results"):
            logs["results"] = run.get("results")

        return logs

    def submit(
        self,
        workflow_id: int,
        params: Optional[Dict[str, Any]] = None,
        override_datastore_id: Optional[int] = None,
        wait: bool = True,
        polling_interval: int = 2
    ) -> Dict[str, Any]:
        """Submit a workflow for execution.
        
        REST API: `POST /api/workflow-runs`
        
        Args:
            workflow_id: ID of the workflow model to run.
            params: Dictionary of runtime parameters.
            override_datastore_id: Optional ID to override default storage.
            wait: If True, waits for the background task to complete.
            polling_interval: Seconds between status checks.
        """
        payload = {
            "workflowId": workflow_id,
            "params": params or {},
        }
        if override_datastore_id:
            payload["overrideDataStoreId"] = override_datastore_id

        response = self.client.post(self.base_url, json=payload)
        
        if not wait:
            return response

        # If waiting, use the taskId returned in the response
        task_id = response.get("taskId")
        if not task_id:
            return response
            
        self.client.tasks.wait(task_id, interval=polling_interval, quiet=True)
        
        # Fetch final run state, artifacts, and logs
        run_id = response.get("workflowRunId")
        final_state = self.get(run_id)
        final_state["artifacts"] = self.get_artifacts(run_id)
        final_state["logs"] = self.get_logs(run_id)
        
        return final_state

    def cancel(self, run_id: int) -> bool:
        """Cancel a running workflow.
        
        REST API: `POST /api/workflow-runs/:id/cancel`
        """
        self.client.post(f"{self.base_url}/{run_id}/cancel", json={})
        return True

    def download_artifact(
        self,
        run_id: int,
        artifact_id: int,
        local_path: str,
        chunk_size: int = 8192
    ) -> str:
        """Download an artifact (output file) produced by a workflow node.
        
        REST API: `GET /api/workflow-runs/:runId/artifacts/:artifactId/download`
        """
        url = f"{self.base_url}/{run_id}/artifacts/{artifact_id}/download"
        
        # Use common download logic from client session
        response = self.client.session.get(f"{self.client.base_url}{url}", stream=True)
        response.raise_for_status()

        # Extract filename from headers or response
        content_disposition = response.headers.get("Content-Disposition")
        filename = None
        
        if content_disposition and "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[1].strip('"')
        
        # Fallback to a generic name if still None
        if not filename:
            filename = f"artifact_{artifact_id}"

        if os.path.isdir(local_path):
            target_file = os.path.join(local_path, filename)
        else:
            target_file = local_path

        print(f"Downloading workflow artifact to {target_file}...")
        with open(target_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                f.write(chunk)

        return os.path.abspath(target_file)
