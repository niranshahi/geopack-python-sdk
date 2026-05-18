"""Normalize dataset API payloads: strip thumbnail BLOBs, expose thumbnail metadata."""

from __future__ import annotations

from typing import Any, Dict, Optional


def dataset_thumbnail_api_path(dataset_id: int) -> str:
    """Relative REST path for GET thumbnail (no host, no auth token)."""
    return f"/datasets/{dataset_id}/thumbnail"


def dataset_thumbnail_resource_uri(dataset_id: int) -> str:
    """MCP resource URI for thumbnail binary (resources/read, not tool JSON)."""
    return f"dataset://{dataset_id}/thumbnail"


def generated_file_resource_uri(generated_file_id: int) -> str:
    """MCP resource URI for generated file binary download."""
    return f"generated-file://{generated_file_id}/download"


def normalize_dataset_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove ``thumbnail`` from dict payloads; set ``hasThumbnail`` / ``thumbnailApiPath``."""
    if not isinstance(data, dict):
        return data

    out = dict(data)
    had_blob = out.pop("thumbnail", None) is not None

    if had_blob and "hasThumbnail" not in out:
        out["hasThumbnail"] = True

    if out.get("hasThumbnail") and "id" in out:
        ds_id = int(out["id"])
        out.setdefault("thumbnailApiPath", dataset_thumbnail_api_path(ds_id))
        out.setdefault("thumbnailResourceUri", dataset_thumbnail_resource_uri(ds_id))

    return out
