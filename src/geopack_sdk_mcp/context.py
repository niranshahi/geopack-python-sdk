"""Access the shared GeopackClient from FastMCP tool and resource handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from geopack_sdk import GeopackClient

from .auth_bootstrap import AppContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context
    from mcp.server.session import ServerSession

_lifespan_client: Optional[GeopackClient] = None


def set_lifespan_client(client: GeopackClient | None) -> None:
    """Set process-wide client (called from FastMCP lifespan)."""
    global _lifespan_client
    _lifespan_client = client


def get_lifespan_client() -> GeopackClient:
    """Return SDK client for resource handlers (lifespan-scoped, no request Context)."""
    if _lifespan_client is None:
        raise RuntimeError("Geopack SDK MCP client is not initialized")
    return _lifespan_client


def get_client(ctx: Any) -> GeopackClient:
    """Return the SDK client from FastMCP tool Context, with lifespan fallback."""
    try:
        return ctx.request_context.lifespan_context.client
    except (ValueError, AttributeError):
        return get_lifespan_client()
