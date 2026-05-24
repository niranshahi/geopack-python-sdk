import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from geopack_sdk.media_access import (
    dataset_thumbnail_mint_path,
    fetch_dataset_thumbnail,
    mint_access_url,
    mint_dataset_thumbnail_url,
)
from geopack_sdk.dataset_payload import normalize_dataset_dict


class TestMediaAccess(unittest.TestCase):
    def test_mint_paths(self):
        self.assertEqual(dataset_thumbnail_mint_path(42), "/datasets/42/thumbnail/access-url")

    def test_normalize_dataset_includes_mint_path(self):
        normalized = normalize_dataset_dict({"id": 7, "hasThumbnail": True})
        self.assertEqual(normalized["thumbnailMintPath"], "/datasets/7/thumbnail/access-url")

    def test_mint_access_url(self):
        client = MagicMock()
        client.get.return_value = {
            "url": "http://localhost:3000/api/datasets/1/thumbnail?media=x&sig=y",
            "expiresAt": "2026-05-24T12:00:00.000Z",
            "mediaQuery": "media=x&sig=y",
        }
        result = mint_access_url(client, "/datasets/1/thumbnail/access-url")
        client.get.assert_called_once_with("datasets/1/thumbnail/access-url")
        self.assertIn("media=x", result.url)
        self.assertEqual(result.media_query, "media=x&sig=y")
        self.assertEqual(result.expires_at.year, 2026)

    def test_mint_dataset_thumbnail_url(self):
        client = MagicMock()
        client.get.return_value = {
            "url": "http://example/api/datasets/2/thumbnail?media=a&sig=b",
            "expiresAt": "2026-06-01T00:00:00+00:00",
        }
        mint_dataset_thumbnail_url(client, 2)
        client.get.assert_called_once_with("datasets/2/thumbnail/access-url")

    def test_fetch_dataset_thumbnail_uses_bearer_not_query_jwt(self):
        client = MagicMock()
        client.base_url = "http://localhost:3000/api"
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.content = b"\x89PNG"
        response.headers = {"Content-Type": "image/png"}
        client.session.get.return_value = response

        body, mime = fetch_dataset_thumbnail(client, 5)

        self.assertEqual(body, b"\x89PNG")
        self.assertEqual(mime, "image/png")
        called_url = client.session.get.call_args[0][0]
        self.assertEqual(called_url, "http://localhost:3000/api/datasets/5/thumbnail")
        self.assertNotIn("auth_token", called_url)


if __name__ == "__main__":
    unittest.main()
