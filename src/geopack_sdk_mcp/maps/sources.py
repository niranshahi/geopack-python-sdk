"""Source resolvers for the local map service (slice 033, Lane A).

Two families:

* **Portal** — fetch through the MCP's own authenticated session. The portal
  credential is *added* here server-side and never echoed; upstream error bodies
  are sanitized before they reach a response (N5).
* **Local** — an allow-listed file under ``GEOPACK_MCP_MAP_ROOT`` with realpath
  containment and an extension allow-list (no traversal, no listing).
"""

from __future__ import annotations

import json
import math
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
    resolve_raster_display,
    styled_publications,
    summarise_symbology,
)
from ..sanitize.filter_dsl import normalize_filter_node
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
    """A sample of one ``field``'s values, to derive a class-breaks symbology.

    Reads the same GeoJSON lane the viewer uses and keeps only the requested
    attribute, so a quantile ``classBreaks`` spec can be computed from a
    representative distribution rather than a caller-guessed set of classes. For a
    *categorical* spec use :func:`dataset_field_distinct_values` instead — a sample
    silently under-counts the categories of a large dataset.
    """
    geojson = query_dataset_geojson(client, int(dataset_id), limit=int(limit))
    return field_values_from_geojson(geojson, field)


#: The aggregate lane caps buckets at 50 (server rule), so a distinct-value probe
#: cannot ask for more than that in one call.
_AGGREGATE_MAX_BUCKETS = 50


def _group_value(row: Dict[str, Any], field: str) -> Any:
    """The groupBy value of a row (its ``field`` key, or the first non-count key)."""
    if field in row:
        return row.get(field)
    for key, value in row.items():
        if key not in ("n", "count", "aggregate_count"):
            return value
    return None


def dataset_field_distinct_values(
    client: Any, dataset_id: int, field: str, *, max_values: int
) -> Tuple[List[Any], bool]:
    """The DISTINCT values of one field, via the aggregate groupBy lane.

    Returns ``(values, truncated)``. Sampling the first N features of a large
    dataset silently under-counts categories (an 18,648-row dataset sampled 1,000
    rows and styled only 7 of 18 classes — issue report 2026-11-24); grouping the
    whole access-scoped column is exact. ``truncated`` is ``True`` when the store
    holds more distinct values than ``max_values`` — the caller decides what to do
    (never silently under-style). The bucket cap (50) is a server rule, so the
    probe asks for ``max_values + 1`` clamped to it. Raises on a bad field name so
    the caller can warn instead of failing the whole map.
    """
    probe = max(1, min(int(max_values) + 1, _AGGREGATE_MAX_BUCKETS))
    aggregation: Dict[str, Any] = {
        "aggregates": [{"aggregate": "count", "alias": "n"}],
        "groupBy": [{"field": field}],
        "limit": probe,
    }
    result = client.datasets.aggregate(int(dataset_id), aggregation=aggregation)
    rows = [
        row for row in (getattr(result, "rows", None) or []) if isinstance(row, dict)
    ]
    values = [_group_value(row, field) for row in rows]
    truncated = len(values) > int(max_values)
    return values[: int(max_values)], truncated


def dataset_distinct_count(
    client: Any, dataset_id: int, field: str
) -> Optional[int]:
    """Best-effort exact count of distinct ``field`` values (``None`` if unknown).

    Used only to make a truncation warning precise; it never changes the result.
    """
    try:
        return int(client.datasets.count(int(dataset_id), field=field, distinct=True))
    except Exception:  # noqa: BLE001 - the warning degrades without the exact total
        return None


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dataset_field_quantiles(
    client: Any,
    dataset_id: int,
    field: str,
    *,
    classes: int,
    where_filter: Optional[Any] = None,
) -> Optional[List[Tuple[float, float]]]:
    """Server-side quantile class breaks over the FULL, optionally filtered column.

    A feature sample both under-counts a large dataset's tails and IGNORES the
    layer's filter, so a sampled ``classBreaks`` legend can be wrong by orders of
    magnitude (issue report 2026-11-24, N2 — a filtered 356-row layer produced the
    same breaks as the whole 18,648-row dataset, every one below the layer's
    minimum). ``percentile`` / ``min`` / ``max`` come from the aggregate lane, so
    the breaks span the true extremes of exactly the rows the layer draws.

    Returns ``None`` when the store cannot aggregate, the field is unusable, or the
    filter cannot be normalized — the caller then falls back to a sampled estimate
    AND says so in ``templateWarnings``.
    """
    class_count = int(classes)
    if class_count < 1:
        return None
    normalized: Optional[Any] = None
    if where_filter is not None:
        try:
            normalized = normalize_filter_node(where_filter, key="query")
        except Exception:  # noqa: BLE001 - fall back rather than send a bad node
            return None
    aggregates: List[Dict[str, Any]] = [
        {"aggregate": "min", "field": field, "alias": "mn"},
        {"aggregate": "max", "field": field, "alias": "mx"},
    ]
    for index in range(1, class_count):
        aggregates.append(
            {
                "aggregate": "percentile",
                "field": field,
                "p": round(index / class_count, 6),
                "alias": f"q{index}",
            }
        )
    try:
        result = client.datasets.aggregate(
            int(dataset_id),
            aggregation={"aggregates": aggregates, "limit": 1},
            filter=normalized,
        )
    except Exception:  # noqa: BLE001 - the caller falls back to a sample
        return None
    rows = [
        row for row in (getattr(result, "rows", None) or []) if isinstance(row, dict)
    ]
    if not rows:
        return None
    row = rows[0]
    low = _as_float(row.get("mn"))
    high = _as_float(row.get("mx"))
    if low is None or high is None:
        return None
    edges: List[float] = [low]
    for index in range(1, class_count):
        value = _as_float(row.get(f"q{index}"))
        if value is None:
            return None
        edges.append(value)
    edges.append(high)
    edges.sort()
    breaks: List[Tuple[float, float]] = []
    for index in range(class_count):
        lo, hi = edges[index], edges[index + 1]
        if hi < lo:
            hi = lo
        breaks.append((lo, hi))
    return breaks


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


#: MBTiles container extensions (the filesystem adapter serves tiles from these).
_MBTILES_EXTENSIONS = (".mbtiles",)
#: Web Mercator metres per degree at the equator (for a native-zoom estimate).
_MERCATOR_METRES_PER_DEGREE = 111319.49079327358
#: Web Mercator world circumference in metres (matches the portal's own math).
_MERCATOR_CIRCUMFERENCE = 40075016.686
#: The portal renders 256-pixel raster tiles by default.
_RASTER_TILE_SIZE = 256


def raster_is_mbtiles(details: Dict[str, Any]) -> bool:
    """True when the raster source is an MBTiles container (pre-rendered tiles).

    An MBTiles raster is served by the raster-tile lane, but its pictures are
    **stored**, so a caller ``display`` cannot recolour it (unlike a PostGIS
    raster, which the portal renders on demand).
    """
    sub_type = str(details.get("subType") or details.get("subtype") or "").lower()
    storage_type = str(details.get("storageType") or "").lower()
    if (
        "mbtiles" in sub_type
        or storage_type == "mbtiles"
        or details.get("hasMBTiles")
        or isinstance(details.get("mbtiles_metadata"), dict)
    ):
        return True
    file_path = details.get("filePath") or details.get("file_path") or details.get("path")
    return isinstance(file_path, str) and file_path.lower().endswith(_MBTILES_EXTENSIONS)


def raster_tile_capable(details: Dict[str, Any]) -> bool:
    """True when the portal's raster-tile lane can render this dataset.

    The portal serves ``GET /datasets/{id}/rastertile/{z}/{x}/{y}.png`` for:

    * a raster stored in a **PostGIS raster table** (the Postgres adapter —
      ``ST_AsPNG`` server-side), and
    * an **MBTiles** dataset (the filesystem adapter reads the tile from the
      SQLite container).

    This is the lane that fills the gap the report named: a raster with **no
    publication** and **no COG**. It is **not** used when the dataset has a COG
    (``hasCOG``) — the direct ``/cog`` byte lane is better — nor for a plain
    filesystem GeoTIFF, which the adapter cannot tile yet.
    """
    if details.get("hasCOG"):
        return False
    if raster_is_mbtiles(details):
        return True
    source = details.get("source") if isinstance(details.get("source"), dict) else {}
    driver = str(source.get("driver") or details.get("driver") or "").lower()
    if driver in ("postgresql", "postgres"):
        return True
    if details.get("dbTableName") and (
        details.get("rasterDbColumn") or details.get("tableName")
    ):
        return True
    return False


def _zoom_for_resolution(resolution_metres: Any) -> Optional[int]:
    """The XYZ zoom whose Web Mercator resolution matches ``resolution_metres``."""
    try:
        resolution = float(resolution_metres)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(resolution) or resolution <= 0:
        return None
    zoom = math.log2(_MERCATOR_CIRCUMFERENCE / (_RASTER_TILE_SIZE * resolution))
    if not math.isfinite(zoom):
        return None
    return max(0, min(24, int(round(zoom))))


def reference_zoom_for_raster(
    details: Dict[str, Any], extent: Optional[List[float]]
) -> Optional[int]:
    """The zoom matching the raster's native pixel size (its best pyramid level).

    The portal picks a raster overview with ``2 ** (ref_z - z)``, so a wrong
    ``ref_z`` either wastes a full-resolution read or blurs the image with an
    over-decimated overview. The frontend derives it from
    ``details.metadata_3857.scalex``; when that is absent (PostGIS rasters often
    omit it) this falls back to ``geo_extent`` width / ``rasterSize.x`` in Web
    Mercator metres, which is the same quantity. ``None`` keeps the portal default.
    """
    metadata = details.get("metadata_3857")
    if isinstance(metadata, dict):
        zoom = _zoom_for_resolution(metadata.get("scalex"))
        if zoom is not None:
            return zoom
    size = details.get("rasterSize")
    size = size if isinstance(size, dict) else {}
    width = size.get("x") or size.get("width")
    if extent and width:
        try:
            degrees_per_pixel = (float(extent[2]) - float(extent[0])) / float(width)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
        if degrees_per_pixel > 0:
            return _zoom_for_resolution(degrees_per_pixel * _MERCATOR_METRES_PER_DEGREE)
    return None


def _display_for_query(display: Dict[str, Any]) -> Dict[str, Any]:
    """Strip display keys the portal renderer does not accept.

    Mirrors the SPA's ``MyRasterWebTileLayer``: a ``customColorMap`` entry's
    ``caption`` is removed before the display is sent as a query value.
    """
    clean = dict(display)
    color_map = clean.get("customColorMap")
    if isinstance(color_map, list):
        clean["customColorMap"] = [
            {key: value for key, value in item.items() if key != "caption"}
            if isinstance(item, dict)
            else item
            for item in color_map
        ]
    return clean


def dataset_raster_tile_url(
    client: Any,
    dataset_id: int,
    z: int,
    x: int,
    y: int,
    *,
    display: Optional[Dict[str, Any]] = None,
    ref_zoom: Optional[int] = None,
    tile_size: Optional[int] = None,
) -> str:
    """The portal's PNG raster-tile URL (the ``/n``/``rastertile`` lane).

    ``display`` carries the dataset's saved raster display (bands / colorMap /
    min-max) so the portal applies the official symbology; it is sent as a JSON
    query value exactly like the SPA does. ``ref_zoom`` selects the pyramid level.
    """
    params: Dict[str, Any] = {}
    if tile_size is not None:
        params["tileSize"] = int(tile_size)
    if ref_zoom is not None:
        params["ref_z"] = int(ref_zoom)
    if display:
        params["display"] = json.dumps(
            _display_for_query(display), ensure_ascii=False, separators=(",", ":")
        )
    url = portal_url(
        client, f"/datasets/{int(dataset_id)}/rastertile/{int(z)}/{int(x)}/{int(y)}.png"
    )
    return f"{url}?{urlencode(params)}" if params else url


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

    if details.get("hasCOG"):
        info["has_cog"] = True
    bands = details.get("bands")
    if isinstance(bands, list) and bands:
        info["bands"] = [band for band in bands if isinstance(band, dict)]
    display = resolve_raster_display(details)
    if isinstance(display, dict) and display:
        # The saved raster display (bands / colorMap / min-max). The map proxy
        # forwards it to the portal renderer so the official symbology is applied.
        info["display"] = display
    if str(data_type or "").lower() == "raster" and raster_tile_capable(details):
        info["raster_tile"] = True
        info["mbtiles"] = raster_is_mbtiles(details)
        ref_zoom = reference_zoom_for_raster(details, info.get("extent"))
        if ref_zoom is not None:
            info["ref_zoom"] = ref_zoom
    info["symbology"] = summarise_symbology(raw)
    field_meta = field_meta_from_details(details)
    if field_meta:
        info["field_meta"] = field_meta
    spec = dataset_style_spec(raw)
    if spec is not None:
        info["style_spec"] = spec
    return info


def publication_layer_name(publication: Any) -> Optional[str]:
    """The WMS/WMTS layer name a publication renders as (for ``GetFeatureInfo``).

    The portal record carries ``canonicalName`` (and the mint descriptor may carry
    ``layerName``); either names the queryable GeoServer layer, which a WMS
    ``GetFeatureInfo`` request must send as ``QUERY_LAYERS``.
    """
    raw = to_jsonable(publication)
    if not isinstance(raw, dict):
        return None
    records: List[Dict[str, Any]] = [raw]
    inner = raw.get("raw")
    if isinstance(inner, dict):
        records.insert(0, inner)
    for record in records:
        for key in ("layerName", "canonicalName", "wmsLayer"):
            value = record.get(key)
            if isinstance(value, str) and value:
                return value
    return None


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


def dataset_cog_url(client: Any, dataset_id: int) -> str:
    """The portal's COG byte-serving endpoint (``GET /datasets/{id}/cog``)."""
    return portal_url(client, f"/datasets/{int(dataset_id)}/cog")


def portal_range_get(
    client: Any, url: str, *, range_header: Optional[str] = None
) -> Tuple[int, Dict[str, str], bytes]:
    """A raw portal GET that forwards a ``Range`` header (COG byte serving).

    Returns ``(status, headers, body)`` where ``headers`` carries the HTTP metadata
    a COG reader needs (``Content-Type``, ``Content-Range``, ``Accept-Ranges``). A
    ``206`` is a valid partial answer, not an error. The portal credential stays
    server-side.
    """
    headers = auth_headers(client)
    if range_header:
        headers = {**headers, "Range": range_header}
    try:
        response = client.session.get(url, headers=headers, timeout=60)
    except Exception as exc:  # noqa: BLE001
        raise MapServiceError(SERVICE_ERROR, _safe_message(exc)) from exc
    if not response.ok and response.status_code != 206:
        raise MapServiceError(
            SERVICE_ERROR,
            f"upstream answered HTTP {response.status_code}.",
            status=response.status_code,
        )
    content_type = (response.headers.get("Content-Type") or "image/tiff").split(";")[0]
    passthrough = {"Content-Type": content_type}
    for name in ("Content-Range", "Accept-Ranges"):
        value = response.headers.get(name)
        if value:
            passthrough[name] = value
    passthrough.setdefault("Accept-Ranges", "bytes")
    return response.status_code, passthrough, response.content


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