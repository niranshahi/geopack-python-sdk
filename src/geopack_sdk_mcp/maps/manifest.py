"""Map manifest / layer models for the local data service (slice 033, Lane A)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LAYER_KINDS = frozenset(
    {"portal-dataset", "portal-publication", "local-file", "inline-geometry"}
)


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
    bbox: Optional[List[float]] = None
    query: Optional[Dict[str, Any]] = None

    def public(self, base_url: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title or self.id,
            "dataUrl": f"{base_url}/data/{self.id}",
        }
        if self.kind in ("portal-dataset", "portal-publication"):
            payload["tileUrl"] = f"{base_url}/tiles/{self.id}/{{z}}/{{x}}/{{y}}.pbf"
        if self.style:
            payload["style"] = self.style
        if self.bbox:
            payload["bbox"] = self.bbox
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
        bbox=spec.get("bbox"),
        query=spec.get("query"),
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