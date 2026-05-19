"""Geocoding tool handler (Nominatim — not Geopack API)."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from geopack_sdk.geocoding import geocode_place as _geocode_place


def geocode_place(query: str, *, limit: int = 1) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Resolve place name to WGS84 bbox for MCP / LLM tools."""
    return _geocode_place(query, limit=limit)
