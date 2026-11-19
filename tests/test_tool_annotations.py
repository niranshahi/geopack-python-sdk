"""Slice 022 — tool annotations, output schemas and client attribution.

The annotation table is re-derived from the policy registry: a tool that is not
annotated, or an annotation that contradicts ``TOOL_POLICY``, fails here (same
pattern as the 021 policy-completeness test).
"""

from __future__ import annotations

import pathlib
import unittest

import geopack_sdk_mcp
from geopack_sdk import GeopackClient
from geopack_sdk_mcp.annotations import (
    NON_IDEMPOTENT_TOOLS,
    OPEN_WORLD_TOOLS,
    TITLES,
)
from geopack_sdk_mcp.auth_bootstrap import MCP_CLIENT_HEADERS
from geopack_sdk_mcp.tools.policy import TOOL_POLICY

STRUCTURED_OUTPUT_TOOLS = {
    "geopack_sdk_get_dataset_schema",
    "geopack_sdk_aggregate_dataset",
    "geopack_sdk_get_quota_summary",
    "geopack_sdk_list_workflow_runs",
    "geopack_sdk_list_generated_files",
}

PASS_THROUGH_TOOLS = (
    "geopack_sdk_get_dataset",
    "geopack_sdk_query_dataset",
    "geopack_sdk_submit_edit_document",
    "geopack_sdk_run_analysis",
)


class AnnotationSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from geopack_sdk_mcp.server import mcp

        cls.tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}  # noqa: SLF001

    def test_titles_cover_the_registered_surface(self):
        self.assertEqual(set(TITLES), set(self.tools))

    def test_every_tool_carries_all_four_hints(self):
        for name, tool in self.tools.items():
            annotations = tool.annotations
            self.assertIsNotNone(annotations, f"{name} has no annotations")
            self.assertTrue(annotations.title, f"{name} has no title")
            for field in (
                "readOnlyHint",
                "destructiveHint",
                "idempotentHint",
                "openWorldHint",
            ):
                self.assertIsNotNone(getattr(annotations, field), f"{name}.{field}")

    def test_the_hints_agree_with_the_policy_registry(self):
        for name, tool in self.tools.items():
            entry = TOOL_POLICY[name]
            read_only = not entry["mutating"] and not entry.get("localWrites")
            annotations = tool.annotations
            self.assertEqual(annotations.readOnlyHint, read_only, name)
            # A read that mints a new artifact (export) is not idempotent.
            self.assertEqual(
                annotations.idempotentHint,
                read_only and name not in NON_IDEMPOTENT_TOOLS,
                name,
            )
            self.assertEqual(annotations.openWorldHint, name in OPEN_WORLD_TOOLS, name)
            self.assertEqual(
                annotations.destructiveHint,
                name == "geopack_sdk_submit_edit_document",
                name,
            )

    def test_only_the_edit_lane_is_destructive(self):
        destructive = sorted(
            name for name, tool in self.tools.items() if tool.annotations.destructiveHint
        )

        self.assertEqual(destructive, ["geopack_sdk_submit_edit_document"])

    def test_cancel_task_is_a_state_change_not_data_loss(self):
        annotations = self.tools["geopack_sdk_cancel_task"].annotations

        self.assertTrue(annotations.destructiveHint is False)
        self.assertTrue(annotations.readOnlyHint is False)

    def test_the_five_stable_read_lanes_declare_an_output_schema(self):
        structured = {name for name, tool in self.tools.items() if tool.output_schema}

        self.assertEqual(structured, STRUCTURED_OUTPUT_TOOLS)

    def test_pass_through_payloads_declare_no_schema(self):
        for name in PASS_THROUGH_TOOLS:
            self.assertIsNone(self.tools[name].output_schema, name)


class AttributionTest(unittest.TestCase):
    def test_the_header_has_a_single_definition(self):
        root = pathlib.Path(geopack_sdk_mcp.__file__).parent
        hits = sorted(
            path.name
            for path in root.rglob("*.py")
            if "X-Geoportal-Client" in path.read_text(encoding="utf-8")
        )

        self.assertEqual(hits, ["auth_bootstrap.py"])

    def test_the_mcp_client_carries_the_header(self):
        client = GeopackClient(
            "http://localhost:3000/api", default_headers=dict(MCP_CLIENT_HEADERS)
        )

        self.assertEqual(client.default_headers["X-Geoportal-Client"], "mcp")


if __name__ == "__main__":
    unittest.main()
