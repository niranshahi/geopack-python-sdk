"""Normalize dataset API payloads: strip thumbnail BLOBs, expose thumbnail metadata."""

from __future__ import annotations

from typing import Any, Dict, Optional


def dataset_thumbnail_api_path(dataset_id: int) -> str:
    """Relative REST path for GET thumbnail (no host, no auth token)."""
    return f"/datasets/{dataset_id}/thumbnail"


def normalize_dataset_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove ``thumbnail`` from dict payloads; set ``hasThumbnail`` / ``thumbnailApiPath``."""
    if not isinstance(data, dict):
        return data

    out = dict(data)
    had_blob = out.pop("thumbnail", None) is not None

    if had_blob and "hasThumbnail" not in out:
        out["hasThumbnail"] = True

    if out.get("hasThumbnail") and "id" in out:
        out.setdefault("thumbnailApiPath", dataset_thumbnail_api_path(int(out["id"])))

    return out
