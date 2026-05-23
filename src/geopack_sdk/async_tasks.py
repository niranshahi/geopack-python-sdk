"""Async task manager — parallel polling and status helpers."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

from .exceptions import GeopackTaskError, GeopackTimeoutError
from .models import ActiveTasksSummary, TaskListResponse, TaskResult
from .tasks import (
    task_log_entries_needing_review,
    task_may_have_hidden_issues,
    task_message_badge_severity,
    task_message_info,
)

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient

logger = logging.getLogger(__name__)

__all__ = [
    "AsyncTaskManager",
    "task_log_entries_needing_review",
    "task_may_have_hidden_issues",
    "task_message_badge_severity",
    "task_message_info",
]


class AsyncTaskManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def summary(self) -> ActiveTasksSummary:
        response_data = await self.client.get("/tasks/summary")
        return ActiveTasksSummary(**response_data)

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        status: Optional[
            Literal[
                "pending",
                "processing",
                "completed",
                "failed",
                "partial_success",
                "canceled",
            ]
        ] = None,
        task_type: Optional[str] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[Literal["ASC", "DESC"]] = None,
    ) -> TaskListResponse:
        params: Dict[str, object] = {
            "page": page,
            "pageSize": page_size,
        }
        if status:
            params["status"] = status
        if task_type:
            params["taskType"] = task_type
        if order_by:
            params["orderBy"] = order_by
        if order_direction:
            params["orderDirection"] = order_direction

        response_data = await self.client.get("/tasks", params=params)
        return TaskListResponse(**response_data)

    async def iter_tasks(
        self,
        page_size: int = 50,
        status: Optional[
            Literal[
                "pending",
                "processing",
                "completed",
                "failed",
                "partial_success",
                "canceled",
            ]
        ] = None,
        task_type: Optional[str] = None,
        order_by: Optional[str] = None,
        order_direction: Optional[Literal["ASC", "DESC"]] = None,
    ):
        """Iterate over all tasks by auto-fetching successive pages asynchronously."""
        current_page = 1
        while True:
            resp = await self.list(
                page=current_page,
                page_size=page_size,
                status=status,
                task_type=task_type,
                order_by=order_by,
                order_direction=order_direction,
            )
            if not resp.tasks:
                break
            for task in resp.tasks:
                yield task
            if len(resp.tasks) < page_size:
                break
            current_page += 1

    async def get_status(self, task_id: str) -> TaskResult:
        response_data = await self.client.get(f"/tasks/{task_id}")
        return TaskResult(**response_data)

    async def wait_for_task(
        self,
        task_id: str,
        timeout: int = 300,
        interval: int = 2,
        quiet: bool = False,
    ) -> TaskResult:
        """Poll until the task reaches a terminal status (async ``asyncio.sleep``)."""
        if not quiet:
            logger.info("Waiting for task %s to complete...", task_id)

        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            status_result = await self.get_status(task_id)
            status = status_result.status

            if not quiet:
                logger.info("Task %s: %s", task_id, status)

            if status in ("completed", "partial_success"):
                return await self.get_status(task_id)
            if status in ("failed", "canceled"):
                if status == "failed" and not quiet:
                    logger.error("Task failed: %s", status_result.message)
                raise GeopackTaskError(
                    task_id,
                    status,
                    status_result.message,
                )

            await asyncio.sleep(interval)

        raise GeopackTimeoutError(
            f"Task {task_id} timed out after {timeout} seconds",
            timeout=float(timeout),
        )

    async def wait(
        self,
        task_id: str,
        timeout: int = 300,
        interval: int = 2,
        quiet: bool = False,
    ) -> TaskResult:
        return await self.wait_for_task(
            task_id, timeout=timeout, interval=interval, quiet=quiet
        )

    async def wait_for_tasks(
        self,
        task_ids: List[str],
        *,
        timeout: int = 300,
        interval: int = 2,
        quiet: bool = False,
    ) -> List[TaskResult]:
        """
        Poll multiple tasks concurrently (``asyncio.gather``).

        Each task receives the full ``timeout`` budget independently.
        """
        return list(
            await asyncio.gather(
                *[
                    self.wait_for_task(
                        task_id,
                        timeout=timeout,
                        interval=interval,
                        quiet=quiet,
                    )
                    for task_id in task_ids
                ]
            )
        )
