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

    def to_geodataframe(
        self,
        dataset_id: int,
        limit: int = 1000,
        **kwargs,
    ):
        """Fetch dataset features and convert them to a GeoPandas GeoDataFrame.

        Requires `geopandas` to be installed.

        Args:
            dataset_id: ID of the dataset.
            limit: Maximum features to fetch (default 1000).
            **kwargs: Additional arguments for `get_features` (bbox, filters, etc.)

        Returns:
            geopandas.GeoDataFrame
        """
        try:
            import geopandas as gpd
        except ImportError:
            raise ImportError(
                "geopandas is required for to_geodataframe(). "
                "Install it via 'pip install geopandas'."
            )

        # 1. Get metadata to find the SRID
        metadata = self.get(dataset_id)
        
        details = metadata.get("details")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = {}
        
        # Geopack stores SRID in details.srid or details.projection
        srid = (details or {}).get("srid") or (details or {}).get("projection") or 4326

        # 2. Fetch features
        geojson = self.get_features(dataset_id, limit=limit, **kwargs)

        # 3. Convert to GeoDataFrame
        if not geojson or not geojson.get("features"):
            # Return empty GDF with appropriate geometry column
            return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=f"EPSG:{srid}")

        gdf = gpd.GeoDataFrame.from_features(geojson["features"])
        
        # 4. Set CRS
        gdf.set_crs(epsg=srid, inplace=True)
        
        return gdf
