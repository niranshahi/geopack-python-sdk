"""Async twins of the query lanes (slice 010, decision D10).

Every assertion here must hold identically on the sync lane: same URL, same
payload keys, same exceptions. The payload is built by the shared helpers, so
these tests guard the wiring, not a second implementation.
"""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_datasets import AsyncDatasetManager
from geopack_sdk.exceptions import AggregationUnsupported, PagedUnsupported
from geopack_sdk.exceptions import GeopackAPIError
from geopack_sdk.models import AggregateResult, MintedUrl, PagedFeatureCollection
from tests.test_query_lanes import _page


class AsyncQueryLanesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncDatasetManager(self.client)

    async def test_query_paged_matches_the_sync_body(self):
        self.client.post.return_value = _page(page=2, page_size=50)

        result = await self.manager.query_paged(
            7, {"filter": None, "spatialFilter": None}, page=2, page_size=50
        )

        self.assertIsInstance(result, PagedFeatureCollection)
        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/7/query/paged"
        )
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["pagination"], {"page": 2, "pageSize": 50})
        self.assertEqual(payload["options"], {"includeTotalCount": True})
        self.assertIsNone(payload["filter"])

    async def test_query_paged_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            await self.manager.query_paged(7, page=0)
        self.client.post.assert_not_awaited()

    async def test_degraded_count_is_not_an_error(self):
        self.client.post.return_value = _page(total=None)

        result = await self.manager.query_paged(7)

        self.assertTrue(result.pagination.is_count_degraded)

    async def test_iterate_pages_is_an_async_generator(self):
        self.client.post.side_effect = [
            _page(page=1, page_size=2, total=3, features=[{}, {}]),
            _page(page=2, page_size=2, total=3, features=[{}]),
        ]

        pages = [page async for page in self.manager.iterate_pages(7, page_size=2)]

        self.assertEqual(len(pages), 2)
        self.assertEqual(self.client.post.await_count, 2)

    async def test_aggregate_and_count(self):
        self.client.post.return_value = {
            "datasetId": 7,
            "rows": [{"value": 9}],
            "columns": [{"type": "number", "key": "value"}],
            "metadata": {"labelOrderApplied": False},
        }

        result = await self.manager.aggregate(
            7, aggregation={"aggregates": [{"aggregate": "count", "alias": "value"}]}
        )
        self.assertIsInstance(result, AggregateResult)
        self.assertEqual(result.rows[0]["value"], 9)

        self.assertEqual(await self.manager.count(7), 9)
        entry = self.client.post.call_args.kwargs["json"]["aggregation"]["aggregates"][0]
        self.assertEqual(entry["aggregate"], "count")

    async def test_typed_errors_surface_on_the_async_lane(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400, reason="Bad Request", text="", json_loader=lambda: {"code": "PAGED_UNSUPPORTED"}
        )
        with self.assertRaises(PagedUnsupported):
            await self.manager.query_paged(7)

        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {"code": "AGGREGATION_UNSUPPORTED"},
        )
        with self.assertRaises(AggregationUnsupported):
            await self.manager.aggregate(7, aggregation={"aggregates": []})

    async def test_minted_urls(self):
        self.client.post.return_value = {
            "url": "https://portal.test/api/datasets/7/query-features",
            "expiresAt": "2026-11-19T12:00:00Z",
            "mediaQuery": "media=q",
        }
        self.client.get.return_value = {"url": "https://portal.test/api/tiles"}

        query_url = await self.manager.mint_query_access_url(7, {"filter": None})
        mvt_url = await self.manager.mint_mvt_access_url(7)
        tiles_url = await self.manager.get_tiles_access_url(7)

        self.assertIsInstance(query_url, MintedUrl)
        self.assertEqual(
            self.client.post.call_args_list[0].kwargs["json"],
            {"queryDsl": {"filter": None}},
        )
        self.assertEqual(self.client.post.call_args_list[1].kwargs["json"], {})
        self.client.get.assert_awaited_once_with("/datasets/7/tiles/access-url")
        self.assertEqual(tiles_url.url, "https://portal.test/api/tiles")
        self.assertEqual(mvt_url.media_query, "media=q")


if __name__ == "__main__":
    unittest.main()
