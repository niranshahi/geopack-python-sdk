"""Translate an ESRI renderer into the portable layer-style spec (slice 033 §12).

One renderer-agnostic JSON object drives two consumers in the built-in viewer —
the vector style **function** and the **legend** — so the drawn map and the legend
can never disagree. The same spec is what ``show_map`` derives from a dataset's
saved ``display.esri.renderer`` and attaches to a ``portal-dataset`` layer, so a
layer shows the portal's intended colours instead of a generic palette colour.

This module is pure (no client, no heavy import) and lenient: anything it cannot
read is simply omitted. It mirrors the frontend's ESRI symbol handling — ESRI
colours are ``[r, g, b, a]`` with components in 0–255.

Shape (§12.1):

.. code-block:: json

    {
      "type": "simple | uniqueValue | classBreaks",
      "geometry": "polygon | line | point",
      "field": "Landuse_Group",
      "simple":  { "fill": "#1b9e77", "stroke": "#83817e", "weight": 0.75, "opacity": 0.77 },
      "unique":  [ { "value": "1", "label": "مسکونی", "style": { "...": "..." } } ],
      "breaks":  [ { "min": 0, "max": 100, "label": "0-100", "style": { "...": "..." } } ],
      "default": { "...": "..." },
      "legend":  { "title": "Landuse_Group", "entries": [ { "label": "مسکونی", "style": { "...": "..." } } ] }
    }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .dataset_symbology import field_meta_from_details, resolve_esri_display

#: ESRI symbol types, grouped by the geometry they draw.
_POLYGON_SYMBOLS = frozenset({"esriSFS", "esriSFSSolid"})
_LINE_SYMBOLS = frozenset({"esriSLS", "esriSLSSolid"})
_POINT_PREFIX = "esriSMS"
_POINT_SYMBOLS = frozenset({"esriPMS", "esriSMS"})

#: Default marker radius when the ESRI symbol carries no size.
_DEFAULT_RADIUS = 5


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clamp_byte(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(255, number))


def _to_hex(color: Any) -> Optional[str]:
    """An ESRI ``[r, g, b, (a)]`` colour as ``#rrggbb``; ``None`` if unusable."""
    if not isinstance(color, (list, tuple)) or len(color) < 3:
        return None
    channels = [_clamp_byte(color[index]) for index in range(3)]
    if any(channel is None for channel in channels):
        return None
    return "#%02x%02x%02x" % tuple(channels)  # type: ignore[arg-type]


def _alpha_opacity(color: Any) -> Optional[float]:
    """The ESRI alpha (0–255) as a 0–1 opacity; ``None`` when fully opaque/absent."""
    if not isinstance(color, (list, tuple)) or len(color) < 4:
        return None
    try:
        alpha = float(color[3])
    except (TypeError, ValueError):
        return None
    if alpha >= 255:
        return None
    return round(max(0.0, alpha / 255.0), 3)


def _symbol_style(symbol: Any) -> Dict[str, Any]:
    """An ESRI symbol as a portable ``{fill, stroke, weight, radius, opacity}``."""
    symbol = _as_dict(symbol)
    stype = symbol.get("type")
    style: Dict[str, Any] = {}

    if stype in _POLYGON_SYMBOLS:
        fill = _to_hex(symbol.get("color"))
        if fill:
            style["fill"] = fill
        outline = _as_dict(symbol.get("outline"))
        stroke = _to_hex(outline.get("color"))
        if stroke:
            style["stroke"] = stroke
        outline_width = outline.get("width")
        if isinstance(outline_width, (int, float)):
            style["weight"] = outline_width
        opacity = _alpha_opacity(symbol.get("color"))
        if opacity is not None:
            style["opacity"] = opacity
        return style

    if stype in _LINE_SYMBOLS:
        stroke = _to_hex(symbol.get("color"))
        if stroke:
            style["stroke"] = stroke
        width = symbol.get("width")
        if isinstance(width, (int, float)):
            style["weight"] = width
        opacity = _alpha_opacity(symbol.get("color"))
        if opacity is not None:
            style["opacity"] = opacity
        return style

    # Markers (and anything unrecognised) draw as points.
    fill = _to_hex(symbol.get("color"))
    if fill:
        style["fill"] = fill
    outline = _as_dict(symbol.get("outline"))
    stroke = _to_hex(outline.get("color")) or _to_hex(symbol.get("color"))
    if stroke:
        style["stroke"] = stroke
    size = symbol.get("size")
    if isinstance(size, (int, float)) and size > 0:
        style["radius"] = round(size / 2.0, 2)
    else:
        style["radius"] = _DEFAULT_RADIUS
    opacity = _alpha_opacity(symbol.get("color"))
    if opacity is not None:
        style["opacity"] = opacity
    return style


def _geometry_from_symbol(symbol: Any) -> Optional[str]:
    stype = _as_dict(symbol).get("type")
    if stype in _POLYGON_SYMBOLS:
        return "polygon"
    if stype in _LINE_SYMBOLS:
        return "line"
    if isinstance(stype, str) and (stype.startswith(_POINT_PREFIX) or stype in _POINT_SYMBOLS):
        return "point"
    return None


def _first_symbol(renderer: Dict[str, Any]) -> Any:
    """A representative symbol, to infer the geometry when the renderer mixes them."""
    for info in renderer.get("uniqueValueInfos") or []:
        if isinstance(info, dict) and info.get("symbol"):
            return info["symbol"]
    for info in renderer.get("classBreakInfos") or []:
        if isinstance(info, dict) and info.get("symbol"):
            return info["symbol"]
    return renderer.get("symbol") or renderer.get("defaultSymbol")


def _unique_entries(renderer: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``[{value, label, symbol}]`` from ``uniqueValueInfos`` or ``uniqueValueGroups``."""
    entries: List[Dict[str, Any]] = []
    infos = renderer.get("uniqueValueInfos")
    if isinstance(infos, list) and infos:
        for info in infos:
            info = _as_dict(info)
            value = info.get("value")
            if value is None and isinstance(info.get("values"), list) and info["values"]:
                value = info["values"][0]
            entries.append(
                {"value": value, "label": info.get("label"), "symbol": info.get("symbol")}
            )
        return entries
    groups = renderer.get("uniqueValueGroups")
    if isinstance(groups, list):
        for group in groups:
            for cls in _as_dict(group).get("classes") or []:
                cls = _as_dict(cls)
                values = cls.get("values")
                value = None
                if isinstance(values, list) and values:
                    first = values[0]
                    value = first[0] if isinstance(first, list) and first else first
                entries.append(
                    {"value": value, "label": cls.get("label"), "symbol": cls.get("symbol")}
                )
    return entries


def _legend_from_classes(
    classes: List[Dict[str, Any]], title: Optional[str]
) -> Dict[str, Any]:
    """The shared ``legend`` block for a set of ``unique``/``breaks`` classes.

    One source of truth for every path that builds a legend, so the drawn classes
    and the legend can never disagree. A class label falls back to its ``value``
    when the renderer/caller omitted one.
    """
    entries: List[Dict[str, Any]] = []
    for item in classes:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        if (label is None or label == "") and item.get("value") is not None:
            label = item.get("value")
        entries.append({"label": label, "style": item.get("style")})
    return {"title": title, "entries": entries}


def _simple_spec(style: Dict[str, Any], geometry: Optional[str]) -> Dict[str, Any]:
    # A single-class renderer needs no legend block; the layer's own legend swatch
    # (from `simple`) already shows the colour.
    return {"type": "simple", "geometry": geometry, "simple": style}


def _unique_spec(
    renderer: Dict[str, Any],
    geometry: Optional[str],
    labels: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    field = renderer.get("field1") or renderer.get("field")
    labels = labels or {}
    entries: List[Dict[str, Any]] = []
    for entry in _unique_entries(renderer):
        style = _symbol_style(entry.get("symbol"))
        label = entry.get("label")
        value = entry.get("value")
        if (label is None or label == "") and value is not None:
            # The renderer omitted a label: fall back to the field's coded-value
            # domain so the legend shows the human value, not the raw code.
            label = labels.get(str(value))
        entries.append({"value": value, "label": label, "style": style})
    default = _symbol_style(renderer.get("defaultSymbol"))
    spec: Dict[str, Any] = {
        "type": "uniqueValue",
        "geometry": geometry,
        "field": field,
        "unique": entries,
    }
    if default:
        spec["default"] = default
    spec["legend"] = _legend_from_classes(entries, field)
    return spec


def _breaks_spec(renderer: Dict[str, Any], geometry: Optional[str]) -> Dict[str, Any]:
    field = renderer.get("field") or renderer.get("field1")
    breaks: List[Dict[str, Any]] = []
    for info in renderer.get("classBreakInfos") or []:
        info = _as_dict(info)
        breaks.append(
            {
                "min": info.get("classMinValue", info.get("minValue")),
                "max": info.get("classMaxValue", info.get("maxValue")),
                "label": info.get("label"),
                "style": _symbol_style(info.get("symbol")),
            }
        )
    default = _symbol_style(renderer.get("defaultSymbol"))
    spec: Dict[str, Any] = {
        "type": "classBreaks",
        "geometry": geometry,
        "field": field,
        "breaks": breaks,
    }
    if default:
        spec["default"] = default
    spec["legend"] = _legend_from_classes(breaks, field)
    return spec


def esri_renderer_to_spec(
    renderer: Any, *, labels: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """Translate an ESRI ``renderer`` object into the portable spec (or ``None``).

    ``labels`` is an optional ``{str(code): humanLabel}`` coded-value domain, used
    only when a unique-value entry carries no label of its own.
    """
    renderer = _as_dict(renderer)
    rtype = renderer.get("type")
    if not isinstance(rtype, str):
        return None
    geometry = _geometry_from_symbol(_first_symbol(renderer))

    if rtype == "uniqueValue":
        return _unique_spec(renderer, geometry, labels)
    if rtype == "classBreaks":
        return _breaks_spec(renderer, geometry)
    if rtype == "simple":
        return _simple_spec(_symbol_style(renderer.get("symbol")), geometry)

    # A renderer family we do not translate yet (pieChart, raster*): a caller can
    # still pass an explicit `style`; the viewer falls back to the palette.
    return None


#: Colours for a data-derived categorical (unique-value) symbology.
CATEGORICAL_PALETTE = (
    "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02",
    "#a6761d", "#666666", "#1f78b4", "#b2df8a", "#fb9a99", "#cab2d6",
)

#: Sequential ramp for a data-derived class-breaks symbology (low → high).
SEQUENTIAL_PALETTE = ("#ffffcc", "#a1dab4", "#41b6c4", "#2c7fb8", "#253494")

#: Outline used by a data-derived symbol (a subtle neutral border).
_DERIVED_STROKE = "#4d4d4d"


def _numeric(values: Any) -> List[float]:
    numbers: List[float] = []
    for value in values or []:
        if isinstance(value, bool):
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return numbers


def _ramp_color(palette: Any, index: int, total: int) -> str:
    if total <= 1:
        return palette[len(palette) // 2]
    if total <= len(palette):
        return palette[index]
    return palette[round(index * (len(palette) - 1) / (total - 1))]


def _format_range(low: float, high: float) -> str:
    def fmt(number: float) -> str:
        return str(int(number)) if float(number).is_integer() else "%.2f" % number

    return f"{fmt(low)} – {fmt(high)}"


def field_values_from_geojson(geojson: Any, field: str) -> List[Any]:
    """The ``field`` values from a GeoJSON FeatureCollection, in feature order."""
    values: List[Any] = []
    if not isinstance(geojson, dict):
        return values
    for feature in geojson.get("features") or []:
        props = feature.get("properties") if isinstance(feature, dict) else None
        if isinstance(props, dict) and field in props:
            values.append(props.get(field))
    return values


def categorical_spec(
    field: str,
    values: Any,
    *,
    domain: Optional[Dict[str, str]] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """A ``uniqueValue`` spec with one palette colour per distinct ``values`` entry.

    ``domain`` is a ``{str(code): humanLabel}`` coded-value domain; when present a
    legend entry shows the human label instead of the raw code. ``title`` (usually
    the field alias) is the legend heading.
    """
    domain = domain or {}
    seen: List[Any] = []
    for raw in values or []:
        key = "" if raw is None else str(raw)
        if key not in [entry[0] for entry in seen]:
            seen.append((key, raw))
    entries: List[Dict[str, Any]] = []
    for index, (key, raw) in enumerate(seen):
        label = domain.get(key) or key or "(no value)"
        entries.append(
            {
                "value": raw,
                "label": label,
                "style": {
                    "fill": CATEGORICAL_PALETTE[index % len(CATEGORICAL_PALETTE)],
                    "stroke": _DERIVED_STROKE,
                    "weight": 0.5,
                },
            }
        )
    return {
        "type": "uniqueValue",
        "geometry": "polygon",
        "field": field,
        "unique": entries,
        "legend": _legend_from_classes(entries, title or field),
    }


def quantile_breaks(values: Any, classes: int) -> List[Any]:
    """``classes`` contiguous quantile ``(low, high)`` pairs from numeric values."""
    numbers = sorted(_numeric(values))
    if not numbers or classes < 1:
        return []
    count = len(numbers)
    edges = [numbers[0]]
    for i in range(1, classes):
        edges.append(numbers[min(count - 1, int(round(i * count / classes)))])
    edges.append(numbers[-1])
    breaks: List[Any] = []
    for i in range(classes):
        low, high = edges[i], edges[i + 1]
        if high < low:
            high = low
        breaks.append((low, high))
    return breaks


def breaks_spec(
    field: str, breaks: Any, *, title: Optional[str] = None
) -> Dict[str, Any]:
    """A ``classBreaks`` spec with a sequential ramp colour per class."""
    total = len(breaks) or 1
    entries: List[Dict[str, Any]] = []
    for index, (low, high) in enumerate(breaks or []):
        entries.append(
            {
                "min": low,
                "max": high,
                "label": _format_range(low, high),
                "style": {
                    "fill": _ramp_color(SEQUENTIAL_PALETTE, index, total),
                    "stroke": _DERIVED_STROKE,
                    "weight": 0.5,
                },
            }
        )
    return {
        "type": "classBreaks",
        "geometry": "polygon",
        "field": field,
        "breaks": entries,
        "legend": _legend_from_classes(entries, title or field),
    }


def ensure_legend(spec: Any, *, title: Optional[str] = None) -> Any:
    """Return ``spec`` with a derived ``legend`` when its classes carry none.

    A caller-authored COMPLETE spec (already holding ``unique``/``breaks``) is used
    verbatim, but if it omits a ``legend`` the viewer's panel would render blank.
    We synthesise one from the spec's own classes — exactly the rule the dataset's
    saved-renderer path follows — so every drawn class is explained. An explicit
    caller ``legend`` (one carrying entries) is always honoured.

    ``title`` overrides the heading (usually the field alias); otherwise the spec's
    own ``field`` is used. A non-dict spec is returned unchanged.
    """
    if not isinstance(spec, dict):
        return spec
    existing = spec.get("legend")
    if isinstance(existing, dict) and existing.get("entries"):
        return spec
    stype = spec.get("type")
    if stype == "classBreaks" or (stype is None and spec.get("breaks")):
        classes = spec.get("breaks") or []
    elif stype in (None, "uniqueValue") or spec.get("unique"):
        classes = spec.get("unique") or []
    else:
        return spec
    entries = [item for item in classes if isinstance(item, dict)]
    if not entries:
        return spec
    heading = title or (spec.get("field") if isinstance(spec.get("field"), str) else None)
    out = dict(spec)
    out["legend"] = _legend_from_classes(entries, heading)
    return out


def dataset_style_spec(record: Any) -> Optional[Dict[str, Any]]:
    """The portable spec for a dataset's saved vector renderer; ``None`` if none.

    ``record`` is the raw dataset record (its ``details`` may be a JSON string).
    Only vector/table renderers are translated — a raster display block has no
    client-side symbol to map.
    """
    record = _as_dict(record)
    data_type = str(record.get("dataType") or record.get("type") or "").lower()
    if data_type == "raster":
        return None
    details = record.get("details")
    if isinstance(details, str):
        import json

        try:
            details = json.loads(details) if details.strip() else {}
        except ValueError:
            details = {}
    details_dict = _as_dict(details)
    display = resolve_esri_display(details_dict)
    if display is None:
        return None
    renderer = _as_dict(display.get("renderer"))
    field = renderer.get("field1") or renderer.get("field")
    labels = None
    if isinstance(field, str) and field:
        labels = (field_meta_from_details(details_dict).get(field) or {}).get("domain") or None
    return esri_renderer_to_spec(renderer, labels=labels)
