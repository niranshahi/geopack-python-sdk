"""MCP tool registration: datasets."""

from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..bbox import normalize_bbox
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.dataset_upload import upload_dataset
from ..tool_handlers.datasets import (
    export_dataset,
    get_dataset,
    get_dataset_thumbnail,
    list_datasets,
    query_dataset,
)
from ..tool_schema import (
    BboxWgs84,
    DataStoreId,
    DataTypeFilter,
    DatasetId,
    DeclaredType,
    DetailsLevel,
    ExportFormat,
    FeatureQuery,
    IsoDate,
    LocalFilePath,
    OutSrid,
    Page,
    PageSize,
    QueryLimit,
    QueryOffset,
    ReturnGeometry,
    SavePath,
    SearchQuery,
    SharingPolicy,
    UploadMetadata,
    WorkgroupId,
    WorkgroupIdOptional,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "List datasets (paginated). Use geocode_place then pass bbox for location searches. "
            "details_level lite | standard | full."
        ),
    )
    def geopack_sdk_list_datasets(
        ctx: Context[ServerSession, AppContext],
        page: Page = 1,
        page_size: PageSize = 20,
        search_query: SearchQuery = None,
        details_level: DetailsLevel = "lite",
        data_type: DataTypeFilter = None,
        bbox: BboxWgs84 = None,
        start_date: IsoDate = None,
        end_date: IsoDate = None,
    ) -> Dict[str, Any]:
        try:
            # Normalize bbox to handle both array and string formats from LLM
            normalized_bbox = normalize_bbox(bbox)
            return list_datasets(
                get_client(ctx),
                page=page,
                page_size=page_size,
                search_query=search_query,
                details_level=details_level,
                data_type=data_type,
                bbox=normalized_bbox,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description="Get one dataset by id. details_level full (default) | standard | lite.",
    )
    def geopack_sdk_get_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        details_level: DetailsLevel = "full",
    ) -> Dict[str, Any]:
        try:
            return get_dataset(
                get_client(ctx),
                dataset_id,
                details_level=details_level,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description=(
            "Query vector dataset features (max 500 in JSON). "
            "Pass FeatureQuery in query or use limit/offset."
        ),
    )
    def geopack_sdk_query_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        query: FeatureQuery = None,
        limit: QueryLimit = 100,
        offset: QueryOffset = 0,
        return_geometry: ReturnGeometry = True,
        out_srid: OutSrid = None,
    ) -> Dict[str, Any]:
        try:
            return query_dataset(
                get_client(ctx),
                dataset_id,
                query,
                limit=limit,
                offset=offset,
                return_geometry=return_geometry,
                out_srid=out_srid,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description=(
            "Save dataset preview PNG on the MCP host. "
            "Default: downloads/dataset_{id}_thumbnail.png under process cwd."
        ),
    )
    def geopack_sdk_get_dataset_thumbnail(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        save_path: SavePath = None,
    ) -> Dict[str, Any]:
        try:
            return get_dataset_thumbnail(
                get_client(ctx),
                dataset_id,
                save_path=save_path,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description=(
            "Upload a local geospatial file; returns taskId (non-blocking). "
            "Chain: geopack_sdk_wait_for_task → createdDatasetId in results. "
            "Set metadata.name for display title. Inline GeoJSON: write a .geojson file first. "
            "MUTATING: MCP does not delete datasets (use portal). Before this call the host must "
            "describe the upload and obtain explicit user consent in conversation; do not call if declined."
        ),
    )
    def geopack_sdk_upload_dataset(
        ctx: Context[ServerSession, AppContext],
        file_path: LocalFilePath,
        data_store_id: DataStoreId,
        workgroup_id: WorkgroupId,
        declared_type: DeclaredType = None,
        metadata: UploadMetadata = None,
    ) -> Dict[str, Any]:
        try:
            return upload_dataset(
                get_client(ctx),
                file_path=file_path,
                data_store_id=data_store_id,
                workgroup_id=workgroup_id,
                declared_type=declared_type,
                metadata=metadata,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool(
        description=(
            "Start async dataset export; returns taskId. "
            "Chain: wait_for_task → download_generated_file."
        ),
    )
    def geopack_sdk_export_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        format: ExportFormat,
        workgroup_id: WorkgroupIdOptional = None,
        sharing_policy: SharingPolicy = "private",
    ) -> Dict[str, Any]:
        try:
            return export_dataset(
                get_client(ctx),
                dataset_id,
                format,
                workgroup_id=workgroup_id,
                sharing_policy=sharing_policy,
            )
        except Exception as exc:
            return tool_error_payload(exc)
