"""Workflow run tool handlers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from geopack_sdk import GeopackClient

from ..ordering import validate_sort_args
from ..sanitize.workflow_payload import sanitize_workflow_run_for_mcp
from ..serialize import to_jsonable

#: List rows are metadata only: a run carries input/output/logs/artifacts and the
#: model must read those through get_workflow_run, not from the index.
_RUN_LIST_KEYS = (
    "id",
    "workflowId",
    "status",
    "taskId",
    "submittedBy",
    "createdAt",
    "updatedAt",
    "startedAt",
    "finishedAt",
    "errorMessage",
)
RUN_DEFAULT_LIMIT = 20
RUN_MAX_LIMIT = 100

#: Server sort whitelist for ``GET /workflow-runs`` (``sortBy``).
ALLOWED_RUN_ORDER_FIELDS = (
    "id",
    "workflow.name",
    "submitter",
    "taskId",
    "status",
    "startedAt",
    "finishedAt",
    "createdAt",
    "updatedAt",
)


def _run_row(item: Any) -> Dict[str, Any]:
    row = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
    return {key: row[key] for key in _RUN_LIST_KEYS if row.get(key) is not None}


def list_workflow_runs(
    client: GeopackClient,
    *,
    workflow_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = RUN_DEFAULT_LIMIT,
    offset: int = 0,
    order_by: Optional[str] = None,
    order_direction: Optional[str] = None,
) -> Dict[str, Any]:
    """List the caller's workflow runs (the answer lane for "what did I start")."""
    sort_field, sort_direction = validate_sort_args(
        order_by,
        order_direction,
        allowed=ALLOWED_RUN_ORDER_FIELDS,
    )
    page_size = max(1, min(int(limit), RUN_MAX_LIMIT))
    effective_offset = max(0, int(offset))

    # ``WorkflowRunManager.list`` composes {limit, offset: (page-1)*pageSize,
    # **filters}; passing offset through filters keeps the server's raw paging
    # contract instead of snapping the caller to a page boundary.
    filters: Dict[str, Any] = {"offset": effective_offset}
    if workflow_id is not None:
        filters["workflowId"] = int(workflow_id)
    if status:
        filters["status"] = str(status).strip()

    response = client.workflow_runs.list(
        page=1,
        page_size=page_size,
        filters=filters,
        order_by=sort_field,
        order_direction=sort_direction,
    )
    items: List[Dict[str, Any]] = [_run_row(item) for item in response.items]

    total = response.total if response.total is not None else (response.totalItems or len(items))
    payload: Dict[str, Any] = {
        "items": items,
        "totalItems": total,
        "currentPage": (effective_offset // page_size) + 1,
        "totalPages": max(1, -(-total // page_size)),
        "pageSize": page_size,
        "hint": (
            "Call geopack_sdk_get_workflow_run for a run's artifacts, node progress and "
            "result summary."
        ),
    }
    if sort_field:
        payload["orderBy"] = sort_field
        payload["orderDirection"] = sort_direction or "asc"
    return payload


def get_workflow_run(client: GeopackClient, run_id: int) -> Dict[str, Any]:
    result = client.workflow_runs.get(run_id)
    return sanitize_workflow_run_for_mcp(to_jsonable(result))


def download_workflow_artifact(
    client: GeopackClient,
    run_id: int,
    artifact_id: int,
    save_path: str,
) -> Dict[str, Any]:
    """Download a workflow artifact (output file) to local disk.
    
    Args:
        client: Authenticated GeopackClient
        run_id: ID of the workflow run
        artifact_id: ID of the artifact to download
        save_path: Local directory or file path to save to
        
    Returns:
        Dict with savedPath (resolved absolute path) and file metadata
    """
    resolved_path = os.path.abspath(
        client.workflow_runs.download_artifact(run_id, artifact_id, save_path)
    )
    from ..context import register_temp_file
    register_temp_file(resolved_path)

    return {
        "workflowRunId": run_id,
        "artifactId": artifact_id,
        "savedPath": resolved_path,
    }

