"""MCP tool registration: workflow runs."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.workflow_runs import get_workflow_run


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_get_workflow_run(
        ctx: Context[ServerSession, AppContext],
        run_id: int,
    ) -> Dict[str, Any]:
        """Get workflow run status, nodes, and artifacts by run id."""
        try:
            return get_workflow_run(get_client(ctx), run_id)
        except Exception as exc:
            return tool_error_payload(exc)
