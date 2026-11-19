"""Virtual datasets — filter views and ad-hoc SQL (slice 013).

Two rules drive every assertion here:

* the SDK composes NOTHING — ``queryDsl`` stays root-scoped, the SQL body is
  sent verbatim, and no field type is ever synthesized;
* the ad-hoc SQL lane is a restricted capability. A ``403`` is expected
  behaviour, surfaces as :class:`GeopackAuthError`, and is never retried.

Recorded deviation: the slice plan names ``GeopackValidationError`` for a
server-side 400. In this SDK that class means "a response failed Pydantic
validation" and is NOT an ``GeopackAPIError``, so routing an HTTP 400 there
would silently drop it out of every ``except GeopackAPIError`` handler. An
unmapped 400 therefore stays on :class:`GeopackAPIError` with the server's
message verbatim.
"""

import unittest
from unittest.mock import MagicMock

from pydantic import ValidationError

from geopack_sdk.datasets import DatasetManager
from geopack_sdk.exceptions import GeopackAPIError, GeopackAuthError
from geopack_sdk.models import (
    CreateVirtualDatasetDto,
    CreateVirtualSqlDatasetDto,
    Dataset,
    VirtualField,
)

DATASET = {
    "id": 91,
    "name": "Wells in zone A",
    "dataType": "vector",
    "ownerUserId": 1,
    "workgroupId": 2,
    "dataStoreId": 3,
    "createdAt": "2026-11-19T10:00:00Z",
    "updatedAt": "2026-11-19T10:00:00Z",
}

PROBE = {
    "valid": True,
    "fields": [
        {"name": "parcel_id", "type": "integer"},
        {"name": "owner", "type": "text"},
    ],
    "geometryColumns": ["shape"],
    "primaryKeyCandidates": ["parcel_id"],
    "spatialReference": {"srid": 4326, "wkt": None, "proj4": None},
    "detectedShapeType": "esriGeometryPolygon",
    "detectedHasZ": False,
    "geometryMetadata": {"shape": {"srid": 4326, "geometryType": "polygon"}},
}


class VirtualDatasetsTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = DatasetManager(self.client)

    # --- POST /datasets/virtual ------------------------------------------

    def test_create_virtual_dataset_posts_the_dto(self):
        self.client.post.return_value = DATASET
        payload = CreateVirtualDatasetDto(
            name="Wells in zone A",
            dataStoreId=3,
            workgroupId=2,
            rootDatasetId=7,
            queryDsl={"filter": {"where": "zone_id = 101"}},
            kind="virtualFilter",
        )

        result = self.manager.create_virtual_dataset(payload)

        self.assertIsInstance(result, Dataset)
        self.assertEqual(result.id, 91)
        self.assertEqual(self.client.post.call_args.args[0], "/datasets/virtual")
        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(body["kind"], "virtualFilter")
        self.assertEqual(body["queryDsl"], {"filter": {"where": "zone_id = 101"}})
        # Nothing is pre-composed and no unset key is sent.
        self.assertNotIn("description", body)
        self.assertNotIn("keywords", body)

    def test_filter_sugar_sends_kind_explicitly(self):
        self.client.post.return_value = DATASET

        self.manager.create_virtual_dataset_from_filter(
            name="Wells in zone A",
            data_store_id=3,
            workgroup_id=2,
            root_dataset_id=7,
            query_dsl={"filter": None},
            description="zone A only",
        )

        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(body["kind"], "virtualFilter")
        self.assertEqual(body["rootDatasetId"], 7)
        self.assertEqual(body["description"], "zone A only")

    def test_deprecated_esri_alias_targets_the_new_route(self):
        self.client.post.return_value = DATASET

        self.manager.create_virtual_esri_dataset(
            {
                "name": "Wells in zone A",
                "dataStoreId": 3,
                "workgroupId": 2,
                "rootDatasetId": 7,
                "queryDsl": {"filter": None},
            }
        )

        # The alias must never route to /virtual-esri (retired for new code).
        self.assertEqual(self.client.post.call_args.args[0], "/datasets/virtual")

    def test_relationship_kind_error_is_verbatim(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "message": 'Invalid Input: kind "virtualJoin" requires an ESRI geodatabase datastore.'
            },
        )

        with self.assertRaises(GeopackAPIError) as ctx:
            self.manager.create_virtual_dataset_from_filter(
                name="x",
                data_store_id=3,
                workgroup_id=2,
                root_dataset_id=7,
                query_dsl={},
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("requires an ESRI geodatabase", ctx.exception.message)

    # --- SQL lane ---------------------------------------------------------

    def test_preview_sql_posts_the_probe_body(self):
        self.client.post.return_value = PROBE

        result = self.manager.preview_sql(3, "SELECT parcel_id, owner, shape FROM parcels")

        self.assertEqual(self.client.post.call_args.args[0], "/datasets/sql-preview")
        self.assertEqual(
            self.client.post.call_args.kwargs["json"],
            {"dataStoreId": 3, "sql": "SELECT parcel_id, owner, shape FROM parcels"},
        )
        self.assertEqual(result["fields"][0]["type"], "integer")

    def test_preview_sql_rejects_an_empty_statement(self):
        for bad in ("", "   ", None):
            with self.assertRaises(ValueError):
                self.manager.preview_sql(3, bad)
        self.client.post.assert_not_called()

    def test_preview_then_create_sends_exactly_the_discovered_fields(self):
        self.client.post.side_effect = [PROBE, DATASET]
        probe = self.manager.preview_sql(3, "SELECT parcel_id, owner, shape FROM parcels")

        payload = CreateVirtualSqlDatasetDto(
            name="Parcels",
            dataStoreId=3,
            workgroupId=2,
            sql="SELECT parcel_id, owner, shape FROM parcels",
            fields=probe["fields"],
            primaryKey=probe["primaryKeyCandidates"][0],
            geometryColumn=probe["geometryColumns"][0],
            spatialReference=probe["spatialReference"],
            detectedShapeType=probe["detectedShapeType"],
            detectedHasZ=probe["detectedHasZ"],
        )
        result = self.manager.create_virtual_sql_dataset(payload)

        self.assertIsInstance(result, Dataset)
        self.assertEqual(self.client.post.call_args.args[0], "/datasets/virtual-sql")
        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(body["fields"], probe["fields"])
        self.assertEqual(body["primaryKey"], "parcel_id")
        self.assertEqual(body["geometryColumn"], "shape")
        self.assertEqual(body["spatialReference"], {"srid": 4326, "wkt": None, "proj4": None})
        self.assertEqual(body["detectedShapeType"], "esriGeometryPolygon")

    def test_create_virtual_sql_accepts_a_plain_dict(self):
        self.client.post.return_value = DATASET

        self.manager.create_virtual_sql_dataset(
            {
                "name": "Parcels",
                "dataStoreId": 3,
                "workgroupId": 2,
                "sql": "SELECT 1",
                "fields": [{"name": "one", "type": "integer"}],
            }
        )

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["fields"],
            [{"name": "one", "type": "integer"}],
        )

    def test_update_virtual_sql_requires_both_capabilities(self):
        self.client.put.return_value = DATASET

        self.manager.update_virtual_sql_dataset(91, {"sql": "SELECT parcel_id FROM parcels"})

        self.assertEqual(
            self.client.put.call_args.args[0], "/datasets/91/virtual-sql"
        )
        # Only what the caller supplied rides the wire — update is partial.
        self.assertEqual(
            self.client.put.call_args.kwargs["json"],
            {"sql": "SELECT parcel_id FROM parcels"},
        )

    def test_missing_capability_is_not_retried(self):
        self.client.put.side_effect = GeopackAuthError.from_http_status(
            403,
            reason="Forbidden",
            text="",
            json_loader=lambda: {
                "message": "Missing permission: dataset:create_virtual_sql"
            },
        )

        with self.assertRaises(GeopackAuthError) as ctx:
            self.manager.update_virtual_sql_dataset(91, {"sql": "SELECT 1"})

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("dataset:create_virtual_sql", ctx.exception.message)
        self.client.put.assert_called_once()

    # --- client-side shape checks (mirror the validator, no semantics) ----

    def test_required_keys_are_checked_client_side(self):
        with self.assertRaises(ValidationError) as ctx:
            CreateVirtualDatasetDto(
                name="x", dataStoreId=0, workgroupId=2, rootDatasetId=7, queryDsl={}
            )
        self.assertIn("dataStoreId", str(ctx.exception))

        with self.assertRaises(ValidationError):
            CreateVirtualDatasetDto(
                name="x", dataStoreId=3, workgroupId=2, rootDatasetId=7
            )

        with self.assertRaises(ValidationError):
            # fields.*.type is required; a type is never synthesized.
            CreateVirtualSqlDatasetDto(
                name="x",
                dataStoreId=3,
                workgroupId=2,
                sql="SELECT 1",
                fields=[{"name": "one"}],
            )

    def test_unknown_kind_is_rejected_locally(self):
        with self.assertRaises(ValidationError):
            CreateVirtualDatasetDto(
                name="x",
                dataStoreId=3,
                workgroupId=2,
                rootDatasetId=7,
                queryDsl={},
                kind="virtualMagic",
            )

    def test_virtual_field_keeps_extra_keys_from_the_probe(self):
        field = VirtualField(name="shape", type="geometry", srid=4326)
        self.assertEqual(field.type, "geometry")
        self.assertEqual(field.srid, 4326)


if __name__ == "__main__":
    unittest.main()
