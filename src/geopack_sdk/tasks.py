import time
import logging
from typing import Any, Dict, List, Literal, NamedTuple, Optional

from .models import ActiveTasksSummary, TaskListResponse, TaskResult
from .exceptions import GeopackTaskError, GeopackTimeoutError

logger = logging.getLogger(__name__)


class TaskMessageInfo(NamedTuple):
    """
    Mirrors ``getMessageInfo`` in ``frontend-ui/src/features/tasks/views/TasksListView.vue``:
    message count, presence of error / warn levels (``warn``, not ``warning``).
    """

    count: int
    has_errors: bool
    has_warnings: bool


def task_message_info(task: TaskResult) -> TaskMessageInfo:
    """
    Same logic as the Task History table **Messages** column (badge / button color).

    - ``has_errors``: any ``level == "error"`` (red in UI)
    - ``has_warnings``: any ``level == "warn"`` (orange if no errors; blue if neither)
    """
    messages = task.messages or []
    count = len(messages)
    has_errors = any(
        isinstance(m, dict) and str(m.get("level", "")).lower() == "error"
        for m in messages
    )
    has_warnings = any(
        isinstance(m, dict) and str(m.get("level", "")).lower() == "warn"
        for m in messages
    )
    return TaskMessageInfo(count, has_errors, has_warnings)


def task_message_badge_severity(task: TaskResult) -> Literal["error", "warn", "info"]:
    """
    Matches Vuetify badge/button colors on the task list: **error** >
    **warn** > **info** (see ``TasksListView.vue`` template).
    """
    info = task_message_info(task)
    if info.has_errors:
        return "error"
    if info.has_warnings:
        return "warn"
    return "info"


def task_log_entries_needing_review(task: TaskResult) -> List[Dict[str, Any]]:
    """
    Log lines with ``level`` ``error`` or ``warn`` (and ``warning`` alias).

    Excludes ``info`` and ``debug`` so this aligns with list **severity** highlights;
    read ``task.messages`` directly for every line including debug when permitted.
    """
    out: List[Dict[str, Any]] = []
    for m in task.messages or []:
        if not isinstance(m, dict):
            continue
        level = str(m.get("level", "info")).lower()
        if level in ("error", "warn", "warning"):
            out.append(m)
    return out


def task_may_have_hidden_issues(task: TaskResult) -> bool:
    """
    True when ``status`` is ``completed`` or ``partial_success`` but the message
    log would show a **non-info** badge in the portal (error or warn lines), i.e.
    :func:`task_message_badge_severity` is not ``"info"``.
    """
    if task.status not in ("completed", "partial_success"):
        return False
    return task_message_badge_severity(task) != "info"


class TaskManager:
    def __init__(self, client):
        self.client = client

    def summary(self) -> ActiveTasksSummary:
        """
        Active task counts for the current user (pending + processing).

        REST API: `GET /api/tasks/summary`
        """
        response_data = self.client.get("/tasks/summary")
        return ActiveTasksSummary(**response_data)

    def iter_tasks(
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
        """Iterate over all tasks by auto-fetching successive pages."""
        current_page = 1
        while True:
            resp = self.list(
                page=current_page,
                page_size=page_size,
                status=status,
                task_type=task_type,
                order_by=order_by,
                order_direction=order_direction,
            )
            if not resp.tasks:
                break
            yield from resp.tasks
            if len(resp.tasks) < page_size:
                break
            current_page += 1

    def list(

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
        """
        Paginated list of tasks for the current user.

        REST API: `GET /api/tasks`

        Requires permission ``task:list`` (normal users typically have this).

        Note:
            List items may omit large fields (e.g. some payloads). For full
            ``messages`` / results, call :meth:`get_status` for a specific ``taskId``.
        """
        params: Dict[str, Any] = {
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

        response_data = self.client.get("/tasks", params=params)
        return TaskListResponse(**response_data)

    def get_status(self, task_id: str) -> TaskResult:
        """
        Fetch the current status of a background task with type-safe response.

        REST API: `GET /api/tasks/{taskId}`

        Args:
            task_id: ID of the task to fetch

        Returns:
            TaskResult: Validated task result model
        """
        response_data = self.client.get(f"/tasks/{task_id}")
        return TaskResult(**response_data)

    def create(self, task_payload: Dict[str, Any]) -> TaskResult:
        """
        Create a new background task with type-safe response.

        REST API: `POST /api/tasks`

        Args:
            task_payload: Task creation payload

        Returns:
            TaskResult: Validated task result model
        """
        response_data = self.client.post("/tasks", json=task_payload)
        return TaskResult(**response_data)

    def wait(self, task_id: str, timeout: int = 300, interval: int = 2, quiet: bool = False) -> TaskResult:
        """
        Alias for wait_for_task.
        """
        return self.wait_for_task(task_id, timeout=timeout, interval=interval, quiet=quiet)

    def wait_for_task(self, task_id: str, timeout: int = 300, interval: int = 2, quiet: bool = False) -> TaskResult:
        """
        Poll the task status until it reaches a terminal state with type-safe response.

        REST API: `GET /api/tasks/{taskId}` (polled)

        Args:
            task_id: ID of the task to wait for
            timeout: Maximum seconds to wait
            interval: Seconds between polls
            quiet: If True, suppress logging output

        Returns:
            TaskResult: Validated task result model when completed or partial_success

        Raises:
            GeopackTaskError: If task fails or is canceled
            GeopackTimeoutError: If task times out

        Expected terminal statuses:
        - completed
        - partial_success
        - failed
        - canceled
        """
        if not quiet:
            logger.info(f"Waiting for task {task_id} to complete...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            status_result = self.get_status(task_id)
            status = status_result.status
            
            if not quiet:
                logger.info(f"Task {task_id}: {status}")

            if status in ("completed", "partial_success"):
                # Final fetch to ensure we have the output field
                return self.get_status(task_id)
            if status in ["failed", "canceled"]:
                if status == "failed" and not quiet:
                    logger.error(f"Task failed: {status_result.message}")
                raise GeopackTaskError(
                    task_id,
                    status,
                    status_result.message,
                )

            time.sleep(interval)

        raise GeopackTimeoutError(
            f"Task {task_id} timed out after {timeout} seconds",
            timeout=float(timeout),
        )
