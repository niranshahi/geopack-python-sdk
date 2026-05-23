"""Access the shared GeopackClient from FastMCP tool and resource handlers."""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Any, Optional, Set


from geopack_sdk import GeopackClient

from .auth_bootstrap import AppContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context
    from mcp.server.session import ServerSession

_lifespan_client: Optional[GeopackClient] = None
_temp_files: Set[str] = set()
_temp_files_lock = threading.Lock()


def register_temp_file(path: str) -> None:
    """Register a local file to be cleaned up on server exit."""
    with _temp_files_lock:
        _temp_files.add(os.path.abspath(path))


def get_registered_temp_files() -> Set[str]:
    """Get all registered temp files for cleanup."""
    with _temp_files_lock:
        return set(_temp_files)


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
