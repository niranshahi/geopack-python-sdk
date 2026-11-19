"""Quota tool handlers (pre-flight before a heavy upload or export)."""

from __future__ import annotations

from typing import Any, Dict, List

from geopack_sdk import GeopackClient

from ..serialize import to_jsonable

# Above this share of a limit the answer carries a hint: a refusal this close
# to the ceiling is worth surfacing before the request is attempted.
WARN_PERCENT = 90.0


def get_quota_summary(client: GeopackClient) -> Dict[str, Any]:
    """Return ``GET /quotas/me/summary`` verbatim plus a hint above 90% used.

    No parameters and no math beyond reading the server's own percentages —
    the portal computes usage, the edge only reports it.
    """
    summary = client.quotas.get_my_quota_summary()
    payload = to_jsonable(summary)

    hints: List[str] = []
    if not summary.enabled:
        hints.append("Quotas are disabled on this portal, so no limit will block the request.")
    elif summary.reason:
        hints.append(f"Quota plan note: {summary.reason}.")

    for row in summary.limits:
        used = row.percentageUsed
        if used is not None and used >= WARN_PERCENT:
            hints.append(
                f"{row.dimensionKey} is {used:.0f}% used "
                f"({row.currentValue:g} of {row.limitValue:g}); a large request may be refused."
            )

    if hints:
        payload["hint"] = " ".join(hints[:3])
    return payload
