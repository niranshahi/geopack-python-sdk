"""Register Geopack SDK MCP tools (reads, read lanes and the two write lanes)."""

from __future__ import annotations

from typing import Any


def register_all_tools(mcp: Any) -> None:
    from . import (
        analysis,
        datasets,
        edits,
        generated_files,
        geocoding,
        geometry,
        maps,
        policy,
        quotas,
        tasks,
        workflow_runs,
        workflows,
    )

    geocoding.register(mcp)
    policy.register(mcp)
    datasets.register(mcp)
    tasks.register(mcp)
    workflows.register(mcp)
    analysis.register(mcp)
    workflow_runs.register(mcp)
    generated_files.register(mcp)
    quotas.register(mcp)
    edits.register(mcp)
    maps.register(mcp)
    geometry.register(mcp)
