"""Register Geopack SDK MCP resources."""

from __future__ import annotations

from typing import Any


def register_all_resources(mcp: Any) -> None:
    from . import auth, datasets, generated_files, guide

    auth.register(mcp)
    datasets.register(mcp)
    generated_files.register(mcp)
    guide.register(mcp)
