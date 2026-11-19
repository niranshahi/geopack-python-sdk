"""Async dataset manager (JSON REST; multipart upload remains sync-only)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

from .datasets import (
    _build_aggregate_payload,
    _build_paged_dsl,
    _positive_int,
    build_geodataframe,
    build_simple_query,
    encode_query_params,
    normalize_feature_query_dsl,
)
from .models import (
    AggregateResult,
    ColumnBounds,
    CreateDatasetDto,
    CreateVirtualDatasetDto,
    CreateVirtualSqlDatasetDto,
    Dataset,
    DatasetAcl,
    DatasetDiscoverResponse,
    DatasetStatsByGeomType,
    DatasetStatsByStore,
    DatasetTimeSeriesPoint,
    DatasetsApiResponse,
    FeatureCollection,
    FieldRestriction,
    FilterStatistics,
    MintedUrl,
    PagedFeatureCollection,
    RelatedRecordsResult,
    RelationshipDescriptor,
    SchemaPreview,
    TaskResult,
    UpdateDatasetDto,
)

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


def _read_file_bytes(path: str) -> bytes:
    """Blocking read used only through ``asyncio.to_thread``."""
    with open(path, "rb") as handle:
        return handle.read()


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

    # --- CRUD, stats, features and file lanes (slice 016 P4a) ----------------

    async def get_features(
        self,
        dataset_id: int,
        limit: int = 100,
        offset: int = 0,
        bbox: Optional[List[float]] = None,
        out_srid: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> FeatureCollection:
        """Async twin of :meth:`DatasetManager.get_features`."""
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if bbox and len(bbox) == 4:
            params["bbox"] = ",".join(map(str, bbox))
        if out_srid:
            params["outSRID"] = out_srid
        if filters:
            params["filter"] = json.dumps(filters)

        response_data = await self.client.get(
            f"/datasets/{dataset_id}/features", params=params
        )
        return FeatureCollection(**response_data)

    async def to_geodataframe(self, dataset_id: int, limit: int = 1000) -> Any:
        """Async twin of :meth:`DatasetManager.to_geodataframe`.

        Network calls are awaited; the GeoDataFrame is built in a worker thread
        through ``asyncio.to_thread`` because geopandas is blocking (slice 016 §3).
        """
        metadata = await self.get(dataset_id)
        if metadata.dataType != 'vector':
            raise ValueError(
                f"Dataset {dataset_id} is not a vector dataset "
                f"(type: {metadata.dataType}). GeoDataFrame only supports vector data."
            )
        feature_collection = await self.get_features(dataset_id, limit=limit)
        return await asyncio.to_thread(
            build_geodataframe, metadata, feature_collection
        )

    async def get_statistics(self) -> FilterStatistics:
        """Async twin of :meth:`DatasetManager.get_statistics`."""
        response_data = await self.client.get("/datasets/statistics")
        return FilterStatistics(**response_data)

    async def get_time_series_stats(
        self, days: Optional[int] = None, data_type: Optional[str] = None
    ) -> List[DatasetTimeSeriesPoint]:
        """Async twin of :meth:`DatasetManager.get_time_series_stats`."""
        params: Dict[str, Any] = {}
        if days is not None:
            params["days"] = days
        if data_type is not None:
            params["dataType"] = data_type
        response_data = await self.client.get(
            "/datasets/stats/time-series", params=encode_query_params(params)
        )
        if isinstance(response_data, list):
            return [DatasetTimeSeriesPoint(**item) for item in response_data]
        return []

    async def get_stats_by_store(self) -> List[DatasetStatsByStore]:
        """Async twin of :meth:`DatasetManager.get_stats_by_store`."""
        response_data = await self.client.get("/datasets/stats/by-store")
        if isinstance(response_data, list):
            return [DatasetStatsByStore(**item) for item in response_data]
        return []

    async def get_stats_by_geom_type(self) -> List[DatasetStatsByGeomType]:
        """Async twin of :meth:`DatasetManager.get_stats_by_geom_type`."""
        response_data = await self.client.get("/datasets/stats/by-geom-type")
        if isinstance(response_data, list):
            return [DatasetStatsByGeomType(**item) for item in response_data]
        return []

    async def create(
        self, dataset_data: Union[CreateDatasetDto, Dict[str, Any]]
    ) -> Dataset:
        """Async twin of :meth:`DatasetManager.create`."""
        payload = (
            dataset_data.model_dump()
            if isinstance(dataset_data, CreateDatasetDto)
            else dataset_data
        )
        response_data = await self.client.post("/datasets", json=payload)
        return Dataset(**response_data)

    async def update(
        self, dataset_id: int, dataset_data: Union[UpdateDatasetDto, Dict[str, Any]]
    ) -> Dataset:
        """Async twin of :meth:`DatasetManager.update`."""
        payload = (
            dataset_data.model_dump(exclude_unset=True)
            if isinstance(dataset_data, UpdateDatasetDto)
            else dataset_data
        )
        response_data = await self.client.put(
            f"/datasets/{dataset_id}", json=payload
        )
        return Dataset(**response_data)

    async def export(
        self,
        dataset_id: int,
        workgroup_id: int,
        format: str,
        sharing_policy: str = "private",
        wait: bool = True,
        polling_interval: int = 2,
    ) -> TaskResult:
        """Async twin of :meth:`DatasetManager.export`."""
        payload = {
            "taskType": "dataset:export",
            "workgroupId": workgroup_id,
            "inputParameters": {
                "datasetId": dataset_id,
                "format": format,
                "options": {"sharingPolicy": sharing_policy},
            },
        }
        task_response = await self.client.tasks.create(payload)
        if not wait:
            return task_response
        return await self.client.tasks.wait(
            task_response.task_id, interval=polling_interval
        )

    async def upload(
        self,
        file_path: str,
        data_store_id: int,
        workgroup_id: int,
        declared_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        wait: bool = True,
        polling_interval: int = 2,
    ) -> TaskResult:
        """Async twin of :meth:`DatasetManager.upload`.

        The file bytes are read in a worker thread and posted as multipart; the
        task then follows the same ``dataset:upload`` flow as the sync client.
        """
        if not await asyncio.to_thread(os.path.exists, file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = os.path.basename(file_path)
        content = await asyncio.to_thread(_read_file_bytes, file_path)
        upload_response = await self.client._request(
            "POST", "/uploads/temp", files={"files": (filename, content)}
        )

        session_id = upload_response["uploadSessionId"]
        uploaded_file = upload_response["files"][0]
        relative_path = uploaded_file["relativePath"]

        input_params: Dict[str, Any] = {
            "sourceFiles": [
                {
                    "type": "tempUpload",
                    "sessionId": session_id,
                    "relativePath": relative_path,
                    "originalName": filename,
                }
            ],
            "dataStoreId": data_store_id,
        }
        if declared_type:
            input_params["declaredType"] = declared_type
        if metadata is not None:
            input_params["metadata"] = metadata

        task_response = await self.client.tasks.create(
            {
                "taskType": "dataset:upload",
                "workgroupId": workgroup_id,
                "inputParameters": input_params,
            }
        )
        if not wait:
            return task_response
        return await self.client.tasks.wait(
            task_response.taskId, interval=polling_interval, quiet=True
        )

    async def download(
        self,
        task_results: Union[TaskResult, Dict[str, Any]],
        local_path: str,
        chunk_size: int = 8192,
    ) -> str:
        """Async twin of :meth:`DatasetManager.download`.

        Resolves the same ``downloadToken`` / ``artifactPath`` pair from the task
        results, then streams the body with ``httpx`` and writes it through
        ``asyncio.to_thread``.
        """
        results = (
            task_results.results
            if isinstance(task_results, TaskResult)
            else task_results.get("results")
        )
        if not results:
            raise ValueError("Task is completed but contains no results/output.")

        download_token = results.get("downloadToken")
        artifact_path = results.get("artifactPath")
        filename = results.get("originalName") or results.get("fileName") or "exported_data"

        if download_token:
            endpoint = f"downloads/{download_token}"
        elif artifact_path:
            endpoint = f"download/{artifact_path.lstrip('/')}"
        else:
            raise ValueError("No download token or artifact path found in task results.")

        return await self.client._stream_to_file(
            endpoint, local_path, fallback_filename=filename, chunk_size=chunk_size
        )

    async def discover(
        self,
        source_files: List[Dict[str, Any]],
        data_store_id: int,
        workgroup_id: int,
        declared_type: Optional[str] = None,
        wait: bool = True,
        polling_interval: int = 2,
    ) -> Union[DatasetDiscoverResponse, TaskResult]:
        """Async twin of :meth:`DatasetManager.discover`."""
        payload: Dict[str, Any] = {
            "sourceFiles": source_files,
            "dataStoreId": data_store_id,
            "workgroupId": workgroup_id,
        }
        if declared_type:
            payload["declaredType"] = declared_type

        response_data = await self.client.post("/datasets/discover", json=payload)
        result = DatasetDiscoverResponse(**response_data)
        if not wait or not result.is_background_task:
            return result

        task_id = result.taskId
        if not task_id:
            return result

        return await self.client.tasks.wait_for_task(
            task_id, interval=polling_interval, quiet=True
        )

    async def get_acls(self, dataset_id: int) -> List[DatasetAcl]:
        """Async twin of :meth:`DatasetManager.get_acls`."""
        response_data = await self.client.get(f"/datasets/{dataset_id}/acl")
        if isinstance(response_data, list):
            return [DatasetAcl(**entry) for entry in response_data]
        return []

    async def create_acls(
        self,
        dataset_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[DatasetAcl]:
        """Async twin of :meth:`DatasetManager.create_acls`."""
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/acl",
            json={
                "principals": principals,
                "permissions": permissions,
                "effect": effect,
            },
        )
        if isinstance(response_data, list):
            return [DatasetAcl(**entry) for entry in response_data]
        return []

    async def delete_acl(self, dataset_id: int, acl_id: int) -> None:
        """Async twin of :meth:`DatasetManager.delete_acl`."""
        await self.client.delete(f"/datasets/{dataset_id}/acl/{acl_id}")

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

    # --- Field-level access / legacy feature CRUD (slice 012) ----------------

    async def update_acl_row_filter(
        self,
        dataset_id: int,
        acl_id: int,
        row_filter: Optional[Dict[str, Any]],
    ) -> DatasetAcl:
        """Async twin of :meth:`DatasetManager.update_acl_row_filter`."""
        response_data = await self.client.patch(
            f"/datasets/{dataset_id}/acl/{acl_id}/row-filter",
            json={"rowFilter": row_filter},
        )
        return DatasetAcl(**(response_data or {}))

    async def get_field_restrictions(
        self, dataset_id: int
    ) -> List[FieldRestriction]:
        """Async twin of :meth:`DatasetManager.get_field_restrictions`."""
        response_data = await self.client.get(
            f"/datasets/{dataset_id}/field-restrictions"
        )
        if isinstance(response_data, list):
            return [FieldRestriction(**entry) for entry in response_data]
        return []

    async def upsert_field_restrictions(
        self,
        dataset_id: int,
        principal_type: str,
        principal_id: int,
        denied_fields: Sequence[str],
    ) -> FieldRestriction:
        """Async twin of :meth:`DatasetManager.upsert_field_restrictions`."""
        if principal_type not in ("USER", "GROUP"):
            raise ValueError("principal_type must be 'USER' or 'GROUP'.")
        response_data = await self.client.put(
            f"/datasets/{dataset_id}/field-restrictions",
            json={
                "principalType": principal_type,
                "principalId": int(principal_id),
                "deniedFields": list(denied_fields or []),
            },
        )
        return FieldRestriction(**(response_data or {}))

    async def delete_field_restrictions(
        self, dataset_id: int, principal_type: str, principal_id: int
    ) -> Dict[str, Any]:
        """Async twin of :meth:`DatasetManager.delete_field_restrictions`."""
        if principal_type not in ("USER", "GROUP"):
            raise ValueError("principal_type must be 'USER' or 'GROUP'.")
        response_data = await self.client.delete(
            f"/datasets/{dataset_id}/field-restrictions",
            params={
                "principalType": principal_type,
                "principalId": int(principal_id),
            },
        )
        return response_data if isinstance(response_data, dict) else {}

    async def create_feature(
        self, dataset_id: int, feature: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Async twin of :meth:`DatasetManager.create_feature`."""
        if not isinstance(feature, dict) or not feature:
            raise ValueError("feature must be a non-empty GeoJSON Feature dict.")
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/features", json=[feature]
        )
        return response_data if isinstance(response_data, dict) else {}

    async def update_feature(
        self, dataset_id: int, feature_id: Any, feature: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Async twin of :meth:`DatasetManager.update_feature`."""
        if not isinstance(feature, dict) or not feature:
            raise ValueError("feature must be a non-empty GeoJSON Feature dict.")
        response_data = await self.client.put(
            f"/datasets/{dataset_id}/features/{feature_id}", json=feature
        )
        return response_data if isinstance(response_data, dict) else {}

    async def delete_feature(self, dataset_id: int, feature_id: Any) -> None:
        """Async twin of :meth:`DatasetManager.delete_feature`."""
        await self.client.delete(f"/datasets/{dataset_id}/features/{feature_id}")

    async def apply_feature_edits(
        self,
        dataset_id: int,
        *,
        adds: Optional[List[Dict[str, Any]]] = None,
        updates: Optional[List[Dict[str, Any]]] = None,
        deletes: Optional[List[Any]] = None,
    ) -> Dict[str, int]:
        """Async twin of :meth:`DatasetManager.apply_feature_edits`."""
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/features/applyEdits",
            json={
                "adds": list(adds or []),
                "updates": list(updates or []),
                "deletes": list(deletes or []),
            },
        )
        return response_data if isinstance(response_data, dict) else {}

    # --- Virtual datasets (slice 013) ----------------------------------------

    async def create_virtual_dataset(
        self, payload: Union[CreateVirtualDatasetDto, Dict[str, Any]]
    ) -> Dataset:
        """Async twin of :meth:`DatasetManager.create_virtual_dataset`."""
        if isinstance(payload, CreateVirtualDatasetDto):
            body = payload.model_dump(exclude_none=True)
        else:
            body = dict(payload or {})
        response_data = await self.client.post("/datasets/virtual", json=body)
        return Dataset(**(response_data or {}))

    async def create_virtual_dataset_from_filter(
        self,
        *,
        name: str,
        data_store_id: int,
        workgroup_id: int,
        root_dataset_id: int,
        query_dsl: Dict[str, Any],
        description: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> Dataset:
        """Async twin of :meth:`DatasetManager.create_virtual_dataset_from_filter`."""
        payload = CreateVirtualDatasetDto(
            name=name,
            dataStoreId=data_store_id,
            workgroupId=workgroup_id,
            rootDatasetId=root_dataset_id,
            queryDsl=query_dsl,
            kind="virtualFilter",
            description=description,
            keywords=keywords,
        )
        return await self.create_virtual_dataset(payload)

    async def create_virtual_esri_dataset(
        self, payload: Union[CreateVirtualDatasetDto, Dict[str, Any]]
    ) -> Dataset:
        """DEPRECATED alias of :meth:`create_virtual_dataset` (calls ``/virtual``)."""
        return await self.create_virtual_dataset(payload)

    async def preview_sql(
        self, data_store_id: int, sql: str
    ) -> Dict[str, Any]:
        """Async twin of :meth:`DatasetManager.preview_sql`."""
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("sql must be a non-empty string.")
        response_data = await self.client.post(
            "/datasets/sql-preview",
            json={"dataStoreId": int(data_store_id), "sql": sql},
        )
        return response_data if isinstance(response_data, dict) else {}

    async def create_virtual_sql_dataset(
        self, payload: Union[CreateVirtualSqlDatasetDto, Dict[str, Any]]
    ) -> Dataset:
        """Async twin of :meth:`DatasetManager.create_virtual_sql_dataset`."""
        if isinstance(payload, CreateVirtualSqlDatasetDto):
            body = payload.model_dump(exclude_none=True)
        else:
            body = dict(payload or {})
        response_data = await self.client.post(
            "/datasets/virtual-sql", json=body
        )
        return Dataset(**(response_data or {}))

    async def update_virtual_sql_dataset(
        self,
        dataset_id: int,
        payload: Union[CreateVirtualSqlDatasetDto, Dict[str, Any]],
    ) -> Dataset:
        """Async twin of :meth:`DatasetManager.update_virtual_sql_dataset`."""
        if isinstance(payload, CreateVirtualSqlDatasetDto):
            body = payload.model_dump(exclude_none=True)
        else:
            body = dict(payload or {})
        response_data = await self.client.put(
            f"/datasets/{dataset_id}/virtual-sql", json=body
        )
        return Dataset(**(response_data or {}))
