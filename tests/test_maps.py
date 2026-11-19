"""Saved-map control plane (slice 014 §1.1 / §0).

A map is a stored record: a caller-owned document, caller-supplied thumbnail
bytes and an ACL. These tests pin the wire contract — JSON-encoded array
filters, multipart thumbnail upload, thumbnail-to-disk reads (no bytes inside
JSON), bearer-only mint, and the ACL payload — and assert the §0 boundary:
nothing here renders, exports or generates an image.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import GeopackAPIError
from geopack_sdk.maps import MapManager

MAP = {
    "id": 12,
    "name": "Wells overview",
    "details": {
        "view": {"center": [-122.4, 37.8], "zoom": 9},
        "layers": [
            {"id": "layer-1", "type": "feature", "url": "http://x/0", "opacity": 0.65}
        ],
    },
    "createdAt": "2026-11-19T10:00:00.000Z",
    "updatedAt": "2026-11-19T10:05:00.000Z",
}


class MapManagerTest(unittest.TestCase):
    def setUp(self):
        self.thumbnail_dir = tempfile.mkdtemp()
        self.client = MagicMock()
        self.client.base_url = "http://localhost:3000/api"
        self.client.auth.token = "test-token"
        self.manager = MapManager(self.client)
        self.auth = {"Authorization": "Bearer test-token"}

    def tearDown(self):
        for name in os.listdir(self.thumbnail_dir):
            os.remove(os.path.join(self.thumbnail_dir, name))
        os.rmdir(self.thumbnail_dir)

    # --- list / statistics -------------------------------------------------

    def test_list_json_encodes_the_five_array_filters(self):
        self.client.get.return_value = {
            "maps": [MAP],
            "totalCount": 1,
            "totalPages": 1,
            "currentPage": 1,
            "itemsPerPage": 10,
        }

        result = self.manager.list(
            page=2,
            page_size=5,
            organizationIds=[1, 2],
            workgroupIds=[3],
            ownerIds=[4],
            keywords=["wells"],
            bbox=[-123.0, 37.0, -122.0, 38.0],
            searchQuery="wells",
            orderBy="updatedAt",
        )

        params = self.client.get.call_args.kwargs["params"]
        self.assertEqual(params["page"], 2)
        self.assertEqual(params["pageSize"], 5)
        self.assertEqual(json.loads(params["organizationIds"]), [1, 2])
        self.assertEqual(json.loads(params["workgroupIds"]), [3])
        self.assertEqual(json.loads(params["ownerIds"]), [4])
        self.assertEqual(json.loads(params["keywords"]), ["wells"])
        self.assertEqual(json.loads(params["bbox"]), [-123.0, 37.0, -122.0, 38.0])
        self.assertEqual(params["searchQuery"], "wells")
        self.assertEqual(params["orderBy"], "updatedAt")
        self.assertEqual(result["maps"][0]["name"], "Wells overview")

    def test_string_filters_are_not_double_encoded(self):
        self.client.get.return_value = {}

        self.manager.list(keywords="already-encoded")

        params = self.client.get.call_args.kwargs["params"]
        self.assertEqual(params["keywords"], "already-encoded")

    def test_statistics_returns_the_facets(self):
        self.client.get.return_value = {
            "organizations": [{"id": 1, "name": "Org", "count": 2}],
            "owners": [],
            "workgroups": [],
            "keywords": [],
            "dateRange": {"min": None, "max": None},
        }

        facets = self.manager.statistics()

        self.client.get.assert_called_once_with("/maps/statistics")
        self.assertEqual(facets["organizations"][0]["count"], 2)

    # --- document CRUD -----------------------------------------------------

    def test_create_sends_the_document_verbatim(self):
        self.client.post.return_value = MAP

        created = self.manager.create({"name": "Wells overview", "details": {"a": 1}})

        sent = self.client.post.call_args.kwargs["json"]
        self.assertEqual(sent, {"name": "Wells overview", "details": {"a": 1}})
        self.assertEqual(created.id, 12)
        self.assertEqual(created.name, "Wells overview")
        self.assertEqual(created.raw["details"]["layers"][0]["opacity"], 0.65)

    def test_create_rejects_a_non_dict_document(self):
        with self.assertRaises(ValueError):
            self.manager.create(["not", "a", "document"])
        self.client.post.assert_not_called()

    def test_get_and_update_target_the_map(self):
        self.client.get.return_value = MAP
        self.assertEqual(self.manager.get(12).id, 12)

        self.client.put.return_value = MAP
        updated = self.manager.update(12, {"details": {"zoom": 4}})
        self.client.put.assert_called_once_with("/maps/12", json={"details": {"zoom": 4}})
        self.assertEqual(updated.raw["id"], 12)

    def test_delete_is_a_204_no_content(self):
        self.client.delete.return_value = None

        self.assertIsNone(self.manager.delete(12))
        self.client.delete.assert_called_once_with("/maps/12")

    # --- thumbnails --------------------------------------------------------

    def test_upload_thumbnail_is_multipart(self):
        self.client.post.return_value = {"message": "Thumbnail uploaded"}
        path = os.path.join(self.thumbnail_dir, "preview.png")
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG-bytes")

        ack = self.manager.upload_thumbnail(12, path)

        self.assertEqual(ack["message"], "Thumbnail uploaded")
        args, kwargs = self.client.post.call_args
        self.assertEqual(args[0], "/maps/12/thumbnail")
        self.assertIn("thumbnail", kwargs["files"])
        filename, _payload, mimetype = kwargs["files"]["thumbnail"]
        self.assertEqual(filename, "preview.png")
        self.assertEqual(mimetype, "application/octet-stream")

    def test_upload_thumbnail_requires_an_existing_file(self):
        with self.assertRaises(ValueError):
            self.manager.upload_thumbnail(12, os.path.join(self.thumbnail_dir, "missing.png"))
        self.client.post.assert_not_called()

    def test_get_thumbnail_writes_bytes_to_disk_and_never_into_json(self):
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.content = b"\x89PNG-thumb"
        response.headers = {"Content-Type": "image/png; charset=binary"}
        self.client.session.get.return_value = response

        target = os.path.join(self.thumbnail_dir, "out.png")
        saved = self.manager.get_thumbnail(12, target)

        self.client.session.get.assert_called_once_with(
            "http://localhost:3000/api/maps/12/thumbnail",
            headers=self.auth,
            timeout=60,
        )
        self.assertEqual(saved.savedPath, os.path.abspath(target))
        self.assertEqual(saved.mimeType, "image/png")
        self.assertEqual(saved.sizeBytes, len(b"\x89PNG-thumb"))
        with open(target, "rb") as handle:
            self.assertEqual(handle.read(), b"\x89PNG-thumb")
        # The model carries a path, never the image bytes.
        self.assertNotIn("content", saved.model_dump())
        self.assertNotIn("bytes", saved.model_dump())

    def test_get_thumbnail_defaults_to_a_temp_file(self):
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.content = b"\xff\xd8-jpeg"
        response.headers = {"Content-Type": "image/jpeg"}
        self.client.session.get.return_value = response

        saved = self.manager.get_thumbnail(12)

        self.assertTrue(saved.savedPath.endswith(".jpg"))
        self.assertTrue(os.path.isfile(saved.savedPath))
        os.remove(saved.savedPath)

    def test_missing_thumbnail_is_a_404(self):
        response = MagicMock()
        response.status_code = 404
        response.ok = False
        self.client.session.get.return_value = response

        with self.assertRaises(GeopackAPIError) as ctx:
            self.manager.get_thumbnail(99)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_thumbnail_access_url_is_bearer_only(self):
        self.client.get.return_value = {
            "url": "http://localhost:3000/api/media/map-thumb?token=x",
            "expiresAt": "2026-11-19T11:00:00.000Z",
        }

        minted = self.manager.get_thumbnail_access_url(12)

        self.client.get.assert_called_once_with("/maps/12/thumbnail/access-url")
        self.assertIn("/api/media/", minted.url)

    # --- ACLs --------------------------------------------------------------

    def test_acls_are_bare_arrays(self):
        self.client.get.return_value = [
            {"id": 1, "principalType": "USER", "principalId": 7, "permission": "map:read"}
        ]

        rows = self.manager.get_acls(12)

        self.client.get.assert_called_once_with("/maps/12/acl")
        self.assertEqual(rows[0]["permission"], "map:read")

    def test_create_acls_posts_the_cartesian_envelope(self):
        self.client.post.return_value = [{"id": 3, "permission": "map:read"}]

        rows = self.manager.create_acls(
            12,
            principals=[{"type": "USER", "id": 7}],
            permissions=["map:read", "map:update"],
            effect="Allow",
        )

        payload = self.client.post.call_args.kwargs["json"]
        self.assertEqual(payload["principals"], [{"type": "USER", "id": 7}])
        self.assertEqual(payload["permissions"], ["map:read", "map:update"])
        self.assertEqual(payload["effect"], "Allow")
        self.assertEqual(len(rows), 1)

    def test_create_acls_requires_principals_and_permissions(self):
        with self.assertRaises(ValueError):
            self.manager.create_acls(12, principals=[], permissions=["map:read"])
        self.client.post.assert_not_called()

    def test_delete_acl_targets_the_entry(self):
        self.manager.delete_acl(12, 4)
        self.client.delete.assert_called_once_with("/maps/12/acl/4")

    # --- §0 boundary -------------------------------------------------------

    def test_no_generation_surface_exists(self):
        verbs = ("render_", "export_", "generate_", "print_", "compose_", "rasterize_", "pdf_")
        public = [name for name in dir(self.manager) if not name.startswith("_")]
        self.assertEqual([name for name in public if name.startswith(verbs)], [])


if __name__ == "__main__":
    unittest.main()
