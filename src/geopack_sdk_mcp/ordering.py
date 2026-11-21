"""Client-side sort-argument validation shared by the MCP list lanes (slice 032 F6).

Every list endpoint takes a sort field plus a direction and silently falls back
to its default order when the field is not in its whitelist. That fallback is a
bad answer for a model -- it looks like the sort was applied -- so the edge
refuses an unknown key *before* the network call and names the legal set in the
error hint (the same contract ``list_datasets`` uses).
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

from .errors import ToolArgumentError


def validate_sort_args(
    order_by: Optional[str],
    order_direction: Optional[str],
    *,
    allowed: Iterable[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(field, direction)`` after validating both, or ``(None, None)``.

    ``field`` is returned unchanged (the whitelists are case-sensitive, exactly
    as the server maps them); ``direction`` is lowercased to ``asc``/``desc``.
    An unknown field or direction raises :class:`ToolArgumentError` with the
    legal values in ``hint``.
    """
    legal = tuple(allowed)

    field: Optional[str] = None
    if order_by:
        candidate = str(order_by).strip()
        if candidate not in legal:
            raise ToolArgumentError(
                f"Unknown order_by {candidate!r}",
                key="order_by",
                hint=f"order_by must be one of: {', '.join(legal)}.",
            )
        field = candidate

    direction: Optional[str] = None
    if order_direction:
        normalized = str(order_direction).strip().lower()
        if normalized not in ("asc", "desc"):
            raise ToolArgumentError(
                'order_direction must be "asc" or "desc"',
                key="order_direction",
                hint='Pass direction "asc" or "desc" (omitted = the portal default).',
            )
        direction = normalized

    return field, direction