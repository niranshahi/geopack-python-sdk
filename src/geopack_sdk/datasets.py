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

    def upload(self, file_path, name, data_store_id, **kwargs):
        """
        Upload a geospatial file and create a new dataset.
        This operation is asynchronous and returns a TaskReference.
        """
        # Note: Implement actual multipart upload logic here
        endpoint = "/datasets/upload" 
        # ... logic to handle file upload ...
        pass
