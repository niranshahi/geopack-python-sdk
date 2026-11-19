from typing import Any, Dict, List, Optional

from .models import QuotaSummary, QuotaSummaryLimit


class QuotaManager:
    """Quota usage for the signed-in user (fail-fast before heavy operations).

    REST API:
        GET  /api/quotas/me/summary
        GET  /api/quotas/dimensions
        GET  /api/quotas/plans
        GET  /api/quotas/plans/:id
        GET  /api/quotas/plans/:planId/limits

    A refusal TODAY arrives as an uncoded ``400`` whose message starts with
    ``Quota exceeded:`` — so pre-flight with :meth:`get_my_quota_summary` /
    :meth:`warn_limits` instead of parsing that text. :class:`QuotaExceeded`
    fires when the server sends a coded ``QUOTA_EXCEEDED`` body (with
    ``dimension`` / ``limit`` / ``used``), which is the intended contract.
    """

    def __init__(self, client):
        self.client = client

    def my_summary(self) -> QuotaSummary:
        """Fetch quota plan and limit usage for the current user."""
        response_data = self.client.get("/quotas/me/summary")
        return QuotaSummary(**response_data)

    def get_my_quota_summary(self) -> QuotaSummary:
        """Caller-scoped quota summary (the canonical name; same endpoint).

        Kept beside :meth:`my_summary` (the older name) instead of replacing
        it — both read ``GET /quotas/me/summary``. When quotas are disabled the
        answer is ``enabled=False`` with an empty ``limits`` list; when the
        user has no plan it is ``enabled=True``, ``reason='no_plan'``.
        """
        return self.my_summary()

    def get_dimensions(self) -> List[Dict[str, Any]]:
        """Every usage dimension (``category``/``key``/units).

        A catalog read: useful to explain a limit in a user message.

        REST API: `GET /api/quotas/dimensions`
        """
        response_data = self.client.get("/quotas/dimensions")
        return response_data if isinstance(response_data, list) else []

    def get_plans(self) -> List[Dict[str, Any]]:
        """Every usage plan (tier, code, display name, status).

        REST API: `GET /api/quotas/plans`
        """
        response_data = self.client.get("/quotas/plans")
        return response_data if isinstance(response_data, list) else []

    def get_plan(self, plan_id: int) -> Dict[str, Any]:
        """One usage plan by id (404 when unknown).

        REST API: `GET /api/quotas/plans/{id}`
        """
        response_data = self.client.get(f"/quotas/plans/{plan_id}")
        return response_data if isinstance(response_data, dict) else {}

    def get_plan_limits(self, plan_id: int) -> List[Dict[str, Any]]:
        """The limit rows of one plan (one per dimension/window).

        REST API: `GET /api/quotas/plans/{planId}/limits`
        """
        response_data = self.client.get(f"/quotas/plans/{plan_id}/limits")
        return response_data if isinstance(response_data, list) else []

    def get_limit(
        self,
        dimension_key: str,
        summary: Optional[QuotaSummary] = None,
    ) -> Optional[QuotaSummaryLimit]:
        """Return the limit row for a dimension key, if present."""
        summary = summary or self.my_summary()
        for row in summary.limits:
            if row.dimensionKey == dimension_key:
                return row
        return None

    def remaining_for(
        self,
        dimension_key: str,
        summary: Optional[QuotaSummary] = None,
    ) -> Optional[float]:
        """Remaining quota for a dimension, or None if unlimited / not configured."""
        row = self.get_limit(dimension_key, summary=summary)
        if row is None:
            return None
        return row.remaining

    def is_over_limit(
        self,
        dimension_key: str,
        summary: Optional[QuotaSummary] = None,
    ) -> bool:
        """True when quotas are enabled and remaining for the dimension is <= 0."""
        summary = summary or self.my_summary()
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
        summary: Optional[QuotaSummary] = None,
        min_percent: float = 80.0,
    ) -> List[QuotaSummaryLimit]:
        """Limits at or above warn threshold (default 80% used)."""
        summary = summary or self.my_summary()
        out: List[QuotaSummaryLimit] = []
        for row in summary.limits:
            threshold = row.warnThresholdPercent
            if threshold is None:
                threshold = min_percent
            used = row.percentageUsed
            if used is not None and used >= threshold:
                out.append(row)
        return out
