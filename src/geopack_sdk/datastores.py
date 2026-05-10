from typing import Any, Dict, List, Optional


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

    def list(self) -> List[Dict[str, Any]]:
        """List all configured DataStores.

        REST API: `GET /api/datastores`

        Returns a list of DataStore objects (connection details excluded).
        Each object includes an enriched `capabilities` array derived from
        its adapter type.
        """
        return self.client.get("/datastores")

    def list_by_capabilities(
        self,
        purpose: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List DataStores filtered by capabilities / purpose.

        REST API: `GET /api/datastores/by-capabilities`

        Args:
            purpose: One of ``'dataset-creation'``, ``'workflow-output'``,
                     or ``None`` (returns all).

        Returns:
            ``{ success, data: [...], metadata: { purpose, count, retrievedAt } }``
        """
        params: Dict[str, Any] = {}
        if purpose:
            params["purpose"] = purpose
        return self.client.get("/datastores/by-capabilities", params=params or None)

    def get(self, data_store_id: int) -> Dict[str, Any]:
        """Get a single DataStore by ID.

        REST API: `GET /api/datastores/:id`

        Returns the DataStore object (connection details excluded).
        """
        return self.client.get(f"/datastores/{data_store_id}")

    def create(self, data_store_input: Dict[str, Any]) -> Dict[str, Any]:
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
            The created DataStore object (safe fields only).
        """
        return self.client.post("/datastores", json=data_store_input)

    def update(
        self,
        data_store_id: int,
        data_store_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an existing DataStore configuration.

        REST API: `PUT /api/datastores/:id`

        Args:
            data_store_id: ID of the DataStore to update.
            data_store_input: Partial dict with fields to update
                (name, description, type, status, organizationId,
                 connectionDetails, predefinedConnectionName).

        Returns:
            The updated DataStore object (safe fields only).
        """
        return self.client.put(f"/datastores/{data_store_id}", json=data_store_input)

    def delete(self, data_store_id: int) -> None:
        """Delete a DataStore configuration.

        REST API: `DELETE /api/datastores/:id`

        Raises if the DataStore has linked datasets (409) or if
        the user lacks permission (403).
        """
        self.client.delete(f"/datastores/{data_store_id}")

    # ── Connection Testing ────────────────────────────────────────────

    def test_connection(self, test_input: Dict[str, Any]) -> Dict[str, Any]:
        """Test a DataStore connection.

        REST API: `POST /api/datastores/test-connection`

        Args:
            test_input: Dict with one of:
                - dataStoreId (int): Test an existing DataStore
                - predefinedConnectionName (str): Test a predefined config
                - connectionDetails (dict) + type (str): Test raw details

        Returns:
            ``{ success: bool, message: str, capabilities?: object }``
        """
        return self.client.post("/datastores/test-connection", json=test_input)

    # ── Predefined Connections ────────────────────────────────────────

    def list_predefined(self) -> List[Dict[str, Any]]:
        """List predefined DataStore connection names and types from server config.

        REST API: `GET /api/config/predefined-datastores`

        Returns a list of ``{ connectionName, type, connectionDetails?: {...} }``.
        """
        return self.client.get("/config/predefined-datastores")

    # ── ACL ───────────────────────────────────────────────────────────

    def get_acls(self, data_store_id: int) -> List[Dict[str, Any]]:
        """Get Access Control List entries for a DataStore.

        REST API: `GET /api/datastores/:id/acl`
        """
        return self.client.get(f"/datastores/{data_store_id}/acl")

    def create_acls(
        self,
        data_store_id: int,
        principals: List[Dict[str, Any]],
        permissions: List[str],
        effect: str = "Allow",
    ) -> List[Dict[str, Any]]:
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
        return self.client.post(f"/datastores/{data_store_id}/acl", json=payload)

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
    ) -> Dict[str, Any]:
        """Discover available datasets in an ESRI Geodatabase DataStore.

        REST API: `GET /api/datastores/:id/esri/datasets`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            include_hidden: Include hidden datasets.
            dataset_type: Filter by type (``'FeatureClass'`` or ``'Table'``).

        Returns:
            ``{ success, data: [...EsriDataset], metadata: { count, datastoreId } }``
        """
        params: Dict[str, Any] = {}
        if include_hidden:
            params["includeHidden"] = "true"
        if dataset_type:
            params["type"] = dataset_type
        return self.client.get(
            f"/datastores/{data_store_id}/esri/datasets",
            params=params or None,
        )

    def register_esri_datasets(
        self,
        data_store_id: int,
        workgroup_id: int,
        dataset_names: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register ESRI datasets from a geodatabase.

        REST API: `POST /api/datastores/:id/esri/datasets/register`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            workgroup_id: Workgroup to assign datasets to.
            dataset_names: Specific dataset names to register (None = register all).
            options: Extra options, e.g. ``{ updateExisting: True }``.

        Returns:
            ``{ success, data: { registered, updated, errors }, metadata }``
        """
        payload: Dict[str, Any] = {"workgroupId": workgroup_id}
        if dataset_names is not None:
            payload["datasetNames"] = dataset_names
        if options is not None:
            payload["options"] = options
        return self.client.post(
            f"/datastores/{data_store_id}/esri/datasets/register",
            json=payload,
        )

    def update_esri_dataset_schemas(
        self,
        data_store_id: int,
        force_update: bool = False,
    ) -> Dict[str, Any]:
        """Update all ESRI dataset schemas from the geodatabase.

        REST API: `PUT /api/datastores/:id/esri/datasets/schemas`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            force_update: Force schema update even if unchanged.

        Returns:
            ``{ success, data: { updated, unchanged, failed }, metadata }``
        """
        return self.client.put(
            f"/datastores/{data_store_id}/esri/datasets/schemas",
            json={"forceUpdate": force_update},
        )

    def delete_all_esri_datasets(
        self,
        data_store_id: int,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Delete all ESRI datasets from a DataStore.

        REST API: `DELETE /api/datastores/:id/esri/datasets`

        Args:
            data_store_id: ID of the ESRI Geodatabase DataStore.
            confirm: Must be ``True`` to execute the bulk delete.

        Returns:
            ``{ success, data: { deleted, failed }, metadata }``
        """
        params = {"confirm": "true"} if confirm else {}
        return self.client.delete(
            f"/datastores/{data_store_id}/esri/datasets",
            params=params or None,
        )

    def get_esri_geodatabase_info(
        self,
        data_store_id: int,
    ) -> Dict[str, Any]:
        """Get ESRI geodatabase information (real-time).

        REST API: `GET /api/datastores/:id/esri/info`

        Returns:
            ``{ success, data: { datastore, geodatabase }, metadata }``
        """
        return self.client.get(f"/datastores/{data_store_id}/esri/info")
