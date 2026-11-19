"""Async twins of the DataStore relationship CRUD (slice 015)."""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_datastores import AsyncDataStoreManager
from geopack_sdk.exceptions import GeopackAPIError, RelationshipCatalogUnavailable
from tests.test_datastore_relationships import CATALOG, DESCRIPTOR, PAYLOAD


class AsyncDataStoreRelationshipsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncDataStoreManager(self.client)

    async def test_crud_hits_the_same_paths_as_sync(self):
        self.client.get.return_value = {"success": True, "data": CATALOG}
        snapshot = await self.manager.get_relationships(3)
        self.assertEqual(snapshot["datastoreUuid"], "ds-3")

        self.client.post.return_value = {"success": True, "data": DESCRIPTOR}
        created = await self.manager.create_relationship(3, PAYLOAD)
        self.assertEqual(created["id"], "rel-1")

        self.client.put.return_value = {"success": True, "data": DESCRIPTOR}
        updated = await self.manager.update_relationship(3, "rel-1", PAYLOAD)
        self.assertEqual(updated["name"], "wells_to_zones")

        self.client.delete.return_value = {"success": True, "data": {"id": "rel-1"}}
        deleted = await self.manager.delete_relationship(3, "rel-1")
        self.assertEqual(deleted["id"], "rel-1")

        self.client.get.assert_awaited_once_with("/datastores/3/relationships")
        self.client.post.assert_awaited_once_with(
            "/datastores/3/relationships", json=PAYLOAD
        )
        self.client.put.assert_awaited_once_with(
            "/datastores/3/relationships/rel-1", json=PAYLOAD
        )
        self.client.delete.assert_awaited_once_with(
            "/datastores/3/relationships/rel-1"
        )

    async def test_409_conflict_is_surfaced(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            409,
            reason="Conflict",
            text="",
            json_loader=lambda: {"error": {"code": "RELATIONSHIP_CATALOG_STALE"}},
        )

        with self.assertRaises(RelationshipCatalogUnavailable):
            await self.manager.create_relationship(3, PAYLOAD)
        self.assertEqual(self.client.post.await_count, 1)


if __name__ == "__main__":
    unittest.main()
