"""MCP tool: local map service + built-in viewer (slice 033, lanes A/B).

``geopack_sdk_show_map`` creates/updates a localhost-only service that proxies
portal data (using the MCP's own auth) and serves local files, then returns a
live **viewer URL** (an OpenLayers page) plus stable data/tile URLs. No map
image is produced.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import host_service_tool
from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_result, tool_result
from ..tool_handlers.maps import show_map
from ..tool_schema import (
    BasemapName,
    MapCenter,
    MapIdArg,
    MapLayers,
    MapRemoveLayers,
    MapReplaceLayers,
    MapStyle,
    MapTemplate,
    MapTitle,
    MapZoom,
    OpenBrowser,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=host_service_tool("geopack_sdk_show_map"),
        description=(
            "Create or update a LOCALHOST-ONLY map service and return a live **viewer URL** "
            "(viewerUrl) plus stable data/tile URLs ({serviceUrl, manifestUrl, "
            "layers[].dataUrl/tileUrl, accessToken}). The built-in viewer is an OpenLayers page "
            "that draws GeoJSON, MVT vector tiles, WMS/WMTS images and WFS vector data — the same "
            "layer families the portal serves — and is customizable via a template (title, "
            "basemaps, palette, layer style, panels). Axis order: `bbox` is "
            "[west,south,east,north] in EPSG:4326 and `view.center` is [lon,lat]; `style` recolours "
            "VECTOR layers only (a WMS/WMTS image is server-rendered), and layers without a fill "
            "rotate through `layerPalette` with a raster swatch in the legend. The page itself is an editable resource file "
            "(`viewerHtmlPath`, a `viewer.html` beside `templatePath`) so advanced users can drop "
            "in their own page. `portal-publication` layers need a real publication id (from "
            "list_datasets publicationsSummary), not a dataset id — it is validated at map-build. "
            "Raster portal-dataset layers are drawn as server-rendered PNG tiles when the dataset "
            "lives in a PostGIS raster table or an MBTiles container (auto `render:'rastertile'` — no "
            "publication or COG needed, and the dataset's saved colorMap/display is applied), or "
            "directly when `details.hasCOG` (auto `render:'cog'`). Only a raster with no tile "
            "source at all falls back to a vector footprint and warns; a raster WMS/WMTS "
            "publication still uses a portal-publication layer. Pass a per-layer `display` "
            "(`{displayType:'colorMap', band, colorMap:'grayscale|pseudocolor|fire|bluered|custom', "
            "minimum, maximum, customColorMap?}` or `{displayType:'RGB', RBand, GBand, BBand}`) to "
            "change a server-rendered raster's rendering; read the saved one from get_dataset's "
            "`symbology` (+ details.bands min/max). `display` is ignored for COG and MBTiles. "
            "Each layer's WGS84 extent is read from "
            "its source dataset when `bbox` is omitted. A page can also reference the URLs directly "
            "instead of embedding data. To change an existing map (map_id) pass replace_layers "
            "to rebuild it with exactly this call's layers, or remove_layers with layer ids to "
            "drop specific layers — otherwise layers append. Opt-in: requires "
            "GEOPACK_MCP_MAP_SERVICE=1. The portal credential never reaches the browser. No map "
            "image is rendered."
        ),
    )
    def geopack_sdk_show_map(
        ctx: Context[ServerSession, AppContext],
        title: MapTitle = None,
        layers: MapLayers = None,
        map_id: MapIdArg = None,
        open_browser: OpenBrowser = False,
        basemap: BasemapName = None,
        template: MapTemplate = None,
        style: MapStyle = None,
        center: MapCenter = None,
        zoom: MapZoom = None,
        replace_layers: MapReplaceLayers = False,
        remove_layers: MapRemoveLayers = None,
    ) -> CallToolResult:
        try:
            client = get_client(ctx)
            return tool_result(
                show_map(
                    client,
                    title=title,
                    layers=layers,
                    map_id=map_id,
                    open_browser=open_browser,
                    basemap=basemap,
                    template=template,
                    style=style,
                    center=center,
                    zoom=zoom,
                    replace_layers=replace_layers,
                    remove_layers=remove_layers,
                )
            )
        except Exception as exc:  # noqa: BLE001 - the error contract renders it
            return tool_error_result(exc)