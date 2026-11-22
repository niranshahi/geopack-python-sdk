"""Handler for ``geopack_sdk_geometry_op`` (slice 033, Lane C).

Pure local compute: resolves supplied geometry (GeoJSON or WKT text) and runs one
op through the selected engine. It NEVER calls the portal and never imports
shapely directly — only :mod:`geopack_sdk_mcp.geometry` (port + select).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..geometry import GeometryOpError, resolve_engine
from ..geometry.errors import INVALID_ARGS, unsupported_op

_GEOMETRY_TYPES = frozenset(
    {
        "Point",
        "LineString",
        "Polygon",
        "MultiPoint",
        "MultiLineString",
        "MultiPolygon",
        "GeometryCollection",
        "Feature",
        "FeatureCollection",
    }
)


def _resolve_geometry(engine: Any, geojson: Optional[Dict[str, Any]],
                      text: Optional[str], label: str) -> Dict[str, Any]:
    if isinstance(geojson, dict) and geojson:
        return geojson
    if isinstance(text, str) and text.strip():
        converted = engine.convert({"wkt": text}, fmt="geojson")
        return converted.geojson["geojson"]
    raise GeometryOpError(
        INVALID_ARGS,
        f"op requires the '{label}' geometry (GeoJSON object or WKT text).",
        key=label,
        hint=f"Pass '{label}' as a GeoJSON object or '{label}_text' as WKT.",
        invalid_args=[label],
    )


def _wrap(op: str, result: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"op": op, "provenance": result.provenance.to_dict()}
    payload.update(result.extra)
    body = result.geojson
    if isinstance(body, dict) and body.get("type") in _GEOMETRY_TYPES:
        payload["geojson"] = body
    elif isinstance(body, dict):
        payload.update(body)
    else:
        payload["result"] = body
    return payload


def geometry_op(
    op: str,
    *,
    geojson: Optional[Dict[str, Any]] = None,
    text: Optional[str] = None,
    b: Optional[Dict[str, Any]] = None,
    b_text: Optional[str] = None,
    overlay_op: Optional[str] = None,
    distance: Optional[float] = None,
    units: Optional[str] = None,
    method: Optional[str] = None,
    wkid: Optional[int] = None,
    segments: Optional[int] = None,
    dissolve: Optional[bool] = None,
    group_by: Optional[List[str]] = None,
    tolerance: Optional[float] = None,
    iterations: Optional[int] = None,
    fmt: Optional[str] = None,
    output_wkid: Optional[int] = None,
    geometry_type: Optional[str] = None,
    coordinates: Optional[Any] = None,
    max_vertices: Optional[int] = None,
    merge: Optional[bool] = None,
) -> Dict[str, Any]:
    engine = resolve_engine()
    if not isinstance(op, str) or not op.strip():
        raise GeometryOpError(INVALID_ARGS, "op is required.", key="op", invalid_args=["op"])
    op = op.strip().lower()
    if not engine.supports(op):
        raise unsupported_op(op, engine=engine.id, legal=engine.capabilities)

    if op == "create":
        if not geometry_type:
            raise GeometryOpError(
                INVALID_ARGS, "create requires geometry_type.", key="geometry_type",
                invalid_args=["geometry_type"],
            )
        if coordinates is None:
            raise GeometryOpError(
                INVALID_ARGS, "create requires coordinates.", key="coordinates",
                invalid_args=["coordinates"],
            )
        return _wrap(op, engine.create(geometry_type, coordinates))

    if op == "convert":
        if not (isinstance(geojson, dict) and geojson) and not (
            isinstance(text, str) and text.strip()
        ):
            raise GeometryOpError(
                INVALID_ARGS,
                "convert requires geojson or WKT text.",
                key="geojson",
                hint="Pass a GeoJSON object, or 'text' holding WKT.",
                invalid_args=["geojson", "text"],
            )
        payload = geojson if isinstance(geojson, dict) and geojson else {"wkt": text}
        target = fmt or ("wkt" if geojson else "geojson")
        return _wrap(op, engine.convert(payload, fmt=target))

    if op == "describe":
        node = _resolve_geometry(engine, geojson, text, "geojson")
        return _wrap(
            op,
            engine.describe(node, max_vertices=max_vertices or 10000),
        )

    if op == "project":
        target = wkid if wkid is not None else output_wkid
        if target is None:
            raise GeometryOpError(
                INVALID_ARGS, "project requires wkid.", key="wkid", invalid_args=["wkid"]
            )
        node = _resolve_geometry(engine, geojson, text, "geojson")
        final = output_wkid if (wkid is not None and output_wkid is not None) else None
        return _wrap(op, engine.project(node, wkid=target, output_wkid=final))

    node = _resolve_geometry(engine, geojson, text, "geojson")

    if op == "buffer":
        if distance is None:
            raise GeometryOpError(
                INVALID_ARGS, "buffer requires distance.", key="distance",
                invalid_args=["distance"],
            )
        return _wrap(
            op,
            engine.buffer(
                node,
                distance=distance,
                units=units or "m",
                method=method or "planar",
                wkid=wkid,
                segments=segments or 64,
                dissolve=True if dissolve is None else bool(dissolve),
            ),
        )

    if op == "overlay":
        other = None
        if b is not None or (b_text and b_text.strip()):
            other = _resolve_geometry(engine, b, b_text, "b")
        return _wrap(op, engine.overlay(node, other, overlay_op or "union", wkid=wkid))

    if op == "convex_hull":
        return _wrap(op, engine.convex_hull(node, merge=True if merge is None else bool(merge)))

    if op == "envelope":
        return _wrap(op, engine.envelope(node))

    if op == "dissolve":
        if not group_by:
            raise GeometryOpError(
                INVALID_ARGS, "dissolve requires group_by.", key="group_by",
                invalid_args=["group_by"],
            )
        return _wrap(op, engine.dissolve(node, group_by))

    if op == "simplify":
        return _wrap(op, engine.simplify(node, tolerance=1.0 if tolerance is None else tolerance, wkid=wkid))

    if op in ("validate", "fix"):
        return _wrap(op, getattr(engine, op)(node))

    if op == "measure":
        return _wrap(op, engine.measure(node, units=units, wkid=wkid))

    if op == "point_on_surface":
        return _wrap(op, engine.point_on_surface(node))

    if op == "smooth":
        return _wrap(op, engine.smooth(node, iterations=1 if iterations is None else iterations))

    if op in ("distance", "nearest", "line_between"):
        other = _resolve_geometry(engine, b, b_text, "b")
        if op == "line_between":
            return _wrap(op, engine.line_between(node, other, wkid=wkid))
        return _wrap(op, getattr(engine, op)(node, other, wkid=wkid, units=units))

    raise unsupported_op(op, engine=engine.id, legal=engine.capabilities)