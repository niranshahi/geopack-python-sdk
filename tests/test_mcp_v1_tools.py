import unittest
from unittest.mock import MagicMock, patch

from geopack_sdk.models import Dataset, TaskResult
from geopack_sdk_mcp.tool_handlers.datasets import export_dataset
from geopack_sdk_mcp.tool_handlers.generated_files import download_generated_file
from geopack_sdk_mcp.tool_handlers.tasks import get_task, wait_for_task


class TestMcpV1ToolHandlers(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_export_dataset_returns_task_without_token(self):
        self.client.datasets.get.return_value = Dataset(
            id=5,
            name="roads",
            dataType="vector",
            ownerUserId=1,
            workgroupId=99,
            dataStoreId=1,
            createdAt="2024-01-01T00:00:00",
            updatedAt="2024-01-01T00:00:00",
        )
        self.client.datasets.export.return_value = TaskResult(
            taskId="task-1",
            status="pending",
            taskType="dataset:export",
        )

        result = export_dataset(self.client, 5, "geojson")

        self.assertEqual(result["taskId"], "task-1")
        self.client.datasets.export.assert_called_once()
        call_kwargs = self.client.datasets.export.call_args
        self.assertEqual(call_kwargs[0][0], 5)
        self.assertEqual(call_kwargs[0][1], 99)
        self.assertEqual(call_kwargs[0][2], "geojson")
        self.assertFalse(call_kwargs[1]["wait"])

    def test_export_dataset_uses_provided_workgroup(self):
        self.client.datasets.export.return_value = TaskResult(
            taskId="task-2",
            status="pending",
            taskType="dataset:export",
        )

        export_dataset(self.client, 5, "gpkg", workgroup_id=77)

        self.client.datasets.get.assert_not_called()
        self.assertEqual(self.client.datasets.export.call_args[0][1], 77)

    def test_wait_for_task_sanitizes_results(self):
        self.client.tasks.wait_for_task.return_value = TaskResult(
            taskId="task-3",
            status="completed",
            taskType="dataset:export",
            results={
                "generatedFileId": 10,
                "downloadToken": "tok",
            },
        )

        result = wait_for_task(self.client, "task-3", timeout=60, interval=1)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"]["downloadApiPath"], "/generated-files/10/download")
        self.assertNotIn("downloadToken", result["results"])

    def test_get_task_applies_sanitize(self):
        self.client.tasks.get_status.return_value = TaskResult(
            taskId="task-4",
            status="completed",
            taskType="dataset:export",
            results={"generatedFileId": 3, "downloadToken": "x"},
        )

        result = get_task(self.client, "task-4")

        self.assertEqual(result["results"]["downloadApiPath"], "/generated-files/3/download")
        self.assertNotIn("downloadToken", result["results"])

    @patch("geopack_sdk_mcp.tool_handlers.generated_files.os.path.abspath")
    def test_download_generated_file(self, mock_abspath):
        mock_abspath.side_effect = lambda p: p
        self.client.generated_files.download.return_value = "/tmp/out/data.geojson"

        result = download_generated_file(self.client, 10, "/tmp/out")

        self.assertEqual(result["generatedFileId"], 10)
        self.assertEqual(result["savedPath"], "/tmp/out/data.geojson")
        self.assertEqual(result["downloadApiPath"], "/generated-files/10/download")
        self.client.generated_files.download.assert_called_once_with(10, "/tmp/out")


if __name__ == "__main__":
    unittest.main()
