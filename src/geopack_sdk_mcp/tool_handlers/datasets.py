"""Dataset tool handlers (testable without the mcp package)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from geopack_sdk import GeopackClient

from ..serialize import to_jsonable


def list_datasets(
    client: GeopackClient,
    *,
    page: int = 1,
    page_size: int = 20,
    search_query: Optional[str] = None,
) -> Dict[str, Any]:
    result = client.datasets.list(
        page=page,
        page_size=page_size,
        search_query=search_query,
    )
    return to_jsonable(result)


def get_dataset(client: GeopackClient, dataset_id: int) -> Dict[str, Any]:
    result = client.datasets.get(dataset_id)
    return to_jsonable(result)
