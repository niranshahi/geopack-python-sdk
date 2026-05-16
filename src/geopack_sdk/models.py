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
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


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
    """Complete Dataset entity with all associated data"""
    id: int
    name: str
    description: Optional[str] = None
    dataType: Literal['vector', 'table', 'raster']
    subType: Optional[str] = None
    keywords: Optional[str] = None
    
    # Identity fields
    ownerUserId: int
    workgroupId: int
    dataStoreId: int
    
    # Metadata - details can be JSON string or dict
    details: Optional[Union[str, Dict[str, Any]]] = None
    status: str = 'active'
    
    # Timestamps
    createdAt: datetime
    updatedAt: datetime
    
    # Optional associations (populated by API when requested)
    owner: Optional[Principal] = None
    workgroup: Optional[Workgroup] = None
    dataStore: Optional[DataStore] = None
    
    # UI helper (thumbnail can be base64 string or Buffer object)
    thumbnail: Optional[Union[str, Dict[str, Any]]] = None
    
    model_config = ConfigDict(
        extra='allow',  # Allow additional fields for forward compatibility
        from_attributes=True  # Allow population from ORM models
    )
    
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
    """Response from GET /api/workflow-runs"""
    items: List[WorkflowRun] = Field(default_factory=list)
    totalItems: int = 0
    currentPage: int = 1
    totalPages: int = 1


# ============================================================================
# --- API RESPONSE WRAPPERS ---
# ============================================================================

class DatasetsApiResponse(BaseModel):
    """Response from GET /api/datasets"""
    datasets: List[Dataset] = Field(default_factory=list)
    totalCount: int
    totalPages: int
    currentPage: int
    itemsPerPage: int


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
        'DataStoreResponse': get_schema(DataStoreResponse),
        'WorkgroupResponse': get_schema(WorkgroupResponse),
        'UserResponse': get_schema(UserResponse),
        'OrganizationResponse': get_schema(OrganizationResponse),
    }


if __name__ == '__main__':
    # Example: Generate and print JSON schema
    import json
    
    schema = Dataset.model_json_schema()
    print(json.dumps(schema, indent=2))
