"""Workflow submission tool handlers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from geopack_sdk import GeopackClient

from ..sanitize.workflow_payload import sanitize_workflow_submit_response
from ..serialize import to_jsonable


def submit_workflow(
    client: GeopackClient,
    workflow_id: int,
    params: Dict[str, Any],
    override_datastore_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Submit a workflow for execution without waiting.

    Returns workflowRunId, taskId, and status only (LLM-safe).
    """
    response = client.workflow_runs.submit(
        workflow_id=workflow_id,
        params=params,
        override_datastore_id=override_datastore_id,
        wait=False,
    )
    return sanitize_workflow_submit_response(to_jsonable(response))
