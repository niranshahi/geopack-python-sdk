"""Async saved-map manager (slice 014) — parity with the sync suite."""

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from geopack_sdk.async_maps import AsyncMapManager
from geopack_sdk.exceptions import GeopackAPIError

MAP = {
    "id": 12,
    "name": "Wells overview",
    "details": {"layers": [{"id": "layer-1", "opacity": 0.65}]},
}


class AsyncMapManagerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.thumbnail_dir = tempfile.mkdtemp()
        self.client = AsyncMock()
        self.client.base_url = "http://localhost:3000/api"
        self.client.auth.token = "test-token"
        self.manager = AsyncMapManager(self.client)

    def tearDown(self):
        for name in os.listdir(self.thumbnail_dir):
            os.remove(os.path.join(self.thumbnail_dir, name))
        os.rmdir(self.thumbnail_dir)

    async def test_list_json_encodes_array_filters(self):
        self.client.get.return_value = {"maps": [MAP], "totalCount": 1}

        await self.manager.list(ownerIds=[4], keywords=["wells"], searchQuery="wells")

        params = self.client.get.call_args.kwargs["params"]
        self.assertEqual(json.loads(params["ownerIds"]), [4])
        self.assertEqual(json.loads(params["keywords"]), ["wells"])
        self.assertEqual(params["searchQuery"], "wells")

    async def test_document_crud_hits_the_sync_paths(self):
        self.client.post.return_value = MAP
        created = await self.manager.create({"name": "Wells overview"})
        self.assertEqual(created.id, 12)

        self.client.get.return_value = MAP
        self.assertEqual((await self.manager.get(12)).name, "Wells overview")

        self.client.put.return_value = MAP
        await self.manager.update(12, {"details": {"zoom": 4}})

        await self.manager.delete(12)

        self.client.post.assert_awaited_once_with(
            "/maps", json={"name": "Wells overview"}
        )
        self.client.get.assert_awaited_once_with("/maps/12")
        self.client.put.assert_awaited_once_with("/maps/12", json={"details": {"zoom": 4}})
        self.client.delete.assert_awaited_once_with("/maps/12")

    async def test_thumbnail_download_lands_on_disk(self):
        response = MagicMock()
        response.status_code = 200
        response.is_success = True
        response.content = b"\x89PNG-thumb"
        response.headers = {"Content-Type": "image/png"}
        self.client.session.get.return_value = response

        target = os.path.join(self.thumbnail_dir, "out.png")
        saved = await self.manager.get_thumbnail(12, target)

        self.client.session.get.assert_awaited_once_with(
            "http://localhost:3000/api/maps/12/thumbnail",
            headers={"Authorization": "Bearer test-token"},
            timeout=60,
        )
        self.assertEqual(saved.mimeType, "image/png")
        self.assertTrue(os.path.isfile(target))

    async def test_thumbnail_404_is_an_api_error(self):
        response = MagicMock()
        response.status_code = 404
        response.is_success = False
        self.client.session.get.return_value = response

        with self.assertRaises(GeopackAPIError):
            await self.manager.get_thumbnail(99)

    async def test_multipart_upload_uses_bytes(self):
        path = os.path.join(self.thumbnail_dir, "preview.png")
        with open(path, "wb") as handle:
            handle.write(b"bytes")
        self.client.post.return_value = {"message": "ok"}

        await self.manager.upload_thumbnail(12, path)

        files = self.client.post.call_args.kwargs["files"]
        self.assertEqual(files["thumbnail"][0], "preview.png")
        self.assertEqual(files["thumbnail"][1], b"bytes")

    async def test_mint_and_acls(self):
        self.client.get.side_effect = [
            {"url": "http://localhost:3000/api/media/x?t=1", "expiresAt": "x"},
            [{"id": 1, "permission": "map:read"}],
        ]

        minted = await self.manager.get_thumbnail_access_url(12)
        self.assertIn("/api/media/", minted.url)

        rows = await self.manager.get_acls(12)
        self.assertEqual(rows[0]["permission"], "map:read")

        self.client.post.return_value = [{"id": 2}]
        await self.manager.create_acls(
            12, principals=[{"type": "USER", "id": 7}], permissions=["map:read"]
        )
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["effect"], "Allow")

        await self.manager.delete_acl(12, 2)
        self.client.delete.assert_awaited_once_with("/maps/12/acl/2")


if __name__ == "__main__":
    unittest.main()
