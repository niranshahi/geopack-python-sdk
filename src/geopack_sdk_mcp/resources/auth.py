"""MCP resource: authentication status + first-run guidance (slice 034 P6)."""

from __future__ import annotations

from typing import Any, Dict

from ..context import peek_lifespan_client
from ..tools.auth import build_auth_status

AUTH_URI = "geopack://auth"


def _markdown(status: Dict[str, Any]) -> str:
    lines = ["# Geopack MCP authentication", ""]
    if status.get("authenticated"):
        lines.append("- Status: **authenticated**")
    else:
        lines.append("- Status: **not authenticated**")
        lines.append(f"- Next step: {status.get('nextStep')}")
    lines.append(f"- Profile: `{status.get('profile')}`")
    lines.append(f"- API URL: {status.get('apiUrl') or '(unset)'}")
    lines.append(f"- Credential store: {status.get('credentialStore')}")
    lines.append(f"- Session present: {status.get('sessionPresent')}")
    checks = status.get("checks") or []
    if checks:
        lines.extend(["", "## Checks"])
        for check in checks:
            mark = "ok" if check.get("ok") else "missing"
            lines.append(f"- [{mark}] {check.get('label')}: {check.get('detail') or ''}")
    return "\n".join(lines)


def register(mcp: Any) -> None:
    @mcp.resource(
        AUTH_URI,
        mime_type="text/markdown",
        description=(
            "Whether this MCP process is authenticated and, if not, the exact "
            "`geopack-sdk login` step. Read this when tools answer AUTH_REQUIRED."
        ),
    )
    def geopack_auth() -> str:
        return _markdown(build_auth_status(peek_lifespan_client()))