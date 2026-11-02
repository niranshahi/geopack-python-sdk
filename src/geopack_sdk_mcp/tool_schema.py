"""Reusable MCP tool parameter annotations (JSON Schema descriptions for LLM hosts)."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, Union

from pydantic import Field

# --- Pagination / search ---

Page = Annotated[int, Field(description="Page number (1-based).", ge=1)]
PageSize = Annotated[int, Field(description="Number of items per page.", ge=1, le=500)]
SearchQuery = Annotated[
    Optional[str],
    Field(description="Optional free-text filter (name, description, keywords).", default=None),
]

# --- Datasets ---

DatasetId = Annotated[int, Field(description="Numeric Geoportal dataset id.")]
DetailsLevel = Annotated[
    str,
    Field(description="Trim response details: lite (default for list) | standard | full."),
]
DataTypeFilter = Annotated[
    Optional[str],
    Field(description="Filter by data type: vector or raster.", default=None),
]
BboxWgs84 = Annotated[
    Optional[List[float]],
    Field(
        description=(
            "Spatial extent filter as [west, south, east, north] in WGS84 degrees. "
            "Use bbox from geopack_sdk_geocode_place before list_datasets when the user names a place."
        ),
        default=None,
    ),
]
IsoDate = Annotated[
    Optional[str],
    Field(description="ISO date YYYY-MM-DD for temporal filter (inclusive).", default=None),
]
FeatureQuery = Annotated[
    Optional[Dict[str, Any]],
    Field(
        description="Optional FeatureQuery DSL. If omitted, use limit/offset/return_geometry instead.",
        default=None,
    ),
]
QueryLimit = Annotated[
    Optional[int],
    Field(description="Max features to return (capped at 500 in MCP). Default 100.", default=None),
]
QueryOffset = Annotated[int, Field(description="Feature offset for pagination.", ge=0)]
ReturnGeometry = Annotated[
    bool,
    Field(description="Include geometry in each feature (default true)."),
]
OutSrid = Annotated[
    Optional[int],
    Field(description="Reproject output geometries to this EPSG code.", default=None),
]
SavePath = Annotated[
    Optional[str],
    Field(
        description=(
            "Local path on the MCP host. Directory or full file path. "
            "Defaults vary by tool (see tool description)."
        ),
        default=None,
    ),
]
SavePathRequired = Annotated[
    str,
    Field(description="Local directory or file path on the MCP host to write bytes."),
]

# --- Upload / export ---

LocalFilePath = Annotated[
    str,
    Field(description="Absolute or resolved path to a file on the MCP host (not a URL)."),
]
DataStoreId = Annotated[int, Field(description="Target datastore id (from dataset list filters or portal).")]
WorkgroupId = Annotated[int, Field(description="Workgroup id that will own the new dataset or task.")]
WorkgroupIdOptional = Annotated[
    Optional[int],
    Field(description="Workgroup for the export task; defaults to the dataset owner workgroup.", default=None),
]
DeclaredType = Annotated[
    Optional[str],
    Field(description="Optional hint: vector or raster.", default=None),
]
UploadMetadata = Annotated[
    Optional[Dict[str, Any]],
    Field(
        description=(
            'Optional metadata for dataset:upload. Use key "name" for the dataset display title, '
            'e.g. {"name": "My dataset"}. Without name, the server uses the file basename.'
        ),
        default=None,
    ),
]
ExportFormat = Annotated[
    str,
    Field(description="Export format (e.g. geojson, shp, geotiff — depends on dataset type)."),
]
SharingPolicy = Annotated[
    str,
    Field(description="Generated file sharing: private (default) or organization."),
]

# --- Tasks ---

TaskId = Annotated[str, Field(description="Background task id (BullMQ job id) from upload/export/workflow submit.")]
WaitTimeout = Annotated[
    int,
    Field(description="Max seconds to poll before timeout.", ge=1),
]
WaitInterval = Annotated[
    int,
    Field(description="Seconds between poll attempts.", ge=1),
]

# --- Workflows ---

WorkflowId = Annotated[int, Field(description="Workflow definition id from geopack_sdk_list_workflows.")]
IncludeWorkflowParams = Annotated[
    bool,
    Field(
        description=(
            "If true, include parameters[] (keys, types, required, defaults). "
            "Use before submit_workflow. graphJson is never returned."
        ),
    ),
]
WorkflowParams = Annotated[
    Dict[str, Any],
    Field(
        description=(
            "Workflow input values keyed by parameter keys from get_workflow(include_params=true), "
            "e.g. param_4 (dataset id), param_7 (output name)."
        ),
    ),
]
OverrideDatastoreId = Annotated[
    Optional[int],
    Field(description="Optional datastore override for workflow execution.", default=None),
]
WorkflowRunId = Annotated[int, Field(description="Workflow run id from submit_workflow or wait_for_task results.")]
ArtifactId = Annotated[int, Field(description="Artifact id from geopack_sdk_get_workflow_run artifacts[].")]

# --- Analysis tools (workflow-as-tool surface, portal slice 030) ---

AnalysisToolId = Annotated[
    int,
    Field(description="Analysis tool id (toolId) from geopack_sdk_list_analysis_tools."),
]
AnalysisToolSelector = Annotated[
    Optional[int],
    Field(
        description=(
            "Optional single-tool selector. When set, the catalog call returns that ONE "
            "tool's full parameter manifest instead of the list — read this before running."
        ),
        default=None,
    ),
]
AnalysisParams = Annotated[
    Dict[str, Any],
    Field(
        description=(
            "Input values keyed by the manifest's params[].key. Read the manifest first "
            "(list_analysis_tools with tool_id); never guess a key."
        ),
    ),
]
AnalysisTag = Annotated[
    Optional[str],
    Field(description="Exact tag filter for the analysis-tool catalog.", default=None),
]
AnalysisWaitFlag = Annotated[
    bool,
    Field(
        description=(
            "true (default): wait for the run to finish and return its result summary. "
            "false: return workflowRunId/taskId immediately and poll with "
            "get_analysis_result."
        ),
    ),
]
AnalysisTimeoutSeconds = Annotated[
    int,
    Field(
        description=(
            "Polling budget in seconds when wait=true (default 900). A timeout does NOT "
            "cancel the run — it keeps going and its run id is returned in the error."
        ),
        ge=1,
        le=86400,
    ),
]

# --- Generated files ---

GeneratedFileId = Annotated[
    int,
    Field(description="generatedFileId from wait_for_task results after export or workflow."),
]

# --- Geocoding ---

PlaceQuery = Annotated[
    str,
    Field(description="Place name or address to geocode (Nominatim, external)."),
]
GeocodeLimit = Annotated[
    int,
    Field(description="Max number of place candidates to return (default 1).", ge=1, le=10),
]

# --- Return types (geocode only) ---

GeocodeResult = Union[Dict[str, Any], List[Dict[str, Any]]]
