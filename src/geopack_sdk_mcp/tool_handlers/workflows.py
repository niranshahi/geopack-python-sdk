"""Workflow definition tool handlers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from geopack_sdk import GeopackClient

from ..serialize import to_jsonable


def list_workflows(
    client: GeopackClient,
    *,
    page: int = 1,
    page_size: int = 20,
    search_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    items = client.workflows.list(
        page=page,
        page_size=page_size,
        search_query=search_query,
    )
    return to_jsonable(items)
