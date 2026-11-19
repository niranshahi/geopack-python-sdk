"""Query lanes: paged, aggregate, minted URLs (slice 010).

Contract tests bind to what ``datasetRoutes.js`` + ``datasetValidators.js``
declare. The validator is the authority for the aggregate kinds — the SDK must
pass all twelve through untouched.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.datasets import DatasetManager
from geopack_sdk.exceptions import (
    AggregationUnsupported,
    GeopackAPIError,
    PagedUnsupported,
)
from geopack_sdk.models import (
    AggregateResult,
    MintedUrl,
    PagedFeatureCollection,
)


def _page(page=1, page_size=100, total=250, features=None):
    return {
        "features": features if features is not None else [{"type": "Feature"}],
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "totalCount": total,
            "totalPages": None if total is None else max(1, -(-total // page_size)),
            "hasNextPage": total is not None and page * page_size < total,
            "hasPreviousPage": page > 1,
        },
        "metadata": {
            "datasetId": 7,
            "baseFilterApplied": True,
            "rlsApplied": True,
            "queryMode": "physical",
        },
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
    }


class QueryLanesTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = DatasetManager(self.client)

    # --- paged ------------------------------------------------------------

    def test_query_paged_posts_the_documented_body(self):
        self.client.post.return_value = _page(page=2, page_size=50)

        result = self.manager.query_paged(
            7,
            {"filter": {"operator": "AND", "conditions": []}, "spatialFilter": None},
            page=2,
            page_size=50,
        )

        self.assertIsInstance(result, PagedFeatureCollection)
        endpoint = self.client.post.call_args.args[0]
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(endpoint, "/datasets/7/query/paged")
        self.assertEqual(payload["pagination"], {"page": 2, "pageSize": 50})
        self.assertEqual(payload["options"], {"includeTotalCount": True})
        # Verbatim DSL: the explicit null survives the round trip.
        self.assertIsNone(payload["spatialFilter"])
        self.assertIn("filter", payload)
        self.assertEqual(result.pagination.page, 2)
        self.assertEqual(result.pagination.page_size, 50)
        self.assertEqual(result.metadata["queryMode"], "physical")
        self.assertFalse(result.pagination.is_count_degraded)

    def test_query_paged_defaults_page_and_size(self):
        self.client.post.return_value = _page()

        self.manager.query_paged(7)

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["pagination"],
            {"page": 1, "pageSize": 100},
        )

    def test_query_paged_honours_dsl_pagination_over_defaults(self):
        self.client.post.return_value = _page()

        self.manager.query_paged(7, {"pagination": {"page": 3, "pageSize": 25}})

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["pagination"],
            {"page": 3, "pageSize": 25},
        )

    def test_query_paged_rejects_non_positive_page(self):
        for kwargs in ({"page": 0}, {"page_size": 0}, {"page": -2}):
            with self.assertRaises(ValueError):
                self.manager.query_paged(7, **kwargs)
        self.client.post.assert_not_called()

    def test_degraded_total_count_is_a_normal_answer(self):
        self.client.post.return_value = _page(total=None)

        result = self.manager.query_paged(7)

        self.assertIsNone(result.pagination.total_count)
        self.assertIsNone(result.pagination.total_pages)
        self.assertTrue(result.pagination.is_count_degraded)

    def test_include_total_count_false_skips_the_count(self):
        self.client.post.return_value = _page(total=None)

        self.manager.query_paged(7, include_total_count=False)

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["options"],
            {"includeTotalCount": False},
        )

    def test_order_by_is_passed_through(self):
        self.client.post.return_value = _page()

        self.manager.query_paged(7, order_by=[{"field": "area", "direction": "DESC"}])

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["orderBy"],
            [{"field": "area", "direction": "DESC"}],
        )

    def test_iterate_pages_stops_on_the_last_page(self):
        self.client.post.side_effect = [
            _page(page=1, page_size=2, total=3, features=[{}, {}]),
            _page(page=2, page_size=2, total=3, features=[{}]),
        ]

        pages = list(self.manager.iterate_pages(7, page_size=2))

        self.assertEqual(len(pages), 2)
        self.assertEqual(self.client.post.call_count, 2)
        self.assertEqual(
            self.client.post.call_args_list[1].kwargs["json"]["pagination"]["page"], 2
        )

    def test_iterate_pages_stops_on_an_empty_page_even_if_the_server_says_more(self):
        broken = _page(page=1, page_size=10, total=1000, features=[])
        self.client.post.return_value = broken

        pages = list(self.manager.iterate_pages(7, page_size=10))

        self.assertEqual(len(pages), 1)
        self.assertEqual(self.client.post.call_count, 1)

    def test_paged_unsupported_surfaces_as_typed_error(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "code": "PAGED_UNSUPPORTED",
                "message": "Store cannot page",
                "dataStoreType": "filesystem",
            },
        )

        with self.assertRaises(PagedUnsupported) as raised:
            self.manager.query_paged(7)

        self.assertEqual(raised.exception.data_store_type, "filesystem")

    # --- aggregate --------------------------------------------------------

    def test_aggregate_passes_the_twelve_kinds_through(self):
        kinds = (
            "count",
            "countDistinct",
            "sum",
            "avg",
            "min",
            "max",
            "stddev",
            "stddevPop",
            "variance",
            "varPop",
            "median",
            "percentile",
        )
        aggregation = {
            "groupBy": [{"field": "zone"}],
            "aggregates": [
                {"field": "area", "aggregate": kind, "alias": f"a_{kind}"}
                for kind in kinds
            ],
            "orderBy": [{"key": "a_count", "direction": "DESC"}],
            "limit": 20,
        }
        self.client.post.return_value = {
            "datasetId": 7,
            "rows": [{"zone": "A", "a_count": 3}],
            "columns": [{"type": "number", "key": "a_count", "field": "area"}],
            "metadata": {"baseFilterApplied": True, "labelOrderApplied": False},
        }

        result = self.manager.aggregate(7, aggregation=aggregation)

        self.assertIsInstance(result, AggregateResult)
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(self.client.post.call_args.args[0], "/datasets/7/query/aggregate")
        self.assertEqual(
            [entry["aggregate"] for entry in payload["aggregation"]["aggregates"]],
            list(kinds),
        )
        self.assertEqual(payload["aggregation"]["limit"], 20)
        self.assertEqual(result.dataset_id, 7)
        self.assertEqual(result.rows[0]["a_count"], 3)
        self.assertEqual(result.columns[0].key, "a_count")

    def test_aggregate_rejects_structural_violations_before_any_call(self):
        bad = (
            {"limit": 51},
            {"limit": 0},
            {"groupBy": [{"field": "a"}, {"field": "b"}, {"field": "c"}, {"field": "d"}]},
            {"orderBy": [{"key": "a"}, {"key": "b"}, {"key": "c"}, {"key": "d"}]},
            {"aggregates": "count"},
        )
        for aggregation in bad:
            with self.assertRaises(ValueError):
                self.manager.aggregate(7, aggregation=aggregation)
        self.client.post.assert_not_called()

    def test_aggregate_sends_explicit_nulls_for_absent_scope(self):
        self.client.post.return_value = {"datasetId": 7, "rows": [], "columns": []}

        self.manager.aggregate(7, aggregation={"aggregates": [{"aggregate": "count"}]})

        payload = self.client.post.call_args.kwargs["json"]
        self.assertIn("filter", payload)
        self.assertIsNone(payload["filter"])
        self.assertIsNone(payload["spatialFilter"])

    def test_aggregation_unsupported_surfaces_as_typed_error(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "code": "AGGREGATION_UNSUPPORTED",
                "dataStoreType": "filesystem",
            },
        )

        with self.assertRaises(AggregationUnsupported):
            self.manager.aggregate(7, aggregation={"aggregates": [{"aggregate": "count"}]})

    # --- count ------------------------------------------------------------

    def test_count_is_sugar_over_aggregate(self):
        self.client.post.return_value = {
            "datasetId": 7,
            "rows": [{"value": 42}],
            "columns": [{"type": "number", "key": "value"}],
        }

        self.assertEqual(self.manager.count(7), 42)

        aggregation = self.client.post.call_args.kwargs["json"]["aggregation"]
        self.assertEqual(aggregation["limit"], 1)
        self.assertEqual(aggregation["aggregates"][0]["aggregate"], "count")
        self.assertEqual(aggregation["aggregates"][0]["alias"], "value")

    def test_count_distinct_names_the_field(self):
        self.client.post.return_value = {"rows": [{"value": 4}], "columns": []}

        self.assertEqual(self.manager.count(7, field="zone", distinct=True), 4)

        entry = self.client.post.call_args.kwargs["json"]["aggregation"]["aggregates"][0]
        self.assertEqual(entry["aggregate"], "countDistinct")
        self.assertEqual(entry["field"], "zone")

    def test_count_reads_a_single_unnamed_value_and_zero_when_empty(self):
        self.client.post.return_value = {"rows": [{"n": "11"}], "columns": []}
        self.assertEqual(self.manager.count(7), 11)

        self.client.post.return_value = {"rows": [], "columns": []}
        self.assertEqual(self.manager.count(7), 0)

    # --- minted URLs ------------------------------------------------------

    def test_mint_query_access_url(self):
        self.client.post.return_value = {
            "url": "https://portal.test/api/datasets/7/query-features?sig=x",
            "expiresAt": "2026-11-19T12:00:00.000Z",
            "mediaQuery": "media=q&sig=x",
        }

        minted = self.manager.mint_query_access_url(7, {"filter": None})

        self.assertIsInstance(minted, MintedUrl)
        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/7/query/mint-access-url"
        )
        self.assertEqual(
            self.client.post.call_args.kwargs["json"], {"queryDsl": {"filter": None}}
        )
        self.assertEqual(minted.media_query, "media=q&sig=x")
        self.assertIsNotNone(minted.expires_at_datetime)

    def test_mint_query_access_url_requires_a_dsl(self):
        with self.assertRaises(ValueError):
            self.manager.mint_query_access_url(7, None)
        self.client.post.assert_not_called()

    def test_mint_mvt_access_url_is_optional_scope(self):
        self.client.post.return_value = {"url": "https://portal.test/api/tiles"}

        self.manager.mint_mvt_access_url(7)

        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/7/mvt/mint-access-url"
        )
        self.assertEqual(self.client.post.call_args.kwargs["json"], {})

    def test_get_tiles_access_url(self):
        self.client.get.return_value = {"url": "https://portal.test/api/tiles"}

        minted = self.manager.get_tiles_access_url(7)

        self.client.get.assert_called_once_with("/datasets/7/tiles/access-url")
        self.assertEqual(minted.url, "https://portal.test/api/tiles")


if __name__ == "__main__":
    unittest.main()
