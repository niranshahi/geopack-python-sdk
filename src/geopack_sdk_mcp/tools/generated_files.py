"""MCP tool registration: generated files."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.generated_files import download_generated_file


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_download_generated_file(
        ctx: Context[ServerSession, AppContext],
        generated_file_id: int,
        save_path: str,
    ) -> Dict[str, Any]:
        """
        Download an export/workflow output file to a local path on the MCP host machine.

        save_path may be a directory (filename from Content-Disposition) or a full file path.
        Uses server env authentication; file bytes are not included in the tool JSON response.
        """
        try:
            return download_generated_file(
                get_client(ctx),
                generated_file_id,
                save_path,
            )
        except Exception as exc:
            return tool_error_payload(exc)
