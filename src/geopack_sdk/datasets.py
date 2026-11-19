import os
import json
from typing import Any, Dict, List, Optional, Sequence, Union
from .models import (
    AggregateResult,
    ColumnBounds,
    Dataset,
    DatasetAcl,
    DatasetsApiResponse,
    CreateDatasetDto,
    UpdateDatasetDto,
    FeatureCollection,
    FilterStatistics,
    DatasetTimeSeriesPoint,
    DatasetStatsByStore,
    DatasetStatsByGeomType,
    DatasetDiscoverResponse,
    FieldRestriction,
    MintedUrl,
    PagedFeatureCollection,
    RelatedRecordsResult,
    RelationshipDescriptor,
    SchemaPreview,
    TaskResult,
)


def _positive_int(value: Any, name: str) -> int:
    """Coerce a pagination argument to an int >= 1 (``ValueError`` otherwise)."""
    number = int(value)
    if number < 1:
        raise ValueError(f"{name} must be >= 1 (got {value!r})")
    return number


def _build_paged_dsl(
    query: Optional[Dict[str, Any]] = None,
    *,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    order_by: Optional[List[Dict[str, Any]]] = None,
    include_total_count: bool = True,
) -> Dict[str, Any]:
    """Compose the ``query/paged`` body from a caller DSL (shared by both lanes).

    The caller's dict is honoured verbatim: ``filter`` / ``spatialFilter`` keep
    an explicit ``null``. Explicit arguments win over values already in the DSL.
    """
    dsl: Dict[str, Any] = dict(query or {})

    pagination = dict(dsl.get("pagination") or {})
    if page is not None:
        pagination["page"] = _positive_int(page, "page")
    if page_size is not None:
        pagination["pageSize"] = _positive_int(page_size, "page_size")
    pagination.setdefault("page", 1)
    pagination.setdefault("pageSize", 100)
    dsl["pagination"] = pagination

    if order_by is not None:
        dsl["orderBy"] = order_by

    options = dict(dsl.get("options") or {})
    options["includeTotalCount"] = bool(include_total_count)
    dsl["options"] = options
    return dsl


def _validate_aggregation(aggregation: Dict[str, Any]) -> None:
    """Mirror the validator's structural limits before spending a round trip.

    The aggregate *kinds* are deliberately not checked: the validator owns that
    enum and the SDK must never narrow it.
    """
    if not isinstance(aggregation, dict) or not aggregation:
        raise ValueError(
            "aggregation must be a non-empty dict "
            "({groupBy?, aggregates?, orderBy?, limit?})"
        )

    group_by = aggregation.get("groupBy")
    if group_by is not None:
        if not isinstance(group_by, list) or len(group_by) > 3:
            raise ValueError("aggregation.groupBy must be a list of at most 3 fields")

    order_by = aggregation.get("orderBy")
    if order_by is not None:
        if not isinstance(order_by, list) or len(order_by) > 3:
            raise ValueError(
                "aggregation.orderBy must be a list of at most 3 {key, direction} entries"
            )

    aggregates = aggregation.get("aggregates")
    if aggregates is not None and not isinstance(aggregates, list):
        raise ValueError("aggregation.aggregates must be a list")

    limit = aggregation.get("limit")
    if limit is not None and not 1 <= int(limit) <= 50:
        raise ValueError("aggregation.limit must be between 1 and 50")


def _build_aggregate_payload(
    aggregation: Dict[str, Any],
    filter: Optional[Dict[str, Any]],
    spatial_filter: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compose the ``query/aggregate`` body (explicit nulls, verbatim DSL)."""
    _validate_aggregation(aggregation)
    return {
        "filter": filter,
        "spatialFilter": spatial_filter,
        "aggregation": dict(aggregation),
    }


def build_simple_query(
    *,
    limit: int = 100,
    offset: int = 0,
    return_geometry: bool = True,
    out_srid: Optional[int] = None,
    where_filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a minimal FeatureQuery DSL for ``POST /api/datasets/{id}/query``.

    Matches ``src/utils/queryBuilder.js`` (``pagination``, ``projection``, optional ``filter``).
    """
    dsl: Dict[str, Any] = {
        "pagination": {"limit": limit, "offset": offset},
        "projection": {"returnGeometry": return_geometry},
    }
    if out_srid is not None:
        dsl["projection"]["outSRID"] = out_srid
    if where_filter:
        dsl["filter"] = where_filter
    return dsl


def normalize_feature_query_dsl(query: Dict[str, Any]) -> Dict[str, Any]:
    """Convert shorthand query bodies to the API FeatureQuery shape.

    Accepts legacy/top-level keys:

    - ``limit`` / ``offset`` -> ``pagination``
    - ``returnGeometry``, ``outSrid``, ``outSRID``, ``out_srid`` -> ``projection``
    """
    dsl = dict(query or {})

    pagination = dict(dsl.get("pagination") or {})
    if "limit" in dsl:
        pagination["limit"] = dsl.pop("limit")
    if "offset" in dsl:
        pagination["offset"] = dsl.pop("offset")
    if pagination:
        dsl["pagination"] = pagination

    projection = dict(dsl.get("projection") or {})
    for out_key in ("outSrid", "outSRID", "out_srid"):
        if out_key in dsl:
            projection["outSRID"] = dsl.pop(out_key)
            break
    if "returnGeometry" in dsl:
        projection["returnGeometry"] = dsl.pop("returnGeometry")
    if projection:
        dsl["projection"] = {**dsl.get("projection", {}), **projection}

    return dsl


def encode_query_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Encode query params for the Geopack REST API (shared by sync and async clients).

    - Arrays must be JSON-stringified.
    - Null/empty values are omitted.
    """
    encoded: Dict[str, Any] = {}

    for key, value in (params or {}).items():
        if value is None:
            continue
        if value == "":
            continue
        if isinstance(value, list):
            if len(value) == 0:
                continue
            encoded[key] = json.dumps(value)
            continue

        encoded[key] = value

    return encoded


class DatasetManager:
    def __init__(self, client):
        self.client = client

    def _encode_query_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return encode_query_params(params)

    def iter_datasets(
        self,
        page_size: int = 50,
        search_query: Optional[str] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None,
        active_filters: Optional[Dict[str, Any]] = None,
    ):
        """Iterate over all datasets matching filters by auto-fetching successive pages."""
        current_page = 1
        while True:
            resp = self.list(
                page=current_page,
                page_size=page_size,
                search_query=search_query,
                order_by=order_by,
                order_direction=order_direction,
                active_filters=active_filters,
            )
            if not resp.datasets:
                break
            yield from resp.datasets
            if len(resp.datasets) < page_size:
                break
            current_page += 1

    def list(

        self,
        page: int = 1,
        page_size: int = 10,
        search_query: Optional[str] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None,
        active_filters: Optional[Dict[str, Any]] = None,
    ) -> DatasetsApiResponse:
        """List datasets with type-safe response.

        REST API: `GET /api/datasets`

        - `search_query` -> query param `searchQuery`
        - Sorting -> `orderBy`, `orderDirection`
        - `active_filters` maps directly to query params, with arrays JSON-stringified.

        Supported `active_filters` keys (as supported by the API):
        - organizationIds, ownerIds, workgroupIds, dataStoreIds
        - subType, dataType, keywords
        - startDate, endDate
        - bbox: [xmin, ymin, xmax, ymax]

        Returns:
            DatasetsApiResponse: Validated response with datasets array and pagination info
        """

        params: Dict[str, Any] = {
            "page": page,
            "pageSize": page_size,
        }

        if search_query is not None:
            params["searchQuery"] = search_query.strip()

        if order_by:
            params["orderBy"] = order_by

        if order_direction:
            params["orderDirection"] = "desc" if str(order_direction).lower() == "desc" else "asc"

        if active_filters:
            for k, v in active_filters.items():
                # The backend expects these specific filters to be arrays (JSON stringified)
                # Matches keys in DatasetFilterPanel.vue and DatasetFilters interface
                array_filters = [
                    'organizationIds', 'ownerIds', 'workgroupIds', 'dataStoreIds', 
                    'subType', 'dataType', 'keywords'
                ]
                if k in array_filters and not isinstance(v, list):
                    params[k] = [v]
                else:
                    params[k] = v

        response_data = self.client.get("/datasets", params=self._encode_query_params(params))

        # Validate and convert to Pydantic model
        return DatasetsApiResponse(**response_data)

    def _get_normalized_details(self, dataset: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to parse and normalize the 'details' field from a dataset object.
        
        The 'details' field in the database can be a JSON string that needs parsing.
        This method mimics the logic in the Vue frontend (datasetStore.ts and DatasetPropertiesPanel.vue).
        """
        details = dataset.get('details', {})
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = {}
        
        if not details:
            details = {}

        # Normalize common fields (mimic DatasetPropertiesPanel.vue logic)
        # Spatial Reference
        srid = details.get('spatialReference', {}).get('srid') or details.get('srid')
        wkt = details.get('spatialReference', {}).get('wkt') or details.get('wkt')
        
        # Extent
        extent = details.get('extent')
        
        # Raster Dimensions
        raster_dims = details.get('rasterDimensions', {})
        if not raster_dims.get('width'): raster_dims['width'] = details.get('width')
        if not raster_dims.get('height'): raster_dims['height'] = details.get('height')
        
        return {
            **details,
            'spatialReference': {'srid': srid, 'wkt': wkt},
            'extent': extent,
            'rasterDimensions': raster_dims
        }

    def download(
        self,
        task_results: Union[TaskResult, Dict[str, Any]],
        local_path: str,
        chunk_size: int = 8192
    ) -> str:
        """Download the result of an export task.

        Args:
            task_results: The completed TaskResult object or dict (containing 'results').
            local_path: Destination directory or file path.
        """
        # The task results for dataset:export contain information about the generated file
        results = task_results.results if isinstance(task_results, TaskResult) else task_results.get("results")
        if not results:
            raise ValueError("Task is completed but contains no results/output.")

        # In Geopack, exported files often return a download token or a direct path
        download_token = results.get("downloadToken")
        artifact_path = results.get("artifactPath")
        filename = results.get("originalName") or results.get("fileName") or "exported_data"

        # Determine download URL
        if download_token:
            url = f"{self.client.base_url}/downloads/{download_token}"
        elif artifact_path:
            url = f"{self.client.base_url}/download/{artifact_path.lstrip('/')}"
        else:
            raise ValueError("No download token or artifact path found in task results.")

        with self.client.session.get(url, stream=True) as r:
            r.raise_for_status()
            
            # Try to get filename from Content-Disposition header (mimic browser)
            content_disposition = r.headers.get("Content-Disposition")
            header_filename = None
            if content_disposition and "filename=" in content_disposition:
                # Basic parsing, handling potential quotes
                header_filename = content_disposition.split("filename=")[1].strip('"')
            
            # Final filename resolution logic
            final_filename = header_filename or filename or "exported_data"
            
            if os.path.isdir(local_path):
                target_file = os.path.join(local_path, final_filename)
            else:
                target_file = local_path

            with open(target_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
        
        return os.path.abspath(target_file)

    def get(self, dataset_id: int) -> Dataset:
        """
        Get detailed information about a single dataset with type-safe response.

        REST API: `GET /api/datasets/{id}`

        Args:
            dataset_id: ID of the dataset to fetch

        Returns:
            Dataset: Validated dataset model
        """
        dataset_data = self.client.get(f"/datasets/{dataset_id}")
        
        # Validate and convert to Pydantic model
        return Dataset(**dataset_data)

    def get_statistics(self) -> FilterStatistics:
        """Fetch aggregated dataset statistics for filter controls with type-safe response.

        REST API: `GET /api/datasets/statistics`

        Returns:
            FilterStatistics: Validated filter statistics model
        """
        response_data = self.client.get("/datasets/statistics")
        return FilterStatistics(**response_data)

    def get_time_series_stats(self, days: Optional[int] = None, data_type: Optional[str] = None) -> List[DatasetTimeSeriesPoint]:
        """Fetch time-series dataset stats with type-safe response.

        REST API: `GET /api/datasets/stats/time-series`

        Args:
            days: Number of days to look back
            data_type: Filter by data type (vector, raster, table)

        Returns:
            List[DatasetTimeSeriesPoint]: Validated time-series data points
        """
        params: Dict[str, Any] = {}
        if days is not None:
            params["days"] = days
        if data_type is not None:
            params["dataType"] = data_type
        response_data = self.client.get("/datasets/stats/time-series", params=self._encode_query_params(params))
        
        # API returns an array, validate each item
        if isinstance(response_data, list):
            return [DatasetTimeSeriesPoint(**item) for item in response_data]
        return []

    def get_stats_by_store(self) -> List[DatasetStatsByStore]:
        """Fetch aggregated stats by datastore type with type-safe response.

        REST API: `GET /api/datasets/stats/by-store`

        Returns:
            List[DatasetStatsByStore]: Validated stats by datastore type
        """
        response_data = self.client.get("/datasets/stats/by-store")
        
        # API returns an array, validate each item
        if isinstance(response_data, list):
            return [DatasetStatsByStore(**item) for item in response_data]
        return []

    def get_stats_by_geom_type(self) -> List[DatasetStatsByGeomType]:
        """Fetch aggregated stats by geometry type with type-safe response.

        REST API: `GET /api/datasets/stats/by-geom-type`

        Returns:
            List[DatasetStatsByGeomType]: Validated stats by geometry type
        """
        response_data = self.client.get("/datasets/stats/by-geom-type")
        
        # API returns an array, validate each item
        if isinstance(response_data, list):
            return [DatasetStatsByGeomType(**item) for item in response_data]
        return []

    def get_features(
        self,
        dataset_id: int,
        limit: int = 100,
        offset: int = 0,
        bbox: Optional[List[float]] = None,
        out_srid: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> FeatureCollection:
        """Fetch features from a dataset as a GeoJSON FeatureCollection with type-safe response.

        REST API: `GET /api/datasets/:id/features`

        Args:
            dataset_id: ID of the dataset.
            limit: Maximum number of features to return.
            offset: Number of features to skip.
            bbox: Optional bounding box filter [minx, miny, maxx, maxy].
            out_srid: Optional output spatial reference ID.
            filters: Optional structured attribute/spatial filters.

        Returns:
            FeatureCollection: Validated GeoJSON FeatureCollection model
        """
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

        response_data = self.client.get(f"/datasets/{dataset_id}/features", params=params)
        return FeatureCollection(**response_data)

    def to_geodataframe(self, dataset_id: int, limit: int = 1000) -> Any:
        """Fetch dataset features and convert to a GeoPandas GeoDataFrame.
        
        Requires `geopandas` to be installed.
        """
        try:
            import geopandas as gpd
            from shapely.geometry import shape
        except ImportError:
            raise ImportError("geopandas and shapely are required for to_geodataframe()")

        # 1. Fetch metadata to check type and CRS
        metadata = self.get(dataset_id)
        if metadata.dataType != 'vector':
            raise ValueError(f"Dataset {dataset_id} is not a vector dataset (type: {metadata.dataType}). GeoDataFrame only supports vector data.")

        # 2. Fetch features (now returns FeatureCollection Pydantic model)
        feature_collection = self.get_features(dataset_id, limit=limit)
        
        if not feature_collection.features:
            # Return empty GeoDataFrame if no features
            return gpd.GeoDataFrame()

        # 3. Convert Pydantic model to dict for GeoPandas
        geojson_dict = feature_collection.model_dump()
        
        # 4. Convert to GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(geojson_dict['features'])
        
        # 5. Set CRS with a robust hierarchy
        # First check if FeatureCollection has CRS
        if feature_collection.crs:
            geojson_crs = feature_collection.crs
        else:
            geojson_crs = geojson_dict.get('crs')
        
        norm = metadata.model_dump().get('normalizedDetails', {})
        sp_ref = norm.get('spatialReference', {})
        
        # Priority 1: Check if GeoJSON already has CRS info
        # Priority 2: Use SRID if valid (> 0)
        srid = sp_ref.get('srid')
        
        # Priority 3: Use WKT if available (more robust than Proj4)
        wkt = sp_ref.get('wkt')
        
        # Priority 4: Use Proj4 if others are missing
        proj4 = sp_ref.get('proj4')

        if geojson_crs and isinstance(geojson_crs, dict):
            # GeoJSON CRS standard often uses 'urn:ogc:def:crs:EPSG::32640'
            crs_name = geojson_crs.get('properties', {}).get('name', '')
            if 'EPSG::' in crs_name:
                try:
                    epsg_code = int(crs_name.split('EPSG::')[-1])
                    gdf.set_crs(epsg=epsg_code, inplace=True)
                except (ValueError, IndexError):
                    pass # Fallback to metadata if parsing fails
        
        # If CRS not set by GeoJSON parsing, follow hierarchy
        if gdf.crs is None:
            if srid and srid > 0:
                gdf.set_crs(epsg=srid, inplace=True)
            elif wkt:
                gdf.set_crs(wkt, inplace=True)
            elif proj4:
                gdf.set_crs(proj4, inplace=True)
            else:
                gdf.set_crs(epsg=4326, inplace=True)
        
        return gdf

    def create(self, dataset_data: CreateDatasetDto) -> Dataset:
        """Create a new dataset.

        REST API: `POST /api/datasets`

        Args:
            dataset_data: Validated CreateDatasetDto model or dict

        Returns:
            Dataset: The created dataset model
        """
        payload = dataset_data.model_dump() if isinstance(dataset_data, CreateDatasetDto) else dataset_data
        response_data = self.client.post("/datasets", json=payload)
        return Dataset(**response_data)

    def update(self, dataset_id: int, dataset_data: UpdateDatasetDto) -> Dataset:
        """Update an existing dataset.

        REST API: `PUT /api/datasets/{id}`

        Args:
            dataset_id: ID of the dataset to update
            dataset_data: Validated UpdateDatasetDto model or dict

        Returns:
            Dataset: The updated dataset model
        """
        payload = dataset_data.model_dump(exclude_unset=True) if isinstance(dataset_data, UpdateDatasetDto) else dataset_data
        response_data = self.client.put(f"/datasets/{dataset_id}", json=payload)
        return Dataset(**response_data)

    def export(
        self,
        dataset_id: int,
        workgroup_id: int,
        format: str,
        sharing_policy: str = "private",
        wait: bool = True,
        polling_interval: int = 2,
    ) -> TaskResult:
        """Request an export of a dataset.

        Args:
            dataset_id: ID of the dataset to export.
            workgroup_id: ID of the workgroup owning the task.
            format: Target format ('geojson', 'shapefile', 'gpkg', 'geotiff', 'csv', etc.)
            sharing_policy: 'private' or 'public'.
            wait: If True, waits for the task to complete.
            polling_interval: Seconds between polls if wait=True.
        """
        payload = {
            "taskType": "dataset:export",
            "workgroupId": workgroup_id,
            "inputParameters": {
                "datasetId": dataset_id,
                "format": format,
                "options": {
                    "sharingPolicy": sharing_policy
                }
            }
        }
        
        # Call the general task creation endpoint
        task_response = self.client.tasks.create(payload)
        
        if not wait:
            return task_response
            
        task_id = task_response.task_id
        return self.client.tasks.wait(task_id, interval=polling_interval)

    def upload(
        self,
        file_path: str,
        data_store_id: int,
        workgroup_id: int,
        declared_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        wait: bool = True,
        polling_interval: int = 2,
    ) -> TaskResult:
        """Upload a geospatial file and create a new dataset.

        Returns:
            TaskResult: The resulting task object or completion result.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # 1. Upload file to temp session
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"files": (filename, f)}
            upload_response = self.client._request(
                "POST", "/uploads/temp", files=files
            )

        session_id = upload_response["uploadSessionId"]
        uploaded_file = upload_response["files"][0]
        relative_path = uploaded_file["relativePath"]

        # 2. Create the dataset:upload task
        input_params = {
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

        task_payload = {
            "taskType": "dataset:upload",
            "workgroupId": workgroup_id,
            "inputParameters": input_params,
        }

        task_response = self.client.tasks.create(task_payload)
        
        if not wait:
            return task_response

        # 3. Wait for completion
        task_id = task_response.taskId
        return self.client.tasks.wait(task_id, interval=polling_interval, quiet=True)

    def delete(self, dataset_id: int) -> None:
        """Delete a dataset by ID (204 No Content).

        REST API: `DELETE /api/datasets/{id}`
        """
        self.client.delete(f"/datasets/{dataset_id}")

    def query(
        self,
        dataset_id: int,
        query: Optional[Dict[str, Any]] = None,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
        return_geometry: bool = True,
        out_srid: Optional[int] = None,
    ) -> FeatureCollection:
        """Run a structured attribute/spatial query on a dataset.

        REST API: `POST /api/datasets/{datasetId}/query`

        Args:
            dataset_id: Target dataset ID.
            query: FeatureQuery DSL (``pagination``, ``projection``, ``filter``,
                ``spatialFilter``, ``orderBy``, …). Shorthand keys ``limit``,
                ``offset``, and ``returnGeometry`` at the top level are normalized
                automatically (see :func:`normalize_feature_query_dsl`).
            limit: If ``query`` is omitted, build a simple DSL with this page size.
            offset: Row offset when using ``limit`` shorthand.
            return_geometry: Include geometry in results (default True).
            out_srid: Optional output SRID in ``projection.outSRID``.

        Example::

            fc = client.datasets.query(
                ds_id,
                build_simple_query(limit=5, offset=0),
            )
        """
        if query is None:
            if limit is None:
                raise ValueError("Provide query dict or limit= for a simple query.")
            query = build_simple_query(
                limit=limit,
                offset=offset,
                return_geometry=return_geometry,
                out_srid=out_srid,
            )
        else:
            query = normalize_feature_query_dsl(query)

        response_data = self.client.post(
            f"/datasets/{dataset_id}/query",
            json=query,
        )
        return FeatureCollection(**response_data)

    # --- Query lanes (slice 010) --------------------------------------------

    def query_paged(
        self,
        dataset_id: int,
        query: Optional[Dict[str, Any]] = None,
        *,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        order_by: Optional[List[Dict[str, Any]]] = None,
        include_total_count: bool = True,
    ) -> PagedFeatureCollection:
        """Run the server-paged query lane (COUNT + page envelope).

        REST API: `POST /api/datasets/{datasetId}/query/paged`

        Args:
            dataset_id: Target dataset ID.
            query: FeatureQuery DSL. The dict is honoured verbatim: ``filter``
                and ``spatialFilter`` keep an explicit ``null`` (the DSL's own
                "no scope"), they are never dropped.
            page: 1-based page number. Defaults to the DSL's value, else 1.
            page_size: Rows per page. Defaults to the DSL's value, else 100.
            order_by: `orderBy` entries, e.g. ``[{"field": "area",
                "direction": "DESC"}]``.
            include_total_count: ``False`` skips the COUNT (``total_count`` is
                then ``None``). Default True.

        Notes:
            The server clamps page/pageSize and may *degrade* the count to
            ``null`` (100k rows or a 15 s timeout). That is a normal 200 answer:
            check :attr:`PagePagination.is_count_degraded`, never an exception.
            ``result.metadata`` carries ``baseFilterApplied`` / ``rlsApplied`` /
            ``queryMode`` — it is how a caller proves the scope was applied.

        Raises:
            PagedUnsupported: the datastore cannot page this query (400
                ``PAGED_UNSUPPORTED``); fall back to :meth:`query`.
        """
        dsl = _build_paged_dsl(
            query,
            page=page,
            page_size=page_size,
            order_by=order_by,
            include_total_count=include_total_count,
        )

        response_data = self.client.post(
            f"/datasets/{dataset_id}/query/paged",
            json=dsl,
        )
        return PagedFeatureCollection(**(response_data or {}))

    def iterate_pages(
        self,
        dataset_id: int,
        query: Optional[Dict[str, Any]] = None,
        *,
        page_size: int = 1000,
        include_total_count: bool = True,
    ):
        """Yield :class:`PagedFeatureCollection` objects until the last page.

        Stops on ``has_next_page == false`` or on an empty page (the guard that
        keeps a server that ignores ``pagination.page`` from looping forever).
        """
        page = 1
        while True:
            result = self.query_paged(
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

    def aggregate(
        self,
        dataset_id: int,
        *,
        aggregation: Dict[str, Any],
        filter: Optional[Dict[str, Any]] = None,
        spatial_filter: Optional[Dict[str, Any]] = None,
    ) -> AggregateResult:
        """Group and aggregate over the same access-scoped base as ``query_paged``.

        REST API: `POST /api/datasets/{datasetId}/query/aggregate`

        Args:
            dataset_id: Target dataset ID.
            aggregation: ``{groupBy?, aggregates?, orderBy?, limit?}``.
                ``aggregates[]`` entries are ``{field?, aggregate, alias?, p?}``
                where ``p`` (0..1) is percentile-only. ``groupBy`` holds at most
                3 ``{field}`` entries, ``orderBy`` at most 3
                ``{key, direction, by?}`` entries and ``limit`` is 1..50.
            filter: Optional attribute scope; sent as an explicit ``null`` when
                omitted, like the portal's own DSL.
            spatial_filter: Optional spatial scope, same null semantics.

        Returns:
            Buckets only — this lane never returns feature rows or geometry.

        Raises:
            ValueError: a structural limit is violated (no round trip spent).
            AggregationUnsupported: the datastore cannot aggregate (400).
            AggregationInvalidArgs: the server rejected a named key (400); the
                offending key is on ``error.key``.
        """
        payload = _build_aggregate_payload(aggregation, filter, spatial_filter)
        response_data = self.client.post(
            f"/datasets/{dataset_id}/query/aggregate",
            json=payload,
        )
        return AggregateResult(**(response_data or {}))

    def count(
        self,
        dataset_id: int,
        *,
        filter: Optional[Dict[str, Any]] = None,
        spatial_filter: Optional[Dict[str, Any]] = None,
        field: Optional[str] = None,
        distinct: bool = False,
    ) -> int:
        """Count features (or distinct values of ``field``) in one round trip.

        Sugar over :meth:`aggregate`: no ``groupBy``, ``limit`` 1. Counting rows
        client-side by paging the whole result set is exactly what this avoids.
        """
        entry: Dict[str, Any] = {
            "aggregate": "countDistinct" if distinct else "count",
            "alias": "value",
        }
        if field:
            entry["field"] = field

        result = self.aggregate(
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

    # --- Minted capability URLs (slice 010) ---------------------------------

    def mint_query_access_url(
        self, dataset_id: int, query_dsl: Dict[str, Any]
    ) -> MintedUrl:
        """Mint a signed URL for the query-features lane.

        REST API: `POST /api/datasets/{datasetId}/query/mint-access-url`
        (bearer-only, no cookie session).

        The answer is a **capability URL**: anyone holding it can read the bound
        query on this dataset until ``expires_at``. Do not log it and do not
        replay it against another dataset.
        """
        if not isinstance(query_dsl, dict):
            raise ValueError("query_dsl must be a dict — the DSL the URL is bound to")
        response_data = self.client.post(
            f"/datasets/{dataset_id}/query/mint-access-url",
            json={"queryDsl": query_dsl},
        )
        return MintedUrl(**(response_data or {}))

    def mint_mvt_access_url(
        self,
        dataset_id: int,
        query_dsl: Optional[Dict[str, Any]] = None,
    ) -> MintedUrl:
        """Mint a signed URL for the MVT tile lane (bearer-only).

        REST API: `POST /api/datasets/{datasetId}/mvt/mint-access-url`

        ``query_dsl`` is optional here (the whole dataset is the default scope).
        The answer is a capability URL — see :meth:`mint_query_access_url`.
        """
        payload: Dict[str, Any] = {}
        if query_dsl is not None:
            if not isinstance(query_dsl, dict):
                raise ValueError("query_dsl must be a dict when provided")
            payload["queryDsl"] = query_dsl
        response_data = self.client.post(
            f"/datasets/{dataset_id}/mvt/mint-access-url",
            json=payload,
        )
        return MintedUrl(**(response_data or {}))

    def get_tiles_access_url(self, dataset_id: int) -> MintedUrl:
        """Mint the dataset tiles access URL (bearer-only).

        REST API: `GET /api/datasets/{id}/tiles/access-url`

        Video and raster datasets answer with the media variant of the same
        envelope. The URL is a capability — see :meth:`mint_query_access_url`.
        """
        response_data = self.client.get(f"/datasets/{dataset_id}/tiles/access-url")
        return MintedUrl(**(response_data or {}))

    # --- Relationships, schema and access context (slice 011) ---------------

    def get_relationships(self, dataset_id: int) -> List[RelationshipDescriptor]:
        """List the provider-neutral relationships of a dataset.

        REST API: `GET /api/datasets/{datasetId}/relationships`

        ESRI entries are returned with ``read_only=True`` — they are surfaced,
        never filtered out. Each descriptor keeps its catalog entry under
        ``raw`` so a provider field addition is not a breaking change.

        Raises:
            RelationshipCatalogUnavailable: 409 — the catalog is unavailable or
                unsupported for this store. Treat it as a state: there is no
                relationship lane for this dataset right now.
        """
        response_data = self.client.get(f"/datasets/{dataset_id}/relationships")
        entries = (response_data or {}).get("relationships") or []
        return [RelationshipDescriptor(**entry) for entry in entries]

    def get_related_records(
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
        """Read the records related to one or more source records.

        REST API: `POST /api/datasets/{datasetId}/related-records`

        Args:
            dataset_id: Source dataset ID.
            relationship_name: Catalog entry name (see :meth:`get_relationships`).
            origin_object_ids: **Source** OID values (``details.oidField``), not
                arbitrary field values. At least one.
            direction: ``forward`` (default) or ``backward``.
            limit: ``queryOptions.limit`` — the paging contract for load-more
                (``rows == limit`` means "maybe more").
            offset: ``queryOptions.offset``.
            return_geometry: ``queryOptions.returnGeometry`` (default True).
            out_srid: Optional ``queryOptions.outSRID``.

        Notes:
            The answer carries ONLY the related (target) records — the source
            leg is stripped server-side. With several origin ids the rows are
            grouped per source record in ``metadata.groups``; do not flatten it.
            ``__jct__*`` properties are junction fields: keep them beside the
            target record, never fused into it.

        Raises:
            ValueError: the request shape is invalid (nothing was sent).
            GeopackAPIError: 400 for an unknown relationship or an unregistered
                related dataset — the message names the field.
            GeopackAuthError: 403 on the *related* leg.
        """
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

        payload = {
            "relationshipName": relationship_name,
            "direction": direction,
            "originObjectIds": oids,
            "queryOptions": query_options,
        }
        response_data = self.client.post(
            f"/datasets/{dataset_id}/related-records",
            json=payload,
        )
        return RelatedRecordsResult(**(response_data or {}))

    def preview_schema(
        self, dataset_id: int, query_dsl: Dict[str, Any]
    ) -> SchemaPreview:
        """Compose the schema of a relationship DSL without executing it.

        REST API: `POST /api/datasets/{datasetId}/schema-preview`

        The DSL must contain a ``relationship`` or ``relationshipJoin`` node — a
        plain query is rejected by the server (the SDK does not second-guess the
        node's nesting, the server is the authority). No dataset is created and
        no row is read: this is the ephemeral-layer lane.

        The payload is returned verbatim: ``fields``, ``relationships`` and the
        geometry/OID hints are what the caller composes the next hop from.
        """
        if not isinstance(query_dsl, dict) or not query_dsl:
            raise ValueError("query_dsl must be a non-empty dict with a relationship node")
        response_data = self.client.post(
            f"/datasets/{dataset_id}/schema-preview",
            json={"queryDsl": query_dsl},
        )
        return SchemaPreview(**(response_data or {}))

    def get_column_bounds(self, dataset_id: int) -> ColumnBounds:
        """Read live numeric column bounds (min/max) for the dataset.

        REST API: `GET /api/datasets/{datasetId}/column-bounds`

        The values come from the live store, not from the cached ``details``,
        so they can differ — that is the point of the endpoint.
        """
        response_data = self.client.get(f"/datasets/{dataset_id}/column-bounds")
        return ColumnBounds(**(response_data or {}))

    def get_access_context(self, dataset_id: int) -> Dict[str, Any]:
        """Read the caller's effective access context for a dataset.

        REST API: `GET /api/datasets/{id}/access-context`

        The payload (row scope + effective field view/edit/deny map) is
        **opaque and authoritative**: deny-wins is a server rule and a client
        copy would drift. Returned as a plain dict on purpose — it is a living
        security surface, not a stable contract.

        Unlike the other reads this one is available to a *would-be editor*: the
        route accepts ``dataset:read``, ``features:read``, ``features:create``
        or ``features:update``.
        """
        response_data = self.client.get(f"/datasets/{dataset_id}/access-context")
        return response_data or {}

    def discover(
        self,
        source_files: List[Dict[str, Any]],
        data_store_id: int,
        workgroup_id: int,
        declared_type: Optional[str] = None,
        wait: bool = True,
        polling_interval: int = 2,
    ) -> Union[DatasetDiscoverResponse, TaskResult]:
        """Discover datasets from uploaded temp files.

        REST API: `POST /api/datasets/discover`

        Args:
            source_files: Upload metadata (sessionId, relativePath, originalName, …).
            data_store_id: Target datastore ID.
            workgroup_id: Owning workgroup ID.
            declared_type: Optional ``vector``, ``raster``, or ``table``.
            wait: If True and API returns a background task, poll until complete.
            polling_interval: Seconds between polls when waiting on a task.

        Returns:
            DatasetDiscoverResponse for immediate discovery, or TaskResult when
            ``wait=True`` and the API queued ``dataset:discovery``.
        """
        payload: Dict[str, Any] = {
            "sourceFiles": source_files,
            "dataStoreId": data_store_id,
            "workgroupId": workgroup_id,
        }
        if declared_type:
            payload["declaredType"] = declared_type

        response_data = self.client.post("/datasets/discover", json=payload)
        result = DatasetDiscoverResponse(**response_data)

        if not wait or not result.is_background_task:
            return result

        task_id = result.taskId
        if not task_id:
            return result

        task = self.client.tasks.wait_for_task(
            task_id, interval=polling_interval, quiet=True
        )
        return task

    def get_acls(self, dataset_id: int) -> List[DatasetAcl]:
        """Get ACL entries for a dataset.

        REST API: `GET /api/datasets/{id}/acl`
        """
        response_data = self.client.get(f"/datasets/{dataset_id}/acl")
        if isinstance(response_data, list):
            return [DatasetAcl(**entry) for entry in response_data]
        return []

    def create_acls(
        self,
        dataset_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[DatasetAcl]:
        """Create ACL entries for a dataset.

        REST API: `POST /api/datasets/{id}/acl`

        Args:
            principals: ``{ principalType: 'USER'|'GROUP', principalId: int }``.
            permissions: Permission name strings (e.g. ``dataset:read``).
            effect: ``Allow`` or ``Deny``.
        """
        payload = {
            "principals": principals,
            "permissions": permissions,
            "effect": effect,
        }
        response_data = self.client.post(
            f"/datasets/{dataset_id}/acl",
            json=payload,
        )
        if isinstance(response_data, list):
            return [DatasetAcl(**entry) for entry in response_data]
        return []

    def delete_acl(self, dataset_id: int, acl_id: int) -> None:
        """Delete one ACL entry for a dataset (204 No Content).

        REST API: `DELETE /api/datasets/{id}/acl/{aclId}`
        """
        self.client.delete(f"/datasets/{dataset_id}/acl/{acl_id}")

    def update_acl_row_filter(
        self,
        dataset_id: int,
        acl_id: int,
        row_filter: Optional[Dict[str, Any]],
    ) -> DatasetAcl:
        """Set or clear the row-level filter on ONE ACL entry (slice 012 §2.3).

        ``row_filter=None`` CLEARS the filter: the key is sent with a null
        value, so the server can tell "clear" from "unchanged". The filter
        uses the same DSL node shape as ``filter`` / ``spatialFilter``; a
        malformed filter comes back as a 400 whose message is kept verbatim.

        REST API: `PATCH /api/datasets/{id}/acl/{aclId}/row-filter`
        """
        response_data = self.client.patch(
            f"/datasets/{dataset_id}/acl/{acl_id}/row-filter",
            json={"rowFilter": row_filter},
        )
        return DatasetAcl(**(response_data or {}))

    def get_field_restrictions(self, dataset_id: int) -> List[FieldRestriction]:
        """List the standalone field-deny overlays for a dataset.

        A restriction SUBTRACTS fields for one principal; it never grants
        table access and never changes ACL uniqueness. Requires
        ``dataset:share`` (or ``admin:dataset:manage_permissions``).

        REST API: `GET /api/datasets/{id}/field-restrictions`
        """
        response_data = self.client.get(
            f"/datasets/{dataset_id}/field-restrictions"
        )
        if isinstance(response_data, list):
            return [FieldRestriction(**entry) for entry in response_data]
        return []

    def upsert_field_restrictions(
        self,
        dataset_id: int,
        principal_type: str,
        principal_id: int,
        denied_fields: Sequence[str],
    ) -> FieldRestriction:
        """Create or replace the deny overlay of ONE principal.

        ``denied_fields`` replaces the stored list (it is not additive). The
        server validates it against the protected-field list and answers a
        coded 400 (``FIELD_POLICY_PROTECTED_FIELD`` / ``FIELD_POLICY_INVALID``)
        which surfaces as :class:`~geopack_sdk.exceptions.FieldPolicyError`.

        REST API: `PUT /api/datasets/{id}/field-restrictions`
        """
        if principal_type not in ("USER", "GROUP"):
            raise ValueError("principal_type must be 'USER' or 'GROUP'.")
        payload = {
            "principalType": principal_type,
            "principalId": int(principal_id),
            "deniedFields": list(denied_fields or []),
        }
        response_data = self.client.put(
            f"/datasets/{dataset_id}/field-restrictions", json=payload
        )
        return FieldRestriction(**(response_data or {}))

    def delete_field_restrictions(
        self, dataset_id: int, principal_type: str, principal_id: int
    ) -> Dict[str, Any]:
        """Remove the deny overlay of one principal.

        The principal rides in the QUERY STRING (the server calls it the
        primary form; the body is only a fallback) — the SDK always uses the
        query form. Answers ``{"deleted": <count>}``; deleting an overlay
        that does not exist is a 200 with ``deleted: 0``, not an error.

        REST API: `DELETE /api/datasets/{id}/field-restrictions`
        """
        if principal_type not in ("USER", "GROUP"):
            raise ValueError("principal_type must be 'USER' or 'GROUP'.")
        response_data = self.client.delete(
            f"/datasets/{dataset_id}/field-restrictions",
            params={
                "principalType": principal_type,
                "principalId": int(principal_id),
            },
        )
        return response_data if isinstance(response_data, dict) else {}

    # --- Legacy feature CRUD (slice 012 §2.2) --------------------------------
    #
    # These are NOT transactional across relationships and they cannot link or
    # unlink records: prefer ``client.edit_documents`` for anything beyond a
    # simple scripted write. A partial patch is unsupported — PUT replaces the
    # whole feature.

    def create_feature(
        self, dataset_id: int, feature: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Insert one GeoJSON Feature; answers ``{"ids": [...]}``.

        The endpoint takes an ARRAY of features, so a single feature is sent
        wrapped in a one-element list.

        REST API: `POST /api/datasets/{datasetId}/features`
        """
        if not isinstance(feature, dict) or not feature:
            raise ValueError("feature must be a non-empty GeoJSON Feature dict.")
        response_data = self.client.post(
            f"/datasets/{dataset_id}/features", json=[feature]
        )
        return response_data if isinstance(response_data, dict) else {}

    def update_feature(
        self, dataset_id: int, feature_id: Any, feature: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Replace one feature with the supplied GeoJSON Feature.

        The lane has no partial patch: send the whole feature (use
        ``edit_documents`` for attribute-only changes). The server answers an
        empty 200, so the SDK returns an empty dict.

        REST API: `PUT /api/datasets/{datasetId}/features/{featureId}`
        """
        if not isinstance(feature, dict) or not feature:
            raise ValueError("feature must be a non-empty GeoJSON Feature dict.")
        response_data = self.client.put(
            f"/datasets/{dataset_id}/features/{feature_id}", json=feature
        )
        return response_data if isinstance(response_data, dict) else {}

    def delete_feature(self, dataset_id: int, feature_id: Any) -> None:
        """Delete one feature (204 No Content; a missing id is also a 204).

        REST API: `DELETE /api/datasets/{datasetId}/features/{featureId}`
        """
        self.client.delete(f"/datasets/{dataset_id}/features/{feature_id}")

    def apply_feature_edits(
        self,
        dataset_id: int,
        *,
        adds: Optional[List[Dict[str, Any]]] = None,
        updates: Optional[List[Dict[str, Any]]] = None,
        deletes: Optional[List[Any]] = None,
    ) -> Dict[str, int]:
        """Apply a batch of legacy feature edits; answers per-kind counts.

        The body keys are ``adds`` / ``updates`` / ``deletes`` and the answer
        is ``{"added", "updated", "deleted"}``. This lane is transactional for
        the batch but relationship-blind: use ``edit_documents`` when a change
        spans relationships.

        REST API: `POST /api/datasets/{datasetId}/features/applyEdits`
        """
        payload = {
            "adds": list(adds or []),
            "updates": list(updates or []),
            "deletes": list(deletes or []),
        }
        response_data = self.client.post(
            f"/datasets/{dataset_id}/features/applyEdits", json=payload
        )
        return response_data if isinstance(response_data, dict) else {}
