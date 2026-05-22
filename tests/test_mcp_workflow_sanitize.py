"""Tests for MCP workflow payload sanitization."""

import unittest

from geopack_sdk_mcp.sanitize.workflow_payload import (
    omit_workflow_graph_blobs,
    sanitize_workflow_for_mcp,
    sanitize_workflow_list_for_mcp,
    sanitize_workflow_submit_response,
)


class TestMcpWorkflowSanitize(unittest.TestCase):
    def test_omit_graph_json_keeps_other_fields(self):
        payload = {
            "id": 42,
            "name": "Hillshade",
            "graphJson": {"nodes": [{"id": "n1"}], "edges": []},
        }
        out = omit_workflow_graph_blobs(payload)
        self.assertEqual(out["id"], 42)
        self.assertEqual(out["name"], "Hillshade")
        self.assertNotIn("graphJson", out)
        self.assertIn("graphOmitted", out)

    def test_parameters_survive_when_present(self):
        payload = {
            "id": 42,
            "graphJson": {"nodes": []},
            "parameters": [
                {"key": "input_dataset_id", "type": "dataset", "required": True},
            ],
        }
        out = sanitize_workflow_for_mcp(payload)
        self.assertEqual(len(out["parameters"]), 1)
        self.assertEqual(out["parameters"][0]["key"], "input_dataset_id")
        self.assertNotIn("graphJson", out)

    def test_include_graph_preserves_blob(self):
        payload = {"id": 1, "graphJson": {"nodes": []}}
        out = sanitize_workflow_for_mcp(payload, include_graph=True)
        self.assertIn("graphJson", out)

    def test_list_sanitizes_each_row(self):
        rows = [
            {"id": 1, "name": "A", "graphJson": {"nodes": []}},
            {"id": 2, "name": "B", "graphJson": {"nodes": []}},
        ]
        out = sanitize_workflow_list_for_mcp(rows)
        self.assertEqual(len(out), 2)
        self.assertNotIn("graphJson", out[0])
        self.assertNotIn("graphJson", out[1])

    def test_submit_response_minimal_fields(self):
        out = sanitize_workflow_submit_response(
            {
                "workflowRunId": 100,
                "taskId": "t-1",
                "status": "queued",
                "messages": [{"level": "info", "message": "x"}],
            }
        )
        self.assertEqual(out, {"workflowRunId": 100, "taskId": "t-1", "status": "queued"})


if __name__ == "__main__":
    unittest.main()
