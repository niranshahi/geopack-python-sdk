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


def cancel_task(client: GeopackClient, task_id: str) -> Dict[str, Any]:
    """Request cancellation of a running task (best effort — 202, not a kill).

    No batch, no "cancel everything": a task is cancelled by id, after the
    caller confirmed it (slice 021 §2). The record is NOT deleted
    (``delete_task_record`` stays SDK-only, D7).
    """
    payload = client.tasks.cancel_task(task_id)
    answer: Dict[str, Any] = dict(payload) if isinstance(payload, dict) else {}
    answer["taskId"] = task_id
    answer["cancelRequested"] = True
    answer["hint"] = (
        "Cancellation was requested, not guaranteed: the worker may finish the step it "
        "is on. Poll geopack_sdk_get_task or geopack_sdk_wait_for_task — 'canceled' is "
        "terminal there and already-completed work stays."
    )
    return answer
