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
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunsplit

from .errors import SERVICE_ERROR, MapServiceError
from ..crs_utils import (
    WGS84 as _WGS84,
    coerce_mapping,
    honor_output_srid,
    looks_wgs84,
    srid_from_dataset,
)
from ..sanitize.dataset_symbology import (
    field_meta_from_details,
    styled_publications,
    summarise_symbology,
)
from ..sanitize.style_spec import dataset_style_spec, field_values_from_geojson
from ..serialize import to_jsonable

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
    limit: Optional[int] = 1000,
    out_srid: Optional[int] = 4326,
) -> Dict[str, Any]:
    """Fetch a dataset's records as a GeoJSON FeatureCollection (portal auth).

    ``out_srid`` defaults to **4326** so the browser gets WGS84 geometry. The
    portal stores many datasets in a projected/native CRS (e.g. Iran Lambert,
    metres); without this the viewer would plot projection-metre numbers as
    lon/lat and show nothing. If the portal ignores the request, the answer is
    repaired locally (:func:`_repair_to_wgs84`).

    ``limit`` caps the GeoJSON page (**1000** by default). ``limit <= 0`` means
    **unbounded**: the request carries no pagination limit, so the server returns
    the WHOLE dataset — the caller has decided to accept the payload cost. The
    server itself imposes no cap on this lane.
    """
    effective_out = out_srid
    try:
        if query:
            dsl = dict(query)
            projection = dict(dsl.get("projection") or {})
            if out_srid is not None:
                projection.setdefault("outSRID", int(out_srid))
            dsl["projection"] = projection
            # An explicit ``projection.outSRID`` wins (both here and at the portal),
            # so repair against what was really asked for, not the outer default.
            if projection.get("outSRID") is not None:
                effective_out = projection.get("outSRID")
            result = client.datasets.query(dataset_id, dsl)
        elif limit is None or int(limit) > 0:
            result = client.datasets.query(
                dataset_id, limit=int(limit or 1000), out_srid=out_srid
            )
        else:
            # Unbounded: send a projection with NO pagination limit so the server
            # returns every row (verified: no default LIMIT on POST /query).
            projection = {"returnGeometry": True}
            if out_srid is not None:
                projection["outSRID"] = int(out_srid)
            result = client.datasets.query(dataset_id, {"projection": projection})
    except MapServiceError:
        raise
    except Exception as exc:  # noqa: BLE001 - sanitize upstream errors
        raise MapServiceError(
            SERVICE_ERROR, _safe_message(exc), key="dataset_id"
        ) from exc
    return _repair_to_wgs84(client, dataset_id, _as_geojson(result), effective_out)


def dataset_feature_count(client: Any, dataset_id: int) -> Optional[int]:
    """Best-effort total feature count via the server COUNT (``None`` if unknown).

    Used only to TELL the caller how much is being truncated by a GeoJSON cap —
    the MCP never changes the layer's renderer or limit on its own.
    """
    try:
        page = client.datasets.query_paged(
            dataset_id, page=1, page_size=1, include_total_count=True
        )
    except Exception:  # noqa: BLE001 - discovery is best-effort
        return None
    pagination = getattr(page, "pagination", None)
    total = getattr(pagination, "total_count", None) if pagination is not None else None
    return int(total) if isinstance(total, int) else None


def dataset_field_values(
    client: Any, dataset_id: int, field: str, *, limit: int = 1000
) -> List[Any]:
    """A sample of one ``field``'s values, to derive a caller-requested symbology.

    Reads the same GeoJSON lane the viewer uses and keeps only the requested
    attribute, so a ``uniqueValue``/``classBreaks`` spec can be computed from the
    real distribution rather than a caller-guessed set of classes.
    """
    geojson = query_dataset_geojson(client, int(dataset_id), limit=int(limit))
    return field_values_from_geojson(geojson, field)


def _repair_to_wgs84(
    client: Any, dataset_id: int, geojson: Dict[str, Any], out_srid: Optional[int]
) -> Dict[str, Any]:
    """Repair a portal answer that ignored ``outSRID=4326`` (viewer needs lon/lat).

    The viewer plots coordinates directly, so a projected answer renders nowhere.
    When the first position is decisively non-lon/lat and the dataset's own SRID is
    known, the FeatureCollection is reprojected locally; otherwise it is returned
    unchanged (the same behaviour as before this safety net).
    """
    if out_srid is None:
        return geojson
    try:
        if int(out_srid) != _WGS84:
            return geojson
    except (TypeError, ValueError):
        return geojson
    if looks_wgs84(geojson) is not False:
        return geojson
    outcome = honor_output_srid(
        geojson,
        target_srid=_WGS84,
        source_srid=srid_from_dataset(_safe_dataset_raw(client, dataset_id)),
    )
    return outcome.feature_collection


def _safe_dataset_raw(client: Any, dataset_id: int) -> Any:
    try:
        return to_jsonable(client.datasets.get(dataset_id))
    except Exception:  # noqa: BLE001 - the layer still renders without the SRID
        return None


def valid_wgs84_bbox(value: Any) -> Optional[List[float]]:
    """Return ``[west, south, east, north]`` when plausible lon/lat, else ``None``.

    Rejects projected extents (metres) and swapped lat/lon boxes so a bad extent
    never drives the viewer's auto-fit to the wrong continent.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        west, south, east, north = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    if abs(west) > 180 or abs(east) > 180 or abs(south) > 90 or abs(north) > 90:
        return None
    if west >= east or south >= north:
        return None
    return [west, south, east, north]


def _as_details(value: Any) -> Dict[str, Any]:
    """Coerce ``details`` to a dict (see :func:`crs_utils.coerce_mapping`).

    The portal answers ``details`` as a JSON **string** for most datasets (only
    some come back as an object), so a dict-only read silently found no extent —
    the reason a projected dataset produced no ``bbox`` (live-QA 2026-11-22).
    """
    return coerce_mapping(value)


def dataset_info(client: Any, dataset_id: int) -> Dict[str, Any]:
    """Best-effort raw dataset facts for extent hints (never raises).

    Returns ``extent`` (WGS84 ``[W,S,E,N]``), ``data_type`` and ``srid``. The
    WGS84 extent comes from ``details.geo_extent`` (object **or** JSON string) and
    falls back to the stored top-level ``ext_west/south/east/north`` columns, so a
    layer gets a ``bbox`` for every dataset whose extent is known — regardless of
    the dataset's own (possibly projected) SRID.
    """
    info: Dict[str, Any] = {}
    try:
        raw = to_jsonable(client.datasets.get(dataset_id))
    except Exception:  # noqa: BLE001 - a map still works without an extent
        return info
    if not isinstance(raw, dict):
        return info
    data_type = raw.get("dataType")
    if data_type is not None:
        info["data_type"] = data_type

    details = _as_details(raw.get("details"))
    extent = valid_wgs84_bbox(details.get("geo_extent") or details.get("geoExtent"))
    if extent is None:
        extent = valid_wgs84_bbox(
            [
                raw.get("ext_west"),
                raw.get("ext_south"),
                raw.get("ext_east"),
                raw.get("ext_north"),
            ]
        )
    if extent is not None:
        info["extent"] = extent

    srid = srid_from_dataset(raw)
    if srid is not None:
        info["srid"] = srid

    info["symbology"] = summarise_symbology(raw)
    field_meta = field_meta_from_details(details)
    if field_meta:
        info["field_meta"] = field_meta
    spec = dataset_style_spec(raw)
    if spec is not None:
        info["style_spec"] = spec
    return info


def publication_dataset_id(publication: Any) -> Optional[int]:
    """The dataset a publication record belongs to, when the portal reports it.

    The SDK's ``Publication`` model dumps as ``{"raw": {...}}`` (the API payload
    under ``raw``), so the top level is searched **after** unwrapping ``raw`` —
    otherwise a publication layer could not borrow its source dataset's extent.
    """
    raw = to_jsonable(publication)
    if not isinstance(raw, dict):
        return None
    records: List[Dict[str, Any]] = [raw]
    inner = raw.get("raw")
    if isinstance(inner, dict):
        records.insert(0, inner)
    for record in records:
        for key in ("datasetId", "dataset_id"):
            value = record.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        dataset = record.get("dataset")
        if isinstance(dataset, dict) and dataset.get("id") is not None:
            try:
                return int(dataset["id"])
            except (TypeError, ValueError):
                return None
    return None


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


def merge_query(url: str, params: Dict[str, Any]) -> str:
    """Merge ``params`` onto a minted OGC URL (browser params win).

    Used by the viewer's WMS/WFS proxy: the minted URL carries the signed
    access query, and the browser adds ``GetMap``/``GetFeature`` parameters.
    """
    if not params:
        return url
    parts = urlsplit(url)
    merged = parse_qs(parts.query, keep_blank_values=True)
    for key, value in params.items():
        merged[key] = list(value) if isinstance(value, (list, tuple)) else [str(value)]
    query = urlencode(merged, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


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