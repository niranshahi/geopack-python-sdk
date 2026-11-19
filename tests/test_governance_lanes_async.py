"""Async twins of the governance lanes (slice 015)."""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_uploads import AsyncUploadManager
from geopack_sdk.async_workflow_runs import AsyncWorkflowRunManager
from geopack_sdk.async_workflows import AsyncWorkflowManager
from tests.test_governance_lanes import (
    COMPILED_NOT_PUBLISHABLE,
    COMPILED_OK,
    LIMITS,
    STATISTICS,
    TOOL_MANIFEST,
)


class AsyncUploadLimitsTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_limits(self):
        client = AsyncMock()
        client.get.return_value = LIMITS
        manager = AsyncUploadManager(client)

        limits = await manager.get_limits()

        client.get.assert_awaited_once_with("/uploads/limits")
        self.assertEqual(limits.max_bytes, 500 * 1024 * 1024)


class AsyncWorkflowAdminTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncWorkflowManager(self.client)

    async def test_get_statistics(self):
        self.client.get.return_value = STATISTICS

        stats = await self.manager.get_statistics()

        self.client.get.assert_awaited_once_with("/workflows/statistics")
        self.assertEqual(stats["organizations"][0]["name"], "Org")

    async def test_compile_spec_both_modes(self):
        self.client.post.return_value = COMPILED_OK

        result = await self.manager.compile_spec({"nodes": []})
        self.assertTrue(result["ok"])
        self.assertEqual(
            self.client.post.call_args.kwargs["json"], {"spec": {"nodes": []}}
        )

        self.client.post.return_value = COMPILED_NOT_PUBLISHABLE
        result = await self.manager.compile_spec(workflow_id=12)
        self.assertFalse(result["ok"])
        self.assertEqual(
            self.client.post.call_args.kwargs["json"], {"workflowId": 12}
        )

    async def test_compile_spec_requires_exactly_one_mode(self):
        with self.assertRaises(ValueError):
            await self.manager.compile_spec()
        with self.assertRaises(ValueError):
            await self.manager.compile_spec({}, workflow_id=1)
        self.client.post.assert_not_awaited()

    async def test_tool_manifest_is_verbatim(self):
        self.client.get.return_value = TOOL_MANIFEST

        manifest = await self.manager.get_tool_manifest(12)

        self.client.get.assert_awaited_once_with("/workflows/12/tool-manifest")
        self.assertIs(manifest, TOOL_MANIFEST)


class AsyncWorkflowRunDeleteTest(unittest.IsolatedAsyncioTestCase):
    async def test_delete(self):
        client = AsyncMock()
        client.delete.return_value = {"id": 9, "deleted": True}
        manager = AsyncWorkflowRunManager(client)

        result = await manager.delete(9)

        client.delete.assert_awaited_once_with("/workflow-runs/9")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
