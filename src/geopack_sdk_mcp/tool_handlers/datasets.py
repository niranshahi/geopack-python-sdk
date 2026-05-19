"""Dataset tool handlers (testable without the mcp package)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Literal, Optional

from geopack_sdk import GeopackClient
from geopack_sdk.datasets import normalize_feature_query_dsl
from geopack_sdk.dataset_payload import dataset_thumbnail_resource_uri

from ..resource_handlers.datasets import fetch_dataset_thumbnail
from ..sanitize.dataset_details import (
    DetailsLevel,
    normalize_details_level,
    trim_dataset_for_mcp,
    trim_datasets_list_payload,
)
from ..sanitize.query_results import clamp_query_limit, trim_feature_collection_for_mcp
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
    details_level: Optional[str] = "lite",
    data_type: Optional[str] = None,
    bbox: Optional[list] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    level: DetailsLevel = normalize_details_level(details_level, default="lite")
    active_filters: Dict[str, Any] = {}
    if data_type:
        active_filters["dataType"] = data_type
    if bbox and len(bbox) == 4:
        active_filters["bbox"] = bbox
    if start_date:
        active_filters["startDate"] = start_date
    if end_date:
        active_filters["endDate"] = end_date

    result = client.datasets.list(
        page=page,
        page_size=page_size,
        search_query=search_query,
        active_filters=active_filters or None,
    )
    return trim_datasets_list_payload(to_jsonable(result), details_level=level)


def get_dataset(
    client: GeopackClient,
    dataset_id: int,
    *,
    details_level: Optional[str] = "full",
) -> Dict[str, Any]:
    level: DetailsLevel = normalize_details_level(details_level, default="full")
    result = client.datasets.get(dataset_id)
    return trim_dataset_for_mcp(to_jsonable(result), level)


def query_dataset(
    client: GeopackClient,
    dataset_id: int,
    query: Optional[Dict[str, Any]] = None,
    *,
    limit: Optional[int] = None,
    offset: int = 0,
    return_geometry: bool = True,
    out_srid: Optional[int] = None,
) -> Dict[str, Any]:
    """Run POST /datasets/{id}/query with MCP-safe limits."""
    if query is None:
        effective_limit = clamp_query_limit(limit)
        result = client.datasets.query(
            dataset_id,
            None,
            limit=effective_limit,
            offset=offset,
            return_geometry=return_geometry,
            out_srid=out_srid,
        )
    else:
        dsl = normalize_feature_query_dsl(dict(query))
        pagination = dict(dsl.get("pagination") or {})
        req_limit = pagination.get("limit", limit)
        effective_limit = clamp_query_limit(
            int(req_limit) if req_limit is not None else limit
        )
        pagination["limit"] = effective_limit
        pagination.setdefault("offset", offset)
        dsl["pagination"] = pagination
        result = client.datasets.query(dataset_id, dsl)

    payload = trim_feature_collection_for_mcp(to_jsonable(result))
    payload["queryLimitApplied"] = effective_limit
    return payload


def get_dataset_thumbnail(
    client: GeopackClient,
    dataset_id: int,
    save_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch thumbnail PNG to disk on the MCP host (for Cursor Agent chat previews).

    Bytes are not returned in tool JSON — only ``savedPath`` and metadata.
    """
    body, mime_type = fetch_dataset_thumbnail(client, dataset_id)

    if save_path:
        target = Path(save_path)
    else:
        target = Path("downloads") / f"dataset_{dataset_id}_thumbnail.png"

    if target.suffix == "" or target.is_dir():
        target = target / f"dataset_{dataset_id}_thumbnail.png"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)

    resolved = str(target.resolve())
    return {
        "datasetId": dataset_id,
        "savedPath": resolved,
        "mimeType": mime_type,
        "sizeBytes": len(body),
        "thumbnailResourceUri": dataset_thumbnail_resource_uri(dataset_id),
    }


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
