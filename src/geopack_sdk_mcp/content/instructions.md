<!-- Editable: this file is served as the MCP *instructions* sent in the `initialize`
     result. Keep it short (it lands in the model's context at connect); the long form
     lives in guide.md. -->

Geopack SDK MCP — a gateway to a Geopack portal: datasets, spatial/attribute queries,
workflows and analysis, maps, tasks, uploads and local geometry.

Work discover-first: find, then inspect, then act.
- Find: geopack_sdk_list_datasets (attribute + spatial filters), geopack_sdk_geocode_place
  (place name -> coordinates).
- Inspect: geopack_sdk_get_dataset, and ALWAYS geopack_sdk_get_dataset_schema before
  writing any where/order clause (it gives real field names, types, aliases and
  coded-value domains).
- Read: geopack_sdk_query_dataset (paged GeoJSON; default CRS EPSG:4326),
  geopack_sdk_aggregate_dataset (group counts/sums/stats), geopack_sdk_export_dataset.
- Run: geopack_sdk_list_analysis_tools -> geopack_sdk_run_analysis ->
  geopack_sdk_wait_for_task (or geopack_sdk_submit_workflow for a saved graph).
- Show: geopack_sdk_show_map opens a live built-in viewer (localhost, opt-in).
- Edit (writes): geopack_sdk_submit_edit_document — run mode='validate'/'preview' first.
- Local: geopack_sdk_geometry_op (buffer/intersect/area/... on supplied GeoJSON/WKT).

Rules: geometry is GeoJSON with [lon, lat] (EPSG:4326) coordinates. Call
geopack_sdk_get_mcp_safety_policy before any mutating tool and for upload caps; a mutating
call needs the user's explicit go-ahead. Read the geopack://guide resource for recipes, the
full tool list and the gotchas.
