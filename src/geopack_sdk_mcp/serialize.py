"""Convert SDK Pydantic models to JSON-serializable structures for MCP tool results."""

from __future__ import annotations

from typing import Any, List, Union

from pydantic import BaseModel


def to_jsonable(value: Any) -> Any:
    """Recursively dump models and lists for MCP ``json_response`` tools."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value
