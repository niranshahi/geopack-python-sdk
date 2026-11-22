"""The geometry engine port (slice 033, Lane C).

Mirrors the FE slice-014 contract: **GeoJSON dicts in, GeoJSON dicts out** — no
engine-specific type ever crosses this boundary, so a future engine (turf, a
WASM port, ...) is swapped by editing :mod:`select` and the adapter only.

Every op returns a :class:`GeometryOpResult` carrying ``provenance``
(``engine``/``methodUsed``/``crsUsed``/``unitsUsed``) — never a bare geometry:
the honesty shape ``geometry_measure`` established in the FE harness.

The default engine (:mod:`shapely_engine`) is the ONLY module allowed to import
``shapely``/``pyproj``/``geopandas``; the swap-enforcement test fences that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional

#: The op ids the lane can advertise (superset; each engine narrows it).
ALL_OPS: FrozenSet[str] = frozenset(
    {
        "buffer",
        "overlay",
        "convex_hull",
        "envelope",
        "dissolve",
        "simplify",
        "validate",
        "fix",
        "convert",
        "project",
        "measure",
        "distance",
        "nearest",
        "point_on_surface",
        "line_between",
        "smooth",
        "create",
        "describe",
    }
)

OVERLAY_MODES: FrozenSet[str] = frozenset(
    {"union", "intersection", "difference", "xor", "clip"}
)


@dataclass(frozen=True)
class GeometryOpProvenance:
    """What the math actually ran as — echoed on every result."""

    engine: str
    method_used: str  # 'planar' | 'geodesic' | 'none' (structural, CRS-preserving)
    crs_used: Optional[int]
    units_used: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "engine": self.engine,
            "methodUsed": self.method_used,
            "crsUsed": self.crs_used,
        }
        if self.units_used:
            payload["unitsUsed"] = self.units_used
        return payload


@dataclass
class GeometryOpResult:
    """A geometry op result: a GeoJSON-ish dict plus its provenance."""

    geojson: Dict[str, Any]
    provenance: GeometryOpProvenance
    extra: Dict[str, Any] = field(default_factory=dict)


class GeometryOpsEngine(ABC):
    """Abstract local geometry engine (GeoJSON-only contract)."""

    #: Stable engine id ('shapely').
    id: str = "abstract"
    #: Op ids this engine can actually run.
    capabilities: FrozenSet[str] = frozenset()

    def supports(self, op: str) -> bool:
        return op in self.capabilities

    @abstractmethod
    def buffer(self, fc: Dict[str, Any], *, distance: float, units: str, method: str,
               wkid: Optional[int] = None, segments: int = 64,
               dissolve: bool = True) -> GeometryOpResult: ...

    @abstractmethod
    def overlay(self, a: Dict[str, Any], b: Optional[Dict[str, Any]], op: str, *,
                wkid: Optional[int] = None) -> GeometryOpResult: ...

    @abstractmethod
    def convex_hull(self, fc: Dict[str, Any], *, merge: bool = True) -> GeometryOpResult: ...

    @abstractmethod
    def envelope(self, fc: Dict[str, Any]) -> GeometryOpResult: ...

    @abstractmethod
    def dissolve(self, fc: Dict[str, Any], group_by: list) -> GeometryOpResult: ...

    @abstractmethod
    def simplify(self, fc: Dict[str, Any], *, tolerance: float,
                 wkid: Optional[int] = None) -> GeometryOpResult: ...

    @abstractmethod
    def validate(self, geojson: Dict[str, Any]) -> GeometryOpResult: ...

    @abstractmethod
    def fix(self, geojson: Dict[str, Any]) -> GeometryOpResult: ...

    @abstractmethod
    def convert(self, geojson: Dict[str, Any], *, fmt: str) -> GeometryOpResult: ...

    @abstractmethod
    def project(self, fc: Dict[str, Any], *, wkid: int,
                output_wkid: Optional[int] = None) -> GeometryOpResult: ...

    @abstractmethod
    def measure(self, fc: Dict[str, Any], *, units: Optional[str] = None,
                wkid: Optional[int] = None) -> GeometryOpResult: ...

    @abstractmethod
    def distance(self, a: Dict[str, Any], b: Dict[str, Any], *,
                 wkid: Optional[int] = None,
                 units: Optional[str] = None) -> GeometryOpResult: ...

    @abstractmethod
    def nearest(self, a: Dict[str, Any], b: Dict[str, Any], *,
                wkid: Optional[int] = None,
                units: Optional[str] = None) -> GeometryOpResult: ...

    @abstractmethod
    def point_on_surface(self, fc: Dict[str, Any]) -> GeometryOpResult: ...

    @abstractmethod
    def line_between(self, a: Dict[str, Any], b: Dict[str, Any], *,
                     wkid: Optional[int] = None) -> GeometryOpResult: ...

    @abstractmethod
    def smooth(self, fc: Dict[str, Any], *, iterations: int = 1) -> GeometryOpResult: ...

    @abstractmethod
    def create(self, geometry_type: str, coordinates: Any) -> GeometryOpResult: ...

    @abstractmethod
    def describe(self, fc: Dict[str, Any], *, max_vertices: int = 10000) -> GeometryOpResult: ...
