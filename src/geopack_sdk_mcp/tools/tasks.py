"""MCP tool registration: tasks."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.tasks import get_task


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_get_task(
        ctx: Context[ServerSession, AppContext],
        task_id: str,
    ) -> Dict[str, Any]:
        """Get task status and message log by task id (BullMQ job id)."""
        try:
            return get_task(get_client(ctx), task_id)
        except Exception as exc:
            return tool_error_payload(exc)
