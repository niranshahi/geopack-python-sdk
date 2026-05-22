"""MCP tool registration: tasks."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.tasks import get_task, wait_for_task
from ..tool_schema import TaskId, WaitInterval, WaitTimeout


def register(mcp: Any) -> None:
    @mcp.tool(
        description="Get background task status and message log by task id.",
    )
    def geopack_sdk_get_task(
        ctx: Context[ServerSession, AppContext],
        task_id: TaskId,
    ) -> Dict[str, Any]:
        try:
            return get_task(get_client(ctx), task_id)
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description=(
            "Poll task until completed, failed, canceled, or timeout. "
            "Upload: results[].createdDatasetId. Export: generatedFileId + downloadApiPath."
        ),
    )
    def geopack_sdk_wait_for_task(
        ctx: Context[ServerSession, AppContext],
        task_id: TaskId,
        timeout: WaitTimeout = 300,
        interval: WaitInterval = 2,
    ) -> Dict[str, Any]:
        try:
            return wait_for_task(
                get_client(ctx),
                task_id,
                timeout=timeout,
                interval=interval,
            )
        except Exception as exc:
            return tool_error_payload(exc)
