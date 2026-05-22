"""MCP tool registration: workflows."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.workflows import get_workflow_for_mcp, list_workflows
from ..tool_schema import (
    IncludeWorkflowParams,
    Page,
    PageSize,
    SearchQuery,
    WorkflowId,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        description="List workflow definitions (no graphJson in JSON).",
    )
    def geopack_sdk_list_workflows(
        ctx: Context[ServerSession, AppContext],
        page: Page = 1,
        page_size: PageSize = 20,
        search_query: SearchQuery = None,
    ) -> Any:
        try:
            return list_workflows(
                get_client(ctx),
                page=page,
                page_size=page_size,
                search_query=search_query,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description=(
            "Get workflow definition. Set include_params=true before submit_workflow "
            "to obtain parameters[] (keys, types, required). graphJson is omitted."
        ),
    )
    def geopack_sdk_get_workflow(
        ctx: Context[ServerSession, AppContext],
        workflow_id: WorkflowId,
        include_params: IncludeWorkflowParams = False,
    ) -> Dict[str, Any]:
        try:
            return get_workflow_for_mcp(
                get_client(ctx),
                workflow_id=workflow_id,
                include_params=include_params,
            )
        except Exception as exc:
            return tool_error_payload(exc)
