"""Dataset tool handlers (testable without the mcp package)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

from geopack_sdk import GeopackClient
from geopack_sdk.datasets import normalize_feature_query_dsl
from geopack_sdk.dataset_payload import dataset_thumbnail_resource_uri
from geopack_sdk.exceptions import (
    AggregationInvalidArgs,
    AggregationUnsupported,
    GeopackAuthError,
    GeopackError,
    QueryValidationError,
    RelationshipCatalogUnavailable,
)

from ..bbox import normalize_bbox
from ..errors import ToolArgumentError
from ..resource_handlers.datasets import fetch_dataset_thumbnail
from ..sanitize.dataset_details import (
    DetailsLevel,
    normalize_details_level,
    trim_dataset_for_mcp,
    trim_datasets_list_payload,
)
from ..sanitize.dataset_schema import build_dataset_schema, build_relationship_rows
from ..sanitize.query_results import clamp_query_limit, trim_feature_collection_for_mcp
from ..sanitize.task_results import sanitize_async_task_start, sanitize_task_payload
from ..serialize import to_jsonable

ExportFormat = Literal[
    "geojson",
    "shapefile",
    "gpkg",
    "geotiff",
    "mbtiles",
    "csv",
    "filegdb",
    "tif",
    "tiff",
]


def list_datasets(
    client: GeopackClient,
    *,
    page: int = 1,
    page_size: int = 20,
    search_query: Optional[str] = None,
    details_level: Optional[str] = "lite",
    data_type: Optional[str] = None,
    bbox: Optional[list | str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    level: DetailsLevel = normalize_details_level(details_level, default="lite")
    active_filters: Dict[str, Any] = {}

    parsed_bbox = normalize_bbox(bbox)

    if data_type:
        active_filters["dataType"] = data_type
    if parsed_bbox is not None:
        active_filters["bbox"] = parsed_bbox
    if start_date:
        active_filters["startDate"] = start_date
    if end_date:
        active_filters["endDate"] = end_date

    result = client.datasets.list(
        page=page,
        page_size=page_size,
        search_query=search_query,
        active_filters=active_filters or None,
    )
    return trim_datasets_list_payload(to_jsonable(result), details_level=level)


def get_dataset(
    client: GeopackClient,
    dataset_id: int,
    *,
    details_level: Optional[str] = "full",
) -> Dict[str, Any]:
    level: DetailsLevel = normalize_details_level(details_level, default="full")
    result = client.datasets.get(dataset_id)
    return trim_dataset_for_mcp(to_jsonable(result), level)


def query_dataset(
    client: GeopackClient,
    dataset_id: int,
    query: Optional[Dict[str, Any]] = None,
    *,
    limit: Optional[int] = None,
    offset: int = 0,
    return_geometry: bool = True,
    out_srid: Optional[int] = None,
) -> Dict[str, Any]:
    """Run POST /datasets/{id}/query with MCP-safe limits."""
    if query is None:
        effective_limit = clamp_query_limit(limit)
        result = client.datasets.query(
            dataset_id,
            None,
            limit=effective_limit,
            offset=offset,
            return_geometry=return_geometry,
            out_srid=out_srid,
        )
    else:
        dsl = normalize_feature_query_dsl(dict(query))
        pagination = dict(dsl.get("pagination") or {})
        req_limit = pagination.get("limit", limit)
        effective_limit = clamp_query_limit(
            int(req_limit) if req_limit is not None else limit
        )
        pagination["limit"] = effective_limit
        pagination.setdefault("offset", offset)
        dsl["pagination"] = pagination
        result = client.datasets.query(dataset_id, dsl)

    payload = trim_feature_collection_for_mcp(to_jsonable(result))
    payload["queryLimitApplied"] = effective_limit
    return payload


def get_dataset_thumbnail(
    client: GeopackClient,
    dataset_id: int,
    save_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch thumbnail PNG to disk on the MCP host (for Cursor Agent chat previews).

    Bytes are not returned in tool JSON — only ``savedPath`` and metadata.
    """
    body, mime_type = fetch_dataset_thumbnail(client, dataset_id)

    if save_path:
        target = Path(save_path)
    else:
        target = Path("downloads") / f"dataset_{dataset_id}_thumbnail.png"

    if target.suffix == "" or target.is_dir():
        target = target / f"dataset_{dataset_id}_thumbnail.png"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    resolved = str(target.resolve())
    from ..context import register_temp_file
    register_temp_file(resolved)

    return {


        "datasetId": dataset_id,
        "savedPath": resolved,
        "mimeType": mime_type,
        "sizeBytes": len(body),
        "thumbnailResourceUri": dataset_thumbnail_resource_uri(dataset_id),
    }


def export_dataset(
    client: GeopackClient,
    dataset_id: int,
    format: str,
    *,
    workgroup_id: Optional[int] = None,
    sharing_policy: str = "private",
) -> Dict[str, Any]:
    """
    Start a dataset:export background task (does not wait for completion).
    """
    if workgroup_id is None:
        dataset = client.datasets.get(dataset_id)
        workgroup_id = dataset.workgroupId

    task = client.datasets.export(
        dataset_id,
        workgroup_id,
        format,
        sharing_policy=sharing_policy,
        wait=False,
    )
    return sanitize_async_task_start(to_jsonable(task))


# Deletes are intentionally not exposed; see docs/09-sdk/mcp-design/mcp-safety.md.
#
# ``delete_dataset`` used to live here with no registration: one line away from
# being wired up by a future contributor. The policy is now *stated* —
# ``tools/policy.py::UNAVAILABLE_OPERATIONS`` lists the operations MCP refuses
# and ``tests/test_mcp_write_tools.py`` asserts the surface matches it.


# --- Read lanes (slice 020) -------------------------------------------------
#
# These four handlers are ANSWER tools: the server already returns the cheap,
# authoritative shape. Nothing here re-derives a count, a schema or a
# relationship — the MCP edge never repeats server semantics.

# The enum lives in the MCP contract (slice 020 §2): a model must not guess it,
# and the SDK deliberately leaves kind validation to the server validator.
AGGREGATE_KINDS = (
    "count",
    "countDistinct",
    "sum",
    "avg",
    "min",
    "max",
    "stddev",
    "stddevPop",
    "variance",
    "varPop",
    "median",
    "percentile",
)
AGGREGATE_DEFAULT_LIMIT = 20
AGGREGATE_MAX_LIMIT = 50
MAX_GROUP_BY = 3
MAX_ORDER_BY = 3

RELATED_DEFAULT_LIMIT = 50
RELATED_MAX_LIMIT = 200
RELATED_MAX_ORIGIN_IDS = 100


def get_dataset_schema(
    client: GeopackClient,
    dataset_id: int,
    *,
    include_domains: bool = False,
    include_relationships: bool = True,
) -> Dict[str, Any]:
    """Return the dataset's FIELD CONTRACT (the answer lane for "which fields").

    ``details.fields`` is read un-slimmed (domains survive, capped at 50
    values) — the opposite of :func:`get_dataset`'s ``_slim_fields``.

    Two side lanes are best-effort: ``GET /:id/access-context`` (a 403 leaves
    ``fieldAccess`` null plus a hint) and the relationship catalog. The
    effective access map is NEVER computed client-side (slice 011 §2.3).
    """
    dataset = to_jsonable(client.datasets.get(dataset_id))

    field_access: Optional[Dict[str, Any]] = None
    access_unavailable = False
    try:
        field_access = client.datasets.get_access_context(dataset_id)
    except GeopackError:
        access_unavailable = True

    relationship_rows: Optional[List[Dict[str, Any]]] = None
    catalog_unavailable = False
    relationships_unavailable = False
    if include_relationships:
        try:
            relationship_rows = build_relationship_rows(
                client.datasets.get_relationships(dataset_id)
            )
        except RelationshipCatalogUnavailable:
            catalog_unavailable = True
        except GeopackError:
            relationships_unavailable = True

    return build_dataset_schema(
        dataset,
        include_domains=include_domains,
        relationships=relationship_rows,
        field_access=field_access,
        access_unavailable=access_unavailable,
        catalog_unavailable=catalog_unavailable,
        relationships_unavailable=relationships_unavailable,
    )


def _normalize_aggregates(aggregates: Any) -> List[Dict[str, Any]]:
    """Validate aggregate specs client-side, before spending a round trip.

    Refusals raise :class:`ToolArgumentError` (slice 022 §1.2): the payload
    names the offending argument and the accepted enumeration, so the model
    fixes the call instead of collecting a server 400.
    """
    specs = list(aggregates) if isinstance(aggregates, (list, tuple)) else []
    if not specs:
        specs = [{"aggregate": "count"}]

    normalized: List[Dict[str, Any]] = []
    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise ToolArgumentError(
                "Each aggregate must be an object like {aggregate: 'sum', field: 'area'}",
                key=f"aggregates.{index}",
                hint="Pass aggregates as a list of {aggregate, field, alias?} objects.",
            )

        kind = spec.get("aggregate")
        if kind not in AGGREGATE_KINDS:
            raise ToolArgumentError(
                f"Unknown aggregate {kind!r}; use one of: {', '.join(AGGREGATE_KINDS)}",
                key=f"aggregates.{index}.aggregate",
                hint=(
                    "aggregates[].aggregate must be one of: "
                    f"{', '.join(AGGREGATE_KINDS)}."
                ),
            )

        entry: Dict[str, Any] = {"aggregate": kind}
        field = spec.get("field")
        if field:
            entry["field"] = str(field)
        elif kind != "count":
            raise ToolArgumentError(
                f"Aggregate {kind!r} needs a field name",
                key=f"aggregates.{index}.field",
                hint=(
                    "Call geopack_sdk_get_dataset_schema and pass an exact field name; "
                    "only count works without one."
                ),
            )
        if spec.get("alias"):
            entry["alias"] = str(spec["alias"])

        if kind == "percentile":
            p = spec.get("p")
            if p is None:
                raise ToolArgumentError(
                    "percentile requires p between 0 and 1",
                    key=f"aggregates.{index}.p",
                    hint="Set p (the percentile fraction, e.g. 0.9) on every percentile aggregate.",
                )
            p_value = float(p)
            if not 0.0 <= p_value <= 1.0:
                raise ToolArgumentError(
                    f"percentile p must be between 0 and 1 (got {p!r})",
                    key=f"aggregates.{index}.p",
                    hint="p is a fraction of the distribution: 0.0..1.0 (p=0.5 is the median).",
                )
            entry["p"] = p_value

        normalized.append(entry)

    return normalized


def _normalize_group_by(group_by: Any) -> List[Dict[str, Any]]:
    fields = [str(name).strip() for name in (group_by or []) if str(name).strip()]
    if len(fields) > MAX_GROUP_BY:
        raise ToolArgumentError(
            f"group_by accepts at most {MAX_GROUP_BY} fields",
            key="group_by",
            hint=f"Pass at most {MAX_GROUP_BY} field names in one call.",
        )
    return [{"field": name} for name in fields]


def _normalize_order_by(order_by: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for index, item in enumerate(order_by or []):
        if not isinstance(item, dict) or not item.get("key"):
            raise ToolArgumentError(
                'Each order_by entry needs a "key" (a groupBy field or an aggregate alias)',
                key=f"order_by.{index}.key",
                hint="Use a group_by field name or an aggregate alias as the order key.",
            )
        direction = str(item.get("direction") or "asc").strip().lower()
        if direction not in ("asc", "desc"):
            raise ToolArgumentError(
                'order_by direction must be "asc" or "desc"',
                key=f"order_by.{index}.direction",
                hint='Pass direction "asc" (default) or "desc".',
            )
        entry: Dict[str, Any] = {"key": item["key"], "direction": direction}
        if item.get("by"):
            entry["by"] = item["by"]
        entries.append(entry)
    if len(entries) > MAX_ORDER_BY:
        raise ToolArgumentError(
            f"order_by accepts at most {MAX_ORDER_BY} entries",
            key="order_by",
            hint=f"Pass at most {MAX_ORDER_BY} order entries in one call.",
        )
    return entries


def aggregate_dataset(
    client: GeopackClient,
    dataset_id: int,
    *,
    aggregates: Any = None,
    group_by: Any = None,
    order_by: Any = None,
    limit: int = AGGREGATE_DEFAULT_LIMIT,
    filter: Optional[Dict[str, Any]] = None,
    spatial_filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The answer-first lane: counts, sums, distributions and top-N in one call.

    The server payload is returned **verbatim** (``rows``/``columns``/
    ``metadata``) plus the normalized echo and ``rowCount``. No client-side
    math, no re-bucketing, no alias rewriting (slice 020 §2).
    """
    bucket_limit = int(limit)
    if not 1 <= bucket_limit <= AGGREGATE_MAX_LIMIT:
        raise ToolArgumentError(
            f"limit must be between 1 and {AGGREGATE_MAX_LIMIT} (got {limit!r})",
            key="limit",
            hint=f"limit is the number of buckets to return: 1..{AGGREGATE_MAX_LIMIT}.",
        )

    aggregation: Dict[str, Any] = {
        "aggregates": _normalize_aggregates(aggregates),
        "limit": bucket_limit,
    }
    grouped = _normalize_group_by(group_by)
    if grouped:
        aggregation["groupBy"] = grouped
    ordered = _normalize_order_by(order_by)
    if ordered:
        aggregation["orderBy"] = ordered

    try:
        result = client.datasets.aggregate(
            dataset_id,
            aggregation=aggregation,
            filter=filter,
            spatial_filter=spatial_filter,
        )
    except AggregationUnsupported as exc:
        return {
            "error": True,
            "type": "AggregationUnsupported",
            "status_code": exc.status_code,
            "code": exc.code,
            "message": exc.message,
            "hint": (
                "This datastore cannot aggregate. Use geopack_sdk_query_dataset and page "
                "the records instead."
            ),
        }
    except AggregationInvalidArgs as exc:
        return {
            "error": True,
            "type": "AggregationInvalidArgs",
            "status_code": exc.status_code,
            "code": exc.code,
            "key": getattr(exc, "key", None),
            "message": exc.message,
            "hint": (
                "Call geopack_sdk_get_dataset_schema and use an exact field name or alias."
            ),
        }

    payload = result.model_dump(by_alias=True, mode="json")
    payload["aggregationApplied"] = aggregation
    payload["rowCount"] = len(payload.get("rows") or [])
    return payload


def get_dataset_relationships(
    client: GeopackClient,
    dataset_id: int,
) -> Dict[str, Any]:
    """List the relationship NAMES valid for get_related_records.

    A coded 409 (``RelationshipCatalogUnavailable``) is a state, not an error:
    the tool degrades it to ``catalogUnavailable: true`` so the model does not
    burn turns retrying (slice 020 §3).
    """
    try:
        rows = build_relationship_rows(client.datasets.get_relationships(dataset_id))
    except RelationshipCatalogUnavailable:
        return {
            "datasetId": dataset_id,
            "relationships": [],
            "catalogUnavailable": True,
            "hint": (
                "This datastore has no authored relationship catalog; query the datasets "
                "directly."
            ),
        }

    payload: Dict[str, Any] = {
        "datasetId": dataset_id,
        "relationships": rows,
        "catalogUnavailable": False,
    }
    payload["hint"] = (
        "Pass one of these names (with OID values from a records query) to "
        "geopack_sdk_get_related_records."
        if rows
        else "No relationships are authored for this dataset; query it directly."
    )
    return payload


def get_related_records(
    client: GeopackClient,
    dataset_id: int,
    relationship_name: str,
    origin_object_ids: Sequence[int],
    *,
    direction: str = "forward",
    limit: int = RELATED_DEFAULT_LIMIT,
    offset: int = 0,
    return_geometry: bool = False,
) -> Dict[str, Any]:
    """Navigate one relationship leg: the records related to these records.

    ``return_geometry`` defaults to False (unlike ``query_dataset``): this lane
    answers *which* records, and geometry dominates the payload. ``__jct__*``
    properties are junction fields — kept verbatim beside the target record.
    """
    name = str(relationship_name or "").strip()
    if not name:
        raise ToolArgumentError(
            "relationship_name is required; call geopack_sdk_get_dataset_relationships first",
            key="relationship_name",
            hint=(
                "Call geopack_sdk_get_dataset_relationships and pass one of the names it "
                "returns; never invent one."
            ),
        )

    normalized_direction = str(direction or "forward").strip().lower()
    if normalized_direction not in ("forward", "backward"):
        raise ToolArgumentError(
            'direction must be "forward" or "backward"',
            key="direction",
            hint='Use "forward" (origin -> related) or "backward" (related -> origin).',
        )

    oids = [int(value) for value in (origin_object_ids or [])]
    if not oids:
        raise ToolArgumentError(
            "origin_object_ids needs at least one source OID",
            key="origin_object_ids",
            hint=(
                "Pass OID values from geopack_sdk_query_dataset; the OID field name is "
                "oidField in geopack_sdk_get_dataset_schema."
            ),
        )
    if len(oids) > RELATED_MAX_ORIGIN_IDS:
        raise ToolArgumentError(
            f"origin_object_ids accepts at most {RELATED_MAX_ORIGIN_IDS} ids per call; "
            "split the request",
            key="origin_object_ids",
            hint=f"Split into batches of at most {RELATED_MAX_ORIGIN_IDS} ids; one call per batch.",
        )

    effective_limit = max(1, min(int(limit), RELATED_MAX_LIMIT))
    effective_offset = max(0, int(offset))

    try:
        result = client.datasets.get_related_records(
            dataset_id,
            name,
            oids,
            direction=normalized_direction,
            limit=effective_limit,
            offset=effective_offset,
            return_geometry=return_geometry,
        )
    except GeopackAuthError as exc:
        if exc.status_code != 403:
            raise
        # Harness lesson: an unlabeled 403 sends the model down the wrong path.
        return {
            "error": True,
            "type": "GeopackAuthError",
            "status_code": exc.status_code,
            "message": exc.message,
            "hint": (
                "Access was denied on the RELATED dataset of this relationship, not on the "
                "origin dataset. Do not retry other relationship names; ask the user for "
                "access to the related dataset."
            ),
        }
    except QueryValidationError as exc:
        return {
            "error": True,
            "type": type(exc).__name__,
            "status_code": exc.status_code,
            "code": exc.code,
            "message": exc.message,
            "hint": (
                "Check the relationship name with geopack_sdk_get_dataset_relationships "
                "and the OID values against the oidField from geopack_sdk_get_dataset_schema."
            ),
        }

    payload = trim_feature_collection_for_mcp(to_jsonable(result))
    payload["groups"] = result.groups
    payload["queryLimitApplied"] = effective_limit
    payload["queryOffsetApplied"] = effective_offset
    if len(payload.get("features") or []) >= effective_limit:
        payload["featuresTruncated"] = True
        payload["hint"] = (
            "The page is full (rows == limit): more related records may exist. Raise limit "
            f"(max {RELATED_MAX_LIMIT}) or advance offset."
        )
    return payload
