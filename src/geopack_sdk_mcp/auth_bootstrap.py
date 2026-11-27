"""Authenticate a GeopackClient once per MCP process (env-only; never from tool args)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from geopack_sdk import GeopackClient
from geopack_sdk.auth_state import store_key
from geopack_sdk.credentials import (
    CredentialStoreError,
    credentials_file_path,
    load_credentials,
    resolve_store,
)
from geopack_sdk.env_loader import DEFAULT_ENV_FILE, load_geopack_env

from .auth_errors import AuthCheck, GeopackMCPAuthError

logger = logging.getLogger(__name__)

_precached_client: Optional[GeopackClient] = None

#: Every call this process makes is attributed to the MCP lane (030 §2 reads
#: ``X-Geoportal-Client`` to derive the run source). Set once, here: the client
#: is the single source of truth for attribution (slice 016 §1.1).
MCP_CLIENT_HEADERS = {"X-Geoportal-Client": "mcp"}


def _auth_checks(api_url: str) -> List[AuthCheck]:
    cred_path = credentials_file_path()
    stored = load_credentials(api_url=api_url)
    has_user = bool(os.getenv("GEOPACK_USERNAME"))
    has_pass = bool(os.getenv("GEOPACK_PASSWORD"))
    user_pass_detail = "set" if (has_user and has_pass) else "not set"
    if has_user != has_pass:
        user_pass_detail = "incomplete (need both USERNAME and PASSWORD)"

    profile = os.getenv("GEOPACK_PROFILE") or "default"
    try:
        store = resolve_store(None)
        has_store_token = bool(store.get_refresh_token(store_key(api_url, profile)))
        store_detail = (
            f"{store.name}: {'refresh token present' if has_store_token else 'no refresh token'}"
        )
    except CredentialStoreError as exc:
        has_store_token = False
        store_detail = f"unavailable ({exc})"

    return [
        AuthCheck(
            "GEOPACK_ACCESS_TOKEN",
            bool(os.getenv("GEOPACK_ACCESS_TOKEN")),
            "set" if os.getenv("GEOPACK_ACCESS_TOKEN") else "not set",
        ),
        AuthCheck(
            f"Credential store (profile '{profile}')",
            has_store_token,
            store_detail,
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
    """Shared SDK client for the lifetime of one MCP server process.

    ``client`` is ``None`` in **degraded mode** (no stored session / token at
    startup, slice 034 P6): the server still starts and every tool answers an
    actionable ``AUTH_REQUIRED`` error until the user runs ``geopack-sdk login``.
    """

    client: Optional[GeopackClient]


def authentication_required() -> GeopackMCPAuthError:
    """The actionable error raised by tools when the process is unauthenticated."""
    return _missing_auth_error(os.getenv("GEOPACK_API_URL") or "")


def bootstrap_geopack_client() -> GeopackClient:
    """
    Create and authenticate a sync GeopackClient from environment variables.

    Required: GEOPACK_API_URL
    Auth (first match wins):
      - GEOPACK_ACCESS_TOKEN (+ optional GEOPACK_REFRESH_TOKEN)
      - GEOPACK_API_KEY (not supported until backend exposes API-key auth)
      - Stored profile in the credential store (GEOPACK_PROFILE; refreshed at startup)
      - Legacy token file from ``geopack-sdk login`` (~/.geopack/credentials.json)
      - GEOPACK_USERNAME + GEOPACK_PASSWORD (dev only, deprecated)

    Loads ``.env`` from the current working directory, then ``python-sdk/.env``
    (when installed from the repo). Set ``GEOPACK_MCP_SKIP_DOTENV=1`` in mcp.json
    to ignore dotenv files (MCP env + token file only).
    """
    global _precached_client
    if _precached_client is not None:
        return _precached_client

    load_geopack_env()
    profile = os.getenv("GEOPACK_PROFILE") or "default"
    store = None
    try:
        store = resolve_store(None)
    except CredentialStoreError:
        store = None

    client = GeopackClient(
        default_headers=dict(MCP_CLIENT_HEADERS),
        credential_store=store,
        auth_profile=profile,
    )
    api_url = os.getenv("GEOPACK_API_URL") or client.base_url

    # 1) Explicit access token from the environment.
    access_token = os.getenv("GEOPACK_ACCESS_TOKEN")
    refresh_token = os.getenv("GEOPACK_REFRESH_TOKEN")
    if access_token:
        _apply_tokens(client, access_token, refresh_token)
        logger.info("Geopack SDK MCP: using GEOPACK_ACCESS_TOKEN from environment")
        return client

    # 2) API keys are not supported yet.
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

    # 3) Stored profile (D10/D11): load the refresh token and mint a fresh access
    #    token at startup, so a rotated token is never relied on from the prior run.
    if store is not None and client.auth_state.load_from_store():
        try:
            client.auth.refresh()
            logger.info(
                "Geopack SDK MCP: refreshed stored session for profile '%s'", profile
            )
            return client
        except Exception as exc:
            logger.warning(
                "Geopack SDK MCP: stored session refresh failed for profile '%s': %s",
                profile,
                exc,
            )

    # 4) Legacy token file (pre-034) — kept for migration (D18).
    stored = load_credentials(api_url=api_url)
    if stored:
        _apply_tokens(client, stored.access_token, stored.refresh_token)
        logger.info(
            "Geopack SDK MCP: using legacy token file %s (user=%s)",
            credentials_file_path(),
            stored.username or "unknown",
        )
        return client

    # 5) Username/password from the environment — dev fallback only (deprecated).
    username = os.getenv("GEOPACK_USERNAME")
    password = os.getenv("GEOPACK_PASSWORD")
    if not username or not password:
        raise _missing_auth_error(api_url)

    logger.warning(
        "Geopack SDK MCP: GEOPACK_USERNAME/PASSWORD is deprecated — prefer `geopack-sdk login`."
    )
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
