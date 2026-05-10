import os
import json
from typing import Any, Dict, List, Optional, Union

class DatasetManager:
    def __init__(self, client):
        self.client = client

    def _encode_query_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Encode query params for the Geopack REST API.

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

    def list(
        self,
        page: int = 1,
        page_size: int = 10,
        search_query: Optional[str] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None,
        active_filters: Optional[Dict[str, Any]] = None,
    ):
        """List datasets.

        REST API: `GET /api/datasets`

        - `search_query` -> query param `searchQuery`
        - Sorting -> `orderBy`, `orderDirection`
        - `active_filters` maps directly to query params, with arrays JSON-stringified.

        Supported `active_filters` keys (as supported by the API):
        - organizationIds, ownerIds, workgroupIds, dataStoreIds
        - subType, dataType, keywords
        - startDate, endDate
        - bbox: [xmin, ymin, xmax, ymax]
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
                params[k] = v

        response = self.client.get("/datasets", params=self._encode_query_params(params))

        # Based on DatasetsApiResponse, datasets are in the 'datasets' field
        if isinstance(response, dict) and "datasets" in response:
            return response["datasets"]
        return response

    def get(self, dataset_id):
        """
        Get detailed information about a single dataset.
        """
        return self.client.get(f"/datasets/{dataset_id}")

    def get_statistics(self):
        """Fetch aggregated dataset statistics for filter controls.

        REST API: `GET /api/datasets/statistics`
        """
        return self.client.get("/datasets/statistics")

    def get_time_series_stats(self, days: Optional[int] = None, data_type: Optional[str] = None):
        """Fetch time-series dataset stats.

        REST API: `GET /api/datasets/stats/time-series`
        """
        params: Dict[str, Any] = {}
        if days is not None:
            params["days"] = days
        if data_type is not None:
            params["dataType"] = data_type
        return self.client.get("/datasets/stats/time-series", params=self._encode_query_params(params))

    def get_stats_by_store(self):
        """Fetch aggregated stats by datastore type.

        REST API: `GET /api/datasets/stats/by-store`
        """
        return self.client.get("/datasets/stats/by-store")

    def get_stats_by_geom_type(self):
        """Fetch aggregated stats by geometry type.

        REST API: `GET /api/datasets/stats/by-geom-type`
        """
        return self.client.get("/datasets/stats/by-geom-type")

    def get_features(
        self,
        dataset_id: int,
        limit: int = 100,
        offset: int = 0,
        bbox: Optional[List[float]] = None,
        out_srid: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch features from a dataset as a GeoJSON FeatureCollection.

        REST API: `GET /api/datasets/:id/features`

        Args:
            dataset_id: ID of the dataset.
            limit: Maximum number of features to return.
            offset: Number of features to skip.
            bbox: Optional bounding box filter [minx, miny, maxx, maxy].
            out_srid: Optional output spatial reference ID.
            filters: Optional structured attribute/spatial filters.

        Returns:
            GeoJSON FeatureCollection.
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

        return self.client.get(f"/datasets/{dataset_id}/features", params=params)

    def export(
        self,
        dataset_id: int,
        workgroup_id: int,
        format: str,
        sharing_policy: str = "private",
        wait: bool = True,
        polling_interval: int = 2,
    ) -> Union[Dict[str, Any], Any]:
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
            
        task_id = task_response.get("taskId")
        return self.client.tasks.wait(task_id, interval=polling_interval)

    def download(
        self,
        task_results: Dict[str, Any],
        local_path: str,
        chunk_size: int = 8192
    ) -> str:
        """Download the result of an export task.

        Args:
            task_results: The completed Task object (containing 'results').
            local_path: Destination directory or file path.
        """
        # The task results for dataset:export contain information about the generated file
        results = task_results.get("results")
        if not results:
            raise ValueError("Task is completed but contains no results/output.")

        # In Geopack, exported files often return a download token or a direct path
        download_token = results.get("downloadToken")
        artifact_path = results.get("artifactPath")
        filename = results.get("originalName") or results.get("fileName") or "exported_data"

        # Determine download URL
        if download_token:
            # The route is apiRouter.use('/downloads', downloadRoutes) -> router.get('/:token')
            url = f"{self.client.base_url}/downloads/{download_token}"
        elif artifact_path:
            # Fallback to direct path
            url = f"{self.client.base_url}/download/{artifact_path.lstrip('/')}"
        else:
            raise ValueError("No download token or artifact path found in task results.")

        print(f"Downloading exported file...")
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
                # If local_path was a specific file path, we respect it
                target_file = local_path

            print(f"Saving to: {target_file}")
            with open(target_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
        
        return os.path.abspath(target_file)

    def upload(
        self,
        file_path: str,
        data_store_id: int,
        workgroup_id: int,
        declared_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        wait: bool = True,
        polling_interval: int = 2,
    ) -> Union[Dict[str, Any], Any]:
        """Upload a geospatial file and create a new dataset.

        This is a two-step process:
        1. Upload the file to a temporary session via `POST /api/uploads/temp`.
        2. Create a `dataset:upload` task via `POST /api/tasks` to process the file.

        Args:
            file_path: Local path to the file (e.g., .geojson, .gpkg, .shp, .zip).
            data_store_id: ID of the target DataStore.
            workgroup_id: ID of the workgroup for ownership.
            declared_type: Optional type hint ('vector', 'raster', 'table').
            metadata: Optional additional metadata for the dataset.
            wait: If True, waits for the background task to complete and returns results.
                  If False, returns the Task object immediately.
            polling_interval: Seconds between polls if wait=True.

        Returns:
            If wait=True: List of created dataset results (from Task output).
            If wait=False: The Task object with `taskId`.
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
        task_id = task_response["taskId"]
        return self.client.tasks.wait(task_id, interval=polling_interval)
