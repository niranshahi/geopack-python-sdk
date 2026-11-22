# Geopack Python SDK

A standalone Python library to interact with the Geopack Geoportal API.

Current release: **0.12.1** — see [CHANGELOG.md](CHANGELOG.md).

## Naming

| What | Name |
|------|------|
| This folder (monorepo) | `python-sdk/` |
| GitHub repository | [geopack-python-sdk](https://github.com/niranshahi/geopack-python-sdk) |
| `pip install` | `geopack-sdk` |
| Python import | `geopack_sdk` |

```python
from geopack_sdk import GeopackClient, AsyncGeopackClient
```

## Installation

```bash
pip install geopack-sdk
```

Async client (parallel task polling, non-blocking REST):

```bash
pip install geopack-sdk[async]
```

Or from Git:

```bash
pip install git+https://github.com/niranshahi/geopack-python-sdk.git
pip install "geopack-sdk[async]"
```

## Client surface

Every manager is available on both `GeopackClient` and `AsyncGeopackClient`:

| Manager | What it drives |
|---------|----------------|
| `client.datastores` / `client.datasets` | DataStore catalog, datasets, CRUD, query lanes |
| `client.edit_documents` / `client.computed_columns` | Edit documents, virtual datasets, computed columns |
| `client.uploads` / `client.tasks` | Upload caps and task control (cancel, stats, wait) |
| `client.workflows` / `client.workflow_runs` | Workflow specs, runs, statistics |
| `client.analysis_tools` / `client.generated_files` | Analysis tools, generated-file artifacts |
| `client.quotas` / `client.users` / `workgroups` / `groups` / `organizations` | Governance and identity |
| `client.maps` | Saved map DOCUMENTS + thumbnails + ACL (control plane) |
| `client.publications` | Publication lifecycle: enable/disable/reconcile, styles, render scopes, minted URLs |
| `client.print_layouts` | Print-layout TEMPLATE registry + thumbnails + ACL |
| `client.external_services` | External OGC registrations: CRUD, probe, style, map settings |

**Maps and layouts are stored, never produced.** The portal has no render / export / rasterize
endpoint, and the SDK deliberately adds none: `client.maps` and `client.print_layouts` read and write
records (documents, template JSON, caller-uploaded thumbnails). Rendering a map image or a printout is
the consuming agent's job, with its own tools.

**Parity:** every public manager method exists on both clients. `tests/test_async_parity.py`
enumerates the sync surface and fails when an async twin is missing, when an argument name or
required/optional status drifts, or when a new async-only helper is not recorded with a reason. Two
honest exceptions: `AsyncWorkflowManager.extract_params` is a **plain** method (pure computation over
the graph, no I/O — awaiting it would be a lie) and `AsyncTaskManager.wait_for_tasks` has no sync twin
(parallel polling is what `asyncio.gather` is for).

**File I/O in async.** `upload`, `download`, `download_artifact` and the generated-file download use
`httpx.AsyncClient` for the network and `asyncio.to_thread` for every file read/write
(`AsyncGeopackClient._stream_to_file` is the shared streaming helper). No coroutine ever calls
`requests`, and a blocking geopandas build runs in a worker thread too.

## Examples & Notebooks

We provide a collection of Jupyter Notebooks in the `notebooks/` directory to help you get started:

1. `01_Getting_Started.ipynb` — connection and data exploration.
2. `02_Data_Analysis_GeoPandas.ipynb` — GeoPandas analysis.
3. `03_Raster_Workflows.ipynb` — workflows, task + run inspection.
4. `04_Data_Management_and_Tasks.ipynb` — upload, export, task log severity.
5. `05_Advanced_API_Coverage.ipynb` — quotas, generated files, dataset query / ACL.
6. `06_ESRI_Geodatabase_Manager.ipynb` — ESRI geodatabase discover / register / schemas (portal manager parity).
7. `07_Async_Client.ipynb` — `AsyncGeopackClient`, `asyncio.gather`, parallel task polling.

**Note for Developers:** Notebooks use the local `src/` directory when cloned from the repo (no `pip install` required).

### Live integration tests (`test_*.py`)

Require a running API and `.env` (`GEOPACK_API_URL`, `GEOPACK_USERNAME`, `GEOPACK_PASSWORD`):

| Script | Purpose |
|--------|---------|
| `test_sdk.py` | Login, list datasets/datastores |
| `test_upload.py` | Upload (`TEST_GEOJSON_PATH`) |
| `test_download.py` | Export + download |
| `test_workflow.py` | Workflow run |
| `test_geopandas.py` | GeoDataFrame |
| `test_quotas.py` | `GET /quotas/me/summary` |
| `test_generated_files.py` | Generated files list/download |
| `test_dataset_query.py` | Structured dataset query |
| `test_dataset_acl.py` | Dataset ACL (read-only by default) |
| `test_esri_datastore.py` | ESRI geodatabase discover/info (mutations via env flags) |
| `test_async_sdk.py` | Async login, `asyncio.gather`, optional `TEST_TASK_ID` / `TEST_TASK_IDS` |
| `test_mcp_sdk.py` | MCP tool **handlers** + API (same logic as tools; **not** stdio MCP) |
| `test_mcp_stdio_client.py` | **Full E2E**: spawns MCP server, `call_tool` over stdio (like Cursor) |

**Unit tests** (no server): `PYTHONPATH=src python -m unittest discover -s tests`

# Initialize client
client = GeopackClient(base_url="https://your-geoportal.com/api")

# Login
client.auth.login(username="admin", password="password")

# List datasets
datasets = client.datasets.list()
for ds in datasets:
    print(ds.name)
```

## Configuration

The SDK can be configured using parameters or environment variables (recommended for security).

### 1. Using Environment Variables
Create a `.env` file in your project:
```bash
# Note: this should be the API base URL and typically includes `/api`
# Example: http://localhost:3000/api
GEOPACK_API_URL=https://your-geoportal.com/api
GEOPACK_USERNAME=admin
GEOPACK_PASSWORD=your_secure_password
```

Then use the SDK without hardcoding:
```python
from dotenv import load_dotenv
from geopack_sdk import GeopackClient

load_dotenv() # Load variables from .env

client = GeopackClient()
client.auth.login() # Automatically uses ENV variables

datasets = client.datasets.list()
```

### 2. Using Parameters (Explicit)
```python
client = GeopackClient(base_url="https://api.geopack.com")
client.auth.login(username="my_user", password="my_password")
```

## Features
- Datasets, DataStores, Workflows, **Analysis tools** (a workflow run as a typed tool), Tasks, **Generated Files**, **Quotas (self)**.
- Dataset **delete**, **ACL**, structured **query** (`build_simple_query`), **discover**.
- Workflow **delete** with an explicit run cascade: `workflows.delete(id)` refuses (409) while the workflow still owns runs, `with_runs=True` accepts the irreversible cascade, and the typed `WorkflowHasRuns` / `WorkflowHasActiveRuns` errors carry the counts.
- Sync and **async** clients (`GeopackClient`, `AsyncGeopackClient`); parallel task polling via `wait_for_tasks` (`partial_success` is terminal and returned like `completed`).
- Task message helpers aligned with the portal UI.
- HTTP retries on 502/503/504; typed exceptions.
- GeoPandas integration; **Geopack SDK MCP** server (**31 tools** + 2 resource templates, v0.12.0+; read lanes for schema/aggregate/relationships/workflow-spec, workflow execution incl. typed analysis tools, the edit ladder, upload, a loopback-only local map data service with a built-in viewer, and local geometry ops; no create/edit/delete of workflows via MCP, no delete at all, no map-image/print export).

## Geopack SDK MCP (Cursor / Claude Desktop)

Typed REST proxy via MCP — not the in-portal assistant. Credentials stay in the MCP server **environment**, never in tool arguments.

**Use the project venv** (recommended — same as notebooks):

```powershell
cd python-sdk
.\venv\Scripts\activate
pip install -e ".[mcp]" --disable-pip-version-check
```

`mcp` is an **optional** dependency in `pyproject.toml` (`[project.optional-dependencies] mcp`) so `pip install geopack-sdk` alone does not pull it in. Install `geopack-sdk[mcp]` or `geopack-sdk[all]` when you need the MCP server.

> **Reinstalling after a code change:** `pip install -e ".[mcp]" --force-reinstall --no-deps --disable-pip-version-check` — skips dependency re-resolution (deps are already installed).
>
> **Windows note:** on some machines pip prints `Successfully installed geopack-sdk-X.Y.Z` and then appears to **hang**. This is pip's post-install version self-check writing to a locked `%LOCALAPPDATA%\pip` cache — **not** a package/build problem. The install has already succeeded: stop it (Ctrl+C) and confirm with `pip show geopack-sdk`. Keeping `--disable-pip-version-check` on the command prevents it.

**Testing (API must be running, `.env` in `python-sdk/`):**

| Command | What it verifies |
|---------|------------------|
| `python test_mcp_sdk.py` | MCP tool handlers + REST (not stdio protocol) |
| `$env:MCP_CHECK_SERVER="1"; python test_mcp_sdk.py` | Above + tools register on FastMCP |
| `python test_mcp_stdio_client.py` | **Full E2E:** tools + geocode + bbox list + resources |
| `python test_mcp_llm_prompt.py --staged "…"` | LLM intent → MCP geocode → list (no Jupyter) |
| `python test_mcp_llm_prompt.py --loop "…"` | OpenAI tool loop over real MCP tools |
| `python examples/langchain_geopack_agent.py` | **LangChain agent** — MCP tools via langchain-mcp-adapters |
| `python examples/langchain_geopack_geocode_workflow.py` | LangChain agent — geocode then list (system prompt) |
| `python -m unittest tests.test_geocoding` | Unit test: Nominatim bbox parsing (mocked HTTP) |
| `python -m geopack_sdk_mcp` | Server only; waits for MCP host (Ctrl+C to stop) |
| `python -m unittest discover -s tests` | Unit test: All tests |

Always use `python script.py`, not `.\script.py` on Windows (wrong interpreter).

**Auth (recommended):** run once in a terminal (with `GEOPACK_API_URL` in `.env` or env):

```bash
geopack-sdk login
geopack-sdk status
```

Tokens are saved to `~/.geopack/credentials.json` (mode `0600`). MCP reads them at startup — no password in IDE config.

**Cursor** (`mcp.json` — use venv executable):

```json
{
  "mcpServers": {
    "geopack-sdk-mcp": {
      "command": "D:\\Works\\geopack-geoportal\\geopack-geoportal-v2\\python-sdk\\venv\\Scripts\\geopack-sdk-mcp.exe",
      "env": {
        "GEOPACK_API_URL": "http://localhost:3000/api",
        "GEOPACK_USERNAME": "your_user",
        "GEOPACK_PASSWORD": "your_password"
      }
    }
  }
}
```

Alternatives: `GEOPACK_ACCESS_TOKEN` in env, or username/password in `env` (dev only). See [MCP authentication options](../docs/09-sdk/mcp-design/mcp-auth.md).

**MCP environment variables — where to set them.** Every `GEOPACK_*` value (auth **and** the optional
map/geometry settings below) goes in the **same `env` object** as `GEOPACK_API_URL` in the host config:

| Host | Config file | Where |
|---|---|---|
| Cursor | `mcp.json` (`.cursor/mcp.json` or global) | `mcpServers.<name>.env` |
| Claude Desktop | `claude_desktop_config.json` | `mcpServers.<name>.env` |
| Manual run | `python-sdk/.env` (loaded by the SDK) or the shell env | same names |

They are **not** read from the portal's `.env` and cannot be passed as tool arguments. After editing the
host config, **restart the MCP host** — the server reads env once at startup.

| Variable | Default | When / what to set |
|---|---|---|
| `GEOPACK_MCP_MAP_SERVICE` | unset (off) | `"1"` to enable `geopack_sdk_show_map`. Without it, `show_map` answers `MAP_SERVICE_BLOCKED`; `geometry_op` works regardless. |
| `GEOPACK_MCP_MAP_ROOT` | unset | **Absolute path** to an existing directory that holds the local layers you want `/local`·`/data` to serve. Files must be under it and use an allow-listed extension (`.geojson .json .gpkg .csv .kml .zip`). Omit it and only inline/portal layers are usable. |
| `GEOPACK_MCP_MAP_CORS` | unset (off) | `"1"` only when an **agent-authored page on another origin** must fetch `/data`·`/tiles`. Same-origin pages need nothing. Keep off otherwise. |
| `GEOPACK_MCP_MAP_IDLE_TIMEOUT` | `1800` | Seconds of inactivity before the local service stops itself. Raise for long editing sessions; `0` disables the idle stop. |
| `GEOPACK_MCP_MAP_PORT` | `0` (random) | Pin the loopback port so a client page/script keeps a stable URL across idle restarts. A random port changes every time the service restarts (e.g. after an idle stop). |
| `GEOPACK_MCP_MAP_TEMPLATES` | `~/.geopack/mcp/maps` | Folder holding the user's `template.json` + optional **`viewer.html`** (the whole page) and `viewer.css`, so the built-in viewer is restyled/rebranded without editing the package. `show_map` returns `templatePath`/`viewerHtmlPath` so you know where to edit. |
| `GEOPACK_MCP_MAP_ASSETS` | unset (CDN) | Absolute path to a folder with `ol.js` + `ol.css` to serve the viewer runtime **locally** (offline/airgapped). Unset = the pinned OpenLayers CDN, no build step. |
| `GEOPACK_MCP_PROXY_HOSTS` | unset | Comma-separated **extra** hosts the proxy may reach, besides the portal host. Set it only when minted GeoServer URLs live on a different host than `GEOPACK_API_URL` (otherwise `show_map` tiles answer "host is not allow-listed"). |
| `GEOPACK_MCP_GEOMETRY_ENGINE` | `shapely` | Selects the local geometry engine. **`shapely` is the only registered engine**; leave it unset unless you are testing a substitute. |
| `GEOPACK_MCP_SKIP_DOTENV` | unset | `"1"` stops the MCP from auto-loading `python-sdk/.env` — use when the host `env` block is the single source of truth. |
| `GEOPACK_MCP_UPLOAD_ROOT` | unset | Restricts `upload_dataset`'s `file_path` to an existing directory (containment guard). Omit to allow any readable file. |
| `GEOPACK_MCP_MAX_UPLOAD_BYTES` | `500 MiB` | Local upload size guard in bytes; the portal's own limits still apply. |

Optional map/geometry block (add to the existing `env`; every value is optional):

```json
{
  "mcpServers": {
    "geopack-sdk-mcp": {
      "command": "D:\\Works\\geopack-geoportal\\geopack-geoportal-v2\\python-sdk\\venv\\Scripts\\geopack-sdk-mcp.exe",
      "env": {
        "GEOPACK_API_URL": "http://localhost:3000/api",
        "GEOPACK_USERNAME": "your_user",
        "GEOPACK_PASSWORD": "your_password",
        "GEOPACK_MCP_MAP_SERVICE": "1",
        "GEOPACK_MCP_MAP_ROOT": "C:\\Users\\you\\geopack-maps",
        "GEOPACK_MCP_MAP_CORS": "0",
        "GEOPACK_MCP_MAP_IDLE_TIMEOUT": "1800",
        "GEOPACK_MCP_MAP_PORT": "0",
        "GEOPACK_MCP_PROXY_HOSTS": "geoserver.example.com",
        "GEOPACK_MCP_GEOMETRY_ENGINE": "shapely"
      }
    }
  }
}
```

No new Python dependency is needed for either lane: the server is `http.server` (stdlib) and the
geometry engine uses `shapely`/`pyproj`, already pulled in by `geopandas`.

**Safety:** Dataset/generated-file **delete is not an MCP tool** (use Geoportal UI). **No workflow authoring or deletion over MCP** either — `geopack_sdk_get_workflow_spec` reads a graph, it cannot create, save or delete one. Call `geopack_sdk_get_mcp_safety_policy` for server rules. Upload/workflow: host must get explicit user consent in chat before calling. See [MCP Safety Policy](../docs/09-sdk/mcp-design/mcp-safety.md).

**Thumbnails — inline is the official mode.** `geopack_sdk_get_dataset_thumbnail` returns the image inside the tool result (the host renders it) and **writes no file unless `save_path` is passed**. A sandboxed host that forbids local writes answers `saved:false` (`saveSkipped:true` when no `save_path`) while the image still comes back — **no file appearing on disk is the expected outcome, not a failure**; `save_path` works only where the host permits writes.

**Local map service + built-in viewer (v0.12.0+, `geopack_sdk_show_map`).** Opt-in (`GEOPACK_MCP_MAP_SERVICE=1`): the MCP opens a **loopback-only** (`127.0.0.1`, ephemeral port, token-gated) HTTP service that **proxies portal data with the MCP's own credentials** and serves local files, then returns a live **`viewerUrl`** plus stable data URLs (`/data`, `/tiles`) a page can reference **instead of embedding data**. The viewer is an **OpenLayers** page served from the same origin and draws GeoJSON, MVT vector tiles, WMS/WMTS images, WFS vector data and XYZ raster — the portal's layer families — with a layer list, basemap switcher and legend. It is **themeable without a build**: edit `template.json` under `GEOPACK_MCP_MAP_TEMPLATES` (title, basemaps, palette, layer style, panels), drop in your own **`viewer.html`** (the whole page is an editable resource, not embedded code), or pass per-call `template`/`style`/`basemap` overrides. OSM tiles load in-browser with a per-element referrer policy, so no "access blocked" image. The viewer runtime comes from a pinned CDN by default; set `GEOPACK_MCP_MAP_ASSETS` to a local `ol.js`/`ol.css` for offline installs. The portal credential stays in the MCP process; only a low-sensitivity session token crosses (`?t=` in `viewerUrl`, embedded into the page by the server; `#t=` also works when a host strips the query). A host that forbids binding answers `MAP_SERVICE_BLOCKED`. **No map image is produced** — the browser draws the live map.

**Local geometry ops (v0.11.0+, `geopack_sdk_geometry_op`).** A **local** compute lane (shapely/pyproj behind a GeoJSON-only engine port) — **no portal call**: `buffer`, `overlay` (`union|intersection|difference|xor|clip`), `convex_hull`, `envelope`, `dissolve`, `simplify`, `validate`, `fix`, `convert`, `project`, `measure`, `distance`, `nearest`, `line_between`, `point_on_surface`, `smooth`, `create`, `describe`. Metric ops auto-project to a local UTM; results carry provenance (`engine`/`methodUsed`/`crsUsed`). Geodesic buffer is not available in v1 (honest code).

**Tools (31, v0.11.0+):**

| Tool | Purpose |
|------|---------|
| `geopack_sdk_get_mcp_safety_policy` | Server rules: mutating tools, local writes, refused operations, upload caps |
| `geopack_sdk_geocode_place` | Place name → WGS84 bbox (Nominatim; use before spatial list) |
| `geopack_sdk_list_datasets` | Paginated list; `bbox`, `data_type`, dates; `details_level` default `lite` (compact cards, `fields` to widen); `order_by` on `updatedAt`/`name`/... |
| `geopack_sdk_get_dataset` | One dataset; `details_level` default `full`; optional `fields` key projection |
| `geopack_sdk_get_dataset_schema` | Field contract: names, types, domains, field access, relationship names |
| `geopack_sdk_query_dataset` | Feature query (max 500 features in JSON) |
| `geopack_sdk_aggregate_dataset` | Counts, sums, distributions, top-N in one call (the answer-first lane); `order_by` accepts the count (`count`/`aggregate_count`), a group field, or a named aggregate |
| `geopack_sdk_get_dataset_relationships` | The relationship names valid for this dataset |
| `geopack_sdk_get_related_records` | One relationship hop from a set of OIDs |
| `geopack_sdk_get_dataset_thumbnail` | Return the preview image **inline** (MCP image content); **nothing is written to disk unless `save_path` is given** (best-effort, never fatal) |
| `geopack_sdk_get_task` | Task status (sanitized) |
| `geopack_sdk_cancel_task` | Request cancellation of a running task (best effort) |
| `geopack_sdk_wait_for_task` | Poll until export/job completes |
| `geopack_sdk_get_quota_summary` | Caller's quota usage per dimension |
| `geopack_sdk_list_generated_files` | Downloadable exports/workflow outputs with ids; `search_query` by name, `order_by` on `createdAt`/`fileName`/`fileSize`/... |
| `geopack_sdk_upload_dataset` | Upload local file on MCP host → `dataset:upload`; use `metadata.name` for title |
| `geopack_sdk_export_dataset` | Start `dataset:export` (returns `taskId`) |
| `geopack_sdk_download_generated_file` | Save export to local `save_path` on MCP host |
| `geopack_sdk_list_workflows` | List workflows (no `graphJson` in JSON); `order_by` on `id`/`name`/`owner.userName`/`updatedAt`/... |
| `geopack_sdk_get_workflow` | Workflow metadata; `include_params=true` adds `parameters[]` |
| `geopack_sdk_get_workflow_spec` | The saved graph as a model-facing wf-spec (nodes, operators, config); no canvas positions. Read-only — never creates or saves |
| `geopack_sdk_submit_workflow` | Start run; returns `workflowRunId` + `taskId` |
| `geopack_sdk_list_workflow_runs` | Runs you can see (id, status, submitter, timestamps); `order_by` on `status`/`startedAt`/`finishedAt`/... |
| `geopack_sdk_get_workflow_run` | Run status + artifacts |
| `geopack_sdk_download_workflow_artifact` | Save workflow output on MCP host |
| `geopack_sdk_list_analysis_tools` | The workflows this caller may run, as typed tools; `tool_id` for one manifest |
| `geopack_sdk_run_analysis` | Run one by `tool_id` + `params`; waits by default. **Mutating** — consent first |
| `geopack_sdk_get_analysis_result` | Result summary (scalars, datasets, artifacts) — never records |
| `geopack_sdk_submit_edit_document` | EditDoc ladder `validate` → `preview` → `apply`. **Mutating** — `apply` writes records |
| `geopack_sdk_show_map` | Start/update the **loopback-only** local map service, declare layers and return a live **`viewerUrl`** (OpenLayers page) plus layer `dataUrl`·`tileUrl`·`wmsUrl`/`wmtsUrl`/`wfsUrl` and a low-sensitivity session token; themeable via `template`/`style`/`basemap` and a user `template.json`. Opt-in (`GEOPACK_MCP_MAP_SERVICE=1`). Holds the portal credential server-side; produces **no map image** |
| `geopack_sdk_geometry_op` | Run one **local** geometry op (buffer, overlay, hull, envelope, dissolve, simplify, validate/fix, convert, project, measure, distance, nearest, line_between, point_on_surface, smooth, create, describe). No portal call; WGS84 output with provenance |

**Error contract (v0.7.0+):** a failed call answers `isError: true` with `structuredContent` = `{error, code, type, statusCode, message, hint, invalidArgs?}`. `code` is the server's coded error when it sends one, otherwise derived from the exception class (`DATASET_READ_ONLY`, `AGGREGATION_UNSUPPORTED`, `EDIT_CONFLICT`, `QUOTA_EXCEEDED`, …). `hint` names the next tool to call; `invalidArgs` lists the arguments a client-side validator refused before any network call. `get_dataset_relationships` still degrades to `catalogUnavailable: true` with `isError: false` (a state, not a failure); `get_mcp_safety_policy` never fails.

**Annotations (v0.7.0+):** every tool declares `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`. `destructiveHint` is true only for `submit_edit_document`; `openWorldHint` only for `geocode_place` and `run_analysis`; `readOnlyHint` is false for the three file-saving tools and the mutating tools, while `idempotentHint` is false for them too and for `export_dataset` (a read that still mints a new artifact on every call).

**Transport:** stdio only in 0.8.0 (`python -m geopack_sdk_mcp`, no transport flag). A future HTTP mode must solve per-request identity (the current bootstrap caches one process-wide client/token), OAuth/token pass-through, and multi-tenant temp-file isolation before it can be offered.

**Resource templates (not listed as tools in Cursor UI):**

| URI template | Purpose |
|--------------|---------|
| `dataset://{dataset_id}/thumbnail` | PNG preview (`resources/read`) |
| `generated-file://{file_id}/download` | Export file bytes (prefer download tool for large files) |

**Export flow:** `export_dataset` → `wait_for_task` → `download_generated_file` (see MCP design doc §12).

**Workflow flow:** `get_workflow(include_params=true)` → `submit_workflow` → `wait_for_task` → `get_workflow_run` → optional `download_workflow_artifact` (MCP design doc §14; notebook `11_LangChain_MCP_Workflow_Execution.ipynb`).

**Analysis flow:** `list_analysis_tools` → `list_analysis_tools(tool_id=…)` for its parameter manifest → `run_analysis(tool_id, params)` → result summary (or `get_analysis_result(run_id)` after `wait=false` / a timeout). Unlike the workflow flow this needs no `wait_for_task`: the tool waits on the run, not the task. The catalog **is** the caller's run set — there is no publish step (ADR-0019).

**Upload flow:** place file on MCP host → `upload_dataset(file_path, data_store_id, workgroup_id, declared_type?, metadata?)` → `wait_for_task` → read `createdDatasetId` from task `results` → optional workflow submit. For a custom title pass `metadata={"name": "My dataset"}`. Inline GeoJSON is not a tool arg — write to disk first. Restart MCP after upgrading so `metadata` appears in the tool schema.

**Dataset thumbnails:** Tool JSON has `hasThumbnail`, `thumbnailApiPath`, `thumbnailMintPath`, `thumbnailResourceUri` (no BLOB, **no JWT in JSON**). MCP fetches bytes via Bearer on `GET /datasets/{id}/thumbnail` (`geopack_sdk.media_access`). For signed `<img>` URLs use `mint_dataset_thumbnail_url` — not `?auth_token=`. See [security.md §2.5](../old-docs/03_architecture/detailed_design/security.md).

Design: [docs/09-sdk/mcp-design/mcp-architecture.md](../docs/09-sdk/mcp-design/mcp-architecture.md) (in the monorepo). Tool parameters use `tool_schema.py` `Field(description=...)` so MCP clients show per-arg help (not docstrings alone).

**Build a Python LLM agent (LangChain):** Start with [`examples/README.md`](examples/README.md) and [`examples/langchain_geopack_agent.py`](examples/langchain_geopack_agent.py) — discovers `geopack_sdk_*` tools from the MCP server via **langchain-mcp-adapters** (`pip install -e ".[langchain]"`). See [langchain-integration.md](../docs/09-sdk/mcp-design/langchain-integration.md).

**Other LLM demos:** [08_LLM_MCP_Dataset_Discovery.ipynb](notebooks/08_LLM_MCP_Dataset_Discovery.ipynb) (OpenAI + MCP, no LangChain); [llm_geoportal_use_cases.md](../old-docs/04_development/sdk/llm_geoportal_use_cases.md).

### Async example

```python
import asyncio
from geopack_sdk import AsyncGeopackClient

async def main():
    async with AsyncGeopackClient() as client:
        await client.auth.login()
        pending = await client.tasks.summary()
        print(pending)

asyncio.run(main())
```
