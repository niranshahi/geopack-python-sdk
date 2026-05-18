"""Trim dataset ``details`` for MCP tool output (avoid multi‑MB tilejson in list)."""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Literal, Optional, Union

DetailsProfile = Literal["list", "get"]

# Keys often large in vector MVT dataset details
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


def trim_details(details: Any, profile: DetailsProfile) -> Any:
    """
    Return trimmed details dict for MCP (never mutates the input).

    - ``list``: drop tilejson and other heavy keys; summarize field lists.
    - ``get``: keep tilejson but omit tilestats value arrays; trim raster metadata blobs.
    """
    parsed = parse_details(details)
    if parsed is None:
        return details

    out = copy.deepcopy(parsed)

    if profile == "list":
        for key in _LIST_DROP_TOP_LEVEL:
            out.pop(key, None)

        if "tilestats" in out:
            out["tilestats"] = _strip_tilestats_values(out.get("tilestats"), omit_values=True)

        fields = out.get("fields")
        if isinstance(fields, list):
            out["fieldsCount"] = len(fields)
            out.pop("fields", None)

        return out

    # profile == "get"
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

    return out


def trim_dataset_for_mcp(dataset: Dict[str, Any], profile: DetailsProfile) -> Dict[str, Any]:
    """Apply details trimming to one dataset record (after ``model_dump``)."""
    if not isinstance(dataset, dict):
        return dataset

    trimmed = dict(dataset)
    if "details" in trimmed:
        trimmed["details"] = trim_details(trimmed["details"], profile)
    return trimmed


def trim_datasets_list_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Trim each dataset in a ``DatasetsApiResponse``-shaped dict."""
    if not isinstance(payload, dict):
        return payload

    out = dict(payload)
    datasets = out.get("datasets")
    if isinstance(datasets, list):
        out["datasets"] = [
            trim_dataset_for_mcp(ds, "list") if isinstance(ds, dict) else ds
            for ds in datasets
        ]
    return out
