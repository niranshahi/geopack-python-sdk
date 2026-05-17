"""Access the shared GeopackClient from FastMCP tool handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from geopack_sdk import GeopackClient

from .auth_bootstrap import AppContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context
    from mcp.server.session import ServerSession


def get_client(ctx: Any) -> GeopackClient:
    """Return the SDK client from FastMCP lifespan context."""
    return ctx.request_context.lifespan_context.client
