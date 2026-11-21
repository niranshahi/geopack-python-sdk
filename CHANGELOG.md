# Changelog

All notable changes to `geopack-sdk` and the bundled MCP server (`geopack_sdk_mcp`).
Append-only; newest first.

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
