"""Async twins of the virtual-dataset lanes (slice 013, decision D10).

Same URL, same body, same exceptions as the sync lane — the DTOs and the
request shapes are shared, so these tests guard the wiring.
"""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_datasets import AsyncDatasetManager
from geopack_sdk.exceptions import GeopackAuthError, GeopackAPIError
from geopack_sdk.models import CreateVirtualSqlDatasetDto, Dataset
from tests.test_virtual_datasets import DATASET, PROBE


class AsyncVirtualDatasetsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncDatasetManager(self.client)

    async def test_create_virtual_dataset_matches_the_sync_body(self):
        self.client.post.return_value = DATASET

        result = await self.manager.create_virtual_dataset_from_filter(
            name="Wells in zone A",
            data_store_id=3,
            workgroup_id=2,
            root_dataset_id=7,
            query_dsl={"filter": None},
        )

        self.assertIsInstance(result, Dataset)
        self.assertEqual(self.client.post.call_args.args[0], "/datasets/virtual")
        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(body["kind"], "virtualFilter")
        self.assertEqual(body["queryDsl"], {"filter": None})

    async def test_deprecated_esri_alias_targets_the_new_route(self):
        self.client.post.return_value = DATASET

        await self.manager.create_virtual_esri_dataset(
            {
                "name": "x",
                "dataStoreId": 3,
                "workgroupId": 2,
                "rootDatasetId": 7,
                "queryDsl": {},
            }
        )

        self.assertEqual(self.client.post.call_args.args[0], "/datasets/virtual")

    async def test_preview_then_create_round_trip(self):
        self.client.post.side_effect = [PROBE, DATASET]

        probe = await self.manager.preview_sql(3, "SELECT parcel_id, owner, shape FROM parcels")
        result = await self.manager.create_virtual_sql_dataset(
            CreateVirtualSqlDatasetDto(
                name="Parcels",
                dataStoreId=3,
                workgroupId=2,
                sql="SELECT parcel_id, owner, shape FROM parcels",
                fields=probe["fields"],
            )
        )

        self.assertIsInstance(result, Dataset)
        self.assertEqual(
            self.client.post.call_args_list[0].args[0], "/datasets/sql-preview"
        )
        self.assertEqual(
            self.client.post.call_args_list[1].args[0], "/datasets/virtual-sql"
        )
        self.assertEqual(
            self.client.post.call_args_list[1].kwargs["json"]["fields"],
            PROBE["fields"],
        )

    async def test_update_is_partial(self):
        self.client.put.return_value = DATASET

        await self.manager.update_virtual_sql_dataset(91, {"sql": "SELECT 1"})

        self.assertEqual(self.client.put.call_args.args[0], "/datasets/91/virtual-sql")
        self.assertEqual(self.client.put.call_args.kwargs["json"], {"sql": "SELECT 1"})

    async def test_missing_capability_is_not_retried(self):
        self.client.put.side_effect = GeopackAuthError.from_http_status(
            403,
            reason="Forbidden",
            text="",
            json_loader=lambda: {"message": "Missing permission: dataset:create_virtual_sql"},
        )

        with self.assertRaises(GeopackAuthError):
            await self.manager.update_virtual_sql_dataset(91, {"sql": "SELECT 1"})

        self.client.put.assert_awaited_once()

    async def test_unsupported_kind_error_is_verbatim(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {"message": "Invalid Input: kind requires ESRI."},
        )

        with self.assertRaises(GeopackAPIError) as ctx:
            await self.manager.create_virtual_dataset_from_filter(
                name="x",
                data_store_id=3,
                workgroup_id=2,
                root_dataset_id=7,
                query_dsl={},
            )

        self.assertIn("requires ESRI", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
