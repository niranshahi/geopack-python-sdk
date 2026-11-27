"""FastMCP server for Geopack SDK (stdio transport by default)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .auth_bootstrap import AppContext, bootstrap_geopack_client
from .auth_errors import GeopackMCPAuthError
from .context import set_lifespan_client
from .guide import SERVER_INSTRUCTIONS
from .resources import register_all_resources
from .tools import register_all_tools
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Login once at process start; reuse session for all tool calls.

    Degraded mode (slice 034 P6): if no credentials/session are available, the
    server still starts. Tools answer an actionable ``AUTH_REQUIRED`` error and
    ``geopack_sdk_auth_status`` explains how to log in — instead of the process
    exiting with a message only visible in host logs.
    """
    client = None
    try:
        client = bootstrap_geopack_client()
    except GeopackMCPAuthError as exc:
        logger.error(
            "Geopack SDK MCP: unauthenticated — starting in degraded mode. Tools will answer "
            "AUTH_REQUIRED until `geopack-sdk login` is run.\n%s",
            exc.format_message(),
        )
    set_lifespan_client(client)

    # Preload the local geometry engine (slice 033, Lane C) so the FIRST
    # geometry_op call does not pay the shapely/pyproj import cost (cold-start
    # timeouts). Optional lane: any failure must not block startup.
    try:
        from .geometry import resolve_engine

        resolve_engine()
    except Exception:  # noqa: BLE001 - the lane degrades to a coded tool error
        logger.debug("Geometry engine preload failed", exc_info=True)

    try:
        yield AppContext(client=client)
    finally:
        set_lifespan_client(None)
        logger.debug("Geopack SDK MCP: shutting down")

        # Stop the opt-in localhost map data service (slice 033).
        try:
            from .maps import stop_service

            stop_service()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            logger.debug("Map service shutdown failed", exc_info=True)

        # Temporary asset Garbage Collection
        from .context import get_registered_temp_files
        import os
        
        temp_files = get_registered_temp_files()
        if temp_files:
            logger.info("Cleaning up %d temporary downloaded files...", len(temp_files))
            for path in temp_files:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        logger.debug("Removed temp file: %s", path)
                    except OSError as e:
                        logger.warning("Failed to remove temp file %s: %s", path, e)



mcp = FastMCP(
    "Geopack SDK MCP",
    instructions=SERVER_INSTRUCTIONS,
    lifespan=_app_lifespan,
    json_response=True,
)

register_all_tools(mcp)
register_all_resources(mcp)
