"""MCP tool registration: generated files."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.generated_files import download_generated_file, list_generated_files
from ..tool_schema import GeneratedFileId, PageSize, QueryOffset, SavePathRequired


def register(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "List downloadable files (exports, workflow outputs) with id, name, size and "
            "timestamps. Use it instead of guessing a generatedFileId, then call "
            "download_generated_file with the id."
        ),
    )
    def geopack_sdk_list_generated_files(
        ctx: Context[ServerSession, AppContext],
        limit: PageSize = 20,
        offset: QueryOffset = 0,
    ) -> Dict[str, Any]:
        try:
            return list_generated_files(get_client(ctx), limit=limit, offset=offset)
        except Exception as exc:
            return tool_error_payload(exc)

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
