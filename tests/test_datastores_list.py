import unittest

from geopack_sdk.datastores import parse_datastore_list_response


class TestParseDatastoreListResponse(unittest.TestCase):
    def test_bare_array_from_api(self):
        ts = "2026-01-01T00:00:00Z"
        raw = [
            {
                "id": 1,
                "name": "pg",
                "type": "postgres",
                "status": "active",
                "createdAt": ts,
                "updatedAt": ts,
            },
            {
                "id": 2,
                "name": "gpkg",
                "type": "gpkg",
                "status": "active",
                "createdAt": ts,
                "updatedAt": ts,
            },
        ]
        resp = parse_datastore_list_response(raw)
        self.assertEqual(len(resp.datastores), 2)
        self.assertEqual(resp.totalCount, 2)
        self.assertEqual(resp.datastores[0].name, "pg")

    def test_wrapped_object(self):
        raw = {
            "datastores": [
                {
                    "id": 3,
                    "name": "esri",
                    "type": "esri",
                    "status": "active",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "updatedAt": "2026-01-01T00:00:00Z",
                }
            ],
            "totalCount": 1,
        }
        resp = parse_datastore_list_response(raw)
        self.assertEqual(len(resp.datastores), 1)


if __name__ == "__main__":
    unittest.main()
