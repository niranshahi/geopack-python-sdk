"""MCP tool: render a chart from tabular data (issue 5 / SDK-011).

Pure local compute (no portal call), like ``geometry_op``: it turns rows the agent
already has into a self-contained SVG chart delivered inline. This closes the
"no charting" gap where ``aggregate_dataset`` returned numbers and ``show_map``
drew a map, but nothing drew a statistical chart.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import local_write_tool
from ..auth_bootstrap import AppContext
from ..errors import tool_error_result, tool_result_with_image
from ..tool_handlers.charts import render_chart
from ..tool_schema import (
    ChartCategoryField,
    ChartFormat,
    ChartRows,
    ChartSavePath,
    ChartSeriesField,
    ChartTitle,
    ChartType,
    ChartValueField,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=local_write_tool("geopack_sdk_render_chart"),
        description=(
            "Render a BAR, LINE or PIE chart from tabular rows as a self-contained SVG image "
            "(returned inline as image/svg+xml, with the same points — and, for a pie, labelled "
            "`slices` with percentages — echoed in the payload). Local compute: no portal call. "
            "Feed it rows you already have (e.g. `geopack_sdk_aggregate_dataset`'s `rows`): set "
            "`category` to the label field and `value` to the numeric field; an optional `series` "
            "field splits a bar/line chart into multiple series. Pass `save_path` to also write "
            "the chart as a file, and `format:'png'` to rasterise it (needs the optional cairosvg "
            "engine; `svg` needs nothing and is faithful for Persian labels). THIS is the charting "
            "lane — `show_map` draws a map, not a statistical chart."
        ),
    )
    def geopack_sdk_render_chart(
        ctx: Context[ServerSession, AppContext],
        rows: ChartRows,
        category: ChartCategoryField,
        value: ChartValueField,
        chart_type: ChartType = "bar",
        series: ChartSeriesField = None,
        title: ChartTitle = None,
        format: ChartFormat = "svg",
        save_path: ChartSavePath = None,
    ) -> CallToolResult:
        _ = ctx  # local render: no portal client needed
        try:
            result = render_chart(
                rows,
                chart_type=chart_type,
                category=category,
                value=value,
                series=series,
                title=title,
                format=format,
                save_path=save_path,
            )
            return tool_result_with_image(result.payload, result.body, result.mime_type)
        except Exception as exc:  # noqa: BLE001 - coded INVALID_ARGS / tool error
            return tool_error_result(exc)