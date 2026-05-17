"""Register Geopack SDK MCP v0 read-only tools."""

from __future__ import annotations

from typing import Any


def register_all_tools(mcp: Any) -> None:
    from . import datasets, tasks, workflow_runs, workflows

    datasets.register(mcp)
    tasks.register(mcp)
    workflows.register(mcp)
    workflow_runs.register(mcp)
