"""MCP resource: dataset thumbnails."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp.exceptions import ResourceError

from ..context import get_lifespan_client
from ..resource_handlers.datasets import fetch_dataset_thumbnail


def register(mcp: Any) -> None:
    @mcp.resource(
        "dataset://{dataset_id}/thumbnail",
        mime_type="image/png",
        description="Dataset preview image (PNG). Use resources/read; not included in tool JSON.",
    )
    def geopack_dataset_thumbnail(dataset_id: str) -> bytes:
        try:
            ds_id = int(dataset_id)
        except ValueError as exc:
            raise ResourceError(f"Invalid dataset_id: {dataset_id}") from exc

        try:
            body, mime = fetch_dataset_thumbnail(get_lifespan_client(), ds_id)
        except Exception as exc:
            raise ResourceError(str(exc)) from exc

        _ = mime
        return body
