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
from ..maps.sources import dataset_info, publication_dataset_id, valid_wgs84_bbox

_WGS84_CRS = "EPSG:4326"
_AXIS_ORDER = "west,south,east,north"

#: Fallback when a template declares no ``layerPalette``.
_DEFAULT_LAYER_PALETTE = ("#3ba776", "#3b7fa7", "#c2703b", "#8b5cf6", "#d1477a", "#2f9e8f")

#: Renderers whose image is produced server-side (a per-layer ``style`` cannot
#: recolour them; only vector renderers honour it).
_RASTER_RENDERS = frozenset({"wms", "wmts", "xyz"})


def _assign_layer_palette(manifest: Any, template_obj: Dict[str, Any]) -> None:
    """Give each vector layer a distinct fill from the template palette.

    Layers without an explicit ``style.fill`` rotate through ``layerPalette`` so
    multiple layers are visually separable (one shared default colour made them
    indistinguishable). Server-rendered raster layers are skipped.
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

    if info.get("data_type") == "raster":
        layer.raster = True
        if layer.kind == "portal-dataset":
            warnings.append(
                f"layer '{label}': dataset {layer.dataset_id} is raster; a portal-dataset layer is "
                "served as vector GeoJSON/MVT and will not show an image — use a portal-publication "
                "layer (a raster WMS/WMTS publication) instead."
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
    if style and isinstance(style, dict):
        per_call["layerStyle"] = {**(per_call.get("layerStyle") or {}), **style}
    if basemap is not None:
        per_call["basemap"] = basemap
    template_obj, warnings, source = viewer.load_template(service.templates_dir, per_call)
    manifest.options = template_obj
    _, viewer_source, viewer_warnings = viewer.load_viewer_html(service.templates_dir)

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

    if open_browser:
        try:
            import webbrowser

            payload["browserOpened"] = bool(webbrowser.open(viewer_url))
        except Exception:  # noqa: BLE001 - best effort, never fatal
            payload["browserOpened"] = False
    return payload