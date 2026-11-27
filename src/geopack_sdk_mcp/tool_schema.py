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
            'kept). E.g. ["id","name","dataType","createdAt"]. Allowed names include the WGS84 '
            "`ext_west/ext_south/ext_east/ext_north` columns, `publicationsSummary`, and the "
            "synthetic `geo_extent` (alias `details.geo_extent`), which returns "
            "{bbox, crs, axisOrder} without pulling the whole `details` blob. To find a "
            "`publicationId` for show_map, sort with order_by='publicationsCount' and read "
            "`publicationsSummary[].id` (a dataset id is not a publication id). Use it to keep "
            "list output inside the token budget."
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
        description=(
            "Optional FeatureQuery DSL. If omitted, use limit/offset/return_geometry instead. "
            "Its `filter` is an attribute node: {type:'rule', field, operator, value} or "
            "{type:'group', operator:'AND'|'OR', children:[...]}. A flat {field, operator, value} "
            "rule (and a list of rules, combined with AND) is accepted and normalized; a different "
            "shape is refused as invalid_args, not sent to the portal."
        ),
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
    Field(
        description=(
            "Output geometry CRS. Defaults to **4326** (WGS84 lon/lat, map-friendly); pass another "
            "EPSG code to override. Applies to both the simple and query-DSL lanes. If the portal "
            "cannot reproject, the result is still returned with a `crsNote` (and `outSridApplied`)."
        ),
        default=4326,
    ),
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
    Optional[Union[Dict[str, Any], List[Any]]],
    Field(
        description=(
            "Optional attribute scope as a filter node. Shape: "
            "{type:'rule', field, operator, value} (operator tokens like '=', '$ilike', 'IN') or "
            "{type:'group', operator:'AND'|'OR', children:[...]}. A flat {field, operator, value} "
            "rule is wrapped as a rule, and a bare list of rules is combined with AND — both are "
            "accepted and normalized client-side (the schema accepts an object, an array or null). "
            "Any other shape (e.g. a Mongo-style {field:{$eq:v}}) is refused as invalid_args "
            "before the round trip. Omit it for no attribute filter — an empty value is not the "
            "same as 'match all'."
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

# --- Local geometry ops (slice 033, Lane C) ---

GeometryOpName = Annotated[
    str,
    Field(
        description=(
            "The local op: buffer | overlay | convex_hull | envelope | dissolve | simplify | "
            "validate | fix | convert | project | measure | distance | nearest | line_between | "
            "point_on_surface | smooth | create | describe. Runs locally — no portal call."
        )
    ),
]
GeometryGeoJson = Annotated[
    Optional[Dict[str, Any]],
    Field(
        description=(
            "Input GeoJSON (geometry, Feature or FeatureCollection) for the first side. "
            "Coordinates are WGS84 unless 'wkid' names the projected CRS for metric math."
        ),
        default=None,
    ),
]
GeometryText = Annotated[
    Optional[str],
    Field(description="Input as WKT text (alternative to 'geojson'; used by convert).", default=None),
]
GeometryBSide = Annotated[
    Optional[Dict[str, Any]],
    Field(description="Second-side GeoJSON for overlay/distance/nearest/line_between.", default=None),
]
GeometryBText = Annotated[
    Optional[str],
    Field(description="Second side as WKT text.", default=None),
]
GeometryOverlayOp = Annotated[
    Optional[str],
    Field(
        description=(
            "Overlay sub-op when op='overlay': union | intersection | difference | xor | clip. "
            "Omit 'b' for union to merge every part of the first input into one geometry."
        ),
        default=None,
    ),
]
GeometryUnits = Annotated[
    Optional[str],
    Field(
        description=(
            "Distance unit: m | km | ft | mi. Unknown units are refused (never defaulted). "
            "buffer input and measure output use it; distance/nearest echo it in the result."
        ),
        default=None,
    ),
]
GeometryDistance = Annotated[
    Optional[float],
    Field(
        description="buffer: distance in the chosen units (must be a positive finite number).",
        default=None,
    ),
]
GeometryMethod = Annotated[
    Optional[str],
    Field(
        description=(
            "Buffer method: planar (default; auto local UTM) or geodesic (not available in v1 — "
            "refused with a code)."
        ),
        default=None,
    ),
]
GeometryWkid = Annotated[
    Optional[int],
    Field(
        description=(
            "Projected EPSG code for metric math (e.g. a UTM zone). Omitted/4326 = derive a local "
            "UTM from the input; a projected code is honoured for buffer/simplify/measure/distance. "
            "For project, wkid is the target CRS (output_wkid is accepted as an alias)."
        ),
        default=None,
    ),
]
GeometrySegments = Annotated[
    Optional[int],
    Field(description="Buffer circle segments (8–256, default 64).", default=None),
]
GeometryDissolve = Annotated[
    Optional[bool],
    Field(description="Buffer: merge all buffered parts into one geometry (default true).", default=None),
]
GeometryGroupBy = Annotated[
    Optional[List[str]],
    Field(description="dissolve: feature property keys to group by (required).", default=None),
]
GeometryTolerance = Annotated[
    Optional[float],
    Field(description="simplify: Douglas–Peucker tolerance in metres (default 1).", default=None),
]
GeometryIterations = Annotated[
    Optional[int],
    Field(description="smooth: Chaikin passes (1–10, default 1).", default=None),
]
GeometryFormat = Annotated[
    Optional[str],
    Field(description="convert target: geojson | wkt (inferred from the input when omitted).", default=None),
]
GeometryOutputWkid = Annotated[
    Optional[int],
    Field(description="project: optional second transform for the output CRS.", default=None),
]
GeometryTypeName = Annotated[
    Optional[str],
    Field(
        description="create: Point | LineString | Polygon | MultiPoint | MultiLineString | MultiPolygon.",
        default=None,
    ),
]
GeometryCoordinates = Annotated[
    Optional[Any],
    Field(description="create: GeoJSON coordinate array for the chosen geometry type.", default=None),
]
GeometryMaxVertices = Annotated[
    Optional[int],
    Field(description="describe: vertex-count cap (1–200000, default 10000).", default=None),
]
GeometryMerge = Annotated[
    Optional[bool],
    Field(description="convex_hull: merge the whole collection into one hull (default true).", default=None),
]

# --- Local map data service (slice 033, Lane A) ---

MapTitle = Annotated[
    Optional[str],
    Field(description="Map title shown in the manifest (default 'Geopack map').", default=None),
]
MapLayers = Annotated[
    Optional[List[Dict[str, Any]]],
    Field(
        description=(
            "Layers to declare, each an object with a 'kind' (or an inferred one): "
            "portal-dataset {datasetId, query?}, portal-publication {publicationId}, "
            "local-file {path under GEOPACK_MCP_MAP_ROOT}, or inline-geometry {geojson}. "
            "Optional id/title/style/bbox/render/limit/xyzUrl. Every layer gets a stable dataUrl; "
            "portal layers also get a tileUrl; portal-publication layers also get wmsUrl/wmtsUrl/wfsUrl. "
            "`bbox` is [west, south, east, north] in EPSG:4326 (when omitted it is read from the "
            "source dataset's WGS84 geo_extent). `publicationId` must be a real publication id "
            "(from list_datasets publicationsSummary), not a dataset id — it is validated at "
            "map-build. A portal-dataset raster is drawn as server-rendered PNG tiles "
            "through the portal's raster-tile lane (`/rasters` -> "
            "`/datasets/{id}/rastertile/{z}/{x}/{y}.png`) whenever the raster lives in PostGIS "
            "or an MBTiles dataset (render 'rastertile', auto-selected), applying the "
            "dataset's saved display/colorMap. It is drawn directly as a COG when "
            "`details.hasCOG` (render 'cog', auto-selected), and a raster WMS/WMTS publication "
            "uses a portal-publication layer. Only a raster with no tile source at all stays a "
            "vector footprint and warns. On the raster-tile lane an optional `display` object "
            "(displayType/RBand/GBand/BBand/band/colorMap/minimum/maximum/reclass/customColorMap) "
            "overrides the dataset's saved rendering, and `refZoom` overrides the computed native "
            "zoom — so the SAME raster can be shown with different renderings. `render` "
            "(geojson|mvt|wms|wmts|wfs|xyz|cog|rastertile) picks the "
            "viewer renderer; for dataset layers it changes the output between vector "
            "(GeoJSON/MVT), the raster-tile image, and the COG lane. `limit` "
            "caps the features a GeoJSON dataset layer loads (default 1000; 0 = the whole dataset). "
            "When a dataset is larger than the cap the manifest warns with the totals — the MCP "
            "never switches renderer or truncates on its own: choose GeoJSON with a higher/0 `limit` "
            "(full data, larger payload, keeps the saved symbology) or render 'mvt' (tiled, full "
            "coverage, but loses the dataset's saved symbology until styled otherwise), and ask the "
            "user when unsure. `symbology` overrides a layer's colouring with a data-driven spec: a "
            "shorthand {type:'uniqueValue', field} gives one colour per distinct value, and "
            "{type:'classBreaks', field, classes?} gives quantile area/value breaks (default 5); a "
            "complete {unique:[...]} or {breaks:[...]} spec (or the dataset's own renderer when "
            "omitted) is honoured too. Use it to show the same dataset styled several ways; it also "
            "drives the legend. `style` ({fill,stroke,weight,radius}) recolours VECTOR layers only "
            "(render geojson | mvt | wfs); a WMS/WMTS/XYZ image is rendered by the server and cannot "
            "be recoloured (use render 'wfs' for a client-styled vector layer). Layers without an "
            "explicit fill rotate through the template `layerPalette`, so several layers stay "
            "distinguishable. The manifest additionally marks a raster source with `raster: true` "
            "(the legend then shows a raster swatch). An `inline-geometry` layer accepts a bare "
            "geometry, a Feature, or a FeatureCollection. Use the reserved `properties.__style__` key "
            "(NOT `style`) to style one feature on top of the layer style: "
            "`__style__` = {fill,stroke,weight,radius,opacity}. It is never mistaken for a normal "
            "attribute and is hidden from the identify popup, so the agent can draw any geometry "
            "with embedded styling."
        ),
        default=None,
    ),
]
MapIdArg = Annotated[
    Optional[str],
    Field(description="Existing map id to update instead of creating a new map.", default=None),
]
OpenBrowser = Annotated[
    bool,
    Field(
        description=(
            "Best-effort: open the built-in viewer page in the default browser. Never depended on "
            "— viewerUrl is always returned and works without spawning a process."
        ),
    ),
]
BasemapName = Annotated[
    Optional[str],
    Field(
        description=(
            "Basemap id to select (must exist in the template's `basemaps`; e.g. 'osm' or 'blank')."
        ),
        default=None,
    ),
]
MapTemplate = Annotated[
    Optional[Dict[str, Any]],
    Field(
        description=(
            "Per-call template override (deep-merged over the user + default template): any of "
            "title, subtitle, footer, basemap, basemaps[], view, palette, layerStyle, "
            "layerPalette[], layerList, legend, scale, attribution. `view.center` is [lon, lat] in "
            "EPSG:4326; `view.mode` is 'fit' (fit the declared layer extents) or 'center'; "
            "`layerPalette` is the rotating fill palette for layers that set no style.fill. "
            "Unknown keys are ignored; a wrong type falls back to the default for that key and is "
            "listed in templateWarnings."
        ),
        default=None,
    ),
]
MapStyle = Annotated[
    Optional[Dict[str, Any]],
    Field(
        description=(
            "Per-call default layer style shorthand: {fill, stroke, weight, opacity, radius}. "
            "Merged into the template's layerStyle and applies to VECTOR layers only (a WMS/WMTS "
            "image is server-rendered and ignores it)."
        ),
        default=None,
    ),
]

MapCenter = Annotated[
    Optional[List[float]],
    Field(
        description=(
            "Point the map at a location: [lon, lat] in EPSG:4326. Sugar for "
            "`template.view.center`; also sets `view.mode='center'` (unless a mode was given) so "
            "the view stays on the point instead of auto-fitting the layer extents."
        ),
        default=None,
    ),
]
MapZoom = Annotated[
    Optional[int],
    Field(
        description=(
            "Initial zoom level (0-24). Sugar for `template.view.zoom`; also sets "
            "`view.mode='center'` (unless a mode was given)."
        ),
        default=None,
    ),
]
MapReplaceLayers = Annotated[
    bool,
    Field(
        description=(
            "When updating an existing map (map_id), drop its current layers before adding "
            "`layers`, so the map holds exactly this call's layers instead of appending "
            "(`layersReplaced: true` in the result). Default false (append)."
        ),
        default=False,
    ),
]
MapRemoveLayers = Annotated[
    Optional[List[str]],
    Field(
        description=(
            "Layer ids (from a previous show_map result) to drop from an existing map before "
            "adding `layers`. Removing layers needs map_id; unknown ids are ignored with a "
            "templateWarning naming them. The dropped ids come back as `removedLayers`."
        ),
        default=None,
    ),
]

# --- Return types (geocode only) ---

GeocodeResult = Union[Dict[str, Any], List[Dict[str, Any]]]
