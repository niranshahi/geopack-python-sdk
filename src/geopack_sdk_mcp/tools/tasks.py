"""MCP tool registration: tasks."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import mutating_tool, read_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_result, tool_result
from ..tool_handlers.tasks import cancel_task, get_task, wait_for_task
from ..tool_schema import TaskId, WaitInterval, WaitTimeout


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_task"),
        description="Get background task status and message log by task id.",
    )
    def geopack_sdk_get_task(
        ctx: Context[ServerSession, AppContext],
        task_id: TaskId,
    ) -> CallToolResult:
        try:
            return tool_result(get_task(get_client(ctx), task_id))
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=mutating_tool("geopack_sdk_cancel_task"),
        description=(
            "Request cancellation of a running background task by id. "
            "Stops a running task; work already completed stays. Confirm with the user "
            "before cancelling. Best effort (202) — poll get_task/wait_for_task for the "
            "outcome. There is no batch or 'cancel all'."
        ),
    )
    def geopack_sdk_cancel_task(
        ctx: Context[ServerSession, AppContext],
        task_id: TaskId,
    ) -> CallToolResult:
        try:
            return tool_result(cancel_task(get_client(ctx), task_id))
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_wait_for_task"),
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
    ) -> CallToolResult:
        try:
            return tool_result(
                wait_for_task(
                    get_client(ctx),
                    task_id,
                    timeout=timeout,
                    interval=interval,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)
