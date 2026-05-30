"""Normalize bbox arguments from LLM / MCP tool calls."""

from __future__ import annotations

import json
from typing import List, Optional, Sequence, Union

BboxInput = Optional[Union[str, Sequence[Union[int, float, str]]]]


def normalize_bbox(bbox: BboxInput) -> Optional[List[float]]:
    """Normalize bbox to ``[west, south, east, north]``.

    Accepts:
    - ``None``
    - list/tuple of numbers, e.g. ``[51.0, 35.5, 51.6, 35.8]``
    - JSON array string, e.g. ``"[51.0, 35.5, 51.6, 35.8]"``
    - comma-delimited string, e.g. ``"51.0, 35.5, 51.6, 35.8"``

    Raises:
        ValueError: If bbox is present but cannot be parsed into four numbers.
    """
    if bbox is None:
        return None

    if isinstance(bbox, str):
        text = bbox.strip()
        if not text:
            return None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"bbox JSON array string is invalid: {exc}") from exc
            return _coerce_bbox_sequence(parsed, source="bbox JSON array string")
        if "," in text:
            parts = [part.strip() for part in text.split(",")]
            return _coerce_bbox_sequence(parts, source="bbox comma-delimited string")
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            raise ValueError(
                "bbox string must be a JSON array or four comma-separated values"
            ) from None
        return _coerce_bbox_sequence(parsed, source="bbox string")

    if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)):
        return _coerce_bbox_sequence(bbox, source="bbox array")

    raise ValueError(f"bbox must be a list or string, got {type(bbox).__name__}")


def _coerce_bbox_sequence(values: Sequence[Union[int, float, str]], *, source: str) -> List[float]:
    if len(values) != 4:
        raise ValueError(f"{source} must have 4 elements, got {len(values)}")
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} must contain numbers: {exc}") from exc
