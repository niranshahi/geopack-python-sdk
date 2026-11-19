"""Workflow definition tool handlers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from geopack_sdk import GeopackClient

from ..sanitize.workflow_payload import (
    sanitize_workflow_for_mcp,
    sanitize_workflow_list_for_mcp,
    strip_graph_ui_keys,
)
from ..serialize import to_jsonable


def list_workflows(
    client: GeopackClient,
    *,
    page: int = 1,
    page_size: int = 20,
    search_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    items = client.workflows.list(
        page=page,
        page_size=page_size,
        search_query=search_query,
    )
    return sanitize_workflow_list_for_mcp(to_jsonable(items))


def get_workflow_for_mcp(
    client: GeopackClient,
    workflow_id: int,
    include_params: bool = False,
    *,
    include_graph: bool = False,
) -> Dict[str, Any]:
    """Get workflow metadata; extract parameters from graphJson before omitting it."""
    workflow = client.workflows.get(workflow_id)
    result = to_jsonable(workflow)

    if include_params:
        # extract_params reads graphJson on the in-memory Workflow model
        result["parameters"] = to_jsonable(client.workflows.extract_params(workflow))

    return sanitize_workflow_for_mcp(result, include_graph=include_graph)


def get_workflow_spec(
    client: GeopackClient,
    workflow_id: int,
    *,
    budget_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """Project a saved workflow into the model-facing wf-spec (read-only).

    ``POST /workflows/compile-spec {workflowId}`` never persists anything: this is
    the inspection lane, not the authoring one. The backend projection is already
    position-free; ``strip_graph_ui_keys`` keeps it that way if the payload grows.
    """
    payload = client.workflows.compile_spec(
        workflow_id=workflow_id,
        budget_chars=budget_chars,
    )
    return strip_graph_ui_keys(to_jsonable(payload))
