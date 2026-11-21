"""MCP tool registration: workflow runs."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import local_write_tool, mutating_tool, read_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_result, tool_result
from ..output_schema import PageEnvelope
from ..tool_handlers.submit_workflow import submit_workflow
from ..tool_handlers.workflow_runs import (
    download_workflow_artifact,
    get_workflow_run,
    list_workflow_runs,
)
from ..tool_schema import (
    ArtifactId,
    OrderDirection,
    OverrideDatastoreId,
    PageSize,
    QueryOffset,
    RunOrderBy,
    RunStatusFilter,
    SavePathRequired,
    WorkflowId,
    WorkflowIdOptional,
    WorkflowParams,
    WorkflowRunId,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=mutating_tool("geopack_sdk_submit_workflow"),
        description=(
            "Start workflow execution (non-blocking). Returns workflowRunId and taskId. "
            "Call get_workflow(include_params=true) first to learn param keys. "
            "MUTATING: Before this call the host must describe workflow and params and obtain "
            "explicit user consent in conversation; do not call if declined."
        ),
    )
    def geopack_sdk_submit_workflow(
        ctx: Context[ServerSession, AppContext],
        workflow_id: WorkflowId,
        params: WorkflowParams,
        override_datastore_id: OverrideDatastoreId = None,
    ) -> CallToolResult:
        try:
            return tool_result(
                submit_workflow(
                    get_client(ctx),
                    workflow_id=workflow_id,
                    params=params,
                    override_datastore_id=override_datastore_id,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)


    @mcp.tool(
        annotations=read_tool("geopack_sdk_list_workflow_runs"),
        description=(
            "List workflow runs you can see (id, workflowId, status, submitter, timestamps), "
            "optionally filtered by workflow_id or status. order_by sorts server-side "
            "(id, workflow.name, submitter, taskId, status, startedAt, finishedAt, createdAt, "
            "updatedAt); the default is createdAt, newest first. Use this to answer 'what did I "
            "start' instead of guessing a run id; then call get_workflow_run for artifacts and "
            "detail."
        ),
    )
    def geopack_sdk_list_workflow_runs(
        ctx: Context[ServerSession, AppContext],
        workflow_id: WorkflowIdOptional = None,
        status: RunStatusFilter = None,
        limit: PageSize = 20,
        offset: QueryOffset = 0,
        order_by: RunOrderBy = None,
        order_direction: OrderDirection = None,
    ) -> Annotated[CallToolResult, PageEnvelope]:
        try:
            return tool_result(
                list_workflow_runs(
                    get_client(ctx),
                    workflow_id=workflow_id,
                    status=status,
                    limit=limit,
                    offset=offset,
                    order_by=order_by,
                    order_direction=order_direction,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_workflow_run"),
        description="Get workflow run status, step nodes, and output artifacts by run id.",
    )
    def geopack_sdk_get_workflow_run(
        ctx: Context[ServerSession, AppContext],
        run_id: WorkflowRunId,
    ) -> CallToolResult:
        try:
            return tool_result(get_workflow_run(get_client(ctx), run_id))
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=local_write_tool("geopack_sdk_download_workflow_artifact"),
        description=(
            "Download a workflow output file to the MCP host. "
            "Returns savedPath. Get artifact_id from get_workflow_run."
        ),
    )
    def geopack_sdk_download_workflow_artifact(
        ctx: Context[ServerSession, AppContext],
        run_id: WorkflowRunId,
        artifact_id: ArtifactId,
        save_path: SavePathRequired = "./",
    ) -> CallToolResult:
        try:
            return tool_result(
                download_workflow_artifact(
                    get_client(ctx),
                    run_id=run_id,
                    artifact_id=artifact_id,
                    save_path=save_path,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)
