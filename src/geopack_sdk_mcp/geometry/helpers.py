"""Pure-Python geometry helpers (no shapely/pyproj) for the local lane (slice 033)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .crs import bbox_of, iter_positions


def _leaf_types(node: Any, acc: set) -> None:
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    if node_type == "FeatureCollection":
        for feature in node.get("features") or []:
            _leaf_types(feature, acc)
        return
    if node_type == "Feature":
        _leaf_types(node.get("geometry"), acc)
        return
    if node_type == "GeometryCollection":
        for geom in node.get("geometries") or []:
            _leaf_types(geom, acc)
        return
    if node_type:
        acc.add(node_type)


def count_vertices(node: Any, cap: int) -> Tuple[int, bool]:
    """Vertex count with an early stop at ``cap``; ``(count, truncated)``."""
    total = 0
    for _ in iter_positions(node):
        total += 1
        if total > cap:
            return cap, True
    return total, False


def describe_geojson(node: Any, *, max_vertices: int = 10000) -> Dict[str, Any]:
    """A pure report: leaf types, feature count, bbox and a capped vertex count."""
    types: set = set()
    _leaf_types(node, types)

    feature_count: Optional[int] = None
    if isinstance(node, dict) and node.get("type") == "FeatureCollection":
        feature_count = len(node.get("features") or [])

    count, truncated = count_vertices(node, max_vertices)
    report: Dict[str, Any] = {
        "types": sorted(types),
        "bbox": bbox_of(node),
        "vertexCount": count,
    }
    if feature_count is not None:
        report["featureCount"] = feature_count
    if truncated:
        report["vertexCountTruncated"] = True
        report["vertexCap"] = max_vertices
    return report


def _chaikin_ring(points: List[List[float]]) -> List[List[float]]:
    """One Chaikin pass on a closed ring (first == last)."""
    closed = points if points and points[0] == points[-1] else points + [points[0]]
    out: List[List[float]] = [closed[0]]
    for i in range(len(closed) - 1):
        p0, p1 = closed[i], closed[i + 1]
        out.append([0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1]])
        out.append([0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1]])
    out.append(closed[-1])
    return out


def _chaikin_line(points: List[List[float]]) -> List[List[float]]:
    """One Chaikin pass on an open line (endpoints pinned)."""
    if len(points) < 3:
        return [list(p) for p in points]
    out: List[List[float]] = [list(points[0])]
    for i in range(len(points) - 1):
        p0, p1 = points[i], points[i + 1]
        out.append([0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1]])
        out.append([0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1]])
    out.append(list(points[-1]))
    return out


def _smooth_ring(points: List[List[float]]) -> List[List[float]]:
    return _chaikin_ring(points)


def chaikin_smooth(geometry: Dict[str, Any], iterations: int) -> Dict[str, Any]:
    """Apply ``iterations`` Chaikin passes to a single geometry dict."""
    geom_type = geometry.get("type")
    if geom_type in ("Point", "MultiPoint"):
        raise ValueError("smooth does not apply to Point/MultiPoint geometry")
    coords = geometry.get("coordinates")
    for _ in range(max(1, iterations)):
        if geom_type == "Polygon":
            coords = [_smooth_ring(ring) for ring in coords]
        elif geom_type == "MultiPolygon":
            coords = [[_smooth_ring(ring) for ring in poly] for poly in coords]
        elif geom_type == "LineString":
            coords = _chaikin_line(coords)
        elif geom_type == "MultiLineString":
            coords = [_chaikin_line(line) for line in coords]
        else:
            break
    return {"type": geom_type, "coordinates": coords}
