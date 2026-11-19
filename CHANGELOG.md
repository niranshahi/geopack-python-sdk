# Changelog

All notable changes to `geopack-sdk` and the bundled MCP server (`geopack_sdk_mcp`).
Append-only; newest first.

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
