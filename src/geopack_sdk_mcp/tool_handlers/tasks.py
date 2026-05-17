"""Task tool handlers."""

from __future__ import annotations

from typing import Any, Dict

from geopack_sdk import GeopackClient

from ..serialize import to_jsonable


def get_task(client: GeopackClient, task_id: str) -> Dict[str, Any]:
    result = client.tasks.get_status(task_id)
    return to_jsonable(result)
