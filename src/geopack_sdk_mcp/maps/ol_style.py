"""Translate a portal raster ``display`` into an OpenLayers WebGL style.

A COG is drawn client-side by ``ol/source/GeoTIFF`` + ``ol/layer/WebGLTile``.
Unlike the server-rendered ``rastertile`` lane, no portal call can apply the
saved symbology, so this module builds the equivalent OpenLayers style
expression (``style.color``) from the same ``display`` object:

* ``colorMap`` (single band) → ``['interpolate', ['linear'], ['band', n], ...]``
  with absolute stop values and ``[r,g,b,a]`` colours (0..255);
* ``RGB`` → ``['array', r, g, b, a]`` where each band is stretched to 0..1.

The viewer must construct the GeoTIFF source with ``normalize: false`` when a
style is present, so ``['band', n]`` is the raw pixel value (the official
OpenLayers COG examples do the same). The named ramps mirror the portal's
``ST_ColorMap`` presets; percentage stops resolve against the band/display
min–max.

``reclass`` is a server-side value reclass and has no client-side equivalent
here, so it is ignored for a COG (the interpolation already maps raw values).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

#: Pixel ranges implied by a raster band's data type (when statistics are absent).
_TYPE_MAX = {
    "byte": 255.0,
    "uint8": 255.0,
    "uint16": 65535.0,
    "int16": 32767.0,
    "uint32": 4294967295.0,
    "int32": 2147483647.0,
}

#: The portal's named ramps (same stops/colours as PostgresRasterManager's
#: ``ST_ColorMap`` presets). ``(percent, [r, g, b, a])`` with percent descending.
_NAMED_RAMPS: Dict[str, List[Tuple[float, List[int]]]] = {
    "grayscale": [
        (100.0, [255, 255, 255, 255]),
        (0.0, [0, 0, 0, 255]),
    ],
    "pseudocolor": [
        (100.0, [255, 0, 0, 255]),
        (50.0, [0, 255, 0, 255]),
        (0.0, [0, 0, 0, 255]),
    ],
    "fire": [
        (100.0, [243, 255, 221, 255]),
        (93.75, [242, 255, 178, 255]),
        (87.5, [255, 255, 135, 255]),
        (81.25, [255, 228, 96, 255]),
        (75.0, [255, 187, 53, 255]),
        (68.75, [255, 131, 7, 255]),
        (62.5, [255, 84, 0, 255]),
        (56.25, [255, 42, 0, 255]),
        (50.0, [255, 0, 0, 255]),
        (43.75, [255, 42, 0, 255]),
        (37.5, [224, 74, 0, 255]),
        (31.25, [183, 91, 0, 255]),
        (25.0, [140, 93, 0, 255]),
        (18.75, [99, 82, 0, 255]),
        (12.5, [58, 58, 1, 255]),
        (6.25, [12, 15, 0, 255]),
        (0.0, [0, 0, 0, 255]),
    ],
    "bluered": [
        (100.0, [165, 0, 33, 255]),
        (94.12, [216, 21, 47, 255]),
        (88.24, [247, 39, 53, 255]),
        (82.35, [255, 61, 61, 255]),
        (76.47, [255, 120, 86, 255]),
        (70.59, [255, 172, 117, 255]),
        (64.71, [255, 214, 153, 255]),
        (58.82, [255, 241, 188, 255]),
        (52.94, [255, 255, 234, 255]),
        (47.06, [234, 255, 255, 255]),
        (41.18, [188, 249, 255, 255]),
        (35.29, [153, 234, 255, 255]),
        (29.41, [117, 211, 255, 255]),
        (23.53, [86, 176, 255, 255]),
        (17.65, [61, 135, 255, 255]),
        (11.76, [40, 87, 255, 255]),
        (5.88, [24, 28, 247, 255]),
        (0.0, [36, 0, 216, 255]),
    ],
}


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _clamp_byte(value: Any, default: int = 255) -> int:
    number = _number(value)
    if number is None:
        return default
    return max(0, min(255, int(round(number))))


def _alpha_unit(value: Any) -> float:
    """OpenLayers colour alpha is 0..1 (RGB stays 0..255)."""
    number = _number(value)
    if number is None:
        return 1.0
    return max(0.0, min(1.0, number / 255.0))


def _rgba(stop: Dict[str, Any]) -> List[Any]:
    color = stop.get("color")
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        return [
            _clamp_byte(color[0]),
            _clamp_byte(color[1]),
            _clamp_byte(color[2]),
            _alpha_unit(color[3] if len(color) >= 4 else 255),
        ]
    return [
        _clamp_byte(stop.get("r")),
        _clamp_byte(stop.get("g")),
        _clamp_byte(stop.get("b")),
        _alpha_unit(stop.get("a")),
    ]


def _band_lookup(bands: Any) -> Dict[int, Dict[str, Any]]:
    lookup: Dict[int, Dict[str, Any]] = {}
    if not isinstance(bands, list):
        return lookup
    for index, band in enumerate(bands):
        if not isinstance(band, dict):
            continue
        raw_number = band.get("band", band.get("id", index + 1))
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            number = index + 1
        stats = band.get("statistics") if isinstance(band.get("statistics"), dict) else {}
        minimum = _number(band.get("minimum", stats.get("min")))
        maximum = _number(band.get("maximum", stats.get("max")))
        no_data = _number(band.get("noDataValue"))
        if no_data is None:
            no_data = _number(band.get("nodata"))
        if no_data is not None and not math.isfinite(no_data):
            no_data = None
        lookup[number] = {
            "minimum": minimum,
            "maximum": maximum,
            "type": str(band.get("type") or "").strip().lower(),
            "nodata": no_data,
        }
    return lookup


def _range_for(
    display: Dict[str, Any], band: Dict[str, Any]
) -> Optional[Tuple[float, float]]:
    minimum = _number(display.get("minimum"))
    maximum = _number(display.get("maximum"))
    if minimum is None:
        minimum = band.get("minimum")
    if maximum is None:
        maximum = band.get("maximum")
    if maximum is None:
        maximum = _TYPE_MAX.get(band.get("type", ""))
    if minimum is None:
        minimum = 0.0
    if maximum is None or maximum <= minimum:
        return None
    return minimum, maximum


def _stop_value(
    value: Any, minimum: Optional[float], maximum: Optional[float]
) -> Optional[float]:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("nv", "null", "nodata"):
            return None
        if text.endswith("%"):
            percent = _number(text[:-1])
            if percent is None or minimum is None or maximum is None:
                return None
            return minimum + (maximum - minimum) * percent / 100.0
        return _number(text)
    return _number(value)


def _band_unit_expr(
    number: int, band: Dict[str, Any]
) -> Optional[List[Any]]:
    """A 0..1 WebGL expression for one band, stretching by min–max."""
    minimum = band.get("minimum")
    maximum = band.get("maximum")
    if maximum is None:
        maximum = _TYPE_MAX.get(band.get("type", ""))
    if minimum is None:
        minimum = 0.0
    if maximum is None or maximum <= minimum:
        return None
    if minimum == 0:
        return ["/", ["band", number], float(maximum)]
    return ["/", ["-", ["band", number], float(minimum)], float(maximum - minimum)]


def _rgb_style(
    display: Dict[str, Any], lookup: Dict[int, Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        red = int(display.get("RBand") or 1)
        green = int(display.get("GBand") or 2)
        blue = int(display.get("BBand") or 3)
    except (TypeError, ValueError):
        return None, "RGB needs numeric RBand/GBand/BBand"
    expressions: List[List[Any]] = []
    for number in (red, green, blue):
        expression = _band_unit_expr(number, lookup.get(number, {}))
        if expression is None:
            return None, f"band {number} has no usable min/max for an RGB stretch"
        expressions.append(expression)
    alpha: Any = 1
    if display.get("ABand") is not None:
        try:
            alpha = _band_unit_expr(
                int(display["ABand"]), lookup.get(int(display["ABand"]), {})
            )
        except (TypeError, ValueError):
            alpha = 1
        if alpha is None:
            alpha = 1
    color_expression: Any = ["array", *expressions, alpha]
    no_data = lookup.get(red, {}).get("nodata")
    if no_data is not None and all(
        lookup.get(number, {}).get("nodata") == no_data
        for number in (red, green, blue)
    ):
        color_expression = [
            "case",
            ["==", ["band", red], float(no_data)],
            [0, 0, 0, 0],
            color_expression,
        ]
    return {"color": color_expression}, None


def _color_map_style(
    display: Dict[str, Any], lookup: Dict[int, Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        band_number = int(display.get("band") or 1)
    except (TypeError, ValueError):
        band_number = 1
    band = lookup.get(band_number, {})
    color_map = str(display.get("colorMap") or "grayscale").strip().lower()
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    stops: List[Tuple[float, List[int]]] = []
    if color_map in _NAMED_RAMPS:
        resolved = _range_for(display, band)
        if resolved is None:
            return None, "the named ramp needs band/display min–max"
        minimum, maximum = resolved
        for percent, rgba in _NAMED_RAMPS[color_map]:
            stops.append(
                (
                    minimum + (maximum - minimum) * percent / 100.0,
                    _rgba({"color": rgba}),
                )
            )
    elif color_map == "custom":
        resolved = _range_for(display, band)
        if resolved is not None:
            minimum, maximum = resolved
        raw_stops = display.get("customColorMap")
        if not isinstance(raw_stops, list):
            return None, "custom needs customColorMap stops"
        for stop in raw_stops:
            if not isinstance(stop, dict):
                continue
            value = _stop_value(stop.get("value"), minimum, maximum)
            if value is None:
                continue
            rgba = _rgba(stop)
            if any(component is None for component in rgba):
                continue
            stops.append((value, rgba))
    else:
        return None, f"colorMap {color_map!r} is not supported for a COG"

    if not stops:
        return None, "no usable colour stops"
    stops.sort(key=lambda item: item[0])
    # OL's interpolate requires strictly increasing stops. Nudge an exact
    # duplicate by a tiny epsilon (preserves a deliberate hard edge).
    previous: Optional[float] = None
    strictly: List[Tuple[float, List[int]]] = []
    for value, rgba in stops:
        if previous is not None and value <= previous:
            value = previous + max(1e-9, abs(previous) * 1e-9)
        strictly.append((value, rgba))
        previous = value
    if len(strictly) == 1:
        color_expression: Any = strictly[0][1]
    else:
        color_expression = ["interpolate", ["linear"], ["band", band_number]]
        for value, rgba in strictly:
            color_expression.append(float(value))
            color_expression.append(rgba)
    nodata = band.get("nodata")
    if nodata is not None:
        # A declared no-data sentinel must be transparent, not the first class
        # (the reported COG artefact where nodata got a class colour).
        color_expression = [
            "case",
            ["==", ["band", band_number], float(nodata)],
            [0, 0, 0, 0],
            color_expression,
        ]
    return {"color": color_expression}, None


def build_cog_style(
    display: Any, bands: Any
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Build an OpenLayers ``WebGLTile`` style from a raster ``display``.

    Returns ``(style, reason)``; ``style`` is ``None`` when the display cannot
    be expressed client-side, with ``reason`` explaining why. The caller should
    then keep the default COG rendering and (optionally) warn.
    """
    if not isinstance(display, dict) or not display:
        return None, "no display"
    lookup = _band_lookup(bands)
    display_type = str(display.get("displayType") or "").strip()
    if display_type.lower() == "rgb":
        return _rgb_style(display, lookup)
    if display_type.lower() == "colormap":
        return _color_map_style(display, lookup)
    return None, "displayType must be RGB or colorMap"