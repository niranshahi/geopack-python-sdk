# Geopack Python SDK

A standalone Python library to interact with the Geopack Geoportal API.

## Installation

```bash
pip install geopack-sdk
```

## Quick Start

```python
from geopack_sdk import GeopackClient

# Initialize client
client = GeopackClient(base_url="https://your-geoportal.com/api")

# Login
client.auth.login(username="admin", password="password")

# List datasets
datasets = client.datasets.list()
for ds in datasets:
    print(ds.name)
```

## Features
- Full API coverage for Datasets, DataStores, and Workflows.
- Async Task management with polling support.
- Native integration with GeoPandas and Rasterio.
- AI-ready with upcoming MCP support.
