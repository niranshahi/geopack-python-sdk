"""MCP tool registration: tasks."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.tasks import get_task, wait_for_task


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

    @mcp.tool()
    def geopack_sdk_wait_for_task(
        ctx: Context[ServerSession, AppContext],
        task_id: str,
        timeout: int = 300,
        interval: int = 2,
    ) -> Dict[str, Any]:
        """
        Poll a background task until completed, failed, canceled, or timeout.

        On success, results may include generatedFileId and downloadApiPath
        (for dataset:export). File bytes are not returned — use
        geopack_sdk_download_generated_file.
        """
        try:
            return wait_for_task(
                get_client(ctx),
                task_id,
                timeout=timeout,
                interval=interval,
            )
        except Exception as exc:
            return tool_error_payload(exc)
