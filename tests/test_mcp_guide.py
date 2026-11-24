"""The server's self-documentation: MCP `instructions` + the `geopack://guide` resource."""

from __future__ import annotations

import asyncio
import unittest

from geopack_sdk_mcp.guide import (
    GUIDE_URI,
    PURPOSES,
    SERVER_INSTRUCTIONS,
    TOOL_INVENTORY_TOKEN,
    build_guide_markdown,
    default_guide_markdown,
    default_instructions,
    tool_inventory,
)
from geopack_sdk_mcp.tools.policy import TOOL_POLICY


class GuideSourceTest(unittest.TestCase):
    def test_the_guide_is_backed_by_an_editable_markdown_file(self):
        # The prose lives in content/guide.md; only the tool list is generated.
        source = default_guide_markdown()
        self.assertIn("# Geopack SDK MCP — usage guide", source)
        self.assertIn(TOOL_INVENTORY_TOKEN, source)
        # The served guide has the token substituted out.
        self.assertNotIn(TOOL_INVENTORY_TOKEN, build_guide_markdown())

    def test_the_instructions_are_backed_by_a_markdown_file(self):
        self.assertEqual(SERVER_INSTRUCTIONS, default_instructions())
        self.assertIn("discover-first", SERVER_INSTRUCTIONS)


class InstructionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from geopack_sdk_mcp.server import mcp

        cls.mcp = mcp

    def test_instructions_are_set_on_the_server(self):
        # Clients that support MCP instructions inject this at connect; it must exist
        # and be exactly what the guide module declares (one source of truth).
        self.assertTrue(self.mcp.instructions)
        self.assertEqual(self.mcp.instructions, SERVER_INSTRUCTIONS)

    def test_instructions_name_the_core_flow_and_the_guide(self):
        for needle in (
            "geopack_sdk_list_datasets",
            "geopack_sdk_get_dataset_schema",
            "geopack_sdk_query_dataset",
            "geopack_sdk_show_map",
            "geopack_sdk_get_mcp_safety_policy",
            GUIDE_URI,
        ):
            self.assertIn(needle, SERVER_INSTRUCTIONS)


class GuideTextTest(unittest.TestCase):
    def test_every_registered_tool_has_a_recorded_purpose(self):
        # A new tool cannot ship without a guide line (the completeness guard).
        self.assertEqual(set(PURPOSES), set(TOOL_POLICY))

    def test_the_inventory_covers_every_registered_tool(self):
        names = {name for _group, name, _purpose in tool_inventory()}
        self.assertEqual(names, set(TOOL_POLICY))

    def test_the_guide_lists_every_registered_tool(self):
        guide = build_guide_markdown()
        for name in TOOL_POLICY:
            self.assertIn(f"`{name}`", guide)

    def test_the_guide_keeps_the_consent_and_axis_order_rules(self):
        guide = build_guide_markdown()
        self.assertIn("consent", guide.lower())
        self.assertIn("[lon, lat]", guide)
        self.assertIn("geopack_sdk_get_mcp_safety_policy", guide)


class GuideResourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from geopack_sdk_mcp.server import mcp

        cls.mcp = mcp

    def test_the_guide_resource_is_registered(self):
        uris = {str(resource.uri) for resource in self.mcp._resource_manager.list_resources()}
        self.assertIn(GUIDE_URI, uris)

    def test_reading_the_guide_returns_the_markdown(self):
        contents = asyncio.run(self.mcp.read_resource(GUIDE_URI))
        self.assertTrue(contents)
        self.assertIn("# Geopack SDK MCP — usage guide", contents[0].content)
        self.assertIn("## Tool inventory", contents[0].content)


if __name__ == "__main__":
    unittest.main()
