import unittest
from unittest.mock import MagicMock

from geopack_sdk.datasets import DatasetManager
from geopack_sdk.models import DatasetAcl, DatasetDiscoverResponse, FeatureCollection


class TestDatasetManagerExtended(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.mgr = DatasetManager(self.client)

    def test_delete(self):
        self.client.delete.return_value = None
        self.mgr.delete(42)
        self.client.delete.assert_called_once_with("/datasets/42")

    def test_query(self):
        self.client.post.return_value = {
            "type": "FeatureCollection",
            "features": [],
        }
        result = self.mgr.query(42, {"limit": 10, "offset": 0, "returnGeometry": True})
        self.assertIsInstance(result, FeatureCollection)
        self.client.post.assert_called_once_with(
            "/datasets/42/query",
            json={
                "pagination": {"limit": 10, "offset": 0},
                "projection": {"returnGeometry": True},
            },
        )

    def test_discover_immediate(self):
        self.client.post.return_value = {
            "success": True,
            "datasets": [{"name": "layer1"}],
            "count": 1,
        }
        result = self.mgr.discover(
            source_files=[{"sessionId": "s1", "relativePath": "a.shp"}],
            data_store_id=1,
            workgroup_id=1,
            wait=False,
        )
        self.assertIsInstance(result, DatasetDiscoverResponse)
        self.assertEqual(result.count, 1)
        self.assertFalse(result.is_background_task)

    def test_get_acls(self):
        self.client.get.return_value = [
            {
                "id": 1,
                "resourceType": "DATASET",
                "resourceId": 42,
                "principalType": "USER",
                "principalId": 2,
                "permissionId": 3,
                "effect": "Allow",
                "createdAt": "2026-01-01T00:00:00.000Z",
                "updatedAt": "2026-01-01T00:00:00.000Z",
            }
        ]
        acls = self.mgr.get_acls(42)
        self.assertEqual(len(acls), 1)
        self.assertIsInstance(acls[0], DatasetAcl)

    def test_create_and_delete_acl(self):
        self.client.post.return_value = []
        self.mgr.create_acls(
            42,
            principals=[{"principalType": "USER", "principalId": 2}],
            permissions=["dataset:read"],
        )
        self.client.post.assert_called_once()

        self.client.delete.return_value = None
        self.mgr.delete_acl(42, 99)
        self.client.delete.assert_called_with("/datasets/42/acl/99")


if __name__ == "__main__":
    unittest.main()
