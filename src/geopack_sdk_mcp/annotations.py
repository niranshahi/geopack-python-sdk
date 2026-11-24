"""Per-tool MCP annotations (slice 022 §2).

A host gates on these hints *before* it calls a tool, so every registered tool
carries one. ``tests/test_tool_annotations.py`` re-derives the expected
annotations from the policy registry (``tools/policy.py``): a new tool that is
not annotated — or annotated against its policy class — fails the suite.

Rules (slice 022 §2):

* ``readOnlyHint`` — true for reads; the three ``localWrites`` tools save files
  on the MCP host, so they are **not** read-only.
* ``destructiveHint`` — true for ``submit_edit_document`` only (a plan may
  delete records); ``cancel_task`` is a state change, not data loss.
* ``idempotentHint`` — true for every read tool; false for uploads, runs,
  edits, file saves, ``cancel_task`` and ``export_dataset`` (each call starts a
  new export task and mints a new generated file).
* ``openWorldHint`` — true for ``geocode_place`` (Nominatim) and
  ``run_analysis`` (a workflow may reach external services).

The 021 policy registry is the source of truth for ``readOnlyHint``:
``export_dataset`` is registered as a read (starting an export needs no
consent), so it is annotated read-only **and** non-idempotent.
"""

from __future__ import annotations

from typing import Dict

from mcp.types import ToolAnnotations

#: Human title per registered tool. Also the completeness list: the annotation
#: test compares it to the live FastMCP surface.
TITLES: Dict[str, str] = {
    "geopack_sdk_list_datasets": "List datasets",
    "geopack_sdk_get_dataset": "Get a dataset",
    "geopack_sdk_get_dataset_schema": "Get a dataset schema",
    "geopack_sdk_aggregate_dataset": "Aggregate a dataset (counts, sums, top-N)",
    "geopack_sdk_get_dataset_relationships": "List dataset relationships",
    "geopack_sdk_get_related_records": "Get related records",
    "geopack_sdk_query_dataset": "Query dataset records",
    "geopack_sdk_get_dataset_thumbnail": "Save a dataset thumbnail",
    "geopack_sdk_upload_dataset": "Upload a dataset",
    "geopack_sdk_export_dataset": "Export a dataset",
    "geopack_sdk_get_task": "Get task status",
    "geopack_sdk_cancel_task": "Cancel a task",
    "geopack_sdk_wait_for_task": "Wait for a task",
    "geopack_sdk_get_quota_summary": "Get quota summary",
    "geopack_sdk_list_generated_files": "List generated files",
    "geopack_sdk_download_generated_file": "Download a generated file",
    "geopack_sdk_geocode_place": "Geocode a place",
    "geopack_sdk_get_mcp_safety_policy": "Get MCP safety policy",
    "geopack_sdk_list_workflows": "List workflows",
    "geopack_sdk_get_workflow": "Get a workflow",
    "geopack_sdk_get_workflow_spec": "Read a workflow's graph as a spec",
    "geopack_sdk_submit_workflow": "Submit a workflow",
    "geopack_sdk_list_workflow_runs": "List workflow runs",
    "geopack_sdk_get_workflow_run": "Get a workflow run",
    "geopack_sdk_download_workflow_artifact": "Download a workflow artifact",
    "geopack_sdk_list_analysis_tools": "List analysis tools",
    "geopack_sdk_run_analysis": "Run an analysis tool",
    "geopack_sdk_get_analysis_result": "Get an analysis result",
    "geopack_sdk_submit_edit_document": "Submit an edit document",
    "geopack_sdk_show_map": "Show a local map data service",
    "geopack_sdk_geometry_op": "Run a local geometry op",
    "geopack_sdk_render_chart": "Render a bar/line/pie chart from data",
}

OPEN_WORLD_TOOLS = frozenset(
    {"geopack_sdk_geocode_place", "geopack_sdk_run_analysis"}
)
DESTRUCTIVE_TOOLS = frozenset({"geopack_sdk_submit_edit_document"})
#: Reads that still answer with a fresh artifact on every call.
NON_IDEMPOTENT_TOOLS = frozenset({"geopack_sdk_export_dataset"})


def _title(name: str) -> str:
    try:
        return TITLES[name]
    except KeyError:  # pragma: no cover - the annotation test catches this
        raise KeyError(
            f"Tool {name!r} has no annotation title; add it to annotations.TITLES."
        ) from None


def read_tool(name: str) -> ToolAnnotations:
    """A pure read: no portal change, no local file."""
    return ToolAnnotations(
        title=_title(name),
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=name not in NON_IDEMPOTENT_TOOLS,
        openWorldHint=name in OPEN_WORLD_TOOLS,
    )


def local_write_tool(name: str) -> ToolAnnotations:
    """Reads from the portal but writes a file on the MCP host."""
    return ToolAnnotations(
        title=_title(name),
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )


def mutating_tool(name: str) -> ToolAnnotations:
    """Changes portal state; ``destructiveHint`` only for the edit lane."""
    return ToolAnnotations(
        title=_title(name),
        readOnlyHint=False,
        destructiveHint=name in DESTRUCTIVE_TOOLS,
        idempotentHint=False,
        openWorldHint=name in OPEN_WORLD_TOOLS,
    )


def host_service_tool(name: str) -> ToolAnnotations:
    """Starts a localhost-only host service; writes no portal data and no file."""
    return ToolAnnotations(
        title=_title(name),
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
