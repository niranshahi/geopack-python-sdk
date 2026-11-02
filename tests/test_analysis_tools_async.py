"""Async mirror of the analysis-tool tests.

The async manager imports its refusals and polling constants from the sync
module, so this file also guards the parity claim: the same server answer must
raise the same exception class on both lanes.
"""

import unittest
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

from geopack_sdk import analysis_tools as sync_module
from geopack_sdk.analysis_tools import AnalysisToolManager
from geopack_sdk.async_analysis_tools import AsyncAnalysisToolManager
from geopack_sdk.exceptions import (
    AnalysisParamError,
    AnalysisSurfaceUnavailable,
    AnalysisTimeout,
    GeopackAPIError,
)
from geopack_sdk.models import AnalysisResult, WorkflowRunSubmitResponse

CATALOG: Dict[str, Any] = {
    "items": [
        {
            "toolId": 5,
            "title": "Well buffer",
            "summary": "Buffer wells by a distance",
            "tags": ["analysis", "buffer"],
            "version": "3",
            "outputs": [{"portId": "out", "dataType": "vector", "fromNode": "n2"}],
            "access": {"canRun": True, "canSee": True},
        }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 20,
}

MANIFEST: Dict[str, Any] = {
    "toolId": 5,
    "title": "Well buffer",
    "params": [{"key": "distance", "label": "Distance", "type": "number", "required": True}],
    "inputs": [{"kind": "scalar", "key": "distance", "label": "Distance", "dataType": "number"}],
    "outputs": [],
}

SUMMARY: Dict[str, Any] = {
    "runId": 7,
    "workflowId": 5,
    "toolId": 5,
    "title": "Well buffer",
    "status": "succeeded",
    "complete": True,
    "durationMs": 1234,
    "source": "mcp",
    "params": {"distance": 100},
    "scalars": {"n2:count": 12},
    "datasets": [{"id": 41, "name": "Buffered wells", "nodeId": "n2"}],
    "artifacts": [],
    "errors": [],
    "portFallbacks": 0,
}

SUBMISSION = {"workflowRunId": 7, "taskId": "task-7", "status": "queued"}


class _AsyncFakeClient:
    """Just the two coroutines the manager awaits."""

    def __init__(self) -> None:
        self.get = AsyncMock()
        self.post = AsyncMock()


class TestAsyncAnalysisToolManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = _AsyncFakeClient()
        self.manager = AsyncAnalysisToolManager(self.client)  # type: ignore[arg-type]

    async def test_catalog_shape_is_the_server_response(self):
        self.client.get.return_value = CATALOG

        catalog = await self.manager.list(search="buffer", tag="analysis", page=2, page_size=5)

        self.assertEqual(catalog.total, 1)
        self.assertEqual(catalog.items[0].toolId, 5)
        self.assertIsNone(catalog.items[0].params)
        self.client.get.assert_awaited_once_with(
            "/workflows/tools",
            params={"page": 2, "pageSize": 5, "q": "buffer", "tag": "analysis"},
        )

    async def test_missing_surface_raises_and_does_not_fall_back(self):
        self.client.get.side_effect = GeopackAPIError(404, "Not found")

        with self.assertRaises(AnalysisSurfaceUnavailable) as raised:
            await self.manager.list()

        self.assertEqual(raised.exception.status_code, 404)
        self.client.get.assert_awaited_once()

    async def test_manifest_refusal_becomes_a_param_error(self):
        self.client.get.side_effect = GeopackAPIError(400, "Parameter node 'bad' has no key")

        with self.assertRaises(AnalysisParamError) as raised:
            await self.manager.get(5)

        self.assertEqual(raised.exception.tool_id, 5)
        self.assertEqual(raised.exception.reason, "Parameter node 'bad' has no key")

    async def test_manifest_403_and_404_keep_their_http_identity(self):
        for status in (403, 404):
            self.client.get.side_effect = GeopackAPIError(status, "nope")
            with self.assertRaises(GeopackAPIError) as raised:
                await self.manager.get(5)
            self.assertNotIsInstance(raised.exception, AnalysisParamError)
            self.assertEqual(raised.exception.status_code, status)

    async def test_run_wait_polls_then_reads_the_summary(self):
        self.client.post.return_value = SUBMISSION
        self.client.get.side_effect = [
            {"status": "running"},
            {"status": "succeeded"},
            SUMMARY,
        ]

        result = await self.manager.run(5, {"distance": 100}, poll_interval_s=0.01)

        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.runId, 7)
        self.assertEqual(result.scalars, {"n2:count": 12})
        self.client.post.assert_awaited_once()
        self.assertEqual(self.client.get.await_count, 3)

    async def test_run_stamps_the_mcp_attribution_header(self):
        self.client.post.return_value = SUBMISSION

        submission = await self.manager.run(5, {"distance": 100}, wait=False)

        self.assertIsInstance(submission, WorkflowRunSubmitResponse)
        self.assertEqual(submission.workflowRunId, 7)
        headers = self.client.post.call_args.kwargs["headers"]
        self.assertEqual(headers["X-Geoportal-Client"], "mcp")
        self.assertEqual(
            self.client.post.call_args.kwargs["json"],
            {"workflowId": 5, "params": {"distance": 100}},
        )
        self.client.get.assert_not_called()

    async def test_override_datastore_rides_along_in_the_payload(self):
        self.client.post.return_value = SUBMISSION

        await self.manager.run(5, {}, wait=False, override_datastore_id=3)

        self.assertEqual(self.client.post.call_args.kwargs["json"]["overrideDataStoreId"], 3)

    async def test_timeout_names_the_run_and_leaves_it_running(self):
        self.client.post.return_value = SUBMISSION
        self.client.get.return_value = {"status": "running"}

        with self.assertRaises(AnalysisTimeout) as raised:
            await self.manager.run(5, {}, timeout_s=0)

        self.assertEqual(raised.exception.run_id, 7)
        self.assertIn("keeps going", str(raised.exception))
        # Only the submit: a polling budget must never cancel the user's run.
        self.client.post.assert_awaited_once()


class TestAsyncSyncParity(unittest.IsolatedAsyncioTestCase):
    """Same server answer, same exception class, on both lanes."""

    async def test_manifest_400_maps_identically(self):
        sync_client = MagicMock()
        sync_client.get.side_effect = GeopackAPIError(400, "bad manifest")
        async_client = _AsyncFakeClient()
        async_client.get.side_effect = GeopackAPIError(400, "bad manifest")

        with self.assertRaises(AnalysisParamError) as sync_raised:
            AnalysisToolManager(sync_client).get(5)
        with self.assertRaises(AnalysisParamError) as async_raised:
            await AsyncAnalysisToolManager(async_client).get(5)  # type: ignore[arg-type]

        self.assertIs(type(async_raised.exception), type(sync_raised.exception))

    async def test_catalog_404_maps_identically(self):
        sync_client = MagicMock()
        sync_client.get.side_effect = GeopackAPIError(404, "missing")
        async_client = _AsyncFakeClient()
        async_client.get.side_effect = GeopackAPIError(404, "missing")

        with self.assertRaises(AnalysisSurfaceUnavailable) as sync_raised:
            AnalysisToolManager(sync_client).list()
        with self.assertRaises(AnalysisSurfaceUnavailable) as async_raised:
            await AsyncAnalysisToolManager(async_client).list()  # type: ignore[arg-type]

        self.assertIs(type(async_raised.exception), type(sync_raised.exception))
        self.assertEqual(async_raised.exception.status_code, sync_raised.exception.status_code)

    async def test_polling_constants_are_shared_not_duplicated(self):
        # The async module imports these from the sync one; a private copy would
        # let the two lanes drift apart on backoff without anyone noticing.
        from geopack_sdk import async_analysis_tools as async_module

        for name in ("_POLL_BACKOFF", "_POLL_MAX_S", "_POLL_FLOOR_S", "_CLIENT_HEADERS"):
            self.assertEqual(
                getattr(async_module, name),
                getattr(sync_module, name),
                name,
            )


if __name__ == "__main__":
    unittest.main()
