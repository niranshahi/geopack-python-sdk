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
    from .auth_bootstrap import bootstrap_geopack_client, precache_geopack_client
    from .auth_errors import GeopackMCPAuthError
    from .context import set_lifespan_client
    from .server import mcp

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting Geopack SDK MCP (stdio). Waiting for MCP host — "
        "Ctrl+C to stop. Errors go to stderr, not stdout."
    )
    try:
        client = bootstrap_geopack_client()
    except GeopackMCPAuthError as exc:
        print(exc.format_message(), file=sys.stderr)
        raise SystemExit(1) from None

    precache_geopack_client(client)
    set_lifespan_client(client)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
