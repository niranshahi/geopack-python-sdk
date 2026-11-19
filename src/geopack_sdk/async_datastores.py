"""Async datastore manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union

from .datastores import _unwrap_success, parse_datastore_list_response
from .models import (
    DataStoreAclEntry,
    DataStoreListResponse,
    DataStoreResponse,
    EsriDiscoverResponse,
    EsriGeodatabaseInfoResponse,
    EsriRegisterOptions,
    EsriRegisterResponse,
    EsriSchemaUpdateResponse,
    EsriBulkDeleteResponse,
    PredefinedDataStore,
    TestConnectionResponse,
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

    # ── CRUD, connection testing and ACLs (slice 016 P4a) ─────────────

    async def list_by_capabilities(
        self,
        purpose: Optional[Literal['dataset-creation', 'workflow-output']] = None,
    ) -> DataStoreListResponse:
        """Async twin of :meth:`DataStoreManager.list_by_capabilities`."""
        params: Dict[str, Any] = {}
        if purpose:
            params["purpose"] = purpose
        response_data = await self.client.get(
            "/datastores/by-capabilities", params=params or None
        )
        data = response_data
        if isinstance(response_data, dict):
            if "data" in response_data:
                data = response_data["data"]
            elif "datastores" in response_data:
                return DataStoreListResponse(**response_data)
        if isinstance(data, list):
            datastores = [DataStoreResponse(**d) for d in data]
            return DataStoreListResponse(datastores=datastores, totalCount=len(datastores))
        return DataStoreListResponse(**response_data)

    async def create(self, data_store_input: Dict[str, Any]) -> DataStoreResponse:
        """Async twin of :meth:`DataStoreManager.create`."""
        response_data = await self.client.post("/datastores", json=data_store_input)
        return DataStoreResponse(**response_data)

    async def update(
        self,
        data_store_id: int,
        data_store_input: Dict[str, Any],
    ) -> DataStoreResponse:
        """Async twin of :meth:`DataStoreManager.update`."""
        response_data = await self.client.put(
            f"/datastores/{data_store_id}", json=data_store_input
        )
        return DataStoreResponse(**response_data)

    async def delete(self, data_store_id: int) -> None:
        """Async twin of :meth:`DataStoreManager.delete`."""
        await self.client.delete(f"/datastores/{data_store_id}")

    async def test_connection(
        self, test_input: Dict[str, Any]
    ) -> TestConnectionResponse:
        """Async twin of :meth:`DataStoreManager.test_connection`."""
        response_data = await self.client.post(
            "/datastores/test-connection", json=test_input
        )
        return TestConnectionResponse(**response_data)

    async def list_predefined(self) -> List[PredefinedDataStore]:
        """Async twin of :meth:`DataStoreManager.list_predefined`."""
        response_data = await self.client.get("/config/predefined-datastores")
        if isinstance(response_data, list):
            return [PredefinedDataStore(**d) for d in response_data]
        return []

    async def get_acls(self, data_store_id: int) -> List[DataStoreAclEntry]:
        """Async twin of :meth:`DataStoreManager.get_acls`."""
        response_data = await self.client.get(f"/datastores/{data_store_id}/acl")
        if isinstance(response_data, list):
            return [DataStoreAclEntry(**d) for d in response_data]
        return []

    async def create_acls(
        self,
        data_store_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[DataStoreAclEntry]:
        """Async twin of :meth:`DataStoreManager.create_acls`."""
        payload = {
            "principals": principals,
            "permissions": permissions,
            "effect": effect,
        }
        response_data = await self.client.post(
            f"/datastores/{data_store_id}/acl", json=payload
        )
        if isinstance(response_data, list):
            return [DataStoreAclEntry(**d) for d in response_data]
        return []

    async def delete_acl(self, data_store_id: int, acl_id: int) -> None:
        """Async twin of :meth:`DataStoreManager.delete_acl`."""
        await self.client.delete(f"/datastores/{data_store_id}/acl/{acl_id}")

    # ── Authored (logical) relationships ──────────────────────────────

    async def get_relationships(self, datastore_id: int) -> Dict[str, Any]:
        """Async twin of :meth:`DataStoreManager.get_relationships`."""
        response_data = await self.client.get(
            f"/datastores/{datastore_id}/relationships"
        )
        return _unwrap_success(response_data)

    async def create_relationship(
        self, datastore_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Async twin of :meth:`DataStoreManager.create_relationship`."""
        response_data = await self.client.post(
            f"/datastores/{datastore_id}/relationships", json=payload
        )
        return _unwrap_success(response_data)

    async def update_relationship(
        self,
        datastore_id: int,
        relationship_uuid: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Async twin of :meth:`DataStoreManager.update_relationship`."""
        response_data = await self.client.put(
            f"/datastores/{datastore_id}/relationships/{relationship_uuid}",
            json=payload,
        )
        return _unwrap_success(response_data)

    async def delete_relationship(
        self, datastore_id: int, relationship_uuid: str
    ) -> Dict[str, Any]:
        """Async twin of :meth:`DataStoreManager.delete_relationship`."""
        response_data = await self.client.delete(
            f"/datastores/{datastore_id}/relationships/{relationship_uuid}"
        )
        return _unwrap_success(response_data)

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
