"""Local geometry lane (slice 033, Lane C).

GeoJSON-only compute: no portal call, no shapely type crossing the port. The
default engine is lazily imported so importing this package does not require
shapely to be installed.
"""

from .engine import (
    ALL_OPS,
    OVERLAY_MODES,
    GeometryOpProvenance,
    GeometryOpResult,
    GeometryOpsEngine,
)
from .errors import (
    EMPTY_RESULT,
    ENGINE_FAILED,
    INVALID_ARGS,
    UNSUPPORTED_OP,
    GeometryOpError,
)
from .select import resolve_engine, set_engine_for_tests

__all__ = [
    "ALL_OPS",
    "OVERLAY_MODES",
    "EMPTY_RESULT",
    "ENGINE_FAILED",
    "INVALID_ARGS",
    "UNSUPPORTED_OP",
    "GeometryOpError",
    "GeometryOpProvenance",
    "GeometryOpResult",
    "GeometryOpsEngine",
    "resolve_engine",
    "set_engine_for_tests",
]