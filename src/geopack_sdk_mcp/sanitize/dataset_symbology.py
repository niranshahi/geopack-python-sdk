"""Detect a dataset's SAVED rendering (symbology) for MCP disclosure.

A portal dataset may carry a default display in ``details.display``: an ESRI
renderer + labeling for vector/table data, or a raster display block
(``displayType`` RGB/colorMap + bands) for rasters. The frontend applies it when a
dataset is added as a layer; the MCP does **not** render it, so an agent must be
TOLD the dataset has its own symbology — otherwise it silently shows the generic
viewer palette and never discovers the official rendering (owner report,
dataset 1577, 2026-11-23).

The precedence mirrors the frontend contract EXACTLY
(``frontend-ui/src/utils/displayMigration.js`` ``getDisplaySettings`` +
``features/arcgis/utils.js`` ``getDatasetEsriDisplay``):

* vector/table — ``details.display.esri`` (unwrap a nested ``.display``) →
  ``details.esri.display`` → ``details.esri`` → ``details.display.default`` →
  flat ``details.display`` when it carries ``renderer``/``labelingInfo``/
  ``labelsVisible``.
* raster — flat ``details.display`` (it carries ``displayType``) →
  ``details.display.esri.display`` → ``details.display.esri``.

Both ``details`` and the whole dataset record may arrive as a JSON string (the
portal sends a string for most datasets). The summary is tiny — safe to attach to
every list row. This module is pure (no client, no heavy import): the portal
publication probe lives in :func:`styled_publications`, which takes a client.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..serialize import to_jsonable

#: ESRI renderer types that are really raster renderers (kind = "raster").
_RASTER_RENDERER_PREFIX = "raster"

#: Friendly labels for the portable renderer kinds the rest of the stack uses
#: (mirrors the frontend ``rendererTypeLabel``).
_RENDERER_LABELS = {
    "simple": "simple",
    "uniqueValue": "unique-value",
    "classBreaks": "class-breaks",
    "pieChart": "pie-chart",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    """Coerce a details/record value (object **or** JSON string) to a dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _has_display_shape(block: Dict[str, Any]) -> bool:
    """True when a block looks like an ESRI display (renderer/labels/type)."""
    return bool(
        block.get("renderer")
        or block.get("labelingInfo")
        or block.get("displayType")
        or "labelsVisible" in block
    )


def resolve_esri_display(details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The ESRI display block, following the frontend precedence; ``None`` if none."""
    display = details.get("display")
    display = display if isinstance(display, dict) else {}

    esri = display.get("esri")
    if isinstance(esri, dict):
        nested = esri.get("display")
        if isinstance(nested, dict) and nested.get("displayType"):
            return nested
        if _has_display_shape(esri):
            return esri

    legacy = details.get("esri")
    if isinstance(legacy, dict):
        nested = legacy.get("display")
        if isinstance(nested, dict) and nested.get("displayType"):
            return nested
        if _has_display_shape(legacy):
            return legacy

    default = display.get("default")
    if isinstance(default, dict) and default.get("displayType"):
        return default
    if _has_display_shape(display):
        return display
    return None


def resolve_raster_display(details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The raster display block (``displayType``), frontend precedence; else ``None``."""
    display = details.get("display")
    if isinstance(display, dict):
        if display.get("displayType"):
            return display
        esri = display.get("esri")
        if isinstance(esri, dict):
            nested = esri.get("display")
            if isinstance(nested, dict) and nested.get("displayType"):
                return nested
            if esri.get("displayType"):
                return esri
    return None


def _esri_summary(block: Dict[str, Any]) -> Dict[str, Any]:
    renderer = block.get("renderer")
    renderer = renderer if isinstance(renderer, dict) else {}
    renderer_type = renderer.get("type")
    is_raster = isinstance(renderer_type, str) and renderer_type.startswith(
        _RASTER_RENDERER_PREFIX
    )
    summary: Dict[str, Any] = {
        "hasSavedStyle": True,
        "kind": "raster" if is_raster else "vector",
        "rendererFamily": "esri",
        "rendererType": renderer_type,
    }
    if not is_raster and isinstance(renderer_type, str):
        summary["rendererLabel"] = _RENDERER_LABELS.get(renderer_type, renderer_type)

    fields = [renderer[key] for key in ("field1", "field2", "field3") if renderer.get(key)]
    if fields:
        summary["fields"] = fields

    for key in ("classBreakInfos",):
        infos = renderer.get(key)
        if isinstance(infos, list):
            summary["classCount"] = len(infos)
    groups = renderer.get("uniqueValueGroups")
    if "classCount" not in summary and isinstance(groups, list) and groups:
        first = groups[0]
        classes = first.get("classes") if isinstance(first, dict) else None
        if isinstance(classes, list):
            summary["classCount"] = len(classes)

    labeling = block.get("labelingInfo")
    if isinstance(labeling, list) and labeling:
        summary["labelingCount"] = len(labeling)
        first = labeling[0]
        if isinstance(first, dict):
            if first.get("labelExpression") is not None:
                summary["labelExpression"] = first["labelExpression"]
            info = first.get("labelExpressionInfo")
            if isinstance(info, dict) and info.get("expression"):
                summary["labelExpression"] = info["expression"]

    if "labelsVisible" in block:
        summary["labelsVisible"] = bool(block["labelsVisible"])

    summary["note"] = (
        "This dataset carries its own saved display; the MCP does not apply it. To see "
        "the official symbology use a portal-publication (WMS/WMTS) layer or pass an "
        "explicit style."
    )
    return summary


def _raster_summary(block: Dict[str, Any]) -> Dict[str, Any]:
    display_type = block.get("displayType")
    summary: Dict[str, Any] = {
        "hasSavedStyle": True,
        "kind": "raster",
        "rendererFamily": "raster",
        "rasterDisplayType": display_type,
        "rendererType": None,
    }
    if display_type == "RGB":
        bands = {
            key: block[key]
            for key in ("RBand", "GBand", "BBand", "ABand")
            if block.get(key) is not None
        }
        if bands:
            summary["bands"] = bands
    elif display_type == "colorMap":
        if block.get("band") is not None:
            summary["band"] = block["band"]
        if block.get("colorMap") is not None:
            summary["colorMap"] = block["colorMap"]
    summary["note"] = (
        "This raster dataset carries a saved display (bands / color map); the MCP map "
        "viewer does not render it. Use a raster portal-publication (WMS/WMTS) to see "
        "the server rendering."
    )
    return summary


def summarise_symbology(dataset: Any) -> Dict[str, Any]:
    """A tiny summary of a dataset's saved rendering, for disclosure.

    Returns ``{"hasSavedStyle": false, "kind": "none"}`` when nothing is stored, so
    a caller can always attach it to a row. A raster dataset is checked for its
    flat ``display`` first, then for an ESRI raster renderer.
    """
    record = _as_dict(dataset)
    details = _as_dict(record.get("details"))
    data_type = str(record.get("dataType") or record.get("type") or "").lower()

    if data_type == "raster":
        raster = resolve_raster_display(details)
        if raster is not None:
            return _raster_summary(raster)

    esri = resolve_esri_display(details)
    if esri is not None and esri.get("renderer"):
        return _esri_summary(esri)

    if data_type == "raster":
        raster = resolve_raster_display(details)
        if raster is not None:
            return _raster_summary(raster)

    if esri is not None:
        # A display with only labeling / labelsVisible (no renderer) is still a
        # saved display the agent should know about.
        return _esri_summary(esri)

    return {"hasSavedStyle": False, "kind": "none"}


def styled_publications(client: Any, dataset_id: int) -> List[Dict[str, Any]]:
    """The dataset's publications, each flagged with whether it carries a style.

    A publication is *styled* when its ``canonicalStyleRevision`` is set (a custom
    SLD override **or** the dataset's own display projected to SLD) — the path that
    renders the official symbology for dataset 1577. Never raises.
    """
    try:
        publications = client.publications.list_for_dataset(dataset_id)
    except Exception:  # noqa: BLE001 - discovery is best-effort
        return []

    rows: List[Dict[str, Any]] = []
    for publication in publications or []:
        raw = to_jsonable(publication)
        record = raw.get("raw") if isinstance(raw, dict) else None
        record = record if isinstance(record, dict) else (raw if isinstance(raw, dict) else {})
        configuration = record.get("configuration")
        configuration = configuration if isinstance(configuration, dict) else {}
        revision = record.get("canonicalStyleRevision")
        has_style = bool(revision) or bool(configuration.get("styleOverride"))
        rows.append(
            {
                "publicationId": record.get("id"),
                "datasetId": record.get("datasetId"),
                "protocol": record.get("protocol"),
                "status": record.get("status"),
                "visibility": record.get("visibility"),
                "hasStyle": has_style,
                "styleRevision": revision,
            }
        )
    return rows
