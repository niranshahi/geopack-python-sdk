"""Chart tool (issue 5 / SDK-011): bar/line/pie from tabular rows, no dependency."""

from __future__ import annotations

import os
import tempfile
import unittest

from geopack_sdk_mcp.errors import ToolArgumentError, tool_result_with_image
from geopack_sdk_mcp.tool_handlers.charts import render_chart

try:  # the optional PNG engine (geopack-sdk[charts])
    import cairosvg  # noqa: F401

    _HAS_CAIRO = True
except Exception:  # noqa: BLE001
    _HAS_CAIRO = False

ROWS = [
    {"Landuse_Group": "1", "aggregate_count": 120},
    {"Landuse_Group": "2", "aggregate_count": 30},
    {"Landuse_Group": "5", "aggregate_count": 26},
]


class RenderChartTest(unittest.TestCase):
    def test_a_bar_chart_returns_an_svg_and_the_points(self):
        result = render_chart(ROWS, chart_type="bar", category="Landuse_Group",
                              value="aggregate_count")
        self.assertEqual(result.mime_type, "image/svg+xml")
        svg = result.body.decode("utf-8")
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.rstrip().endswith("</svg>"))
        self.assertIn("<rect", svg)
        self.assertEqual(result.payload["chartType"], "bar")
        self.assertEqual(result.payload["categories"], ["1", "2", "5"])
        self.assertEqual([p["value"] for p in result.payload["points"]], [120.0, 30.0, 26.0])
        self.assertEqual(result.payload["valueRange"], [26.0, 120.0])

    def test_a_line_chart_draws_a_polyline(self):
        result = render_chart(ROWS, chart_type="line", category="Landuse_Group",
                              value="aggregate_count")
        self.assertIn("<polyline", result.body.decode("utf-8"))
        self.assertEqual(result.payload["chartType"], "line")

    def test_a_pie_chart_draws_slices(self):
        result = render_chart(ROWS, chart_type="pie", category="Landuse_Group",
                              value="aggregate_count")
        self.assertIn("<path", result.body.decode("utf-8"))
        self.assertEqual(result.payload["chartType"], "pie")

    def test_a_series_field_splits_the_chart(self):
        rows = [
            {"month": "Jan", "kind": "a", "n": 1},
            {"month": "Jan", "kind": "b", "n": 2},
            {"month": "Feb", "kind": "a", "n": 3},
            {"month": "Feb", "kind": "b", "n": 4},
        ]
        result = render_chart(rows, chart_type="bar", category="month", value="n", series="kind")
        self.assertEqual(result.payload["seriesNames"], ["a", "b"])
        self.assertEqual(len(result.payload["points"]), 4)

    def test_non_numeric_rows_are_skipped_and_reported(self):
        rows = ROWS + [{"Landuse_Group": "9", "aggregate_count": "n/a"}]
        result = render_chart(rows, category="Landuse_Group", value="aggregate_count")
        self.assertEqual(result.payload["skippedRows"], 1)
        self.assertEqual(result.payload["pointCount"], 3)

    def test_a_title_is_rendered_and_escaped(self):
        result = render_chart(ROWS, category="Landuse_Group", value="aggregate_count",
                              title="Areas <top>")
        svg = result.body.decode("utf-8")
        self.assertIn("Areas &lt;top&gt;", svg)

    def test_more_than_the_cap_is_truncated_and_disclosed(self):
        rows = [{"c": f"v{i}", "n": i} for i in range(250)]
        result = render_chart(rows, category="c", value="n")
        self.assertEqual(result.payload["pointCount"], 200)
        self.assertEqual(result.payload["truncatedPoints"], 50)

    def test_empty_rows_is_an_argument_error(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            render_chart([], category="c", value="n")
        self.assertEqual(ctx.exception.invalid_args, ["rows"])

    def test_no_numeric_values_is_an_argument_error(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            render_chart([{"c": "a", "n": "x"}], category="c", value="n")
        self.assertEqual(ctx.exception.invalid_args, ["value"])

    def test_an_unknown_chart_type_is_refused(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            render_chart(ROWS, chart_type="radar", category="Landuse_Group",
                         value="aggregate_count")
        self.assertEqual(ctx.exception.invalid_args, ["chart_type"])

    def test_a_pie_exposes_labelled_slices_with_percentages(self):
        result = render_chart(ROWS, chart_type="pie", category="Landuse_Group",
                              value="aggregate_count")
        self.assertEqual([s["label"] for s in result.payload["slices"]], ["1", "2", "5"])
        self.assertAlmostEqual(sum(s["percent"] for s in result.payload["slices"]), 100.0, places=1)
        # The SVG itself carries the labels (a renderer shows them).
        self.assertIn("1 —", result.body.decode("utf-8"))

    def test_save_path_writes_the_file_and_reports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "chart.svg")
            result = render_chart(ROWS, category="Landuse_Group", value="aggregate_count",
                                  save_path=target)
            self.assertTrue(result.payload["saved"])
            self.assertEqual(result.payload["savedPath"], os.path.realpath(target))
            with open(target, "rb") as handle:
                self.assertTrue(handle.read().startswith(b"<svg"))

    def test_no_save_path_writes_nothing(self):
        result = render_chart(ROWS, category="Landuse_Group", value="aggregate_count")
        self.assertFalse(result.payload["saved"])
        self.assertTrue(result.payload["saveSkipped"])

    @unittest.skipIf(_HAS_CAIRO, "cairosvg installed; the png path is available")
    def test_png_without_the_optional_engine_is_a_coded_refusal(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            render_chart(ROWS, category="Landuse_Group", value="aggregate_count", format="png")
        self.assertEqual(ctx.exception.invalid_args, ["format"])

    def test_an_unknown_format_is_refused(self):
        with self.assertRaises(ToolArgumentError) as ctx:
            render_chart(ROWS, category="Landuse_Group", value="aggregate_count", format="pdf")
        self.assertEqual(ctx.exception.invalid_args, ["format"])

    def test_the_result_travels_as_an_image_block_plus_text(self):
        result = render_chart(ROWS, category="Landuse_Group", value="aggregate_count")
        call = tool_result_with_image(result.payload, result.body, result.mime_type)
        self.assertFalse(call.isError)
        self.assertEqual(call.content[0].type, "image")
        self.assertEqual(call.content[0].mimeType, "image/svg+xml")
        self.assertEqual(call.content[1].type, "text")


if __name__ == "__main__":
    unittest.main()