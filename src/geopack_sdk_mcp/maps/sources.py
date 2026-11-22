"""Source resolvers for the local map service (slice 033, Lane A).

Two families:

* **Portal** — fetch through the MCP's own authenticated session. The portal
  credential is *added* here server-side and never echoed; upstream error bodies
  are sanitized before they reach a response (N5).
* **Local** — an allow-listed file under ``GEOPACK_MCP_MAP_ROOT`` with realpath
  containment and an extension allow-list (no traversal, no listing).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .errors import SERVICE_ERROR, MapServiceError

#: Local file extensions the service may serve.
LOCAL_EXTENSIONS = frozenset({".geojson", ".json", ".gpkg", ".csv", ".kml", ".zip"})
#: Hard cap for a local file read (bytes).
MAX_LOCAL_BYTES = 50 * 1024 * 1024

CONTENT_TYPES: Dict[str, str] = {
    ".geojson": "application/geo+json",
    ".json": "application/json",
    ".gpkg": "application/geopackage+sqlite3",
    ".csv": "text/csv",
    ".kml": "application/vnd.google-earth.kml+xml",
    ".zip": "application/zip",
}


def auth_headers(client: Any) -> Dict[str, str]:
    """The Bearer header for portal calls (never logged, never echoed)."""
    token = getattr(getattr(client, "auth", None), "token", None)
    return {"Authorization": f"Bearer {token}"} if token else {}


def portal_url(client: Any, path: str) -> str:
    base = str(getattr(client, "base_url", "") or "").rstrip("/")
    if not base:
        raise MapServiceError(SERVICE_ERROR, "the portal base URL is not configured.")
    return f"{base}/{path.lstrip('/')}"


def safe_local_path(root: Optional[str], ref: str) -> Tuple[str, str]:
    """Resolve ``ref`` under ``root``; return ``(absolute_path, extension)``.

    Raises :class:`MapServiceError` on a missing root, a non-allow-listed
    extension, an escape outside the root, or a missing file.
    """
    if not root:
        raise MapServiceError(
            SERVICE_ERROR,
            "GEOPACK_MCP_MAP_ROOT is not set; local files cannot be served.",
            key="path",
        )
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, ref))
    if os.path.commonpath([root_real, candidate]) != root_real:
        raise MapServiceError(
            SERVICE_ERROR, "local path escapes the configured map root.", key="path"
        )
    extension = os.path.splitext(candidate)[1].lower()
    if extension not in LOCAL_EXTENSIONS:
        raise MapServiceError(
            SERVICE_ERROR,
            f"extension {extension!r} is not allow-listed.",
            key="path",
        )
    if not os.path.isfile(candidate):
        raise MapServiceError(SERVICE_ERROR, "local file not found.", key="path")
    if os.path.getsize(candidate) > MAX_LOCAL_BYTES:
        raise MapServiceError(SERVICE_ERROR, "local file exceeds the size cap.", key="path")
    return candidate, extension


def read_local_file(root: Optional[str], ref: str) -> Tuple[bytes, str]:
    path, extension = safe_local_path(root, ref)
    with open(path, "rb") as handle:
        return handle.read(MAX_LOCAL_BYTES), CONTENT_TYPES.get(extension, "application/octet-stream")


def _as_geojson(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    raise MapServiceError(SERVICE_ERROR, "the portal returned an unexpected dataset payload.")


def query_dataset_geojson(
    client: Any,
    dataset_id: int,
    *,
    query: Optional[Dict[str, Any]] = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    """Fetch a dataset's records as a GeoJSON FeatureCollection (portal auth)."""
    try:
        if query:
            result = client.datasets.query(dataset_id, query)
        else:
            result = client.datasets.query(dataset_id, limit=limit)
    except MapServiceError:
        raise
    except Exception as exc:  # noqa: BLE001 - sanitize upstream errors
        raise MapServiceError(
            SERVICE_ERROR, _safe_message(exc), key="dataset_id"
        ) from exc
    return _as_geojson(result)


def portal_get_bytes(
    client: Any, url: str, *, params: Optional[Dict[str, Any]] = None
) -> Tuple[int, str, bytes]:
    """A raw portal GET (tiles/images) using the authenticated session."""
    headers = auth_headers(client)
    try:
        response = client.session.get(url, headers=headers, params=params, timeout=30)
    except Exception as exc:  # noqa: BLE001
        raise MapServiceError(SERVICE_ERROR, _safe_message(exc)) from exc
    content_type = (response.headers.get("Content-Type") or "application/octet-stream").split(";")[0]
    if not response.ok:
        raise MapServiceError(
            SERVICE_ERROR, f"upstream answered HTTP {response.status_code}.", status=response.status_code
        )
    return response.status_code, content_type, response.content


def dataset_tile_url(client: Any, dataset_id: int, z: int, x: int, y: int) -> str:
    return portal_url(client, f"/datasets/{dataset_id}/mvt/{z}/{x}/{y}.pbf")


def mint_publication_url(client: Any, publication_id: int, protocol: str) -> str:
    """Mint a signed render URL and return it (protocol-specific key)."""
    managers = {
        "tiles": ("mint_tiles_url", "tileUrl"),
        "wms": ("mint_wms_url", "wmsUrl"),
        "wmts": ("mint_wmts_url", "wmtsUrl"),
        "wfs": ("mint_wfs_url", "wfsUrl"),
    }
    if protocol not in managers:
        raise MapServiceError(
            SERVICE_ERROR,
            f"unknown publication protocol {protocol!r}.",
            key="protocol",
        )
    method_name, url_key = managers[protocol]
    try:
        descriptor = getattr(client.publications, method_name)(publication_id)
    except Exception as exc:  # noqa: BLE001
        raise MapServiceError(SERVICE_ERROR, _safe_message(exc)) from exc
    if isinstance(descriptor, dict):
        url = descriptor.get(url_key) or descriptor.get("url")
    else:
        url = None
    if not url:
        raise MapServiceError(
            SERVICE_ERROR, f"the mint answer carried no {url_key}.", key="publicationId"
        )
    return str(url)


def url_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def allowed_upstream(url: str, portal_base: str, extra_hosts: List[str]) -> bool:
    """Only the portal host (and explicitly configured hosts) may be proxied."""
    host = url_host(url)
    allowed = {url_host(portal_base)} | {h.lower() for h in extra_hosts if h}
    return bool(host) and host in allowed


def _safe_message(exc: BaseException) -> str:
    """A short message with no token, host path or request detail."""
    status = getattr(exc, "status_code", None)
    message = str(getattr(exc, "message", "") or "")
    if not message:
        message = type(exc).__name__
    if status:
        return f"{message} (HTTP {status})"
    return message