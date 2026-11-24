<!-- Editable: this file is served verbatim as the `geopack://guide` resource.
     Write the prose freely. Leave the `%%TOOL_INVENTORY%%` token on its own line — the
     loader replaces it at read time with the tool list generated from the safety
     registry (TOOL_POLICY). Do not hand-edit that generated section (it would drift);
     edit the prose around it and the per-tool lines in guide.py's PURPOSES. -->

# Geopack SDK MCP — usage guide

A gateway to a **Geopack portal**: a catalog of spatial datasets plus workflows, analysis
tools and background tasks. Every read is *access-scoped* to the caller's account — you
see exactly the rows and fields that account may see, never more.

The core habits:

1. **Discover first.** Find the dataset, read its schema, then act. Never guess a field
   name, a relationship name, a publication id or a coded value.
2. **Answer-first.** For a count, sum, average, distribution or top-N, use
   `geopack_sdk_aggregate_dataset` — it is exact and one call. Do **not** page records to
   compute a statistic.
3. **Geometry is GeoJSON `[lon, lat]`** in EPSG:4326 unless a result says otherwise.
4. **Ask before writing.** Every mutating tool needs the user's explicit go-ahead, and
   `geopack_sdk_get_mcp_safety_policy` is the authority on which tools write.

A result is either the data (a normal payload) or a structured error
(`{"error": true, "code", "message", "hint", "invalidArgs"}`). Branch on `code`, read
`hint` for the next step, and never retry a 4xx that names a wrong argument.

%%TOOL_INVENTORY%%

## The portal objects, in one breath

- **Dataset** — a table/vector/raster/table source with fields, an extent and (for
  vector) a geometry. Identified by an integer `datasetId`.
- **Field** — has a `name`, a `type`, often an `alias` (display label) and sometimes a
  **coded-value domain** (an integer `code` maps to a human label). Always read
  `geopack_sdk_get_dataset_schema` before writing a field into a filter or aggregate.
- **Publication** — a published, renderable view of a dataset (WMS/WMTS/WFS/tiles). It
  has its own integer `publicationId` and may carry the dataset's **official symbology**.
  A publication id is **not** a dataset id.
- **Relationship** — a named hop from a dataset's records to another dataset's records.
  The name comes from `geopack_sdk_get_dataset_relationships`; never invent one.
- **Workflow / analysis tool** — a saved graph, or a catalog entry that runs as one.
- **Task** — the async unit behind uploads, exports, workflow runs and analyses.

## Recipes

### Find -> inspect -> query
1. `geopack_sdk_list_datasets` — paginated catalog. `order_by` defaults to newest first,
   so "the 10 latest" is `page_size=10`. `bbox` filters on the dataset's **stored**
   extent, not feature geometry (a null-extent dataset, common for rasters, is simply not
   matched). Use `geopack_sdk_geocode_place` to turn a place name into coordinates first.
2. `geopack_sdk_get_dataset` — confirm the dataset; `geopack_sdk_get_dataset_schema` —
   the **field contract**: real names, types, aliases, coded-value domains and valid
   relationship names.
3. `geopack_sdk_query_dataset` — page features. Pass a `query` FeatureQuery for filters
   / projection / ordering, or the `limit`/`offset`/`return_geometry`/`out_srid` shorthands.
   The page is bounded (`limit` is capped at 500); it is **never** the whole dataset unless
   you deliberately raise the limit.
4. `geopack_sdk_aggregate_dataset` — when you only need counts/stats (see below).

### Filter and query grammar
`filter` is a typed node tree:

```
{"type": "rule",  "field": "<name>", "operator": "<op>", "value": <value>}
{"type": "group", "operator": "AND" | "OR", "children": [ <rule|group>, ... ]}
```

Operator tokens are the portal's own (`=`, `$ilike`, `IN`, ...). A **flat** rule
(`{"field": ..., "operator": ..., "value": ...}`) and a **list** of rules (combined with
AND) are accepted and normalized for you; any other shape — including a Mongo-style
`{"field": {"$eq": 5}}` — is refused as `invalid_args` **before** the round trip, so fix
the shape rather than chasing a server error. Put the same node grammar under
`query.filter` and under `aggregate_dataset(filter=...)`.

### Aggregate
Use `geopack_sdk_aggregate_dataset` for `count`, `countDistinct`, `sum`, `avg`, `min`,
`max`, `stddev`/`stddevPop`, `variance`/`varPop`, `median` and `percentile` (with `p` in
0..1). `group_by` holds at most 3 fields; `order_by` at most 3 entries keyed by a group
field or an aggregate alias (a count aggregate's key is `count`/`aggregate_count` — its
alias is accepted and translated). `limit` is 1..50 buckets. Rows come back **verbatim**;
do the reading, not the arithmetic.

### Run an analysis or a workflow
1. `geopack_sdk_list_analysis_tools` -> pick a tool and its inputs.
2. `geopack_sdk_run_analysis` (ask the user first — it starts a run).
3. Poll with `geopack_sdk_get_task` or block with `geopack_sdk_wait_for_task`, then read
   outputs with `geopack_sdk_get_analysis_result`.

For a saved graph: `geopack_sdk_get_workflow` (definition) or
`geopack_sdk_get_workflow_spec` (portable wf-spec graph) -> `geopack_sdk_submit_workflow`.

### Follow a relationship
1. `geopack_sdk_get_dataset_relationships` for the valid names (a 409
   `catalogUnavailable` is a **state**, not a bug — that dataset has no relationship lane).
2. Get the **OID** values from a records query (`oidField` is in the schema).
3. `geopack_sdk_get_related_records` with one relationship name and those OIDs. `__jct__*`
   properties are junction fields — keep them beside the record, do not fuse them in.

### Show a map
`geopack_sdk_show_map` starts a **localhost-only** viewer and returns a live `viewerUrl`
(an OpenLayers page) plus stable `dataUrl`/`tileUrl` links. It is opt-in
(`GEOPACK_MCP_MAP_SERVICE=1`), holds the portal credential server-side, and produces **no
image** — the user opens the URL in a browser.

- **Layers:** `portal-dataset` (vector GeoJSON/MVT, or a COG when the dataset is a
  Cloud-Optimized GeoTIFF), `portal-publication` (WMS/WMTS/WFS — the path that shows a
  dataset's *official* symbology), `local-file` (under `GEOPACK_MCP_MAP_ROOT`), and
  `inline-geometry` (GeoJSON you supply, e.g. from `geopack_sdk_geometry_op`).
- **Extent:** omit `bbox` and each layer borrows its source dataset's WGS84 extent;
  `bbox` is `[west, south, east, north]` and `view.center` is `[lon, lat]`.
- **Symbology:** pass `symbology: {type:'uniqueValue', field}` for one colour **per
  distinct value** (derived by grouping the whole column, up to a documented cap), or
  `{type:'classBreaks', field, classes?}` for quantile breaks. A complete
  `{unique:[...]}`/`{breaks:[...]}` spec is honoured, and a missing `legend` is derived for
  you so the panel is never blank.
- **Editing an existing map:** `show_map(map_id=...)` **appends** layers by default. Pass
  `replace_layers=true` to rebuild it with exactly this call's layers, or `remove_layers`
  with layer ids to drop specific layers. Unknown ids are reported in `templateWarnings`.
- **Geometry cap:** a GeoJSON dataset layer loads a bounded page (default 1,000). When the
  dataset is larger the manifest warns with the totals — **you choose** whether to raise
  `limit` (or 0 for all) or switch to `render:'mvt'`; ask the user when unsure.

### Local geometry
`geopack_sdk_geometry_op` runs shapely locally on GeoJSON/WKT you supply (buffer, area,
length, centroid, intersect, union, ...). No portal call, no data leaves the machine. The
result feeds straight into an `inline-geometry` map layer.

### Chart your data
`geopack_sdk_render_chart` draws a **bar / line / pie** chart from tabular rows you already
have — local compute, no portal call. Feed it `geopack_sdk_aggregate_dataset`'s `rows`:

- `rows` = the aggregate rows (a list of objects); `category` = the label/group field;
  `value` = the numeric field (e.g. `aggregate_count`, `sum`).
- `chart_type` = `bar` (comparisons) · `line` (a sequence) · `pie` (shares). An optional
  `series` field splits a bar/line chart into multiple series; an optional `title` labels it.
- The result is an inline **SVG** image (`image/svg+xml`), with the same `points` echoed in
  the payload (and, for a pie, `slices` with `{label, value, percent}`) so a client that
  does not display SVG still receives the data. This is the charting lane — `show_map`
  draws a map, not a statistical chart.
- **As a file:** pass `save_path` to also write the chart (best-effort; `saved`/`savePath`/
  `saveError` in the payload) and `format` `svg` (default; needs nothing) or `png`
  (rasterises via the optional `cairosvg` engine, `geopack-sdk[charts]`).

### Edit records
1. Build an EditDoc and call `geopack_sdk_submit_edit_document` with `mode='validate'`
   (or `'preview'`) — it writes nothing.
2. Confirm the diff with the user, then re-call with `mode='apply'`.

## Gotchas

- **Axis order:** GeoJSON is `[lon, lat]`. `query_dataset` defaults to EPSG:4326; a
  projected dataset is reprojected when possible and its result names the CRS actually
  returned (`outSridApplied`) — never assume.
- **Read the schema first:** field names, aliases and coded-value domains come from
  `geopack_sdk_get_dataset_schema`; a coded value in the data is its **code**, and the
  domain gives the human label.
- **Paging:** `query_dataset` returns one bounded page. Raise `limit` deliberately, or ask
  the user before a huge pull. The server may **degrade** a total count to `null` (very
  large sets / timeout) — that is a normal answer, not an error.
- **Consent:** call `geopack_sdk_get_mcp_safety_policy` before any mutating tool and for
  upload caps; a mutating call needs the user's explicit go-ahead. MCP never deletes
  datasets.
- **Local writes:** `download_*` and the thumbnail save are best-effort on a sandboxed
  host — they answer `saved=false` with the data still delivered inline rather than
  failing. No file appearing on disk is expected, not an error.
- **Rasters:** a raster `portal-dataset` layer is vector-only and warns; use a raster
  WMS/WMTS `portal-publication`, or rely on the COG lane when `details.hasCOG` is set.
- **Error contract:** branch on `code`, read `hint`, and fix `invalidArgs`. A 5xx is a
  portal failure (retry once); a named 4xx means the call, not the server, is wrong.
