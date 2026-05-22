"""MCP tool: geocode place via Nominatim."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.geocoding import geocode_place
from ..tool_schema import GeocodeLimit, GeocodeResult, PlaceQuery


def register(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "Resolve place name or address to WGS84 bbox [west, south, east, north] (Nominatim). "
            "Pass bbox to geopack_sdk_list_datasets. Not a Geopack API endpoint."
        ),
    )
    def geopack_sdk_geocode_place(
        ctx: Context[ServerSession, AppContext],
        query: PlaceQuery,
        limit: GeocodeLimit = 1,
    ) -> GeocodeResult:
        _ = get_client(ctx)  # ensures MCP auth is valid; geocoding is external
        try:
            return geocode_place(query, limit=limit)
        except Exception as exc:
            return tool_error_payload(exc)
