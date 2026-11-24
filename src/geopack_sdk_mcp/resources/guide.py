"""MCP resource: the server usage guide (Markdown playbook)."""

from __future__ import annotations

from typing import Any

from ..guide import GUIDE_URI, build_guide_markdown


def register(mcp: Any) -> None:
    @mcp.resource(
        GUIDE_URI,
        mime_type="text/markdown",
        description=(
            "How to use this server: the discover-first workflow, a full tool inventory "
            "grouped by safety, task recipes and gotchas. Worth reading once per session."
        ),
    )
    def geopack_guide() -> str:
        return build_guide_markdown()
