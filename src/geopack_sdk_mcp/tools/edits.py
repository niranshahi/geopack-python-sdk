"""MCP tool registration: record edits (EditDoc ladder)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import mutating_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_result, tool_result
from ..tool_handlers.edits import submit_edit_document
from ..tool_schema import DatasetId, EditDocumentPayload, EditMode


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=mutating_tool("geopack_sdk_submit_edit_document"),
        description=(
            "Send an EditDoc through the edit ladder: validate (default, plans only) | preview "
            "(plans + simulated per-operation result) | apply (writes). "
            "MUTATING: apply writes records, including related datasets. Describe every change "
            "(dataset, rows, operations) and obtain explicit user consent before calling with "
            "mode='apply'. Do not call if declined. "
            "validate/preview never write — run them first and reuse the same document."
        ),
    )
    def geopack_sdk_submit_edit_document(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        document: EditDocumentPayload,
        mode: EditMode = "validate",
    ) -> CallToolResult:
        try:
            return tool_result(
                submit_edit_document(
                    get_client(ctx),
                    dataset_id,
                    document,
                    mode=mode,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)
