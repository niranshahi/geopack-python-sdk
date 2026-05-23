"""FastMCP server for Geopack SDK (stdio transport by default)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .auth_bootstrap import AppContext, bootstrap_geopack_client
from .context import set_lifespan_client
from .resources import register_all_resources
from .tools import register_all_tools
from .confirmation_endpoints import register_confirmation_endpoints

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Login once at process start; reuse session for all tool calls."""
    client = bootstrap_geopack_client()
    set_lifespan_client(client)
    try:
        yield AppContext(client=client)
    finally:
        set_lifespan_client(None)
        logger.debug("Geopack SDK MCP: shutting down")
        
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
    lifespan=_app_lifespan,
    json_response=True,
)

register_all_tools(mcp)
register_all_resources(mcp)
register_confirmation_endpoints(mcp)
