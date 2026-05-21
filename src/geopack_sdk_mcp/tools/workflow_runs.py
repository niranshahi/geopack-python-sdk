"""MCP tool registration: workflow runs."""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.submit_workflow import submit_workflow
from ..tool_handlers.workflow_runs import download_workflow_artifact, get_workflow_run


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_submit_workflow(
        ctx: Context[ServerSession, AppContext],
        workflow_id: int,
        params: Dict[str, Any],
        override_datastore_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Submit a workflow for execution.
        
        Returns workflowRunId and taskId for polling.
        Use geopack_sdk_wait_for_task(taskId) to wait for completion.
        
        Args:
            workflow_id: ID of the workflow to execute
            params: Dictionary of parameter values for the workflow
            override_datastore_id: Optional datastore ID override
        """
        try:
            return submit_workflow(
                get_client(ctx),
                workflow_id=workflow_id,
                params=params,
                override_datastore_id=override_datastore_id,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool()
    def geopack_sdk_get_workflow_run(
        ctx: Context[ServerSession, AppContext],
        run_id: int,
    ) -> Dict[str, Any]:
        """Get workflow run status, nodes, and artifacts by run id."""
        try:
            return get_workflow_run(get_client(ctx), run_id)
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool()
    def geopack_sdk_download_workflow_artifact(
        ctx: Context[ServerSession, AppContext],
        run_id: int,
        artifact_id: int,
        save_path: str = "./",
    ) -> Dict[str, Any]:
        """Download a workflow artifact (output file) to local disk.
        
        Args:
            run_id: ID of the workflow run
            artifact_id: ID of the artifact to download
            save_path: Local directory or file path to save to (default: current directory)
        
        Returns:
            Dict with savedPath (absolute path to downloaded file)
        """
        try:
            return download_workflow_artifact(
                get_client(ctx),
                run_id=run_id,
                artifact_id=artifact_id,
                save_path=save_path,
            )
        except Exception as exc:
            return tool_error_payload(exc)
