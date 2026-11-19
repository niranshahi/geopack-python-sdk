"""Slice 022 — the MCP error contract: shape, codes, hints and ``isError``.

The contract is a **public** surface (§1.1): ``code`` values are stable, every
actionable 4xx carries a hint that names the next tool, and a payload with
``"error": true`` is returned inside a ``CallToolResult(isError=True)``.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import MagicMock

from mcp.types import CallToolResult

from geopack_sdk.exceptions import (
    AggregationInvalidArgs,
    DatasetReadOnly,
    EditConflict,
    GeopackAPIError,
    GeopackAuthError,
    GeopackTaskError,
    GeopackTimeoutError,
    PagedUnsupported,
    QuotaExceeded,
)
from geopack_sdk_mcp.errors import (
    ToolArgumentError,
    tool_error_payload,
    tool_error_result,
    tool_result,
)
from geopack_sdk_mcp.sanitize.dataset_details import normalize_details_level
from geopack_sdk_mcp.tool_handlers.datasets import aggregate_dataset, get_related_records


class ToolArgumentErrorTest(unittest.TestCase):
    def test_it_stays_a_value_error(self):
        # Pre-022 callers and tests catch ValueError; the class must stay one.
        self.assertIsInstance(ToolArgumentError("bad", key="k"), ValueError)

    def test_payload_names_the_argument_and_the_hint(self):
        exc = ToolArgumentError(
            "Unknown aggregate 'mode'",
            key="aggregates.0.aggregate",
            hint="Use count, sum, avg, min, max, median or percentile.",
        )

        payload = tool_error_payload(exc)

        self.assertEqual(payload["code"], "INVALID_ARGS")
        self.assertEqual(payload["type"], "ToolArgumentError")
        self.assertEqual(payload["invalidArgs"], ["aggregates.0.aggregate"])
        self.assertEqual(payload["hint"], "Use count, sum, avg, min, max, median or percentile.")
        self.assertNotIn("statusCode", payload)

    def test_a_validator_without_a_hint_still_gets_one(self):
        payload = tool_error_payload(ToolArgumentError("bad"))

        self.assertTrue(payload["hint"])
        self.assertEqual(payload["invalidArgs"], [])


class ApiErrorPayloadTest(unittest.TestCase):
    def test_the_shape_carries_code_type_status_and_a_hint(self):
        payload = tool_error_payload(GeopackAPIError(404, "Dataset 7 not found"))

        self.assertTrue(payload["error"])
        self.assertEqual(payload["type"], "GeopackAPIError")
        self.assertEqual(payload["code"], "NOT_FOUND")
        self.assertEqual(payload["statusCode"], 404)
        self.assertEqual(payload["status_code"], 404)  # pre-022 alias
        self.assertIn("geopack_sdk_list_datasets", payload["hint"])

    def test_the_server_code_wins_over_the_class_table(self):
        payload = tool_error_payload(
            PagedUnsupported(400, "cannot page", {"code": "PAGED_UNSUPPORTED_ALT"})
        )

        self.assertEqual(payload["code"], "PAGED_UNSUPPORTED_ALT")

    def test_423_derives_dataset_read_only(self):
        payload = tool_error_payload(DatasetReadOnly(423, "Dataset is archived"))

        self.assertEqual(payload["code"], "DATASET_READ_ONLY")
        self.assertIn("archived or locked", payload["hint"])

    def test_401_and_403_are_distinguished(self):
        unauthorized = tool_error_payload(GeopackAuthError(401, "no token"))
        forbidden = tool_error_payload(GeopackAuthError(403, "no access"))

        self.assertEqual(unauthorized["code"], "UNAUTHORIZED")
        self.assertIn("Re-authenticate", unauthorized["hint"])
        self.assertEqual(forbidden["code"], "FORBIDDEN")
        self.assertIn("Ask the user", forbidden["hint"])

    def test_aggregation_invalid_args_names_the_key(self):
        payload = tool_error_payload(
            AggregationInvalidArgs(
                400, "bad order key", {"code": "AGGREGATION_INVALID_ARGS", "key": "orderBy.0.key"}
            )
        )

        self.assertEqual(payload["code"], "AGGREGATION_INVALID_ARGS")
        self.assertEqual(payload["invalidArgs"], ["orderBy.0.key"])
        self.assertIn("geopack_sdk_get_dataset_schema", payload["hint"])

    def test_edit_conflict_keeps_the_issues_and_the_ref(self):
        payload = tool_error_payload(
            EditConflict(
                409,
                "conflict",
                {
                    "code": "EDIT_CONFLICT",
                    "issues": [{"index": 0, "reason": "stale"}],
                    "editRef": "ref-1",
                },
            )
        )

        self.assertEqual(payload["code"], "EDIT_CONFLICT")
        self.assertEqual(payload["issues"], [{"index": 0, "reason": "stale"}])
        self.assertEqual(payload["editRef"], "ref-1")

    def test_quota_exceeded_reports_the_dimension(self):
        payload = tool_error_payload(
            QuotaExceeded(
                403,
                "quota",
                {"code": "QUOTA_EXCEEDED", "dimension": "storage", "limit": 10, "used": 10},
            )
        )

        self.assertEqual(payload["code"], "QUOTA_EXCEEDED")
        self.assertEqual(payload["quota"]["dimension"], "storage")

    def test_task_timeout_and_unknown_errors_are_coded(self):
        task = tool_error_payload(GeopackTaskError("task-1", "failed", "boom"))
        timeout = tool_error_payload(GeopackTimeoutError("slow", timeout=5))
        unknown = tool_error_payload(ValueError("raw failure"))

        self.assertEqual(task["code"], "TASK_FAILED")
        self.assertEqual(task["task_id"], "task-1")
        self.assertIn("geopack_sdk_get_task", task["hint"])
        self.assertEqual(timeout["code"], "TIMEOUT")
        self.assertEqual(timeout["timeout"], 5)
        self.assertEqual(unknown["code"], "UNKNOWN_ERROR")
        self.assertEqual(unknown["type"], "ValueError")

    def test_no_credential_or_url_leaks_into_the_payload(self):
        payload = tool_error_payload(
            GeopackAPIError(
                500,
                "boom",
                {"token": "secret-token", "url": "http://internal/api/datasets"},
            )
        )

        rendered = json.dumps(payload)

        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("http://internal", rendered)


class ResultWrapperTest(unittest.TestCase):
    def test_an_error_result_sets_is_error_and_keeps_the_payload(self):
        result = tool_error_result(GeopackAPIError(500, "boom"))

        self.assertIsInstance(result, CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["code"], "SERVER_ERROR")
        self.assertEqual(json.loads(result.content[0].text)["code"], "SERVER_ERROR")

    def test_a_success_result_is_not_an_error(self):
        result = tool_result({"items": [], "hint": "pass an id"})

        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent, {"items": [], "hint": "pass an id"})

    def test_a_handler_error_dict_becomes_an_error_result(self):
        # The 020/021 handlers build their own dicts; the wrapper completes the
        # contract so every error carries code/statusCode/hint.
        result = tool_result(
            {
                "error": True,
                "type": "AggregationUnsupported",
                "status_code": 400,
                "message": "cannot aggregate",
            }
        )

        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["code"], "AGGREGATION_UNSUPPORTED")
        self.assertEqual(result.structuredContent["statusCode"], 400)
        self.assertTrue(result.structuredContent["hint"])

    def test_a_non_dict_payload_stays_text_only(self):
        result = tool_result([{"name": "a place"}])

        self.assertFalse(result.isError)
        self.assertIsNone(result.structuredContent)


class HandlerValidationTest(unittest.TestCase):
    """§1.2 — the refusals happen before any network call, with candidates."""

    def test_details_level_names_the_candidates(self):
        with self.assertRaises(ToolArgumentError) as caught:
            normalize_details_level("everything", default="lite")

        self.assertEqual(caught.exception.invalid_args, ["details_level"])
        self.assertIn("lite", caught.exception.hint)

    def test_percentile_without_p_never_reaches_the_client(self):
        client = MagicMock()

        with self.assertRaises(ToolArgumentError) as caught:
            aggregate_dataset(
                client, 5, aggregates=[{"aggregate": "percentile", "field": "area"}]
            )

        client.datasets.aggregate.assert_not_called()
        self.assertEqual(caught.exception.invalid_args, ["aggregates.0.p"])

    def test_an_unknown_aggregate_lists_the_enumeration(self):
        with self.assertRaises(ToolArgumentError) as caught:
            aggregate_dataset(MagicMock(), 5, aggregates=[{"aggregate": "mode"}])

        self.assertEqual(caught.exception.invalid_args, ["aggregates.0.aggregate"])
        self.assertIn("median", caught.exception.hint)

    def test_related_records_refuses_an_unknown_direction(self):
        with self.assertRaises(ToolArgumentError) as caught:
            get_related_records(MagicMock(), 5, "roads", [1], direction="sideways")

        self.assertEqual(caught.exception.invalid_args, ["direction"])
        self.assertIn('"backward"', caught.exception.hint)


class FastMcpSurfaceTest(unittest.TestCase):
    """End-to-end through FastMCP: the host can branch on ``isError``."""

    @classmethod
    def setUpClass(cls):
        from geopack_sdk_mcp.server import mcp

        cls.mcp = mcp

    def test_a_forced_failure_returns_is_error(self):
        # No lifespan client in this process: the tool fails before any network.
        result = asyncio.run(
            self.mcp.call_tool("geopack_sdk_get_dataset", {"dataset_id": 1})
        )

        self.assertIsInstance(result, CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["error"], True)
        self.assertTrue(result.structuredContent["code"])

    def test_the_policy_tool_never_fails(self):
        result = asyncio.run(self.mcp.call_tool("geopack_sdk_get_mcp_safety_policy", {}))

        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["version"], 2)


if __name__ == "__main__":
    unittest.main()
