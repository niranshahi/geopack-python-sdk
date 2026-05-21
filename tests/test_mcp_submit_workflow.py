"""Tests for workflow submission MCP tool handlers."""

import unittest
from unittest.mock import MagicMock, patch

from geopack_sdk.models import WorkflowParameter, WorkflowRun, WorkflowRunSubmitResponse
from geopack_sdk_mcp.tool_handlers.submit_workflow import (
    get_workflow_with_params,
    submit_workflow,
)
from geopack_sdk_mcp.tool_handlers.workflow_runs import download_workflow_artifact


class TestSubmitWorkflowHandlers(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_submit_workflow_returns_sanitized_response(self):
        """Submit workflow should return taskId and workflowRunId."""
        self.client.workflow_runs.submit.return_value = WorkflowRunSubmitResponse(
            workflowRunId=123,
            taskId="task-abc",
            status="queued",
        )

        result = submit_workflow(
            self.client,
            workflow_id=42,
            params={"input_dataset_id": 100},
        )

        self.assertEqual(result["workflowRunId"], 123)
        self.assertEqual(result["taskId"], "task-abc")
        self.assertEqual(result["status"], "queued")
        self.client.workflow_runs.submit.assert_called_once_with(
            workflow_id=42,
            params={"input_dataset_id": 100},
            override_datastore_id=None,
            wait=False,
        )

    def test_submit_workflow_with_override_datastore(self):
        """Submit workflow with datastore override."""
        self.client.workflow_runs.submit.return_value = WorkflowRunSubmitResponse(
            workflowRunId=124,
            taskId="task-def",
            status="queued",
        )

        result = submit_workflow(
            self.client,
            workflow_id=42,
            params={"input_dataset_id": 100},
            override_datastore_id=5,
        )

        self.assertEqual(result["workflowRunId"], 124)
        self.client.workflow_runs.submit.assert_called_once_with(
            workflow_id=42,
            params={"input_dataset_id": 100},
            override_datastore_id=5,
            wait=False,
        )

    def test_get_workflow_with_params(self):
        """Get workflow with parameter extraction."""
        workflow_dict = {
            "id": 42,
            "name": "Hillshade",
            "description": "Generate hillshade from DEM",
        }

        params = [
            WorkflowParameter(
                key="input_dataset_id",
                type="dataset",
                description="Input DEM dataset",
                default=None,
                required=True,
                runVisibility="editable",
                dataType="raster",
                multiple=False,
            ),
            WorkflowParameter(
                key="azimuth",
                type="number",
                description="Azimuth angle",
                default=315,
                required=False,
                runVisibility="editable",
            ),
        ]

        workflow = MagicMock()

        self.client.workflows.get.return_value = workflow
        self.client.workflows.extract_params.return_value = params

        with patch(
            "geopack_sdk_mcp.tool_handlers.submit_workflow.to_jsonable"
        ) as mock_to_jsonable:
            def to_jsonable_impl(value):
                # Handle workflow dict
                if value is workflow:
                    return workflow_dict
                # Handle Pydantic models
                if hasattr(value, "model_dump"):
                    return value.model_dump(mode="json")
                # Handle lists
                if isinstance(value, list):
                    return [to_jsonable_impl(item) for item in value]
                # Handle dicts
                if isinstance(value, dict):
                    return {k: to_jsonable_impl(v) for k, v in value.items()}
                return value

            mock_to_jsonable.side_effect = to_jsonable_impl

            result = get_workflow_with_params(
                self.client,
                workflow_id=42,
                include_params=True,
            )

            self.assertEqual(result["id"], 42)
            self.assertEqual(result["name"], "Hillshade")
            self.assertIn("parameters", result)
            self.assertEqual(len(result["parameters"]), 2)
            self.assertEqual(result["parameters"][0]["key"], "input_dataset_id")
            self.assertEqual(result["parameters"][0]["required"], True)
            self.assertEqual(result["parameters"][1]["key"], "azimuth")
            self.assertEqual(result["parameters"][1]["default"], 315)

    def test_get_workflow_without_params(self):
        """Get workflow without parameter extraction."""
        workflow_dict = {
            "id": 42,
            "name": "Hillshade",
        }

        workflow = MagicMock()

        self.client.workflows.get.return_value = workflow
        self.client.workflows.extract_params.return_value = []

        with patch(
            "geopack_sdk_mcp.tool_handlers.submit_workflow.to_jsonable"
        ) as mock_to_jsonable:
            mock_to_jsonable.side_effect = lambda x: (
                workflow_dict if x is workflow else x
            )

            result = get_workflow_with_params(
                self.client,
                workflow_id=42,
                include_params=False,
            )

            self.assertEqual(result["id"], 42)
            self.assertEqual(result["name"], "Hillshade")
            self.assertNotIn("parameters", result)
            self.client.workflows.extract_params.assert_not_called()

    def test_download_workflow_artifact(self):
        """Download workflow artifact should return saved path."""
        self.client.workflow_runs.download_artifact.return_value = (
            "./output/hillshade.tif"
        )

        result = download_workflow_artifact(
            self.client,
            run_id=123,
            artifact_id=5,
            save_path="./output/",
        )

        self.assertIn("savedPath", result)
        self.assertEqual(result["workflowRunId"], 123)
        self.assertEqual(result["artifactId"], 5)
        self.assertTrue(result["savedPath"].endswith("hillshade.tif"))
        self.client.workflow_runs.download_artifact.assert_called_once_with(
            123, 5, "./output/"
        )


if __name__ == "__main__":
    unittest.main()
