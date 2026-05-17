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
- Sync and **async** clients (`GeopackClient`, `AsyncGeopackClient`); parallel task polling via `wait_for_tasks`.
- Task message helpers aligned with the portal UI.
- HTTP retries on 502/503/504; typed exceptions.
- GeoPandas integration; **Geopack SDK MCP** server (v0 read-only tools).

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
| `python test_mcp_stdio_client.py` | **Full E2E:** spawns server, `call_tool` over stdio (like Cursor) |
| `python -m geopack_sdk_mcp` | Server only; waits for MCP host (Ctrl+C to stop) |

Always use `python script.py`, not `.\script.py` on Windows (wrong interpreter).

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

Or use `GEOPACK_ACCESS_TOKEN` (+ optional `GEOPACK_REFRESH_TOKEN`) instead of username/password.

**v0 tools:** `geopack_sdk_list_datasets`, `geopack_sdk_get_dataset`, `geopack_sdk_get_task`, `geopack_sdk_list_workflows`, `geopack_sdk_get_workflow_run`.

**Dataset thumbnails:** Tool results include `hasThumbnail` and `thumbnailApiPath` only (no image bytes). **Cursor does not auto-build image URLs from these fields** — use a notebook (see [pydantic_models_guide.md § Dataset thumbnails](../docs/04_development/sdk/pydantic_models_guide.md)), the Geoportal UI, or future MCP Resources (v1.5). Details: [geopack_sdk_mcp_design.md §11](../docs/04_development/sdk/geopack_sdk_mcp_design.md).

Design: [docs/04_development/sdk/geopack_sdk_mcp_design.md](../docs/04_development/sdk/geopack_sdk_mcp_design.md) (in the monorepo).

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
