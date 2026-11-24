"""Handler for ``geopack_sdk_render_chart`` (issue 5 / SDK-011).

Renders a small **bar / line / pie** chart from caller-supplied tabular rows as a
self-contained SVG string and echoes the same numeric points in the structured
payload. Pure local compute: no portal call and **no third-party graphics
dependency** — the SVG is built from the standard library only, so the shipped
package stays dependency-light.

Why SVG (not PNG): the MCP image-content path passes any ``image/*`` mime through,
and ``image/svg+xml`` is text that needs no rasteriser. A host that does not draw
SVG still receives the points in the payload (``points``) plus a note, so the data
is never lost. Rows feed straight from ``geopack_sdk_aggregate_dataset`` (its
``rows`` list) or any list of dict records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from xml.sax.saxutils import escape

from ..errors import ToolArgumentError

CHART_TYPES = ("bar", "line", "pie")
_DEFAULT_TYPE = "bar"

#: Points drawn before the tail is summarised (keeps the SVG small and legible).
_MAX_POINTS = 200
_WIDTH = 720
_HEIGHT = 420
_MARGIN_TOP = 44
_MARGIN_LEFT = 64
_MARGIN_BOTTOM = 96
_PLOT_H = _HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM

#: Series/slice colours (shared, deterministic — first series is always the same).
_PALETTE = (
    "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02",
    "#a6761d", "#666666", "#1f78b4", "#b2df8a", "#fb9a99", "#cab2d6",
)

#: Sentinel series name for a single-series chart (never shown in a legend).
_SINGLE = "(value)"


@dataclass(frozen=True)
class ChartResult:
    payload: Dict[str, Any]
    body: bytes
    mime_type: str


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}"


def _unique(items: Sequence[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _open(title: Optional[str]) -> List[str]:
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" '
            f'viewBox="0 0 {_WIDTH} {_HEIGHT}" font-family="Segoe UI, Arial, sans-serif">'
        ),
        f'<rect width="{_WIDTH}" height="{_HEIGHT}" fill="#ffffff"/>',
    ]
    if title:
        parts.append(
            f'<text x="24" y="26" font-size="16" font-weight="600" fill="#111827">'
            f"{escape(str(title))}</text>"
        )
    return parts


def _render_xy(
    points: List[Dict[str, Any]],
    categories: List[str],
    series_names: List[str],
    chart_type: str,
    title: Optional[str],
) -> List[str]:
    multi = len(series_names) > 1
    right = 176 if multi else 24
    plot_w = _WIDTH - _MARGIN_LEFT - right
    left, top = _MARGIN_LEFT, _MARGIN_TOP
    n_cat = max(1, len(categories))
    cat_pos = {name: index for index, name in enumerate(categories)}

    values = [point["value"] for point in points]
    y_min, y_max = min(values), max(values)
    if y_max < 0:
        y_max = 0.0
    if y_min > 0:
        y_min = 0.0
    if y_max == y_min:
        y_max = y_min + 1.0

    def y_of(value: float) -> float:
        return top + _PLOT_H * (1 - (value - y_min) / (y_max - y_min))

    def x_center(index: int) -> float:
        return left + plot_w * (index + 0.5) / n_cat

    parts = _open(title)
    baseline = y_of(0.0)

    ticks = 5
    for tick in range(ticks + 1):
        value = y_min + (y_max - y_min) * tick / ticks
        y = y_of(value)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w:.1f}" y2="{y:.1f}" '
            'stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
            f'fill="#4b5563">{escape(_fmt(value))}</text>'
        )
    parts.append(
        f'<line x1="{left}" y1="{baseline:.1f}" x2="{left + plot_w:.1f}" y2="{baseline:.1f}" '
        'stroke="#9ca3af" stroke-width="1"/>'
    )

    rotated = n_cat > 10 or any(len(name) > 12 for name in categories)
    label_y = top + _PLOT_H + 18
    for index, name in enumerate(categories):
        x = x_center(index)
        if rotated:
            parts.append(
                f'<text x="{x:.1f}" y="{label_y:.1f}" text-anchor="end" font-size="10" '
                f'fill="#374151" transform="rotate(-35 {x:.1f} {label_y:.1f})">'
                f"{escape(name)}</text>"
            )
        else:
            parts.append(
                f'<text x="{x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="11" '
                f'fill="#374151">{escape(name)}</text>'
            )

    table: Dict[str, Dict[str, float]] = {name: {} for name in series_names}
    for point in points:
        table[point["series"]][str(point["category"])] = (
            table[point["series"]].get(str(point["category"]), 0.0) + point["value"]
        )

    if chart_type == "bar":
        slot = plot_w / n_cat
        bar_w = max(1.0, slot * 0.8 / len(series_names))
        for s_index, series in enumerate(series_names):
            color = _PALETTE[s_index % len(_PALETTE)]
            group_w = bar_w * len(series_names)
            for name, index in cat_pos.items():
                value = table[series].get(name)
                if value is None:
                    continue
                x = left + slot * index + (slot - group_w) / 2 + bar_w * s_index
                y_top = y_of(max(value, 0.0))
                y_bottom = y_of(min(value, 0.0))
                height = max(0.0, y_bottom - y_top)
                parts.append(
                    f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bar_w:.1f}" '
                    f'height="{height:.1f}" fill="{color}"/>'
                )
    else:  # line
        for s_index, series in enumerate(series_names):
            color = _PALETTE[s_index % len(_PALETTE)]
            coords = []
            for name, index in cat_pos.items():
                value = table[series].get(name)
                if value is None:
                    continue
                coords.append(f"{x_center(index):.1f},{y_of(value):.1f}")
            if len(coords) >= 2:
                parts.append(
                    f'<polyline fill="none" stroke="{color}" stroke-width="2.5" '
                    f'points="{" ".join(coords)}"/>'
                )
            for coord in coords:
                cx, cy = coord.split(",")
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{color}"/>')

    if multi:
        legend_x = left + plot_w + 16
        for s_index, series in enumerate(series_names):
            color = _PALETTE[s_index % len(_PALETTE)]
            y = top + s_index * 20
            parts.append(f'<rect x="{legend_x}" y="{y}" width="12" height="12" fill="{color}"/>')
            parts.append(
                f'<text x="{legend_x + 18}" y="{y + 10}" font-size="11" fill="#111827">'
                f"{escape(series)}</text>"
            )

    parts.append("</svg>")
    return parts


def _render_pie(points: List[Dict[str, Any]], title: Optional[str]) -> List[str]:
    totals: Dict[str, float] = {}
    for point in points:
        if point["value"] > 0:
            label = str(point["category"])
            totals[label] = totals.get(label, 0.0) + point["value"]
    if not totals:
        raise ToolArgumentError(
            "a pie chart needs at least one positive value.",
            key="value",
            hint="Use chart_type 'bar' or 'line' for values at or below zero.",
        )
    labels = list(totals.keys())
    total = sum(totals.values())
    cx, cy, radius = 190.0, _HEIGHT / 2 + 4, 128.0
    parts = _open(title)
    start = -math.pi / 2
    for index, label in enumerate(labels):
        fraction = totals[label] / total
        angle = fraction * 2 * math.pi
        end = start + angle
        x1 = cx + radius * math.cos(start)
        y1 = cy + radius * math.sin(start)
        x2 = cx + radius * math.cos(end)
        y2 = cy + radius * math.sin(end)
        large = 1 if angle > math.pi else 0
        color = _PALETTE[index % len(_PALETTE)]
        parts.append(
            f'<path d="M {cx:.1f} {cy:.1f} L {x1:.2f} {y1:.2f} '
            f'A {radius} {radius} 0 {large} 1 {x2:.2f} {y2:.2f} Z" '
            f'fill="{color}" stroke="#ffffff" stroke-width="1"/>'
        )
        start = end
    legend_x = 380
    for index, label in enumerate(labels):
        y = 70 + index * 24
        color = _PALETTE[index % len(_PALETTE)]
        parts.append(f'<rect x="{legend_x}" y="{y}" width="12" height="12" fill="{color}"/>')
        share = totals[label] / total * 100
        parts.append(
            f'<text x="{legend_x + 18}" y="{y + 10}" font-size="11" fill="#111827">'
            f"{escape(label)} — {escape(_fmt(totals[label]))} ({share:.0f}%)</text>"
        )
    parts.append("</svg>")
    return parts


def render_chart(
    rows: Any,
    *,
    chart_type: str = _DEFAULT_TYPE,
    category: str,
    value: str,
    series: Optional[str] = None,
    title: Optional[str] = None,
) -> ChartResult:
    """Build an SVG chart (bar/line/pie) from ``rows`` and its structured payload."""
    kind = (chart_type or _DEFAULT_TYPE).strip().lower()
    if kind not in CHART_TYPES:
        raise ToolArgumentError(
            f"chart_type must be one of: {', '.join(CHART_TYPES)} (got {chart_type!r}).",
            key="chart_type",
        )
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ToolArgumentError(
            "rows must be a non-empty list of objects (e.g. aggregate_dataset rows).",
            key="rows",
            hint="Call geopack_sdk_aggregate_dataset first and pass its `rows` array here.",
        )
    if not isinstance(category, str) or not category:
        raise ToolArgumentError("category must be a field name.", key="category")
    if not isinstance(value, str) or not value:
        raise ToolArgumentError("value must be a numeric field name.", key="value")

    points: List[Dict[str, Any]] = []
    skipped = 0
    for row in rows:
        if not isinstance(row, dict) or category not in row:
            skipped += 1
            continue
        number = _as_float(row.get(value))
        if number is None:
            skipped += 1
            continue
        raw_category = row.get(category)
        if series and row.get(series) is not None:
            series_name = str(row.get(series))
        else:
            series_name = _SINGLE
        points.append(
            {
                "category": raw_category,
                "series": series_name,
                "value": number,
            }
        )

    if not points:
        raise ToolArgumentError(
            f"no rows carried a numeric '{value}' for category '{category}'.",
            key="value",
            hint=(
                "Check the field names against geopack_sdk_get_dataset_schema; a numeric field "
                "like `aggregate_count`/`sum` is required."
            ),
        )

    truncated = 0
    if len(points) > _MAX_POINTS:
        truncated = len(points) - _MAX_POINTS
        points = points[:_MAX_POINTS]

    categories = _unique([str(point["category"]) for point in points])
    series_names = _unique([point["series"] for point in points])

    if kind == "pie":
        parts = _render_pie(points, title)
        value_range = [0.0, float(sum(p["value"] for p in points if p["value"] > 0))]
    else:
        parts = _render_xy(points, categories, series_names, kind, title)
        numbers = [point["value"] for point in points]
        value_range = [min(numbers), max(numbers)]

    payload: Dict[str, Any] = {
        "chartType": kind,
        "title": title,
        "category": category,
        "value": value,
        "series": series,
        "categories": categories,
        "seriesNames": [] if series_names == [_SINGLE] else series_names,
        "points": points,
        "pointCount": len(points),
        "skippedRows": skipped,
        "truncatedPoints": truncated,
        "valueRange": value_range,
        "mimeType": "image/svg+xml",
        "note": (
            "Chart rendered inline as image/svg+xml. If your client does not display SVG, the "
            "same points are in `points`."
        ),
    }
    body = "".join(parts).encode("utf-8")
    return ChartResult(payload=payload, body=body, mime_type="image/svg+xml")