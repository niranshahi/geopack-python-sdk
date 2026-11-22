"""MCP tool: local geometry operations (slice 033, Lane C).

One family tool (ADR-0011) with an ``op`` argument. Pure local compute — no
portal call, no Geoportal reference (N4). Every result echoes provenance.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import read_tool
from ..auth_bootstrap import AppContext
from ..errors import tool_error_result, tool_result
from ..tool_handlers.geometry import geometry_op
from ..tool_schema import (
    GeometryBSide,
    GeometryBText,
    GeometryCoordinates,
    GeometryDissolve,
    GeometryDistance,
    GeometryFormat,
    GeometryGeoJson,
    GeometryGroupBy,
    GeometryIterations,
    GeometryMaxVertices,
    GeometryMerge,
    GeometryMethod,
    GeometryOpName,
    GeometryOutputWkid,
    GeometryOverlayOp,
    GeometrySegments,
    GeometryText,
    GeometryTolerance,
    GeometryTypeName,
    GeometryUnits,
    GeometryWkid,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=read_tool("geopack_sdk_geometry_op"),
        description=(
            "Run one LOCAL geometry op on supplied GeoJSON/WKT (no portal, no map image): "
            "buffer, overlay (union/intersection/difference/xor/clip), convex_hull, envelope, "
            "dissolve, simplify, validate, fix, convert (GeoJSON<->WKT), project, measure, "
            "distance, nearest, line_between, point_on_surface, smooth, create, describe. "
            "Metric ops auto-project to a local UTM; results are WGS84 with provenance "
            "(engine, methodUsed, crsUsed). Empty results and engine failures are coded errors."
        ),
    )
    def geopack_sdk_geometry_op(
        ctx: Context[ServerSession, AppContext],
        op: GeometryOpName,
        geojson: GeometryGeoJson = None,
        text: GeometryText = None,
        b: GeometryBSide = None,
        b_text: GeometryBText = None,
        overlay_op: GeometryOverlayOp = None,
        distance: GeometryDistance = None,
        units: GeometryUnits = None,
        method: GeometryMethod = None,
        wkid: GeometryWkid = None,
        segments: GeometrySegments = None,
        dissolve: GeometryDissolve = None,
        group_by: GeometryGroupBy = None,
        tolerance: GeometryTolerance = None,
        iterations: GeometryIterations = None,
        fmt: GeometryFormat = None,
        output_wkid: GeometryOutputWkid = None,
        geometry_type: GeometryTypeName = None,
        coordinates: GeometryCoordinates = None,
        max_vertices: GeometryMaxVertices = None,
        merge: GeometryMerge = None,
    ) -> CallToolResult:
        _ = ctx  # local compute: no portal client needed (N4)
        try:
            return tool_result(
                geometry_op(
                    op,
                    geojson=geojson,
                    text=text,
                    b=b,
                    b_text=b_text,
                    overlay_op=overlay_op,
                    distance=distance,
                    units=units,
                    method=method,
                    wkid=wkid,
                    segments=segments,
                    dissolve=dissolve,
                    group_by=group_by,
                    tolerance=tolerance,
                    iterations=iterations,
                    fmt=fmt,
                    output_wkid=output_wkid,
                    geometry_type=geometry_type,
                    coordinates=coordinates,
                    max_vertices=max_vertices,
                    merge=merge,
                )
            )
        except Exception as exc:  # noqa: BLE001 - the error contract renders it
            return tool_error_result(exc)