"""Shapely-backed local geometry engine (slice 033, Lane C).

THE ONLY module in this package (and in ``geopack_sdk_mcp/geometry``) allowed to
import ``shapely``/``pyproj``/``geopandas`` — the swap-enforcement test reads
``geometry/**.py`` and fails on any other importer.

Contract (mirrors FE slice-014): GeoJSON dicts in, GeoJSON dicts out; every op
returns provenance. Metric ops project WGS84 input to a local UTM (or an explicit
``wkid``), run on metres, then project back to 4326 with the ``crs`` member
embedded. ``shapely`` has no geodesic buffer, so ``method='geodesic'`` is an
honest ``GEOMETRY_UNSUPPORTED_OP`` in v1.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Sequence

import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import nearest_points, transform as shapely_transform, unary_union

from . import helpers
from .crs import DISTANCE_UNITS, pick_local_utm_wkid, resolve_distance_units
from .engine import (
    ALL_OPS,
    OVERLAY_MODES,
    GeometryOpProvenance,
    GeometryOpResult,
    GeometryOpsEngine,
)
from .errors import (
    INVALID_ARGS,
    GeometryOpError,
    empty_result,
    engine_failed,
)

_WGS84 = 4326
#: Number of shapely points per quarter-circle for a requested total segment count.
_MAX_SEGMENTS = 256
_MIN_SEGMENTS = 8


def _geojson_geom(geom: Any) -> Dict[str, Any]:
    """A plain-JSON GeoJSON geometry (tuples normalised to lists)."""
    return json.loads(json.dumps(mapping(geom)))


def _iter_shapes(node: Any) -> Iterable[Any]:
    """Yield individual shapely geometries from a GeoJSON-ish node."""
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    if node_type == "FeatureCollection":
        for feature in node.get("features") or []:
            yield from _iter_shapes(feature)
        return
    if node_type == "Feature":
        if node.get("geometry"):
            yield shape(node["geometry"])
        return
    if node_type == "GeometryCollection":
        for geom in node.get("geometries") or []:
            yield from _iter_shapes(geom)
        return
    if node_type:
        yield shape(node)


def _to_shape(node: Any) -> Any:
    geoms = [g for g in _iter_shapes(node) if g is not None and not g.is_empty]
    if not geoms:
        return None
    if len(geoms) == 1:
        return geoms[0]
    return unary_union(geoms)


def _collection(geom: Any, *, crs: Optional[int] = None) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    if geom is not None and not geom.is_empty:
        features.append(
            {"type": "Feature", "properties": {}, "geometry": _geojson_geom(geom)}
        )
    payload: Dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs:
        payload["crs"] = {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{crs}"},
        }
    return payload


def _require_nonempty(geom: Any, op: str) -> Any:
    if geom is None or geom.is_empty:
        raise empty_result(op)
    return geom


def _transformer(src: int, dst: int) -> Transformer:
    return Transformer.from_crs(f"EPSG:{src}", f"EPSG:{dst}", always_xy=True)


def _project(geom: Any, src: int, dst: int) -> Any:
    if src == dst or geom is None or geom.is_empty:
        return geom
    return shapely_transform(_transformer(src, dst).transform, geom)


class ShapelyGeometryEngine(GeometryOpsEngine):
    id = "shapely"
    capabilities = ALL_OPS

    # --- internals ---------------------------------------------------------

    def _op_crs(self, nodes: Sequence[Any], wkid: Optional[int]) -> int:
        if wkid is not None and int(wkid) != _WGS84:
            return int(wkid)
        picked = None
        for node in nodes:
            picked = pick_local_utm_wkid(node)
            if picked:
                break
        if picked is None:
            raise GeometryOpError(
                INVALID_ARGS,
                "A projected CRS could not be derived from the input (empty geometry "
                "or |lat| > 84).",
                key="wkid",
                hint="Pass an explicit projected wkid (e.g. a UTM code) or use method='geodesic'.",
                invalid_args=["wkid"],
            )
        return int(picked)

    def _to_op(self, node: Any, op_wkid: int) -> Any:
        return _project(_to_shape(node), _WGS84, op_wkid)

    def _from_op(self, geom: Any, op_wkid: int) -> Dict[str, Any]:
        back = _project(geom, op_wkid, _WGS84)
        return _collection(back, crs=_WGS84)

    def _planar_provenance(self, op_wkid: int, units: Optional[str] = None) -> GeometryOpProvenance:
        return GeometryOpProvenance(
            engine=self.id, method_used="planar", crs_used=op_wkid, units_used=units
        )

    def _structural(self) -> GeometryOpProvenance:
        return GeometryOpProvenance(
            engine=self.id, method_used="none", crs_used=_WGS84
        )

    # --- buffer ------------------------------------------------------------

    def buffer(self, fc, *, distance, units="m", method="planar", wkid=None,
               segments=64, dissolve=True) -> GeometryOpResult:
        if not isinstance(distance, (int, float)) or distance != distance or distance <= 0:
            raise GeometryOpError(
                INVALID_ARGS,
                f"buffer distance must be a positive finite number (got {distance!r}).",
                key="distance",
                invalid_args=["distance"],
            )
        if method not in ("planar", "geodesic"):
            raise GeometryOpError(
                INVALID_ARGS,
                f"unknown buffer method {method!r}.",
                key="method",
                hint="Use 'planar' (geodesic is not available in v1).",
                invalid_args=["method"],
            )
        if method == "geodesic":
            raise GeometryOpError(
                "GEOMETRY_UNSUPPORTED_OP",
                "geodesic buffer is not available in v1 (the local engine is planar).",
                key="method",
                hint="Use method='planar'; the op projects to a local UTM automatically.",
                invalid_args=["method"],
                engine=self.id,
            )
        factor = resolve_distance_units(units)
        op_wkid = self._op_crs([fc], wkid)
        geom = _require_nonempty(self._to_op(fc, op_wkid), "buffer")
        seg = int(segments)
        if not _MIN_SEGMENTS <= seg <= _MAX_SEGMENTS:
            raise GeometryOpError(
                INVALID_ARGS,
                f"segments must be between {_MIN_SEGMENTS} and {_MAX_SEGMENTS} (got {seg}).",
                key="segments",
                invalid_args=["segments"],
            )
        quad_segs = max(1, round(seg / 4.0))
        buffered = geom.buffer(distance * factor, quad_segs=quad_segs)
        if dissolve:
            buffered = unary_union(buffered)
        buffered = _require_nonempty(buffered, "buffer")
        return GeometryOpResult(
            geojson=self._from_op(buffered, op_wkid),
            provenance=self._planar_provenance(op_wkid, units),
        )

    # --- overlay -----------------------------------------------------------

    def overlay(self, a, b, op, *, wkid=None) -> GeometryOpResult:
        if op not in OVERLAY_MODES:
            raise GeometryOpError(
                INVALID_ARGS,
                f"unknown overlay op {op!r}.",
                key="overlay_op",
                hint="Use one of: " + ", ".join(sorted(OVERLAY_MODES)) + ".",
                invalid_args=["overlay_op"],
            )
        normalized = "intersection" if op == "clip" else op
        if normalized == "union" and b is None:
            op_wkid = self._op_crs([a], wkid)
            geom_a = _require_nonempty(self._to_op(a, op_wkid), "overlay")
            result = _require_nonempty(unary_union(geom_a), "overlay")
            return GeometryOpResult(
                self._from_op(result, op_wkid), self._planar_provenance(op_wkid)
            )

        if b is None:
            raise GeometryOpError(
                INVALID_ARGS,
                f"overlay op '{op}' requires a second input ('b').",
                key="b",
                invalid_args=["b"],
            )
        op_wkid = self._op_crs([a, b], wkid)
        geom_a = _require_nonempty(self._to_op(a, op_wkid), "overlay")
        geom_b = _require_nonempty(self._to_op(b, op_wkid), "overlay")
        try:
            if normalized == "union":
                result = unary_union([geom_a, geom_b])
            elif normalized == "intersection":
                result = geom_a.intersection(geom_b)
            elif normalized == "difference":
                result = geom_a.difference(geom_b)
            else:  # xor
                result = geom_a.symmetric_difference(geom_b)
        except Exception as exc:  # noqa: BLE001 - surface the engine message verbatim
            raise engine_failed("overlay", str(exc)) from exc
        result = _require_nonempty(result, "overlay")
        return GeometryOpResult(
            self._from_op(result, op_wkid), self._planar_provenance(op_wkid)
        )

    # --- hull / envelope ---------------------------------------------------

    def convex_hull(self, fc, *, merge=True) -> GeometryOpResult:
        geoms = [g for g in _iter_shapes(fc) if g is not None and not g.is_empty]
        if not geoms:
            raise empty_result("convex_hull")
        if merge:
            hull = _require_nonempty(unary_union(geoms).convex_hull, "convex_hull")
            return GeometryOpResult(_collection(hull, crs=_WGS84), self._structural())
        features = [
            {
                "type": "Feature",
                "properties": {},
                "geometry": _geojson_geom(g.convex_hull),
            }
            for g in geoms
        ]
        return GeometryOpResult(
            {"type": "FeatureCollection", "features": features}, self._structural()
        )

    def envelope(self, fc) -> GeometryOpResult:
        geom = _require_nonempty(_to_shape(fc), "envelope")
        return GeometryOpResult(_collection(geom.envelope, crs=_WGS84), self._structural())

    # --- dissolve ----------------------------------------------------------

    def dissolve(self, fc, group_by) -> GeometryOpResult:
        if not isinstance(group_by, list) or not group_by:
            raise GeometryOpError(
                INVALID_ARGS,
                "group_by must be a non-empty list of property keys.",
                key="group_by",
                invalid_args=["group_by"],
            )
        groups: Dict[tuple, List[Any]] = {}
        key_values: Dict[tuple, Dict[str, Any]] = {}
        for feature in (fc.get("features") or []) if isinstance(fc, dict) else []:
            if not isinstance(feature, dict) or not feature.get("geometry"):
                continue
            props = feature.get("properties") or {}
            key = tuple(props.get(name) for name in group_by)
            groups.setdefault(key, []).append(shape(feature["geometry"]))
            key_values.setdefault(key, {name: props.get(name) for name in group_by})
        if not groups:
            raise empty_result("dissolve")

        features: List[Dict[str, Any]] = []
        for key, geoms in groups.items():
            if len(geoms) == 1:
                merged = geoms[0]
            else:
                try:
                    merged = unary_union(geoms)
                except Exception as exc:  # noqa: BLE001 - fail loud (§4.11 parity)
                    raise engine_failed("dissolve", str(exc)) from exc
            merged = _require_nonempty(merged, "dissolve")
            features.append(
                {
                    "type": "Feature",
                    "properties": {"role": "dissolve_group", **key_values[key]},
                    "geometry": _geojson_geom(merged),
                }
            )
        return GeometryOpResult(
            {"type": "FeatureCollection", "features": features}, self._structural()
        )

    # --- simplify ----------------------------------------------------------

    def simplify(self, fc, *, tolerance, wkid=None) -> GeometryOpResult:
        if not isinstance(tolerance, (int, float)) or tolerance <= 0:
            raise GeometryOpError(
                INVALID_ARGS,
                f"tolerance must be a positive number of metres (got {tolerance!r}).",
                key="tolerance",
                invalid_args=["tolerance"],
            )
        op_wkid = self._op_crs([fc], wkid)
        geom = _require_nonempty(self._to_op(fc, op_wkid), "simplify")
        simplified = _require_nonempty(geom.simplify(tolerance), "simplify")
        return GeometryOpResult(
            self._from_op(simplified, op_wkid), self._planar_provenance(op_wkid, "m")
        )

    # --- validate / fix ----------------------------------------------------

    def _report_for_geom(self, geom: Any) -> Dict[str, Any]:
        geom_type = geom.geom_type
        simple = bool(shapely.is_simple(geom))
        valid = bool(shapely.is_valid(geom))
        verdict = valid if geom_type not in ("LineString", "MultiLineString") else simple
        return {
            "valid": bool(verdict),
            "isValid": valid,
            "isSimple": simple,
            "geometryType": geom_type,
            "reason": None if valid else shapely.is_valid_reason(geom),
        }

    def validate(self, geojson) -> GeometryOpResult:
        geom = _to_shape(geojson)
        if geom is None:
            raise empty_result("validate")
        report = self._report_for_geom(geom)
        report["verdict"] = "valid" if report["valid"] else "invalid"
        return GeometryOpResult(report, self._structural())

    def fix(self, geojson) -> GeometryOpResult:
        geom = _to_shape(geojson)
        if geom is None:
            raise empty_result("fix")
        try:
            fixed = shapely.make_valid(geom)
        except Exception as exc:  # noqa: BLE001
            raise engine_failed("fix", str(exc)) from exc
        fixed = _require_nonempty(fixed, "fix")
        payload = _collection(fixed, crs=_WGS84)
        payload["fixed"] = self._report_for_geom(fixed)
        return GeometryOpResult(payload, self._structural())

    # --- convert / create --------------------------------------------------

    def convert(self, geojson, *, fmt="wkt") -> GeometryOpResult:
        if fmt not in ("wkt", "geojson"):
            raise GeometryOpError(
                INVALID_ARGS,
                f"unknown format {fmt!r}.",
                key="format",
                hint="Use 'geojson' or 'wkt'.",
                invalid_args=["format"],
            )
        if isinstance(geojson, dict) and geojson.get("wkt"):
            try:
                geom = shapely.from_wkt(geojson["wkt"])
            except Exception as exc:  # noqa: BLE001
                raise GeometryOpError(
                    INVALID_ARGS, f"invalid WKT: {exc}", key="text", invalid_args=["text"]
                ) from exc
        else:
            geom = _to_shape(geojson)
        if geom is None:
            raise empty_result("convert")
        mapped = _geojson_geom(geom)
        wkt = shapely.to_wkt(geom, rounding_precision=-1)
        result = {"format": fmt, "wkt": wkt, "geojson": mapped}
        if fmt == "wkt":
            result["text"] = wkt
        else:
            result["text"] = json.dumps(mapped)
        return GeometryOpResult(result, self._structural())

    def create(self, geometry_type, coordinates) -> GeometryOpResult:
        try:
            geom = shape({"type": geometry_type, "coordinates": coordinates})
        except Exception as exc:  # noqa: BLE001
            raise GeometryOpError(
                INVALID_ARGS,
                f"cannot build {geometry_type}: {exc}",
                key="coordinates",
                invalid_args=["coordinates"],
            ) from exc
        geom = _require_nonempty(geom, "create")
        return GeometryOpResult(_collection(geom, crs=_WGS84), self._structural())

    # --- project -----------------------------------------------------------

    def project(self, fc, *, wkid, output_wkid=None) -> GeometryOpResult:
        target = int(wkid)
        geom = _require_nonempty(_to_shape(fc), "project")
        try:
            projected = _project(geom, _WGS84, target)
        except Exception as exc:  # noqa: BLE001
            raise engine_failed("project", str(exc)) from exc
        out = projected
        if output_wkid is not None and int(output_wkid) != target:
            out = _project(projected, target, int(output_wkid))
        crs_member = int(output_wkid) if output_wkid is not None else target
        return GeometryOpResult(
            _collection(out, crs=crs_member),
            GeometryOpProvenance(
                engine=self.id,
                method_used="planar",
                crs_used=crs_member,
            ),
        )

    # --- measure -----------------------------------------------------------

    def measure(self, fc, *, units=None, wkid=None) -> GeometryOpResult:
        if units is not None and units not in DISTANCE_UNITS:
            raise GeometryOpError(
                INVALID_ARGS,
                f"unknown unit {units!r}.",
                key="units",
                hint="Use one of: " + ", ".join(DISTANCE_UNITS) + ".",
                invalid_args=["units"],
            )
        op_wkid = self._op_crs([fc], wkid)
        geom = _require_nonempty(self._to_op(fc, op_wkid), "measure")
        area_sq_m = float(geom.area)
        length_m = float(geom.length)
        report: Dict[str, Any] = {
            "area": area_sq_m,
            "areaUnit": "sq_m",
            "length": length_m,
            "lengthUnit": "m",
            "geometryType": geom.geom_type,
        }
        if units:
            factor = DISTANCE_UNITS[units]
            area_factor = factor * factor
            report["area"] = area_sq_m / area_factor
            report["areaUnit"] = {
                "m": "sq_m",
                "km": "sq_km",
                "ft": "sq_ft",
                "mi": "sq_mi",
            }[units]
            report["length"] = length_m / factor
            report["lengthUnit"] = units
        return GeometryOpResult(
            report, self._planar_provenance(op_wkid, units or "m")
        )

    # --- distance / nearest / line_between ---------------------------------

    def _pair(self, a, b, wkid, op_name):
        op_wkid = self._op_crs([a, b], wkid)
        geom_a = _require_nonempty(self._to_op(a, op_wkid), op_name)
        geom_b = _require_nonempty(self._to_op(b, op_wkid), op_name)
        return op_wkid, geom_a, geom_b

    def distance(self, a, b, *, wkid=None, units=None) -> GeometryOpResult:
        factor = resolve_distance_units(units) if units else 1.0
        unit_label = units or "m"
        op_wkid, geom_a, geom_b = self._pair(a, b, wkid, "distance")
        value = float(geom_a.distance(geom_b))
        pa, pb = nearest_points(geom_a, geom_b)
        back_a = _project(pa, op_wkid, _WGS84)
        back_b = _project(pb, op_wkid, _WGS84)
        return GeometryOpResult(
            {
                "distance": value / factor,
                "unit": unit_label,
                "nearestPoints": [[back_a.x, back_a.y], [back_b.x, back_b.y]],
            },
            self._planar_provenance(op_wkid, unit_label),
        )

    def nearest(self, a, b, *, wkid=None, units=None) -> GeometryOpResult:
        factor = resolve_distance_units(units) if units else 1.0
        unit_label = units or "m"
        op_wkid, geom_a, geom_b = self._pair(a, b, wkid, "nearest")
        pa, pb = nearest_points(geom_a, geom_b)
        value = float(geom_a.distance(geom_b))
        back_a = _project(pa, op_wkid, _WGS84)
        back_b = _project(pb, op_wkid, _WGS84)
        payload = _collection(back_a, crs=_WGS84)
        payload["features"].append(
            {"type": "Feature", "properties": {"role": "nearest_b"},
             "geometry": _geojson_geom(back_b)}
        )
        payload["distance"] = value / factor
        payload["distanceUnit"] = unit_label
        return GeometryOpResult(payload, self._planar_provenance(op_wkid, unit_label))

    def line_between(self, a, b, *, wkid=None) -> GeometryOpResult:
        op_wkid, geom_a, geom_b = self._pair(a, b, wkid, "line_between")
        pa, pb = nearest_points(geom_a, geom_b)
        from shapely.geometry import LineString

        line = LineString([(pa.x, pa.y), (pb.x, pb.y)])
        return GeometryOpResult(
            self._from_op(line, op_wkid), self._planar_provenance(op_wkid, "m")
        )

    # --- point on surface --------------------------------------------------

    def point_on_surface(self, fc) -> GeometryOpResult:
        geoms = [g for g in _iter_shapes(fc) if g is not None and not g.is_empty]
        if not geoms:
            raise empty_result("point_on_surface")
        anchors = [g.representative_point() for g in geoms]
        merged = anchors[0] if len(anchors) == 1 else unary_union(anchors)
        return GeometryOpResult(_collection(merged, crs=_WGS84), self._structural())

    # --- smooth / describe -------------------------------------------------

    def smooth(self, fc, *, iterations=1) -> GeometryOpResult:
        if not isinstance(iterations, int) or not 1 <= iterations <= 10:
            raise GeometryOpError(
                INVALID_ARGS,
                f"iterations must be an integer between 1 and 10 (got {iterations!r}).",
                key="iterations",
                invalid_args=["iterations"],
            )
        geom = _require_nonempty(_to_shape(fc), "smooth")
        try:
            smoothed = helpers.chaikin_smooth(_geojson_geom(geom), iterations)
        except ValueError as exc:
            raise GeometryOpError(
                INVALID_ARGS, str(exc), key="geojson", invalid_args=["geojson"]
            ) from exc
        return GeometryOpResult(_collection(shape(smoothed), crs=_WGS84), self._structural())

    def describe(self, fc, *, max_vertices=10000) -> GeometryOpResult:
        if not isinstance(max_vertices, int) or not 1 <= max_vertices <= 200000:
            raise GeometryOpError(
                INVALID_ARGS,
                f"max_vertices must be between 1 and 200000 (got {max_vertices!r}).",
                key="max_vertices",
                invalid_args=["max_vertices"],
            )
        return GeometryOpResult(
            helpers.describe_geojson(fc, max_vertices=max_vertices),
            self._structural(),
        )