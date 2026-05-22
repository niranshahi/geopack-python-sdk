"""MCP tool registration: workflows."""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.workflows import get_workflow_for_mcp, list_workflows


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

    @mcp.tool()
    def geopack_sdk_get_workflow(
        ctx: Context[ServerSession, AppContext],
        workflow_id: int,
        include_params: bool = False,
    ) -> Dict[str, Any]:
        """Get workflow definition with optional parameter extraction.
        
        Parameters tell you what inputs the workflow needs (key, type, required, default, etc.).
        graphJson is omitted from the tool result; use include_params=true for the parameters array.
        
        Args:
            workflow_id: ID of the workflow to fetch
            include_params: If True, extract runtime parameters from the workflow graph (server-side)
        """
        try:
            return get_workflow_for_mcp(
                get_client(ctx),
                workflow_id=workflow_id,
                include_params=include_params,
            )
        except Exception as exc:
            return tool_error_payload(exc)
