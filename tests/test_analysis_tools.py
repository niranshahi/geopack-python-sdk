"""Tests for the analysis-tool SDK manager, its MCP handlers and the sanitizer."""

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from geopack_sdk.analysis_tools import AnalysisToolManager
from geopack_sdk.exceptions import (
    AnalysisParamError,
    AnalysisSurfaceUnavailable,
    AnalysisTimeout,
    GeopackAPIError,
)
from geopack_sdk.models import (
    AnalysisResult,
    AnalysisTool,
    AnalysisToolListResponse,
    WorkflowRunSubmitResponse,
)
from geopack_sdk_mcp.sanitize.analysis_result import (
    find_forbidden_keys,
    sanitize_analysis_result,
)
from geopack_sdk_mcp.tool_handlers.analysis import (
    get_analysis_result,
    list_analysis_tools,
    run_analysis,
)
from geopack_sdk_mcp.tools import policy as policy_tools

CATALOG: Dict[str, Any] = {
    "items": [
        {
            "toolId": 5,
            "title": "Well buffer",
            "summary": "Buffer wells by a distance",
            "tags": ["analysis", "buffer"],
            "version": "3",
            "outputs": [{"portId": "out", "dataType": "vector", "fromNode": "n2"}],
            "graph": {"nodeCount": 2, "paramCount": 1, "operations": ["qgis:buffer"]},
            "runtime": {"estimatedDurationMs": None, "supportsCancel": True},
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
    "summary": "Buffer wells by a distance",
    "tags": ["analysis"],
    "version": "3",
    "params": [
        {
            "key": "distance",
            "label": "Distance",
            "type": "number",
            "required": True,
            "nullable": True,
            "default": 100,
            "description": "Buffer distance in metres",
        }
    ],
    "inputs": [{"kind": "scalar", "key": "distance", "label": "Distance", "dataType": "number"}],
    "outputs": [],
    "graph": {"nodeCount": 2, "paramCount": 1, "operations": ["qgis:buffer"]},
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
    "artifacts": [
        {
            "artifactId": 3,
            "artifactType": "vector",
            "name": "buffered.gpkg",
            "bytes": 2048,
            "downloadUrl": "/api/workflow-runs/7/artifacts/3/download",
        }
    ],
    "errors": [],
    "portFallbacks": 0,
}

SUBMISSION = {"workflowRunId": 7, "taskId": "task-7", "status": "queued"}


class _FakeMCP:
    """Captures the functions a register() call decorates."""

    def __init__(self) -> None:
        self.tools: Dict[str, Any] = {}

    def tool(self, description: str = ""):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            setattr(fn, "__mcp_description__", description)
            return fn

        return decorator


class TestAnalysisToolManager(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = AnalysisToolManager(self.client)

    def test_catalog_shape_is_the_server_response(self):
        self.client.get.return_value = CATALOG

        catalog = self.manager.list(search="buffer", tag="analysis", page=2, page_size=5)

        self.assertEqual(catalog.total, 1)
        self.assertEqual(catalog.items[0].toolId, 5)
        self.assertEqual(catalog.items[0].tags, ["analysis", "buffer"])
        # Cards carry no per-parameter detail, so it must be None — not [].
        self.assertIsNone(catalog.items[0].params)
        self.client.get.assert_called_once_with(
            "/workflows/tools",
            params={"page": 2, "pageSize": 5, "q": "buffer", "tag": "analysis"},
        )

    def test_missing_surface_raises_and_does_not_fall_back(self):
        self.client.get.side_effect = GeopackAPIError(404, "Not found")

        with self.assertRaises(AnalysisSurfaceUnavailable) as raised:
            self.manager.list()

        self.assertEqual(raised.exception.status_code, 404)
        # No downgrade to list_workflows: exactly one call, then stop.
        self.client.get.assert_called_once()

    def test_manifest_refusal_becomes_a_param_error(self):
        self.client.get.side_effect = GeopackAPIError(
            400, "Parameter node 'bad' has no key"
        )

        with self.assertRaises(AnalysisParamError) as raised:
            self.manager.get(5)

        self.assertEqual(raised.exception.tool_id, 5)
        self.assertEqual(raised.exception.reason, "Parameter node 'bad' has no key")

    def test_manifest_404_and_403_keep_their_http_identity(self):
        for status in (403, 404):
            self.client.get.side_effect = GeopackAPIError(status, "nope")
            with self.assertRaises(GeopackAPIError) as raised:
                self.manager.get(5)
            self.assertNotIsInstance(raised.exception, AnalysisParamError)
            self.assertEqual(raised.exception.status_code, status)

    def test_run_wait_polls_then_reads_the_summary(self):
        self.client.post.return_value = SUBMISSION
        self.client.get.side_effect = [
            {"status": "running"},
            {"status": "succeeded"},
            SUMMARY,
        ]

        result = self.manager.run(5, {"distance": 100}, poll_interval_s=0.01)

        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.runId, 7)
        self.assertEqual(result.scalars, {"n2:count": 12})
        self.assertTrue(result.complete)
        # One submit, then status, status, summary.
        self.client.post.assert_called_once()
        self.assertEqual(self.client.get.call_count, 3)

    def test_run_leaves_attribution_to_the_client(self):
        self.client.post.return_value = SUBMISSION

        submission = self.manager.run(5, {"distance": 100}, wait=False)

        self.assertIsInstance(submission, WorkflowRunSubmitResponse)
        self.assertEqual(submission.workflowRunId, 7)
        # 030 §2 attributes the lane from X-Geoportal-Client, which the MCP
        # bootstrap sets as a CLIENT default (slice 016 §1.1). The manager must
        # not hard-code it: one source of truth for both sync and async lanes.
        self.assertNotIn("headers", self.client.post.call_args.kwargs)
        self.assertEqual(
            self.client.post.call_args.kwargs["json"],
            {"workflowId": 5, "params": {"distance": 100}},
        )
        # wait=false never polls.
        self.client.get.assert_not_called()

    def test_timeout_names_the_run_and_leaves_it_running(self):
        self.client.post.return_value = SUBMISSION
        self.client.get.return_value = {"status": "running"}

        with self.assertRaises(AnalysisTimeout) as raised:
            self.manager.run(5, {}, timeout_s=0)

        self.assertEqual(raised.exception.run_id, 7)
        self.assertIn("keeps going", str(raised.exception))
        # No cancel call: a polling budget must never kill the user's run.
        self.assertEqual(self.client.post.call_count, 1)


class TestAnalysisHandlers(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_selector_returns_the_manifest_not_the_catalog(self):
        # A REAL model, not a mock: the handler serializes through `to_jsonable`,
        # which dumps pydantic models (a duck-typed `model_dump` would not be
        # what production ever receives).
        self.client.analysis_tools.get.return_value = AnalysisTool(**MANIFEST)

        result = list_analysis_tools(self.client, tool_id=5)

        self.client.analysis_tools.get.assert_called_once_with(5)
        self.client.analysis_tools.list.assert_not_called()
        self.assertEqual(result["params"][0]["key"], "distance")

    def test_catalog_cards_omit_absent_parameter_detail(self):
        card = AnalysisTool(
            toolId=5,
            title="Well buffer",
            params=None,
            inputs=None,
            outputs=[],
        )
        self.client.analysis_tools.list.return_value = AnalysisToolListResponse(
            items=[card],
            total=1,
        )

        payload = list_analysis_tools(self.client)

        # A card saying `params: []` would read as "this tool takes no arguments".
        self.assertNotIn("params", payload["items"][0])
        self.assertNotIn("inputs", payload["items"][0])
        self.assertIn("outputs", payload["items"][0])

    def test_run_analysis_sanitizes_the_result(self):
        self.client.analysis_tools.run.return_value = AnalysisResult(**SUMMARY)

        payload = run_analysis(self.client, 5, {"distance": 100})

        self.assertEqual(payload["runId"], 7)
        self.assertEqual(find_forbidden_keys(payload), [])

    def test_get_analysis_result_reads_the_summary(self):
        self.client.analysis_tools.result.return_value = AnalysisResult(**SUMMARY)

        payload = get_analysis_result(self.client, 7)

        self.client.analysis_tools.result.assert_called_once_with(7)
        self.assertEqual(payload["datasets"][0]["name"], "Buffered wells")


class TestAnalysisSanitizer(unittest.TestCase):
    def test_payload_keys_are_dropped_at_any_depth(self):
        doctored = {
            "runId": 7,
            "artifacts": [{"artifactId": 3, "features": [{"a": 1}], "path": "/srv/x.gpkg"}],
            "datasets": [{"id": 41, "name": "Buffered", "geometry": {"type": "Point"}}],
        }

        cleaned = sanitize_analysis_result(doctored)

        self.assertEqual(find_forbidden_keys(cleaned), [])
        self.assertEqual(cleaned["artifacts"][0], {"artifactId": 3})
        self.assertEqual(cleaned["datasets"][0], {"id": 41, "name": "Buffered"})

    def test_the_callers_own_params_are_echoed_verbatim(self):
        # A workflow may legitimately declare a param keyed `geometry` or `path`;
        # stripping it would hide the caller's own input from them.
        payload = {"runId": 7, "params": {"geometry": "EPSG:3857", "path": "a/b"}}

        cleaned = sanitize_analysis_result(payload)

        self.assertEqual(cleaned["params"], {"geometry": "EPSG:3857", "path": "a/b"})


class TestAnalysisPolicy(unittest.TestCase):
    def test_run_analysis_is_declared_mutating(self):
        mcp = _FakeMCP()
        policy_tools.register(mcp)
        policy: Dict[str, Any] = mcp.tools["geopack_sdk_get_mcp_safety_policy"]()

        mutating: List[str] = list(policy["mutating_tools_require_host_consent"])
        self.assertIn("geopack_sdk_run_analysis", mutating)
        self.assertIn("consent", policy["mutating_tools_require_host_consent"]["geopack_sdk_run_analysis"].lower())

    def test_the_surface_adds_exactly_three_tools(self):
        from geopack_sdk_mcp.tools import analysis as analysis_tools

        mcp = _FakeMCP()
        analysis_tools.register(mcp)

        self.assertEqual(
            sorted(mcp.tools),
            [
                "geopack_sdk_get_analysis_result",
                "geopack_sdk_list_analysis_tools",
                "geopack_sdk_run_analysis",
            ],
        )

    def test_tool_descriptions_stay_inside_the_catalog_budget(self):
        from geopack_sdk_mcp.tools import analysis as analysis_tools

        mcp = _FakeMCP()
        analysis_tools.register(mcp)

        for name, fn in mcp.tools.items():
            description = getattr(fn, "__mcp_description__", "")
            self.assertLessEqual(len(description), 300, name)


if __name__ == "__main__":
    unittest.main()
