"""Local map data service (slice 033, Lane A).

Process-global lifecycle: one :class:`LocalService` per MCP process, started
lazily by ``show_map`` when ``GEOPACK_MCP_MAP_SERVICE=1`` and stopped on the
MCP lifespan exit (or its idle timeout).
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from .errors import SERVICE_BLOCKED, MapServiceError
from .manifest import MapLayer, MapManifest, layer_from_spec
from .service import LocalService, service_enabled

_service: Optional[LocalService] = None
_lock = threading.Lock()

__all__ = [
    "LocalService",
    "MapLayer",
    "MapManifest",
    "MapServiceError",
    "layer_from_spec",
    "get_service",
    "get_or_start_service",
    "stop_service",
    "reset_for_tests",
    "service_enabled",
]


def get_or_start_service(client: Any, *, force: bool = False, **kwargs: Any) -> LocalService:
    """Return the process service, starting it on first use.

    ``force`` bypasses the ``GEOPACK_MCP_MAP_SERVICE`` opt-in (tests only). A
    host that forbids binding answers :class:`MapServiceError`
    ``MAP_SERVICE_BLOCKED`` — never a crash.
    """
    global _service, _service_client_id

    if not force and not service_enabled():
        raise MapServiceError(
            SERVICE_BLOCKED,
            "the local map service is opt-in and is not enabled (GEOPACK_MCP_MAP_SERVICE is not 1).",
            hint=(
                "Ask the user to set GEOPACK_MCP_MAP_SERVICE=1 (loopback-only, opt-in) and retry; "
                "until then, return data as GeoJSON in the tool result."
            ),
        )

    with _lock:
        if _service is None:
            _service = LocalService(client, **kwargs)
        _service.client = client
        if _service.port is None:
            _service.start()
        return _service


def get_service() -> Optional[LocalService]:
    return _service


def stop_service() -> None:
    global _service
    with _lock:
        if _service is not None:
            _service.stop()
        _service = None


def reset_for_tests() -> None:
    """Stop and forget the process service (test isolation)."""
    stop_service()