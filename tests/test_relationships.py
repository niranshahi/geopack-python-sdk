"""Relationships, schema preview, column bounds, access context (slice 011).

The SDK must not re-derive any scope server-side logic here: relationships come
from the catalog, related records from the navigation lane, and the access
context is returned as an opaque authoritative dict.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.datasets import DatasetManager
from geopack_sdk.exceptions import (
    GeopackAPIError,
    QueryValidationError,
    RelationshipCatalogUnavailable,
)
from geopack_sdk.models import (
    ColumnBounds,
    RelatedRecordsResult,
    RelationshipDescriptor,
    SchemaPreview,
)

RELATIONSHIPS = {
    "dataStoreId": 3,
    "dataStoreType": "postgres",
    "relationships": [
        {
            "name": "wells_to_zones",
            "direction": "forward",
            "origin": {"datasetId": 7, "field": "zone_id"},
            "destination": {"datasetId": 8, "field": "id"},
        },
        {
            "relationshipName": "esri_parcels_to_owners",
            "readOnly": True,
            "provider": "esri",
        },
    ],
}

RELATED = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": 11,
            "properties": {"name": "Zone A", "__jct__oid": 55},
        }
    ],
    "metadata": {
        "queryMode": "relate",
        "relationshipName": "wells_to_zones",
        "direction": "forward",
        "sourceDatasetId": 7,
        "relatedDatasetId": 8,
        "count": 1,
        "navigation": "join",
        "groups": {"101": [11]},
    },
}


class RelationshipsTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = DatasetManager(self.client)

    def test_get_relationships_surfaces_read_only_and_keeps_raw(self):
        self.client.get.return_value = RELATIONSHIPS

        relationships = self.manager.get_relationships(7)

        self.client.get.assert_called_once_with("/datasets/7/relationships")
        self.assertEqual(len(relationships), 2)
        self.assertIsInstance(relationships[0], RelationshipDescriptor)
        self.assertEqual(relationships[0].name, "wells_to_zones")
        self.assertFalse(relationships[0].read_only)
        # ESRI entry: read-only is surfaced, never hidden.
        self.assertEqual(relationships[1].name, "esri_parcels_to_owners")
        self.assertTrue(relationships[1].read_only)
        # The escape hatch survives a provider field the model does not know.
        self.assertEqual(relationships[1].raw["provider"], "esri")
        self.assertEqual(relationships[1].raw["name"], "esri_parcels_to_owners")

    def test_relationship_catalog_unavailable_is_a_state(self):
        self.client.get.side_effect = GeopackAPIError.from_http_status(
            409,
            reason="Conflict",
            text="",
            json_loader=lambda: {"code": "RELATIONSHIP_CATALOG_UNAVAILABLE"},
        )

        with self.assertRaises(RelationshipCatalogUnavailable):
            self.manager.get_relationships(7)

    def test_get_related_records_builds_query_options(self):
        self.client.post.return_value = RELATED

        result = self.manager.get_related_records(
            7, "wells_to_zones", ["101"], limit=50, offset=0
        )

        self.assertIsInstance(result, RelatedRecordsResult)
        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/7/related-records"
        )
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["relationshipName"], "wells_to_zones")
        self.assertEqual(payload["direction"], "forward")  # default
        self.assertEqual(payload["originObjectIds"], [101])  # coerced to int
        self.assertEqual(
            payload["queryOptions"],
            {"returnGeometry": True, "limit": 50, "offset": 0},
        )
        # metadata is verbatim; groups is lifted, not flattened.
        self.assertEqual(result.metadata["navigation"], "join")
        self.assertEqual(result.groups, {"101": [11]})
        self.assertEqual(result.count_hint, 1)
        # __jct__* stays beside the target record, never fused into it.
        self.assertEqual(result.features[0]["properties"]["__jct__oid"], 55)

    def test_get_related_records_omits_unset_options(self):
        self.client.post.return_value = RELATED

        self.manager.get_related_records(7, "wells_to_zones", [101], out_srid=3857)

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["queryOptions"],
            {"returnGeometry": True, "outSRID": 3857},
        )

    def test_get_related_records_validates_before_any_call(self):
        cases = (
            ("", [101]),
            ("rel", []),
            ("rel", None),
        )
        for name, oids in cases:
            with self.assertRaises(ValueError):
                self.manager.get_related_records(7, name, oids)
        with self.assertRaises(ValueError):
            self.manager.get_related_records(7, "rel", [1], direction="sideways")
        self.client.post.assert_not_called()

    def test_coded_400_from_the_related_lane_is_typed(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "code": "RELATIONSHIP_QUERY_NOT_FOUND",
                "message": 'Relationship "x" not found on this dataset.',
            },
        )

        with self.assertRaises(QueryValidationError):
            self.manager.get_related_records(7, "x", [1])

    def test_preview_schema_posts_the_dsl_and_returns_it_verbatim(self):
        self.client.post.return_value = {
            "success": True,
            "schema": {
                "fields": [{"name": "well_id"}, {"name": "zone_name"}],
                "geometryType": "point",
                "oidField": "objectid",
                "relationships": [{"name": "wells_to_zones"}],
                "dataType": "vector",
                "title": "Wells ⋈ Zones",
            },
        }

        preview = self.manager.preview_schema(7, {"relationship": {"name": "wells_to_zones"}})

        self.assertIsInstance(preview, SchemaPreview)
        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/7/schema-preview"
        )
        self.assertEqual(
            self.client.post.call_args.kwargs["json"],
            {"queryDsl": {"relationship": {"name": "wells_to_zones"}}},
        )
        self.assertTrue(preview.success)
        self.assertEqual(preview.schema.geometry_type, "point")
        self.assertEqual(preview.schema.oid_field, "objectid")
        self.assertEqual(len(preview.schema.relationships), 1)
        self.assertEqual(preview.schema.data_type, "vector")

    def test_preview_schema_requires_a_dsl(self):
        for dsl in (None, {}):
            with self.assertRaises(ValueError):
                self.manager.preview_schema(7, dsl)
        self.client.post.assert_not_called()

    def test_column_bounds_are_a_thin_passthrough(self):
        self.client.get.return_value = {
            "success": True,
            "data": {"area": {"min": 1.5, "max": 900.0}},
        }

        bounds = self.manager.get_column_bounds(7)

        self.client.get.assert_called_once_with("/datasets/7/column-bounds")
        self.assertIsInstance(bounds, ColumnBounds)
        self.assertEqual(bounds.data["area"]["max"], 900.0)
        self.assertEqual(bounds.raw["success"], True)

    def test_access_context_is_opaque(self):
        context = {
            "rowScope": {"filter": None, "rlsApplied": False},
            "fields": {"area": {"view": True, "edit": False}},
            "canEdit": False,
        }
        self.client.get.return_value = context

        result = self.manager.get_access_context(7)

        self.client.get.assert_called_once_with("/datasets/7/access-context")
        self.assertEqual(result, context)


if __name__ == "__main__":
    unittest.main()
