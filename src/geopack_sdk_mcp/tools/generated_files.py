"""MCP tool registration: generated files."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..confirmation import get_confirmation_manager
from ..destructive_guard import guard_destructive_operation
from ..errors import tool_error_payload
from ..tool_handlers.generated_files import delete_generated_file, download_generated_file
from ..tool_schema import GeneratedFileId, SavePathRequired


def register(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "Download export/workflow output file to MCP host. "
            "Use generatedFileId from wait_for_task. save_path: directory or full file path."
        ),
    )
    def geopack_sdk_download_generated_file(
        ctx: Context[ServerSession, AppContext],
        generated_file_id: GeneratedFileId,
        save_path: SavePathRequired,
    ) -> Dict[str, Any]:
        try:
            return download_generated_file(
                get_client(ctx),
                generated_file_id,
                save_path,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description=(
            "Delete a generated file record and its storage. WARNING: This is destructive. "
            "Requires confirmation_id from a human-approved request (geopack-sdk-confirm CLI)."
        ),
    )
    def geopack_sdk_delete_generated_file(
        ctx: Context[ServerSession, AppContext],
        generated_file_id: GeneratedFileId,
        confirmation_id: str | None = None,
    ) -> Dict[str, Any]:
        guard = guard_destructive_operation(
            "delete_generated_file",
            generated_file_id,
            confirmation_id=confirmation_id,
        )
        if not guard.should_execute:
            return guard.response or {}

        manager = get_confirmation_manager()
        try:
            result = delete_generated_file(get_client(ctx), generated_file_id)
            manager.consume_request(guard.confirmation_id)
            return result
        except Exception as exc:
            return tool_error_payload(exc)
