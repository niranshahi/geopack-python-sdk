"""CRS selection for the local geometry lane (slice-014 §6 parity, pure Python).

No ``shapely``/``pyproj`` import here — the swap-enforcement test forbids it.
The picker is a straight port of the FE ``pickLocalUtmWkid`` intent: derive a
local UTM zone from the input centroid (326xx north / 327xx south) so metric
ops (buffer / distance / simplify) run on metres, not degrees.

Deliberately NOT inherited from the legacy picker (FE slice-014 §6.2): the
legacy had **no polar guard**. Here |lat| > 84 yields ``None`` so the caller
asks for an explicit ``wkid`` instead of silently minting a wrong zone.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

#: Beyond this latitude a UTM zone is not meaningful (and 327xx/326xx break).
_MAX_LAT = 84.0


def iter_positions(node: Any) -> Iterator[Tuple[float, float]]:
    """Yield every ``(x, y)`` position found anywhere in a GeoJSON-ish tree."""
    if node is None:
        return
    if isinstance(node, dict):
        node_type = node.get("type")
        if node_type == "FeatureCollection":
            for feature in node.get("features") or []:
                yield from iter_positions(feature)
            return
        if node_type == "Feature":
            yield from iter_positions(node.get("geometry"))
            return
        if node_type == "GeometryCollection":
            for geom in node.get("geometries") or []:
                yield from iter_positions(geom)
            return
        if "coordinates" in node:
            yield from _iter_coords(node.get("coordinates"))
            return
        if "geometry" in node:
            yield from iter_positions(node.get("geometry"))
            return
    # A bare coordinate tree (list of positions / nested lists).
    if isinstance(node, (list, tuple)):
        yield from _iter_coords(node)


def _iter_coords(coords: Any) -> Iterator[Tuple[float, float]]:
    if not isinstance(coords, (list, tuple)) or not coords:
        return
    first = coords[0]
    if isinstance(first, (int, float)):
        if len(coords) >= 2 and isinstance(coords[1], (int, float)):
            yield float(coords[0]), float(coords[1])
        return
    for item in coords:
        yield from _iter_coords(item)


def bbox_of(node: Any) -> Optional[List[float]]:
    """``[minx, miny, maxx, maxy]`` over all positions, or ``None`` if empty."""
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    found = False
    for x, y in iter_positions(node):
        found = True
        minx = min(minx, x)
        miny = min(miny, y)
        maxx = max(maxx, x)
        maxy = max(maxy, y)
    if not found:
        return None
    return [minx, miny, maxx, maxy]


def polygon_from_bbox(bbox: List[float]) -> Dict[str, Any]:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [minx, miny],
                [maxx, miny],
                [maxx, maxy],
                [minx, maxy],
                [minx, miny],
            ]
        ],
    }


def pick_local_utm_wkid(node: Any) -> Optional[int]:
    """Local UTM EPSG code for the centroid of ``node`` (or ``None``).

    ``None`` means "cannot derive": empty geometry, or |lat| beyond the 84°
    cap. The caller then requires an explicit ``wkid`` (never a silent
    EPSG:3857 default — FE slice-014 §6.7).
    """
    box = bbox_of(node)
    if box is None:
        return None
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    if abs(cy) > _MAX_LAT:
        return None
    zone = int((cx + 180.0) // 6.0) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if cy >= 0 else 32700) + zone


#: Distance units the lane accepts, mapped to their metre factor.
DISTANCE_UNITS: Dict[str, float] = {
    "m": 1.0,
    "km": 1000.0,
    "ft": 0.3048,
    "mi": 1609.344,
}

#: Area units the lane echoes (for measure), mapped to square-metre factors.
AREA_UNITS: Dict[str, float] = {
    "sq_m": 1.0,
    "sq_km": 1_000_000.0,
    "sq_ft": 0.09290304,
    "sq_mi": 2_589_988.110336,
    "ha": 10_000.0,
}


def resolve_distance_units(units: str) -> float:
    """Factor to metres; an unknown/wrong-family unit is REJECTED, never defaulted."""
    from .errors import INVALID_ARGS, GeometryOpError

    if not isinstance(units, str) or units not in DISTANCE_UNITS:
        raise GeometryOpError(
            INVALID_ARGS,
            f"unknown distance unit {units!r}.",
            key="units",
            hint="Use one of: " + ", ".join(DISTANCE_UNITS) + ".",
            invalid_args=["units"],
        )
    return DISTANCE_UNITS[units]
