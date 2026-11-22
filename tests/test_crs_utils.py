"""Client-side CRS verification/reprojection (slice 033 robustness)."""

from __future__ import annotations

import unittest

from geopack_sdk_mcp.crs_utils import (
    honor_output_srid,
    looks_wgs84,
    parse_epsg,
    srid_from_dataset,
    WGS84,
)

PROJECTED_UTM40N = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Point", "coordinates": [500000.0, 4000000.0]},
        }
    ],
}

WGS84_FEATURES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Point", "coordinates": [51.389, 35.689]},
        }
    ],
}


class ParseEpsgTest(unittest.TestCase):
    def test_reads_every_shape_the_portal_uses(self):
        self.assertEqual(parse_epsg(4326), 4326)
        self.assertEqual(parse_epsg(32640.0), 32640)
        self.assertEqual(parse_epsg("EPSG:4326"), 4326)
        self.assertEqual(parse_epsg("epsg:32640"), 32640)
        self.assertEqual(parse_epsg("urn:ogc:def:crs:EPSG::4326"), 4326)
        self.assertEqual(parse_epsg("3857"), 3857)
        self.assertEqual(parse_epsg({"srid": 32640}), 32640)
        self.assertEqual(parse_epsg({"wkid": "4326"}), 4326)

    def test_unusable_values_are_none_never_a_guess(self):
        self.assertIsNone(parse_epsg(None))
        self.assertIsNone(parse_epsg(True))
        self.assertIsNone(parse_epsg({}))
        self.assertIsNone(parse_epsg(""))
        self.assertIsNone(parse_epsg("no digits here"))
        self.assertIsNone(parse_epsg(0))


class SridFromDatasetTest(unittest.TestCase):
    def test_reads_a_dict_spatial_reference(self):
        raw = {"details": {"spatialReference": {"srid": 32640}}}
        self.assertEqual(srid_from_dataset(raw), 32640)

    def test_reads_a_json_string_details_blob(self):
        raw = {"details": '{"spatialReference": {"srid": 32640}}'}
        self.assertEqual(srid_from_dataset(raw), 32640)

    def test_reads_a_top_level_srid_fallback(self):
        self.assertEqual(srid_from_dataset({"srid": 4326}), 4326)

    def test_an_empty_spatial_reference_declares_no_srid(self):
        # Dataset 2554 (Iran Lambert) reports an empty/`{}` spatial reference.
        self.assertIsNone(srid_from_dataset({"details": {"spatialReference": {}}}))


class LooksWgs84Test(unittest.TestCase):
    def test_projected_metres_are_decisively_not_wgs84(self):
        self.assertIs(looks_wgs84(PROJECTED_UTM40N), False)

    def test_lon_lat_is_wgs84(self):
        self.assertIs(looks_wgs84(WGS84_FEATURES), True)

    def test_no_features_is_unknown(self):
        self.assertIsNone(looks_wgs84({"type": "FeatureCollection", "features": []}))


class HonorOutputSridTest(unittest.TestCase):
    def test_a_honoured_wgs84_answer_is_trusted(self):
        outcome = honor_output_srid(WGS84_FEATURES, target_srid=4326)
        self.assertEqual(outcome.applied_srid, 4326)
        self.assertIsNone(outcome.note)
        self.assertFalse(outcome.reprojected)

    def test_an_unknown_answer_is_trusted(self):
        outcome = honor_output_srid(
            {"type": "FeatureCollection", "features": []}, target_srid=4326
        )
        self.assertEqual(outcome.applied_srid, 4326)
        self.assertFalse(outcome.reprojected)

    def test_a_non_wgs84_target_is_passed_through(self):
        outcome = honor_output_srid(PROJECTED_UTM40N, target_srid=3857)
        self.assertEqual(outcome.applied_srid, 3857)
        self.assertFalse(outcome.reprojected)

    def test_a_projected_answer_with_a_known_source_is_repaired(self):
        outcome = honor_output_srid(
            PROJECTED_UTM40N, target_srid=4326, source_srid=32640
        )
        self.assertTrue(outcome.reprojected)
        self.assertEqual(outcome.applied_srid, WGS84)
        self.assertIn("reprojected", outcome.note or "")
        x, y = outcome.feature_collection["features"][0]["geometry"]["coordinates"]
        self.assertLessEqual(abs(x), 180)
        self.assertLessEqual(abs(y), 90)
        # Matches pyproj directly (always_xy) rather than a lat/lon swap.
        from pyproj import Transformer

        expected = Transformer.from_crs(
            "EPSG:32640", "EPSG:4326", always_xy=True
        ).transform(500000.0, 4000000.0)
        self.assertAlmostEqual(x, expected[0], places=6)
        self.assertAlmostEqual(y, expected[1], places=6)

    def test_a_projected_answer_without_a_source_is_reported_not_fixed(self):
        outcome = honor_output_srid(PROJECTED_UTM40N, target_srid=4326)
        self.assertFalse(outcome.reprojected)
        self.assertIsNone(outcome.applied_srid)
        self.assertIn("could not be repaired", outcome.note or "")


if __name__ == "__main__":
    unittest.main()
