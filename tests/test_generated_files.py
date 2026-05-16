import unittest
from unittest.mock import MagicMock

from geopack_sdk.generated_files import GeneratedFileManager
from geopack_sdk.models import GeneratedFileListResponse


class TestGeneratedFileManager(unittest.TestCase):
    def test_list_parses_response(self):
        client = MagicMock()
        client.get.return_value = {
            "totalItems": 1,
            "totalPages": 1,
            "currentPage": 1,
            "pageSize": 10,
            "items": [
                {
                    "id": 7,
                    "fileName": "hillshade.tif",
                    "fileSize": 1024,
                    "sharingPolicy": "private",
                    "downloadToken": "abc",
                    "expiresAt": "2026-12-31T00:00:00.000Z",
                    "createdAt": "2026-05-16T00:00:00.000Z",
                }
            ],
        }
        mgr = GeneratedFileManager(client)
        result = mgr.list(page=1, page_size=10, search_query="hill")

        self.assertIsInstance(result, GeneratedFileListResponse)
        self.assertEqual(result.totalItems, 1)
        self.assertEqual(result.items[0].fileName, "hillshade.tif")
        client.get.assert_called_once_with(
            "/generated-files",
            params={
                "page": 1,
                "pageSize": 10,
                "orderBy": "createdAt",
                "orderDirection": "desc",
                "searchQuery": "hill",
            },
        )

    def test_delete_calls_api(self):
        client = MagicMock()
        client.delete.return_value = None
        mgr = GeneratedFileManager(client)
        mgr.delete(7)
        client.delete.assert_called_once_with("/generated-files/7")


if __name__ == "__main__":
    unittest.main()
