"""MCP tool: geocode place via Nominatim."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.geocoding import geocode_place


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_geocode_place(
        ctx: Context[ServerSession, AppContext],
        query: str,
        limit: int = 1,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Resolve a place name or address to WGS84 bbox [west, south, east, north] via Nominatim.

        Use the returned bbox in geopack_sdk_list_datasets(bbox=...). Not a Geopack API endpoint.
        """
        _ = get_client(ctx)  # ensures MCP auth is valid; geocoding is external
        try:
            return geocode_place(query, limit=limit)
        except Exception as exc:
            return tool_error_payload(exc)
