"""Dataset tool handlers (testable without the mcp package)."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from geopack_sdk import GeopackClient

from ..sanitize.dataset_details import trim_dataset_for_mcp, trim_datasets_list_payload
from ..sanitize.task_results import sanitize_task_payload
from ..serialize import to_jsonable

ExportFormat = Literal[
    "geojson",
    "shapefile",
    "gpkg",
    "geotiff",
    "mbtiles",
    "csv",
    "filegdb",
    "tif",
    "tiff",
]


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
    return trim_datasets_list_payload(to_jsonable(result))


def get_dataset(client: GeopackClient, dataset_id: int) -> Dict[str, Any]:
    result = client.datasets.get(dataset_id)
    return trim_dataset_for_mcp(to_jsonable(result), "get")


def export_dataset(
    client: GeopackClient,
    dataset_id: int,
    format: str,
    *,
    workgroup_id: Optional[int] = None,
    sharing_policy: str = "private",
) -> Dict[str, Any]:
    """
    Start a dataset:export background task (does not wait for completion).
    """
    if workgroup_id is None:
        dataset = client.datasets.get(dataset_id)
        workgroup_id = dataset.workgroupId

    task = client.datasets.export(
        dataset_id,
        workgroup_id,
        format,
        sharing_policy=sharing_policy,
        wait=False,
    )
    return sanitize_task_payload(to_jsonable(task))
