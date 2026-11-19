"""Print-layout template registry (slice 014 §1.3 / §0).

A layout is a stored template definition consumed by the FRONTEND renderer.
These tests pin the wire quirks: ``limit``/``offset`` paging, minimal create /
update / delete answers, the JSON-base64 thumbnail upload, and thumbnail reads
that land on disk.
"""

import base64
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import GeopackAPIError
from geopack_sdk.print_layouts import PrintLayoutManager

LAYOUT = {
    "id": 8,
    "name": "A4 landscape",
    "layoutJson": {
        "page": {"size": "A4", "orientation": "landscape"},
        "elements": [{"id": "title-1", "type": "text", "text": "Report"}],
    },
    "isTemplate": True,
    "createdAt": "2026-11-19T08:00:00.000Z",
    "updatedAt": "2026-11-19T08:10:00.000Z",
}


class PrintLayoutManagerTest(unittest.TestCase):
    def setUp(self):
        self.thumbnail_dir = tempfile.mkdtemp()
        self.client = MagicMock()
        self.client.base_url = "http://localhost:3000/api"
        self.client.auth.token = "test-token"
        self.manager = PrintLayoutManager(self.client)

    def tearDown(self):
        for name in os.listdir(self.thumbnail_dir):
            os.remove(os.path.join(self.thumbnail_dir, name))
        os.rmdir(self.thumbnail_dir)

    def test_list_derives_limit_and_offset(self):
        self.client.get.return_value = {
            "items": [LAYOUT],
            "total": 1,
            "totalPages": 1,
            "currentPage": 3,
        }

        result = self.manager.list(page=3, page_size=10, ownerId=5, isTemplate=True)

        params = self.client.get.call_args.kwargs["params"]
        self.assertEqual(params["limit"], 10)
        self.assertEqual(params["offset"], 20)
        self.assertEqual(params["ownerId"], 5)
        self.assertTrue(params["isTemplate"])
        self.assertEqual(result["items"][0]["name"], "A4 landscape")

    def test_list_skips_none_filters(self):
        self.client.get.return_value = {}

        self.manager.list(q="A4", orgId=None, wgId=None)

        params = self.client.get.call_args.kwargs["params"]
        self.assertEqual(params, {"limit": 20, "offset": 0, "q": "A4"})

    def test_create_returns_the_minimal_answer(self):
        self.client.post.return_value = {
            "id": 8,
            "createdAt": LAYOUT["createdAt"],
            "updatedAt": LAYOUT["updatedAt"],
        }
        payload = {"name": "A4 landscape", "layoutJson": LAYOUT["layoutJson"]}

        created = self.manager.create(payload)

        self.client.post.assert_called_once_with("/print-layouts", json=payload)
        self.assertEqual(created.id, 8)
        # The create answer carries no definition; callers re-fetch.
        self.assertNotIn("layoutJson", created.raw)

    def test_get_returns_the_stored_definition_verbatim(self):
        self.client.get.return_value = LAYOUT

        layout = self.manager.get(8)

        self.client.get.assert_called_once_with("/print-layouts/8")
        self.assertEqual(
            layout.raw["layoutJson"]["elements"][0],
            {"id": "title-1", "type": "text", "text": "Report"},
        )

    def test_update_and_delete_answer_their_acks(self):
        self.client.put.return_value = {"id": 8, "updated": True}
        self.assertEqual(
            self.manager.update(8, {"name": "A3 landscape"}),
            {"id": 8, "updated": True},
        )
        self.client.put.assert_called_once_with(
            "/print-layouts/8", json={"name": "A3 landscape"}
        )

        self.client.delete.return_value = {"id": 8, "deleted": True}
        self.assertEqual(self.manager.delete(8), {"id": 8, "deleted": True})
        self.client.delete.assert_called_once_with("/print-layouts/8")

    def test_upload_thumbnail_base64_encodes_a_local_file(self):
        raw = b"\x89PNG-layout-thumb"
        path = os.path.join(self.thumbnail_dir, "thumb.png")
        with open(path, "wb") as handle:
            handle.write(raw)
        self.client.post.return_value = {"message": "Thumbnail updated"}

        ack = self.manager.upload_thumbnail(8, path)

        self.client.post.assert_called_once_with(
            "/print-layouts/8/thumbnail",
            json={"thumbnailBase64": base64.b64encode(raw).decode("ascii")},
        )
        self.assertEqual(ack["message"], "Thumbnail updated")

    def test_upload_thumbnail_passes_an_already_encoded_payload(self):
        self.client.post.return_value = {}

        self.manager.upload_thumbnail(8, thumbnail_base64="QUJD")

        self.client.post.assert_called_once_with(
            "/print-layouts/8/thumbnail", json={"thumbnailBase64": "QUJD"}
        )

    def test_upload_thumbnail_requires_exactly_one_source(self):
        with self.assertRaises(ValueError):
            self.manager.upload_thumbnail(8)
        with self.assertRaises(ValueError):
            self.manager.upload_thumbnail(8, "a.png", thumbnail_base64="QUJD")
        self.client.post.assert_not_called()

    def test_get_thumbnail_lands_on_disk(self):
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.content = b"jpeg-bytes"
        response.headers = {"Content-Type": "image/jpeg"}
        self.client.session.get.return_value = response

        target = os.path.join(self.thumbnail_dir, "layout.jpg")
        saved = self.manager.get_thumbnail(8, target)

        self.client.session.get.assert_called_once_with(
            "http://localhost:3000/api/print-layouts/8/thumbnail",
            headers={"Authorization": "Bearer test-token"},
            timeout=60,
        )
        self.assertEqual(saved.savedPath, os.path.abspath(target))
        self.assertEqual(saved.sizeBytes, len(b"jpeg-bytes"))

    def test_missing_thumbnail_is_a_404(self):
        response = MagicMock()
        response.status_code = 404
        response.ok = False
        self.client.session.get.return_value = response

        with self.assertRaises(GeopackAPIError):
            self.manager.get_thumbnail(8)

    def test_access_url_mint_and_acls(self):
        self.client.get.side_effect = [
            {"url": "http://localhost:3000/api/media/layout-thumb?t=1", "expiresAt": "x"},
            [{"id": 2, "permission": "print_layout:read"}],
        ]

        minted = self.manager.get_thumbnail_access_url(8)
        self.assertIn("/api/media/", minted.url)

        rows = self.manager.get_acls(8)
        self.assertEqual(rows[0]["permission"], "print_layout:read")

        self.client.post.return_value = [{"id": 3}]
        self.manager.create_acls(
            8, principals=[{"type": "WORKGROUP", "id": 2}], permissions=["print_layout:read"]
        )
        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["principals"], [{"type": "WORKGROUP", "id": 2}])

        self.manager.delete_acl(8, 3)
        self.client.delete.assert_called_once_with("/print-layouts/8/acl/3")

    def test_no_generation_surface_exists(self):
        verbs = ("render_", "export_", "generate_", "print_", "compose_", "rasterize_", "pdf_")
        public = [name for name in dir(self.manager) if not name.startswith("_")]
        self.assertEqual([name for name in public if name.startswith(verbs)], [])


if __name__ == "__main__":
    unittest.main()
