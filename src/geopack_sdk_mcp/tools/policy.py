"""MCP-enforced safety policy (independent of host agent prompts)."""

from __future__ import annotations

from typing import Any, Dict


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
            },
            "note": (
                "Conversational consent is enforced by MCP tool design for mutating tools only. "
                "Irreversible deletes are excluded from MCP entirely."
            ),
        }
