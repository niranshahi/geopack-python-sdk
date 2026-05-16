import os
import json
from typing import Any, Dict, List, Optional, Union
from .models import (
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
    TaskResult,
)

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
