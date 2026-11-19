"""MCP-enforced safety policy (independent of host agent prompts)."""

from __future__ import annotations

from typing import Any, Dict

# Tool policy registry (slice 020 §10 step 4).
#
# Every tool that touches state declares its mode here, so "what may change" is
# a written contract rather than the absence of a handler. The seven read lanes
# below never write anything: no portal record, no local file. Slice 021
# promotes this registry into the machine-readable payload returned by
# ``geopack_sdk_get_mcp_safety_policy``; until then the mapping is the source
# the payload is generated from.
TOOL_POLICY: Dict[str, Dict[str, Any]] = {
    "geopack_sdk_get_dataset_schema": {"mutating": False},
    "geopack_sdk_aggregate_dataset": {"mutating": False},
    "geopack_sdk_get_dataset_relationships": {"mutating": False},
    "geopack_sdk_get_related_records": {"mutating": False},
    "geopack_sdk_get_quota_summary": {"mutating": False},
    "geopack_sdk_list_workflow_runs": {"mutating": False},
    "geopack_sdk_list_generated_files": {"mutating": False},
}


def register(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "Returns Geopack MCP safety rules enforced by the server. "
            "Call before destructive or mutating operations."
        ),
    )
    def geopack_sdk_get_mcp_safety_policy() -> Dict[str, Any]:
        """Policy is returned by the MCP server, not by agent instructions."""
        return {
            "enforced_by_mcp_server": True,
            "not_available_via_mcp": {
                "delete_dataset": (
                    "Dataset deletion is not an MCP tool. "
                    "Use the Geoportal web UI (Datasets)."
                ),
                "delete_generated_file": (
                    "Generated file deletion is not an MCP tool. "
                    "Use the Geoportal web UI."
                ),
            },
            "mutating_tools_require_host_consent": {
                "geopack_sdk_upload_dataset": (
                    "Before calling: describe file, datastore, and workgroup; "
                    "obtain explicit user consent in conversation (yes/proceed). "
                    "Do not call if user declined."
                ),
                "geopack_sdk_submit_workflow": (
                    "Before calling: describe workflow id, params, and effects; "
                    "obtain explicit user consent in conversation. "
                    "Do not call if user declined."
                ),
                "geopack_sdk_run_analysis": (
                    "Before calling: read the tool's manifest (list_analysis_tools with "
                    "tool_id), describe the tool and every param value, and obtain explicit "
                    "user consent in conversation. Do not call if user declined."
                ),
            },
            "note": (
                "Conversational consent is enforced by MCP tool design for mutating tools only. "
                "Irreversible deletes are excluded from MCP entirely."
            ),
        }
