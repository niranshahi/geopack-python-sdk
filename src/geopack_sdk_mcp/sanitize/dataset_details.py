"""Trim dataset ``details`` for MCP tool output (avoid multi‑MB tilejson in list)."""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Literal, Optional, Union

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
    raise ValueError(
        f"Invalid details_level {level!r}; use lite, standard, or full."
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

    # level == "full"
    tilejson = out.get("tilejson")
    if isinstance(tilejson, dict):
        if isinstance(tilejson.get("tilestats"), dict):
            tilejson["tilestats"] = _strip_tilestats_values(
                tilejson["tilestats"], omit_values=True
            )

    if "tilestats" in out:
        out["tilestats"] = _strip_tilestats_values(out.get("tilestats"), omit_values=True)

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
) -> Dict[str, Any]:
    """Apply details trimming to one dataset record (after ``model_dump``)."""
    if not isinstance(dataset, dict):
        return dataset

    trimmed = dict(dataset)
    if "details" in trimmed:
        trimmed["details"] = trim_details(trimmed["details"], level)
    return trimmed


def trim_datasets_list_payload(
    payload: Dict[str, Any],
    *,
    details_level: DetailsLevel = "lite",
) -> Dict[str, Any]:
    """Trim each dataset in a ``DatasetsApiResponse``-shaped dict."""
    if not isinstance(payload, dict):
        return payload

    out = dict(payload)
    datasets = out.get("datasets")
    if isinstance(datasets, list):
        out["datasets"] = [
            trim_dataset_for_mcp(ds, details_level) if isinstance(ds, dict) else ds
            for ds in datasets
        ]
    return out
