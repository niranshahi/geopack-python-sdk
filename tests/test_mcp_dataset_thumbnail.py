import tempfile
import unittest
from unittest.mock import MagicMock, patch

from geopack_sdk_mcp.tool_handlers.datasets import get_dataset_thumbnail


class TestMcpDatasetThumbnail(unittest.TestCase):
    @patch("geopack_sdk_mcp.tool_handlers.datasets.fetch_dataset_thumbnail")
    def test_get_dataset_thumbnail_writes_file(self, mock_fetch):
        mock_fetch.return_value = (b"\x89PNG", "image/png")
        client = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/thumb.png"
            result = get_dataset_thumbnail(client, 2360, save_path=path)

        self.assertEqual(result["datasetId"], 2360)
        self.assertTrue(result["savedPath"].endswith("thumb.png"))
        self.assertEqual(result["sizeBytes"], 4)
        self.assertEqual(result["thumbnailResourceUri"], "dataset://2360/thumbnail")


if __name__ == "__main__":
    unittest.main()
