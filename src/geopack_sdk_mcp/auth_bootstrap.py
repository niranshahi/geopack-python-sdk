"""Authenticate a GeopackClient once per MCP process (env-only; never from tool args)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from geopack_sdk import GeopackClient
from geopack_sdk.credentials import credentials_file_path, load_credentials
from geopack_sdk.env_loader import DEFAULT_ENV_FILE, load_geopack_env

from .auth_errors import AuthCheck, GeopackMCPAuthError

logger = logging.getLogger(__name__)

_precached_client: Optional[GeopackClient] = None


def _auth_checks(api_url: str) -> List[AuthCheck]:
    cred_path = credentials_file_path()
    stored = load_credentials(api_url=api_url)
    has_user = bool(os.getenv("GEOPACK_USERNAME"))
    has_pass = bool(os.getenv("GEOPACK_PASSWORD"))
    user_pass_detail = "set" if (has_user and has_pass) else "not set"
    if has_user != has_pass:
        user_pass_detail = "incomplete (need both USERNAME and PASSWORD)"

    return [
        AuthCheck(
            "GEOPACK_ACCESS_TOKEN",
            bool(os.getenv("GEOPACK_ACCESS_TOKEN")),
            "set" if os.getenv("GEOPACK_ACCESS_TOKEN") else "not set",
        ),
        AuthCheck(
            f"Token file ({cred_path})",
            stored is not None,
            f"found for {api_url}" if stored else "missing or no match for API URL",
        ),
        AuthCheck(
            "GEOPACK_USERNAME + GEOPACK_PASSWORD",
            has_user and has_pass,
            user_pass_detail,
        ),
    ]


def _missing_auth_error(api_url: str) -> GeopackMCPAuthError:
    sdk_env = DEFAULT_ENV_FILE
    fixes = [
        "Recommended: run `geopack-sdk login` in a terminal (with GEOPACK_API_URL set), "
        "then keep only GEOPACK_API_URL in Cursor mcp.json.",
        "Or add GEOPACK_USERNAME and GEOPACK_PASSWORD to mcp.json env (local dev only).",
        "Or set GEOPACK_ACCESS_TOKEN (+ optional GEOPACK_REFRESH_TOKEN) in mcp.json env.",
    ]
    if sdk_env.is_file():
        fixes.append(
            f"Note: python-sdk/.env is loaded automatically unless GEOPACK_MCP_SKIP_DOTENV=1. "
            f"If you commented credentials there, use one of the options above."
        )
    return GeopackMCPAuthError(
        summary="No Geoportal credentials found for this MCP process.",
        checks=_auth_checks(api_url),
        fixes=fixes,
    )


@dataclass
class AppContext:
    """Shared SDK client for the lifetime of one MCP server process."""

    client: GeopackClient


def bootstrap_geopack_client() -> GeopackClient:
    """
    Create and authenticate a sync GeopackClient from environment variables.

    Required: GEOPACK_API_URL
    Auth (first match wins):
      - GEOPACK_ACCESS_TOKEN (+ optional GEOPACK_REFRESH_TOKEN)
      - GEOPACK_API_KEY (not supported until backend exposes API-key auth)
      - Tokens from ``geopack-sdk login`` (~/.geopack/credentials.json)
      - GEOPACK_USERNAME + GEOPACK_PASSWORD

    Loads ``.env`` from the current working directory, then ``python-sdk/.env``
    (when installed from the repo). Set ``GEOPACK_MCP_SKIP_DOTENV=1`` in mcp.json
    to ignore dotenv files (MCP env + token file only).
    """
    global _precached_client
    if _precached_client is not None:
        return _precached_client

    load_geopack_env()
    client = GeopackClient()
    api_url = os.getenv("GEOPACK_API_URL") or client.base_url

    access_token = os.getenv("GEOPACK_ACCESS_TOKEN")
    refresh_token = os.getenv("GEOPACK_REFRESH_TOKEN")
    if access_token:
        _apply_tokens(client, access_token, refresh_token)
        logger.info("Geopack SDK MCP: using GEOPACK_ACCESS_TOKEN from environment")
        return client

    api_key = os.getenv("GEOPACK_API_KEY")
    if api_key:
        raise GeopackMCPAuthError(
            summary="GEOPACK_API_KEY is set but API-key auth is not supported yet.",
            checks=[
                AuthCheck("GEOPACK_API_KEY", True, "set — backend support pending"),
            ],
            fixes=[
                "Remove GEOPACK_API_KEY and use `geopack-sdk login` instead.",
                "Or use GEOPACK_ACCESS_TOKEN / username+password until API keys ship.",
                "See docs/09-sdk/mcp-design/mcp-auth.md.",
            ],
        )

    stored = load_credentials(api_url=api_url)
    if stored:
        _apply_tokens(client, stored.access_token, stored.refresh_token)
        logger.info(
            "Geopack SDK MCP: using tokens from %s (user=%s)",
            credentials_file_path(),
            stored.username or "unknown",
        )
        return client

    username = os.getenv("GEOPACK_USERNAME")
    password = os.getenv("GEOPACK_PASSWORD")
    if not username or not password:
        raise _missing_auth_error(api_url)

    try:
        client.auth.login(username=username, password=password)
    except Exception as exc:
        raise GeopackMCPAuthError(
            summary=f"Login failed for user '{username}' at {api_url}.",
            checks=_auth_checks(api_url),
            fixes=[
                "Verify username/password (or run `geopack-sdk login` again).",
                "Ensure GEOPACK_API_URL points to a running Geoportal API.",
                f"Server message: {exc}",
            ],
        ) from exc

    logger.info("Geopack SDK MCP: logged in as %s", username)
    return client


def precache_geopack_client(client: GeopackClient) -> None:
    """Store client from early startup check so lifespan does not bootstrap twice."""
    global _precached_client
    _precached_client = client


def _apply_tokens(
    client: GeopackClient,
    access_token: str,
    refresh_token: Optional[str] = None,
) -> None:
    client.auth.token = access_token
    client.auth.refresh_token = refresh_token
    client.session.headers.update({"Authorization": f"Bearer {access_token}"})
