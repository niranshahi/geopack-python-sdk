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

    def test_list_payload_trims_each_dataset(self):
        huge = json.dumps(self._sample_vector_details())
        payload = {
            "datasets": [{"id": 1, "name": "x", "details": huge}],
            "totalCount": 1,
            "totalPages": 1,
            "currentPage": 1,
            "itemsPerPage": 10,
        }
        out = trim_datasets_list_payload(payload)
        details = out["datasets"][0]["details"]
        self.assertIsInstance(details, dict)
        self.assertNotIn("tilejson", details)

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


if __name__ == "__main__":
    unittest.main()
