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
from geopack_sdk import GeopackClient
```

## Installation

```bash
pip install geopack-sdk
```
or
```bash
pip install git+https://github.com/niranshahi/geopack-python-sdk.git
```

## Examples & Notebooks

We provide a collection of Jupyter Notebooks in the `notebooks/` directory to help you get started:

1. `01_Getting_Started.ipynb` — connection and data exploration.
2. `02_Data_Analysis_GeoPandas.ipynb` — GeoPandas analysis.
3. `03_Raster_Workflows.ipynb` — workflows, task + run inspection.
4. `04_Data_Management_and_Tasks.ipynb` — upload, export, task log severity.
5. `05_Advanced_API_Coverage.ipynb` — quotas, generated files, dataset query / ACL.

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
- Async tasks with polling; task message helpers aligned with the portal UI.
- HTTP retries on 502/503/504; typed exceptions.
- GeoPandas integration; MCP server planned.
