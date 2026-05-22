"""Tests for MCP dataset upload handler."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from geopack_sdk.models import TaskResult
from geopack_sdk_mcp.tool_handlers.dataset_upload import (
    upload_dataset,
    validate_upload_file_path,
)


class TestValidateUploadFilePath(unittest.TestCase):
    def test_rejects_url(self):
        with self.assertRaises(ValueError) as ctx:
            validate_upload_file_path("https://example.com/data.geojson")
        self.assertIn("URL", str(ctx.exception))

    def test_rejects_parent_traversal(self):
        with self.assertRaises(ValueError) as ctx:
            validate_upload_file_path("../etc/passwd")
        self.assertIn("..", str(ctx.exception))

    def test_accepts_existing_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            tmp.write(b'{"type":"FeatureCollection","features":[]}')
            tmp_path = tmp.name
        try:
            resolved = validate_upload_file_path(tmp_path, max_bytes=1024 * 1024)
            self.assertTrue(resolved.is_file())
        finally:
            os.unlink(tmp_path)

    def test_rejects_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            validate_upload_file_path(
                os.path.join(tempfile.gettempdir(), "no-such-mcp-upload.bin")
            )

    def test_enforces_max_bytes(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x" * 200)
            tmp_path = tmp.name
        try:
            with self.assertRaises(ValueError) as ctx:
                validate_upload_file_path(tmp_path, max_bytes=100)
            self.assertIn("GEOPACK_MCP_MAX_UPLOAD_BYTES", str(ctx.exception))
        finally:
            os.unlink(tmp_path)

    def test_upload_root_constraint(self):
        with tempfile.TemporaryDirectory() as root:
            inside = os.path.join(root, "ok.geojson")
            with open(inside, "wb") as f:
                f.write(b"{}")

            resolved = validate_upload_file_path(inside, upload_root=root)
            self.assertTrue(str(resolved).startswith(str(Path(root).resolve())))

    def test_upload_root_rejects_outside(self):
        with tempfile.TemporaryDirectory() as root:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as outside:
                outside.write(b"{}")
                outside_path = outside.name
            try:
                with self.assertRaises(ValueError) as ctx:
                    validate_upload_file_path(outside_path, upload_root=root)
                self.assertIn("GEOPACK_MCP_UPLOAD_ROOT", str(ctx.exception))
            finally:
                os.unlink(outside_path)


class TestUploadDatasetHandler(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    @patch("geopack_sdk_mcp.tool_handlers.dataset_upload.validate_upload_file_path")
    def test_upload_returns_minimal_task_json(self, mock_validate):
        mock_validate.return_value = Path("/tmp/demo.geojson")
        self.client.datasets.upload.return_value = TaskResult(
            taskId="upload-task-1",
            status="pending",
            taskType="dataset:upload",
        )

        result = upload_dataset(
            self.client,
            file_path="/tmp/demo.geojson",
            data_store_id=11,
            workgroup_id=1,
            declared_type="vector",
        )

        self.assertEqual(result["taskId"], "upload-task-1")
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["taskType"], "dataset:upload")
        self.assertEqual(result["fileName"], "demo.geojson")
        self.assertEqual(result["dataStoreId"], 11)
        self.assertEqual(result["declaredType"], "vector")
        self.assertNotIn("messages", result)

        call_args = self.client.datasets.upload.call_args
        self.assertEqual(call_args[0][1], 11)
        self.assertEqual(call_args[0][2], 1)
        self.assertEqual(call_args[1]["declared_type"], "vector")
        self.assertFalse(call_args[1]["wait"])
        self.assertTrue(str(call_args[0][0]).endswith("demo.geojson"))

    @patch("geopack_sdk_mcp.tool_handlers.dataset_upload.validate_upload_file_path")
    def test_upload_passes_metadata_name(self, mock_validate):
        mock_validate.return_value = Path("/tmp/named.geojson")
        self.client.datasets.upload.return_value = TaskResult(
            taskId="upload-task-2",
            status="pending",
            taskType="dataset:upload",
        )

        result = upload_dataset(
            self.client,
            file_path="/tmp/named.geojson",
            data_store_id=11,
            workgroup_id=1,
            metadata={"name": "فایل از متن"},
        )

        self.assertEqual(result["datasetName"], "فایل از متن")
        self.assertEqual(
            self.client.datasets.upload.call_args[1]["metadata"],
            {"name": "فایل از متن"},
        )


if __name__ == "__main__":
    unittest.main()
