from typing import Any, Dict, List, Optional, Literal, Union

from .models import (
    DataStoreResponse,
    DataStoreListResponse,
    TestConnectionResponse,
    PredefinedDataStore,
    DataStoreAclEntry,
    EsriDiscoverResponse,
    EsriRegisterResponse,
    EsriRegisterOptions,
    EsriSchemaUpdateResponse,
    EsriBulkDeleteResponse,
    EsriGeodatabaseInfoResponse,
)


def parse_datastore_list_response(response_data: Any) -> DataStoreListResponse:
    """Normalize GET /datastores (and similar) payloads into DataStoreListResponse.

    The API may return a bare JSON array or an object with a ``datastores`` field.
    """
    if isinstance(response_data, list):
        datastores = [DataStoreResponse(**d) for d in response_data]
        return DataStoreListResponse(datastores=datastores, totalCount=len(datastores))
    return DataStoreListResponse(**response_data)


class DataStoreManager:
    """Manages DataStore resources via the Geopack REST API.

    DataStores represent connections to spatial databases (PostgreSQL/PostGIS,
    MS SQL Server, GeoPackage, MBTiles, ESRI Geodatabase, etc.).

    Endpoints:
        GET    /datastores                          — List all datastores
        GET    /datastores/by-capabilities           — List by purpose
        GET    /datastores/:id                       — Get by ID
        POST   /datastores                           — Create
        PUT    /datastores/:id                       — Update
        DELETE /datastores/:id                       — Delete
        POST   /datastores/test-connection           — Test connection
        GET    /config/predefined-datastores         — Predefined connections
        GET    /datastores/:id/acl                   — Get ACLs
        POST   /datastores/:id/acl                   — Create ACLs
        DELETE /datastores/:id/acl/:aclId            — Delete ACL
        GET    /datastores/:id/esri/datasets         — Discover ESRI datasets
        POST   /datastores/:id/esri/datasets/register — Register ESRI datasets
        PUT    /datastores/:id/esri/datasets/schemas — Update ESRI schemas
        DELETE /datastores/:id/esri/datasets         — Delete all ESRI datasets
        GET    /datastores/:id/esri/info             — ESRI geodatabase info
    """

    def __init__(self, client):
        self.client = client

    # ── CRUD ──────────────────────────────────────────────────────────

    def list(self) -> DataStoreListResponse:
        """List all configured DataStores with type-safe response.

        REST API: `GET /api/datastores`

        Returns a list of DataStore objects (connection details excluded).
        Each object includes an enriched `capabilities` array derived from
        its adapter type.

        Returns:
            DataStoreListResponse: Validated response with datastores list
        """
        response_data = self.client.get("/datastores")
        return parse_datastore_list_response(response_data)

    def list_by_capabilities(
        self,
        purpose: Optional[Literal['dataset-creation', 'workflow-output']] = None,
    ) -> DataStoreListResponse:
        """List DataStores filtered by capabilities / purpose.

        REST API: `GET /api/datastores/by-capabilities`

        Args:
            purpose: One of ``'dataset-creation'``, ``'workflow-output'``,
                     or ``None`` (returns all).

        Returns:
            DataStoreListResponse: Validated response with filtered datastores list
        """
        params: Dict[str, Any] = {}
        if purpose:
            params["purpose"] = purpose
        response_data = self.client.get("/datastores/by-capabilities", params=params or None)
        
        # Handle both formats: direct array or { success, data, metadata }
        data = response_data
        if isinstance(response_data, dict):
            if 'data' in response_data:
                data = response_data['data']
            elif 'datastores' in response_data:
                return DataStoreListResponse(**response_data)
        
        if isinstance(data, list):
            datastores = [DataStoreResponse(**d) for d in data]
            return DataStoreListResponse(datastores=datastores, totalCount=len(datastores))
            
        return DataStoreListResponse(**response_data)

    def get(self, data_store_id: int) -> DataStoreResponse:
        """Get a single DataStore by ID with type-safe response.

        REST API: `GET /api/datastores/:id`

        Args:
            data_store_id: ID of the DataStore to fetch

        Returns:
            DataStoreResponse: Validated DataStore model
        """
        response_data = self.client.get(f"/datastores/{data_store_id}")
        return DataStoreResponse(**response_data)

    def create(self, data_store_input: Dict[str, Any]) -> DataStoreResponse:
        """Create a new DataStore configuration.

        REST API: `POST /api/datastores`

        Args:
            data_store_input: Dict with keys:
                - name (str): DataStore name (optional if predefinedConnectionName used)
                - type (str): Adapter type, e.g. ``'postgres'``, ``'mssql'``, ``'gpkg'``
                - description (str, optional)
                - organizationId (int, optional — defaults to user's org)
                - connectionDetails (dict, optional): Raw connection params
                - predefinedConnectionName (str, optional): Name from server config
                - options (dict, optional): Extra options (e.g. autoRegisterDatasets for ESRI)

        Returns:
            DataStoreResponse: The created DataStore object.
        """
        response_data = self.client.post("/datastores", json=data_store_input)
        return DataStoreResponse(**response_data)

    def update(
        self,
        data_store_id: int,
        data_store_input: Dict[str, Any],
    ) -> DataStoreResponse:
        """Update an existing DataStore configuration.

        REST API: `PUT /api/datastores/:id`

        Args:
            data_store_id: ID of the DataStore to update.
            data_store_input: Partial dict with fields to update
                (name, description, type, status, organizationId,
                 connectionDetails, predefinedConnectionName).

        Returns:
            DataStoreResponse: The updated DataStore object.
        """
        response_data = self.client.put(f"/datastores/{data_store_id}", json=data_store_input)
        return DataStoreResponse(**response_data)

    def delete(self, data_store_id: int) -> None:
        """Delete a DataStore configuration.

        REST API: `DELETE /api/datastores/:id`

        Raises if the DataStore has linked datasets (409) or if
        the user lacks permission (403).
        """
        self.client.delete(f"/datastores/{data_store_id}")

    # ── Connection Testing ────────────────────────────────────────────

    def test_connection(self, test_input: Dict[str, Any]) -> TestConnectionResponse:
        """Test a DataStore connection with type-safe response.

        REST API: `POST /api/datastores/test-connection`

        Args:
            test_input: Dict with one of:
                - dataStoreId (int): Test an existing DataStore
                - predefinedConnectionName (str): Test a predefined config
                - connectionDetails (dict) + type (str): Test raw details

        Returns:
            TestConnectionResponse: Validated response with success status
        """
        response_data = self.client.post("/datastores/test-connection", json=test_input)
        return TestConnectionResponse(**response_data)

    # ── Predefined Connections ────────────────────────────────────────

    def list_predefined(self) -> List[PredefinedDataStore]:
        """List predefined DataStore connection names and types from server config with type-safe response.

        REST API: `GET /api/config/predefined-datastores`

        Returns:
            List[PredefinedDataStore]: Validated list of predefined connections
        """
        response_data = self.client.get("/config/predefined-datastores")
        if isinstance(response_data, list):
            return [PredefinedDataStore(**d) for d in response_data]
        return []

    # ── ACL ───────────────────────────────────────────────────────────

    def get_acls(self, data_store_id: int) -> List[DataStoreAclEntry]:
        """Get Access Control List entries for a DataStore.

        REST API: `GET /api/datastores/:id/acl`
        """
        response_data = self.client.get(f"/datastores/{data_store_id}/acl")
        if isinstance(response_data, list):
            return [DataStoreAclEntry(**d) for d in response_data]
        return []

    def create_acls(
        self,
        data_store_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[DataStoreAclEntry]:
        """Create or update ACL entries for a DataStore.

        REST API: `POST /api/datastores/:id/acl`

        Args:
            data_store_id: Target DataStore ID.
            principals: List of ``{ principalType: 'USER'|'GROUP', principalId: int }``.
            permissions: List of permission name strings.
            effect: ``'Allow'`` or ``'Deny'``.

        Returns:
            List of created/updated ACL entries with principal details.
        """
        payload = {
            "principals": principals,
            "permissions": permissions,
            "effect": effect,
        }
        response_data = self.client.post(f"/datastores/{data_store_id}/acl", json=payload)
        if isinstance(response_data, list):
            return [DataStoreAclEntry(**d) for d in response_data]
        return []

    def delete_acl(self, data_store_id: int, acl_id: int) -> None:
        """Delete a specific ACL entry for a DataStore.

        REST API: `DELETE /api/datastores/:id/acl/:aclId`
        """
        self.client.delete(f"/datastores/{data_store_id}/acl/{acl_id}")

    # ── ESRI Geodatabase ──────────────────────────────────────────────

    def discover_esri_datasets(
        self,
        data_store_id: int,
        include_hidden: bool = False,
        dataset_type: Optional[str] = None,
    ) -> EsriDiscoverResponse:
        """Discover available datasets in an ESRI Geodatabase DataStore.

        REST API: `GET /api/datastores/:id/esri/datasets`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            include_hidden: Include hidden datasets.
            dataset_type: Filter by type (``'FeatureClass'`` or ``'Table'``).

        Returns:
            :class:`EsriDiscoverResponse` with ``data`` as discovered datasets
            (``name``, ``type``, ``physicalName``, ``geometryType``, etc.).
        """
        params: Dict[str, Any] = {}
        if include_hidden:
            params["includeHidden"] = "true"
        if dataset_type:
            params["type"] = dataset_type
        raw = self.client.get(
            f"/datastores/{data_store_id}/esri/datasets",
            params=params or None,
        )
        return EsriDiscoverResponse(**raw)

    def register_esri_datasets(
        self,
        data_store_id: int,
        workgroup_id: int,
        dataset_names: Optional[List[str]] = None,
        options: Optional[Union[EsriRegisterOptions, Dict[str, Any]]] = None,
    ) -> EsriRegisterResponse:
        """Register ESRI datasets from a geodatabase.

        REST API: `POST /api/datastores/:id/esri/datasets/register`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            workgroup_id: Workgroup to assign datasets to.
            dataset_names: Specific dataset names to register (None = register all).
            options: Registration options (``updateExisting``, etc.).

        Returns:
            :class:`EsriRegisterResponse` with ``data.registered``, ``updated``,
            ``skipped``, and ``errors`` lists.
        """
        payload: Dict[str, Any] = {"workgroupId": workgroup_id}
        if dataset_names is not None:
            payload["datasetNames"] = dataset_names
        if options is not None:
            if isinstance(options, EsriRegisterOptions):
                payload["options"] = options.model_dump(exclude_none=True)
            else:
                payload["options"] = options
        raw = self.client.post(
            f"/datastores/{data_store_id}/esri/datasets/register",
            json=payload,
        )
        return EsriRegisterResponse(**raw)

    def update_esri_dataset_schemas(
        self,
        data_store_id: int,
        force_update: bool = False,
    ) -> EsriSchemaUpdateResponse:
        """Update all ESRI dataset schemas from the geodatabase.

        REST API: `PUT /api/datastores/:id/esri/datasets/schemas`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            force_update: Force schema update even if unchanged.

        Returns:
            :class:`EsriSchemaUpdateResponse` with ``updated``, ``unchanged``,
            and ``failed`` lists.
        """
        raw = self.client.put(
            f"/datastores/{data_store_id}/esri/datasets/schemas",
            json={"forceUpdate": force_update},
        )
        return EsriSchemaUpdateResponse(**raw)

    def delete_all_esri_datasets(
        self,
        data_store_id: int,
        confirm: bool = False,
    ) -> EsriBulkDeleteResponse:
        """Delete all ESRI datasets from a DataStore.

        REST API: `DELETE /api/datastores/:id/esri/datasets`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            confirm: Must be ``True`` to execute the bulk delete.

        Returns:
            :class:`EsriBulkDeleteResponse` with ``deleted`` and ``failed`` lists.
        """
        params = {"confirm": "true"} if confirm else {}
        raw = self.client.delete(
            f"/datastores/{data_store_id}/esri/datasets",
            params=params or None,
        )
        return EsriBulkDeleteResponse(**raw)

    def get_esri_geodatabase_info(
        self,
        data_store_id: int,
    ) -> EsriGeodatabaseInfoResponse:
        """Get ESRI geodatabase information (real-time).

        REST API: `GET /api/datastores/:id/esri/info`

        Returns:
            :class:`EsriGeodatabaseInfoResponse` with portal ``datastore`` summary
            and adapter ``geodatabase`` statistics.
        """
        raw = self.client.get(f"/datastores/{data_store_id}/esri/info")
        return EsriGeodatabaseInfoResponse(**raw)
