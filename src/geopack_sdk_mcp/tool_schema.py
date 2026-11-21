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
    Field(
        description=(
            "Filter by data type: vector, raster, table (or service). Omit to list every "
            "type; service/leaf rows have no datastore and are still returned."
        ),
        default=None,
    ),
]
BboxWgs84 = Annotated[
    Optional[List[float]],
    Field(
        description=(
            "Spatial extent filter as [west, south, east, north] in WGS84 degrees. "
            "Filters on the dataset's STORED extent (ext_*), not feature geometry: datasets "
            "whose stored extent is null (common for rasters) are NOT matched, so a short "
            "list does not mean 'nothing there'. Use bbox from geopack_sdk_geocode_place "
            "before list_datasets when the user names a place."
        ),
        default=None,
    ),
]
DatasetFields = Annotated[
    Optional[List[str]],
    Field(
        description=(
            "Optional projection: return only these top-level dataset keys (id is always "
            'kept). E.g. ["id","name","dataType","createdAt"]. Use it to keep list output '
            "inside the token budget."
        ),
        default=None,
    ),
]
ListOrderBy = Annotated[
    Optional[str],
    Field(
        description=(
            "Sort field: id | name | dataType | subType | updatedAt | createdAt | "
            "owner.userName | workgroup.name | dataStore.name | publicationsCount. "
            "Omitted = the portal default (updatedAt, newest first). Prefer order_by over "
            "paging everything to find recent items."
        ),
        default=None,
    ),
]
OrderDirection = Annotated[
    Optional[str],
    Field(description='Sort direction "asc" or "desc" (default asc when order_by is set).', default=None),
]
WorkflowOrderBy = Annotated[
    Optional[str],
    Field(
        description=(
            "Sort field: id | name | owner.userName | updatedAt | createdAt | version. "
            "Omitted = the portal default (updatedAt, newest first). Prefer it over paging "
            "everything to find recent workflows."
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
ThumbnailSavePath = Annotated[
    Optional[str],
    Field(
        description=(
            "OPTIONAL local write of the PNG. Inline return is the official delivery mode; "
            "the image always comes back in the tool result. A file is written only when the "
            "MCP host permits local writes — many sandboxed hosts do not, and then the result "
            "answers saved=false (saveSkipped when omitted) with the image still inline. "
            "Omit it unless you specifically need a file on disk."
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

# --- Dataset schema / aggregate / relationships (slice 020 read lanes) ---

IncludeDomainValues = Annotated[
    bool,
    Field(
        description=(
            "Include coded-value domain values for each field (values are capped at 50). "
            "Leave false unless the user asks what the codes mean."
        )
    ),
]
IncludeRelationships = Annotated[
    bool,
    Field(
        description=(
            "Include the dataset's authored relationship names (target dataset + cardinality). "
            "Keep true: it lets get_related_records run without another lookup."
        )
    ),
]
AggregateList = Annotated[
    Optional[List[Dict[str, Any]]],
    Field(
        description=(
            'Aggregate specs: [{field?, aggregate, alias?, p?}]. aggregate is one of count, '
            "countDistinct, sum, avg, min, max, stddev, stddevPop, variance, varPop, median, "
            'percentile. percentile requires p in 0..1. field is required except for count. '
            'Default [{aggregate: "count"}].'
        ),
        default=None,
    ),
]
GroupByList = Annotated[
    Optional[List[str]],
    Field(
        description=(
            "Field names to group by (max 3). Take the names from geopack_sdk_get_dataset_schema; "
            "never guess a column."
        ),
        default=None,
    ),
]
AggregateOrderBy = Annotated[
    Optional[List[Dict[str, Any]]],
    Field(
        description=(
            'Bucket ordering: [{key, direction, by?}] max 3. key = a group_by field name, '
            'count/aggregate_count, or an aggregate ALIAS (a count aggregate\'s alias is '
            'accepted and resolved to aggregate_count); direction = asc | desc; by = what '
            'the key names — "value" (the stored code, default) or "label" (the code\'s '
            'declared name). An unknown key is refused with the legal key list.'
        ),
        default=None,
    ),
]
AggregateLimit = Annotated[
    int,
    Field(description="Max buckets to return (1-50, default 20).", ge=1, le=50),
]
FeatureFilter = Annotated[
    Optional[Dict[str, Any]],
    Field(
        description=(
            "Optional attribute scope as the portal's FeatureQuery DSL filter node. "
            "Omit it for no attribute filter — an empty value is not the same as 'match all'."
        ),
        default=None,
    ),
]
SpatialFilter = Annotated[
    Optional[Dict[str, Any]],
    Field(
        description=(
            "Optional spatial scope (FeatureQuery DSL spatialFilter node: geometry + spatialRel). "
            "Omit it for no spatial filter."
        ),
        default=None,
    ),
]
RelationshipName = Annotated[
    str,
    Field(
        description=(
            "Relationship name from geopack_sdk_get_dataset_relationships. Never invent one."
        )
    ),
]
OriginObjectIds = Annotated[
    List[int],
    Field(
        description=(
            "Source record OID values (the oidField reported by geopack_sdk_get_dataset_schema). "
            "At least 1, at most 100 per call."
        )
    ),
]
RelatedLimit = Annotated[
    int,
    Field(description="Max related records to return (1-200, default 50).", ge=1, le=200),
]
RelationshipDirection = Annotated[
    str,
    Field(
        description=(
            'forward (default): origin record -> related records; backward: the reverse leg.'
        )
    ),
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
BudgetChars = Annotated[
    Optional[int],
    Field(
        description=(
            "Optional character budget for the projected spec. Omit for the full spec; "
            "a small budget answers with refs (and a section index when even those do not fit)."
        ),
        ge=2000,
        le=200000,
        default=None,
    ),
]
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
WorkflowIdOptional = Annotated[
    Optional[int],
    Field(description="Optional workflow definition id filter (from list_workflows).", default=None),
]
RunStatusFilter = Annotated[
    Optional[str],
    Field(
        description=(
            "Optional run status filter: queued, running, canceling, succeeded, failed or canceled."
        ),
        default=None,
    ),
]
ArtifactId = Annotated[int, Field(description="Artifact id from geopack_sdk_get_workflow_run artifacts[].")]
RunOrderBy = Annotated[
    Optional[str],
    Field(
        description=(
            "Sort field: id | workflow.name | submitter | taskId | status | startedAt | "
            "finishedAt | createdAt | updatedAt. Omitted = the portal default (createdAt, "
            "newest first)."
        ),
        default=None,
    ),
]

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

# --- Record edits (EditDoc) ---

EditDocumentPayload = Annotated[
    Dict[str, Any],
    Field(
        description=(
            "EditDoc envelope: {version: '1.0', editRef?: uuid, options?: {...}, changes: [...]}. "
            "changes[] is the portal's edit grammar (operation + dataset + records); the SDK never "
            "re-derives it. Always send the SAME document to validate, preview and apply."
        )
    ),
]
EditMode = Annotated[
    str,
    Field(
        description=(
            "Ladder step: validate (default, plans only) | preview (plans + simulated per-op result) "
            "| apply (WRITES, one transaction, needs consent and an editRef)."
        )
    ),
]

# --- Generated files ---

GeneratedFileId = Annotated[
    int,
    Field(description="generatedFileId from wait_for_task results after export or workflow."),
]
GeneratedFileOrderBy = Annotated[
    Optional[str],
    Field(
        description=(
            "Sort field: createdAt | fileName | fileSize | expiresAt | sharingPolicy. "
            "Omitted = the portal default (createdAt, newest first)."
        ),
        default=None,
    ),
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
