"""Field-level access and legacy feature CRUD (slice 012 §2.2/§2.3).

Two rules are pinned here:

* a field restriction SUBTRACTS fields and its DELETE carries the principal in
  the QUERY STRING (the server's primary form);
* the legacy feature lane is relationship-blind — its contract tests only
  assert the body keys and the response counts.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.datasets import DatasetManager
from geopack_sdk.exceptions import FieldPolicyError, GeopackAPIError, DatasetReadOnly
from geopack_sdk.models import DatasetAcl, FieldRestriction

RESTRICTIONS = [
    {
        "id": 5,
        "datasetId": 7,
        "principalType": "GROUP",
        "principalId": 12,
        "deniedFields": ["owner_email", "owner_phone"],
        "updatedAt": "2026-11-18T10:00:00.000Z",
    }
]

UPSERTED = {
    "id": 5,
    "datasetId": 7,
    "principalType": "GROUP",
    "principalId": 12,
    "deniedFields": ["owner_email"],
}

ACL_ENTRY = {
    "id": 31,
    "resourceType": "DATASET",
    "resourceId": 7,
    "principalType": "USER",
    "principalId": 44,
    "permissionId": 3,
    "effect": "Allow",
    "rowFilter": {"field": "status", "op": "eq", "value": "open"},
    "createdAt": "2026-11-01T08:00:00.000Z",
    "updatedAt": "2026-11-18T09:30:00.000Z",
}


class FieldAccessTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = DatasetManager(self.client)

    def test_list_restrictions_returns_deny_overlays(self):
        self.client.get.return_value = RESTRICTIONS

        restrictions = self.manager.get_field_restrictions(7)

        self.client.get.assert_called_once_with("/datasets/7/field-restrictions")
        self.assertEqual(len(restrictions), 1)
        self.assertIsInstance(restrictions[0], FieldRestriction)
        self.assertEqual(restrictions[0].principal_type, "GROUP")
        self.assertEqual(
            restrictions[0].denied_fields, ["owner_email", "owner_phone"]
        )
        self.assertEqual(restrictions[0].dataset_id, 7)

    def test_upsert_sends_the_principal_and_the_full_deny_list(self):
        self.client.put.return_value = UPSERTED

        restriction = self.manager.upsert_field_restrictions(
            7, "GROUP", 12, ["owner_email"]
        )

        endpoint = self.client.put.call_args.args[0]
        body = self.client.put.call_args.kwargs["json"]
        self.assertEqual(endpoint, "/datasets/7/field-restrictions")
        self.assertEqual(
            body,
            {
                "principalType": "GROUP",
                "principalId": 12,
                "deniedFields": ["owner_email"],
            },
        )
        self.assertEqual(restriction.denied_fields, ["owner_email"])

    def test_upsert_rejects_an_unknown_principal_type_locally(self):
        with self.assertRaises(ValueError):
            self.manager.upsert_field_restrictions(7, "ROLE", 12, ["x"])

        self.client.put.assert_not_called()

    def test_delete_puts_the_principal_in_the_query_string(self):
        self.client.delete.return_value = {"deleted": 1}

        result = self.manager.delete_field_restrictions(7, "GROUP", 12)

        endpoint = self.client.delete.call_args.args[0]
        params = self.client.delete.call_args.kwargs["params"]
        self.assertEqual(endpoint, "/datasets/7/field-restrictions")
        self.assertEqual(params, {"principalType": "GROUP", "principalId": 12})
        self.assertEqual(result, {"deleted": 1})

    def test_delete_of_a_missing_overlay_is_not_an_error(self):
        self.client.delete.return_value = {"deleted": 0}

        self.assertEqual(self.manager.delete_field_restrictions(7, "USER", 44), {"deleted": 0})

    def test_a_protected_field_is_a_coded_field_policy_error(self):
        self.client.put.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "code": "FIELD_POLICY_PROTECTED_FIELD",
                "message": "Field 'gid' cannot be denied.",
            },
        )

        with self.assertRaises(FieldPolicyError) as caught:
            self.manager.upsert_field_restrictions(7, "GROUP", 12, ["gid"])

        self.assertEqual(caught.exception.code, "FIELD_POLICY_PROTECTED_FIELD")
        self.assertEqual(caught.exception.status_code, 400)

    def test_row_filter_patch_sends_the_dsl_node(self):
        self.client.patch.return_value = ACL_ENTRY
        row_filter = {"field": "status", "op": "eq", "value": "open"}

        acl = self.manager.update_acl_row_filter(7, 31, row_filter)

        endpoint = self.client.patch.call_args.args[0]
        self.assertEqual(endpoint, "/datasets/7/acl/31/row-filter")
        self.assertEqual(self.client.patch.call_args.kwargs["json"], {"rowFilter": row_filter})
        self.assertIsInstance(acl, DatasetAcl)
        self.assertEqual(acl.rowFilter, row_filter)

    def test_row_filter_none_clears_with_a_null_value(self):
        self.client.patch.return_value = {**ACL_ENTRY, "rowFilter": None}

        self.manager.update_acl_row_filter(7, 31, None)

        # The key must be PRESENT with a null value: an absent key means
        # "unchanged" to the server.
        self.assertEqual(
            self.client.patch.call_args.kwargs["json"], {"rowFilter": None}
        )

    def test_a_malformed_row_filter_keeps_the_server_message(self):
        self.client.patch.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {"message": "Invalid rowFilter: unknown field status_x"},
        )

        with self.assertRaises(GeopackAPIError) as caught:
            self.manager.update_acl_row_filter(7, 31, {"field": "status_x"})

        self.assertEqual(
            caught.exception.message, "Invalid rowFilter: unknown field status_x"
        )


class LegacyFeatureCrudTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = DatasetManager(self.client)

    def test_create_feature_wraps_one_feature_in_an_array(self):
        self.client.post.return_value = {"ids": [101]}
        feature = {"type": "Feature", "properties": {"name": "A"}}

        result = self.manager.create_feature(7, feature)

        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/7/features"
        )
        self.assertEqual(self.client.post.call_args.kwargs["json"], [feature])
        self.assertEqual(result, {"ids": [101]})

    def test_create_feature_rejects_an_empty_body_before_the_request(self):
        with self.assertRaises(ValueError):
            self.manager.create_feature(7, {})

        self.client.post.assert_not_called()

    def test_update_feature_puts_the_full_feature(self):
        self.client.put.return_value = None
        feature = {"type": "Feature", "id": 101, "properties": {"name": "B"}}

        result = self.manager.update_feature(7, 101, feature)

        self.assertEqual(
            self.client.put.call_args.args[0], "/datasets/7/features/101"
        )
        self.assertEqual(self.client.put.call_args.kwargs["json"], feature)
        self.assertEqual(result, {})

    def test_delete_feature_calls_the_feature_path(self):
        self.manager.delete_feature(7, 101)

        self.assertEqual(
            self.client.delete.call_args.args[0], "/datasets/7/features/101"
        )

    def test_apply_feature_edits_sends_the_three_body_keys(self):
        self.client.post.return_value = {"added": 1, "updated": 2, "deleted": 0}

        counts = self.manager.apply_feature_edits(
            7,
            adds=[{"type": "Feature"}],
            updates=[{"type": "Feature", "id": 1}],
            deletes=[2],
        )

        endpoint = self.client.post.call_args.args[0]
        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(endpoint, "/datasets/7/features/applyEdits")
        self.assertEqual(set(body), {"adds", "updates", "deletes"})
        self.assertEqual(body["adds"], [{"type": "Feature"}])
        self.assertEqual(body["deletes"], [2])
        self.assertEqual(counts, {"added": 1, "updated": 2, "deleted": 0})

    def test_apply_feature_edits_sends_empty_lists_not_null(self):
        self.client.post.return_value = {"added": 0, "updated": 0, "deleted": 0}

        self.manager.apply_feature_edits(7)

        self.assertEqual(
            self.client.post.call_args.kwargs["json"],
            {"adds": [], "updates": [], "deletes": []},
        )

    def test_a_read_only_dataset_is_its_own_error(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            423,
            reason="Locked",
            text="",
            json_loader=lambda: {
                "code": "DATASET_READ_ONLY",
                "message": "Dataset is read-only.",
            },
        )

        with self.assertRaises(DatasetReadOnly):
            self.manager.create_feature(7, {"type": "Feature"})


if __name__ == "__main__":
    unittest.main()
