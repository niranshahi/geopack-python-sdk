"""Async dataset manager (JSON REST; multipart upload remains sync-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from .datasets import (
    build_simple_query,
    encode_query_params,
    normalize_feature_query_dsl,
)
from .models import Dataset, DatasetsApiResponse, FeatureCollection

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
