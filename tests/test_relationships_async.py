"""Async twins of the relationship/schema lane (slice 011)."""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_datasets import AsyncDatasetManager
from geopack_sdk.exceptions import GeopackAPIError, RelationshipCatalogUnavailable
from geopack_sdk.models import (
    ColumnBounds,
    RelatedRecordsResult,
    RelationshipDescriptor,
    SchemaPreview,
)
from tests.test_relationships import RELATED, RELATIONSHIPS


class AsyncRelationshipsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncDatasetManager(self.client)

    async def test_get_relationships(self):
        self.client.get.return_value = RELATIONSHIPS

        relationships = await self.manager.get_relationships(7)

        self.client.get.assert_awaited_once_with("/datasets/7/relationships")
        self.assertIsInstance(relationships[0], RelationshipDescriptor)
        self.assertTrue(relationships[1].read_only)

    async def test_relationship_catalog_unavailable(self):
        self.client.get.side_effect = GeopackAPIError.from_http_status(
            409,
            reason="Conflict",
            text="",
            json_loader=lambda: {"code": "RELATIONSHIP_CATALOG_UNAVAILABLE"},
        )

        with self.assertRaises(RelationshipCatalogUnavailable):
            await self.manager.get_relationships(7)

    async def test_get_related_records_matches_the_sync_body(self):
        self.client.post.return_value = RELATED

        result = await self.manager.get_related_records(
            7, "wells_to_zones", [101], limit=50
        )

        self.assertIsInstance(result, RelatedRecordsResult)
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["direction"], "forward")
        self.assertEqual(payload["originObjectIds"], [101])
        self.assertEqual(payload["queryOptions"], {"returnGeometry": True, "limit": 50})
        self.assertEqual(result.groups, {"101": [11]})

    async def test_get_related_records_validates_before_any_call(self):
        with self.assertRaises(ValueError):
            await self.manager.get_related_records(7, "rel", [])
        self.client.post.assert_not_awaited()

    async def test_preview_schema_and_passthrough_reads(self):
        self.client.post.return_value = {"success": True, "schema": {"fields": []}}
        self.client.get.side_effect = [
            {"success": True, "data": {"area": {"min": 0, "max": 1}}},
            {"canEdit": True},
        ]

        preview = await self.manager.preview_schema(7, {"relationshipJoin": {}})
        bounds = await self.manager.get_column_bounds(7)
        context = await self.manager.get_access_context(7)

        self.assertIsInstance(preview, SchemaPreview)
        self.assertIsInstance(bounds, ColumnBounds)
        self.assertEqual(context, {"canEdit": True})
        self.assertEqual(
            self.client.get.call_args_list[0].args[0], "/datasets/7/column-bounds"
        )
        self.assertEqual(
            self.client.get.call_args_list[1].args[0], "/datasets/7/access-context"
        )


if __name__ == "__main__":
    unittest.main()
