# Changelog

All notable changes to `geopack-sdk` and the bundled MCP server (`geopack_sdk_mcp`).
Append-only; newest first.

## 0.12.9 — 2026-11-23

Responsive viewer layout (slice 033). Viewer-only; no new tool (31), no new
Python dependency.

### Changed

- **Fixed the box-sizing reset** in the viewer shell (it was malformed — a
  missing `*`), the root cause of the panel's controls overflowing.
- **Two-line layer rows** — checkbox + name (ellipsized, with tooltip) + a zoom
  button on the first line, the opacity slider full-width on the second, so the
  slider and zoom control never overflow a narrow panel.
- **Collapsible sections** — Background / Layers / Legend are `<details>` blocks
  (open by default) with a chevron.
- **Responsive panel** — `min(300px, 92vw)`; on `max-width: 640px` it becomes a
  bottom sheet and the header shrinks; the identify popup is width-capped.
- **Zoom icon** — a monochrome magnifier SVG (clearer than the corner-arrows).
- **Coordinate status bar** — `#statusbar` shows the live WGS84 Lon/Lat under the
  pointer (a dedicated container for future tools such as a measure readout).

### Verification

- Full suite **781 tests** OK (was 780; +1 responsive-layout viewer test).

Touched files:
- `src/geopack_sdk_mcp/maps/templates/default/viewer.html`
- `src/geopack_sdk_mcp/maps/templates/default/viewer.js`
- `tests/test_map_viewer.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.12.8 — 2026-11-23

Shared viewer runtime, COG raster layers, click identify and zoom-to-layer
(slice 033 §13/§14). No new tool (31), no new Python dependency; the viewer now
also loads the pinned geotiff.js bundle in the browser (for COG).

### Added

- **Shared viewer runtime** — the page's drawing logic moved out of
  `viewer.html` into `templates/default/viewer.js` (served at
  `/viewer/asset/viewer.js`; a Tier-2 `viewer.js` overrides it), so several page
  shells share one runtime. `viewer.html` is now markup + a `window.GP_VIEWER`
  bootstrap. The COG lane works because the page loads the geotiff UMD bundle
  (global `GeoTIFF`) **before** OpenLayers — the legacy `ol.js` does not embed it
  (fixes `GeoTIFF is not defined`).
- **COG raster lane** — a raster dataset with `details.hasCOG` gets
  `render: 'cog'`; the manifest exposes a Range-capable `cogUrl`
  (`/cog/{datasetId}` proxies `GET /datasets/{id}/cog`, forwarding `Range` /
  `Content-Range`); the viewer draws it with `ol/source.GeoTIFF` +
  `ol/layer.WebGLTile`.
- **Click identify** (client-side, mirroring the frontend) — (I1) vector features
  (`geojson`/`mvt`/`wfs`) with field **aliases + coded-value domains**
  (`layer.fields` from `details.fields`); (I2) WMS/WMTS publications via **OGC
  GetFeatureInfo** through the proxy (`QUERY_LAYERS` from `identifyWmsLayers`,
  WMS 1.1.1 `SRS=EPSG:4326`, `INFO_FORMAT=application/json`); (I3) COG **pixel
  value** at the click via `WebGLTile.getData(pixel)` with band metadata
  (`rasterBands`; no-data sentinel masked).
- **Zoom to layer** — a per-row button in the layer list fits the view to the
  layer's manifest `bbox` (fallback: the vector source extent).

### Fixed

- **WMS GetFeatureInfo 401** — the request appended a second `?` after the
  `?t=` token (`...?t=TOKEN?SERVICE=...`), truncating the token; it now extends
  the query with `&`.

### Verification

- Full suite **780 tests** OK (was 762). Live-verified on dataset 1577 (WMS
  GetFeatureInfo returns parcels; COG 1949 renders and reports pixel values).

Touched files:
- `src/geopack_sdk_mcp/maps/templates/default/viewer.js` (new)
- `src/geopack_sdk_mcp/maps/templates/default/viewer.html`
- `src/geopack_sdk_mcp/maps/viewer.py`
- `src/geopack_sdk_mcp/maps/service.py`
- `src/geopack_sdk_mcp/maps/sources.py`
- `src/geopack_sdk_mcp/maps/manifest.py`
- `src/geopack_sdk_mcp/tool_handlers/maps.py`
- `src/geopack_sdk_mcp/tool_schema.py`
- `tests/test_map_service.py`, `tests/test_map_tools.py`, `tests/test_map_viewer.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.12.7 — 2026-11-23

Portable layer-style model, Phase 2 (slice 033 §12.2/§12.3 F2+F4). A dataset's
saved ESRI renderer is now **translated** into a renderer-agnostic spec and
**applied** to the layer — the map shows the portal's intended colours instead of
a palette colour, and the legend is built from the same spec (owner request). No
new tool (31), no new dependency.

### Added

- **`sanitize/style_spec.py`** — `esri_renderer_to_spec` (uniqueValue →
  `unique[]`, classBreaks → `breaks[]`, simple → `simple`; ESRI `[r,g,b,a]`
  colours → `#rrggbb` + `opacity`; esriSFS/esriSLS/esriSMS → polygon/line/point)
  and `dataset_style_spec` (reads `display.esri.renderer` with the frontend's
  precedence; vector/table only).
- **`show_map` applies the derived spec** — a `portal-dataset` layer with a
  translatable saved renderer and no explicit `style` now carries `symbology`
  (the portable spec) in its manifest; an explicit `style` still wins. The
  disclosure warning from 0.12.5 is emitted only when the saved style is **not**
  applied (a raster display block, an untranslated renderer family, or a styled
  publication — the latter two still name the portal-publication route).
- **Viewer style function + legend block** — the OpenLayers vector style is now a
  **function** (uniqueValue matches a feature property, classBreaks buckets a
  numeric value, simple is constant); the legend draws one swatch row per class
  from the **same** spec, so the drawn map and the legend cannot disagree.
- **Caller `symbology` on a layer** — a layer spec may carry a complete portable
  spec (`unique`/`breaks`) or a shorthand the handler derives from the layer's own
  data: `{type:'uniqueValue', field}` (one colour per distinct value) and
  `{type:'classBreaks', field, classes}` (quantile breaks, default 5). Caller
  symbology wins over the dataset's saved renderer, so one dataset can be shown
  styled several ways.
- **Coded-value domain labels** — a field's `details.fields[].domain`
  (`{type:'codedValues', items:[{code, value}]}`) is read so the legend shows the
  human value (e.g. «اوقاف») instead of the raw code, and the field `alias`
  (e.g. «مالکیت») is the legend title. Applies to both derived and saved renderers
  (a saved renderer label is used when present; the domain is the fallback).

### Fixed

- **Derived symbology was overridden by the palette** — `_assign_layer_palette`
  ran after the symbology was attached and set a palette `style`, which the
  viewer lets win over `symbology`, so the map stayed one flat colour while the
  legend showed every class. A layer that carries `symbology` is now skipped by
  the palette, and the viewer builds its legend from the same `appliedSym` the
  style function uses.

## 0.12.6 — 2026-11-23

Viewer download progress (slice 033, Lane B follow-up). A whole-dataset GeoJSON
(`limit:0`) can be tens of MB and, with the default OpenLayers url loader, the
viewer looked frozen until it finished (owner report on dataset 1577). No new
tool (31), no new dependency.

### Added

- **Per-layer download progress in the viewer legend** — a `geojson` layer is now
  streamed by the page (`fetch` + `ReadableStream`), so its legend row shows a
  spinner, then a byte/percentage bar from `Content-Length`, until the feature
  collection is on the map. The layer list/legend behaviour is unchanged
  otherwise; MVT/WMS/WMTS/XYZ layers keep their built-in loaders.

## 0.12.5 — 2026-11-23

Dataset saved-symbology disclosure (slice 033 Phase 1). An agent could not tell
that a dataset carries its own rendering, so `show_map`/`portal-dataset` silently
used the generic viewer palette and the official symbology was never discovered
(owner report about dataset 1577). The MCP now **detects and discloses** it. No
new tool (31), no new dependency.

### Added

- **A `symbology` summary on every dataset record** (`get_dataset` and
  `list_datasets`, all detail levels incl. `lite`), resolved with the SAME
  precedence as the frontend (`displayMigration.getDisplaySettings` +
  `getDatasetEsriDisplay`): vector/table `details.display.esri` (legacy
  `details.esri.display`/`details.esri`, generic `display.default`) and raster
  flat `details.display` (`displayType` RGB/colorMap). It reports
  `hasSavedStyle`, `kind` (`vector|raster|none`), `rendererFamily`, `rendererType`
  (+friendly `rendererLabel`), `fields`, `classCount`, `labelingCount`, and for
  rasters `rasterDisplayType`/`bands`/`band`/`colorMap`.
- **`styledPublications` (opt-in `fields`)** — the dataset's publications, each
  flagged `hasStyle` (a set `canonicalStyleRevision` or a `configuration.styleOverride`),
  naming the publication that renders the official symbology. Computed on demand
  (it costs one publications call).
- **`show_map` disclosure** — a `portal-dataset` layer whose dataset has a saved
  symbology (or, failing that, a styled publication) now adds a
  `templateWarnings` entry telling the agent to use `kind:'portal-publication'`
  (or an explicit style) instead of the generic palette. An explicitly styled
  layer is not warned.
- New `sanitize/dataset_symbology.py` (`summarise_symbology`,
  `styled_publications`, resolvers). Live-verified on dataset 1577
  (`uniqueValue` on `Landuse_Group`, 24 classes; publications 204/202 styled).
- **Per-layer `limit` on a `portal-dataset` layer** — caps the features a GeoJSON
  layer loads (`default 1000`; `0` = the **whole** dataset, sent with no pagination
  limit). Fixes reports that a large dataset (1577: 18,648 features) appeared
  sparse at 1,000. The MCP does **not** switch renderer or truncate silently: when a
  dataset exceeds the cap it adds a `templateWarnings` entry naming the totals and
  the levers (`limit:0` for the full GeoJSON, keeping the saved symbology; or
  `render:'mvt'` for tiled full coverage) so the **agent** chooses (and can ask the
  user). `query_dataset_geojson` gained `limit<=0` unbounded semantics;
  `dataset_feature_count` reads the server COUNT via `query_paged`.

## 0.12.4 — 2026-11-22

Client-side CRS verification (slice 033 robustness). A fifth live-QA report showed
the portal can silently ignore `out_srid`/`outSRID=4326` and return native
projected coordinates while the payload still claims the requested CRS. The
dataset and map lanes now **verify** the answer and **repair** it locally. No new
tool (31); `pyproj` is an optional, lazily-imported extra.

### Fixed

- **The output CRS is now verified, not assumed.** `query_dataset` reads
  `outSridApplied` from the CRS **actually in the payload**: if the first position
  is decisively non-lon/lat (projected metres) and the dataset's own SRID is known,
  the geometry is reprojected to EPSG:4326 locally with `pyproj` and the repair is
  reported in `crsNote`; if it cannot be repaired (unknown source CRS, or `pyproj`
  absent), `crsNote` says so and `outSridApplied` is omitted — metre coordinates
  are never echoed as WGS84. The map lane (`show_map`'s `portal-dataset` layers)
  performs the same repair so a projected dataset still renders in the viewer.
- **New module `geopack_sdk_mcp/crs_utils.py`** — `parse_epsg`, `srid_from_dataset`,
  `looks_wgs84`, `reproject_feature_collection`, `honor_output_srid`. It sits
  outside `geometry/` and imports `pyproj` lazily, so the map/dataset lanes keep
  working where the optional geometry extras are absent (degrade to the `crsNote`
  warning, never a crash). `dataset_info` now shares `srid_from_dataset`.

## 0.12.3 — 2026-11-22

Fourth live-QA round (slice 033). `query_dataset` now answers in WGS84 by
default (both query lanes), `geo_extent` is a requestable lightweight field, and
the docs cover the new manifest/argument fields. No new tool (31), no new
dependency.

### Changed

- **`query_dataset` defaults to `out_srid=4326`.** A dataset stored in a
  projected/native CRS used to return metre coordinates unless the caller asked
  otherwise, so any client plotting them as lon/lat saw nothing. The default is
  now WGS84 (map-friendly); `out_srid` overrides it. The **query-DSL lane** also
  applies it now (it used to ignore `out_srid`), while an explicit
  `projection.outSRID` still wins. The result echoes `outSridApplied`, and if the
  portal cannot reproject a `crsNote` says so. Verified live: `query_dataset(2554)`
  returns `59.17, 36.58`.
- **`geo_extent` is a requestable `fields` projection.** `fields=["geo_extent"]`
  (alias `"details.geo_extent"`) returns a labelled `{bbox, crs, axisOrder}` built
  from `details.geo_extent` (object **or** JSON string) with an `ext_*` fallback —
  no need to pull the whole `details` blob. Works in list and single-get, and
  survives the list `lite` details drop. Verified live for 2554.

### Docs

- Tool schema and `python-sdk.md` now state: `query_dataset` defaults to 4326;
  the `geo_extent` field; the manifest `raster: true` flag and `layerPalette`;
  axis order; and that `style` affects vector layers only (SLD for WMS planned,
  slice 033 §12).

## 0.12.2 — 2026-11-22

Map-service live-QA follow-up (slice 033), from a third owner/Claude report. Layer
styling now actually renders, a `bbox` is emitted for every dataset regardless of
SRID, layers get distinct palette colours, and the legend matches the real layer.
No new tool (31), no new dependency.

### Fixed

- **`style` now recolours the rendered vector layer.** Previously a per-layer
  `style` was accepted and echoed (and tinted the legend swatch) but never applied
  to the OpenLayers vector/MVT/WFS layer, so both layers looked identical. The
  viewer now resolves `layerStyle` + the layer's own `style` into the style it
  actually draws, and the legend reports that same fill. A WMS/WMTS/XYZ image is
  rendered by the server: `style` cannot recolour it, so it is ignored with a
  warning (use `render:'wfs'` for client styling; SLD-based WMS styling is
  planned — slice 033 §12).
- **`bbox` is emitted for every dataset, whatever its SRID.** The portal returns
  `details` as a JSON **string** for most datasets; `dataset_info` only handled a
  dict, so it silently found no extent for projected datasets (32640/UTM, SRID-less
  Iran Lambert) and rasters. It now parses the string and falls back to the stored
  top-level `ext_west/south/east/north`, so a layer gets a WGS84 `bbox` for
  2580/2436/2554/2304/2291 alike (verified against the live portal).
- **Distinct default colours.** Layers without an explicit `style.fill` rotate
  through a new `layerPalette` (template-configurable), so multiple layers are no
  longer the same green.
- **A publication layer borrows its source dataset's extent.** The SDK's
  `Publication` model serialises as `{"raw": {...}}`, so `publication_dataset_id`
  never found the dataset and the layer got no `bbox`. It now unwraps `raw` (or
  reads `raw.dataset.id`) — verified live: pub 60 → dataset 2554, pubs 17/18 →
  1761.
- **`query_dataset` warns when its output is not WGS84.** When `out_srid` is
  omitted and the first geometry looks projected (metres), the result carries
  `crsNote` telling the caller to pass `out_srid=4326` before drawing it on a
  WGS84 map (the map path already requests 4326).
- **Legend matches the layer.** Image layers (WMS/WMTS/XYZ) and raster datasets
  (`raster: true` in the manifest) show a raster swatch instead of a fake vector
  colour (e.g. the grey hillshade no longer gets a green box).

### Verified

- `portal-dataset` geometry is requested with `outSRID=4326`; the live portal
  reprojects projected datasets (2436, 2554) to WGS84, so the map path is not in a
  native CRS. The plain `query_dataset` tool keeps its own `out_srid` contract.

### Docs

- Tool schema states axis order (`bbox` `[W,S,E,N]`, `view.center` `[lon,lat]`),
  that `style` affects vector layers only, that `layerPalette` rotates fills, that
  `fields` accepts the `ext_*` columns and `publicationsSummary`, and that a
  publication id is discovered with `order_by='publicationsCount'`. The backend
  extent-contract gap remains **BE-010**.

### Planned (not in this release)

- A portable style model (unique value, class breaks) applied to vector layers and
  generated as SLD for WMS/WMTS, plus converting a dataset's default portal
  symbology into that model — slice 033 §12.

## 0.12.1 — 2026-11-22

Map-service live-QA fixes (slice 033), from a second Claude report. Fail-fast
publication validation, WGS84 dataset output, self-labelled extents, and a fixed
layer list/legend. No new tool (31), no new Python dependency.

### Fixed

- **Layer list + legend were empty and layers could not be toggled.** The panel
  iterated the basemap list (so no data layer appeared) and the legend was drawn
  before the panel HTML reset (so it was wiped). Both now render from the actual
  data layers, with visibility toggles and opacity sliders (`viewer.html`).
- **`portal-dataset` geometry is now served in EPSG:4326.** `/data` requests
  `outSRID=4326`, so a dataset stored in a projected/native CRS (e.g. Iran
  Lambert) renders on a WGS84 map instead of plotting metre values as lon/lat.
- **`publicationId` is validated at map-build** (fail fast with `publicationId`
  + a hint to use `list_datasets` `publicationsSummary`), not a 404 at tile time.
- **Extents are self-describing and auto-filled.** `show_map` reads the source
  dataset's WGS84 `geo_extent` when a layer `bbox` is omitted and emits
  `bboxCrs`/`bboxAxisOrder`; a projected or lat/lon-swapped `bbox` is rejected
  (with a warning) in favour of the dataset extent, and the viewer refuses any
  implausible box so auto-fit cannot land on the wrong continent.
- **Raster `portal-dataset` layers warn** that they are vector-only and should
  use a `portal-publication` (WMS/WMTS) instead.

### Changed

- `fields` now accepts `publicationsSummary` and the stored `ext_*` keys.
- Tool schema states axis order (`bbox` `[W,S,E,N]`; `view.center` `[lon,lat]`),
  that `render` only changes publication output, and the raster rule. The
  backend extent-contract gap is tracked as **BE-010**.

## 0.12.0 — 2026-11-22

Built-in **map viewer** (slice 033, Lane B) with **user-editable templates**. `geopack_sdk_show_map`
now returns a live `viewerUrl` — an OpenLayers page served from the same loopback origin — instead of
`viewerUrl:null`. The page draws the manifest's layers and is restyled after install without touching
the package. No new tool (surface stays **31**), no new Python dependency, no map image.

### Added — the viewer

- **`/map/{mapId}`** serves the viewer shell (token-exempt; it holds no secret). `viewerUrl` carries the
  low-sensitivity session token as **`?t=...`**, and the server **embeds a validated token into the
  page** so it works even when a host/chat client strips part of the URL; **`#t=...` is still accepted
  as a fallback**. The token gates the `/map/{id}/manifest.json`, `/data` and `/tiles` calls. A strict
  `Content-Security-Policy` and `Referrer-Policy: strict-origin-when-cross-origin` ship with the page
  (origin-only, so `?t=` never leaks to a third party).
- **OpenLayers** is the runtime: one lightweight, plugin-free library that renders **GeoJSON, MVT
  vector tiles, WMS/WMTS images, WFS vector data and XYZ raster** — the portal's layer families —
  with a layer list (visibility + opacity), basemap switcher, legend and scale line. Distribution is
  the **pinned CDN by default** (no build step); `GEOPACK_MCP_MAP_ASSETS=<dir>` serves a vendored
  `ol.js`/`ol.css` for offline/airgapped installs.
- **The page is an editable resource, not embedded code.** The shipped viewer lives at
  `maps/templates/default/viewer.html` (read from disk); a user **`viewer.html`** in the Tier-2 dir
  replaces it — validated to keep the required `__…__` placeholders, else the shipped page is used with
  a warning. `show_map` returns `viewerHtmlPath` / `viewerHtmlUsed`.
- **OSM tiles render in-browser.** The shell's `Referrer-Policy` is origin-only and every XYZ tile
  `<img>` sets a per-element `referrerPolicy: strict-origin-when-cross-origin`, so OSM receives the
  `Referer` it requires instead of answering with its "access blocked" policy image — the OpenLayers
  equivalent of the portal frontend's `OsmWebTileLayer`.
- **Publication layers** now expose `wmsUrl`/`wmtsUrl`/`wfsUrl` (proxied, minted on demand) and a
  `render` hint (`geojson|mvt|wms|wmts|wfs|xyz`); `/proxy/publication/{id}/{protocol}` forwards the
  browser's OGC query string (WMS `GetMap`, WFS `GetFeature`) after minting.
- `open_browser=true` now opens the **viewer** URL (best-effort, never depended on).

### Added — templates (N6, three tiers)

- **Tier 1** shipped default `maps/templates/default/` (`viewer.html` + `template.json`); **Tier 2**
  user `viewer.html` / `template.json` (and optional `viewer.css`) under `GEOPACK_MCP_MAP_TEMPLATES` or
  `~/.geopack/mcp/maps/`; **Tier 3** per-call `template` / `style` / `basemap` arguments.
  `template.json` deep-merges (higher tier wins); `viewer.html` replaces the page wholesale.
- Editable keys: `title`/`subtitle`/`footer`, `basemaps[]` (named XYZ/none backgrounds),
  `basemap`, `view` (fit or center/zoom), `palette`, `layerStyle`, `layerList`/`legend`/`scale`/
  `attribution`. Unknown keys are ignored and a type error falls back to the default **for that
  key** with a `templateWarnings[]` entry — never a crash.
- `show_map` returns `viewerUrl`, `templatePath`, `templateUsed`, `viewerHtmlPath`, `viewerHtmlUsed`
  and `templateWarnings`.

### Changed

- `manifestUrl` is now `/map/{mapId}/manifest.json` (the old `/manifest/{mapId}` still works).
- **OSM is loaded by the browser**, not proxied by the MCP (the GIS-088 lesson: OSM forbids anonymous
  proxying; the client sends the required `Referer` via a per-element referrer policy). A template
  basemap may point at any XYZ service.

### Notes

- Still **no map image** and no portal renderer (D1/D8 unchanged). Lane B's product is a live URL the
  browser draws.

## 0.11.0 — 2026-11-22

Local data service + local geometry ops (slice 033, lanes A and C). The MCP can now stand up a
**loopback-only data service** that proxies portal data with its own credentials and serves local
files, so a page can reference a **URL instead of embedding data**, and it can run **local spatial
tools** with no Geoportal dependency. **No map image is produced** and **no portal renderer is added**
(the D8 boundary is unchanged; the built-in viewer is Lane B and remains deferred). Surface **29 → 31
tools** (`geopack_sdk_show_map`, `geopack_sdk_geometry_op`).

### Added — Lane A: local map data service

- **`geopack_sdk_show_map`** starts/updates a `ThreadingHTTPServer` bound to `127.0.0.1` on an
  ephemeral port, declares layers, and returns `{serviceUrl, manifestUrl, layers[].dataUrl/tileUrl,
  accessToken}`. It is **opt-in** (`GEOPACK_MCP_MAP_SERVICE=1`), token-gated, `Host`-checked
  (anti-DNS-rebinding), and the **portal credential never crosses to the browser** — only a
  low-sensitivity per-process session token does. A host that forbids binding answers
  `MAP_SERVICE_BLOCKED`; `open_browser` is accepted but opens nothing until a viewer page exists
  (Lane B), and says so.
- **Endpoints:** `/data/{layerId}` (GeoJSON for a portal dataset or inline geometry; a local file for
  `local-file`), `/tiles/{layerId}/{z}/{x}/{y}.pbf` (portal-native MVT or minted publication tiles),
  `/local/{layerId}` (allow-listed local file), `/proxy/publication/{id}/{protocol}` (minted
  WMS/WMTS/MVT/WFS passthrough), `/manifest/{mapId}`, `/shutdown`.
- **Local files** are limited to `GEOPACK_MCP_MAP_ROOT` with realpath containment, an extension
  allow-list and a size cap. **Upstreams** are allow-listed to the portal host plus
  `GEOPACK_MCP_PROXY_HOSTS`. Scoped CORS is **off by default** (`GEOPACK_MCP_MAP_CORS=1` enables it on
  `/data` and `/tiles` only).

### Added — Lane C: local geometry ops

- **`geopack_sdk_geometry_op`** — one family tool with an `op` argument over a **shapely/pyproj** engine
  (already dependencies via geopandas; **no new dependency**): `buffer`, `overlay`
  (`union|intersection|difference|xor|clip`), `convex_hull`, `envelope`, `dissolve`, `simplify`,
  `validate`, `fix`, `convert` (GeoJSON↔WKT), `project`, `measure`, `distance`, `nearest`,
  `line_between`, `point_on_surface`, `smooth`, `create`, `describe`. **No portal call.**
- GeoJSON-dict-only **engine port** (`geometry/engine.py`) with a swap-enforcement test: only
  `shapely_engine.py` may import shapely/pyproj/geopandas. Metric ops auto-project WGS84 to a local
  UTM (or an explicit `wkid`) and project back with the `crs` member; every result echoes provenance
  (`engine`/`methodUsed`/`crsUsed`/`unitsUsed`).
- New coded refusals (additive): `GEOMETRY_UNSUPPORTED_OP`, `GEOMETRY_EMPTY_RESULT`,
  `GEOMETRY_ENGINE_FAILED`; unknown units/args stay `INVALID_ARGS`. **Geodesic buffer is not
  available in v1** — it answers an honest code instead of faking it.

### Changed

- New policy bucket **`hostServices`** names `geopack_sdk_show_map` in `get_mcp_safety_policy`;
  `geopack_sdk_geometry_op` is a pure read.
- New env vars: `GEOPACK_MCP_MAP_SERVICE`, `GEOPACK_MCP_MAP_ROOT`, `GEOPACK_MCP_MAP_CORS`,
  `GEOPACK_MCP_MAP_IDLE_TIMEOUT`, `GEOPACK_MCP_MAP_PORT`, `GEOPACK_MCP_PROXY_HOSTS`,
  `GEOPACK_MCP_GEOMETRY_ENGINE`.

### Fixed — owner live-QA round (Claude Desktop)

- **`geometry_op` cold start.** The shapely/pyproj import is now **preloaded in the server lifespan**,
  so the first call no longer pays it (the reported first-call timeout).
- **`project` accepts `output_wkid` as the target alias.** `output_wkid` used to be ignored unless
  `wkid` was also given; now either names the target CRS.
- **`distance`/`nearest` echo the requested `units`.** They returned metres regardless of `units`;
  now `units` (`m|km|ft|mi`, default `m`) is validated and the result is converted + labelled.
- **`show_map` opens no browser.** `open_browser=true` used to open the raw JSON manifest in a
  browser (reported as a "map opened" false positive). It now returns `browserOpened:false` with a
  note, because there is no viewer page until Lane B.
- **Stable port option.** `GEOPACK_MCP_MAP_PORT` pins the loopback port; a random port changed on
  every idle-restart, breaking client URLs. `allow_reuse_address` is on so a pinned port rebinds.

### Notes

- Lane B (the built-in Leaflet viewer / user-editable map templates) is **deferred** by the owner's
  lane choice (A + C); `show_map` returns data URLs and states honestly that no viewer page is served.

## 0.10.0 — 2026-11-21

Sort parity across the MCP list lanes, plus a thumbnail-save hardening from the owner's live re-check.
0.9.0 gave `list_datasets` an `order_by`/`order_direction` knob; this release gives the same knob to
the other lanes whose **backend already supported it** — so "sort the list I searched" works
everywhere it can, not only where the live-QA report happened to land. No new tools, no
annotation/policy change: the surface stays **29 tools**.

### Fixed

- **`geopack_sdk_get_dataset_thumbnail` no longer crashes with no `save_path`.** 0.9.0 returned the
  image inline but still *invented* a temp target, so a sandboxed host with no usable temp dir failed
  the whole call with `FileNotFoundError: No usable temporary directory` (owner live re-check). The
  local save is now **opt-in**: with no `save_path` nothing is written and no filesystem call is made
  (`saved: false`, `saveSkipped: true`); with a `save_path`, a refused/failed write is a state
  (`saved: false` + `saveError`), never `isError`. `save_path` stays — it works on hosts that permit
  writes — and the tool description says nothing is written unless it is given.

### Added

- **`order_by`/`order_direction` on three MCP list lanes** (same contract as `list_datasets`: an
  unknown key is refused **before** the call with the legal values in `hint`; an omitted direction
  keeps the portal default):
  - `geopack_sdk_list_workflows` — `id | name | owner.userName | updatedAt | createdAt | version`
    (default `updatedAt`, newest first).
  - `geopack_sdk_list_workflow_runs` — `id | workflow.name | submitter | taskId | status | startedAt |
    finishedAt | createdAt | updatedAt` (default `createdAt`, newest first); the result echoes
    `orderBy`/`orderDirection`.
  - `geopack_sdk_list_generated_files` — `createdAt | fileName | fileSize | expiresAt | sharingPolicy`
    (default `createdAt`, newest first); the tool also gains `search_query` (name match) and echoes
    the applied sort.
- **SDK forwarding:** `WorkflowManager.list(order_by=, order_direction=)` →
  `sortBy`/`sortOrder` and `WorkflowRunManager.list(order_by=, order_direction=)` → `sortBy`/`sortOrder`
  (sync **and** async twins). `GeneratedFileManager.list` already took `order_by`/`order_direction`;
  the MCP handler now passes them through.
- Shared edge helper `ordering.validate_sort_args(...)` — one whitelist-refusal implementation for
  the list lanes.

### Notes

- **Thumbnail docs made explicit (owner live re-check follow-up).** Inline delivery is the official
  mode for `geopack_sdk_get_dataset_thumbnail`; `save_path` writes only where the host permits it, and
  a host that forbids writes answers `saved:false` with the image still returned. This is now stated in
  the tool description, the `save_path` field description (`ThumbnailSavePath`), the README MCP
  section and `get_mcp_safety_policy`'s `note`, so a missing file on disk is not read as a failure.
- `list_analysis_tools` stays unsorted on purpose: the catalog endpoint hard-codes `name ASC`
  (`workflowToolService.js`), so there is nothing to expose yet.
- Backend sort keys were read from `workflowService.js` (`sortBy`/`sortOrder`,
  `updatedAt DESC` default), `workflowRunService.js` (`sortBy`/`sortOrder`, `createdAt DESC` default)
  and `generatedFileService.js` (`orderBy`/`orderDirection` whitelist) — the edge mirrors those
  whitelists exactly.

## 0.9.0 — 2026-11-21

A live-QA round against `geopack-sdk-mcp` 0.8.0 (Claude Desktop) surfaced five defects; this release
fixes them without adding, removing or re-annotating a tool. The surface stays **29 tools**.

### Fixed

- **Models tolerate partial portal rows.** `Dataset` no longer rejects a row over a stray field:
  `dataType`/`subType`/`status`/`description`/`keywords` coerce to text, the `*Id` foreign keys
  degrade to `None` on a bad value, and `createdAt`/`updatedAt` accept `null`. A row that cannot be
  fully parsed is **repaired** into an identity-only shell carrying `validationDegraded: true` and a
  `validationErrors` list, instead of failing the whole page — a `service`-typed dataset now lists
  and reads cleanly.
- **Thumbnails render inline.** `geopack_sdk_get_dataset_thumbnail` now returns the preview as MCP
  **image content** (base64 PNG), so an MCP host shows the picture. `save_path` is still honoured;
  a non-writable destination degrades to `saved: false` + `saveError` (no absolute path echoed) with
  an inline-image fallback, never a failed call.
- **`order_by` resolves against the server's legal keys.** `geopack_sdk_aggregate_dataset` now
  matches the caller's key case-insensitively against the count (`count`/`aggregate_count`), the
  group-by field names and the named non-count aliases, translating the count alias to the server's
  `aggregate_count`. An unknown key is refused **before any network call** with the legal keys in
  `hint`; `by` is validated to `value`/`label`.
- **Bounded read lanes.** `geopack_sdk_list_datasets` gains `order_by`/`order_direction` (server
  whitelist) and a `fields` projection; `lite` now strips `details` and marks `detailsOmitted`, so a
  list page stays compact. `geopack_sdk_get_dataset` gains `fields`. Unknown projection keys are
  refused client-side.
- **bbox transparency.** The `bbox` argument now documents that a bounding-box filter drops rows
  with no stored extent (the backend predicate is on `ext_*` only) — see backend `BE-009`. No
  silent-result change: the note is emitted as `extentFilterNote` on a bbox list.

### Notes

- Backend companion finding registered as **BE-009** in the portal `docs/ISSUES.md`
  (`datasetService.js` bbox predicate over `ext_*` silently drops null-extent rows); the MCP fix is
  disclosure, the behavioural fix belongs to the backend.
- Design of record: portal slice `032-mcp-liveqa-remediation.md`.

## 0.8.0 — 2026-11-19

One new read lane over MCP, and no authoring. A saved workflow can now be *inspected* by an MCP
host, which was the one gap left in the 0.7.0 workflow surface.

### Added

- **`geopack_sdk_get_workflow_spec`** (MCP, tool 29): projects a saved workflow into the
  model-facing wf-spec through `POST /workflows/compile-spec {workflowId}` — nodes, operators,
  their config, `summary` and `issues`. Read-only: it never creates, saves or edits a workflow.
  Optional `budget_chars` (2 000–200 000) asks for the compacted-by-reference form and, when even
  that does not fit, a `sectionIndex` instead of `projected`.
- `WorkflowManager.compile_spec(..., budget_chars=)` and its async twin: the character budget is
  forwarded as `budgetChars`; omitted when `None`.
- **Workflow delete contract** (portal slice 033): `WorkflowManager.delete(workflow_id,
  with_runs=False)` — the default lane is refused with a typed `WorkflowHasRuns` (409) while the
  workflow still owns runs, `with_runs=True` sends `?withRuns=true` and accepts the **irreversible**
  cascade (run rows + artifacts + workflow, one transaction). New typed errors `WorkflowHasRuns`
  (`runs`, `active`, `by_status`) and `WorkflowHasActiveRuns` (`active`, `running`), mapped from
  the coded 409s at the SDK boundary.

### Changed

- The spec lane strips **UI-only keys** recursively (`position`, `positions`, `ui`, `measured`,
  `selected`, `dragging`, `handleBounds`, `nodeInternals`, `sourcePosition`, `targetPosition`,
  `positionAbsolute`, `computedPosition`, `parentNode`, `zIndex`, `expanded`) — canvas state has no
  MCP consumer and costs tokens. Operator config keys (`width`, `height`, `style`) are **kept**:
  they are run-form semantics, not canvas state.
- `UNAVAILABLE_OPERATIONS` gains `delete_workflow_run`, beside `delete_workflow`: the run lane has
  no delete tool and now says so instead of staying silent.
- `workflows.delete()` returns the outcome dict `{id, deleted, runsDeleted}` instead of `True` —
  the count is what a cascade confirmation has to show. Callers that ignored the return value are
  unaffected.

### Notes

- **No authoring over MCP, by owner ruling:** no `create_workflow`, no `save_workflow` and no
  `validate_workflow_spec`. A validator whose only consumer is a save that cannot happen is dead
  surface; the projection tool is a *reader*, the same way `get_dataset_schema` exists without a
  "create table" tool.
- Deleting a workflow that still has runs is a backend contract question, not an MCP one — MCP has
  no delete. The API now refuses by default instead of answering a raw FK error, and a `running`
  run blocks both lanes (the worker is still writing into the row it would lose). See the workflow
  delete-contract slice.

## 0.7.0 — 2026-11-19

First release since 0.6.0 that brings the SDK back in line with the portal API and rebuilds the MCP
edge on the patterns the in-portal assistant harness proved.

### Added

- **Query lanes:** paginated feature queries, server-side aggregates (counts, sums, statistics,
  percentiles, top-N, ordering, limit) and minted access URLs for query and MVT tiles.
- **Relationships and schema:** relationship catalog, related-record hops, schema preview, column
  bounds and the dataset access context.
- **Field access and editing:** field restrictions in the dataset payload, ACL row-filter updates,
  the EditDoc ladder (`validate` → `preview` → `apply`) and the legacy per-feature CRUD/`applyEdits`
  endpoints.
- **Virtual and computed:** virtual dataset authoring (including virtual SQL with preview) and the
  computed-column catalog/preview.
- **Maps, publications, layouts, external services:** control-plane CRUD only — no render, compose
  or export method exists (owner ruling 2026-11-19, decision D8).
- **Governance:** task types/stats/cancel/delete, quota summaries, workflow
  `statistics`/`compile-spec`/`tool-manifest`, workflow-run delete and datastore relationships.
- **Attribution:** `default_headers` on both clients; the MCP server sends
  `X-Geoportal-Client: mcp` so `workflowRun.source` reads `mcp`.
- **Async twins** for every method above (`AsyncGeopackClient`), fenced by
  `tests/test_async_parity.py`.
- **MCP tools (19 → 28):** `get_dataset_schema`, `aggregate_dataset`, `get_dataset_relationships`,
  `get_related_records`, `get_quota_summary`, `list_workflow_runs`, `list_generated_files`,
  `submit_edit_document` and `cancel_task`.
- **MCP error contract:** a failed call is `isError: true` with `structuredContent` =
  `{error, code, type, statusCode, status_code, message, hint, invalidArgs?}`; an unreachable API is
  `TRANSPORT_ERROR` with the host/port stripped from the message.
- **MCP annotations and structured output:** every tool declares `title`, `readOnlyHint`,
  `destructiveHint`, `idempotentHint` and `openWorldHint`; five stable read lanes carry typed
  output schemas.

### Changed

- `mcp` stays an optional extra, with a floor of `>=1.27.1,<2` (first release with the annotation
  and structured-output surfaces this package relies on).
- `GeopackAPIError` carries the server's `code`; the MCP edge derives a code from the exception
  class when the server sends none, and `hint` names the next tool to call.
- Client-side validators refuse bad enumerations and wrong arity **before** any network call and
  list the offending argument in `invalidArgs`.

### Deprecated

- `datasets.create_virtual_esri_dataset()` — alias of `create_virtual_dataset()`;
  `POST /datasets/virtual-esri` stays server-side for older clients only.

### Fixed

- Removed the unregistered, dead `delete_dataset` MCP handler (deletes stay portal-only).
- Closed the sync/async parity gaps the 0.7.0 audit found.

### Notes

- No breaking changes: existing signatures and response fields are preserved, and `status_code`
  remains in error payloads as the snake_case alias of `statusCode`.
- MCP transport is **stdio only** in 0.7.0 (`python -m geopack_sdk_mcp` accepts no transport flag).
