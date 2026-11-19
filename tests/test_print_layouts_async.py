"""Async print-layout manager (slice 014) — parity with the sync suite."""

import base64
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from geopack_sdk.async_print_layouts import AsyncPrintLayoutManager

LAYOUT = {
    "id": 8,
    "name": "A4 landscape",
    "layoutJson": {"page": {"size": "A4"}},
}


class AsyncPrintLayoutManagerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.thumbnail_dir = tempfile.mkdtemp()
        self.client = AsyncMock()
        self.client.base_url = "http://localhost:3000/api"
        self.client.auth.token = "test-token"
        self.manager = AsyncPrintLayoutManager(self.client)

    def tearDown(self):
        for name in os.listdir(self.thumbnail_dir):
            os.remove(os.path.join(self.thumbnail_dir, name))
        os.rmdir(self.thumbnail_dir)

    async def test_list_uses_limit_offset(self):
        self.client.get.return_value = {"items": [LAYOUT], "total": 1}

        await self.manager.list(page=2, page_size=5, isTemplate=True)

        params = self.client.get.call_args.kwargs["params"]
        self.assertEqual(params, {"limit": 5, "offset": 5, "isTemplate": True})

    async def test_crud_paths(self):
        self.client.get.return_value = LAYOUT
        layout = await self.manager.get(8)
        self.assertEqual(layout.raw["layoutJson"]["page"]["size"], "A4")

        self.client.post.return_value = {"id": 8}
        created = await self.manager.create({"name": "A4 landscape"})
        self.assertEqual(created.id, 8)

        self.client.put.return_value = {"id": 8, "updated": True}
        self.assertTrue((await self.manager.update(8, {"name": "A3"}))["updated"])

        self.client.delete.return_value = {"id": 8, "deleted": True}
        self.assertTrue((await self.manager.delete(8))["deleted"])

    async def test_base64_thumbnail_upload(self):
        raw = b"\x89PNG"
        path = os.path.join(self.thumbnail_dir, "thumb.png")
        with open(path, "wb") as handle:
            handle.write(raw)
        self.client.post.return_value = {"message": "ok"}

        await self.manager.upload_thumbnail(8, path)

        self.client.post.assert_awaited_once_with(
            "/print-layouts/8/thumbnail",
            json={"thumbnailBase64": base64.b64encode(raw).decode("ascii")},
        )

    async def test_thumbnail_download_and_mint(self):
        response = MagicMock()
        response.status_code = 200
        response.is_success = True
        response.content = b"jpeg"
        response.headers = {"Content-Type": "image/jpeg"}
        self.client.session.get.return_value = response

        target = os.path.join(self.thumbnail_dir, "out.jpg")
        saved = await self.manager.get_thumbnail(8, target)
        self.assertTrue(os.path.isfile(saved.savedPath))

        self.client.get.return_value = {"url": "http://x/media/y?t=1", "expiresAt": "x"}
        minted = await self.manager.get_thumbnail_access_url(8)
        self.assertIn("/media/", minted.url)

    async def test_acls(self):
        self.client.get.return_value = [{"id": 1}]
        self.assertEqual(len(await self.manager.get_acls(8)), 1)

        self.client.post.return_value = [{"id": 2}]
        await self.manager.create_acls(8, principals=[{"type": "USER", "id": 1}], permissions=["print_layout:read"])
        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["permissions"],
            ["print_layout:read"],
        )

        await self.manager.delete_acl(8, 2)
        self.client.delete.assert_awaited_once_with("/print-layouts/8/acl/2")


if __name__ == "__main__":
    unittest.main()
