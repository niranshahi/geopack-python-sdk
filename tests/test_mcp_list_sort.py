"""Sort parity across the MCP list lanes (slice 032 F6)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from geopack_sdk.workflow_runs import WorkflowRunManager
from geopack_sdk.workflows import WorkflowManager
from geopack_sdk_mcp.errors import ToolArgumentError
from geopack_sdk_mcp.tool_handlers.generated_files import list_generated_files
from geopack_sdk_mcp.tool_handlers.workflow_runs import list_workflow_runs
from geopack_sdk_mcp.tool_handlers.workflows import (
    ALLOWED_WORKFLOW_ORDER_FIELDS,
    list_workflows,
)


class _McpSortTestBase(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()


class WorkflowListSortTest(_McpSortTestBase):
    def test_order_by_is_forwarded(self):
        self.client.workflows.list.return_value = []

        list_workflows(
            self.client,
            page=2,
            page_size=5,
            search_query="area",
            order_by="name",
            order_direction="ASC",
        )

        kwargs = self.client.workflows.list.call_args.kwargs
        self.assertEqual(kwargs["order_by"], "name")
        self.assertEqual(kwargs["order_direction"], "asc")
        self.assertEqual(kwargs["page"], 2)
        self.assertEqual(kwargs["page_size"], 5)

    def test_unknown_order_key_is_refused_before_the_call(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            list_workflows(self.client, order_by="password")

        self.assertIn("owner.userName", ctx.exception.hint)
        self.assertIn("version", ctx.exception.hint)
        self.client.workflows.list.assert_not_called()

    def test_wrong_direction_is_refused(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            list_workflows(self.client, order_by="name", order_direction="up")

        self.assertIn("asc", ctx.exception.hint)
        self.client.workflows.list.assert_not_called()

    def test_whitelist_matches_the_server_mapping(self):
        self.assertEqual(
            ALLOWED_WORKFLOW_ORDER_FIELDS,
            ("id", "name", "owner.userName", "updatedAt", "createdAt", "version"),
        )


class WorkflowRunListSortTest(_McpSortTestBase):
    def _empty_response(self):
        return SimpleNamespace(items=[], total=0, totalItems=0)

    def test_order_by_is_forwarded_and_echoed(self):
        self.client.workflow_runs.list.return_value = self._empty_response()

        payload = list_workflow_runs(
            self.client,
            workflow_id=7,
            limit=10,
            order_by="startedAt",
            order_direction="desc",
        )

        kwargs = self.client.workflow_runs.list.call_args.kwargs
        self.assertEqual(kwargs["order_by"], "startedAt")
        self.assertEqual(kwargs["order_direction"], "desc")
        self.assertEqual(kwargs["filters"]["workflowId"], 7)
        self.assertEqual(payload["orderBy"], "startedAt")
        self.assertEqual(payload["orderDirection"], "desc")

    def test_unknown_order_key_is_refused_before_the_call(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            list_workflow_runs(self.client, order_by="bogus")

        self.assertIn("workflow.name", ctx.exception.hint)
        self.assertIn("finishedAt", ctx.exception.hint)
        self.client.workflow_runs.list.assert_not_called()


class GeneratedFileListSortTest(_McpSortTestBase):
    def test_sort_and_search_are_forwarded_and_echoed(self):
        self.client.generated_files.list.return_value = SimpleNamespace(
            items=[], totalItems=0
        )

        payload = list_generated_files(
            self.client,
            limit=30,
            search_query="dem",
            order_by="fileSize",
            order_direction="desc",
        )

        kwargs = self.client.generated_files.list.call_args.kwargs
        self.assertEqual(kwargs["search_query"], "dem")
        self.assertEqual(kwargs["order_by"], "fileSize")
        self.assertEqual(kwargs["order_direction"], "desc")
        self.assertEqual(payload["orderBy"], "fileSize")
        self.assertEqual(payload["orderDirection"], "desc")

    def test_unknown_order_key_is_refused_before_the_call(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            list_generated_files(self.client, order_by="downloadToken")

        self.assertIn("sharingPolicy", ctx.exception.hint)
        self.client.generated_files.list.assert_not_called()

    def test_no_sort_uses_the_portal_default(self):
        self.client.generated_files.list.return_value = SimpleNamespace(
            items=[], totalItems=0
        )

        payload = list_generated_files(self.client)

        kwargs = self.client.generated_files.list.call_args.kwargs
        self.assertNotIn("order_by", kwargs)
        self.assertNotIn("order_direction", kwargs)
        self.assertNotIn("orderBy", payload)


class SdkSortForwardingTest(unittest.TestCase):
    def test_workflows_list_sends_sort_by(self):
        client = MagicMock()
        client.get.return_value = {"items": []}

        WorkflowManager(client).list(
            page=1, page_size=10, order_by="version", order_direction="desc"
        )

        params = client.get.call_args.kwargs["params"]
        self.assertEqual(params["sortBy"], "version")
        self.assertEqual(params["sortOrder"], "desc")

    def test_workflow_runs_list_sends_sort_by(self):
        client = MagicMock()
        client.get.return_value = {"items": []}

        WorkflowRunManager(client).list(
            page=1, page_size=10, order_by="status", order_direction="asc"
        )

        params = client.get.call_args.kwargs["params"]
        self.assertEqual(params["sortBy"], "status")
        self.assertEqual(params["sortOrder"], "asc")


if __name__ == "__main__":
    unittest.main()