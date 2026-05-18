import unittest
from unittest.mock import MagicMock

from geopack_sdk.models import (
    Dataset,
    DatasetsApiResponse,
    FeatureCollection,
    TaskResult,
    Workflow,
    WorkflowRun,
)
from geopack_sdk_mcp.tool_handlers.datasets import get_dataset, list_datasets, query_dataset
from geopack_sdk_mcp.tool_handlers.tasks import get_task
from geopack_sdk_mcp.tool_handlers.workflow_runs import get_workflow_run
from geopack_sdk_mcp.tool_handlers.workflows import list_workflows


class TestMcpToolHandlers(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_list_datasets_returns_jsonable_dict(self):
        self.client.datasets.list.return_value = DatasetsApiResponse(
            datasets=[
                Dataset(
                    id=1,
                    name="demo",
                    dataType="vector",
                    ownerUserId=1,
                    workgroupId=1,
                    dataStoreId=1,
                    createdAt="2024-01-01T00:00:00",
                    updatedAt="2024-01-01T00:00:00",
                )
            ],
            totalCount=1,
            totalPages=1,
            currentPage=1,
            itemsPerPage=10,
        )

        result = list_datasets(self.client, page=1, page_size=10)

        self.assertIn("datasets", result)
        self.assertEqual(result["datasets"][0]["name"], "demo")
        self.assertNotIn("thumbnail", result["datasets"][0])
        self.client.datasets.list.assert_called_once()

    def test_get_task_returns_task_result(self):
        self.client.tasks.get_status.return_value = TaskResult(
            taskId="abc",
            status="completed",
            taskType="upload",
        )

        result = get_task(self.client, "abc")

        self.assertEqual(result["taskId"], "abc")
        self.assertEqual(result["status"], "completed")

    def test_list_workflows_returns_list(self):
        self.client.workflows.list.return_value = [
            Workflow(
                id=5,
                name="Buffer",
                graphJson={"nodes": [], "connections": []},
                createdAt="2024-01-01T00:00:00",
                updatedAt="2024-01-01T00:00:00",
            )
        ]

        result = list_workflows(self.client)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Buffer")

    def test_get_workflow_run(self):
        self.client.workflow_runs.get.return_value = WorkflowRun(
            id=99,
            workflowId=5,
            status="succeeded",
            createdAt="2024-01-01T00:00:00",
            updatedAt="2024-01-01T00:00:00",
        )

        result = get_workflow_run(self.client, 99)

        self.assertEqual(result["id"], 99)
        self.assertEqual(result["status"], "succeeded")

    def test_get_dataset(self):
        self.client.datasets.get.return_value = Dataset(
            id=2,
            name="roads",
            dataType="vector",
            ownerUserId=1,
            workgroupId=1,
            dataStoreId=1,
            createdAt="2024-01-01T00:00:00",
            updatedAt="2024-01-01T00:00:00",
            hasThumbnail=True,
        )

        result = get_dataset(self.client, 2)

        self.assertEqual(result["name"], "roads")
        self.assertEqual(result["thumbnailApiPath"], "/datasets/2/thumbnail")
        self.assertNotIn("thumbnail", result)

    def test_query_dataset_applies_limit(self):
        self.client.datasets.query.return_value = FeatureCollection(
            type="FeatureCollection",
            features=[],
        )

        result = query_dataset(self.client, 10, limit=50)

        self.assertEqual(result["queryLimitApplied"], 50)
        self.client.datasets.query.assert_called_once()
        call_kwargs = self.client.datasets.query.call_args.kwargs
        self.assertEqual(call_kwargs["limit"], 50)


if __name__ == "__main__":
    unittest.main()
