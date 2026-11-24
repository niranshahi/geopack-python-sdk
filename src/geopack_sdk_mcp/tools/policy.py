"""MCP-enforced safety policy (independent of host agent prompts).

Slice 021 §3 turned this module from a "we never registered a delete" posture
into a **stated** contract:

* ``mutatingTools`` — every tool that changes portal state, with its consent
  mode and whether it has a dry run;
* ``localWrites`` — tools that write to the MCP **host** filesystem (not a
  portal mutation, but the host should still know);
* ``unavailable`` — the operations that deliberately have no tool.

``TOOL_POLICY`` is the single registry: one entry per registered tool. The
completeness test in ``tests/test_mcp_write_tools.py`` compares it against the
live FastMCP surface, so adding a tool without classifying it fails the suite —
that is deliberate (maintenance note, slice 021).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from geopack_sdk import GeopackClient
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import read_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_result

#: Tools that change portal state. ``dryRun`` is the mode that writes nothing
#: (``False`` when there is none); ``consent`` is how loudly the description
#: must ask: ``explicit`` = describe every effect and get a yes,
#: ``brief`` = confirm before cancelling.
_MUTATING_TOOLS: Dict[str, Dict[str, Any]] = {
    "geopack_sdk_upload_dataset": {
        "consent": "explicit",
        "dryRun": False,
        "changes": "Creates datasets and uploads file bytes",
    },
    "geopack_sdk_submit_workflow": {
        "consent": "explicit",
        "dryRun": False,
        "changes": "Starts a workflow run (writes datasets/files per the graph)",
    },
    "geopack_sdk_run_analysis": {
        "consent": "explicit",
        "dryRun": False,
        "changes": "Starts a workflow run through the analysis-tool surface",
    },
    "geopack_sdk_submit_edit_document": {
        "consent": "explicit",
        "dryRun": "validate",
        "changes": "mode='apply' writes records, including related datasets",
    },
    "geopack_sdk_cancel_task": {
        "consent": "brief",
        "dryRun": False,
        "changes": "Requests cancellation of a running task; completed work stays",
    },
}

#: Tools that write to the MCP host filesystem (a saved thumbnail/download).
_LOCAL_WRITE_TOOLS = (
    "geopack_sdk_get_dataset_thumbnail",
    "geopack_sdk_download_generated_file",
    "geopack_sdk_download_workflow_artifact",
)

#: Tools that start a LOCALHOST-ONLY host service (slice 033). Not a portal
#: mutation and no local file write, but the host should still know a socket is
#: opened. ``readOnlyHint`` is false for these (see annotations).
_HOST_SERVICE_TOOLS = ("geopack_sdk_show_map",)

#: Everything else is a pure read: no portal change, no local file.
_READ_TOOLS = (
    "geopack_sdk_list_datasets",
    "geopack_sdk_get_dataset",
    "geopack_sdk_get_dataset_schema",
    "geopack_sdk_query_dataset",
    "geopack_sdk_aggregate_dataset",
    "geopack_sdk_get_dataset_relationships",
    "geopack_sdk_get_related_records",
    "geopack_sdk_export_dataset",
    "geopack_sdk_list_workflows",
    "geopack_sdk_get_workflow",
    "geopack_sdk_get_workflow_spec",
    "geopack_sdk_get_workflow_run",
    "geopack_sdk_list_workflow_runs",
    "geopack_sdk_list_analysis_tools",
    "geopack_sdk_get_analysis_result",
    "geopack_sdk_get_task",
    "geopack_sdk_wait_for_task",
    "geopack_sdk_list_generated_files",
    "geopack_sdk_get_quota_summary",
    "geopack_sdk_geocode_place",
    "geopack_sdk_get_mcp_safety_policy",
    "geopack_sdk_geometry_op",
    "geopack_sdk_render_chart",
)

#: Operations that are NOT exposed as tools — the stated exclusion list that
#: replaces the old "we simply never registered it" posture (D7).
UNAVAILABLE_OPERATIONS = (
    "delete_dataset",
    "delete_generated_file",
    "delete_map",
    "delete_publication",
    "delete_workflow",
    "delete_workflow_run",
    "delete_task_record",
)

TOOL_POLICY: Dict[str, Dict[str, Any]] = {
    **{name: {"mutating": True, **spec} for name, spec in _MUTATING_TOOLS.items()},
    **{name: {"mutating": False, "localWrites": True} for name in _LOCAL_WRITE_TOOLS},
    **{name: {"mutating": False, "hostServices": True} for name in _HOST_SERVICE_TOOLS},
    **{name: {"mutating": False} for name in _READ_TOOLS},
}

_POLICY_NOTE = (
    "Mutating tools require the consent their entry names before they are called. "
    "Client-side validation refusals answer type='invalid_args' with candidates and "
    "write nothing. Irreversible deletes are excluded from MCP entirely. "
    "Tools listed in localWrites write to the MCP host filesystem only on a best-effort "
    "basis: a sandboxed host that forbids writes answers saved=false instead of failing, "
    "and geopack_sdk_get_dataset_thumbnail delivers the image inline regardless (inline is "
    "the official delivery mode for a thumbnail). Tools listed in hostServices may open a "
    "LOCALHOST-ONLY browser/data service (127.0.0.1, ephemeral port, opt-in via "
    "GEOPACK_MCP_MAP_SERVICE): it holds the portal credential and exposes only a "
    "low-sensitivity local session token; it produces no map image."
)


def _upload_limits(client: Optional[GeopackClient]) -> Dict[str, Any]:
    """``GET /uploads/limits``, best effort — the policy tool never fails.

    The endpoint carries exactly two caps; it has no allowed-extension or
    declared-type list, so the payload must not invent one.
    """
    if client is None:
        return {"unavailable": True, "reason": "No client in this context"}
    try:
        limits = client.uploads.get_limits()
    except Exception as exc:  # noqa: BLE001 - policy must degrade, never raise
        return {"unavailable": True, "reason": type(exc).__name__}
    return {
        "maxFileSizeMb": limits.maxFileSizeMb,
        "maxFilesPerUpload": limits.maxFilesPerUpload,
        "maxBytes": limits.max_bytes,
        "note": "The portal publishes no allowed-extension or declared-type list.",
    }


def build_policy_payload(client: Optional[GeopackClient] = None) -> Dict[str, Any]:
    """The machine-readable policy registry (version 2)."""
    return {
        "version": 2,
        "mutatingTools": {
            name: entry for name, entry in TOOL_POLICY.items() if entry["mutating"]
        },
        "readOnlyTools": [
            name
            for name, entry in TOOL_POLICY.items()
            if not entry["mutating"] and not entry.get("hostServices")
        ],
        "localWrites": list(_LOCAL_WRITE_TOOLS),
        "hostServices": list(_HOST_SERVICE_TOOLS),
        "unavailable": list(UNAVAILABLE_OPERATIONS),
        "uploadLimits": _upload_limits(client),
        "note": _POLICY_NOTE,
    }


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_mcp_safety_policy"),
        description=(
            "Returns the MCP safety policy: which tools mutate state (and what consent they "
            "need), which only write local files, which operations are deliberately unavailable, "
            "and the upload size caps. Call before a mutating operation or when the user asks "
            "'what can you change?'. Never fails — a degraded field says so."
        ),
    )
    def geopack_sdk_get_mcp_safety_policy(
        ctx: Context[ServerSession, AppContext],
    ) -> CallToolResult:
        """Policy is returned by the MCP server, not by agent instructions."""
        try:
            client: Optional[GeopackClient] = get_client(ctx)
        except Exception:  # noqa: BLE001 - policy must never fail
            client = None
        return tool_result(build_policy_payload(client))
