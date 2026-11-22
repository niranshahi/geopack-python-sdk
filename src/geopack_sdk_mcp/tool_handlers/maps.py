"""Handler for ``geopack_sdk_show_map`` (slice 033, Lane A).

Stands up (or reuses) the local loopback data service, declares layers on a map
manifest and returns stable URLs a page can reference **instead of embedding
data** (N1/N2). The built-in viewer is Lane B and is deferred, so the payload
points at the data/tile URLs and says so honestly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..maps import get_or_start_service, layer_from_spec
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
) -> Dict[str, Any]:
    service = get_or_start_service(client)

    manifest = service.find_map(map_id) if map_id else None
    if map_id and manifest is None:
        raise MapServiceError(SERVICE_ERROR, "unknown map id.", key="map_id")
    if manifest is None:
        manifest = service.create_map(title or "Geopack map")
    elif title:
        manifest.title = title

    if basemap is not None:
        manifest.options["basemap"] = basemap

    added = 0
    for spec in layers or []:
        manifest.add_layer(layer_from_spec(spec))
        added += 1

    base = service.base_url
    payload = manifest.public(base)
    for entry in payload.get("layers", []):
        _with_token(entry, service.token)

    payload.update(
        {
            "serviceUrl": base,
            "manifestUrl": f"{base}/manifest/{manifest.map_id}",
            "accessToken": service.token,
            "tokenParameter": "t",
            "layersAdded": added,
            "corsEnabled": service.cors,
            "viewerUrl": None,
            "viewerNote": (
                "The built-in viewer is Lane B and is deferred in this build. Reference the "
                "layers' dataUrl/tileUrl from your own page; append ?t=<accessToken> for "
                "cross-origin fetches when GEOPACK_MCP_MAP_CORS=1 (same-origin pages need no token "
                "in the URL but still need the header/query on this service)."
            ),
            "credentialNote": (
                "This is a low-sensitivity local session token, not the portal credential. "
                "The portal credential never leaves the MCP process (N5)."
            ),
        }
    )

    if open_browser:
        # There is no viewer page yet (Lane B), so there is nothing to open —
        # opening the JSON manifest in a browser would be misleading.
        payload["browserOpened"] = False
        payload["browserNote"] = (
            "No browser was opened: the built-in viewer (Lane B) is not in this build, "
            "so there is no map page to open yet. Fetch serviceUrl/manifestUrl from your "
            "own page instead."
        )
    return payload