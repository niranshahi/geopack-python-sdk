"""MCP tool registration: datasets."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult

from ..annotations import local_write_tool, mutating_tool, read_tool
from ..auth_bootstrap import AppContext
from ..bbox import normalize_bbox
from ..context import get_client
from ..errors import tool_error_result, tool_result, tool_result_with_image
from ..output_schema import AggregateEnvelope, DatasetSchemaEnvelope
from ..tool_handlers.dataset_upload import upload_dataset
from ..tool_handlers.datasets import (
    aggregate_dataset,
    export_dataset,
    get_dataset,
    get_dataset_relationships,
    get_dataset_schema,
    get_dataset_thumbnail,
    get_related_records,
    list_datasets,
    query_dataset,
)
from ..tool_schema import (
    AggregateLimit,
    AggregateList,
    AggregateOrderBy,
    BboxWgs84,
    DataStoreId,
    DataTypeFilter,
    DatasetFields,
    DatasetId,
    DeclaredType,
    DetailsLevel,
    ExportFormat,
    FeatureFilter,
    FeatureQuery,
    GroupByList,
    IncludeDomainValues,
    IncludeRelationships,
    IsoDate,
    ListOrderBy,
    LocalFilePath,
    OrderDirection,
    OriginObjectIds,
    OutSrid,
    Page,
    PageSize,
    QueryLimit,
    QueryOffset,
    RelatedLimit,
    RelationshipDirection,
    RelationshipName,
    ReturnGeometry,
    SearchQuery,
    SharingPolicy,
    SpatialFilter,
    ThumbnailSavePath,
    UploadMetadata,
    WorkgroupId,
    WorkgroupIdOptional,
)


def register(mcp: Any) -> None:
    @mcp.tool(
        annotations=read_tool("geopack_sdk_list_datasets"),
        description=(
            "List datasets (paginated). details_level lite (card: no details blob) | standard "
            "(adds the field list) | full. Use fields to project top-level keys and keep the "
            "result inside the token budget. order_by defaults to updatedAt desc (newest first), "
            "so '10 latest' is page_size=10. bbox filters on the STORED dataset extent; use "
            "geocode_place for a place search."
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
        fields: DatasetFields = None,
        order_by: ListOrderBy = None,
        order_direction: OrderDirection = None,
    ) -> CallToolResult:
        try:
            # Normalize bbox to handle both array and string formats from LLM
            normalized_bbox = normalize_bbox(bbox)
            return tool_result(
                list_datasets(
                    get_client(ctx),
                    page=page,
                    page_size=page_size,
                    search_query=search_query,
                    details_level=details_level,
                    data_type=data_type,
                    bbox=normalized_bbox,
                    start_date=start_date,
                    end_date=end_date,
                    fields=fields,
                    order_by=order_by,
                    order_direction=order_direction,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_dataset"),
        description=(
            "Get one dataset by id. details_level full (default) | standard | lite. "
            "Use fields to project top-level keys. For field names, types, domains and valid "
            "relationship names use geopack_sdk_get_dataset_schema instead of reading the "
            "details blob."
        ),
    )
    def geopack_sdk_get_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        details_level: DetailsLevel = "full",
        fields: DatasetFields = None,
    ) -> CallToolResult:
        try:
            return tool_result(
                get_dataset(
                    get_client(ctx),
                    dataset_id,
                    details_level=details_level,
                    fields=fields,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_dataset_schema"),
        description=(
            "Return the dataset's FIELD CONTRACT: field names, types, computed flags, optional "
            "coded-value domains, effective field access and the valid relationship names. "
            "Call this before writing a filter or an aggregate; do not guess field names."
        ),
    )
    def geopack_sdk_get_dataset_schema(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        include_domains: IncludeDomainValues = False,
        include_relationships: IncludeRelationships = True,
    ) -> Annotated[CallToolResult, DatasetSchemaEnvelope]:
        try:
            return tool_result(
                get_dataset_schema(
                    get_client(ctx),
                    dataset_id,
                    include_domains=include_domains,
                    include_relationships=include_relationships,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_aggregate_dataset"),
        description=(
            "Answer counts, sums, averages, min/max, distributions and top-N in ONE call over "
            "the same access-scoped rows as query_dataset. aggregates[].aggregate is one of: "
            "count, countDistinct, sum, avg, min, max, stddev, stddevPop, variance, varPop, "
            "median, percentile (percentile needs p in 0..1). This is the answer-first lane: do "
            "not page records to compute a count or a sum."
        ),
    )
    def geopack_sdk_aggregate_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        aggregates: AggregateList = None,
        group_by: GroupByList = None,
        order_by: AggregateOrderBy = None,
        limit: AggregateLimit = 20,
        filter: FeatureFilter = None,
        spatial_filter: SpatialFilter = None,
    ) -> Annotated[CallToolResult, AggregateEnvelope]:
        try:
            return tool_result(
                aggregate_dataset(
                    get_client(ctx),
                    dataset_id,
                    aggregates=aggregates,
                    group_by=group_by,
                    order_by=order_by,
                    limit=limit,
                    filter=filter,
                    spatial_filter=spatial_filter,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_dataset_relationships"),
        description=(
            "List the relationship names valid for this dataset (name, target dataset, "
            "cardinality, read-only). Call it before geopack_sdk_get_related_records; never "
            "invent a relationship name."
        ),
    )
    def geopack_sdk_get_dataset_relationships(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
    ) -> CallToolResult:
        try:
            return tool_result(get_dataset_relationships(get_client(ctx), dataset_id))
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_get_related_records"),
        description=(
            "Records related to the given source OIDs through ONE relationship hop. Get "
            "relationship_name from geopack_sdk_get_dataset_relationships and the OID values "
            "from a records query. return_geometry defaults to false; __jct__* properties are "
            "junction fields. Use query_dataset when the records are NOT related."
        ),
    )
    def geopack_sdk_get_related_records(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        relationship_name: RelationshipName,
        origin_object_ids: OriginObjectIds,
        direction: RelationshipDirection = "forward",
        limit: RelatedLimit = 50,
        offset: QueryOffset = 0,
        return_geometry: ReturnGeometry = False,
    ) -> CallToolResult:
        try:
            return tool_result(
                get_related_records(
                    get_client(ctx),
                    dataset_id,
                    relationship_name,
                    origin_object_ids,
                    direction=direction,
                    limit=limit,
                    offset=offset,
                    return_geometry=return_geometry,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_query_dataset"),
        description=(
            "Query vector dataset features (max 500 in JSON). "
            "Pass FeatureQuery in query or use limit/offset. "
            "Returns RECORDS: for any count, sum, average, min/max, distribution or top-N use "
            "geopack_sdk_aggregate_dataset — it is cheaper and exact."
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
    ) -> CallToolResult:
        try:
            return tool_result(
                query_dataset(
                    get_client(ctx),
                    dataset_id,
                    query,
                    limit=limit,
                    offset=offset,
                    return_geometry=return_geometry,
                    out_srid=out_srid,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=local_write_tool("geopack_sdk_get_dataset_thumbnail"),
description=(
            "Return the dataset preview image. INLINE is the official delivery mode: the image "
            "is returned in the tool result and the host renders it. No file is written unless "
            "save_path is given, and a sandboxed host that forbids writes answers saved=false "
            "while the image is still returned inline — no file appearing on disk is expected, "
            "not an error. No portal state changes."
        ),
    )
    def geopack_sdk_get_dataset_thumbnail(
        ctx: Context[ServerSession, AppContext],
        dataset_id: DatasetId,
        save_path: ThumbnailSavePath = None,
    ) -> CallToolResult:
        try:
            result = get_dataset_thumbnail(
                get_client(ctx),
                dataset_id,
                save_path=save_path,
            )
            return tool_result_with_image(
                result.payload, result.body, result.mime_type
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=mutating_tool("geopack_sdk_upload_dataset"),
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
    ) -> CallToolResult:
        try:
            return tool_result(
                upload_dataset(
                    get_client(ctx),
                    file_path=file_path,
                    data_store_id=data_store_id,
                    workgroup_id=workgroup_id,
                    declared_type=declared_type,
                    metadata=metadata,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)

    @mcp.tool(
        annotations=read_tool("geopack_sdk_export_dataset"),
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
    ) -> CallToolResult:
        try:
            return tool_result(
                export_dataset(
                    get_client(ctx),
                    dataset_id,
                    format,
                    workgroup_id=workgroup_id,
                    sharing_policy=sharing_policy,
                )
            )
        except Exception as exc:
            return tool_error_result(exc)
