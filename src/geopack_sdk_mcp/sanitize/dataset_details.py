"""Trim dataset ``details`` for MCP tool output (avoid multi‑MB tilejson in list)."""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Literal, Optional, Union

from ..errors import ToolArgumentError

DetailsLevel = Literal["lite", "standard", "full"]
# Legacy aliases used internally before v0.5
DetailsProfile = Literal["list", "get"]

_LIST_DROP_TOP_LEVEL = frozenset(
    {
        "tilejson",
        "thumbnail",
        "metadata_4326",
        "metadata_3857",
        "pgisMetadata",
        "display",
    }
)

_GET_RASTER_OMIT_KEYS = frozenset({"metadata_4326", "metadata_3857", "pgisMetadata", "thumbnail"})

_SR_STRIP_KEYS = frozenset({"wkt", "proj4", "srsName"})

#: Top-level keys a dataset record may carry. ``fields`` projection refuses a
#: name outside this set instead of silently answering nothing (live-QA 2026-11-21).
DATASET_TOP_LEVEL_KEYS = frozenset(
    {
        "id",
        "name",
        "description",
        "dataType",
        "subType",
        "keywords",
        "ownerUserId",
        "workgroupId",
        "dataStoreId",
        "details",
        "status",
        "createdAt",
        "updatedAt",
        "owner",
        "workgroup",
        "dataStore",
        "hasThumbnail",
        "thumbnailApiPath",
        "thumbnailMintPath",
        "thumbnailResourceUri",
        # stored WGS84 extent (may be null for rasters) and per-dataset publications
        "ext_west",
        "ext_south",
        "ext_east",
        "ext_north",
        "publicationsSummary",
        # synthetic, derived from details.geo_extent — request the exact WGS84
        # box without pulling the whole (large) `details` blob
        "geo_extent",
        "details.geo_extent",
        # present only on a degraded (unparseable) row — kept projectable
        "validationDegraded",
        "validationErrors",
        "rawRecord",
    }
)

#: ``bbox`` filters on the stored dataset extent; say so instead of letting a
#: caller assume it is a geometric intersection (backend fix tracked as BE-009).
EXTENT_FILTER_NOTE = (
    "bbox filters on the STORED dataset extent (ext_west/south/east/north), not on "
    "feature geometry. Datasets whose stored extent is null (common for rasters) are "
    "not matched — do not read a short list as 'nothing there'."
)


#: ``fields`` names that ask for the derived, labelled WGS84 extent.
GEO_EXTENT_FIELDS = frozenset({"geo_extent", "details.geo_extent"})


def wants_geo_extent(fields: Optional[List[str]]) -> bool:
    """True when ``fields`` asks for ``geo_extent`` (or ``details.geo_extent``)."""
    return bool(fields) and any(name in GEO_EXTENT_FIELDS for name in fields)


def _as_wgs84_bbox(value: Any) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        west, south, east, north = (float(part) for part in value)
    except (TypeError, ValueError):
        return None
    if abs(west) > 180 or abs(east) > 180 or abs(south) > 90 or abs(north) > 90:
        return None
    if west >= east or south >= north:
        return None
    return [west, south, east, north]


def _geo_extent_object(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Derive a labelled WGS84 extent from ``details.geo_extent`` / ``ext_*``.

    ``details`` may be an object or a JSON string (the portal sends a string for
    most datasets). Returns ``{bbox, crs, axisOrder}`` — the shape agents can use
    without guessing the axis order.
    """
    details = record.get("details")
    if isinstance(details, str):
        try:
            parsed = json.loads(details)
        except json.JSONDecodeError:
            parsed = None
        details = parsed if isinstance(parsed, dict) else {}
    if not isinstance(details, dict):
        details = {}
    bbox = _as_wgs84_bbox(details.get("geo_extent") or details.get("geoExtent"))
    if bbox is None:
        bbox = _as_wgs84_bbox(
            [
                record.get("ext_west"),
                record.get("ext_south"),
                record.get("ext_east"),
                record.get("ext_north"),
            ]
        )
    if bbox is None:
        return None
    return {"bbox": bbox, "crs": "EPSG:4326", "axisOrder": "west,south,east,north"}


def normalize_fields(fields: Any) -> Optional[List[str]]:
    """Accept a list (or a comma-separated string) of top-level field names."""
    if fields is None:
        return None
    if isinstance(fields, str):
        raw = [part.strip() for part in fields.split(",")]
    elif isinstance(fields, (list, tuple, set)):
        raw = [str(part).strip() for part in fields]
    else:
        raise ToolArgumentError(
            "fields must be a list of dataset field names (or a comma-separated string).",
            key="fields",
            hint="Pass e.g. [\"id\",\"name\",\"dataType\",\"createdAt\"].",
        )
    names = [name for name in dict.fromkeys(raw) if name]
    return names or None


def validate_projection_fields(fields: Optional[List[str]]) -> None:
    """Refuse an unknown projection key up front (even when the page is empty)."""
    if not fields:
        return
    unknown = sorted(name for name in fields if name not in DATASET_TOP_LEVEL_KEYS)
    if unknown:
        raise ToolArgumentError(
            f"Unknown field(s) in fields: {', '.join(unknown)}",
            key="fields",
            hint=(
                "fields may only name top-level dataset keys: "
                f"{', '.join(sorted(DATASET_TOP_LEVEL_KEYS))}."
            ),
        )


def project_dataset_keys(
    record: Dict[str, Any],
    fields: Optional[List[str]],
) -> Dict[str, Any]:
    """Keep only the requested top-level keys (``id`` is always kept).

    An unknown name is a client-side refusal that lists the accepted set — a
    projection that silently returns nothing is indistinguishable from an empty
    record.
    """
    if not fields or not isinstance(record, dict):
        return record

    validate_projection_fields(fields)

    wants_geo = wants_geo_extent(fields)
    source = record
    if wants_geo and "geo_extent" not in record:
        derived = _geo_extent_object(record)
        if derived is not None:
            source = dict(record)
            source["geo_extent"] = derived

    projected = {
        name: source[name]
        for name in fields
        if name in source and name not in GEO_EXTENT_FIELDS
    }
    if wants_geo and "geo_extent" in source:
        projected["geo_extent"] = source["geo_extent"]
    if "id" in record:
        projected["id"] = record["id"]
    return projected


def normalize_details_level(
    level: Optional[str],
    *,
    default: DetailsLevel,
) -> DetailsLevel:
    """Parse tool ``details_level``; accept legacy ``list`` / ``get`` aliases."""
    if level is None:
        return default
    normalized = level.strip().lower()
    if normalized in ("lite", "standard", "full"):
        return normalized  # type: ignore[return-value]
    if normalized == "list":
        return "lite"
    if normalized == "get":
        return "full"
    raise ToolArgumentError(
        f"Invalid details_level {level!r}; use lite, standard, or full.",
        key="details_level",
        hint=(
            "details_level is lite | standard | full (defaults: lite for lists, full for "
            "a single dataset)."
        ),
    )


def parse_details(details: Any) -> Optional[Dict[str, Any]]:
    if details is None:
        return None
    if isinstance(details, dict):
        return details
    if isinstance(details, str):
        if not details.strip():
            return None
        try:
            parsed = json.loads(details)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _strip_tilestats_values(tilestats: Any, *, omit_values: bool) -> Any:
    if not isinstance(tilestats, dict):
        return tilestats

    out = copy.deepcopy(tilestats)
    layers: List[Any] = out.get("layers") or []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for attribute in layer.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            values = attribute.get("values")
            if not isinstance(values, list):
                continue
            if omit_values:
                attribute.pop("values", None)
                attribute["valuesOmitted"] = True
                attribute["valuesCount"] = len(values)
            elif len(values) > 50:
                attribute["values"] = values[:50]
                attribute["valuesTruncated"] = True
                attribute["valuesTotal"] = len(values)
    return out


def _omit_raster_metadata_blob(value: Any) -> Dict[str, Any]:
    hint: Dict[str, Any] = {"_omitted": True}
    if isinstance(value, dict):
        for key in ("srid", "width", "height", "size", "dataType", "driver"):
            if key in value:
                hint[key] = value[key]
    return hint


def _slim_spatial_reference(spatial_ref: Any) -> Any:
    if not isinstance(spatial_ref, dict):
        return spatial_ref
    slim = dict(spatial_ref)
    for key in _SR_STRIP_KEYS:
        slim.pop(key, None)
    return slim


def _omit_display_blob(display: Any) -> Dict[str, Any]:
    """Replace portal symbology (renderer/labeling) with a tiny summary for LLM tools."""
    hint: Dict[str, Any] = {"_omitted": True, "reason": "portal_map_symbology"}
    if not isinstance(display, dict):
        return hint
    esri = display.get("esri")
    if not isinstance(esri, dict):
        return hint
    renderer = esri.get("renderer")
    if isinstance(renderer, dict):
        hint["rendererType"] = renderer.get("type")
        for key in ("field1", "field2", "field3"):
            if key in renderer:
                hint[key] = renderer[key]
        groups = renderer.get("uniqueValueGroups") or []
        if groups and isinstance(groups[0], dict):
            classes = groups[0].get("classes") or []
            if isinstance(classes, list):
                hint["classCount"] = len(classes)
    labeling = esri.get("labelingInfo")
    if isinstance(labeling, list) and labeling:
        hint["labelingCount"] = len(labeling)
        first = labeling[0]
        if isinstance(first, dict):
            if "labelExpression" in first:
                hint["labelExpression"] = first["labelExpression"]
            info = first.get("labelExpressionInfo")
            if isinstance(info, dict) and info.get("expression"):
                hint["labelExpression"] = info["expression"]
    return hint


def _slim_fields(fields: Any) -> List[Dict[str, Any]]:
    slimmed: List[Dict[str, Any]] = []
    if not isinstance(fields, list):
        return slimmed
    for field in fields:
        if not isinstance(field, dict):
            continue
        slimmed.append(
            {
                key: field[key]
                for key in ("name", "alias", "type", "nullable")
                if key in field
            }
        )
    return slimmed


def _apply_lite(out: Dict[str, Any]) -> Dict[str, Any]:
    for key in _LIST_DROP_TOP_LEVEL:
        out.pop(key, None)

    if "tilestats" in out:
        out["tilestats"] = _strip_tilestats_values(out.get("tilestats"), omit_values=True)

    fields = out.get("fields")
    if isinstance(fields, list):
        out["fieldsCount"] = len(fields)
        out.pop("fields", None)

    if "spatialReference" in out:
        out["spatialReference"] = _slim_spatial_reference(out["spatialReference"])

    return out


def trim_details(details: Any, level: Union[DetailsLevel, DetailsProfile]) -> Any:
    """
    Return trimmed details dict for MCP (never mutates the input).

    - ``lite``: smallest payload (default for list tools).
    - ``standard``: lite + field name/type list.
    - ``full``: single-dataset view; keep tilejson, omit tilestats values.
    """
    if level in ("list", "get"):
        level = "lite" if level == "list" else "full"

    parsed = parse_details(details)
    if parsed is None:
        return details

    out = copy.deepcopy(parsed)

    if level == "lite":
        return _apply_lite(out)

    if level == "standard":
        out = _apply_lite(out)
        fields = parsed.get("fields")
        if isinstance(fields, list):
            out["fields"] = _slim_fields(fields)
            out["fieldsCount"] = len(fields)
        return out

    # level == "full" — keep tilejson (MVT hints) but drop portal UI symbology
    if "display" in out:
        out["display"] = _omit_display_blob(out["display"])

    for key in ("thumbnail",):
        out.pop(key, None)

    tilejson = out.get("tilejson")
    if isinstance(tilejson, dict):
        if isinstance(tilejson.get("tilestats"), dict):
            tilejson["tilestats"] = _strip_tilestats_values(
                tilejson["tilestats"], omit_values=True
            )

    if "tilestats" in out:
        out["tilestats"] = _strip_tilestats_values(out.get("tilestats"), omit_values=True)

    fields = out.get("fields")
    if isinstance(fields, list):
        out["fields"] = _slim_fields(fields)
        out["fieldsCount"] = len(fields)

    data_type = out.get("dataType") or out.get("type")
    if data_type == "raster":
        for key in _GET_RASTER_OMIT_KEYS:
            if key in out:
                out[key] = _omit_raster_metadata_blob(out[key])

    if "spatialReference" in out:
        out["spatialReference"] = _slim_spatial_reference(out["spatialReference"])

    return out


def trim_dataset_for_mcp(
    dataset: Dict[str, Any],
    level: Union[DetailsLevel, DetailsProfile] = "lite",
    *,
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Apply details trimming to one dataset record (after ``model_dump``).

    ``fields`` projects the top-level keys afterwards — a record here is a single
    ``get_dataset`` answer, so ``lite`` still keeps its (trimmed) ``details``.
    """
    if not isinstance(dataset, dict):
        return dataset

    trimmed = dict(dataset)
    if "details" in trimmed:
        trimmed["details"] = trim_details(trimmed["details"], level)
    return project_dataset_keys(trimmed, fields)


def trim_datasets_list_payload(
    payload: Dict[str, Any],
    *,
    details_level: DetailsLevel = "lite",
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Trim each dataset in a ``DatasetsApiResponse``-shaped dict.

    In a LIST, ``lite`` is a true card: the ``details`` blob is dropped (a list
    of 264 vectors is otherwise ~392 KB). ``standard``/``full`` keep the trimmed
    details; an explicit ``fields`` including ``details`` keeps it too.
    """
    if not isinstance(payload, dict):
        return payload

    out = dict(payload)
    datasets = out.get("datasets")
    if isinstance(datasets, list):
        normalized: List[Any] = []
        for ds in datasets:
            if not isinstance(ds, dict):
                normalized.append(ds)
                continue
            row = trim_dataset_for_mcp(ds, details_level)
            keep_details = fields is not None and (
                "details" in fields or wants_geo_extent(fields)
            )
            if details_level == "lite" and not keep_details:
                row.pop("details", None)
                row["detailsOmitted"] = True
            normalized.append(project_dataset_keys(row, fields))
        out["datasets"] = normalized
    return out
