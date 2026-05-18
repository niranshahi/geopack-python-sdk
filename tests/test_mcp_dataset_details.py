import json
import unittest

from geopack_sdk_mcp.sanitize.dataset_details import (
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

    def test_list_profile_drops_tilejson_and_fields(self):
        out = trim_details(self._sample_vector_details(), "list")
        self.assertNotIn("tilejson", out)
        self.assertEqual(out["fieldsCount"], 2)
        self.assertNotIn("fields", out)

    def test_get_profile_keeps_tilejson_strips_values(self):
        out = trim_details(self._sample_vector_details(), "get")
        self.assertIn("tilejson", out)
        attr = out["tilejson"]["tilestats"]["layers"][0]["attributes"][0]
        self.assertNotIn("values", attr)
        self.assertTrue(attr.get("valuesOmitted"))
        self.assertEqual(attr.get("valuesCount"), 200)

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

    def test_trim_dataset_for_mcp_list(self):
        ds = {"id": 5, "name": "r", "details": self._sample_vector_details()}
        out = trim_dataset_for_mcp(ds, "list")
        self.assertNotIn("tilejson", out["details"])


if __name__ == "__main__":
    unittest.main()
