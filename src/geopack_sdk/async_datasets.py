"""Async dataset manager (JSON REST; multipart upload remains sync-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from .datasets import (
    _build_aggregate_payload,
    _build_paged_dsl,
    _positive_int,
    build_simple_query,
    encode_query_params,
    normalize_feature_query_dsl,
)
from .models import (
    AggregateResult,
    ColumnBounds,
    Dataset,
    DatasetsApiResponse,
    FeatureCollection,
    MintedUrl,
    PagedFeatureCollection,
    RelatedRecordsResult,
    RelationshipDescriptor,
    SchemaPreview,
)

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncDatasetManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        search_query: Optional[str] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None,
        active_filters: Optional[Dict[str, Any]] = None,
    ) -> DatasetsApiResponse:
        params: Dict[str, Any] = {
            "page": page,
            "pageSize": page_size,
        }
        if search_query is not None:
            params["searchQuery"] = search_query.strip()
        if order_by:
            params["orderBy"] = order_by
        if order_direction:
            params["orderDirection"] = (
                "desc" if str(order_direction).lower() == "desc" else "asc"
            )
        if active_filters:
            array_filters = [
                "organizationIds",
                "ownerIds",
                "workgroupIds",
                "dataStoreIds",
                "subType",
                "dataType",
                "keywords",
            ]
            for key, value in active_filters.items():
                if key in array_filters and not isinstance(value, list):
                    params[key] = [value]
                else:
                    params[key] = value

        response_data = await self.client.get(
            "/datasets", params=encode_query_params(params)
        )
        return DatasetsApiResponse(**response_data)

    async def iter_datasets(
        self,
        page_size: int = 50,
        search_query: Optional[str] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None,
        active_filters: Optional[Dict[str, Any]] = None,
    ):
        """Iterate over all datasets matching filters by auto-fetching successive pages asynchronously."""
        current_page = 1
        while True:
            resp = await self.list(
                page=current_page,
                page_size=page_size,
                search_query=search_query,
                order_by=order_by,
                order_direction=order_direction,
                active_filters=active_filters,
            )
            if not resp.datasets:
                break
            for dataset in resp.datasets:
                yield dataset
            if len(resp.datasets) < page_size:
                break
            current_page += 1

    async def get(self, dataset_id: int) -> Dataset:

        response_data = await self.client.get(f"/datasets/{dataset_id}")
        return Dataset(**response_data)

    async def query(
        self,
        dataset_id: int,
        query: Optional[Dict[str, Any]] = None,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
        return_geometry: bool = True,
        out_srid: Optional[int] = None,
    ) -> FeatureCollection:
        if query is None:
            query = build_simple_query(
                limit=limit or 100,
                offset=offset,
                return_geometry=return_geometry,
                out_srid=out_srid,
            )
        else:
            query = normalize_feature_query_dsl(dict(query))

        response_data = await self.client.post(
            f"/datasets/{dataset_id}/query",
            json=query,
        )
        return FeatureCollection(**response_data)

    async def delete(self, dataset_id: int) -> None:
        await self.client.delete(f"/datasets/{dataset_id}")

    # --- Query lanes (slice 010) --------------------------------------------

    async def query_paged(
        self,
        dataset_id: int,
        query: Optional[Dict[str, Any]] = None,
        *,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        order_by: Optional[List[Dict[str, Any]]] = None,
        include_total_count: bool = True,
    ) -> PagedFeatureCollection:
        """Async twin of :meth:`geopack_sdk.datasets.DatasetManager.query_paged`."""
        dsl = _build_paged_dsl(
            query,
            page=page,
            page_size=page_size,
            order_by=order_by,
            include_total_count=include_total_count,
        )
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/query/paged",
            json=dsl,
        )
        return PagedFeatureCollection(**(response_data or {}))

    async def iterate_pages(
        self,
        dataset_id: int,
        query: Optional[Dict[str, Any]] = None,
        *,
        page_size: int = 1000,
        include_total_count: bool = True,
    ):
        """Async twin of :meth:`DatasetManager.iterate_pages`."""
        page = 1
        while True:
            result = await self.query_paged(
                dataset_id,
                query,
                page=page,
                page_size=page_size,
                include_total_count=include_total_count,
            )
            yield result
            if not result.features or not result.pagination.has_next_page:
                break
            page += 1

    async def aggregate(
        self,
        dataset_id: int,
        *,
        aggregation: Dict[str, Any],
        filter: Optional[Dict[str, Any]] = None,
        spatial_filter: Optional[Dict[str, Any]] = None,
    ) -> AggregateResult:
        """Async twin of :meth:`DatasetManager.aggregate`."""
        payload = _build_aggregate_payload(aggregation, filter, spatial_filter)
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/query/aggregate",
            json=payload,
        )
        return AggregateResult(**(response_data or {}))

    async def count(
        self,
        dataset_id: int,
        *,
        filter: Optional[Dict[str, Any]] = None,
        spatial_filter: Optional[Dict[str, Any]] = None,
        field: Optional[str] = None,
        distinct: bool = False,
    ) -> int:
        """Async twin of :meth:`DatasetManager.count`."""
        entry: Dict[str, Any] = {
            "aggregate": "countDistinct" if distinct else "count",
            "alias": "value",
        }
        if field:
            entry["field"] = field

        result = await self.aggregate(
            dataset_id,
            aggregation={"aggregates": [entry], "limit": 1},
            filter=filter,
            spatial_filter=spatial_filter,
        )

        if not result.rows:
            return 0
        row = result.rows[0]
        value = row.get("value")
        if value is None and len(row) == 1:
            value = next(iter(row.values()))
        return int(value or 0)

    async def mint_query_access_url(
        self, dataset_id: int, query_dsl: Dict[str, Any]
    ) -> MintedUrl:
        """Async twin of :meth:`DatasetManager.mint_query_access_url`."""
        if not isinstance(query_dsl, dict):
            raise ValueError("query_dsl must be a dict — the DSL the URL is bound to")
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/query/mint-access-url",
            json={"queryDsl": query_dsl},
        )
        return MintedUrl(**(response_data or {}))

    async def mint_mvt_access_url(
        self,
        dataset_id: int,
        query_dsl: Optional[Dict[str, Any]] = None,
    ) -> MintedUrl:
        """Async twin of :meth:`DatasetManager.mint_mvt_access_url`."""
        payload: Dict[str, Any] = {}
        if query_dsl is not None:
            if not isinstance(query_dsl, dict):
                raise ValueError("query_dsl must be a dict when provided")
            payload["queryDsl"] = query_dsl
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/mvt/mint-access-url",
            json=payload,
        )
        return MintedUrl(**(response_data or {}))

    async def get_tiles_access_url(self, dataset_id: int) -> MintedUrl:
        """Async twin of :meth:`DatasetManager.get_tiles_access_url`."""
        response_data = await self.client.get(f"/datasets/{dataset_id}/tiles/access-url")
        return MintedUrl(**(response_data or {}))

    # --- Relationships, schema and access context (slice 011) ---------------

    async def get_relationships(self, dataset_id: int) -> List[RelationshipDescriptor]:
        """Async twin of :meth:`DatasetManager.get_relationships`."""
        response_data = await self.client.get(f"/datasets/{dataset_id}/relationships")
        entries = (response_data or {}).get("relationships") or []
        return [RelationshipDescriptor(**entry) for entry in entries]

    async def get_related_records(
        self,
        dataset_id: int,
        relationship_name: str,
        origin_object_ids: Sequence[int],
        *,
        direction: str = "forward",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        return_geometry: bool = True,
        out_srid: Optional[int] = None,
    ) -> RelatedRecordsResult:
        """Async twin of :meth:`DatasetManager.get_related_records`."""
        if not relationship_name:
            raise ValueError("relationship_name is required")
        if direction not in ("forward", "backward"):
            raise ValueError('direction must be "forward" or "backward"')

        oids = [int(oid) for oid in (origin_object_ids or [])]
        if not oids:
            raise ValueError("origin_object_ids must contain at least one source OID")

        query_options: Dict[str, Any] = {"returnGeometry": bool(return_geometry)}
        if limit is not None:
            query_options["limit"] = _positive_int(limit, "limit")
        if offset is not None:
            query_options["offset"] = int(offset)
        if out_srid is not None:
            query_options["outSRID"] = int(out_srid)

        response_data = await self.client.post(
            f"/datasets/{dataset_id}/related-records",
            json={
                "relationshipName": relationship_name,
                "direction": direction,
                "originObjectIds": oids,
                "queryOptions": query_options,
            },
        )
        return RelatedRecordsResult(**(response_data or {}))

    async def preview_schema(
        self, dataset_id: int, query_dsl: Dict[str, Any]
    ) -> SchemaPreview:
        """Async twin of :meth:`DatasetManager.preview_schema`."""
        if not isinstance(query_dsl, dict) or not query_dsl:
            raise ValueError("query_dsl must be a non-empty dict with a relationship node")
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/schema-preview",
            json={"queryDsl": query_dsl},
        )
        return SchemaPreview(**(response_data or {}))

    async def get_column_bounds(self, dataset_id: int) -> ColumnBounds:
        """Async twin of :meth:`DatasetManager.get_column_bounds`."""
        response_data = await self.client.get(f"/datasets/{dataset_id}/column-bounds")
        return ColumnBounds(**(response_data or {}))

    async def get_access_context(self, dataset_id: int) -> Dict[str, Any]:
        """Async twin of :meth:`DatasetManager.get_access_context`."""
        response_data = await self.client.get(f"/datasets/{dataset_id}/access-context")
        return response_data or {}
