"""MCP tool registration: analysis tools (portal workflow-as-tool surface)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import mutating_tool, read_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_result, tool_result
from ..tool_handlers.analysis import (
    get_analysis_result,
    list_analysis_tools,
    run_analysis,
)
from ..tool_schema import (
    AnalysisParams,
    AnalysisTag,
    AnalysisTimeoutSeconds,
    AnalysisToolId,
    AnalysisToolSelector,
    AnalysisWaitFlag,
    OverrideDatastoreId,
    Page,
    PageSize,
    SearchQuery,
    WorkflowRunId,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=read_tool("geopack_sdk_list_analysis_tools"),
        description=(
            "List the analysis tools this caller may run (portal workflows exposed as "
            "typed tools). Cards carry toolId, title, tags and outputs. Pass tool_id for "
            "that ONE tool's parameter manifest — read it before run_analysis."
        ),
    )
    def geopack_sdk_list_analysis_tools(
        ctx: Context[ServerSession, AppContext],
        search_query: SearchQuery = None,
        tag: AnalysisTag = None,
        page: Page = 1,
        page_size: PageSize = 20,
        tool_id: AnalysisToolSelector = None,
    ) -> CallToolResult:
        try:
            return tool_result(
                list_analysis_tools(
                    get_client(ctx),
                    search=search_query,
                    tag=tag,
                    page=page,
                    page_size=page_size,
                    tool_id=tool_id,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=mutating_tool("geopack_sdk_run_analysis"),
        description=(
            "Run an analysis tool by tool_id with params keyed by its manifest. Waits by "
            "default and returns the result summary (scalars, datasets, artifacts). "
            "MUTATING: describe the tool and its params and obtain explicit user consent "
            "before calling; do not call if declined."
        ),
    )
    def geopack_sdk_run_analysis(
        ctx: Context[ServerSession, AppContext],
        tool_id: AnalysisToolId,
        params: AnalysisParams,
        wait: AnalysisWaitFlag = True,
        timeout_s: AnalysisTimeoutSeconds = 900,
        override_datastore_id: OverrideDatastoreId = None,
    ) -> CallToolResult:
        try:
            return tool_result(
                run_analysis(
                    get_client(ctx),
                    tool_id,
                    params,
                    wait=wait,
                    timeout_s=timeout_s,
                    override_datastore_id=override_datastore_id,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_analysis_result"),
        description=(
            "Read an analysis run's result summary by run id: status, scalars, datasets, "
            "artifacts, errors. Metadata only — no records or geometry. Use after "
            "run_analysis(wait=false) or a timeout."
        ),
    )
    def geopack_sdk_get_analysis_result(
        ctx: Context[ServerSession, AppContext],
        run_id: WorkflowRunId,
    ) -> CallToolResult:
        try:
            return tool_result(get_analysis_result(get_client(ctx), run_id))
        except Exception as exc:
            return tool_error_result(exc)
