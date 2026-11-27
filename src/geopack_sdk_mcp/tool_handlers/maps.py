"""Handler for ``geopack_sdk_show_map`` (slice 033, lanes A/B).

Stands up (or reuses) the local loopback data service, declares layers on a map
manifest and returns stable URLs plus a live ``viewerUrl`` (an OpenLayers page) a
page can reference **instead of embedding data** (N1/N2).

Map-build is **fail-fast** for a bad ``publicationId`` (a dataset id is a common
mistake) and **self-describing** for extents: when a layer has no ``bbox`` the
handler reads the source dataset's WGS84 ``geo_extent`` and labels the box with
its CRS/axis order, so auto-fit never relies on a caller-guessed order.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..maps import get_or_start_service, layer_from_spec
from ..maps import viewer
from ..maps.errors import SERVICE_ERROR, MapServiceError
from ..maps.sources import (
    dataset_distinct_count,
    dataset_feature_count,
    dataset_field_distinct_values,
    dataset_field_quantiles,
    dataset_field_values,
    dataset_info,
    publication_dataset_id,
    publication_layer_name,
    valid_wgs84_bbox,
)
from ..sanitize.dataset_symbology import styled_publications
from ..sanitize.style_spec import (
    CATEGORICAL_PALETTE,
    breaks_spec,
    categorical_spec,
    ensure_legend,
    field_values_from_geojson,
    quantile_breaks,
)

_WGS84_CRS = "EPSG:4326"
_AXIS_ORDER = "west,south,east,north"

#: Fallback when a template declares no ``layerPalette``.
_DEFAULT_LAYER_PALETTE = ("#3ba776", "#3b7fa7", "#c2703b", "#8b5cf6", "#d1477a", "#2f9e8f")

#: Raster renderers: the image is produced by the server or byte-served as a COG,
#: so a per-layer vector ``style`` cannot recolour them and the legend shows a
#: raster swatch (only vector renderers honour ``style``).
_RASTER_RENDERS = frozenset({"wms", "wmts", "xyz", "cog", "rastertile"})

#: Colour ramps the portal's ``ST_ColorMap`` raster renderer understands.
_VALID_RASTER_COLOR_MAPS = frozenset(
    {"grayscale", "pseudocolor", "fire", "bluered", "custom"}
)

#: Display keys a caller may send (backend-native names + friendly aliases).
_RASTER_DISPLAY_KEYS = frozenset(
    {
        "displayType",
        "band",
        "colorMap",
        "customColorMap",
        "minimum",
        "maximum",
        "reclass",
        "resampling",
        "referenceZoom",
        "RBand",
        "GBand",
        "BBand",
        "ABand",
        "bands",
    }
)


def _normalize_raster_display(
    display: Dict[str, Any], label: str, warnings: List[str]
) -> Optional[Dict[str, Any]]:
    """Normalize a caller ``display`` to the portal raster renderer's schema.

    The friendly shapes an agent is likely to send are accepted and converted:

    * ``bands:{r,g,b,a}`` / ``bands:[r,g,b,a]`` → ``RBand``/``GBand``/``BBand``/``ABand``;
    * a ``customColorMap`` stop's ``color:[r,g,b,a]`` → ``r``/``g``/``b``/``a``.

    ``displayType`` defaults from the supplied keys, ``colorMap`` is validated
    against the portal's named ramps, and an unusable display returns ``None`` so
    the dataset's saved rendering is used instead (with a warning).
    """
    normalized = {
        key: value for key, value in display.items() if key in _RASTER_DISPLAY_KEYS
    }
    bands = normalized.pop("bands", None)
    display_type = normalized.get("displayType")
    if isinstance(display_type, str):
        display_type = display_type.strip().lower()
        if display_type in ("rgb", "truecolor", "true-color"):
            normalized["displayType"] = "RGB"
        elif display_type in ("colormap", "color-map", "colourmap", "colour-map"):
            normalized["displayType"] = "colorMap"
        else:
            normalized["displayType"] = display.get("displayType")
    if normalized.get("displayType") not in ("RGB", "colorMap"):
        has_rgb = bool(bands) or any(
            normalized.get(key) is not None for key in ("RBand", "GBand", "BBand")
        )
        normalized["displayType"] = "RGB" if has_rgb else "colorMap"

    if isinstance(bands, dict):
        for source, target in (("r", "RBand"), ("g", "GBand"), ("b", "BBand"), ("a", "ABand")):
            if bands.get(source) is not None:
                normalized[target] = bands[source]
    elif isinstance(bands, (list, tuple)):
        for index, target in enumerate(("RBand", "GBand", "BBand", "ABand")):
            if index < len(bands) and bands[index] is not None:
                normalized[target] = bands[index]

    for key in ("band", "RBand", "GBand", "BBand", "ABand", "referenceZoom"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            normalized[key] = int(value.strip())
    for key in ("minimum", "maximum"):
        value = normalized.get(key)
        if isinstance(value, str):
            try:
                normalized[key] = float(value)
            except ValueError:
                pass
    if "reclass" in normalized:
        value = normalized["reclass"]
        if isinstance(value, str):
            normalized["reclass"] = value.strip().lower() in ("1", "true", "yes", "on")
        else:
            normalized["reclass"] = bool(value)

    if normalized["displayType"] == "RGB":
        missing = [
            target
            for target in ("RBand", "GBand", "BBand")
            if normalized.get(target) is None
        ]
        if missing:
            warnings.append(
                f"layer '{label}': RGB display needs bands {', '.join(missing)}; "
                "using the dataset's saved rendering instead."
            )
            return None
        return normalized

    color_map = str(normalized.get("colorMap") or "grayscale").strip().lower()
    if color_map not in _VALID_RASTER_COLOR_MAPS:
        warnings.append(
            f"layer '{label}': colorMap {color_map!r} is not a portal ramp; use "
            "grayscale|pseudocolor|fire|bluered|custom (using grayscale)."
        )
        color_map = "grayscale"
    normalized["colorMap"] = color_map
    if color_map == "custom":
        stops = normalized.get("customColorMap")
        cleaned: List[Dict[str, Any]] = []
        if isinstance(stops, list):
            for stop in stops:
                if not isinstance(stop, dict):
                    continue
                entry = dict(stop)
                color = entry.pop("color", None)
                if isinstance(color, (list, tuple)) and len(color) >= 3:
                    entry.setdefault("r", color[0])
                    entry.setdefault("g", color[1])
                    entry.setdefault("b", color[2])
                    if len(color) >= 4:
                        entry.setdefault("a", color[3])
                if any(entry.get(key) is None for key in ("r", "g", "b")):
                    continue
                entry.setdefault("a", 255)
                cleaned.append(entry)
        if not cleaned:
            warnings.append(
                f"layer '{label}': colorMap 'custom' needs customColorMap stops with "
                "value + r/g/b (or color:[r,g,b,a]); using grayscale."
            )
            normalized["colorMap"] = "grayscale"
        else:
            normalized["customColorMap"] = cleaned
    return normalized

#: Features a portal-dataset GeoJSON layer loads when no ``limit`` is set.
_GEOJSON_DEFAULT_LIMIT = 1000

#: Features sampled to derive a caller-requested symbology from the data.
_SYMBOLOGY_SAMPLE_LIMIT = 1000
#: Default class count for a caller-requested ``classBreaks`` symbology.
_DEFAULT_BREAK_CLASSES = 5
#: A caller-requested ``classBreaks`` count above this is capped: a quantile class
#: map beyond a handful of classes is unreadable and the sequential ramp cannot
#: separate the bands.
_MAX_BREAK_CLASSES = 12
#: A data-derived categorical symbology above this many classes is refused (a
#: high-cardinality field like an id would render an unreadable legend).
_MAX_DERIVED_CLASSES = 30


def _assign_layer_palette(manifest: Any, template_obj: Dict[str, Any]) -> None:
    """Give each vector layer a distinct fill from the template palette.

    Layers without an explicit ``style.fill`` rotate through ``layerPalette`` so
    multiple layers are visually separable (one shared default colour made them
    indistinguishable). Server-rendered raster layers are skipped, and so is any
    layer that already carries a derived ``symbology`` spec — its colours come
    from the dataset's own renderer, and adding a palette ``style`` would override
    it in the viewer (an explicit ``style`` wins over the derived spec there).
    """
    palette = template_obj.get("layerPalette")
    if not isinstance(palette, list):
        palette = list(_DEFAULT_LAYER_PALETTE)
    colors = [c for c in palette if isinstance(c, str) and c.strip()] or list(
        _DEFAULT_LAYER_PALETTE
    )
    for index, layer in enumerate(manifest.layers.values()):
        if layer.raster or layer.resolved_render() in _RASTER_RENDERS:
            continue
        if layer.symbology:
            continue  # the derived dataset spec already fixes the colours
        style = dict(layer.style) if isinstance(layer.style, dict) else {}
        if not style.get("fill"):
            style["fill"] = colors[index % len(colors)]
        layer.style = style


def _with_token(entry: Dict[str, Any], token: str) -> None:
    data_url = entry.get("dataUrl")
    if data_url:
        entry["dataUrlWithToken"] = f"{data_url}?t={token}"
    tile_url = entry.get("tileUrl")
    if tile_url:
        entry["tileUrlWithToken"] = f"{tile_url}?t={token}"


def _require_publication(client: Any, publication_id: int) -> Any:
    """Fail fast: a publication must resolve at map-build, not 404 at tile time."""
    try:
        return client.publications.get(publication_id)
    except Exception as exc:  # noqa: BLE001 - turn a 404 into a clear contract error
        raise MapServiceError(
            SERVICE_ERROR,
            f"publication {publication_id} was not found or is not accessible.",
            key="publicationId",
            hint=(
                "Pass a real publication id, not a dataset id. Find one via list_datasets "
                "with order_by='publicationsCount' and read publicationsSummary[].id."
            ),
        ) from exc


def _bboxes_overlap(a: Any, b: Any) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _valid_lonlat(value: Any) -> Optional[List[float]]:
    """``[lon, lat]`` in EPSG:4326, or ``None`` when implausible."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        lon = float(value[0])
        lat = float(value[1])
    except (TypeError, ValueError):
        return None
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    return [lon, lat]


def _layer_filter(layer: Any) -> Optional[Any]:
    """The attribute filter a portal-dataset layer draws with (``None`` = all rows).

    A layer spec carries its scope in ``query`` (the FeatureQuery DSL); the server
    applies ``query.filter`` to the GeoJSON the layer loads, so a data-derived
    symbology must honour the SAME filter to describe what is on screen.
    """
    query = getattr(layer, "query", None)
    if isinstance(query, dict):
        return query.get("filter")
    return None


def _resolve_caller_symbology(
    client: Any, layer: Any, warnings: List[str], field_meta: Optional[Dict[str, Any]] = None
) -> None:
    """Resolve a caller-supplied ``symbology`` into a complete portable spec.

    A caller may pass either a COMPLETE spec (already carrying ``unique``/``breaks``)
    or a SHORTHAND the handler derives from the layer's own data:

    * ``{"type": "uniqueValue", "field": "Ownership"}`` — one colour per distinct value
    * ``{"type": "classBreaks", "field": "DB_SHAPE_Area", "classes": 5}`` — quantile breaks

    The resolved spec is left on ``layer.symbology`` (so the viewer draws it and the
    dataset's own saved renderer is never consulted); ``None`` means "no usable
    symbology" and the caller is told why in ``warnings``.

    A COMPLETE spec is kept verbatim, except that a missing ``legend`` is derived
    from its own ``unique``/``breaks`` (so the legend panel is never blank); an
    explicit ``legend`` the caller sent is honoured as-is.
    """
    symbology = layer.symbology
    if not isinstance(symbology, dict) or not symbology:
        layer.symbology = None
        return
    stype = symbology.get("type")
    label = layer.title or layer.id

    field = symbology.get("field")
    field_info = (field_meta or {}).get(field) if isinstance(field, str) else None
    field_info = field_info if isinstance(field_info, dict) else {}
    domain = field_info.get("domain") if isinstance(field_info.get("domain"), dict) else {}
    alias = field_info.get("alias")
    if isinstance(alias, str) and alias:
        title: Optional[str] = alias
    elif isinstance(field, str) and field:
        title = field
    else:
        title = None

    # A complete caller-authored spec (already carrying `unique`/`breaks`) is used
    # verbatim — but if it omits a `legend`, we derive one from its own classes so
    # the panel is never blank (the SAME rule the dataset's saved-renderer path
    # follows). An explicit caller `legend` is always honoured.
    if (symbology.get("unique") and stype in (None, "uniqueValue")) or (
        symbology.get("breaks") and stype in (None, "classBreaks")
    ):
        layer.symbology = ensure_legend(symbology, title=title)
        return

    if not isinstance(field, str) or not field:
        warnings.append(
            f"layer '{label}': symbology needs a 'field' (or explicit 'unique'/'breaks'); ignored."
        )
        layer.symbology = None
        return

    if stype == "classBreaks":
        classes = symbology.get("classes")
        classes = (
            int(classes)
            if isinstance(classes, int) and not isinstance(classes, bool) and classes > 0
            else _DEFAULT_BREAK_CLASSES
        )
        if classes > _MAX_BREAK_CLASSES:
            warnings.append(
                f"layer '{label}': symbology requested {classes} classes; capped at "
                f"{_MAX_BREAK_CLASSES} (a higher count is not legible on a quantile map)."
            )
            classes = _MAX_BREAK_CLASSES
        breaks: Optional[List[Any]] = None
        if layer.kind == "portal-dataset":
            # Break on the FULL, filtered column server-side. A feature SAMPLE both
            # under-counts a large dataset's tails and IGNORES the layer's filter, so
            # a sampled legend can be wrong by orders of magnitude (issue report
            # 2026-11-24, N2: a 356-row filtered layer reproduced the whole 18,648-row
            # dataset's breaks, all below the layer's own minimum). The layer filter
            # is forwarded so the breaks describe exactly the rows the layer draws.
            breaks = dataset_field_quantiles(
                client,
                int(layer.dataset_id),
                field,
                classes=classes,
                where_filter=_layer_filter(layer),
            )
            if breaks is None:
                # Store cannot aggregate (or the filter is unparsable): fall back to a
                # sample, but SAY so — never present a sampled estimate as exact.
                warnings.append(
                    f"layer '{label}': could not compute server-side class breaks for "
                    f"field '{field}'; used a {_SYMBOLOGY_SAMPLE_LIMIT}-feature sample "
                    "instead (breaks may not match the layer's filter)."
                )
        if breaks is None:
            if layer.kind == "portal-dataset":
                values = dataset_field_values(
                    client, int(layer.dataset_id), field, limit=_SYMBOLOGY_SAMPLE_LIMIT
                )
            else:
                values = field_values_from_geojson(layer.geojson, field)
            breaks = quantile_breaks(values, classes)
        if not breaks:
            warnings.append(
                f"layer '{label}': symbology field '{field}' has no numeric values; ignored."
            )
            layer.symbology = None
            return
        layer.symbology = breaks_spec(field, breaks, title=title)
        return

    # uniqueValue (the default): one class per DISTINCT value. A feature sample
    # silently under-counts the categories of a large dataset (it styled only 7 of
    # 18 classes by reading the first 1,000 of 18,648 rows), so the portal lane
    # groups the whole access-scoped column instead (issue report 2026-11-24).
    truncated = False
    if layer.kind == "portal-dataset":
        try:
            values, truncated = dataset_field_distinct_values(
                client, int(layer.dataset_id), field, max_values=_MAX_DERIVED_CLASSES
            )
        except Exception:  # noqa: BLE001 - a bad field must not fail the whole map
            warnings.append(
                f"layer '{label}': could not read distinct values for field '{field}' "
                "(check the field name with geopack_sdk_get_dataset_schema); symbology ignored."
            )
            layer.symbology = None
            return
    else:
        values = field_values_from_geojson(layer.geojson, field)

    spec = categorical_spec(field, values, domain=domain, title=title)
    if not spec["unique"]:
        warnings.append(f"layer '{label}': symbology field '{field}' has no values; ignored.")
        layer.symbology = None
        return
    # Guard the palette/class-cap invariant: if the palette is shorter than the
    # class cap, `categorical_spec` cycles and two categories share a colour (the
    # original N3 defect). The cap and palette are kept equal, so this only fires
    # if one is changed without the other — say so instead of hiding it.
    if len(spec["unique"]) > len(CATEGORICAL_PALETTE):
        warnings.append(
            f"layer '{label}': symbology field '{field}' has {len(spec['unique'])} "
            f"distinct values, more than the {len(CATEGORICAL_PALETTE)} palette colours; "
            "some classes share a colour."
        )
    if truncated:
        shown = len(spec["unique"])
        total = (
            dataset_distinct_count(client, int(layer.dataset_id), field)
            if layer.kind == "portal-dataset"
            else None
        )
        if total is not None and total > shown:
            detail = f"has {total} distinct values"
            remainder = f"the other {total - shown} render with the default style"
        else:
            detail = f"has more than {_MAX_DERIVED_CLASSES} distinct values"
            remainder = "the rest render with the default style"
        warnings.append(
            f"layer '{label}': symbology field '{field}' {detail} (cap {_MAX_DERIVED_CLASSES}); "
            f"showing {shown} classes — {remainder}. Use an explicit 'unique' spec or a "
            "lower-cardinality field."
        )
    layer.symbology = spec


def _apply_extent(
    client: Any,
    layer: Any,
    *,
    publication: Any = None,
    warnings: List[str],
) -> None:
    """Fill/label a layer's WGS84 bbox and warn about raster-on-dataset use.

    The source dataset's WGS84 ``geo_extent`` is authoritative: a caller ``bbox``
    that does not overlap it (e.g. a lat/lon axis swap) is replaced, so auto-fit
    cannot land on the wrong continent.
    """
    label = layer.title or layer.id
    info: Dict[str, Any] = {}
    if layer.kind == "portal-dataset":
        info = dataset_info(client, int(layer.dataset_id))
    elif layer.kind == "portal-publication" and publication is not None:
        dataset_id = publication_dataset_id(publication)
        if dataset_id is not None:
            info = dataset_info(client, dataset_id)
        layer.identify_layers = publication_layer_name(publication)
    dataset_extent = info.get("extent")

    if layer.bbox is not None:
        box = valid_wgs84_bbox(layer.bbox)
        if box is None:
            warnings.append(
                f"layer '{label}': bbox must be [west,south,east,north] in EPSG:4326; ignored."
            )
            layer.bbox = None
        elif dataset_extent and not _bboxes_overlap(box, dataset_extent):
            warnings.append(
                f"layer '{label}': bbox does not overlap the dataset extent; using the dataset "
                "extent (check the axis order: [west,south,east,north])."
            )
            layer.bbox = dataset_extent
        else:
            layer.bbox = box

    if layer.bbox is None and dataset_extent:
        layer.bbox = dataset_extent

    if layer.bbox is not None:
        layer.bbox_crs = _WGS84_CRS
        layer.bbox_axis_order = _AXIS_ORDER

    field_meta = info.get("field_meta")
    if isinstance(field_meta, dict) and field_meta:
        # Field aliases + coded-value domains for the viewer's identify popup, so a
        # coded field shows its human value (e.g. 1 -> "اوقاف"), not the raw code.
        layer.fields = [
            {
                "name": name,
                "alias": meta.get("alias") if isinstance(meta, dict) else None,
                "domain": (meta.get("domain") if isinstance(meta, dict) else None) or {},
            }
            for name, meta in field_meta.items()
            if isinstance(name, str) and name
        ]

    if layer.kind == "portal-dataset":
        if info.get("has_cog"):
            # The dataset ships a Cloud-Optimized GeoTIFF: byte-serve it directly
            # (the viewer draws it with ol/source/GeoTIFF) rather than vectorising.
            layer.has_cog = True
        elif layer.render == "cog":
            warnings.append(
                f"layer '{label}': render 'cog' needs a Cloud-Optimized GeoTIFF; dataset "
                f"{layer.dataset_id} has none — using the default renderer."
            )
            layer.render = None

    if layer.has_cog and info.get("bands"):
        # Band metadata lets the viewer label the value read at a click and skip
        # the no-data sentinel (e.g. -2147483647).
        layer.raster_bands = [
            {
                "band": band.get("band") or (index + 1),
                "label": band.get("name") or band.get("description"),
                "type": band.get("type") or band.get("dataType"),
                "colorInterpretation": band.get("colorInterpretation"),
                "noDataValue": band.get("noDataValue"),
                "minimum": band.get("minimum"),
                "maximum": band.get("maximum"),
            }
            for index, band in enumerate(info["bands"])
        ]

    if info.get("data_type") == "raster":
        layer.raster = True
        # Was the display supplied by the CALLER (vs. the dataset's saved one)?
        caller_display = isinstance(layer.raster_display, dict) and bool(
            layer.raster_display
        )
        if layer.kind == "portal-dataset" and not layer.has_cog:
            # A raster stored in PostGIS (or an MBTiles container) can be rendered
            # by the portal's own PNG tile lane — no publication and no COG needed.
            # This is the lane the frontend uses (`/datasets/{id}/rastertile/...`):
            # the portal applies the dataset's saved display, so the map shows real
            # pixels with the official symbology.
            # A caller may override the saved raster rendering (`display`) and the
            # reference zoom; otherwise the dataset's own display is used.
            display = info.get("display")
            if not caller_display and isinstance(display, dict) and display:
                layer.raster_display = display
            ref_zoom = info.get("ref_zoom")
            if (
                layer.ref_zoom is None
                and isinstance(ref_zoom, int)
                and not isinstance(ref_zoom, bool)
            ):
                layer.ref_zoom = ref_zoom
            if info.get("raster_tile"):
                layer.raster_tile = True
                if layer.render in (None, "rastertile"):
                    layer.render = "rastertile"
                # An explicit vector render (geojson/mvt) is honoured: the caller
                # consciously asked for the footprint instead of the image.
            elif layer.render == "rastertile":
                warnings.append(
                    f"layer '{label}': render 'rastertile' needs a PostGIS/MBTiles raster "
                    f"dataset; dataset {layer.dataset_id} is not served by that lane — using "
                    "the default renderer."
                )
                layer.render = None
            elif layer.render not in ("geojson", "mvt", "wfs"):
                warnings.append(
                    f"layer '{label}': dataset {layer.dataset_id} is raster and has no raster-tile "
                    "support; a portal-dataset layer is served as vector GeoJSON/MVT and will not "
                    "show an image — use a portal-publication layer (a raster WMS/WMTS publication) "
                    "instead."
                )

            if caller_display:
                if not info.get("raster_tile"):
                    warnings.append(
                        f"layer '{label}': 'display' only applies to a server-rendered raster "
                        "(the raster-tile lane); ignored."
                    )
                    layer.raster_display = None
                elif info.get("mbtiles"):
                    # MBTiles stores finished pictures; the portal cannot recolour them.
                    warnings.append(
                        f"layer '{label}': dataset {layer.dataset_id} is MBTiles (pre-rendered "
                        "tiles); 'display' cannot recolour it and was ignored."
                    )
                    layer.raster_display = None
                else:
                    normalized = _normalize_raster_display(
                        layer.raster_display, label, warnings
                    )
                    if normalized is None:
                        layer.raster_display = (
                            info.get("display")
                            if isinstance(info.get("display"), dict)
                            else None
                        )
                    else:
                        if (
                            layer.ref_zoom is None
                            and isinstance(normalized.get("referenceZoom"), int)
                            and not isinstance(normalized.get("referenceZoom"), bool)
                        ):
                            layer.ref_zoom = normalized["referenceZoom"]
                        layer.raster_display = normalized

    if layer.symbology:
        # A caller asked for a specific symbology. Resolve it (a shorthand spec is
        # derived from the layer's data) and never overwrite it with the dataset's
        # own renderer.
        if layer.resolved_render() in _RASTER_RENDERS:
            warnings.append(
                f"layer '{label}': symbology does not affect a "
                f"{layer.resolved_render().upper()} image layer (the server renders it); ignored."
            )
            layer.symbology = None
        else:
            _resolve_caller_symbology(
                client, layer, warnings, field_meta=info.get("field_meta")
            )
    elif info.get("style_spec") and layer.kind == "portal-dataset" and not layer.style:
        # No caller symbology: apply the dataset's saved symbol as the layer's
        # default style, so the map reproduces the portal colouring instead of a
        # palette colour.
        layer.symbology = info["style_spec"]

    if layer.raster_display and layer.resolved_render() != "rastertile":
        warnings.append(
            f"layer '{label}': 'display' only applies to a server-rendered raster "
            "(render 'rastertile'); ignored for this layer."
        )
        layer.raster_display = None

    _warn_about_saved_symbology(client, layer, info, warnings)
    _warn_about_geojson_cap(client, layer, warnings)


def _warn_about_geojson_cap(client: Any, layer: Any, warnings: List[str]) -> None:
    """Say how many features a GeoJSON cap hides — never decide for the caller.

    A portal-dataset layer's ``dataUrl`` is always served by the GeoJSON lane, so
    it returns the first 1,000 features by default regardless of renderer. The MCP
    does NOT silently switch to tiles or raise the limit; it names the numbers and
    the levers (`limit`, `render:'mvt'`) so the AGENT (with the user) chooses.

    The warning used to be emitted only for ``render:'mvt'`` layers, so an MVT
    layer advertised a ``dataUrl`` truncated to 1/18th of the rows with no signal
    while its tiles were full coverage (issue report 2026-11-24, N5). It now names
    what is actually capped: the MAP for a GeoJSON render, or the ``dataUrl`` for
    an MVT/WFS render (whose map is already full coverage).
    """
    if layer.kind != "portal-dataset":
        return
    render = layer.resolved_render()
    if render not in ("geojson", "mvt", "wfs"):
        return  # no feature rows to truncate (raster/image render)
    cap = layer.limit if layer.limit is not None else _GEOJSON_DEFAULT_LIMIT
    if cap is not None and cap <= 0:
        return  # the caller already asked for the whole dataset
    total = dataset_feature_count(client, int(layer.dataset_id))
    if total is None or total <= cap:
        return
    label = layer.title or layer.id
    if render == "geojson":
        warnings.append(
            f"layer '{label}': dataset {layer.dataset_id} has {total} features but a GeoJSON layer "
            f"loads the first {cap}. To show all, set the layer `limit` to 0 (whole dataset) or use "
            "render:'mvt' (tiled, full coverage) — choose the appropriate one (ask the user if unsure)."
        )
        return
    warnings.append(
        f"layer '{label}': dataset {layer.dataset_id} has {total} features; the map renders all "
        f"via {render}, but the layer's `dataUrl` returns only the first {cap}. Fetch the tiles for "
        "full coverage, or set the layer `limit` to 0 to make `dataUrl` return the whole dataset "
        "(ask the user if unsure)."
    )


def _warn_about_saved_symbology(
    client: Any, layer: Any, info: Dict[str, Any], warnings: List[str]
) -> None:
    """Disclose a dataset's saved rendering when the MCP cannot render it.

    A `portal-dataset` layer whose dataset has a **translatable** vector renderer
    is now drawn with the derived portable spec (``layer.symbology``), so no
    warning is needed there. This still warns when the saved symbology is NOT
    applied — a raster display block, or a renderer family we do not translate —
    and, failing that, names the styled *publication* that carries the official
    look (the path that renders dataset 1577).
    """
    if layer.kind != "portal-dataset":
        return
    if layer.symbology:
        return  # the dataset's saved vector symbology IS applied; nothing to warn
    if layer.resolved_render() == "rastertile":
        # The raster-tile lane forwards the dataset's saved `display`, so the portal
        # renders the official symbology — there is nothing left to disclose.
        return
    if isinstance(layer.style, dict) and layer.style:
        return  # a caller style is deliberate; the disclosure is noise here
    label = layer.title or layer.id
    symbology = info.get("symbology") or {}
    if symbology.get("hasSavedStyle"):
        kind = symbology.get("kind")
        flavour = symbology.get("rendererType") or symbology.get("rasterDisplayType")
        detail = f"{kind}" + (f" ({flavour})" if flavour else "")
        warnings.append(
            f"layer '{label}': dataset {layer.dataset_id} has its own saved symbology {detail}; a "
            "portal-dataset layer does not apply it and shows the generic viewer style. Use a "
            "portal-publication layer to render the official symbology, or pass an explicit style."
        )
        return

    styled = [
        pub
        for pub in styled_publications(client, int(layer.dataset_id))
        if pub.get("hasStyle")
    ]
    if styled:
        ids = ", ".join(str(pub.get("publicationId")) for pub in styled)
        warnings.append(
            f"layer '{label}': dataset {layer.dataset_id} stores no symbology, but publication(s) "
            f"{ids} carry a saved style — use kind:'portal-publication' with that publicationId to "
            "render the official symbology instead of the generic viewer style."
        )


def show_map(
    client: Any,
    *,
    title: Optional[str] = None,
    layers: Optional[List[Dict[str, Any]]] = None,
    map_id: Optional[str] = None,
    open_browser: bool = False,
    basemap: Optional[str] = None,
    template: Optional[Dict[str, Any]] = None,
    style: Optional[Dict[str, Any]] = None,
    center: Optional[List[float]] = None,
    zoom: Optional[int] = None,
    replace_layers: bool = False,
    remove_layers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    service = get_or_start_service(client)

    manifest = service.find_map(map_id) if map_id else None
    if map_id and manifest is None:
        raise MapServiceError(SERVICE_ERROR, "unknown map id.", key="map_id")
    if manifest is None:
        manifest = service.create_map(title or "Geopack map")
    elif title:
        manifest.title = title

    per_call: Dict[str, Any] = dict(template) if isinstance(template, dict) else {}

    # `center`/`zoom` are sugar for `template.view.*`: pointing the map at a place
    # also switches the mode to 'center' so auto-fit does not move it away.
    view_warnings: List[str] = []
    view = dict(per_call["view"]) if isinstance(per_call.get("view"), dict) else {}
    if center is not None:
        point = _valid_lonlat(center)
        if point is None:
            view_warnings.append("center must be [lon, lat] in EPSG:4326; ignored.")
        else:
            view["center"] = point
            view.setdefault("mode", "center")
    if zoom is not None:
        level: Optional[int] = None
        if isinstance(zoom, int) and not isinstance(zoom, bool):
            level = zoom
        elif isinstance(zoom, str) and zoom.strip().isdigit():
            level = int(zoom.strip())
        if level is None or level < 0 or level > 24:
            view_warnings.append("zoom must be an integer 0-24; ignored.")
        else:
            view["zoom"] = level
            view.setdefault("mode", "center")
    if view:
        per_call["view"] = view

    if style and isinstance(style, dict):
        per_call["layerStyle"] = {**(per_call.get("layerStyle") or {}), **style}
    if basemap is not None:
        per_call["basemap"] = basemap
    template_obj, warnings, source = viewer.load_template(service.templates_dir, per_call)
    warnings = view_warnings + warnings
    manifest.options = template_obj
    _, viewer_source, viewer_warnings = viewer.load_viewer_html(service.templates_dir)

    # Editing an existing map: remove named layers and/or replace the whole set.
    # Without this, show_map(map_id=...) could only APPEND, so a corrected map kept
    # serving its stale layers (issue report 2026-11-24).
    removed_ids: List[str] = []
    missing_ids: List[str] = []
    for layer_id in remove_layers or []:
        key = str(layer_id)
        if manifest.remove_layer(key):
            removed_ids.append(key)
        else:
            missing_ids.append(key)
    if missing_ids:
        warnings.append(
            "remove_layers: unknown layer id(s) " + ", ".join(missing_ids) + "; ignored."
        )
    if replace_layers:
        manifest.clear_layers()

    added = 0
    for spec in layers or []:
        layer = layer_from_spec(spec)
        publication = None
        if layer.kind == "portal-publication":
            publication = _require_publication(client, int(layer.publication_id))
        _apply_extent(client, layer, publication=publication, warnings=warnings)
        if layer.style and layer.resolved_render() in {"wms", "wmts"}:
            warnings.append(
                f"layer '{layer.title or layer.id}': style does not affect a "
                f"{layer.resolved_render().upper()} image layer (the server renders it); "
                "use the publication's own symbology, an SLD style (planned), or render 'wfs' "
                "for a client-styled vector layer."
            )
        manifest.add_layer(layer)
        added += 1

    # A per-call ``style`` with an explicit fill is a deliberate single style for
    # every layer; otherwise rotate a palette so layers are separable.
    if not (isinstance(style, dict) and style.get("fill")):
        _assign_layer_palette(manifest, template_obj)

    manifest.template_warnings = warnings + viewer_warnings

    base = service.base_url
    payload = manifest.public(base)
    for entry in payload.get("layers", []):
        _with_token(entry, service.token)

    viewer_url = f"{base}/map/{manifest.map_id}?t={service.token}"
    payload.update(
        {
            "serviceUrl": base,
            "manifestUrl": f"{base}/map/{manifest.map_id}/manifest.json",
            "viewerUrl": viewer_url,
            "accessToken": service.token,
            "tokenParameter": "t",
            "layersAdded": added,
            "corsEnabled": service.cors,
            "basemap": template_obj.get("basemap"),
            "templatePath": viewer.template_path(service.templates_dir),
            "templateUsed": source,
            "viewerHtmlPath": viewer.viewer_html_path(service.templates_dir),
            "viewerHtmlUsed": viewer_source,
            "templateWarnings": warnings + viewer_warnings,
            "viewerNote": (
                "Open viewerUrl in a browser on this machine to see the live map. The URL carries "
                "the local session token (?t=...); if a host or chat client strips it, append " +
                f"#t={service.token} instead. The portal credential never leaves the MCP process."
            ),
            "credentialNote": (
                "This is a low-sensitivity local session token, not the portal credential. "
                "The portal credential never leaves the MCP process (N5)."
            ),
        }
    )
    if replace_layers:
        payload["layersReplaced"] = True
    if removed_ids:
        payload["removedLayers"] = removed_ids

    if open_browser:
        try:
            import webbrowser

            payload["browserOpened"] = bool(webbrowser.open(viewer_url))
        except Exception:  # noqa: BLE001 - best effort, never fatal
            payload["browserOpened"] = False
    return payload