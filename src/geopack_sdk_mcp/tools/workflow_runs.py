"""MCP tool registration: workflow runs."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.submit_workflow import submit_workflow
from ..tool_handlers.workflow_runs import download_workflow_artifact, get_workflow_run
from ..tool_schema import (
    ArtifactId,
    OverrideDatastoreId,
    SavePathRequired,
    WorkflowId,
    WorkflowParams,
    WorkflowRunId,
)


def register(mcp: Any) -> None:
    @mcp.tool(
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
    ) -> Dict[str, Any]:
        try:
            return submit_workflow(
                get_client(ctx),
                workflow_id=workflow_id,
                params=params,
                override_datastore_id=override_datastore_id,
            )
        except Exception as exc:
            return tool_error_payload(exc)


    @mcp.tool(
        description="Get workflow run status, step nodes, and output artifacts by run id.",
    )
    def geopack_sdk_get_workflow_run(
        ctx: Context[ServerSession, AppContext],
        run_id: WorkflowRunId,
    ) -> Dict[str, Any]:
        try:
            return get_workflow_run(get_client(ctx), run_id)
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
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
    ) -> Dict[str, Any]:
        try:
            return download_workflow_artifact(
                get_client(ctx),
                run_id=run_id,
                artifact_id=artifact_id,
                save_path=save_path,
            )
        except Exception as exc:
            return tool_error_payload(exc)
