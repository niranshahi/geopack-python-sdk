"""Task tool handlers."""

from __future__ import annotations

from typing import Any, Dict

from geopack_sdk import GeopackClient

from ..sanitize.task_results import sanitize_task_payload
from ..serialize import to_jsonable


def get_task(client: GeopackClient, task_id: str) -> Dict[str, Any]:
    result = client.tasks.get_status(task_id)
    return sanitize_task_payload(to_jsonable(result))


def wait_for_task(
    client: GeopackClient,
    task_id: str,
    *,
    timeout: int = 300,
    interval: int = 2,
) -> Dict[str, Any]:
    """Poll until the task completes, fails, or times out."""
    result = client.tasks.wait_for_task(
        task_id,
        timeout=timeout,
        interval=interval,
        quiet=True,
    )
    return sanitize_task_payload(to_jsonable(result))
