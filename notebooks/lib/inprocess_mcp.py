"""
In-process MCP tool execution for Jupyter (and other hosts without stdio fileno).

Uses the same tool_handlers and FastMCP tool schemas as geopack-sdk-mcp stdio server.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

SDK_ROOT = Path(__file__).resolve().parents[2]


def _ensure_sdk_on_path() -> None:
    src = SDK_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


@dataclass
class ListedTool:
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class ListedTools:
    tools: List[ListedTool]


def use_inprocess_mcp() -> bool:
    """True when MCP stdio subprocess is unsafe (Jupyter) or forced via env."""
    mode = os.getenv("GEOPACK_MCP_MODE", "").strip().lower()
    if mode == "stdio":
        return False
    if mode in ("inprocess", "in-process"):
        return True
    try:
        from IPython import get_ipython

        if get_ipython() is not None:
            return True
    except ImportError:
        pass
    return False


def dispatch_tool(client: Any, name: str, arguments: Dict[str, Any]) -> Any:
    """Invoke MCP tool handler (same logic as stdio server tools)."""
    from geopack_sdk_mcp.errors import tool_error_payload

    try:
        if name == "geopack_sdk_geocode_place":
            from geopack_sdk_mcp.tool_handlers.geocoding import geocode_place

            return geocode_place(
                str(arguments["query"]),
                limit=int(arguments.get("limit", 1)),
            )

        if name == "geopack_sdk_list_datasets":
            from geopack_sdk_mcp.tool_handlers.datasets import list_datasets

            return list_datasets(
                client,
                page=int(arguments.get("page", 1)),
                page_size=int(arguments.get("page_size", 20)),
                search_query=arguments.get("search_query"),
                details_level=arguments.get("details_level", "lite"),
                data_type=arguments.get("data_type"),
                bbox=arguments.get("bbox"),
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
            )

        if name == "geopack_sdk_get_dataset":
            from geopack_sdk_mcp.tool_handlers.datasets import get_dataset

            return get_dataset(
                client,
                int(arguments["dataset_id"]),
                details_level=arguments.get("details_level", "full"),
            )

        if name == "geopack_sdk_query_dataset":
            from geopack_sdk_mcp.tool_handlers.datasets import query_dataset

            return query_dataset(
                client,
                int(arguments["dataset_id"]),
                query=arguments.get("query"),
                limit=arguments.get("limit"),
                offset=int(arguments.get("offset", 0)),
                return_geometry=bool(arguments.get("return_geometry", True)),
                out_srid=arguments.get("out_srid"),
            )

        if name == "geopack_sdk_get_dataset_thumbnail":
            from geopack_sdk_mcp.tool_handlers.datasets import get_dataset_thumbnail

            return get_dataset_thumbnail(
                client,
                int(arguments["dataset_id"]),
                save_path=arguments.get("save_path"),
            )

        if name == "geopack_sdk_export_dataset":
            from geopack_sdk_mcp.tool_handlers.datasets import export_dataset

            return export_dataset(
                client,
                int(arguments["dataset_id"]),
                str(arguments["format"]),
                workgroup_id=arguments.get("workgroup_id"),
                sharing_policy=str(arguments.get("sharing_policy", "private")),
            )

        if name == "geopack_sdk_get_task":
            from geopack_sdk_mcp.tool_handlers.tasks import get_task

            return get_task(client, str(arguments["task_id"]))

        if name == "geopack_sdk_wait_for_task":
            from geopack_sdk_mcp.tool_handlers.tasks import wait_for_task

            return wait_for_task(
                client,
                str(arguments["task_id"]),
                timeout=int(arguments.get("timeout", 300)),
                interval=int(arguments.get("interval", 2)),
            )

        if name == "geopack_sdk_list_workflows":
            from geopack_sdk_mcp.tool_handlers.workflows import list_workflows

            return list_workflows(
                client,
                page=int(arguments.get("page", 1)),
                page_size=int(arguments.get("page_size", 20)),
                search_query=arguments.get("search_query"),
            )

        if name == "geopack_sdk_get_workflow":
            from geopack_sdk_mcp.tool_handlers.workflows import get_workflow_for_mcp

            return get_workflow_for_mcp(
                client,
                workflow_id=int(arguments["workflow_id"]),
                include_params=arguments.get("include_params", False),
            )

        if name == "geopack_sdk_submit_workflow":
            from geopack_sdk_mcp.tool_handlers.submit_workflow import submit_workflow

            return submit_workflow(
                client,
                workflow_id=int(arguments["workflow_id"]),
                params=arguments.get("params", {}),
                override_datastore_id=arguments.get("override_datastore_id"),
            )

        if name == "geopack_sdk_download_workflow_artifact":
            from geopack_sdk_mcp.tool_handlers.workflow_runs import download_workflow_artifact

            return download_workflow_artifact(
                client,
                run_id=int(arguments["run_id"]),
                artifact_id=int(arguments["artifact_id"]),
                save_path=arguments.get("save_path", "./"),
            )

        if name == "geopack_sdk_get_workflow_run":
            from geopack_sdk_mcp.tool_handlers.workflow_runs import get_workflow_run

            run_id = arguments.get("run_id", arguments.get("workflow_run_id"))
            return get_workflow_run(client, int(run_id))

        if name == "geopack_sdk_download_generated_file":
            from geopack_sdk_mcp.tool_handlers.generated_files import download_generated_file

            return download_generated_file(
                client,
                int(arguments["generated_file_id"]),
                str(arguments["save_path"]),
            )

        raise ValueError(f"Unknown MCP tool: {name}")
    except Exception as exc:
        return tool_error_payload(exc)


class InProcessMcpSession:
    """MCP-like session for notebooks: list_tools + call_tool without stdio subprocess."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def list_tools(self) -> ListedTools:
        _ensure_sdk_on_path()
        from geopack_sdk_mcp.server import mcp

        listed = mcp._tool_manager.list_tools()  # noqa: SLF001
        tools = [
            ListedTool(
                name=t.name,
                description=t.description or "",
                inputSchema=dict(t.parameters),
            )
            for t in listed
        ]
        return ListedTools(tools=tools)

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(dispatch_tool, self._client, name, arguments)


async def open_inprocess_session() -> InProcessMcpSession:
    _ensure_sdk_on_path()
    from geopack_sdk_mcp.auth_bootstrap import bootstrap_geopack_client

    client = await asyncio.to_thread(bootstrap_geopack_client)
    return InProcessMcpSession(client)
