"""Register Geopack SDK MCP resources."""

from __future__ import annotations

from typing import Any


def register_all_resources(mcp: Any) -> None:
    from . import datasets, generated_files

    datasets.register(mcp)
    generated_files.register(mcp)
