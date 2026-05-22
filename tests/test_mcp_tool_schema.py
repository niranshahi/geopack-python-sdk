"""Ensure MCP tools expose per-parameter JSON Schema descriptions."""

from __future__ import annotations

import unittest

from geopack_sdk_mcp.server import mcp


class TestMcpToolSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = {t.name: t for t in mcp._tool_manager.list_tools()}  # noqa: SLF001

    def _prop(self, tool_name: str, param: str) -> dict:
        tool = self.tools[tool_name]
        props = tool.parameters.get("properties", {})
        self.assertIn(param, props, f"{tool_name} missing property {param}")
        return props[param]

    def test_upload_dataset_metadata_has_description(self):
        meta = self._prop("geopack_sdk_upload_dataset", "metadata")
        desc = meta.get("description", "")
        self.assertIn("name", desc.lower())
        self.assertTrue(len(desc) > 20)

    def test_upload_dataset_tool_description_mentions_chain(self):
        tool = self.tools["geopack_sdk_upload_dataset"]
        self.assertIn("wait_for_task", tool.description.lower())

    def test_get_workflow_include_params_has_description(self):
        prop = self._prop("geopack_sdk_get_workflow", "include_params")
        self.assertIn("parameters", prop.get("description", "").lower())

    def test_list_datasets_bbox_has_description(self):
        prop = self._prop("geopack_sdk_list_datasets", "bbox")
        self.assertIn("geocode", prop.get("description", "").lower())

    def test_all_tools_have_description(self):
        for name, tool in self.tools.items():
            self.assertTrue(
                tool.description and tool.description.strip(),
                f"{name} missing tool description",
            )

    def test_all_tool_properties_have_descriptions(self):
        skip = {"ctx"}  # injected by FastMCP, not in public schema
        for name, tool in self.tools.items():
            for param, spec in tool.parameters.get("properties", {}).items():
                if param in skip:
                    continue
                desc = spec.get("description", "")
                self.assertTrue(
                    desc and str(desc).strip(),
                    f"{name}.{param} missing description",
                )


if __name__ == "__main__":
    unittest.main()
