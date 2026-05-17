"""Convert SDK Pydantic models to JSON-serializable structures for MCP tool results."""

from __future__ import annotations

from typing import Any, List, Union

from pydantic import BaseModel

from geopack_sdk.dataset_payload import normalize_dataset_dict


def _maybe_normalize_dataset_dict(data: dict) -> dict:
    if "id" in data and "dataType" in data:
        return normalize_dataset_dict(data)
    return data


def to_jsonable(value: Any) -> Any:
    """Recursively dump models and lists for MCP ``json_response`` tools."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        normalized = _maybe_normalize_dataset_dict(value)
        return {key: to_jsonable(item) for key, item in normalized.items()}
    return value
