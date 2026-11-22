"""Handler for ``geopack_sdk_show_map`` (slice 033, Lane A).

Stands up (or reuses) the local loopback data service, declares layers on a map
manifest and returns stable URLs a page can reference **instead of embedding
data** (N1/N2). The built-in viewer is Lane B and is deferred, so the payload
points at the data/tile URLs and says so honestly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..maps import get_or_start_service, layer_from_spec
from ..maps import viewer
from ..maps.errors import SERVICE_ERROR, MapServiceError


def _with_token(entry: Dict[str, Any], token: str) -> None:
    data_url = entry.get("dataUrl")
    if data_url:
        entry["dataUrlWithToken"] = f"{data_url}?t={token}"
    tile_url = entry.get("tileUrl")
    if tile_url:
        entry["tileUrlWithToken"] = f"{tile_url}?t={token}"


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
    manifest.template_warnings = warnings + viewer_warnings

    added = 0
    for spec in layers or []:
        manifest.add_layer(layer_from_spec(spec))
        added += 1

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