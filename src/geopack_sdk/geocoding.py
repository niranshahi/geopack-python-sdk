"""Place name → WGS84 bbox via OpenStreetMap Nominatim."""

from __future__ import annotations

from typing import Any, Dict, List, Union

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = (
    "geopack-sdk/1.0 (Geoportal MCP geocoding; +https://github.com/niranshahi/geopack-python-sdk)"
)


def geocode_place(
    query: str,
    *,
    limit: int = 1,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Resolve a place name to WGS84 bbox via Nominatim HTTP API.

    Returns dict (limit==1) or list of dicts with keys:
    ``display_name``, ``lat``, ``lon``, ``bbox`` as [west, south, east, north].
    """
    params = {
        "q": query.strip(),
        "format": "json",
        "limit": max(1, min(limit, 10)),
        "addressdetails": 0,
    }
    headers = {"User-Agent": user_agent}
    response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise ValueError(f"No Nominatim results for: {query!r}")

    parsed = [_nominatim_row_to_result(row) for row in rows]
    return parsed[0] if limit == 1 else parsed


def _nominatim_row_to_result(row: Dict[str, Any]) -> Dict[str, Any]:
    south, north, west, east = (float(v) for v in row["boundingbox"])
    return {
        "display_name": row.get("display_name"),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "bbox": [west, south, east, north],
    }
