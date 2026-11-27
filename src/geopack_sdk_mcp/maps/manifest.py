"""Map manifest / layer models for the local data service (slice 033, Lane A)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LAYER_KINDS = frozenset(
    {"portal-dataset", "portal-publication", "local-file", "inline-geometry"}
)

#: Viewer renderers a layer spec may request explicitly.
#:
#: ``rastertile`` is the portal's own HTTP raster-tile lane
#: (``GET /datasets/{id}/rastertile/{z}/{x}/{y}.png``): a PostGIS (or filesystem)
#: raster is rendered server-side with the dataset's saved display and streamed as
#: PNG XYZ tiles. Unlike ``cog`` it needs no Cloud-Optimized GeoTIFF and unlike
#: ``wms``/``wmts`` it needs no publication — the exact gap for a raster that is
#: stored but neither published nor COG.
RENDER_KINDS = frozenset(
    {"geojson", "mvt", "wms", "wmts", "wfs", "xyz", "cog", "rastertile"}
)


def _render_or_none(spec: Dict[str, Any]) -> Optional[str]:
    from .errors import SERVICE_ERROR, MapServiceError

    render = spec.get("render")
    if render is None:
        return None
    if render not in RENDER_KINDS:
        raise MapServiceError(
            SERVICE_ERROR,
            f"unknown render {render!r}; use one of: " + ", ".join(sorted(RENDER_KINDS)),
            key="render",
        )
    return render


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class MapLayer:
    """One declared layer, resolvable by a stable URL.

    ``path`` (local files) is kept internal — the public manifest exposes a
    ``/local`` URL, never an absolute host path (the errors contract rule).
    """

    id: str
    kind: str
    title: Optional[str] = None
    dataset_id: Optional[int] = None
    publication_id: Optional[int] = None
    path: Optional[str] = None
    geojson: Optional[Dict[str, Any]] = None
    style: Optional[Dict[str, Any]] = None
    #: The portable style spec (slice 033 §12) derived from the dataset's saved
    #: ESRI renderer. A vector layer applies it via a style FUNCTION and the
    #: legend is built from it; an explicit ``style`` overrides it.
    symbology: Optional[Dict[str, Any]] = None
    bbox: Optional[List[float]] = None
    bbox_crs: Optional[str] = None
    bbox_axis_order: Optional[str] = None
    query: Optional[Dict[str, Any]] = None
    render: Optional[str] = None
    xyz_url: Optional[str] = None
    #: Field labels + coded-value domains (``name``/``alias``/``domain``) for the
    #: viewer's identify popup, from the source dataset's ``details.fields``. Small;
    #: omitted when the layer declares none.
    fields: Optional[List[Dict[str, Any]]] = None
    #: The queryable WMS layer name a publication renders as, so the viewer's
    #: identify can send a ``GetFeatureInfo`` (``QUERY_LAYERS``) for an image
    #: layer. ``None`` for non-publication layers.
    identify_layers: Optional[str] = None
    #: Band descriptors for a raster/COG layer (from the dataset's ``details.bands``)
    #: so the viewer can label the value read at a click (band name, type, no-data).
    raster_bands: Optional[List[Dict[str, Any]]] = None
    #: GeoJSON page cap for a portal-dataset layer (``None`` = the 1,000 default;
    #: ``<= 0`` = unbounded — the server returns the whole dataset). The caller
    #: decides; the MCP never silently switches or truncates.
    limit: Optional[int] = None
    #: True when the layer's source is a raster (a raster dataset or a WMS/WMTS
    #: publication). The viewer shows a raster swatch for these, never a made-up
    #: vector colour, even when ``render`` is vector (a raster dataset is served
    #: as vector but shows nothing — the caller is warned).
    raster: bool = False
    #: True when a ``portal-dataset`` carries a Cloud-Optimized GeoTIFF the viewer
    #: can byte-serve directly (``details.hasCOG``). It then defaults to the ``cog``
    #: renderer and the manifest exposes a Range-capable ``cogUrl``.
    has_cog: bool = False
    #: True when the portal's raster-tile lane can render this dataset
    #: (``GET /datasets/{id}/rastertile/{z}/{x}/{y}.png``). The viewer then draws
    #: PNG XYZ tiles through the local ``/rasters`` proxy and the manifest exposes a
    #: ``rasterTileUrl`` template. Set by the handler from the source dataset's
    #: details; never guessed from the layer kind alone.
    raster_tile: bool = False
    #: The dataset's saved raster display block (``details.display``: displayType,
    #: bands, colorMap, min/max, ...). Kept **server-side only** — the local proxy
    #: forwards it upstream as the ``display`` query so the official symbology is
    #: applied by the portal renderer and never has to travel through the browser.
    raster_display: Optional[Dict[str, Any]] = None
    #: An OpenLayers ``WebGLTile`` style translated from ``raster_display`` for the
    #: client-side COG lane. Exposed in the manifest as ``rasterStyle``; the viewer
    #: sets it on the ``ol/layer/WebGLTile`` (constructed with ``normalize: false``).
    raster_style: Optional[Dict[str, Any]] = None
    #: Reference zoom for the raster-tile lane (the zoom whose resolution matches
    #: the raster's native pixel size). The portal uses it to pick/overview-create
    #: the right pyramid level; ``None`` lets the portal default apply.
    ref_zoom: Optional[int] = None

    def resolved_render(self) -> str:
        """The viewer renderer for this layer (explicit override or inferred)."""
        if self.render:
            return self.render
        if self.has_cog:
            return "cog"
        if self.raster_tile:
            return "rastertile"
        if self.xyz_url:
            return "xyz"
        if self.kind == "portal-publication":
            return "wms"
        return "geojson"

    def public(self, base_url: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title or self.id,
            "dataUrl": f"{base_url}/data/{self.id}",
            "render": self.resolved_render(),
        }
        if self.limit is not None:
            payload["limit"] = self.limit
        if self.kind in ("portal-dataset", "portal-publication"):
            payload["tileUrl"] = f"{base_url}/tiles/{self.id}/{{z}}/{{x}}/{{y}}.pbf"
        if self.kind == "portal-publication" and self.publication_id is not None:
            for protocol, key in (("wms", "wmsUrl"), ("wmts", "wmtsUrl"), ("wfs", "wfsUrl")):
                payload[key] = f"{base_url}/proxy/publication/{self.publication_id}/{protocol}"
        if self.xyz_url:
            payload["xyzUrl"] = self.xyz_url
        if self.fields:
            payload["fields"] = self.fields
        if self.identify_layers:
            payload["identifyWmsLayers"] = self.identify_layers
        if self.raster_bands:
            payload["rasterBands"] = self.raster_bands
        if self.has_cog and self.dataset_id is not None:
            payload["cogUrl"] = f"{base_url}/cog/{self.dataset_id}"
        if self.resolved_render() == "rastertile" and self.dataset_id is not None:
            # An XYZ template the browser can hand straight to ol/source/XYZ. The
            # local proxy adds the portal credential and the saved `display`.
            payload["rasterTileUrl"] = (
                f"{base_url}/rasters/{self.id}/{{z}}/{{x}}/{{y}}.png"
            )
        if self.resolved_render() == "cog" and self.raster_style:
            # A COG is drawn client-side; this is the OpenLayers WebGL style built
            # from the saved/caller `display` (colorMap or RGB).
            payload["rasterStyle"] = self.raster_style
        if self.raster:
            payload["raster"] = True
        if self.style:
            payload["style"] = self.style
        if self.symbology:
            payload["symbology"] = self.symbology
        if self.bbox:
            payload["bbox"] = self.bbox
            payload["bboxCrs"] = self.bbox_crs or "EPSG:4326"
            payload["bboxAxisOrder"] = self.bbox_axis_order or "west,south,east,north"
        return payload


@dataclass
class MapManifest:
    map_id: str
    title: str
    layers: Dict[str, MapLayer] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    template_warnings: List[str] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)

    def add_layer(self, layer: MapLayer) -> MapLayer:
        self.layers[layer.id] = layer
        return layer

    def remove_layer(self, layer_id: str) -> bool:
        """Drop one layer by id; ``True`` when it existed (so a typo is disclosed)."""
        return self.layers.pop(layer_id, None) is not None

    def clear_layers(self) -> None:
        """Drop every layer (used by ``show_map(replace_layers=True)``)."""
        self.layers.clear()

    def public(self, base_url: str) -> Dict[str, Any]:
        return {
            "mapId": self.map_id,
            "title": self.title,
            "createdAt": self.created_at,
            "layers": [layer.public(base_url) for layer in self.layers.values()],
            "options": self.options,
            "templateWarnings": list(self.template_warnings),
        }


def layer_from_spec(spec: Dict[str, Any]) -> MapLayer:
    """Build a ``MapLayer`` from a ``show_map`` layer spec (lenient)."""
    from .errors import SERVICE_ERROR, MapServiceError

    if not isinstance(spec, dict):
        raise MapServiceError(
            SERVICE_ERROR, "each layer must be an object.", key="layers"
        )
    kind = spec.get("kind") or _infer_kind(spec)
    if kind not in LAYER_KINDS:
        raise MapServiceError(
            SERVICE_ERROR,
            f"unknown layer kind {kind!r}; use one of: " + ", ".join(sorted(LAYER_KINDS)),
            key="kind",
        )
    layer = MapLayer(
        id=spec.get("id") or new_id("layer"),
        kind=kind,
        title=spec.get("title"),
        style=spec.get("style"),
        symbology=spec.get("symbology") if isinstance(spec.get("symbology"), dict) else None,
        raster_display=_display_or_none(spec),
        ref_zoom=_int_or_none(spec.get("refZoom") or spec.get("ref_zoom")),
        bbox=spec.get("bbox"),
        query=spec.get("query"),
        render=_render_or_none(spec),
        xyz_url=spec.get("xyzUrl") or spec.get("xyz_url"),
        limit=_int_or_none(spec.get("limit")),
    )
    if kind == "portal-dataset":
        layer.dataset_id = _int_or_none(spec.get("datasetId") or spec.get("dataset_id"))
        if layer.dataset_id is None:
            raise MapServiceError(
                SERVICE_ERROR, "a portal-dataset layer needs datasetId.", key="datasetId"
            )
    elif kind == "portal-publication":
        layer.publication_id = _int_or_none(
            spec.get("publicationId") or spec.get("publication_id")
        )
        if layer.publication_id is None:
            raise MapServiceError(
                SERVICE_ERROR,
                "a portal-publication layer needs publicationId.",
                key="publicationId",
            )
    elif kind == "local-file":
        layer.path = spec.get("path") or spec.get("localPath")
        if not layer.path:
            raise MapServiceError(
                SERVICE_ERROR, "a local-file layer needs path.", key="path"
            )
    elif kind == "inline-geometry":
        layer.geojson = spec.get("geojson") or spec.get("geometry")
        if not isinstance(layer.geojson, dict) or not layer.geojson:
            raise MapServiceError(
                SERVICE_ERROR,
                "an inline-geometry layer needs a GeoJSON geojson object.",
                key="geojson",
            )
    return layer


def _infer_kind(spec: Dict[str, Any]) -> str:
    if spec.get("datasetId") or spec.get("dataset_id"):
        return "portal-dataset"
    if spec.get("publicationId") or spec.get("publication_id"):
        return "portal-publication"
    if spec.get("path") or spec.get("localPath"):
        return "local-file"
    if spec.get("geojson") or spec.get("geometry"):
        return "inline-geometry"
    return "portal-dataset"


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _display_or_none(spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A caller-supplied raster display override (``display``/``rasterDisplay``)."""
    value = spec.get("display")
    if value is None:
        value = spec.get("rasterDisplay") or spec.get("raster_display")
    if isinstance(value, str) and value.strip():
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) and value else None