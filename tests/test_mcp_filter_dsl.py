"""Filter-node normalization for the query/aggregate lanes (2026-11-24 report).

A flat or Mongo-ish filter node used to reach the portal and answer an opaque
HTTP 500; it must instead be coerced to the typed node grammar client-side, or
refused with a coded ``invalid_args`` 4xx before any round trip.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from geopack_sdk.models import AggregateResult

from geopack_sdk_mcp.errors import ToolArgumentError
from geopack_sdk_mcp.sanitize.filter_dsl import normalize_filter_node
from geopack_sdk_mcp.tool_handlers.datasets import aggregate_dataset, query_dataset


class NormalizeFilterNodeTest(unittest.TestCase):
    def test_none_passes_through(self):
        self.assertIsNone(normalize_filter_node(None))

    def test_a_typed_rule_is_kept(self):
        rule = {"type": "rule", "field": "name", "operator": "$ilike", "value": "%a%"}
        self.assertEqual(normalize_filter_node(rule), rule)

    def test_a_flat_rule_is_wrapped(self):
        node = {"field": "name", "operator": "=", "value": "A"}
        self.assertEqual(
            normalize_filter_node(node),
            {"type": "rule", "field": "name", "operator": "=", "value": "A"},
        )

    def test_a_rule_without_value_is_kept(self):
        node = {"field": "name", "operator": "isNull"}
        self.assertEqual(
            normalize_filter_node(node),
            {"type": "rule", "field": "name", "operator": "isNull"},
        )

    def test_a_group_without_type_is_typed(self):
        node = {"operator": "or", "children": [{"field": "a", "operator": "=", "value": 1}]}
        self.assertEqual(
            normalize_filter_node(node),
            {
                "type": "group",
                "operator": "OR",
                "children": [{"type": "rule", "field": "a", "operator": "=", "value": 1}],
            },
        )

    def test_a_list_becomes_an_and_group(self):
        node = [
            {"field": "a", "operator": "=", "value": 1},
            {"field": "b", "operator": ">", "value": 2},
        ]
        self.assertEqual(
            normalize_filter_node(node),
            {
                "type": "group",
                "operator": "AND",
                "children": [
                    {"type": "rule", "field": "a", "operator": "=", "value": 1},
                    {"type": "rule", "field": "b", "operator": ">", "value": 2},
                ],
            },
        )

    def test_nested_children_are_normalized(self):
        node = {
            "type": "group",
            "operator": "AND",
            "children": [{"field": "a", "operator": "=", "value": 1}],
        }
        self.assertEqual(
            normalize_filter_node(node),
            {
                "type": "group",
                "operator": "AND",
                "children": [{"type": "rule", "field": "a", "operator": "=", "value": 1}],
            },
        )

    def test_a_mongo_style_node_is_refused(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            normalize_filter_node({"landuse": {"$eq": 5}})
        self.assertEqual(ctx.exception.invalid_args, ["filter"])

    def test_an_unknown_type_is_refused(self):
        with self.assertRaises(ToolArgumentError):
            normalize_filter_node({"type": "bogus", "field": "a"})

    def test_a_group_without_children_is_refused(self):
        with self.assertRaises(ToolArgumentError):
            normalize_filter_node({"type": "group", "operator": "AND"})

    def test_the_key_names_the_argument(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            normalize_filter_node("nope", key="query")
        self.assertEqual(ctx.exception.invalid_args, ["query"])


class AggregateFilterTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.datasets.aggregate.return_value = AggregateResult(
            datasetId=7, rows=[], columns=[], metadata={}
        )

    def test_a_flat_filter_is_typed_before_the_call(self):
        aggregate_dataset(self.client, 7, filter={"field": "a", "operator": "=", "value": 1})
        sent = self.client.datasets.aggregate.call_args.kwargs["filter"]
        self.assertEqual(sent, {"type": "rule", "field": "a", "operator": "=", "value": 1})

    def test_a_mongo_filter_is_refused_without_a_round_trip(self):
        with self.assertRaises(ToolArgumentError):
            aggregate_dataset(self.client, 7, filter={"a": {"$eq": 1}})
        self.client.datasets.aggregate.assert_not_called()


class QueryFilterTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.datasets.query.return_value = {
            "type": "FeatureCollection",
            "features": [],
        }

    def test_a_flat_filter_in_the_query_dsl_is_typed(self):
        query_dataset(
            self.client,
            7,
            {"filter": {"field": "name", "operator": "$ilike", "value": "%a%"}},
            return_geometry=False,
        )
        sent = self.client.datasets.query.call_args.args[1]
        self.assertEqual(
            sent["filter"],
            {"type": "rule", "field": "name", "operator": "$ilike", "value": "%a%"},
        )

    def test_a_mongo_filter_in_the_query_dsl_is_refused(self):
        with self.assertRaises(ToolArgumentError):
            query_dataset(self.client, 7, {"filter": {"name": {"$eq": "a"}}})
        self.client.datasets.query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
