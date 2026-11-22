"""Slice 033 Lane C — local geometry engine contract + golden cases."""

from __future__ import annotations

import pathlib
import unittest
from typing import Any, Dict

import geopack_sdk_mcp.geometry as geometry_pkg
from geopack_sdk_mcp.geometry import (
    GeometryOpError,
    GeometryOpProvenance,
    GeometryOpResult,
    GeometryOpsEngine,
    set_engine_for_tests,
)
from geopack_sdk_mcp.geometry.crs import pick_local_utm_wkid
from geopack_sdk_mcp.geometry.shapely_engine import ShapelyGeometryEngine

SQUARE_A = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
}
SQUARE_B = {
    "type": "Polygon",
    "coordinates": [[[0.05, 0.05], [0.15, 0.05], [0.15, 0.15], [0.05, 0.15], [0.05, 0.05]]],
}
BOWTIE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
}


def fc(*geometries: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": geom} for geom in geometries
        ],
    }


class _FakeEngine(GeometryOpsEngine):
    id = "fake"
    capabilities = frozenset({"buffer"})

    def buffer(self, fc, *, distance, units="m", method="planar", wkid=None,
               segments=64, dissolve=True):
        return GeometryOpResult(
            {"type": "FeatureCollection", "features": []},
            GeometryOpProvenance("fake", "planar", 32639, units),
        )

    def _no(self, *args, **kwargs):
        raise NotImplementedError

    overlay = convex_hull = envelope = dissolve = simplify = validate = fix = _no
    convert = project = measure = distance = nearest = point_on_surface = _no
    line_between = smooth = create = describe = _no


class PortContractTest(unittest.TestCase):
    def test_a_result_always_carries_provenance(self):
        engine = _FakeEngine()
        result = engine.buffer(fc(SQUARE_A), distance=10, units="m")

        self.assertIsInstance(result.provenance, GeometryOpProvenance)
        prov = result.provenance.to_dict()
        self.assertEqual(prov["engine"], "fake")
        self.assertEqual(prov["methodUsed"], "planar")
        self.assertEqual(prov["crsUsed"], 32639)
        self.assertEqual(prov["unitsUsed"], "m")

    def test_capability_rejection_names_the_legal_set(self):
        set_engine_for_tests(_FakeEngine())
        try:
            from geopack_sdk_mcp.tool_handlers.geometry import geometry_op

            with self.assertRaises(GeometryOpError) as ctx:
                geometry_op("envelope", geojson=SQUARE_A)
        finally:
            set_engine_for_tests(None)
        self.assertEqual(ctx.exception.code, "GEOMETRY_UNSUPPORTED_OP")
        self.assertIn("buffer", ctx.exception.extra["legalOps"])


class CrsPickerTest(unittest.TestCase):
    def test_tehran_is_zone_39_north(self):
        self.assertEqual(pick_local_utm_wkid({"type": "Point", "coordinates": [51.4, 35.7]}), 32639)

    def test_southern_hemisphere_is_327xx(self):
        self.assertEqual(pick_local_utm_wkid({"type": "Point", "coordinates": [-58.4, -34.6]}), 32721)

    def test_beyond_the_polar_cap_is_refused(self):
        self.assertIsNone(pick_local_utm_wkid({"type": "Point", "coordinates": [10, 89]}))

    def test_empty_geometry_yields_none(self):
        self.assertIsNone(pick_local_utm_wkid(fc()))


class ShapelyGoldenTest(unittest.TestCase):
    def setUp(self):
        self.engine = ShapelyGeometryEngine()

    def test_buffer_is_metric_a_local_utm(self):
        result = self.engine.buffer(
            {"type": "Point", "coordinates": [51.4, 35.7]},
            distance=100, units="m", method="planar", wkid=32639,
        )

        self.assertEqual(result.provenance.engine, "shapely")
        self.assertEqual(result.provenance.crs_used, 32639)
        self.assertEqual(len(result.geojson["features"]), 1)
        area = self.engine.measure(result.geojson, wkid=32639).geojson["area"]
        self.assertAlmostEqual(area, 3.14159 * 100 * 100, delta=0.08 * 3.14159 * 10000)

    def test_overlay_intersection_area_is_a_quarter(self):
        result = self.engine.overlay(fc(SQUARE_A), fc(SQUARE_B), "intersection", wkid=32631)
        inter_area = self.engine.measure(result.geojson, wkid=32631).geojson["area"]
        a_area = self.engine.measure(fc(SQUARE_A), wkid=32631).geojson["area"]

        self.assertGreater(inter_area, 0)
        self.assertAlmostEqual(inter_area / a_area, 0.25, delta=0.05)

    def test_disjoint_intersection_is_a_coded_error(self):
        far = {
            "type": "Polygon",
            "coordinates": [[[10, 10], [10.1, 10], [10.1, 10.1], [10, 10.1], [10, 10]]],
        }
        with self.assertRaises(GeometryOpError) as ctx:
            self.engine.overlay(fc(SQUARE_A), fc(far), "intersection", wkid=32631)
        self.assertEqual(ctx.exception.code, "GEOMETRY_EMPTY_RESULT")

    def test_union_without_b_merges_all_parts(self):
        result = self.engine.overlay(
            fc(SQUARE_A, SQUARE_B), None, "union", wkid=32631
        )
        geom = result.geojson["features"][0]["geometry"]
        self.assertIn(geom["type"], ("Polygon", "MultiPolygon"))

    def test_clip_is_an_alias_of_intersection(self):
        inter = self.engine.overlay(fc(SQUARE_A), fc(SQUARE_B), "intersection", wkid=32631)
        clip = self.engine.overlay(fc(SQUARE_A), fc(SQUARE_B), "clip", wkid=32631)
        self.assertAlmostEqual(
            self.engine.measure(inter.geojson, wkid=32631).geojson["area"],
            self.engine.measure(clip.geojson, wkid=32631).geojson["area"],
            places=3,
        )

    def test_convex_hull_drops_an_interior_point(self):
        tri = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [2, 0], [0, 2], [0, 0]]],
        }
        result = self.engine.convex_hull(fc(tri, {"type": "Point", "coordinates": [0.2, 0.2]}))
        ring = result.geojson["features"][0]["geometry"]["coordinates"][0]
        self.assertNotIn([0.2, 0.2], ring)

    def test_envelope_is_the_bbox(self):
        result = self.engine.envelope(fc(SQUARE_A, SQUARE_B))
        ring = result.geojson["features"][0]["geometry"]["coordinates"][0]
        xs = [pt[0] for pt in ring]
        ys = [pt[1] for pt in ring]
        self.assertEqual((min(xs), min(ys), max(xs), max(ys)), (0.0, 0.0, 0.15, 0.15))

    def test_validate_and_fix_a_bowtie(self):
        report = self.engine.validate(BOWTIE).geojson
        self.assertFalse(report["valid"])
        fixed = self.engine.fix(BOWTIE).geojson
        self.assertEqual(len(fixed["features"]), 1)
        self.assertTrue(fixed["fixed"]["valid"])

    def test_convert_round_trips_wkt_and_geojson(self):
        to_wkt = self.engine.convert({"type": "Point", "coordinates": [1, 2]}, fmt="wkt")
        self.assertIn("POINT", to_wkt.geojson["wkt"].upper())

        back = self.engine.convert({"wkt": to_wkt.geojson["wkt"]}, fmt="geojson")
        self.assertEqual(back.geojson["geojson"]["type"], "Point")

    def test_describe_reports_counts_and_bbox(self):
        report = self.engine.describe(fc(SQUARE_A, SQUARE_B)).geojson
        self.assertEqual(report["featureCount"], 2)
        self.assertEqual(report["bbox"], [0.0, 0.0, 0.15, 0.15])

    def test_distance_and_nearest_points(self):
        result = self.engine.distance(
            {"type": "Point", "coordinates": [0.05, 0.05]},
            {"type": "Point", "coordinates": [0.06, 0.05]},
            wkid=32631,
        )
        self.assertGreater(result.geojson["distance"], 0)
        self.assertEqual(len(result.geojson["nearestPoints"]), 2)

    def test_distance_echoes_the_requested_unit(self):
        a = {"type": "Point", "coordinates": [0.05, 0.05]}
        b = {"type": "Point", "coordinates": [0.06, 0.05]}

        meters = self.engine.distance(a, b, wkid=32631).geojson
        kms = self.engine.distance(a, b, wkid=32631, units="km").geojson
        nearest_km = self.engine.nearest(a, b, wkid=32631, units="km").geojson

        self.assertEqual(meters["unit"], "m")
        self.assertEqual(kms["unit"], "km")
        self.assertAlmostEqual(kms["distance"] * 1000, meters["distance"], places=6)
        self.assertEqual(nearest_km["distanceUnit"], "km")
        self.assertAlmostEqual(nearest_km["distance"] * 1000, meters["distance"], places=6)

    def test_geodesic_buffer_is_honestly_unsupported(self):
        with self.assertRaises(GeometryOpError) as ctx:
            self.engine.buffer(
                {"type": "Point", "coordinates": [51.4, 35.7]},
                distance=100, units="m", method="geodesic", wkid=32639,
            )
        self.assertEqual(ctx.exception.code, "GEOMETRY_UNSUPPORTED_OP")


class HandlerArgAliasTest(unittest.TestCase):
    def test_project_accepts_output_wkid_as_the_target(self):
        from geopack_sdk_mcp.tool_handlers.geometry import geometry_op

        out = geometry_op(
            "project",
            geojson={"type": "Point", "coordinates": [51.389, 35.689]},
            output_wkid=32639,
        )

        self.assertIn("geojson", out)
        self.assertEqual(out["provenance"]["crsUsed"], 32639)

    def test_project_still_requires_a_target(self):
        from geopack_sdk_mcp.geometry.errors import GeometryOpError
        from geopack_sdk_mcp.tool_handlers.geometry import geometry_op

        with self.assertRaises(GeometryOpError):
            geometry_op(
                "project",
                geojson={"type": "Point", "coordinates": [51.389, 35.689]},
            )


class SwapEnforcementTest(unittest.TestCase):
    def test_no_module_outside_the_adapter_imports_shapely_or_pyproj(self):
        root = pathlib.Path(geometry_pkg.__file__).parent
        offenders = []
        for path in root.glob("*.py"):
            if path.name == "shapely_engine.py":
                continue
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in ("import shapely", "from shapely",
                                               "import pyproj", "from pyproj",
                                               "import geopandas", "from geopandas")):
                offenders.append(path.name)

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()