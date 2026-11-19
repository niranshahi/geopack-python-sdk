"""Async computed-column authoring (``httpx``).

Mirrors :class:`geopack_sdk.computed_columns.ComputedColumnManager`; the body
builder is shared so the two lanes cannot drift.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .computed_columns import _build_preview_body
from .models import ComputedColumnPreview


class AsyncComputedColumnManager:
    """Async twin of :class:`geopack_sdk.computed_columns.ComputedColumnManager`."""

    def __init__(self, client):
        self.client = client

    async def catalog(self, data_store_type: str) -> Dict[str, Any]:
        """Async twin of :meth:`ComputedColumnManager.catalog`."""
        if not isinstance(data_store_type, str) or not data_store_type.strip():
            raise ValueError("data_store_type must be a non-empty string.")
        response_data = await self.client.get(
            "/datasets/computed-column/catalog",
            params={"dataStoreType": data_store_type},
        )
        return response_data if isinstance(response_data, dict) else {}

    async def preview(
        self,
        *,
        data_store_type: str,
        fields: Optional[List[Any]] = None,
        shape_field: Optional[str] = None,
        oid_field: Optional[str] = None,
        expression: Optional[str] = None,
        calc: Optional[Dict[str, Any]] = None,
    ) -> ComputedColumnPreview:
        """Async twin of :meth:`ComputedColumnManager.preview`."""
        body = _build_preview_body(
            data_store_type=data_store_type,
            fields=fields,
            shape_field=shape_field,
            oid_field=oid_field,
            expression=expression,
            calc=calc,
        )
        response_data = await self.client.post(
            "/datasets/computed-column/preview", json=body
        )
        return ComputedColumnPreview(**(response_data or {}))
