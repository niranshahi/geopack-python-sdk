"""Local-geometry error codes (slice 033) — additive to the MCP error contract.

The geometry lane is *local compute*: it never calls the portal, so it owns its
own refusal vocabulary. ``code`` values are a public contract — adding one is
fine, renaming one breaks every host that branches on it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

#: The requested op is not advertised by the selected engine (or the engine
#: cannot honour a sub-mode such as geodesic buffer in v1).
UNSUPPORTED_OP = "GEOMETRY_UNSUPPORTED_OP"
#: The inputs were valid but the op produced nothing (disjoint intersection,
#: empty hull). Never a silent empty geometry — an explicit state.
EMPTY_RESULT = "GEOMETRY_EMPTY_RESULT"
#: The engine adapter threw; the message is surfaced verbatim.
ENGINE_FAILED = "GEOMETRY_ENGINE_FAILED"
#: A client-side argument refusal (unknown op/units/format, missing CRS ...).
INVALID_ARGS = "INVALID_ARGS"

_DEFAULT_HINTS: Dict[str, str] = {
    UNSUPPORTED_OP: (
        "Use one of the ops the engine advertises (the message lists the legal set)."
    ),
    EMPTY_RESULT: (
        "The inputs produced no geometry (for example a disjoint intersection). "
        "Report it honestly or choose another op instead of retrying unchanged."
    ),
    ENGINE_FAILED: (
        "The geometry engine rejected the input. Run op='validate' (and 'fix') on the "
        "geometry, then retry."
    ),
    INVALID_ARGS: (
        "Correct the named argument and retry; the message lists the accepted values."
    ),
}


class GeometryOpError(Exception):
    """A local geometry refusal carrying a machine-readable ``code``.

    Not a subclass of the SDK's API errors — this lane never touches the
    portal. The MCP error contract renders ``code``/``hint``/``invalidArgs``
    from this object (see ``geopack_sdk_mcp.errors``).
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        key: Optional[str] = None,
        hint: Optional[str] = None,
        invalid_args: Optional[List[str]] = None,
        **extra: Any,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.key = key
        self.hint = hint or _DEFAULT_HINTS.get(code)
        if invalid_args is not None:
            self.invalid_args = [str(name) for name in invalid_args]
        elif key:
            self.invalid_args = [str(key)]
        else:
            self.invalid_args = []
        self.extra = dict(extra)


def unsupported_op(op: str, *, engine: str, legal: Any) -> GeometryOpError:
    legal_list = ", ".join(sorted(legal))
    return GeometryOpError(
        UNSUPPORTED_OP,
        f"op '{op}' is not supported by engine '{engine}'.",
        key="op",
        hint=f"Use one of: {legal_list}.",
        invalid_args=["op"],
        engine=engine,
        legalOps=sorted(legal),
    )


def empty_result(op: str) -> GeometryOpError:
    return GeometryOpError(
        EMPTY_RESULT,
        f"op '{op}' produced no geometry for the given inputs.",
        key="geojson",
    )


def engine_failed(op: str, message: str) -> GeometryOpError:
    return GeometryOpError(
        ENGINE_FAILED,
        f"op '{op}' failed: {message}",
        hint=(
            "Surface this message verbatim; the engine refused the geometry. "
            "Try op='fix' first."
        ),
    )
