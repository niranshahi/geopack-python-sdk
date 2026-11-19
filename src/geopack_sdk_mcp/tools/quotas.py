"""MCP tool registration: quotas (self)."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.quotas import get_quota_summary


def register(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "Returns the caller's quota usage per dimension (enabled, plan, limits, remaining). "
            "Call before a large upload or export when the user asks for something big, instead "
            "of discovering the limit through a refusal. Takes no arguments."
        ),
    )
    def geopack_sdk_get_quota_summary(
        ctx: Context[ServerSession, AppContext],
    ) -> Dict[str, Any]:
        try:
            return get_quota_summary(get_client(ctx))
        except Exception as exc:
            return tool_error_payload(exc)
