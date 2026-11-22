"""Local map-service error codes (slice 033, Lane A) — additive to the contract."""

from __future__ import annotations

from typing import Any, Dict, Optional

#: The host forbids binding a loopback socket (sandboxed desktop host).
SERVICE_BLOCKED = "MAP_SERVICE_BLOCKED"
#: The service ran but an endpoint failed (bad layer, upstream error ...).
SERVICE_ERROR = "MAP_SERVICE_ERROR"

_HINTS: Dict[str, str] = {
    SERVICE_BLOCKED: (
        "This host forbids opening a loopback socket. Fall back to a static file or "
        "embedded HTML, and report the limitation."
    ),
    SERVICE_ERROR: "Check the layer id and the portal connection, then retry once.",
}


class MapServiceError(Exception):
    """A local-map refusal with a machine-readable ``code``."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: Optional[str] = None,
        key: Optional[str] = None,
        **extra: Any,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint or _HINTS.get(code)
        self.key = key
        self.invalid_args = [str(key)] if key else []
        self.extra = dict(extra)