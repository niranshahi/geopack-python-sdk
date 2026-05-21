"""Workflow submission tool handlers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from geopack_sdk import GeopackClient

from ..sanitize.task_results import sanitize_task_payload
from ..serialize import to_jsonable


def submit_workflow(
    client: GeopackClient,
    workflow_id: int,
    params: Dict[str, Any],
    override_datastore_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Submit a workflow for execution without waiting.
    
    Args:
        client: Authenticated GeopackClient
        workflow_id: ID of the workflow to execute
        params: Dictionary of runtime parameters for the workflow
        override_datastore_id: Optional datastore ID override
        
    Returns:
        WorkflowRunSubmitResponse JSON with workflowRunId, taskId, status
    """
    response = client.workflow_runs.submit(
        workflow_id=workflow_id,
        params=params,
        override_datastore_id=override_datastore_id,
        wait=False,  # Non-blocking for MCP
    )
    return sanitize_task_payload(to_jsonable(response))


def get_workflow_with_params(
    client: GeopackClient,
    workflow_id: int,
    include_params: bool = False,
) -> Dict[str, Any]:
    """Get workflow definition with optional parameter extraction.
    
    Args:
        client: Authenticated GeopackClient
        workflow_id: ID of the workflow
        include_params: If True, extract and include runtime parameters
        
    Returns:
        Workflow JSON with optional 'parameters' array
    """
    workflow = client.workflows.get(workflow_id)
    result = to_jsonable(workflow)
    
    if include_params:
        params = client.workflows.extract_params(workflow)
        result["parameters"] = to_jsonable(params)
    
    return result
