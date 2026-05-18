"""MCP resource: generated file download (export outputs)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp.exceptions import ResourceError

from ..context import get_lifespan_client
from ..resource_handlers.generated_files import fetch_generated_file_bytes


def register(mcp: Any) -> None:
    @mcp.resource(
        "generated-file://{file_id}/download",
        mime_type="application/octet-stream",
        description=(
            "Binary body of a generated export file. Prefer geopack_sdk_download_generated_file "
            "for large files on disk; use resources/read for host UI preview."
        ),
    )
    def geopack_generated_file_download(file_id: str) -> bytes:
        try:
            gf_id = int(file_id)
        except ValueError as exc:
            raise ResourceError(f"Invalid file_id: {file_id}") from exc

        try:
            body, _mime = fetch_generated_file_bytes(get_lifespan_client(), gf_id)
        except Exception as exc:
            raise ResourceError(str(exc)) from exc

        return body
