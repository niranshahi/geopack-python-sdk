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
    from .server import mcp

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting Geopack SDK MCP (stdio). Waiting for MCP host — "
        "Ctrl+C to stop. Errors go to stderr, not stdout."
    )
    # Auth is resolved in the server lifespan. If it fails, the server starts in
    # degraded mode (slice 034 P6): tools answer an actionable AUTH_REQUIRED error
    # and `geopack_sdk_auth_status` reports the fix, instead of the process
    # exiting with a message only visible in the host's logs.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()