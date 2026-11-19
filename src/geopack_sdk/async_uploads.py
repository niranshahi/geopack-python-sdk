"""Async upload limits (``httpx``).

Mirrors :class:`geopack_sdk.uploads.UploadManager`; the payload parser is
shared so the two lanes cannot drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import UploadLimits
from .uploads import _parse_upload_limits

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncUploadManager:
    """Async twin of :class:`geopack_sdk.uploads.UploadManager`."""

    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def get_limits(self) -> UploadLimits:
        """Async twin of :meth:`UploadManager.get_limits`."""
        response_data = await self.client.get("/uploads/limits")
        return _parse_upload_limits(response_data)
