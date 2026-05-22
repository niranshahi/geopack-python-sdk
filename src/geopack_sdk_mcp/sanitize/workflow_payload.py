"""Strip heavy workflow graph blobs from MCP tool JSON (parameters are extracted first)."""

from __future__ import annotations

from typing import Any, Dict, List, Union

# Runtime parameters are parsed server-side from graphJson via WorkflowManager.extract_params
# before these keys are removed from tool output.
_GRAPH_BLOB_KEYS = ("graphJson", "graph_json", "graphSnapshot", "graph_snapshot")


def omit_workflow_graph_blobs(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove graph definitions from a workflow or workflow-run dict for LLM-safe JSON."""
    if not isinstance(payload, dict):
        return payload

    out = dict(payload)
    omitted = False
    for key in _GRAPH_BLOB_KEYS:
        if key in out and out[key] is not None:
            out.pop(key, None)
            omitted = True

    if omitted:
        # Tell the model to use `parameters` from get_workflow(include_params=true), not graphJson.
        out.setdefault(
            "graphOmitted",
            "graphJson/graphSnapshot removed from MCP output; use parameters array or list/get workflow tools",
        )

    return out


def sanitize_workflow_for_mcp(
    payload: Union[Dict[str, Any], Any],
    *,
    include_graph: bool = False,
) -> Dict[str, Any]:
    """Workflow definition safe for MCP tools (graph stripped by default)."""
    if not isinstance(payload, dict):
        return payload  # type: ignore[return-value]
    if include_graph:
        return payload
    return omit_workflow_graph_blobs(payload)


def sanitize_workflow_list_for_mcp(
    items: List[Any],
    *,
    include_graph: bool = False,
) -> List[Dict[str, Any]]:
    """List workflows without per-item graphJson."""
    out: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            row = dict(item)
        elif hasattr(item, "model_dump"):
            row = item.model_dump(mode="json")
        else:
            continue
        out.append(
            sanitize_workflow_for_mcp(row, include_graph=include_graph)
            if isinstance(row, dict)
            else row
        )
    return out


def sanitize_workflow_submit_response(payload: Any) -> Dict[str, Any]:
    """Minimal submit response for MCP (workflowRunId, taskId, status)."""
    if not isinstance(payload, dict):
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        else:
            return {"status": str(payload)}

    keep = ("workflowRunId", "taskId", "status")
    return {k: payload[k] for k in keep if k in payload}


def sanitize_workflow_run_for_mcp(payload: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    """Workflow run JSON without graph snapshot blob."""
    if not isinstance(payload, dict):
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        else:
            return payload  # type: ignore[return-value]
    return omit_workflow_graph_blobs(payload)
