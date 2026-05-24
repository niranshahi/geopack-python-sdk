import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import GeopackAPIError
from geopack_sdk_mcp.resource_handlers.datasets import fetch_dataset_thumbnail
from geopack_sdk_mcp.resource_handlers.generated_files import fetch_generated_file_bytes


class TestMcpResourceHandlers(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.base_url = "http://localhost:3000/api"

    def test_fetch_dataset_thumbnail_success(self):
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.content = b"\x89PNG\r\n"
        response.headers = {"Content-Type": "image/png; charset=binary"}
        self.client.session.get.return_value = response

        body, mime = fetch_dataset_thumbnail(self.client, 2360)

        self.assertEqual(body, b"\x89PNG\r\n")
        self.assertEqual(mime, "image/png")
        self.client.session.get.assert_called_once_with(
            "http://localhost:3000/api/datasets/2360/thumbnail",
            timeout=60,
            stream=False,
        )

    def test_fetch_dataset_thumbnail_404(self):
        response = MagicMock()
        response.status_code = 404
        response.ok = False
        self.client.session.get.return_value = response

        with self.assertRaises(GeopackAPIError) as ctx:
            fetch_dataset_thumbnail(self.client, 999)

        self.assertEqual(ctx.exception.status_code, 404)

    def test_fetch_generated_file_bytes_success(self):
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.content = b"geojson-bytes"
        response.headers = {"Content-Type": "application/geo+json"}
        self.client.session.get.return_value = response

        body, mime = fetch_generated_file_bytes(self.client, 42)

        self.assertEqual(body, b"geojson-bytes")
        self.assertEqual(mime, "application/geo+json")
        self.client.session.get.assert_called_once_with(
            "http://localhost:3000/api/generated-files/42/download",
            stream=True,
            timeout=300,
        )
