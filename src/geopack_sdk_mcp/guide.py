"""Server-level usage guidance: MCP ``instructions`` + the ``geopack://guide`` resource.

An MCP server cannot install a host "skill". The two levers that actually reach the
model are:

* **A — ``instructions``** (the ``initialize`` result): short, stable orientation that a
  capable client injects into the model's context at connect. Passed to ``FastMCP`` in
  ``server.py``.
* **B — the ``geopack://guide`` resource**: the full playbook, read on demand via
  ``resources/read``, so it never bloats the system prompt.

Both are **editable Markdown files** under ``content/`` (``instructions.md``,
``guide.md``) — change the prose without touching Python. The one derived part, the tool
inventory, is generated from ``TOOL_POLICY`` (the same registry the safety policy uses)
and injected at the ``%%TOOL_INVENTORY%%`` token, so the guide cannot omit a registered
tool. A test asserts full coverage; the guide must never weaken the consent rules stated
by ``geopack_sdk_get_mcp_safety_policy``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

from .tools.policy import TOOL_POLICY

#: The resource URI clients read for the full guide.
GUIDE_URI = "geopack://guide"

#: Token in ``content/guide.md`` replaced at load time by the generated inventory.
TOOL_INVENTORY_TOKEN = "%%TOOL_INVENTORY%%"

#: Where the editable Markdown lives (shipped as package data).
CONTENT_DIR = Path(__file__).resolve().parent / "content"

#: One short purpose per registered tool. A test asserts these keys equal the
#: registered tool set, so a new tool cannot ship without a guide line.
PURPOSES: Dict[str, str] = {
    # --- Read ---------------------------------------------------------------
    "geopack_sdk_list_datasets": "Search/list datasets (attribute + spatial filters).",
    "geopack_sdk_get_dataset": "One dataset's metadata (`lite` drops heavy fields).",
    "geopack_sdk_get_dataset_schema": (
        "Fields, types, aliases, coded-value domains — read this BEFORE any where/order."
    ),
    "geopack_sdk_query_dataset": (
        "Page features as GeoJSON (filters, fields, order, limit); default EPSG:4326."
    ),
    "geopack_sdk_aggregate_dataset": "Group + count/sum/avg/min/max/percentile statistics.",
    "geopack_sdk_get_dataset_relationships": "Relationships defined for a dataset.",
    "geopack_sdk_get_related_records": "Records of a related dataset for one record.",
    "geopack_sdk_export_dataset": "Export a dataset/query to a file (async task).",
    "geopack_sdk_list_workflows": "List workflows.",
    "geopack_sdk_get_workflow": "One workflow's definition.",
    "geopack_sdk_get_workflow_spec": "A saved workflow as a position-free wf-spec graph.",
    "geopack_sdk_get_workflow_run": "One workflow run with its status and result summary.",
    "geopack_sdk_list_workflow_runs": "Workflow runs (filter by workflow/status).",
    "geopack_sdk_list_analysis_tools": "Analysis tools you can run, with their inputs.",
    "geopack_sdk_get_analysis_result": "The result summary/outputs of an analysis run.",
    "geopack_sdk_get_task": "One task's status and messages.",
    "geopack_sdk_wait_for_task": "Block until a task finishes (bounded) and return it.",
    "geopack_sdk_list_generated_files": "Generated files (exports and artifacts).",
    "geopack_sdk_get_quota_summary": "Storage/usage quota summary.",
    "geopack_sdk_geocode_place": "Geocode a place name to coordinates (Nominatim).",
    "geopack_sdk_get_mcp_safety_policy": (
        "The safety policy: mutating tools + consent, local writes, upload caps."
    ),
    "geopack_sdk_auth_status": (
        "Is this MCP authenticated? If not, the exact `geopack-sdk login` step."
    ),
    "geopack_sdk_geometry_op": (
        "Local geometry ops (buffer/area/intersect/...) on supplied GeoJSON/WKT."
    ),
    # --- Local file writes --------------------------------------------------
    "geopack_sdk_get_dataset_thumbnail": "Dataset preview PNG, delivered inline.",
    "geopack_sdk_download_generated_file": "Save a generated file to disk (best-effort).",
    "geopack_sdk_download_workflow_artifact": "Save a workflow artifact to disk (best-effort).",
    # --- Host service -------------------------------------------------------
    "geopack_sdk_show_map": "Open a live built-in map viewer (localhost, opt-in).",
    # --- Mutating -----------------------------------------------------------
    "geopack_sdk_upload_dataset": "Upload a local file as a new dataset.",
    "geopack_sdk_submit_workflow": "Start a workflow run.",
    "geopack_sdk_run_analysis": "Run an analysis tool (starts a workflow run).",
    "geopack_sdk_submit_edit_document": "Edit records via an EditDoc (validate/preview first).",
    "geopack_sdk_cancel_task": "Request cancellation of a running task.",
}

#: Group heading per policy flag, in the order the guide lists them.
_GROUP_READ = "Read (no side effects)"
_GROUP_LOCAL = "Local file writes (MCP host only)"
_GROUP_HOST = "Host services (a localhost socket)"
_GROUP_WRITE = "Write (mutates portal state — needs the user's consent)"

#: Never let a packaging gap break the server: a minimal fallback if a file is absent.
_FALLBACK_INSTRUCTIONS = (
    "Geopack SDK MCP — a gateway to a Geopack portal (datasets, queries, workflows, maps, "
    "tasks, uploads, geometry). Call geopack_sdk_get_dataset_schema before any where/order "
    "clause; call geopack_sdk_get_mcp_safety_policy before any mutating tool; geometry is "
    "GeoJSON [lon, lat]. Read the geopack://guide resource for the full playbook."
)
_FALLBACK_GUIDE = (
    "# Geopack SDK MCP — usage guide\n\n"
    "(the guide content file is missing from this install)\n\n"
    f"{TOOL_INVENTORY_TOKEN}\n"
)


#: A leading HTML comment (human editing notes) is stripped from served text.
_LEADING_HTML_COMMENT = re.compile(r"^\s*<!--.*?-->\s*", re.DOTALL)


def _read_content(name: str, fallback: str) -> str:
    try:
        text = (CONTENT_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return fallback
    text = _LEADING_HTML_COMMENT.sub("", text, count=1)
    return text.strip()


def _group_of(entry: Dict[str, object]) -> str:
    if entry.get("mutating"):
        return _GROUP_WRITE
    if entry.get("localWrites"):
        return _GROUP_LOCAL
    if entry.get("hostServices"):
        return _GROUP_HOST
    return _GROUP_READ


def tool_inventory() -> List[Tuple[str, str, str]]:
    """``(group, name, purpose)`` for every registered tool, in a stable order.

    Generated from ``TOOL_POLICY`` so it cannot omit a registered tool.
    """
    order = (_GROUP_READ, _GROUP_LOCAL, _GROUP_HOST, _GROUP_WRITE)
    rank = {group: index for index, group in enumerate(order)}
    rows = [
        (_group_of(entry), name, PURPOSES.get(name, "(no purpose recorded)"))
        for name, entry in TOOL_POLICY.items()
    ]
    rows.sort(key=lambda row: (rank.get(row[0], len(order)), row[1]))
    return rows


def inventory_markdown() -> str:
    """The generated ``## Tool inventory`` section, one bullet per tool by safety."""
    out: List[str] = []
    current = None
    for group, name, purpose in tool_inventory():
        if group != current:
            current = group
            if out:
                out.append("")
            out.append(f"### {group}")
        out.append(f"- `{name}` — {purpose}")
    return "\n".join(["## Tool inventory", ""] + out)


def default_instructions() -> str:
    """The editable always-on instructions (``content/instructions.md``)."""
    return _read_content("instructions.md", _FALLBACK_INSTRUCTIONS)


def default_guide_markdown() -> str:
    """The raw guide source (``content/guide.md``), with the inventory token intact."""
    return _read_content("guide.md", _FALLBACK_GUIDE)


def build_guide_markdown() -> str:
    """The served guide: the editable file with the inventory token substituted."""
    text = default_guide_markdown()
    if TOOL_INVENTORY_TOKEN in text:
        return text.replace(TOOL_INVENTORY_TOKEN, inventory_markdown())
    return text


#: Short, always-on orientation injected at connect (MCP *instructions*). Read from
#: ``content/instructions.md`` at import.
SERVER_INSTRUCTIONS = default_instructions()
