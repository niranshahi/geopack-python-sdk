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

1. `01_Getting_Started.ipynb`: Basic connection and data exploration.
2. `02_Data_Analysis_GeoPandas.ipynb`: Spatial analysis with GeoPandas.
3. `03_Raster_Workflows.ipynb`: Server-side processing with GDAL/OGR Workflows.
4. `04_Data_Management_and_Tasks.ipynb`: Uploading, exporting, and monitoring tasks.

**Note for Developers:** If you are running these notebooks directly from the cloned repository, they are pre-configured to use the local `src/` directory without requiring a global installation.

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
- Full API coverage for Datasets, DataStores, and Workflows.
- Async Task management with polling support.
- Native integration with GeoPandas and Rasterio.
- AI-ready with upcoming MCP support.
