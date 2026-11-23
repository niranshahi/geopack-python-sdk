import json
import unittest

from geopack_sdk_mcp.sanitize.dataset_details import (
    normalize_details_level,
    trim_dataset_for_mcp,
    trim_details,
    trim_datasets_list_payload,
)


class TestMcpDatasetDetails(unittest.TestCase):
    def _sample_vector_details(self) -> dict:
        return {
            "type": "vector",
            "featureCount": 118,
            "extent": [1, 2, 3, 4],
            "fields": [{"name": "a"}, {"name": "b"}],
            "tilejson": {
                "name": "big",
                "tilestats": {
                    "layers": [
                        {
                            "attributes": [
                                {"attribute": "x", "values": list(range(200))},
                            ]
                        }
                    ]
                },
            },
        }

    def test_lite_drops_tilejson_and_fields(self):
        out = trim_details(self._sample_vector_details(), "lite")
        self.assertNotIn("tilejson", out)
        self.assertEqual(out["fieldsCount"], 2)
        self.assertNotIn("fields", out)

    def test_standard_includes_slim_fields(self):
        out = trim_details(self._sample_vector_details(), "standard")
        self.assertNotIn("tilejson", out)
        self.assertEqual(len(out["fields"]), 2)
        self.assertIn("fields", out)
        self.assertNotIn("tilejson", out)

    def test_full_profile_keeps_tilejson_strips_values(self):
        out = trim_details(self._sample_vector_details(), "full")
        self.assertIn("tilejson", out)
        attr = out["tilejson"]["tilestats"]["layers"][0]["attributes"][0]
        self.assertNotIn("values", attr)
        self.assertTrue(attr.get("valuesOmitted"))
        self.assertEqual(attr.get("valuesCount"), 200)

    def test_full_omits_display_renderer_blob(self):
        raw = {
            "type": "vector",
            "tilejson": {"name": "x", "tiles": ["/mvt"]},
            "display": {
                "esri": {
                    "renderer": {
                        "type": "uniqueValue",
                        "field1": "distr_id",
                        "uniqueValueGroups": [{"classes": [{"label": str(i)} for i in range(50)]}],
                    },
                    "labelingInfo": [{"labelExpression": "[name]"}],
                }
            },
        }
        out = trim_details(raw, "full")
        self.assertIn("display", out)
        self.assertTrue(out["display"].get("_omitted"))
        self.assertEqual(out["display"].get("rendererType"), "uniqueValue")
        self.assertEqual(out["display"].get("field1"), "distr_id")
        self.assertEqual(out["display"].get("classCount"), 50)
        self.assertEqual(out["display"].get("labelExpression"), "[name]")
        self.assertNotIn("uniqueValueGroups", out["display"])

    def test_list_payload_lite_drops_details_blob(self):
        """A LIST lite row is a card: no details blob (F4, live-QA 2026-11-21)."""
        huge = json.dumps(self._sample_vector_details())
        payload = {
            "datasets": [{"id": 1, "name": "x", "details": huge}],
            "totalCount": 1,
            "totalPages": 1,
            "currentPage": 1,
            "itemsPerPage": 10,
        }
        out = trim_datasets_list_payload(payload)
        row = out["datasets"][0]
        self.assertNotIn("details", row)
        self.assertTrue(row["detailsOmitted"])

    def test_symbology_is_attached_at_lite(self):
        details = {"display": {"esri": {"renderer": {"type": "uniqueValue", "field1": "LANDUSE"}}}}
        row = trim_dataset_for_mcp({"id": 5, "dataType": "vector", "details": details}, "lite")
        self.assertTrue(row["symbology"]["hasSavedStyle"])
        self.assertEqual(row["symbology"]["rendererType"], "uniqueValue")
        self.assertEqual(row["symbology"]["fields"], ["LANDUSE"])

    def test_list_lite_rows_still_carry_the_symbology_flag(self):
        # Discovery must survive the lite details drop: the summary is tiny.
        payload = {
            "datasets": [
                {
                    "id": 7,
                    "dataType": "vector",
                    "details": {
                        "display": {"esri": {"renderer": {"type": "classBreaks", "classBreakInfos": [1]}}}
                    },
                }
            ]
        }
        row = trim_datasets_list_payload(payload)["datasets"][0]
        self.assertNotIn("details", row)
        self.assertEqual(row["symbology"]["rendererType"], "classBreaks")

    def test_a_plain_row_reports_no_saved_style(self):
        row = trim_dataset_for_mcp({"id": 7, "dataType": "vector", "details": {}}, "lite")
        self.assertEqual(row["symbology"], {"hasSavedStyle": False, "kind": "none"})

    def test_list_payload_standard_keeps_trimmed_details(self):
        huge = json.dumps(self._sample_vector_details())
        payload = {"datasets": [{"id": 1, "name": "x", "details": huge}]}
        out = trim_datasets_list_payload(payload, details_level="standard")

        details = out["datasets"][0]["details"]
        self.assertIsInstance(details, dict)
        self.assertNotIn("tilejson", details)

    def test_fields_projection_keeps_only_requested_keys(self):
        payload = {
            "datasets": [
                {"id": 1, "name": "x", "dataType": "vector", "ownerUserId": 9, "details": {}}
            ]
        }

        out = trim_datasets_list_payload(payload, fields=["name", "dataType"])

        self.assertEqual(set(out["datasets"][0]), {"id", "name", "dataType"})

    def test_fields_projection_refuses_an_unknown_key(self):
        payload = {"datasets": [{"id": 1, "name": "x"}]}

        with self.assertRaises(ValueError) as ctx:
            trim_datasets_list_payload(payload, fields=["geometry"])

        self.assertIn("geometry", str(ctx.exception))

    def test_raster_get_omits_metadata_blobs(self):
        raw = {
            "type": "raster",
            "metadata_4326": {"srid": 4326, "width": 1000, "histogram": [1] * 5000},
            "bands": [{"band": 1}],
        }
        out = trim_details(raw, "get")
        self.assertIn("_omitted", out["metadata_4326"])
        self.assertEqual(out["metadata_4326"].get("srid"), 4326)

    def test_trim_dataset_for_mcp_lite(self):
        ds = {"id": 5, "name": "r", "details": self._sample_vector_details()}
        out = trim_dataset_for_mcp(ds, "lite")
        self.assertNotIn("tilejson", out["details"])

    def test_lite_strips_wkt_from_spatial_reference(self):
        raw = {
            "type": "vector",
            "spatialReference": {"srid": 4326, "wkt": "GEOGCRS[...very long...]"},
        }
        out = trim_details(raw, "lite")
        self.assertEqual(out["spatialReference"], {"srid": 4326})

    def test_normalize_details_level_legacy_aliases(self):
        self.assertEqual(normalize_details_level("list", default="lite"), "lite")
        self.assertEqual(normalize_details_level("get", default="full"), "full")

    def test_geo_extent_is_a_requestable_projection(self):
        # details may be a JSON string; geo_extent returns a labelled box without
        # pulling the whole (large) details blob.
        ds = {
            "id": 2554,
            "name": "parcel",
            "details": json.dumps(
                {"geo_extent": [45.115, 25.354, 62.110, 38.067], "fields": [{"name": "a"}]}
            ),
        }

        out = trim_dataset_for_mcp(ds, "lite", fields=["id", "geo_extent"])

        self.assertEqual(
            out["geo_extent"],
            {
                "bbox": [45.115, 25.354, 62.110, 38.067],
                "crs": "EPSG:4326",
                "axisOrder": "west,south,east,north",
            },
        )
        self.assertNotIn("details", out)

    def test_details_geo_extent_alias_returns_the_same_box(self):
        ds = {"id": 1, "details": {"geo_extent": [1.0, 2.0, 3.0, 4.0]}}

        out = trim_dataset_for_mcp(ds, "lite", fields=["details.geo_extent"])

        self.assertEqual(out["geo_extent"]["bbox"], [1.0, 2.0, 3.0, 4.0])

    def test_geo_extent_falls_back_to_the_ext_columns(self):
        ds = {
            "id": 2304,
            "details": {},
            "ext_west": 50.0,
            "ext_south": 33.0,
            "ext_east": 51.0,
            "ext_north": 34.0,
        }

        out = trim_dataset_for_mcp(ds, "lite", fields=["geo_extent"])

        self.assertEqual(out["geo_extent"]["bbox"], [50.0, 33.0, 51.0, 34.0])

    def test_list_geo_extent_survives_the_lite_details_drop(self):
        payload = {
            "datasets": [
                {"id": 1, "details": json.dumps({"geo_extent": [1.0, 2.0, 3.0, 4.0]})}
            ]
        }

        out = trim_datasets_list_payload(payload, fields=["id", "geo_extent"])

        row = out["datasets"][0]
        self.assertEqual(row["geo_extent"]["bbox"], [1.0, 2.0, 3.0, 4.0])
        self.assertNotIn("details", row)


if __name__ == "__main__":
    unittest.main()
