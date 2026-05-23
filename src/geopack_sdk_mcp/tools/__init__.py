"""Register Geopack SDK MCP tools (v0 read-only + v1 export/download)."""

from __future__ import annotations

from typing import Any


def register_all_tools(mcp: Any) -> None:
    from . import datasets, generated_files, geocoding, policy, tasks, workflow_runs, workflows

    geocoding.register(mcp)
    policy.register(mcp)
    datasets.register(mcp)
    tasks.register(mcp)
    workflows.register(mcp)
    workflow_runs.register(mcp)
    generated_files.register(mcp)
