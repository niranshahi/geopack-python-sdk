# Changelog

All notable changes to `geopack-sdk` and the bundled MCP server (`geopack_sdk_mcp`).
Append-only; newest first.

## 0.16.1 — 2026-11-27

**Fix `colorMap: 'custom'` on the raster-tile lane (live-QA of 0.16.0).** A custom ramp
rendered as an **empty/transparent tile** while `pseudocolor`/`fire`/`bluered` worked.
Root cause: the backend's `ST_ColorMap` is order-sensitive, and the SPA's
`RasterDisplayPanel.apply()` sorts `customColorMap` **descending** before rendering; the
MCP forwarded the caller's ascending stops unchanged.

### Fixed

- `customColorMap` stops are normalized to the portal's flat `r/g/b/a` form **and sorted
  descending** (percentage stops resolved against `minimum`/`maximum`; `nv`/`null` last),
  mirroring the panel. The panel's exact working sample and the report's ascending 3/5-stop
  ramps are now pinned by tests.
- `geopack://guide` now states the ordering rule and the real `custom` semantics: the ramp
  **interpolates** between stops, so **discrete/flat classes need paired same-colour stops**
  at each boundary (e.g. `24.99%` then `25%`). `reclass` is a **boolean** that only affects
  the **named** ramps (an 8-bit min→max value reclass), is **ignored for `custom`**, and is
  not an `equalInterval` object. A `custom` + `reclass` call now **warns** that it has no
  effect instead of silently doing nothing.

## 0.16.0 — 2026-11-27

**Map viewer: server-rendered raster tiles for a raster with no publication and no COG
(slice 033 follow-up).** A `portal-dataset` raster stored in PostGIS (or as a filesystem
raster) is now drawn as real pixels in the built-in OpenLayers viewer. It uses the
portal's existing PNG tile lane — `GET /datasets/{id}/rastertile/{z}/{x}/{y}.png` — which
the SPA already consumes through `MyRasterWebTileLayer`; **no backend change** and no
temporary/permanent COG generation was added.

### Added

- `render: 'rastertile'` (auto-selected for a raster portal-dataset whose `details`
  identify a PostGIS raster table — `dbTableName` + `rasterDbColumn` — or an MBTiles
  dataset). A COG still takes the direct `/cog` byte lane.
- A loopback `GET /rasters/{layerId}/{z}/{x}/{y}.png` proxy that adds the portal
  credential and forwards the dataset's saved raster `display` (bands / colorMap /
  min-max) plus a computed `ref_z`, so the **official symbology is applied** by the
  portal renderer and the display never travels through the browser. A layer may pass
  an optional `display` (and `refZoom`) to **override** the saved rendering — the tile
  lane, unlike a COG, can be re-rendered. The friendly `bands:{r,g,b}` / `[r,g,b]` and
  `customColorMap` `color:[r,g,b,a]` shapes are normalized, an unknown `colorMap` name is
  refused back to `grayscale` **with a warning** (a bad ramp cannot fail the tile), and a
  `display` on a COG/MBTiles/vector layer is ignored with a warning.
- `geopack://guide` gained a "Raster rendering (`display`)" section (ramps, bands,
  min/max, custom stops, `refZoom`, how to read the saved `symbology`/`details.bands`),
  and the `show_map`/`get_dataset` descriptions now point at it.
- The manifest exposes `rasterTileUrl` (an XYZ template) for these layers; the viewer
  draws them with `ol/source/XYZ` and shows a raster legend swatch.
- `ref_z` is derived from `details.metadata_3857.scalex` (frontend parity) or, when
  absent, from `geo_extent` width / `rasterSize.x`, so the portal picks the right
  overview instead of the blurry default level.
- Tests: a PostGIS raster selects `rastertile` with no misleading warning; an MBTiles raster uses
  the same lane; a raster without a tile source still warns and falls back; a caller `display`
  overrides the saved one; the `/rasters` proxy forwards credential + `display` + `ref_z`; the viewer
  runtime has the XYZ branch.

## 0.15.0 — 2026-11-26

**Authentication hardening (slice 034) — complete, not rewrite, the JWT+session flow.** A local MCP
server now runs on a session created once by the CLI, with **no password in `mcp.json`**. No OAuth.

### Added

- `geopack-sdk login|logout|status|profiles` with `--profile`/`--store`. `login` reads the password
  interactively (`getpass`, never an argv value) and persists only the **refresh token**; it also
  prompts for the username when not supplied. `logout` revokes the server session (best-effort) then
  clears the store; `logout --all` is a separate, explicit bulk action. `status` never prints a token.
- Pluggable `CredentialStore`: OS secret store via the optional `keyring` package (default), an
  explicit plaintext `file` fallback that **warns** (never selected silently), and `memory` for tests;
  plus `ProfileRegistry` (`~/.geopack/profiles.json`, non-secret metadata) and atomic writes.
- `AuthState` / `AsyncAuthState`: per-client token state with a single-flight refresh lock.
- MCP bootstrap reads the stored profile and **refreshes at startup**; `GEOPACK_PROFILE` selects it.
  Precedence: `GEOPACK_ACCESS_TOKEN` → stored profile → legacy token file → `GEOPACK_USERNAME`/`PASSWORD`.
- New optional extra `geopack-sdk[keyring]` (also pulled in by `[mcp]` and `[all]`).
- Backend `POST /api/auth/logout` (idempotent; revokes the token's `sid`) — used by CLI/MCP logout.
- **Degraded auth mode (P6):** if no session is available at startup the MCP **still starts**; every tool answers a coded `AUTH_REQUIRED` error with the fix, and a new `geopack_sdk_auth_status` tool + `geopack://auth` resource explain how to log in. The process no longer exits with a message visible only in host logs. The surface is now **32 tools**.

### Changed — BREAKING

- `TokenRegistry` is **no longer a process-wide singleton**; each client owns an `AuthState`, so
  clients/accounts/servers are independent. Code that relied on implicit token sharing between
  clients must pass the same `AuthState` (new `auth_state=` argument).
- `GeopackClient`/`AsyncGeopackClient` accept `auth_state` / `credential_store` / `auth_profile`.
- `GEOPACK_USERNAME`/`GEOPACK_PASSWORD` in `mcp.json` are **deprecated** (dev only).

### Fixed

- Concurrent `401`s now perform **one** refresh (single-flight); a caller whose token was already
  rotated while waiting skips the redundant refresh.
- The rotated refresh token is persisted (write-through), so restarting the MCP no longer reuses a
  stale token and forces a re-login.

### Verification

- Full suite **856 tests** OK (`python -m unittest discover -s tests`).

Touched files:
- `src/geopack_sdk/token_registry.py`, `auth_state.py` (new), `auth.py`, `async_auth.py`,
  `client.py`, `async_client.py`, `credentials.py`, `cli/main.py`
- `src/geopack_sdk_mcp/auth_bootstrap.py`, `server.py`, `context.py`, `errors.py`, `__main__.py`
- `src/geopack_sdk_mcp/tools/auth.py` (new), `tools/__init__.py`, `tools/policy.py`,
  `annotations.py`, `guide.py`, `resources/auth.py` (new), `resources/__init__.py`
- `tests/test_token_registry.py`, `test_credentials_store.py` (new), `test_cli_profiles.py` (new),
  `test_mcp_auth_bootstrap.py` (new), `test_mcp_degraded_auth.py` (new), `test_default_headers.py`,
  `test_mcp_read_tools.py`, `test_map_tools.py`
- `pyproject.toml`, `README.md`, `CHANGELOG.md`

## 0.14.0 — 2026-11-24

**Removed `geopack_sdk_render_chart`.** The bundled chart renderer (added across 0.13.0–0.13.2)
did not meet the bar: Persian digit/separator order was wrong, a dwarfed second series was drawn
at zero width, long Persian category labels crowded the axis, and an `image/svg+xml` result does
not preview in a chat client — so an operator could not review it. Chart QUALITY (fonts, shaping,
digits, units, layout) is controlled far better by a renderer the caller owns, so the server now
stops at the DATA.

### Removed

- The chart tool is no longer registered; the surface is back to **31 tools**. The data lanes
  that feed a chart are untouched: `geopack_sdk_aggregate_dataset` (rows carry `groupLabels`),
  `geopack_sdk_query_dataset`, `geopack_sdk_list_datasets`, `geopack_sdk_get_dataset`/`_schema`,
  `geopack_sdk_export_dataset`, `geopack_sdk_geocode_place` and the local `geopack_sdk_geometry_op`.
- Recommended path: get the numbers from the MCP, then render the chart with a script/library
  under your own control. The in-app assistant harness keeps its own client-side ```chart fence
  (drawn with the app's `c3`) for that purpose.
- Deleted `tools/charts.py`, `tool_handlers/charts.py`, `tests/test_mcp_chart_tool.py`, and the
  `Chart*` schema aliases; the guide's chart recipe now says to render client-side.

### Verification

- Full suite **830 tests** OK (was 849 at 0.13.2; the chart-tool suite and its schema were removed).

Touched files:
- `src/geopack_sdk_mcp/tools/__init__.py`, `tools/policy.py`, `annotations.py`, `guide.py`, `tool_schema.py`, `content/guide.md`, `README.md`
- removed `src/geopack_sdk_mcp/tools/charts.py`, `src/geopack_sdk_mcp/tool_handlers/charts.py`, `tests/test_mcp_chart_tool.py`
- `tests/test_mcp_read_tools.py`, `tests/test_map_tools.py`, `tests/test_mcp_write_tools.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.13.2 — 2026-11-24

Makes the charting lane own non-Latin text, and corrects/extends `geopack://guide`.

### Changed

- **`render_chart` is SVG-only and inspectable.** `format:'png'` is now a coded refusal:
  no bundled raster engine shapes complex scripts (cairo's toy text API and Pillow without
  Raqm do not), so a rasterised Persian label would be wrong — SVG keeps text in LOGICAL
  order and lets the renderer join/shape it. The SVG source is echoed as a string in the
  payload (`svg`), so a caller can inspect/verify/embed/post-process the chart (it was an
  opaque image payload before). The SVG declares an Arabic-capable font stack
  (`Tahoma, 'Segoe UI', 'Noto Naskh Arabic', …`) and RTL labels carry `direction="rtl"`;
  the text is never pre-shaped (no U+FB50–U+FEFF, no ZWJ/ZWNJ). `save_path` writes the SVG.
- **Coded-value labels.** `render_chart` now reads `groupLabels[<category field>]` from the
  aggregate rows and uses the human label automatically, so a Persian-coded field charts
  with names, not integer codes — no manual row flattening.

### Fixed

- **`invalidArgs` names the right argument (report G5).** A chart whose category field does
  not exist in the rows now refuses with `invalidArgs:["category"]` (and a `groupLabels`
  hint) instead of blaming `value`.

### Docs

- **`geopack://guide` corrected and extended (report B).** Fixed the `order_by` key rules
  (alias vs `aggregate_<kind>_<field>`), the MVT `dataUrl` cap (bounded for every renderer;
  only tiles are full coverage), the session-scoped links (token rotates; stale `?t=` → a
  readable 401 page), the consent split (`explicit` vs `brief`), and the chart recipe (SVG +
  `groupLabels`). Added: the export→download chain, thumbnail-vs-publication, task lifecycle,
  the MCP resources (`geopack://guide`, `dataset://…/thumbnail`, `generated-file://…/download`),
  RTL/script guidance, and a recurring-code troubleshooting table.

### Verification

- Full suite **849 tests** OK (was 846; +3 — Persian-SVG, `groupLabels`, category error).

Touched files:
- `src/geopack_sdk_mcp/tool_handlers/charts.py`, `src/geopack_sdk_mcp/tool_schema.py`
- `src/geopack_sdk_mcp/content/guide.md`, `README.md`
- `tests/test_mcp_chart_tool.py`; `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.13.1 — 2026-11-24

Adds a file form + labelled slices to the charting lane and makes an expired map link
legible. N5/N7 from the v5 report were re-tested and already behave correctly on 0.13.0
(see "Re-verified").

### Added

- **`render_chart` file output + pie labels.** Optional `save_path` writes the chart
  (best-effort, like the thumbnail lane — `saved`/`savePath`/`saveError`, never an error
  result), and `format:'svg'|'png'` selects the artifact: `svg` needs nothing (faithful for
  Persian labels and a normal downloadable file); `png` rasterises via the optional
  `cairosvg` engine (`geopack-sdk[charts]`) and is otherwise a coded `invalid_args`. A pie
  also returns `slices` (`{label, value, percent}`) so a text-only client can read it.
  Because it may write, `render_chart` is now classified under `localWrites` (still
  non-mutating; inline delivery is unchanged).

### Fixed

- **Expired/invalid viewer links are legible (N6).** The viewer shell is token-free by
  design (the token rides `?t=` or the URL fragment), so a bad `?t=` used to answer 200 and
  leave a blank canvas. The server now answers **401** with a readable "link expired" page
  for an invalid `?t=`, **404** with a "map no longer exists" page for an unknown map id,
  and the viewer shows an explicit "expired — re-run show_map" message when its manifest
  fetch is 401/403 (the fragment-token case). Maps and the session token remain per-run
  (in memory): links are intentionally session-scoped.

### Re-verified (no code change)

- **N5** — the MVT/WFS `dataUrl` truncation warning fires: a live `show_map` of dataset
  1577 `render:'mvt'` returned the "1,000 of 18,648" `templateWarnings` entry.
- **N7** — `order_by` on a non-count aggregate alias works: a live `aggregate_dataset`
  (count AS n + sum(area) AS area, group Landuse_Group, filter >10000) ordered by `area`
  returned 200 with the largest area first; an unknown key is a coded `INVALID_ARGS`. Pinned
  by unit tests. Both look like the mixed `~eopack_sdk-*` install the report flagged; a
  clean reinstall is advised.

### Verification

- Full suite **846 tests** OK (was 838; +8 — the chart file/slices and N6 page tests).

Touched files:
- `src/geopack_sdk_mcp/tool_handlers/charts.py`, `src/geopack_sdk_mcp/tools/charts.py`, `tools/policy.py`
- `src/geopack_sdk_mcp/tool_schema.py`, `src/geopack_sdk_mcp/content/guide.md`, `README.md`
- `src/geopack_sdk_mcp/maps/service.py`, `maps/templates/default/viewer.js`
- `tests/test_mcp_chart_tool.py`, `tests/test_map_tools.py`, `tests/test_mcp_write_tools.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.13.0 — 2026-11-24

Adds the **charting lane** (issue 5 / SDK-011): a local `geopack_sdk_render_chart` tool draws a
bar/line/pie chart from rows the agent already has, closing the gap where `aggregate_dataset`
returned numbers and `show_map` drew a map but nothing drew a statistical chart. The in-app
harness gains the matching agent-side ```chart fence (see the portal changelog). **32 tools**;
still no new Python dependency (the SVG is built from the standard library).

### Added

- **`geopack_sdk_render_chart`** — takes `rows` (e.g. `geopack_sdk_aggregate_dataset`'s `rows`)
  plus `category`/`value` (and optional `series`/`title`) and returns a self-contained **SVG**
  chart inline as `image/svg+xml`, with the same numeric `points` echoed in the structured
  payload (a client that does not render SVG still receives the data). Pure local compute: no
  portal call, no third-party graphics dependency. `chart_type` is `bar`/`line`/`pie`; points
  are capped at 200 with the remainder disclosed; non-numeric rows are skipped and reported.
  Bad input is a coded `invalid_args`.

### Fixed

- **An MVT/WFS layer's `dataUrl` truncation is now disclosed.** `show_map` emitted the
  GeoJSON-cap warning only for `render:'geojson'`, so an MVT layer advertised a `dataUrl`
  capped at the first 1,000 features with no signal while its tiles were full coverage (issue
  report 2026-11-24, N5). The warning is render-aware now: a GeoJSON render names the capped
  MAP, an MVT/WFS render names the capped `dataUrl` (and says the map itself is full).

### Verification

- Full suite **838 tests** OK (was 826; +12 — the chart handler/tool and the N5 warning).

Touched files:
- `src/geopack_sdk_mcp/tool_handlers/charts.py` (new)
- `src/geopack_sdk_mcp/tools/charts.py` (new), `tools/__init__.py`, `tools/policy.py`
- `src/geopack_sdk_mcp/tool_handlers/maps.py`, `src/geopack_sdk_mcp/tool_schema.py`
- `src/geopack_sdk_mcp/annotations.py`, `src/geopack_sdk_mcp/guide.py`, `content/guide.md`
- `tests/test_mcp_chart_tool.py` (new), `tests/test_map_tools.py`, `tests/test_mcp_read_tools.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `README.md`, `CHANGELOG.md`

## 0.12.13 — 2026-11-24

Follow-up to the live issue report: exact, filter-aware class breaks; a `uniqueValue`
palette that cannot collide under the class cap; a list `filter` accepted at the schema;
and the documented default output CRS actually applied. Still 31 tools; no new dependency.

### Fixed

- **`classBreaks` breaks ignored the layer filter and came from a sample.** A
  `classBreaks` shorthand was computed from the first 1,000 features, so a **filtered**
  layer reported the whole dataset's breaks — a 356-row layer (`DB_SHAPE_Area > 10000`,
  true min ≈ 10,004) reproduced the unfiltered 18,648-row dataset's sampled breaks
  (`48.76 – 199.97`, … all below the layer's own minimum). The portal dataset lane now
  computes the breaks **server-side** over the full, access-scoped column
  (`maps/sources.dataset_field_quantiles`, aggregate `min`/`max`/`percentile`), and the
  layer's own `query.filter` is forwarded so the breaks describe exactly the rows the
  layer draws. If the store cannot aggregate (or the filter is unparsable) it falls back
  to a sample AND says so in `templateWarnings` — a sampled estimate is never passed off
  as exact. Caller-requested `classes` are capped at **12** (a higher count is not
  legible on a quantile map) with a warning.
- **A `uniqueValue` shorthand could draw unrelated categories the same colour.** The
  categorical palette held 12 colours but the derived class cap is 30, so an 18-class
  field cycled after the twelfth and two categories shared a fill (6 colliding pairs of
  18). The palette is now **30** distinct colours (sized to the cap), so every category
  up to the cap gets its own colour; a guard warns if the palette ever falls below the cap.
- **A bare list `filter` was rejected by the argument schema.** `aggregate_dataset`
  refused `filter=[{...}, {...}]` with a raw Pydantic `Input should be a valid dictionary`
  (no `code`/`invalidArgs`). `tool_schema.FeatureFilter` now accepts an object **or** an
  array (the handler already combined a list with `AND`), so a list reaches the portal as
  a normalized `AND` group instead of a schema error.
- **`query_dataset` did not apply its documented default `out_srid`.** With the parameter
  omitted the portal lane returned metre coordinates in the native CRS (no
  `outSridApplied`), while passing `out_srid: 4326` returned lon/lat. The default is now
  applied on both the tool and the handler (`4326`, guarding a null/0 echo), so an omitted
  `out_srid` answers WGS84 like the documented default.

### Notes

- Supersedes the 0.12.12 note that "class-breaks still samples": breaks are now
  server-side and filter-aware for portal-dataset layers; a local `inline-geometry`
  layer still quantiles over its own features.

### Verification

- Full suite **826 tests** OK (was 820; +6 — server-side class breaks, sample fallback,
  class-cap, palette-collision, list-filter and filter-schema).

Touched files:
- `src/geopack_sdk_mcp/maps/sources.py`
- `src/geopack_sdk_mcp/tool_handlers/maps.py`
- `src/geopack_sdk_mcp/tool_handlers/datasets.py`
- `src/geopack_sdk_mcp/sanitize/style_spec.py`
- `src/geopack_sdk_mcp/tool_schema.py`, `src/geopack_sdk_mcp/tools/datasets.py`
- `tests/test_map_tools.py`, `tests/test_mcp_filter_dsl.py`, `tests/test_mcp_read_tools.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.12.12 — 2026-11-24

Server self-documentation plus query/aggregate/map hardening from a live issue report.
Still 31 tools; no new Python dependency.

### Added

- **MCP `instructions`** — the server now sends `initialize` instructions
  (`guide.SERVER_INSTRUCTIONS`, ~1.4 KB): what the server is, the discover-first flow
  (find → `get_dataset_schema` → `query_dataset` → run → `show_map` → edit) and the
  consent / axis-order / paging rules. Clients that support MCP instructions inject it
  at connect, so an agent no longer needs a hand-written reminder to use the tools.
- **`geopack://guide` resource** (Markdown) — a **holistic** playbook, read on demand via
  `resources/read`: the portal object model (dataset/field/publication/relationship/task),
  a **tool inventory generated from `TOOL_POLICY`** (grouped by safety), task recipes
  (find→query, filter/query grammar, aggregate semantics, run an analysis/workflow, follow
  a relationship, show a map, local geometry, edit records) and the gotchas. It explains
  how the tools fit together, not merely what each one does; the long form never bloats
  the system prompt.
- **Editable content files** — both texts live as plain Markdown under
  `src/geopack_sdk_mcp/content/` (`instructions.md`, `guide.md`), viewable and editable
  without touching Python. Only the tool list is derived; it is injected at the
  `%%TOOL_INVENTORY%%` token so the prose stays hand-written and the inventory stays exact.

### Fixed

- **A flat or Mongo-ish `filter` node answered an opaque HTTP 500.** `query_dataset`
  (its `query.filter`) and `aggregate_dataset(filter=...)` now normalize the attribute
  scope to the portal's typed node grammar client-side (`sanitize/filter_dsl.py`): a flat
  `{field, operator, value}` rule is wrapped as a `rule`, a bare list of rules becomes an
  `AND` group, and a group without `type` is typed. Anything else — including a
  Mongo-style `{"field": {"$eq": 5}}` — is refused as `invalid_args` naming the accepted
  shapes, before any round trip. The grammar is documented on the tool surface
  (`tool_schema.FeatureFilter` / `FeatureQuery`).
- **A `uniqueValue` shorthand silently styled only a sample of the categories.**
  `show_map` derived one class per distinct value from the first 1,000 features, so an
  18,648-row dataset with 18 categories produced only 7 classes. It now groups the whole
  access-scoped column (via `aggregate` groupBy): all categories up to the documented cap
  (30) are styled, and above the cap the manifest warns with the exact distinct count and
  how many were left unstyled — never a silent under-style. (Class-breaks still samples;
  a quantile needs a representative distribution.)
- **`show_map(map_id=...)` could only append layers.** A corrected map kept serving its
  stale layers. `show_map` now accepts `replace_layers=true` (rebuild the map with exactly
  this call's layers) and `remove_layers` (drop named layer ids); unknown ids are reported
  in `templateWarnings` and the dropped ids come back as `removedLayers`.

### Notes

- Single source of truth: the inventory is built from the safety registry, and a
  completeness test fails if a registered tool has no guide line, so the guide cannot
  drift from the surface. The guide re-states — never weakens — the consent rules.
- A leading HTML comment in each content file is stripped from the served text, so the
  files can carry editing notes without leaking them to the model.

### Verification

- Full suite **820 tests** OK (was 791; +29 — guide/instructions, filter normalization,
  distinct-value symbology and map layer replacement).

Touched files:
- `src/geopack_sdk_mcp/guide.py`
- `src/geopack_sdk_mcp/content/guide.md`
- `src/geopack_sdk_mcp/content/instructions.md`
- `src/geopack_sdk_mcp/server.py`
- `src/geopack_sdk_mcp/resources/guide.py`
- `src/geopack_sdk_mcp/resources/__init__.py`
- `src/geopack_sdk_mcp/sanitize/filter_dsl.py`
- `src/geopack_sdk_mcp/tool_handlers/datasets.py`
- `src/geopack_sdk_mcp/tool_handlers/maps.py`
- `src/geopack_sdk_mcp/maps/manifest.py`, `maps/sources.py`
- `src/geopack_sdk_mcp/tool_schema.py`, `src/geopack_sdk_mcp/tools/maps.py`
- `tests/test_mcp_guide.py`, `tests/test_mcp_filter_dsl.py`, `tests/test_map_tools.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.12.11 — 2026-11-23

Legend derivation for a caller-supplied complete style spec (slice 033; SDK-008).
Viewer/handler fix; no new tool (31), no new Python dependency.

### Fixed

- **A caller-supplied COMPLETE `uniqueValue` `symbology` produced a blank legend.**
  `show_map` passed a spec that already carried `unique` through verbatim, skipping
  legend derivation, so the viewer panel drew an empty/grey row under the layer while
  the map styled correctly — inconsistent with the `classBreaks` shorthand and the
  dataset saved-renderer paths, which both derive a legend. A shared
  `ensure_legend` / `_legend_from_classes` builder (one source of truth for every
  legend-producing path) now derives `legend` from the spec's own `unique`/`breaks`:
  an entry label falls back to its value, the title is the field alias, and an
  explicit caller `legend` is honoured as-is.

### Verification

- Full suite **791 tests** OK (was 784; +7 — 5 `ensure_legend` unit tests and 2
  `show_map` caller-symbology tests).

Touched files:
- `src/geopack_sdk_mcp/sanitize/style_spec.py`
- `src/geopack_sdk_mcp/tool_handlers/maps.py`
- `tests/test_style_spec.py`
- `tests/test_map_tools.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

## 0.12.10 — 2026-11-23

View-at-location and geometry-with-embedded-style (slice 033). Viewer lane +
`show_map` sugar; no new tool (31), no new Python dependency.

### Added

- **`show_map(center=[lon, lat], zoom=N)`** — sugar for `template.view.*`; also sets
  `view.mode='center'` (unless a mode was given) so the map stays on the point instead
  of auto-fitting the layer extents. An implausible center or an out-of-range zoom
  (0–24) is warned and ignored.
- **Viewer URL view override** — an existing map can be pointed at a place without
  recreating it: `?center=lon,lat&zoom=N` (or `?lon=&lat=&z=`); when present the
  auto-fit is suppressed so the view stays put.
- **Per-feature styling** via the reserved `properties.__style__` key
  (`{fill,stroke,weight,radius,opacity}`) — styles one feature on top of the layer
  style (per-value `Style` cache). `__style__` is never mistaken for a normal
  attribute and is hidden from the identify popup.
- **Bare geometries** — an `inline-geometry` layer may now carry a bare geometry
  (Point/LineString/Polygon), a Feature, or a FeatureCollection; a bare geometry is
  wrapped so OpenLayers can read it.

### Changed

- **Layer list and legend are reversed** so the top of the panel matches the map
  stacking (the newest layer is drawn on top).

### Verification

- Full suite **784 tests** OK (was 781; +3 for center/zoom, invalid-center and
  URL-override/per-feature-style).

Touched files:
- `src/geopack_sdk_mcp/maps/templates/default/viewer.js`
- `src/geopack_sdk_mcp/tool_handlers/maps.py`
- `src/geopack_sdk_mcp/tool_schema.py`
- `src/geopack_sdk_mcp/tools/maps.py`
- `tests/test_map_tools.py`
- `tests/test_map_viewer.py`
- `pyproject.toml`, `src/geopack_sdk/__init__.py`, `CHANGELOG.md`

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
