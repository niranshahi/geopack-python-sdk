"""Engine selection for the local geometry lane (slice 033).

Handlers import ONLY this module (and :mod:`engine`) — never an adapter. A future
engine enters by registering here; ``set_engine_for_tests`` lets the contract
suite run against a fake adapter without importing shapely.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from .engine import GeometryOpsEngine

_lock = threading.Lock()
_test_engine: Optional[GeometryOpsEngine] = None
_default_engine: Optional[GeometryOpsEngine] = None


def resolve_engine() -> GeometryOpsEngine:
    """Return the selected engine (default ``shapely``).

    ``GEOPACK_MCP_GEOMETRY_ENGINE`` may name another registered engine; an
    unknown name fails loud rather than silently falling back.
    """
    global _default_engine, _test_engine
    if _test_engine is not None:
        return _test_engine
    with _lock:
        if _default_engine is None:
            name = os.getenv("GEOPACK_MCP_GEOMETRY_ENGINE", "shapely").strip().lower()
            if name != "shapely":
                raise RuntimeError(
                    f"Unknown geometry engine {name!r}; only 'shapely' is registered."
                )
            from .shapely_engine import ShapelyGeometryEngine

            _default_engine = ShapelyGeometryEngine()
        return _default_engine


def set_engine_for_tests(engine: Optional[GeometryOpsEngine]) -> None:
    """Swap the engine for the duration of a test (``None`` restores default)."""
    global _test_engine
    _test_engine = engine