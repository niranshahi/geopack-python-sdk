"""Async datastore manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .datastores import parse_datastore_list_response
from .models import (
    DataStoreListResponse,
    DataStoreResponse,
    EsriDiscoverResponse,
    EsriGeodatabaseInfoResponse,
    EsriRegisterOptions,
    EsriRegisterResponse,
    EsriSchemaUpdateResponse,
    EsriBulkDeleteResponse,
)

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncDataStoreManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def list(self) -> DataStoreListResponse:
        response_data = await self.client.get("/datastores")
        return parse_datastore_list_response(response_data)

    async def get(self, data_store_id: int) -> DataStoreResponse:
        response_data = await self.client.get(f"/datastores/{data_store_id}")
        return DataStoreResponse(**response_data)

    async def discover_esri_datasets(
        self,
        data_store_id: int,
        include_hidden: bool = False,
        dataset_type: Optional[str] = None,
    ) -> EsriDiscoverResponse:
        params: Dict[str, Any] = {}
        if include_hidden:
            params["includeHidden"] = "true"
        if dataset_type:
            params["type"] = dataset_type
        raw = await self.client.get(
            f"/datastores/{data_store_id}/esri/datasets",
            params=params or None,
        )
        return EsriDiscoverResponse(**raw)

    async def register_esri_datasets(
        self,
        data_store_id: int,
        workgroup_id: int,
        dataset_names: Optional[List[str]] = None,
        options: Optional[Union[EsriRegisterOptions, Dict[str, Any]]] = None,
    ) -> EsriRegisterResponse:
        payload: Dict[str, Any] = {"workgroupId": workgroup_id}
        if dataset_names is not None:
            payload["datasetNames"] = dataset_names
        if options is not None:
            if isinstance(options, EsriRegisterOptions):
                payload["options"] = options.model_dump(exclude_none=True)
            else:
                payload["options"] = options
        raw = await self.client.post(
            f"/datastores/{data_store_id}/esri/datasets/register",
            json=payload,
        )
        return EsriRegisterResponse(**raw)

    async def update_esri_dataset_schemas(
        self,
        data_store_id: int,
        force_update: bool = False,
    ) -> EsriSchemaUpdateResponse:
        raw = await self.client.put(
            f"/datastores/{data_store_id}/esri/datasets/schemas",
            json={"forceUpdate": force_update},
        )
        return EsriSchemaUpdateResponse(**raw)

    async def delete_all_esri_datasets(
        self,
        data_store_id: int,
        confirm: bool = False,
    ) -> EsriBulkDeleteResponse:
        params = {"confirm": "true"} if confirm else {}
        raw = await self.client.delete(
            f"/datastores/{data_store_id}/esri/datasets",
            params=params or None,
        )
        return EsriBulkDeleteResponse(**raw)

    async def get_esri_geodatabase_info(
        self,
        data_store_id: int,
    ) -> EsriGeodatabaseInfoResponse:
        raw = await self.client.get(f"/datastores/{data_store_id}/esri/info")
        return EsriGeodatabaseInfoResponse(**raw)
