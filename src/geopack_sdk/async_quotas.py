"""Async quota manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .models import QuotaSummary, QuotaSummaryLimit

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncQuotaManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def my_summary(self) -> QuotaSummary:
        response_data = await self.client.get("/quotas/me/summary")
        return QuotaSummary(**response_data)

    async def get_my_quota_summary(self) -> QuotaSummary:
        """Async twin of :meth:`QuotaManager.get_my_quota_summary`."""
        return await self.my_summary()

    async def get_dimensions(self) -> List[Dict[str, Any]]:
        """Async twin of :meth:`QuotaManager.get_dimensions`."""
        response_data = await self.client.get("/quotas/dimensions")
        return response_data if isinstance(response_data, list) else []

    async def get_plans(self) -> List[Dict[str, Any]]:
        """Async twin of :meth:`QuotaManager.get_plans`."""
        response_data = await self.client.get("/quotas/plans")
        return response_data if isinstance(response_data, list) else []

    async def get_plan(self, plan_id: int) -> Dict[str, Any]:
        """Async twin of :meth:`QuotaManager.get_plan`."""
        response_data = await self.client.get(f"/quotas/plans/{plan_id}")
        return response_data if isinstance(response_data, dict) else {}

    async def get_plan_limits(self, plan_id: int) -> List[Dict[str, Any]]:
        """Async twin of :meth:`QuotaManager.get_plan_limits`."""
        response_data = await self.client.get(f"/quotas/plans/{plan_id}/limits")
        return response_data if isinstance(response_data, list) else []

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
