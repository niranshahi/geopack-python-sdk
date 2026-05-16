"""Async quota manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from .models import QuotaSummary, QuotaSummaryLimit

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncQuotaManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def my_summary(self) -> QuotaSummary:
        response_data = await self.client.get("/quotas/me/summary")
        return QuotaSummary(**response_data)

    def get_limit(
        self,
        dimension_key: str,
        summary: QuotaSummary,
    ) -> Optional[QuotaSummaryLimit]:
        for row in summary.limits:
            if row.dimensionKey == dimension_key:
                return row
        return None

    def remaining_for(
        self,
        dimension_key: str,
        summary: QuotaSummary,
    ) -> Optional[float]:
        row = self.get_limit(dimension_key, summary=summary)
        if row is None:
            return None
        return row.remaining

    async def is_over_limit(
        self,
        dimension_key: str,
        summary: Optional[QuotaSummary] = None,
    ) -> bool:
        summary = summary or await self.my_summary()
        if not summary.enabled:
            return False
        row = self.get_limit(dimension_key, summary=summary)
        if row is None:
            return False
        if row.remaining is None:
            return False
        return row.remaining <= 0

    def warn_limits(
        self,
        summary: QuotaSummary,
        min_percent: float = 80.0,
    ) -> List[QuotaSummaryLimit]:
        out: List[QuotaSummaryLimit] = []
        for row in summary.limits:
            threshold = row.warnThresholdPercent
            if threshold is None:
                threshold = min_percent
            used = row.percentageUsed
            if used is not None and used >= threshold:
                out.append(row)
        return out
