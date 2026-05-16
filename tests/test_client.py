import unittest
from unittest.mock import MagicMock, patch

import requests

from geopack_sdk.client import GeopackClient


class TestGeopackClientNoContent(unittest.TestCase):
    def setUp(self):
        self.client = GeopackClient(
            base_url="http://example.com/api",
            enable_http_retries=False,
        )

    @patch.object(requests.Session, "request")
    def test_delete_returns_none_on_204(self, mock_request):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 204
        mock_response.content = b""
        mock_request.return_value = mock_response

        result = self.client.delete("/datasets/1")
        self.assertIsNone(result)

    @patch.object(requests.Session, "request")
    def test_get_json_on_200(self, mock_request):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'
        mock_response.json.return_value = {"ok": True}
        mock_request.return_value = mock_response

        result = self.client.get("/datasets")
        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()
