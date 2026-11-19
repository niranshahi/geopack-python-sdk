"""Async field-level access and legacy feature CRUD — parity with the sync lane."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from geopack_sdk.async_datasets import AsyncDatasetManager
from geopack_sdk.exceptions import FieldPolicyError, GeopackAPIError
from geopack_sdk.models import DatasetAcl, FieldRestriction

from tests.test_field_access import ACL_ENTRY, RESTRICTIONS, UPSERTED


class AsyncFieldAccessTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.get = AsyncMock()
        self.client.post = AsyncMock()
        self.client.put = AsyncMock()
        self.client.delete = AsyncMock()
        self.client.patch = AsyncMock()
        self.manager = AsyncDatasetManager(self.client)

    async def test_list_and_upsert_restrictions(self):
        self.client.get.return_value = RESTRICTIONS
        restrictions = await self.manager.get_field_restrictions(7)
        self.assertEqual(restrictions[0].principal_type, "GROUP")

        self.client.put.return_value = UPSERTED
        restriction = await self.manager.upsert_field_restrictions(
            7, "GROUP", 12, ["owner_email"]
        )
        self.assertIsInstance(restriction, FieldRestriction)
        self.assertEqual(
            self.client.put.call_args.kwargs["json"]["principalType"], "GROUP"
        )

    async def test_delete_uses_the_query_string(self):
        self.client.delete.return_value = {"deleted": 1}

        await self.manager.delete_field_restrictions(7, "GROUP", 12)

        self.assertEqual(
            self.client.delete.call_args.kwargs["params"],
            {"principalType": "GROUP", "principalId": 12},
        )

    async def test_protected_field_error_is_typed(self):
        self.client.put.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "code": "FIELD_POLICY_PROTECTED_FIELD",
                "message": "Field 'gid' cannot be denied.",
            },
        )

        with self.assertRaises(FieldPolicyError):
            await self.manager.upsert_field_restrictions(7, "GROUP", 12, ["gid"])

    async def test_row_filter_patch_and_clear(self):
        self.client.patch.return_value = ACL_ENTRY
        acl = await self.manager.update_acl_row_filter(7, 31, {"field": "status"})
        self.assertIsInstance(acl, DatasetAcl)

        await self.manager.update_acl_row_filter(7, 31, None)
        self.assertEqual(
            self.client.patch.call_args.kwargs["json"], {"rowFilter": None}
        )

    async def test_legacy_feature_crud(self):
        self.client.post.return_value = {"ids": [101]}
        created = await self.manager.create_feature(7, {"type": "Feature"})
        self.assertEqual(created, {"ids": [101]})
        self.assertEqual(self.client.post.call_args.kwargs["json"], [{"type": "Feature"}])

        self.client.put.return_value = None
        await self.manager.update_feature(7, 101, {"type": "Feature", "id": 101})
        self.assertEqual(
            self.client.put.call_args.args[0], "/datasets/7/features/101"
        )

        await self.manager.delete_feature(7, 101)
        self.assertEqual(
            self.client.delete.call_args.args[0], "/datasets/7/features/101"
        )

    async def test_apply_feature_edits_sends_empty_lists_not_null(self):
        self.client.post.return_value = {"added": 0, "updated": 0, "deleted": 0}

        await self.manager.apply_feature_edits(7)

        self.assertEqual(
            self.client.post.call_args.kwargs["json"],
            {"adds": [], "updates": [], "deletes": []},
        )


if __name__ == "__main__":
    unittest.main()
