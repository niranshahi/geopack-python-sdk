"""Client-side CRS helpers for the dataset and map lanes (slice 033 robustness).

The portal owns reprojection: :func:`query_dataset` asks for ``out_srid`` and the
map lane for ``projection.outSRID``. A live-QA report (2026-11-22) showed the
portal can *silently ignore* that request and hand back the dataset's native
projected coordinates — metre numbers a WGS84 client plots nowhere, while the
payload still claims the requested SRID. These helpers make the answer
**verifiable and repairable**:

* :func:`parse_epsg` / :func:`srid_from_dataset` — read an EPSG code from the many
  shapes the portal uses (``4326``, ``"EPSG:4326"``, an OGC URN, ``{"srid": ...}``).
* :func:`looks_wgs84` — does a GeoJSON payload actually carry lon/lat degrees?
* :func:`reproject_feature_collection` — repair it locally with ``pyproj``.

``pyproj`` is imported **lazily**, inside the reprojection call, and this module —
deliberately outside the ``geometry/`` package — is the only non-geometry place
that touches it. The map/dataset lanes must keep working on a host where the
optional geometry extras are absent, so a missing ``pyproj`` degrades to the loud
``crsNote`` warning, never a crash.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .serialize import to_jsonable

#: Every WGS84 name keys the portal may use to name a CRS in a descriptors dict.
_CRS_KEYS = ("srid", "wkid", "latestWkid", "EPSG", "epsg")
#: The final integer of a CRS string ("EPSG:4326", "urn:...:EPSG::32640", "4326").
_EPSG_TAIL = re.compile(r"(\d{3,6})\s*$")
_EPSG_ANY = re.compile(r"(\d{3,6})")

WGS84 = 4326


def coerce_mapping(value: Any) -> Dict[str, Any]:
    """Coerce ``details`` (object **or** JSON string) to a dict, else ``{}``.

    The portal answers ``details`` as a JSON string for most datasets; a dict-only
    read silently finds nothing (the original cause of a missing projected extent).
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def parse_epsg(value: Any) -> Optional[int]:
    """Best-effort EPSG code from an int/float/str/dict, or ``None``.

    Never raises and never guesses from text without digits: an unparseable or
    empty value (e.g. the portal's ``{}`` spatial reference) is ``None``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value > 0 else None
    if isinstance(value, dict):
        for key in _CRS_KEYS:
            code = parse_epsg(value.get(key))
            if code is not None:
                return code
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        match = _EPSG_TAIL.search(text) or _EPSG_ANY.search(text)
        if match is None:
            return None
        code = int(match.group(1))
        return code if code > 0 else None
    return None


def srid_from_dataset(raw: Any) -> Optional[int]:
    """The native EPSG SRID of a dataset payload, or ``None`` if it declares none.

    Order: ``details.spatialReference`` (object or scalar), then ``srid``/``wkid``
    on ``details`` and the top level. Covers the live portal's mixed shapes
    (2580 → 4326, 2436 → 32640, 2554 → none).
    """
    if not isinstance(raw, dict):
        return None
    details = coerce_mapping(raw.get("details"))
    spatial = details.get("spatialReference") or details.get("spatial_reference")
    code = parse_epsg(spatial)
    if code is not None:
        return code
    for source in (details, raw):
        for key in ("srid", "wkid", "latestWkid"):
            code = parse_epsg(source.get(key))
            if code is not None:
                return code
    return None


def dataset_srid(client: Any, dataset_id: int) -> Optional[int]:
    """Fetch a dataset and read its native SRID (best-effort, never raises)."""
    try:
        raw = to_jsonable(client.datasets.get(dataset_id))
    except Exception:  # noqa: BLE001 - a query still works without the source CRS
        return None
    return srid_from_dataset(raw)


def first_position(geometry: Any) -> Optional[Tuple[float, float]]:
    """The first ``(x, y)`` of a GeoJSON geometry (nested coordinates unwrapped)."""
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    while isinstance(coords, list) and coords and isinstance(coords[0], list):
        coords = coords[0]
    if (
        isinstance(coords, list)
        and len(coords) >= 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in coords[:2])
    ):
        return coords[0], coords[1]
    return None


def looks_wgs84(payload: Any) -> Optional[bool]:
    """``True``/``False`` for the first feature's position, or ``None`` if unknown.

    ``None`` means "cannot tell" (no features, no coordinates) — the caller trusts
    the portal. A ``False`` is decisive evidence the payload is NOT lon/lat.
    """
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return None
    for feature in features:
        if isinstance(feature, dict):
            position = first_position(feature.get("geometry"))
            if position is not None:
                x, y = position
                return abs(x) <= 180 and abs(y) <= 90
    return None


def _reproject_position(coords: Any, transformer: Any) -> Any:
    if not isinstance(coords, (list, tuple)) or not coords:
        return coords
    first = coords[0]
    if isinstance(first, (int, float)) and not isinstance(first, bool):
        if len(coords) >= 2 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in coords[:2]
        ):
            x, y = transformer.transform(float(coords[0]), float(coords[1]))
            return [float(x), float(y), *list(coords[2:])]
        return list(coords)
    return [_reproject_position(item, transformer) for item in coords]


def _reproject_geometry(geometry: Any, transformer: Any) -> Any:
    if not isinstance(geometry, dict):
        return geometry
    out = dict(geometry)
    if geometry.get("type") == "GeometryCollection":
        out["geometries"] = [
            _reproject_geometry(geom, transformer)
            for geom in geometry.get("geometries") or []
        ]
    else:
        out["coordinates"] = _reproject_position(geometry.get("coordinates"), transformer)
    return out


def reproject_feature_collection(
    payload: Any, source_srid: int, target_srid: int
) -> Dict[str, Any]:
    """Reproject every feature of a FeatureCollection ``source_srid -> target_srid``.

    ``pyproj`` is imported here (lazily); this is the only heavy import in the
    module. The output embeds the standard ``crs`` member the geometry lane uses.
    """
    from pyproj import Transformer

    transformer = Transformer.from_crs(
        f"EPSG:{int(source_srid)}", f"EPSG:{int(target_srid)}", always_xy=True
    )
    base = dict(payload) if isinstance(payload, dict) else {}
    features = []
    for feature in base.get("features") or []:
        if isinstance(feature, dict):
            new_feature = dict(feature)
            if isinstance(feature.get("geometry"), dict):
                new_feature["geometry"] = _reproject_geometry(
                    feature["geometry"], transformer
                )
            features.append(new_feature)
        else:
            features.append(feature)
    base["features"] = features
    base["crs"] = {
        "type": "name",
        "properties": {"name": f"urn:ogc:def:crs:EPSG::{int(target_srid)}"},
    }
    return base


@dataclass(frozen=True)
class OutputSridResult:
    """The verdict of :func:`honor_output_srid`."""

    feature_collection: Dict[str, Any]
    applied_srid: Optional[int]
    note: Optional[str]
    reprojected: bool


def honor_output_srid(
    payload: Dict[str, Any],
    *,
    target_srid: Optional[int],
    source_srid: Optional[Any] = None,
) -> OutputSridResult:
    """Guarantee the payload is really in ``target_srid`` — or say it is not.

    The portal is trusted for any non-4326 target (its degree/metre range cannot be
    cheaply verified). For ``4326`` the payload's first position is checked: a
    decisive non-lon/lat answer is **repaired locally** with ``pyproj`` when the
    source SRID is known, and otherwise reported via ``note`` (never silently
    passed off as WGS84). ``applied_srid`` is the CRS actually in the payload.
    """
    if target_srid is None:
        return OutputSridResult(payload, None, None, False)

    target = int(target_srid)
    if target != WGS84:
        return OutputSridResult(payload, target, None, False)

    if looks_wgs84(payload) is not False:
        # True (honoured) or None (nothing to check): trust the portal.
        return OutputSridResult(payload, WGS84, None, False)

    source = parse_epsg(source_srid)
    if source is None or source == WGS84:
        return OutputSridResult(
            payload,
            None,
            "Geometry coordinates still look projected (not EPSG:4326 lon/lat) after "
            "requesting out_srid=4326, and the source CRS is not known, so the result "
            "could not be repaired locally. Use a portal-publication (WMS) layer, or "
            "query the source in its own CRS.",
            False,
        )

    try:
        repaired = reproject_feature_collection(payload, source, WGS84)
    except Exception as exc:  # noqa: BLE001 - pyproj missing or transform failure
        return OutputSridResult(
            payload,
            None,
            "Geometry coordinates look projected (not EPSG:4326 lon/lat) after requesting "
            f"out_srid=4326; local reprojection from EPSG:{source} failed "
            f"({type(exc).__name__}). Use a portal-publication (WMS) layer.",
            False,
        )

    return OutputSridResult(
        repaired,
        WGS84,
        "The portal returned EPSG:"
        f"{source} coordinates despite out_srid=4326; they were reprojected to EPSG:4326 "
        "locally by the MCP.",
        True,
    )
