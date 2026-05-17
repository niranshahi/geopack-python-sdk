"""Map SDK exceptions to safe MCP tool error payloads (no tokens in output)."""

from __future__ import annotations

from typing import Any, Dict

from geopack_sdk.exceptions import GeopackAPIError, GeopackError


def tool_error_payload(exc: BaseException) -> Dict[str, Any]:
    """Structured error dict for tool results — never includes credentials."""
    if isinstance(exc, GeopackAPIError):
        return {
            "error": True,
            "type": "GeopackAPIError",
            "status_code": exc.status_code,
            "message": exc.message,
        }
    if isinstance(exc, GeopackError):
        return {
            "error": True,
            "type": type(exc).__name__,
            "message": exc.message,
        }
    return {
        "error": True,
        "type": type(exc).__name__,
        "message": str(exc),
    }
