import unittest

from geopack_sdk_mcp.sanitize.query_results import (
    MAX_QUERY_LIMIT,
    clamp_query_limit,
    trim_feature_collection_for_mcp,
)


class TestMcpQuerySanitize(unittest.TestCase):
    def test_clamp_query_limit_defaults(self):
        self.assertEqual(clamp_query_limit(None), 100)

    def test_clamp_query_limit_caps(self):
        self.assertEqual(clamp_query_limit(9999), MAX_QUERY_LIMIT)

    def test_trim_feature_collection_truncates(self):
        payload = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}}] * 600,
        }
        out = trim_feature_collection_for_mcp(payload)
        self.assertEqual(len(out["features"]), MAX_QUERY_LIMIT)
        self.assertTrue(out["featuresTruncated"])
        self.assertEqual(out["featuresTotal"], 600)


if __name__ == "__main__":
    unittest.main()
