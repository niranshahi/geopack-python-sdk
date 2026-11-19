"""DataStore relationship catalog CRUD (slice 015).

Authored (logical) relationships live in the DataStore's ``gp_catalog``, not in
the database. Every route answers the controller's ``{success, data}``
envelope; the manager returns ``data``. A ``409`` (catalog unavailable /
conflict) and a ``404`` on a native relationship delete are surfaced verbatim —
never retried, never swallowed.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.datastores import DataStoreManager
from geopack_sdk.exceptions import (
    GeopackAPIError,
    RelationshipCatalogUnavailable,
)


CATALOG = {
    "dataStoreId": 3,
    "datastoreUuid": "ds-3",
    "catalogNamespace": "gp_catalog",
    "archiveDefinitions": [],
    "relationships": [
        {
            "id": "rel-1",
            "name": "wells_to_zones",
            "cardinality": "manyToOne",
            "relationshipKind": "logical",
            "managementMode": "logical",
            "originDatasetId": 7,
            "destinationDatasetId": 8,
            "keys": [
                {"side": "origin", "ordinal": 1, "fieldName": "zone_id"},
                {"side": "destination", "ordinal": 1, "fieldName": "id"},
            ],
        }
    ],
}

DESCRIPTOR = CATALOG["relationships"][0]

PAYLOAD = {
    "originDatasetId": 7,
    "destinationDatasetId": 8,
    "name": "wells_to_zones",
    "cardinality": "manyToOne",
    "relationshipKind": "logical",
    "managementMode": "logical",
    "keys": [
        {"side": "origin", "ordinal": 1, "fieldName": "zone_id"},
        {"side": "destination", "ordinal": 1, "fieldName": "id"},
    ],
}


class DataStoreRelationshipsTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = DataStoreManager(self.client)

    def test_get_relationships_unwraps_the_envelope(self):
        self.client.get.return_value = {"success": True, "data": CATALOG}

        snapshot = self.manager.get_relationships(3)

        self.client.get.assert_called_once_with("/datastores/3/relationships")
        self.assertEqual(snapshot["datastoreUuid"], "ds-3")
        self.assertNotIn("success", snapshot)
        self.assertEqual(snapshot["relationships"][0]["name"], "wells_to_zones")

    def test_a_bare_payload_is_passed_through(self):
        self.client.get.return_value = CATALOG

        self.assertEqual(self.manager.get_relationships(3)["dataStoreId"], 3)

    def test_create_relationship_posts_the_body_verbatim(self):
        self.client.post.return_value = {"success": True, "data": DESCRIPTOR}

        created = self.manager.create_relationship(3, PAYLOAD)

        self.client.post.assert_called_once_with(
            "/datastores/3/relationships", json=PAYLOAD
        )
        self.assertEqual(created["id"], "rel-1")

    def test_update_relationship_targets_the_uuid(self):
        self.client.put.return_value = {"success": True, "data": DESCRIPTOR}

        updated = self.manager.update_relationship(3, "rel-1", PAYLOAD)

        self.client.put.assert_called_once_with(
            "/datastores/3/relationships/rel-1", json=PAYLOAD
        )
        self.assertEqual(updated["name"], "wells_to_zones")

    def test_delete_relationship_targets_the_uuid(self):
        self.client.delete.return_value = {"success": True, "data": {"id": "rel-1"}}

        deleted = self.manager.delete_relationship(3, "rel-1")

        self.client.delete.assert_called_once_with("/datastores/3/relationships/rel-1")
        self.assertEqual(deleted["id"], "rel-1")

    def test_409_conflict_is_surfaced_verbatim(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            409,
            reason="Conflict",
            text="",
            json_loader=lambda: {
                "success": False,
                "error": {
                    "code": "RELATIONSHIP_CATALOG_UNAVAILABLE",
                    "message": "Catalog is busy",
                },
            },
        )

        with self.assertRaises(RelationshipCatalogUnavailable) as ctx:
            self.manager.create_relationship(3, PAYLOAD)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "RELATIONSHIP_CATALOG_UNAVAILABLE")
        # One attempt: a conflict is a state, not a transient error.
        self.assertEqual(self.client.post.call_count, 1)

    def test_404_on_a_native_relationship_delete_is_not_retried(self):
        self.client.delete.side_effect = GeopackAPIError.from_http_status(
            404,
            reason="Not Found",
            text="",
            json_loader=lambda: {
                "success": False,
                "error": {"message": "Relationship not found or read-only"},
            },
        )

        with self.assertRaises(GeopackAPIError) as ctx:
            self.manager.delete_relationship(3, "native-rel")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(self.client.delete.call_count, 1)


if __name__ == "__main__":
    unittest.main()
