"""FastMCP server for Geopack SDK (stdio transport by default)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .auth_bootstrap import AppContext, bootstrap_geopack_client
from .tools import register_all_tools

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Login once at process start; reuse session for all tool calls."""
    client = bootstrap_geopack_client()
    try:
        yield AppContext(client=client)
    finally:
        logger.debug("Geopack SDK MCP: shutting down")


mcp = FastMCP(
    "Geopack SDK MCP",
    lifespan=_app_lifespan,
    json_response=True,
)

register_all_tools(mcp)
