"""CLI entry point: ``geopack-sdk-mcp`` (stdio MCP transport)."""

from __future__ import annotations

import logging
import sys


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # Import server after logging is configured; lifespan calls bootstrap_geopack_client()
    from .server import mcp

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting Geopack SDK MCP (stdio). Waiting for MCP host — "
        "Ctrl+C to stop. Errors go to stderr, not stdout."
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
