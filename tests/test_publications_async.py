"""Async publication manager (slice 014) — parity with the sync suite."""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_publications import AsyncPublicationManager
from geopack_sdk.exceptions import GeopackAPIError, PublicationStateConflict

PUBLICATION = {
    "id": 41,
    "datasetId": 7,
    "protocol": "wms",
    "status": "draft",
}


class AsyncPublicationManagerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncPublicationManager(self.client)

    async def test_dataset_mount_create_and_list(self):
        self.client.get.return_value = [PUBLICATION]
        rows = await self.manager.list_for_dataset(7)
        self.assertEqual(rows[0].status, "draft")

        self.client.post.return_value = PUBLICATION
        created = await self.manager.create(7, {"protocol": "wms"})
        self.assertEqual(created.id, 41)

        self.client.get.assert_awaited_once_with("/datasets/7/publications")
        self.client.post.assert_awaited_once_with(
            "/datasets/7/publications", json={"protocol": "wms"}
        )

    async def test_lifecycle_transitions_are_single_calls(self):
        self.client.post.side_effect = [
            {**PUBLICATION, "status": "sync_pending"},
            {**PUBLICATION, "status": "disabled"},
            {"publication": PUBLICATION, "taskId": "task-1"},
            {**PUBLICATION, "publicAccessToken": "tok"},
        ]

        self.assertEqual((await self.manager.enable(41)).status, "sync_pending")
        self.assertEqual((await self.manager.disable(41)).status, "disabled")
        self.assertEqual((await self.manager.reconcile(41))["taskId"], "task-1")
        self.assertEqual(
            (await self.manager.rotate_public_token(41)).raw["publicAccessToken"],
            "tok",
        )

        self.assertEqual(self.client.post.await_count, 4)
        self.assertEqual(
            [call.args[0] for call in self.client.post.await_args_list],
            [
                "/publications/41/enable",
                "/publications/41/disable",
                "/publications/41/reconcile",
                "/publications/41/public-token/rotate",
            ],
        )

    async def test_delete_force_and_202(self):
        self.client.delete.return_value = None
        self.assertIsNone(await self.manager.delete(41))

        self.client.delete.return_value = {"status": "deleting"}
        self.assertEqual(await self.manager.delete(41), {"status": "deleting"})

        self.client.delete.return_value = {"id": 41, "deleted": True}
        self.assertTrue((await self.manager.delete(41, force=True))["deleted"])

        self.client.delete.assert_awaited_with("/publications/41/force")

    async def test_style_and_render_scope_lanes(self):
        sld = "<StyledLayerDescriptor/>"
        self.client.post.return_value = {"valid": True, "errors": []}
        self.assertTrue((await self.manager.validate_style(41, sld))["valid"])
        self.client.post.assert_awaited_once_with(
            "/publications/41/style/validate", json={"sld": sld}
        )

        self.client.post.return_value = {"valid": True, "sld": sld}
        await self.manager.preview_style(41, {"style": {"type": "sld", "sld": sld}})
        self.client.post.assert_awaited_with(
            "/publications/41/style/preview", json={"style": {"type": "sld", "sld": sld}}
        )

        self.client.post.return_value = {"scope": "sc", "expiresAt": "x"}
        descriptor = await self.manager.create_render_scope(41, {"ttlSeconds": 300})
        self.assertEqual(descriptor["scope"], "sc")

    async def test_mint_keys_and_missing_url(self):
        self.client.post.return_value = {"scope": "sc", "wmtsUrl": "http://x/wmts?scope=sc"}
        data = await self.manager.mint_wmts_url(41)
        self.assertIn("wmtsUrl", data)

        self.client.post.return_value = {"scope": "sc"}
        with self.assertRaises(GeopackAPIError) as ctx:
            await self.manager.mint_tiles_url(41)
        self.assertEqual(ctx.exception.status_code, 502)

    async def test_state_conflict_maps_to_the_typed_error(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            409,
            reason="Conflict",
            text="",
            json_loader=lambda: {
                "error": {"code": "PUBLICATION_STATE_CONFLICT", "state": "deleting"}
            },
        )

        with self.assertRaises(PublicationStateConflict):
            await self.manager.enable(41)
        self.assertEqual(self.client.post.await_count, 1)


if __name__ == "__main__":
    unittest.main()
