from typing import List, Optional

from .models import QuotaSummary, QuotaSummaryLimit


class QuotaManager:
    """Quota usage for the signed-in user (fail-fast before heavy operations).

    REST API:
        GET /api/quotas/me/summary
    """

    def __init__(self, client):
        self.client = client

    def my_summary(self) -> QuotaSummary:
        """Fetch quota plan and limit usage for the current user."""
        response_data = self.client.get("/quotas/me/summary")
        return QuotaSummary(**response_data)

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
