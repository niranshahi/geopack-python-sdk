"""Async twin of the computed-column manager (slice 013, decision D10).

The body builder is shared with the sync lane, so a coded rejection in a
``200`` must be returned — never raised — on both.
"""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_computed_columns import AsyncComputedColumnManager
from geopack_sdk.models import ComputedColumnPreview
from tests.test_computed_columns import CATALOG, COMPILED, REJECTED


class AsyncComputedColumnsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncComputedColumnManager(self.client)

    async def test_catalog_matches_the_sync_lane(self):
        self.client.get.return_value = CATALOG

        result = await self.manager.catalog("postgres")

        self.client.get.assert_awaited_once_with(
            "/datasets/computed-column/catalog",
            params={"dataStoreType": "postgres"},
        )
        self.assertEqual(result["dialect"], "postgres")

    async def test_preview_compiles_an_expression(self):
        self.client.post.return_value = COMPILED

        result = await self.manager.preview(
            data_store_type="postgres", expression="1 + 1"
        )

        self.assertIsInstance(result, ComputedColumnPreview)
        self.assertTrue(result.ok)
        self.assertEqual(result.compiled_sql, COMPILED["expression"])
        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/computed-column/preview"
        )

    async def test_preview_compiles_a_calc(self):
        self.client.post.return_value = {**COMPILED, "isWindow": True}
        calc = {"kind": "measure", "fn": "area", "field": "shape"}

        result = await self.manager.preview(
            data_store_type="postgres", calc=calc
        )

        self.assertTrue(result.isWindow)
        self.assertEqual(self.client.post.call_args.kwargs["json"]["calc"], calc)

    async def test_rejected_expression_does_not_raise(self):
        self.client.post.return_value = REJECTED

        result = await self.manager.preview(data_store_type="postgres", expression="nope")

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "EXPR_UNKNOWN_IDENTIFIER")
        self.assertIsNone(result.compiled_sql)

    async def test_input_checks_run_before_any_request(self):
        with self.assertRaises(ValueError):
            await self.manager.catalog("")
        with self.assertRaises(ValueError):
            await self.manager.preview(data_store_type="postgres")
        self.client.get.assert_not_awaited()
        self.client.post.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
