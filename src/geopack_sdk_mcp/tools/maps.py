"""MCP tool: local map data service (slice 033, Lane A).

``geopack_sdk_show_map`` creates/updates a localhost-only service that proxies
portal data (using the MCP's own auth) and serves local files, so a page can
reference a URL instead of embedding data. No map image is produced.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import host_service_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_result, tool_result
from ..tool_handlers.maps import show_map
from ..tool_schema import BasemapName, MapIdArg, MapLayers, MapTitle, OpenBrowser


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=host_service_tool("geopack_sdk_show_map"),
        description=(
            "Create or update a LOCALHOST-ONLY data service that proxies portal data with the "
            "MCP's own credentials and serves local files, then declare map layers and return "
            "stable URLs ({serviceUrl, manifestUrl, layers[].dataUrl/tileUrl, accessToken}). A "
            "page can reference these URLs instead of embedding data. Opt-in: requires "
            "GEOPACK_MCP_MAP_SERVICE=1. The portal credential never reaches the browser. No map "
            "image is rendered (the built-in viewer is a later lane)."
        ),
    )
    def geopack_sdk_show_map(
        ctx: Context[ServerSession, AppContext],
        title: MapTitle = None,
        layers: MapLayers = None,
        map_id: MapIdArg = None,
        open_browser: OpenBrowser = False,
        basemap: BasemapName = None,
    ) -> CallToolResult:
        try:
            client = get_client(ctx)
            return tool_result(
                show_map(
                    client,
                    title=title,
                    layers=layers,
                    map_id=map_id,
                    open_browser=open_browser,
                    basemap=basemap,
                )
            )
        except Exception as exc:  # noqa: BLE001 - the error contract renders it
            return tool_error_result(exc)