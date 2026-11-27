"""MCP tool: authentication status + first-run guidance (slice 034 P6).

This is the only tool that works in degraded mode. A host that starts without a
stored session can call it to learn exactly what to do (run ``geopack-sdk login``),
so the agent can guide the human instead of leaving a silent failure in the logs.
It reads only local configuration/state and never contacts the portal.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import read_tool
from ..auth_bootstrap import AppContext, _auth_checks
from ..context import get_client
from ..errors import tool_error_result, tool_result


def _resolve_store_name() -> str:
    try:
        from geopack_sdk.credentials import resolve_store

        return resolve_store(None).name
    except Exception:  # noqa: BLE001 - status must never fail
        return "unavailable"


def _session_present() -> bool:
    try:
        from geopack_sdk.auth_state import store_key
        from geopack_sdk.credentials import resolve_store

        api_url = os.getenv("GEOPACK_API_URL") or ""
        profile = os.getenv("GEOPACK_PROFILE") or "default"
        return bool(resolve_store(None).get_refresh_token(store_key(api_url, profile)))
    except Exception:  # noqa: BLE001 - status must never fail
        return False


def build_auth_status(client: Optional[Any]) -> Dict[str, Any]:
    api_url = os.getenv("GEOPACK_API_URL") or ""
    profile = os.getenv("GEOPACK_PROFILE") or "default"
    authenticated = client is not None
    checks = (
        [
            {"label": c.label, "ok": c.ok, "detail": c.detail}
            for c in _auth_checks(api_url)
        ]
        if api_url
        else []
    )
    payload: Dict[str, Any] = {
        "authenticated": authenticated,
        "apiUrl": api_url or None,
        "profile": profile,
        "credentialStore": _resolve_store_name(),
        "sessionPresent": _session_present(),
        "checks": checks,
    }
    if not authenticated:
        payload["nextStep"] = (
            "Run `geopack-sdk login` in a terminal (with GEOPACK_API_URL set), then restart "
            "the MCP host."
        )
    return payload


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=read_tool("geopack_sdk_auth_status"),
        description=(
            "Reports whether this MCP process is authenticated and, if not, exactly how to log in "
            "(run `geopack-sdk login`). Call this first when other tools answer AUTH_REQUIRED or "
            "when the user asks why the server is not working. Reads only local config; never "
            "contacts the portal, never returns a token."
        ),
    )
    def geopack_sdk_auth_status(
        ctx: Context[ServerSession, AppContext],
    ) -> CallToolResult:
        try:
            client = None
            try:
                client = get_client(ctx)
            except Exception:  # noqa: BLE001 - degraded mode is expected here
                client = None
            return tool_result(build_auth_status(client))
        except Exception as exc:  # noqa: BLE001 - status must never crash the turn
            return tool_error_result(exc)