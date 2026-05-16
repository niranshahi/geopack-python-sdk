import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .models import (
    WorkflowRun,
    WorkflowRunArtifact,
    WorkflowRunListResponse,
    WorkflowRunSubmitResponse,
)
from .tasks import (
    task_log_entries_needing_review,
    task_message_badge_severity,
    task_message_info,
)

if TYPE_CHECKING:
    from .client import GeopackClient


def inspect_workflow_run_outcome(
    client: "GeopackClient",
    task_id: str,
    run_id: Optional[int] = None,
) -> Optional[int]:
    """Inspect a workflow run via task log and workflow-run record (portal parity).

    Two layers:
    1. Background task ``workflow:run`` — messages, ``task.status``, ``task.results``
    2. :class:`WorkflowRun` — run status, node statuses, artifacts

    A run may show ``succeeded`` while the task log still has warn/error lines;
    always check both.

    Args:
        client: Authenticated :class:`GeopackClient`.
        task_id: BullMQ task id from ``workflow_runs.submit`` (``taskId``).
        run_id: Optional ``workflowRunId``; resolved from task input/results if omitted.

    Returns:
        Resolved workflow run id, or ``None`` if it could not be determined.
    """
    task = client.tasks.get_status(task_id)
    info = task_message_info(task)
    severity = task_message_badge_severity(task)

    print(
        f"Task {task_id} ({task.taskType}): status={task.status}, "
        f"badge={severity}, messages={info.count}"
    )

    if severity in ("error", "warn"):
        print(
            "  Task log has warn/error lines "
            "(may appear even when run status is succeeded):"
        )
        for line in task_log_entries_needing_review(task):
            print(
                f"    [{line.get('level')}] {line.get('timestamp')} "
                f"{line.get('message')}"
            )

    if task.results:
        print(f"  task.results: {task.results}")

    wr_id = run_id
    if wr_id is None and task.inputParameters:
        wr_id = task.inputParameters.get("workflowRunId")
    if wr_id is None and isinstance(task.results, dict):
        wr_id = task.results.get("workflowRunId")

    if wr_id is None:
        print("  (No workflowRunId — pass run_id from submit response)")
        return None

    run = client.workflow_runs.get(wr_id)
    logs = client.workflow_runs.get_logs(wr_id)
    print(f"\nWorkflowRun #{wr_id}: status={run.status}")

    if logs.get("error"):
        print(f"  run error: {logs['error']}")
    node_statuses = logs.get("nodeStatuses") or {}
    failed_nodes = {
        k: v
        for k, v in node_statuses.items()
        if str(v).lower() in ("failed", "error")
    }
    if failed_nodes:
        print(f"  failed nodes: {failed_nodes}")

    if run.artifacts:
        print(f"  artifacts: {len(run.artifacts)}")

    return wr_id

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
    ) -> WorkflowRunListResponse:
        """List workflow runs.
        
        REST API: `GET /api/workflow-runs`
        """
        params = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
            **(filters or {})
        }
        response_data = self.client.get(self.base_url, params=params)
        return WorkflowRunListResponse(**response_data)

    def get(self, run_id: int) -> WorkflowRun:
        """Get detailed status of a workflow run, including node-level progress.
        
        REST API: `GET /api/workflow-runs/:id`
        """
        response_data = self.client.get(f"{self.base_url}/{run_id}")
        
        # Proactively fetch artifacts if not in response
        if "artifacts" not in response_data or not response_data["artifacts"]:
            try:
                # Use raw fetch to avoid recursion or model overhead
                art_resp = self.client.get(f"{self.base_url}/{run_id}/artifacts")
                items = art_resp.get("items", [])
                if items:
                    response_data["artifacts"] = items
            except Exception:
                pass 
                
        return WorkflowRun(**response_data)

    def get_artifacts(self, run_id: int) -> List[WorkflowRunArtifact]:
        """Get the list of artifacts produced by a workflow run."""
        response = self.client.get(f"{self.base_url}/{run_id}/artifacts")
        items = response.get("items", [])
        
        results = []
        for item in items:
            # Frontend and API results may store path in data object or root
            data = item.get("data") or {}
            
            # Safely parse JSON if data is a string
            if isinstance(data, str):
                import json
                try:
                    data = json.loads(data)
                except Exception:
                    data = {}
            
            # Priority: pathOrUri (from terminal logs), path, or filePath
            file_path = item.get("pathOrUri") or data.get("pathOrUri") or \
                        data.get("path") or item.get("filePath")
            
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

    def get_logs(self, run_id: int) -> Dict[str, Any]:
        """Get execution logs, errors, and node-level statuses."""
        # Use raw fetch to avoid recursion
        run_data = self.client.get(f"{self.base_url}/{run_id}")
        
        logs = {
            "workflowId": run_data.get("workflowId"),
            "status": run_data.get("status"),
            "startedAt": run_data.get("createdAt"),
            "finishedAt": run_data.get("updatedAt"),
        }

        # Add error info if failed
        if run_data.get("status") == "failed" and run_data.get("error"):
            logs["error"] = run_data.get("error")

        # Add stats if available
        if run_data.get("stats"):
            logs["stats"] = run_data.get("stats")

        # Add node statuses from graphSnapshot
        snapshot = run_data.get("graphSnapshot") or {}
        node_statuses = snapshot.get("nodeStatuses")
        if node_statuses:
            logs["nodeStatuses"] = node_statuses

        # Add execution results
        if run_data.get("results"):
            logs["results"] = run_data.get("results")

        return logs

    def submit(
        self,
        workflow_id: int,
        params: Optional[Dict[str, Any]] = None,
        override_datastore_id: Optional[int] = None,
        wait: bool = True,
        polling_interval: int = 2
    ) -> Union[WorkflowRun, WorkflowRunSubmitResponse]:
        """Submit a workflow for execution.
        
        REST API: `POST /api/workflow-runs`
        
        Args:
            workflow_id: ID of the workflow model to run.
            params: Dictionary of runtime parameters.
            override_datastore_id: Optional ID to override default storage.
            wait: If True, waits for the background task to complete and returns
                the final :class:`WorkflowRun`. If False, returns
                :class:`WorkflowRunSubmitResponse` (``workflowRunId``, ``taskId``,
                run ``status`` e.g. ``queued`` — not a :class:`TaskResult`).
            polling_interval: Seconds between status checks.
        """
        payload = {
            "workflowId": workflow_id,
            "params": params or {},
        }
        if override_datastore_id:
            payload["overrideDataStoreId"] = override_datastore_id

        response_data = self.client.post(self.base_url, json=payload)
        
        if not wait:
            return WorkflowRunSubmitResponse(**response_data)

        # If waiting, use the taskId returned in the response
        task_id = response_data.get("taskId")
        if not task_id:
            return WorkflowRunSubmitResponse(**response_data)
            
        self.client.tasks.wait(task_id, interval=polling_interval, quiet=True)
        
        # Fetch final run state
        run_id = response_data.get("workflowRunId")
        return self.get(run_id)

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
