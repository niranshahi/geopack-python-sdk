"""MCP tool registration: workflows."""

from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.workflows import list_workflows


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_list_workflows(
        ctx: Context[ServerSession, AppContext],
        page: int = 1,
        page_size: int = 20,
        search_query: Optional[str] = None,
    ) -> Any:
        """List workflow definitions available to the authenticated user."""
        try:
            return list_workflows(
                get_client(ctx),
                page=page,
                page_size=page_size,
                search_query=search_query,
            )
        except Exception as exc:
            return tool_error_payload(exc)
