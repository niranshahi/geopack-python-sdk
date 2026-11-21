import tempfile
import unittest
from unittest.mock import MagicMock, patch

from geopack_sdk_mcp.errors import tool_result_with_image
from geopack_sdk_mcp.tool_handlers.datasets import (
    ThumbnailResult,
    get_dataset_thumbnail,
)


class TestMcpDatasetThumbnail(unittest.TestCase):
    @patch("geopack_sdk_mcp.tool_handlers.datasets.fetch_dataset_thumbnail")
    def test_explicit_save_path_writes_file(self, mock_fetch):
        mock_fetch.return_value = (b"\x89PNG", "image/png")
        client = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/thumb.png"
            result = get_dataset_thumbnail(client, 2360, save_path=path)

        self.assertIsInstance(result, ThumbnailResult)
        self.assertEqual(result.body, b"\x89PNG")
        self.assertEqual(result.payload["datasetId"], 2360)
        self.assertTrue(result.payload["saved"])
        self.assertTrue(result.payload["savedPath"].endswith("thumb.png"))
        self.assertEqual(result.payload["sizeBytes"], 4)
        self.assertEqual(
            result.payload["thumbnailResourceUri"], "dataset://2360/thumbnail"
        )

    @patch("geopack_sdk_mcp.tool_handlers.datasets.fetch_dataset_thumbnail")
    def test_no_save_path_writes_nothing_and_never_touches_the_disk(self, mock_fetch):
        """The reported crash: no save_path must not invent a temp target.

        A sandboxed host can have no usable temporary directory (``gettempdir``
        raises), so the default lane must not attempt any write at all.
        """
        mock_fetch.return_value = (b"\x89PNG", "image/png")
        client = MagicMock()

        with patch(
            "pathlib.Path.mkdir", side_effect=AssertionError("must not touch disk")
        ), patch(
            "pathlib.Path.write_bytes", side_effect=AssertionError("must not touch disk")
        ):
            result = get_dataset_thumbnail(client, 2973)

        self.assertFalse(result.payload["saved"])
        self.assertTrue(result.payload["saveSkipped"])
        self.assertNotIn("saveError", result.payload)
        self.assertNotIn("savedPath", result.payload)
        self.assertEqual(result.body, b"\x89PNG")
        self.assertIn("inline", result.payload["hint"])

    @patch("geopack_sdk_mcp.tool_handlers.datasets.fetch_dataset_thumbnail")
    def test_unwritable_host_returns_image_and_saved_false(self, mock_fetch):
        """A sandboxed host refuses the explicit write: the bytes still come back (F2)."""
        mock_fetch.return_value = (b"\x89PNG", "image/png")
        client = MagicMock()

        with patch(
            "geopack_sdk_mcp.tool_handlers.datasets.Path.write_bytes",
            side_effect=PermissionError(13, "Access is denied"),
        ):
            result = get_dataset_thumbnail(client, 2973, save_path="thumb.png")

        self.assertFalse(result.payload["saved"])
        self.assertEqual(result.payload["saveError"], "PermissionError (errno 13)")
        self.assertNotIn("\\", result.payload["saveError"])
        self.assertNotIn(":", result.payload["saveError"].replace("PermissionError", ""))
        self.assertEqual(result.body, b"\x89PNG")
        self.assertIn("inline", result.payload["hint"])

    @patch("geopack_sdk_mcp.tool_handlers.datasets.fetch_dataset_thumbnail")
    def test_missing_parent_is_not_fatal(self, mock_fetch):
        """A path that resolves to a non-directory is a state, not a failed call."""
        mock_fetch.return_value = (b"\x89PNG", "image/png")
        client = MagicMock()

        with patch(
            "geopack_sdk_mcp.tool_handlers.datasets.Path.mkdir",
            side_effect=FileNotFoundError(2, "No usable temporary directory"),
        ):
            result = get_dataset_thumbnail(client, 9, save_path="/nonexistent/dir/thumb.png")

        self.assertFalse(result.payload["saved"])
        self.assertIn("FileNotFoundError", result.payload["saveError"])
        self.assertNotIn("/nonexistent", result.payload["saveError"])
        self.assertEqual(result.body, b"\x89PNG")

    def test_tool_result_carries_an_image_block(self):
        result = tool_result_with_image(
            {"datasetId": 7, "saved": False, "mimeType": "image/png"},
            b"\x89PNG",
            "image/png",
        )

        self.assertFalse(result.isError)
        kinds = [block.type for block in result.content]
        self.assertIn("image", kinds)
        self.assertIn("text", kinds)
        image = next(block for block in result.content if block.type == "image")
        self.assertEqual(image.mimeType, "image/png")
        self.assertEqual(result.structuredContent["saved"], False)

    def test_non_image_mime_is_normalised(self):
        result = tool_result_with_image({}, b"raw", "application/octet-stream")
        image = next(block for block in result.content if block.type == "image")
        self.assertEqual(image.mimeType, "image/png")


if __name__ == "__main__":
    unittest.main()