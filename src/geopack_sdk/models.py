"""
Geopack Python SDK - Pydantic Models

This module contains all Pydantic BaseModel definitions for type-safe API responses
and request payloads. These models provide:
- Runtime validation
- IDE autocompletion
- JSON schema generation (for MCP integration)
- Better error handling

Usage:
    from geopack_sdk.models import Dataset, DatasetsApiResponse
    
    response: DatasetsApiResponse = client.datasets.list()
    for dataset in response.datasets:
        print(dataset.name)  # IDE knows 'name' is str
"""

import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, ConfigDict, ValidationError, field_validator, model_validator

from .dataset_payload import normalize_dataset_dict


# ============================================================================
# --- NESTED / SHARED MODELS ---
# ============================================================================

class Principal(BaseModel):
    """Represents a User or Group principal"""
    id: int
    userName: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    isActive: bool = True
    
    model_config = ConfigDict(extra='allow')  # Forward compatibility


class DataStore(BaseModel):
    """Represents a DataStore (data source)"""
    id: int
    name: str
    type: str  # 'postgresql', 'mssql', 'filesystem', 'gpkg', 'mbtiles'
    predefinedConnectionName: Optional[str] = None
    
    model_config = ConfigDict(extra='allow')


class Workgroup(BaseModel):
    """Represents a Workgroup"""
    id: int
    name: str
    
    model_config = ConfigDict(extra='allow')


class Organization(BaseModel):
    """Represents an Organization"""
    id: int
    name: str
    
    model_config = ConfigDict(extra='allow')


# ============================================================================
# --- DATASET MODELS ---
# ============================================================================

class Dataset(BaseModel):
    """Complete Dataset entity with all associated data.

    The portal stores ``dataType`` as a free string (the column is
    ``STRING(50)`` with no CHECK) and exposes rows this SDK does not author —
    notably ``dataType="service"`` (an external-service dataset) and rows with
    ``dataStoreId`` / ``ownerUserId`` / ``workgroupId`` null. Those are NOT
    parse failures: a strict ``Literal`` here made a single service row reject
    the whole page (live-QA 2026-11-21, ``list_datasets`` with no ``data_type``
    filter). Keep the identity fields optional and the enumerations advisory.
    """
    id: int
    name: str
    description: Optional[str] = None
    #: Advisory, not a closed enum: vector | table | raster | service | ...
    dataType: Optional[str] = None
    subType: Optional[str] = None
    keywords: Optional[str] = None

    # Identity fields (nullable for service / virtual rows)
    ownerUserId: Optional[int] = None
    workgroupId: Optional[int] = None
    dataStoreId: Optional[int] = None

    # Metadata - details can be JSON string or dict
    details: Optional[Union[str, Dict[str, Any]]] = None
    status: str = 'active'

    # Timestamps
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    # Optional associations (populated by API when requested)
    owner: Optional[Principal] = None
    workgroup: Optional[Workgroup] = None
    dataStore: Optional[DataStore] = None
    
    # Thumbnail metadata (BLOB never included in list/get JSON)
    hasThumbnail: Optional[bool] = None
    thumbnailApiPath: Optional[str] = Field(
        default=None,
        description="Relative GET path for thumbnail bytes, e.g. /datasets/42/thumbnail (Bearer or signed URL)",
    )
    thumbnailMintPath: Optional[str] = Field(
        default=None,
        description="Relative mint path (Bearer only), e.g. /datasets/42/thumbnail/access-url",
    )
    thumbnailResourceUri: Optional[str] = Field(
        default=None,
        description="MCP resource URI, e.g. dataset://42/thumbnail — use resources/read in MCP hosts",
    )

    model_config = ConfigDict(
        extra='allow',  # Allow additional fields for forward compatibility
        from_attributes=True  # Allow population from ORM models
    )

    @model_validator(mode='before')
    @classmethod
    def strip_thumbnail_blob(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return normalize_dataset_dict(data)
        return data

    @field_validator('dataType', 'subType', 'status', 'description', 'keywords', mode='before')
    @classmethod
    def _coerce_text_field(cls, value: Any) -> Any:
        """A numerified/misspelled enum must not reject the record."""
        return None if value is None else str(value)

    @field_validator('ownerUserId', 'workgroupId', 'dataStoreId', mode='before')
    @classmethod
    def _coerce_optional_int(cls, value: Any) -> Any:
        """API sends ``null`` for service rows; a numeric string is accepted."""
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    
    @property
    def keywords_array(self) -> List[str]:
        """Helper property to split keywords string into array"""
        if not self.keywords:
            return []
        return [k.strip() for k in self.keywords.split(';') if k.strip()]
    
    @property
    def parsed_details(self) -> Dict[str, Any]:
        """Helper property to parse details if it's a JSON string"""
        if isinstance(self.details, dict):
            return self.details
        if isinstance(self.details, str):
            try:
                import json
                return json.loads(self.details)
            except json.JSONDecodeError:
                return {}
        return {}


def _repair_dataset_item(raw: Any) -> Any:
    """Return one list item that is guaranteed to validate as :class:`Dataset`.

    The portal can add a row shape this SDK has never seen. The list lane must
    never let that reject the whole page (live-QA 2026-11-21): the offending
    record is degraded to its identity fields, flagged ``validationDegraded``
    and its untouched payload is kept under ``rawRecord`` — never dropped.
    """
    if not isinstance(raw, dict):
        return raw
    try:
        Dataset.model_validate(raw)
        return raw
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg')}"
            for err in exc.errors()[:5]
        ]
        # Keep the untouched payload beside the degraded shell — never drop it.
        degraded: Dict[str, Any] = {
            "validationDegraded": True,
            "validationErrors": errors,
            "rawRecord": dict(raw),
        }
        try:
            degraded["id"] = int(raw.get("id"))
        except (TypeError, ValueError):
            degraded["id"] = -1
        name = raw.get("name")
        degraded["name"] = name if isinstance(name, str) and name else str(name or "unknown")
        # Only carry values whose declared type this model can accept.
        for key in ("description", "dataType", "subType", "keywords", "status"):
            if isinstance(raw.get(key), str):
                degraded[key] = raw[key]
        if isinstance(raw.get("details"), (str, dict)):
            degraded["details"] = raw["details"]
        for key in ("ownerUserId", "workgroupId", "dataStoreId"):
            if raw.get(key) is not None:
                try:
                    degraded[key] = int(raw[key])
                except (TypeError, ValueError):
                    pass
        if raw.get("hasThumbnail") is not None:
            degraded["hasThumbnail"] = bool(raw["hasThumbnail"])
        for key in ("thumbnailApiPath", "thumbnailMintPath", "thumbnailResourceUri"):
            if isinstance(raw.get(key), str):
                degraded[key] = raw[key]

        try:
            Dataset.model_validate(degraded)
            return degraded
        except ValidationError:
            # Absolute floor: identity only (these two fields always validate).
            return {
                "id": degraded["id"],
                "name": degraded["name"],
                "validationDegraded": True,
                "validationErrors": errors,
                "rawRecord": dict(raw),
            }


class CreateDatasetDto(BaseModel):
    """DTO for creating a new dataset"""
    name: str = Field(..., min_length=1, description="Dataset name")
    description: Optional[str] = None
    dataType: Literal['vector', 'table', 'raster']
    workgroupId: int = Field(..., description="Target workgroup ID")
    dataStoreId: int = Field(..., description="Target datastore ID")
    details: Optional[Dict[str, Any]] = None
    keywords: Optional[str] = None


class UpdateDatasetDto(BaseModel):
    """DTO for updating an existing dataset"""
    name: Optional[str] = None
    description: Optional[str] = None
    dataType: Optional[Literal['vector', 'table', 'raster']] = None
    details: Optional[Dict[str, Any]] = None
    keywords: Optional[str] = None


class DatasetField(BaseModel):
    """Field definition within a Dataset"""
    name: str = Field(..., description="Field name in database")
    type: str = Field(..., description="SQL type (varchar, integer, geometry, etc.)")
    alias: Optional[str] = None
    length: Optional[int] = None
    scale: Optional[int] = None
    precision: Optional[int] = None
    default: Optional[Any] = None
    notNull: Optional[bool] = None
    isPrimaryKey: Optional[bool] = None
    hidden: Optional[bool] = None
    readonly: Optional[bool] = None


# ============================================================================
# --- FILTER & STATISTICS MODELS ---
# ============================================================================

class FilterOption(BaseModel):
    """A single option in a filter list"""
    id: int
    name: Optional[str] = None  # API may use userName instead
    userName: Optional[str] = None  # Alternative field name used by API
    count: int


class DataTypeOption(BaseModel):
    """Data type filter option (vector, raster, table)"""
    name: str
    count: int


class FilterStatistics(BaseModel):
    """Complete filter statistics for dataset discovery"""
    organizations: List[FilterOption] = Field(default_factory=list)
    owners: List[FilterOption] = Field(default_factory=list)
    workgroups: List[FilterOption] = Field(default_factory=list)
    dataStores: List[FilterOption] = Field(default_factory=list)
    subTypes: List[DataTypeOption] = Field(default_factory=list)
    dataTypes: List[DataTypeOption] = Field(default_factory=list)
    keywords: List[DataTypeOption] = Field(default_factory=list)
    dateRange: Optional[Dict[str, Optional[str]]] = None


class DatasetTimeSeriesPoint(BaseModel):
    """Single point in time-series dataset statistics"""
    date: str
    vector: int = 0
    raster: int = 0
    table: int = 0
    total: int = 0


class DatasetStatsByStore(BaseModel):
    """Dataset composition by datastore"""
    storeType: str
    vector: int = 0
    raster: int = 0
    table: int = 0
    total: int = 0


class DatasetStatsByGeomType(BaseModel):
    """Dataset statistics by geometry type"""
    geomType: str
    count: int = 0


# ============================================================================
# --- GEOJSON MODELS ---
# ============================================================================

class Geometry(BaseModel):
    """GeoJSON Geometry object"""
    type: str  # 'Point', 'LineString', 'Polygon', 'MultiPoint', etc.
    coordinates: Any  # Structure depends on geometry type


class Feature(BaseModel):
    """GeoJSON Feature object"""
    type: Literal['Feature'] = 'Feature'
    id: Optional[int | str] = None
    geometry: Optional[Geometry] = None
    properties: Optional[Dict[str, Any]] = None


class FeatureCollection(BaseModel):
    """GeoJSON FeatureCollection"""
    type: Literal['FeatureCollection'] = 'FeatureCollection'
    features: List[Feature] = Field(default_factory=list)
    crs: Optional[Dict[str, Any]] = None
    
    @property
    def feature_count(self) -> int:
        """Helper to get feature count"""
        return len(self.features)


# ============================================================================
# --- QUERY LANE MODELS (slice 010) ---
# ============================================================================
#
# The envelopes below are ``extra="allow"`` on purpose: a server field addition
# must never break an installed client.


class PagePagination(BaseModel):
    """Page envelope returned by ``POST /datasets/{id}/query/paged``."""

    page: int = 1
    page_size: Optional[int] = Field(default=None, alias="pageSize")
    total_count: Optional[int] = Field(default=None, alias="totalCount")
    total_pages: Optional[int] = Field(default=None, alias="totalPages")
    has_next_page: bool = Field(default=False, alias="hasNextPage")
    has_previous_page: bool = Field(default=False, alias="hasPreviousPage")

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @property
    def is_count_degraded(self) -> bool:
        """True when the server skipped the COUNT (``totalCount`` is null).

        This is a documented 200 answer (100k rows or a 15 s count timeout),
        never a failure: callers must not treat it as an error.
        """
        return self.total_count is None


class PagedFeatureCollection(BaseModel):
    """One page of features plus the scope metadata a caller uses as proof."""

    features: List[Dict[str, Any]] = Field(default_factory=list)
    pagination: PagePagination = Field(default_factory=PagePagination)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    crs: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")

    @property
    def feature_count(self) -> int:
        return len(self.features)


class AggregateColumn(BaseModel):
    """Column descriptor from ``POST /datasets/{id}/query/aggregate``."""

    type: Optional[str] = None
    field: Optional[str] = None
    key: Optional[str] = None
    source_alias: Optional[str] = Field(default=None, alias="sourceAlias")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class AggregateResult(BaseModel):
    """Buckets only: the aggregate lane never returns rows or geometry."""

    dataset_id: Optional[int] = Field(default=None, alias="datasetId")
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[AggregateColumn] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class MintedUrl(BaseModel):
    """A capability URL — it grants read access until ``expires_at``.

    Treat it like a credential: do not log it and do not reuse it against a
    different dataset.
    """

    url: str
    expires_at: Optional[str] = Field(default=None, alias="expiresAt")
    media_query: Optional[str] = Field(default=None, alias="mediaQuery")

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @property
    def expires_at_datetime(self) -> Optional[datetime]:
        """``expires_at`` as an aware datetime (``None`` when absent/invalid)."""
        if not self.expires_at:
            return None
        try:
            return datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return None


# ============================================================================
# --- RELATIONSHIP / SCHEMA MODELS (slice 011) ---
# ============================================================================


class RelationshipDescriptor(BaseModel):
    """One provider-neutral relationship from ``GET /datasets/{id}/relationships``.

    ``raw`` keeps the whole catalog entry: a provider field addition must not
    break an installed client (slice 011 maintenance note). ``read_only`` is
    surfaced, never hidden — ESRI relationships are navigable but not editable.
    """

    name: Optional[str] = None
    relationship_name: Optional[str] = Field(default=None, alias="relationshipName")
    direction: Optional[str] = None
    read_only: bool = Field(default=False, alias="readOnly")
    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _fill_name_and_raw(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        inner = dict(data)
        if not inner.get("name"):
            inner["name"] = inner.get("relationshipName")
        if not inner.get("relationshipName"):
            inner["relationshipName"] = inner.get("name")
        # Snapshot AFTER the name fill (callers read raw["name"]) but BEFORE the
        # assignment: inserting the dict into itself makes the model undumpable
        # (pydantic: "Circular reference detected").
        if not isinstance(inner.get("raw"), dict):
            inner["raw"] = dict(inner)
        return inner


class RelatedRecordsResult(BaseModel):
    """Target records for one relationship hop.

    ``features`` carries ONLY the related (target) records: the source leg is
    stripped server-side. ``__jct__*`` properties are junction fields — keep
    them as-is and do not fuse them into the target record. With several
    ``originObjectIds`` the response is grouped per source record under
    ``metadata.groups`` (``{sourceOid: [targetOid, ...]}``); the SDK never
    synthesizes a flat collection across origins.
    """

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    crs: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")

    @property
    def groups(self) -> Dict[str, List[Any]]:
        """``metadata.groups`` lifted for convenience (empty for one origin)."""
        groups = self.metadata.get("groups")
        return groups if isinstance(groups, dict) else {}

    @property
    def count_hint(self) -> Optional[int]:
        """``metadata.count`` when the server reported one."""
        count = self.metadata.get("count")
        return count if isinstance(count, int) else None


class SchemaPreviewSchema(BaseModel):
    """Composed schema of an ephemeral relationship layer."""

    fields: List[Dict[str, Any]] = Field(default_factory=list)
    geometry_type: Optional[str] = Field(default=None, alias="geometryType")
    oid_field: Optional[str] = Field(default=None, alias="oidField")
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    data_type: Optional[str] = Field(default=None, alias="dataType")
    title: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SchemaPreview(BaseModel):
    """``POST /datasets/{id}/schema-preview`` answer, returned verbatim.

    The wire key is literally ``schema``; the field is declared as
    ``schema_fields`` (alias ``schema``) because a field named ``schema``
    shadows ``BaseModel.schema`` and makes pydantic emit a ``UserWarning`` on
    import. Read it through the ``schema`` property; dumping by alias still
    emits ``schema``.
    """

    success: bool = True
    schema_fields: Optional[SchemaPreviewSchema] = Field(
        default=None, alias="schema", serialization_alias="schema"
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @property
    def schema(self) -> Optional[SchemaPreviewSchema]:
        """The composed schema (wire key ``schema``)."""
        return self.schema_fields


class ColumnBounds(BaseModel):
    """Thin wrapper over ``{success, data}`` from the live column-bounds lane.

    The values come from the LIVE store (``getLiveColumnMetaService``), so they
    can legitimately differ from the cached dataset ``details``.
    """

    success: bool = True
    data: Any = None
    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _capture_raw(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = dict(data)
            raw.setdefault("raw", raw)
            return raw
        return data


# ============================================================================
# --- TASK MODELS ---
# ============================================================================

class TaskResult(BaseModel):
    """Result of a background task execution or detailed Task object"""
    taskId: str  # UUID
    taskType: Optional[str] = None
    status: Literal['pending', 'processing', 'completed', 'failed', 'canceled', 'partial_success']
    priority: int = 10
    progress: Optional[Any] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    inputParameters: Dict[str, Any] = Field(default_factory=dict)
    results: Optional[Any] = None
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    userId: Optional[int] = None
    workgroupId: Optional[int] = None
    owner: Optional[Principal] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    # Compatibility aliases
    id: Optional[str] = None
    message: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra='allow')
    
    @property
    def task_id(self) -> str:
        """Helper to get task ID"""
        return self.taskId


class TaskListResponse(BaseModel):
    """Response from GET /api/tasks (paginated list for the current user)."""

    totalItems: int
    totalPages: int
    currentPage: int
    pageSize: int
    tasks: List[TaskResult] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ActiveTasksSummary(BaseModel):
    """Response from GET /api/tasks/summary (pending + processing counts)."""

    pending: int = 0
    processing: int = 0

    model_config = ConfigDict(extra="allow")


# ============================================================================
# --- WORKFLOW MODELS ---
# ============================================================================

class WorkflowParameter(BaseModel):
    """Parameter definition in a workflow"""
    key: str
    type: Literal['string', 'number', 'dataset', 'dataset-field', 'geometry']
    description: Optional[str] = None
    default: Optional[Any] = None
    required: bool = False
    runVisibility: Literal['editable', 'hidden', 'readonly'] = 'editable'
    dataType: Optional[str] = None  # For dataset-selector
    geometryType: Optional[str] = None  # For geom-param
    multiple: bool = False


class Workflow(BaseModel):
    """Workflow definition"""
    id: int
    name: str
    description: Optional[str] = None
    graphJson: Dict[str, Any]  # Contains nodes and connections
    createdAt: datetime
    updatedAt: datetime
    
    model_config = ConfigDict(extra='allow')




# ============================================================================
# --- ACL & PERMISSION MODELS ---
# ============================================================================

class Permission(BaseModel):
    """Permission definition"""
    id: int
    name: str
    description: Optional[str] = None


class DatasetAcl(BaseModel):
    """ACL entry for a dataset"""
    id: int
    resourceType: Literal['DATASET']
    resourceId: int
    principalType: Literal['USER', 'GROUP']
    principalId: int
    permissionId: int
    effect: Literal['Allow', 'Deny']
    createdAt: datetime
    updatedAt: datetime
    
    # Joined data for display
    principalName: Optional[str] = None
    permissionName: Optional[str] = None
    
    model_config = ConfigDict(extra='allow')


# ============================================================================
# --- DATASTORE MODELS ---
# ============================================================================

class DataStoreResponse(BaseModel):
    """Complete DataStore entity with all associated data"""
    id: int
    name: str
    type: Literal[
        'postgresql', 'mssql', 'sqlserver', 'filesystem', 'gpkg', 
        'mbtiles', 'esri', 'postgres', 'esri-geodatabase-mssql', 
        'esri-geodatabase-postgres', 'file_tiles', 'cog_storage'
    ]
    description: Optional[str] = None
    status: Literal['active', 'inactive', 'error', 'maintenance'] = 'active'
    capabilities: List[str] = Field(default_factory=list)
    organizationId: Optional[int] = None
    creatorUserId: Optional[int] = None
    predefinedConnectionName: Optional[str] = None
    connectionDetails: Optional[Dict[str, Any]] = None
    createdAt: datetime
    updatedAt: datetime
    
    model_config = ConfigDict(extra='allow')


class DataStoreListResponse(BaseModel):
    """Response from GET /api/datastores"""
    datastores: List[DataStoreResponse] = Field(default_factory=list)
    totalCount: int = 0


class TestConnectionResponse(BaseModel):
    """Response from POST /api/datastores/test-connection"""
    success: bool
    message: str
    capabilities: Optional[Dict[str, Any]] = None


class PredefinedDataStore(BaseModel):
    """Predefined datastore connection from server config"""
    connectionName: str
    type: str
    connectionDetails: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra='allow')


class DataStoreAclEntry(BaseModel):
    """ACL entry for a datastore"""
    id: int
    resourceType: Literal['DATASTORE']
    resourceId: int
    principalType: Literal['USER', 'GROUP']
    principalId: int
    permissionId: int
    effect: Literal['Allow', 'Deny']
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    # Joined data for display
    principalName: Optional[str] = None
    permissionName: Optional[str] = None
    
    model_config = ConfigDict(extra='allow')


# ============================================================================
# --- ESRI GEODATABASE MODELS ---
# ============================================================================

class EsriSpatialReference(BaseModel):
    """Spatial reference entry from ESRI geodatabase info."""

    wkid: int
    name: str

    model_config = ConfigDict(extra="allow")


class EsriDatasetDiscovered(BaseModel):
    """Single dataset row from ``GET /datastores/{id}/esri/datasets`` (adapter discovery)."""

    name: str
    aliasName: Optional[str] = None
    type: Literal["FeatureClass", "Table"]
    physicalName: str
    featureDataset: Optional[str] = None
    description: Optional[str] = None
    geometryType: Optional[str] = None
    registered: Optional[bool] = None

    model_config = ConfigDict(extra="allow")


class EsriApiMetadata(BaseModel):
    """Common ``metadata`` block on ESRI admin API responses."""

    count: Optional[int] = None
    totalProcessed: Optional[int] = None
    datastoreId: Optional[int] = None
    retrievedAt: Optional[datetime] = None

    model_config = ConfigDict(extra="allow")


class EsriDiscoverResponse(BaseModel):
    """``GET /api/datastores/{id}/esri/datasets``"""

    success: bool = True
    data: List[EsriDatasetDiscovered] = Field(default_factory=list)
    metadata: Optional[EsriApiMetadata] = None

    model_config = ConfigDict(extra="allow")


class EsriRegistrationResultItem(BaseModel):
    """One row in register / update / delete result lists."""

    datasetName: str
    datasetId: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None
    changes: Optional[List[str]] = None

    model_config = ConfigDict(extra="allow")


class EsriRegistrationResults(BaseModel):
    """``data`` payload for ``POST …/esri/datasets/register``."""

    registered: List[EsriRegistrationResultItem] = Field(default_factory=list)
    updated: List[EsriRegistrationResultItem] = Field(default_factory=list)
    skipped: List[EsriRegistrationResultItem] = Field(default_factory=list)
    errors: List[EsriRegistrationResultItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class EsriRegisterResponse(BaseModel):
    """``POST /api/datastores/{id}/esri/datasets/register``"""

    success: bool = True
    data: EsriRegistrationResults = Field(default_factory=EsriRegistrationResults)
    metadata: Optional[EsriApiMetadata] = None

    model_config = ConfigDict(extra="allow")


class EsriSchemaUpdateResults(BaseModel):
    """``data`` payload for ``PUT …/esri/datasets/schemas``."""

    updated: List[EsriRegistrationResultItem] = Field(default_factory=list)
    unchanged: List[EsriRegistrationResultItem] = Field(default_factory=list)
    failed: List[EsriRegistrationResultItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class EsriSchemaUpdateResponse(BaseModel):
    """``PUT /api/datastores/{id}/esri/datasets/schemas``"""

    success: bool = True
    data: EsriSchemaUpdateResults = Field(default_factory=EsriSchemaUpdateResults)
    metadata: Optional[EsriApiMetadata] = None

    model_config = ConfigDict(extra="allow")


class EsriBulkDeleteResults(BaseModel):
    """``data`` payload for ``DELETE …/esri/datasets``."""

    deleted: List[EsriRegistrationResultItem] = Field(default_factory=list)
    failed: List[EsriRegistrationResultItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class EsriBulkDeleteResponse(BaseModel):
    """``DELETE /api/datastores/{id}/esri/datasets`` (requires ``confirm=true``)."""

    success: bool = True
    data: EsriBulkDeleteResults = Field(default_factory=EsriBulkDeleteResults)
    metadata: Optional[EsriApiMetadata] = None

    model_config = ConfigDict(extra="allow")


class EsriDatastoreSummary(BaseModel):
    """Datastore slice inside ``GET …/esri/info``."""

    id: int
    name: str
    description: Optional[str] = None
    type: str
    status: Optional[str] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = ConfigDict(extra="allow")


class EsriGeodatabaseStats(BaseModel):
    """Geodatabase statistics from ``adapter.getGeodatabaseInfo()``."""

    version: Optional[str] = None
    isVersioned: Optional[bool] = None
    hasArchive: Optional[bool] = None
    datasetCount: Optional[int] = None
    featureClassCount: Optional[int] = None
    tableCount: Optional[int] = None
    versionedTableCount: Optional[int] = None
    archivedTableCount: Optional[int] = None
    supportedGeometryTypes: List[str] = Field(default_factory=list)
    spatialReferences: List[EsriSpatialReference] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class EsriGeodatabaseInfoPayload(BaseModel):
    """``data`` object for ``GET /api/datastores/{id}/esri/info``."""

    datastore: EsriDatastoreSummary
    geodatabase: EsriGeodatabaseStats

    model_config = ConfigDict(extra="allow")


class EsriGeodatabaseInfoResponse(BaseModel):
    """``GET /api/datastores/{id}/esri/info``"""

    success: bool = True
    data: EsriGeodatabaseInfoPayload
    metadata: Optional[EsriApiMetadata] = None

    model_config = ConfigDict(extra="allow")


class EsriRegisterOptions(BaseModel):
    """Options for ``POST …/esri/datasets/register``."""

    updateExisting: bool = False

    model_config = ConfigDict(extra="allow")


# ============================================================================
# --- RESOURCE MODELS (WORKGROUP, USER, ORGANIZATION) ---
# ============================================================================

class WorkgroupResponse(BaseModel):
    """Complete Workgroup entity"""
    id: int
    name: str
    description: Optional[str] = None
    organizationId: Optional[int] = None
    ownerUserId: Optional[int] = None
    status: str = 'active'
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    # Optional associations
    organization: Optional[Organization] = None
    owner: Optional[Principal] = None
    
    model_config = ConfigDict(extra='allow')


class WorkgroupListResponse(BaseModel):
    """Response from GET /api/workgroups"""
    workgroups: List[WorkgroupResponse] = Field(default_factory=list)
    totalItems: int = 0
    currentPage: int = 1
    totalPages: int = 1


class UserResponse(BaseModel):
    """Complete User entity"""
    id: int
    userName: str
    email: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    organizationId: Optional[int] = None
    status: str = 'active'
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    # Optional associations
    organization: Optional[Organization] = None
    
    model_config = ConfigDict(extra='allow')


class UserListResponse(BaseModel):
    """Response from GET /api/users"""
    users: List[UserResponse] = Field(default_factory=list)
    totalItems: int = 0


class OrganizationResponse(BaseModel):
    """Complete Organization entity"""
    id: int
    name: str
    description: Optional[str] = None
    status: str = 'active'
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    model_config = ConfigDict(extra='allow')


class OrganizationListResponse(BaseModel):
    """Response from GET /api/organizations"""
    organizations: List[OrganizationResponse] = Field(default_factory=list)
    totalItems: int = 0


class GroupResponse(BaseModel):
    """Complete Group entity"""
    id: int
    name: str
    description: Optional[str] = None
    organizationId: Optional[int] = None
    status: str = 'active'
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    model_config = ConfigDict(extra='allow')


class GroupListResponse(BaseModel):
    """Response from GET /api/groups"""
    groups: List[GroupResponse] = Field(default_factory=list)
    totalItems: int = 0


# ============================================================================
# --- WORKFLOW RUN MODELS ---
# ============================================================================

class WorkflowRunArtifact(BaseModel):
    """Artifact produced by a workflow run"""
    id: int
    nodeId: Optional[str] = None
    nodeType: Optional[str] = None
    dataType: Optional[str] = None
    filePath: Optional[str] = None
    pathOrUri: Optional[str] = None
    datasetId: Optional[int] = None
    createdAt: Optional[datetime] = None
    
    # Populated helper
    display_name: Optional[str] = None
    
    @model_validator(mode='before')
    @classmethod
    def resolve_paths(cls, data: Any) -> Any:
        if isinstance(data, dict):
            inner_data = data.get("data") or {}
            
            # Safely parse JSON if inner_data is a string
            if isinstance(inner_data, str):
                try:
                    inner_data = json.loads(inner_data)
                except Exception:
                    inner_data = {}

            # Resolve filePath
            if not data.get("filePath"):
                data["filePath"] = data.get("pathOrUri") or inner_data.get("pathOrUri") or \
                                 inner_data.get("path") or inner_data.get("filePath")
            
            # Resolve datasetId
            if not data.get("datasetId"):
                data["datasetId"] = data.get("datasetId") or inner_data.get("datasetId")
                
            # Resolve display_name
            if not data.get("display_name"):
                if data.get("datasetId"):
                    data["display_name"] = f"Dataset #{data['datasetId']}"
                elif data.get("filePath"):
                    data["display_name"] = os.path.basename(data["filePath"])
                else:
                    data["display_name"] = f"Artifact {data.get('id')}"
                    
        return data

    model_config = ConfigDict(extra='allow')


class WorkflowRunSubmitResponse(BaseModel):
    """202 response from POST /api/workflow-runs (run queued, not a full Task object)."""

    workflowRunId: int
    taskId: str
    status: Literal[
        "queued",
        "running",
        "canceling",
        "succeeded",
        "failed",
        "canceled",
    ]

    model_config = ConfigDict(extra="allow")


class WorkflowRun(BaseModel):
    """Workflow execution run"""
    id: int
    workflowId: int
    status: Literal[
        "queued",
        "running",
        "canceling",
        "succeeded",
        "failed",
        "canceled",
        # legacy / alternate values seen in API snapshots
        "pending",
        "processing",
        "completed",
        "error",
        "waiting",
    ]
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    artifacts: List[WorkflowRunArtifact] = Field(default_factory=list)
    logs: Optional[Dict[str, Any]] = None
    createdAt: datetime
    updatedAt: datetime
    
    model_config = ConfigDict(extra='allow')


class WorkflowRunListResponse(BaseModel):
    """Response from GET /api/workflow-runs.

    The server pages with raw ``limit``/``offset`` and answers ``{items, total}``;
    ``totalItems``/``currentPage``/``totalPages`` are kept for portals that page
    by page number. Read :attr:`total` first — it is the count that exists.
    """

    items: List[WorkflowRun] = Field(default_factory=list)
    total: Optional[int] = None
    totalItems: int = 0
    currentPage: int = 1
    totalPages: int = 1


# ============================================================================
# --- ANALYSIS TOOLS (workflow-as-tool surface, portal slice 030) ---
# ============================================================================


class AnalysisParam(BaseModel):
    """One input a caller must supply to run an analysis tool.

    Derived server-side from the workflow's param nodes on every read, so it
    cannot go stale when the graph changes (030 §1).
    """

    key: str
    label: Optional[str] = None
    type: str
    required: bool = False
    nullable: bool = True
    options: Optional[List[Any]] = None
    allowCustom: bool = False
    default: Any = None
    description: str = ""
    bindingMode: str = "param"

    model_config = ConfigDict(extra="allow")


class AnalysisTool(BaseModel):
    """A runnable workflow as the portal describes it.

    Both response shapes parse here: the catalog returns CARDS (no ``params`` /
    ``inputs``, which are per-parameter detail) and the single-tool selector
    returns the full MANIFEST.
    """

    toolId: int
    title: str
    summary: str = ""
    tags: List[str] = Field(default_factory=list)
    version: str = "1"
    # None (not []) on a catalog card: the server omits per-parameter detail there,
    # and an empty list would read as "this tool takes no arguments".
    params: Optional[List[AnalysisParam]] = None
    inputs: Optional[List[Dict[str, Any]]] = None
    outputs: List[Dict[str, Any]] = Field(default_factory=list)
    graph: Optional[Dict[str, Any]] = None
    runtime: Optional[Dict[str, Any]] = None
    access: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


class AnalysisToolListResponse(BaseModel):
    """Response from GET /api/workflows/tools — the caller's run set."""

    items: List[AnalysisTool] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    pageSize: int = 20
    warnings: List[Dict[str, Any]] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Response from GET /api/workflow-runs/:id/result-summary.

    Metadata only — scalars, dataset NAMES and artifact metadata. Records,
    geometry and filesystem paths never cross this boundary (030 §5).
    """

    runId: int
    workflowId: int
    toolId: Optional[int] = None
    title: Optional[str] = None
    status: str
    complete: bool = False
    startedAt: Optional[datetime] = None
    finishedAt: Optional[datetime] = None
    durationMs: Optional[int] = None
    source: str = "ui"
    params: Dict[str, Any] = Field(default_factory=dict)
    scalars: Dict[str, Any] = Field(default_factory=dict)
    datasets: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    portFallbacks: int = 0
    warnings: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# ============================================================================
# --- GENERATED FILES ---
# ============================================================================

class GeneratedFile(BaseModel):
    """File produced by a background task (exports, workflow outputs, etc.)."""

    id: int
    fileName: str
    fileSize: int
    downloadToken: Optional[str] = None
    sharingPolicy: Literal["public", "private"] = "private"
    expiresAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    taskId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


class GeneratedFileListResponse(BaseModel):
    """Response from GET /api/generated-files"""

    items: List[GeneratedFile] = Field(default_factory=list)
    totalItems: int = 0
    totalPages: int = 1
    currentPage: int = 1
    pageSize: int = 10

    model_config = ConfigDict(extra="allow")


# ============================================================================
# --- QUOTAS (SELF) ---
# ============================================================================

class UsagePlanSummary(BaseModel):
    """Plan summary embedded in quota responses (matches UsagePlan in API/DB)."""

    id: int
    code: str
    displayName: str
    description: Optional[str] = None
    status: Optional[str] = None
    tier: Optional[int] = None
    isDefaultForSelfRegistered: Optional[bool] = None
    isDefaultForTempAccounts: Optional[bool] = None
    isDefaultForOrgId: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class QuotaSummaryLimit(BaseModel):
    """Single limit row in GET /api/quotas/me/summary."""

    limitId: int
    dimensionKey: str
    limitType: str
    limitValue: float
    warnThresholdPercent: Optional[float] = None
    window: str
    windowDays: Optional[int] = None
    windowStart: Optional[datetime] = None
    windowEnd: Optional[datetime] = None
    currentValue: float = 0
    remaining: Optional[float] = None
    percentageUsed: Optional[float] = None
    dimension: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


class QuotaSummary(BaseModel):
    """Response from GET /api/quotas/me/summary."""

    enabled: bool
    reason: Optional[str] = None
    plan: Optional[UsagePlanSummary] = None
    limits: List[QuotaSummaryLimit] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# ============================================================================
# --- DATASET DISCOVER ---
# ============================================================================

class DatasetDiscoverResponse(BaseModel):
    """Response from POST /api/datasets/discover (200 or 202)."""

    success: bool = True
    datasets: List[Dict[str, Any]] = Field(default_factory=list)
    taskId: Optional[str] = None
    message: Optional[str] = None
    estimatedTime: Optional[float] = None
    discoverySessionId: Optional[str] = None
    count: Optional[int] = None
    status: Optional[str] = None

    model_config = ConfigDict(extra="allow")

    @property
    def is_background_task(self) -> bool:
        return bool(self.taskId)


# ============================================================================
# --- EDIT DOCUMENT / FIELD-ACCESS MODELS (slice 012) ---
# ============================================================================


class EditResult(BaseModel):
    """Answer of ``POST /datasets/{id}/edits``, whatever the mode was.

    ``validate``/``preview`` answer ``applied=False`` with a ``plan`` (and
    ``previews`` for ``preview``) and put their findings in ``issues``;
    ``apply`` answers ``applied=True`` with ``counts`` and ``identities``.
    Use :attr:`notes` when you do not care which key the mode used, and
    :attr:`ok` to tell an accepted document from an applied one.
    """

    edit_ref: Optional[str] = Field(default=None, alias="editRef")
    mode: Optional[str] = None
    applied: bool = False
    plan: Any = None
    previews: List[Any] = Field(default_factory=list)
    issues: List[Any] = Field(default_factory=list)
    warnings: List[Any] = Field(default_factory=list)
    counts: Optional[Dict[str, Any]] = None
    identities: Any = None
    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _capture_raw(cls, data: Any) -> Any:
        # ``raw`` keeps the whole wire answer, but it must NOT be inserted into
        # itself: that makes the model undumpable (pydantic rejects the cycle
        # with "Circular reference detected"). Copy first, then attach.
        if isinstance(data, dict):
            raw = dict(data)
            if not isinstance(raw.get("raw"), dict):
                data = dict(data)
                data["raw"] = raw
            return data
        return data

    @property
    def ok(self) -> bool:
        """Accepted by the server — ``apply`` must actually have applied."""
        if self.mode == "apply":
            return self.applied
        return self.mode in ("validate", "preview")

    @property
    def notes(self) -> List[Any]:
        """``issues`` + ``warnings`` — the server names them per mode."""
        return [*self.issues, *self.warnings]


class FieldRestriction(BaseModel):
    """One standalone field-deny overlay (slice 012 §2.3).

    A restriction SUBTRACTS ``denied_fields`` for one principal. It never
    grants table access and never changes ACL uniqueness. ``PUT`` answers the
    saved overlay, ``GET`` the list, and neither echoes ``grantedById`` yet —
    every field is optional so a shape change cannot break parsing.
    """

    id: Optional[int] = None
    dataset_id: Optional[int] = Field(default=None, alias="datasetId")
    principal_type: Optional[str] = Field(default=None, alias="principalType")
    principal_id: Optional[int] = Field(default=None, alias="principalId")
    denied_fields: List[str] = Field(default_factory=list, alias="deniedFields")
    updated_at: Optional[str] = Field(default=None, alias="updatedAt")
    granted_by_id: Optional[int] = Field(default=None, alias="grantedById")
    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _capture_raw(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = dict(data)
            raw.setdefault("raw", raw)
            return raw
        return data


# ============================================================================
# --- VIRTUAL DATASET / COMPUTED COLUMN MODELS (slice 013) ---
# ============================================================================


class VirtualField(BaseModel):
    """One field of an ad-hoc SQL result set (``name`` + ``type``).

    Comes from ``POST /datasets/sql-preview``; the SDK never synthesizes the
    type — ``virtual-sql`` requires exactly the discovered shape.
    """

    name: str
    type: str

    model_config = ConfigDict(extra="allow")


class CreateVirtualDatasetDto(BaseModel):
    """Body of ``POST /datasets/virtual`` (authoring-time contract).

    ``kind`` defaults to ``virtualFilter`` server-side; send it explicitly.
    ``queryDsl`` is the ROOT-scoped DSL: it is composed with the caller's own
    base filter/RLS at read time, so nothing is pre-composed here.
    """

    name: str = Field(..., min_length=1)
    dataStoreId: int = Field(..., ge=1)
    workgroupId: int = Field(..., ge=1)
    rootDatasetId: int = Field(..., ge=1)
    queryDsl: Dict[str, Any]
    kind: Optional[
        Literal["virtualRelate", "virtualJoin", "virtualGraph", "virtualFilter"]
    ] = None
    description: Optional[str] = None
    keywords: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class CreateVirtualSqlDatasetDto(BaseModel):
    """Body of ``POST /datasets/virtual-sql`` (ad-hoc SQL; restricted).

    ``fields`` must be the discovered list from ``sql-preview`` — inventing a
    field type is how a stored view drifts from the real result set.
    """

    name: str = Field(..., min_length=1)
    dataStoreId: int = Field(..., ge=1)
    workgroupId: int = Field(..., ge=1)
    sql: str = Field(..., min_length=1)
    fields: List[VirtualField] = Field(..., min_length=1)
    primaryKey: Optional[str] = None
    geometryColumn: Optional[str] = None
    hasZ: Optional[bool] = None
    # Discovery echoes: ``sql-preview`` answers these, ``virtual-sql`` stores
    # them. Sending them back keeps the stored view identical to the probe.
    shapeType: Optional[str] = None
    detectedShapeType: Optional[str] = None
    detectedHasZ: Optional[bool] = None
    spatialReference: Optional[Dict[str, Any]] = None
    description: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ComputedColumnPreview(BaseModel):
    """Answer of ``POST /datasets/computed-column/preview``.

    The wire shape is FLAT: the compiled SQL rides ``expression`` and a
    rejection rides ``code`` + ``message`` in a 200 (not an ``error`` object) —
    a rejected expression is a normal authoring answer and must not raise.
    :attr:`compiled_sql`, :attr:`error` and :attr:`catalog` are convenience
    views over those fields.

    This is a TEXT compile only: nothing is executed, and the authoritative
    validation re-runs on dataset save against the stored schema.
    """

    ok: bool = False
    dialect: Optional[str] = None
    expression: Optional[str] = None
    resultType: Optional[str] = None
    isWindow: bool = False
    code: Optional[str] = None
    message: Optional[str] = None
    templates: List[Any] = Field(default_factory=list)
    measures: List[Any] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _capture_raw(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = dict(data)
            raw.setdefault("raw", raw)
            return raw
        return data

    @property
    def compiled_sql(self) -> Optional[str]:
        """The compiled SQL text (``None`` when the expression was rejected)."""
        return self.expression if self.ok else None

    @property
    def error(self) -> Optional[Dict[str, Any]]:
        """``{code, message}`` when the expression was rejected, else ``None``."""
        if self.ok or not (self.code or self.message):
            return None
        return {"code": self.code, "message": self.message}

    @property
    def catalog(self) -> Dict[str, Any]:
        """The dialect's authoring catalog, as returned beside the compile."""
        return {
            "dialect": self.dialect,
            "templates": self.templates,
            "measures": self.measures,
        }


# ============================================================================
# --- GOVERNANCE MODELS (slice 015) ---
# ============================================================================


class UploadLimits(BaseModel):
    """The upload caps the portal enforces (``GET /uploads/limits``).

    The wire carries exactly these two values — there is no allowed-extension
    or declared-type list on the endpoint, so do not invent one. Read them
    BEFORE ``upload()`` to fail fast on size instead of collecting a 413.
    """

    maxFileSizeMb: int
    maxFilesPerUpload: int

    model_config = ConfigDict(extra="allow")

    @property
    def max_bytes(self) -> int:
        """``maxFileSizeMb`` in bytes (the portal's own unit)."""
        return int(self.maxFileSizeMb) * 1024 * 1024


# ============================================================================
# --- CONTROL-PLANE STORED RECORDS (slice 014) ---
# ============================================================================


class StoredDocument(BaseModel):
    """A stored record whose body is an inert, caller-owned JSON document.

    Map documents, publications and print-layout templates are passed through
    unchanged in ``raw``: the SDK never validates, normalizes or re-serializes
    their internals (the frontend owns that grammar). Only the identity fields
    the API guarantees are exposed as typed conveniences.
    """

    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @classmethod
    def from_api(cls, data: Any) -> "StoredDocument":
        """Wrap a response body; a non-dict answer yields an empty record."""
        return cls(raw=dict(data) if isinstance(data, dict) else {})

    def _field(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    @property
    def id(self) -> Optional[int]:
        return self._field("id")

    @property
    def name(self) -> Optional[str]:
        return self._field("name")

    @property
    def created_at(self) -> Optional[str]:
        return self._field("createdAt")

    @property
    def updated_at(self) -> Optional[str]:
        return self._field("updatedAt")


class MapDocument(StoredDocument):
    """A saved map: ``id``, ``name`` and an opaque ``details`` document."""


class Publication(StoredDocument):
    """A dataset publication record (OGC lifecycle state machine)."""

    @property
    def status(self) -> Optional[str]:
        return self._field("status")


class PrintLayout(StoredDocument):
    """A print-layout TEMPLATE definition (never rendered by the SDK)."""


class ThumbnailFile(BaseModel):
    """A thumbnail written to disk — bytes never travel inside JSON."""

    savedPath: str
    mimeType: str
    sizeBytes: int

    model_config = ConfigDict(extra="allow")


# ============================================================================
# --- API RESPONSE WRAPPERS ---
# ============================================================================

class DatasetsApiResponse(BaseModel):
    """Response from GET /api/datasets.

    Validation is per-item soft: a record the model cannot parse is degraded
    (``validationDegraded`` + ``rawRecord``) instead of rejecting the whole
    page — the discovery lane must survive a row shape this SDK has not seen.
    """
    datasets: List[Dataset] = Field(default_factory=list)
    totalCount: int = 0
    totalPages: int = 1
    currentPage: int = 1
    itemsPerPage: int = 0

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _repair_dataset_items(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw_items = data.get("datasets")
        if not isinstance(raw_items, list):
            return data
        return {**data, "datasets": [_repair_dataset_item(item) for item in raw_items]}


class ApiErrorResponse(BaseModel):
    """Standard error response from API"""
    success: bool = False
    message: str
    errors: Optional[Dict[str, Any]] = None
    statusCode: int = 400


class ApiSuccessResponse(BaseModel):
    """Generic success response wrapper"""
    success: bool = True
    data: Optional[Any] = None
    message: Optional[str] = None


# ============================================================================
# --- UTILITY: JSON SCHEMA GENERATION ---
# ============================================================================

def get_schema(model_class: type[BaseModel]) -> Dict[str, Any]:
    """
    Generate JSON schema for a Pydantic model.
    Useful for MCP integration.
    
    Usage:
        schema = get_schema(Dataset)
        # LLM can use this to understand the structure
    """
    return model_class.model_json_schema()


def get_schemas_for_mcp() -> Dict[str, Dict[str, Any]]:
    """
    Generate JSON schemas for all main models (for MCP integration).
    """
    return {
        'Dataset': get_schema(Dataset),
        'CreateDatasetDto': get_schema(CreateDatasetDto),
        'FeatureCollection': get_schema(FeatureCollection),
        'FilterStatistics': get_schema(FilterStatistics),
        'TaskResult': get_schema(TaskResult),
        'Workflow': get_schema(Workflow),
        'WorkflowRun': get_schema(WorkflowRun),
        'WorkflowRunSubmitResponse': get_schema(WorkflowRunSubmitResponse),
        'GeneratedFile': get_schema(GeneratedFile),
        'QuotaSummary': get_schema(QuotaSummary),
        'DatasetDiscoverResponse': get_schema(DatasetDiscoverResponse),
        'DataStoreResponse': get_schema(DataStoreResponse),
        'EsriDatasetDiscovered': get_schema(EsriDatasetDiscovered),
        'EsriDiscoverResponse': get_schema(EsriDiscoverResponse),
        'EsriRegisterResponse': get_schema(EsriRegisterResponse),
        'EsriGeodatabaseInfoResponse': get_schema(EsriGeodatabaseInfoResponse),
        'WorkgroupResponse': get_schema(WorkgroupResponse),
        'UserResponse': get_schema(UserResponse),
        'OrganizationResponse': get_schema(OrganizationResponse),
    }


if __name__ == '__main__':
    # Example: Generate and print JSON schema
    import json
    
    schema = Dataset.model_json_schema()
    print(json.dumps(schema, indent=2))
