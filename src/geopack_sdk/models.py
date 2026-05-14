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

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any, Literal, List, Union
from datetime import datetime


# ============================================================================
# --- NESTED / SHARED MODELS ---
# ============================================================================

class Principal(BaseModel):
    """Represents a User or Group principal"""
    id: int
    userName: Optional[str] = None
    name: Optional[str] = None
    
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
    """Result of a background task execution"""
    id: Optional[str] = None  # API may return taskId instead
    taskId: Optional[str] = None  # Alternative field name used by API
    status: Literal['pending', 'processing', 'completed', 'failed', 'canceled', 'partial_success']
    message: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    results: Optional[Any] = None  # Can be list of IDs, FeatureCollection, etc.
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    model_config = ConfigDict(extra='allow')
    
    @property
    def task_id(self) -> Optional[str]:
        """Helper to get task ID from either field"""
        return self.taskId or self.id


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


class WorkflowRun(BaseModel):
    """Workflow execution run"""
    id: int
    workflowId: int
    status: Literal['pending', 'processing', 'completed', 'failed', 'canceled']
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
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
    }


if __name__ == '__main__':
    # Example: Generate and print JSON schema
    import json
    
    schema = Dataset.model_json_schema()
    print(json.dumps(schema, indent=2))
