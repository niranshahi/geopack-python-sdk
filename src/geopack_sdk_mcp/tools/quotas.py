"""MCP tool registration: quotas (self)."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import read_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_result, tool_result
from ..output_schema import QuotaSummaryEnvelope
from ..tool_handlers.quotas import get_quota_summary


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_quota_summary"),
        description=(
            "Returns the caller's quota usage per dimension (enabled, plan, limits, remaining). "
            "Call before a large upload or export when the user asks for something big, instead "
            "of discovering the limit through a refusal. Takes no arguments."
        ),
    )
    def geopack_sdk_get_quota_summary(
        ctx: Context[ServerSession, AppContext],
    ) -> Annotated[CallToolResult, QuotaSummaryEnvelope]:
        try:
            return tool_result(get_quota_summary(get_client(ctx)))
        except Exception as exc:
            return tool_error_result(exc)
