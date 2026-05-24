# Geopack Python SDK

A standalone Python library to interact with the Geopack Geoportal API.

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
- Datasets, DataStores, Workflows, Tasks, **Generated Files**, **Quotas (self)**.
- Dataset **delete**, **ACL**, structured **query** (`build_simple_query`), **discover**.
- Sync and **async** clients (`GeopackClient`, `AsyncGeopackClient`); parallel task polling via `wait_for_tasks` (`partial_success` is terminal and returned like `completed`).
- Task message helpers aligned with the portal UI.
- HTTP retries on 502/503/504; typed exceptions.
- GeoPandas integration; **Geopack SDK MCP** server (**16 tools** + 2 resource templates, v0.5.4+; workflow execution, upload; no dataset delete via MCP).

## Geopack SDK MCP (Cursor / Claude Desktop)

Typed REST proxy via MCP — not the in-portal assistant. Credentials stay in the MCP server **environment**, never in tool arguments.

**Use the project venv** (recommended — same as notebooks):

```powershell
cd python-sdk
.\venv\Scripts\activate
pip install -e ".[mcp]"
```

`mcp` is an **optional** dependency in `pyproject.toml` (`[project.optional-dependencies] mcp`) so `pip install geopack-sdk` alone does not pull it in. Install `geopack-sdk[mcp]` or `geopack-sdk[all]` when you need the MCP server.

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

Alternatives: `GEOPACK_ACCESS_TOKEN` in env, or username/password in `env` (dev only). See [MCP authentication options](../docs/04_development/sdk/mcp_auth_options.md).

**Safety:** Dataset/generated-file **delete is not an MCP tool** (use Geoportal UI). Call `geopack_sdk_get_mcp_safety_policy` for server rules. Upload/workflow: host must get explicit user consent in chat before calling. See [MCP Safety Policy](../docs/04_development/sdk/mcp_safety_policy.md).

**Tools (16, v0.5.4+):**

| Tool | Purpose |
|------|---------|
| `geopack_sdk_get_mcp_safety_policy` | Server rules: what MCP cannot do (e.g. no dataset delete) |
| `geopack_sdk_geocode_place` | Place name → WGS84 bbox (Nominatim; use before spatial list) |
| `geopack_sdk_list_datasets` | Paginated list; `bbox`, `data_type`, dates; `details_level` default `lite` |
| `geopack_sdk_get_dataset` | One dataset; `details_level` default `full` |
| `geopack_sdk_query_dataset` | Feature query (max 500 features in JSON) |
| `geopack_sdk_get_dataset_thumbnail` | Save preview PNG on MCP host (`save_path` optional) |
| `geopack_sdk_get_task` | Task status (sanitized) |
| `geopack_sdk_wait_for_task` | Poll until export/job completes |
| `geopack_sdk_upload_dataset` | Upload local file on MCP host → `dataset:upload`; use `metadata.name` for title |
| `geopack_sdk_export_dataset` | Start `dataset:export` (returns `taskId`) |
| `geopack_sdk_download_generated_file` | Save export to local `save_path` on MCP host |
| `geopack_sdk_list_workflows` | List workflows (no `graphJson` in JSON) |
| `geopack_sdk_get_workflow` | Workflow metadata; `include_params=true` adds `parameters[]` |
| `geopack_sdk_submit_workflow` | Start run; returns `workflowRunId` + `taskId` |
| `geopack_sdk_get_workflow_run` | Run status + artifacts |
| `geopack_sdk_download_workflow_artifact` | Save workflow output on MCP host |

**Resource templates (not listed as tools in Cursor UI):**

| URI template | Purpose |
|--------------|---------|
| `dataset://{dataset_id}/thumbnail` | PNG preview (`resources/read`) |
| `generated-file://{file_id}/download` | Export file bytes (prefer download tool for large files) |

**Export flow:** `export_dataset` → `wait_for_task` → `download_generated_file` (see MCP design doc §12).

**Workflow flow:** `get_workflow(include_params=true)` → `submit_workflow` → `wait_for_task` → `get_workflow_run` → optional `download_workflow_artifact` (MCP design doc §14; notebook `11_LangChain_MCP_Workflow_Execution.ipynb`).

**Upload flow:** place file on MCP host → `upload_dataset(file_path, data_store_id, workgroup_id, declared_type?, metadata?)` → `wait_for_task` → read `createdDatasetId` from task `results` → optional workflow submit. For a custom title pass `metadata={"name": "My dataset"}`. Inline GeoJSON is not a tool arg — write to disk first. Restart MCP after upgrading so `metadata` appears in the tool schema.

**Dataset thumbnails:** Tool JSON has `hasThumbnail`, `thumbnailApiPath`, `thumbnailMintPath`, `thumbnailResourceUri` (no BLOB, **no JWT in JSON**). MCP fetches bytes via Bearer on `GET /datasets/{id}/thumbnail` (`geopack_sdk.media_access`). For signed `<img>` URLs use `mint_dataset_thumbnail_url` — not `?auth_token=`. See [security.md §2.5](../docs/03_architecture/detailed_design/security.md).

Design: [docs/04_development/sdk/geopack_sdk_mcp_design.md](../docs/04_development/sdk/geopack_sdk_mcp_design.md) (in the monorepo). Tool parameters use `tool_schema.py` `Field(description=...)` so MCP clients show per-arg help (not docstrings alone).

**Build a Python LLM agent (LangChain):** Start with [`examples/README.md`](examples/README.md) and [`examples/langchain_geopack_agent.py`](examples/langchain_geopack_agent.py) — discovers `geopack_sdk_*` tools from the MCP server via **langchain-mcp-adapters** (`pip install -e ".[langchain]"`). See [langchain_mcp_agents_design.md](../docs/04_development/sdk/langchain_mcp_agents_design.md).

**Other LLM demos:** [08_LLM_MCP_Dataset_Discovery.ipynb](notebooks/08_LLM_MCP_Dataset_Discovery.ipynb) (OpenAI + MCP, no LangChain); [llm_geoportal_use_cases.md](../docs/04_development/sdk/llm_geoportal_use_cases.md).

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
