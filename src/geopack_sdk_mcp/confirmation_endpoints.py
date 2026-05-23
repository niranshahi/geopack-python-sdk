"""Read-only MCP tools for confirmation polling (agent-safe)."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from .confirmation import get_confirmation_manager


def register_confirmation_endpoints(mcp: FastMCP) -> None:
    """Register agent-readable confirmation status tools.

    Approve/reject are intentionally NOT MCP tools — operators use
    ``geopack-sdk-confirm`` so agents cannot self-approve.
    """
    manager = get_confirmation_manager()

    @mcp.tool(
        description=(
            "Poll confirmation status by ID. "
            "Returns status: pending | approved | rejected | executed | not_found."
        ),
    )
    def geopack_sdk_get_confirmation_status(
        confirmation_id: str,
    ) -> Dict[str, Any]:
        req = manager.get_request(confirmation_id)
        if req is None:
            return {
                "status": "not_found",
                "confirmation_id": confirmation_id,
                "message": "Confirmation request not found or expired.",
            }
        return {"status": "ok", **req.to_dict()}

    @mcp.tool(
        description=(
            "List pending confirmation requests. "
            "Human must approve via geopack-sdk-confirm CLI (not via agent tools)."
        ),
    )
    def geopack_sdk_list_pending_confirmations() -> Dict[str, Any]:
        pending = manager.list_pending()
        return {
            "success": True,
            "count": len(pending),
            "confirmations": [req.to_dict() for req in pending],
            "operator_hint": "Approve with: geopack-sdk-confirm approve <confirmation_id>",
        }
