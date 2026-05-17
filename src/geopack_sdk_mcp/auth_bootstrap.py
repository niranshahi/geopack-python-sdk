"""Authenticate a GeopackClient once per MCP process (env-only; never from tool args)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from geopack_sdk import GeopackClient

logger = logging.getLogger(__name__)


def _load_geopack_env() -> None:
    """Load ``python-sdk/.env`` for local runs (same as ``test_mcp_sdk.py`` / ``test_sdk.py``)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    if load_dotenv():
        return

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.is_file():
        load_dotenv(env_file)


@dataclass
class AppContext:
    """Shared SDK client for the lifetime of one MCP server process."""

    client: GeopackClient


def bootstrap_geopack_client() -> GeopackClient:
    """
    Create and authenticate a sync GeopackClient from environment variables.

    Required: GEOPACK_API_URL
    Auth (one of):
      - GEOPACK_ACCESS_TOKEN (+ optional GEOPACK_REFRESH_TOKEN)
      - GEOPACK_USERNAME + GEOPACK_PASSWORD

    Loads ``.env`` from the current working directory, then ``python-sdk/.env``
  (when installed from the repo). Cursor should still pass ``env`` in ``mcp.json``.
    """
    _load_geopack_env()
    client = GeopackClient()

    access_token = os.getenv("GEOPACK_ACCESS_TOKEN")
    if access_token:
        client.auth.token = access_token
        client.auth.refresh_token = os.getenv("GEOPACK_REFRESH_TOKEN")
        client.session.headers.update({"Authorization": f"Bearer {access_token}"})
        logger.info("Geopack SDK MCP: using GEOPACK_ACCESS_TOKEN from environment")
        return client

    username = os.getenv("GEOPACK_USERNAME")
    password = os.getenv("GEOPACK_PASSWORD")
    if not username or not password:
        raise ValueError(
            "Geopack SDK MCP requires authentication via environment: "
            "set GEOPACK_ACCESS_TOKEN, or GEOPACK_USERNAME and GEOPACK_PASSWORD."
        )

    client.auth.login(username=username, password=password)
    logger.info("Geopack SDK MCP: logged in as %s", username)
    return client
