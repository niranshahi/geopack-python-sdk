import time
import logging
from typing import Any, Dict, Optional
from .models import TaskResult

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, client):
        self.client = client

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
        Poll the task status until it is completed or failed with type-safe response.

        REST API: `GET /api/tasks/{taskId}` (polled)

        Args:
            task_id: ID of the task to wait for
            timeout: Maximum seconds to wait
            interval: Seconds between polls
            quiet: If True, suppress logging output

        Returns:
            TaskResult: Validated task result model when completed

        Raises:
            Exception: If task fails or is canceled
            TimeoutError: If task times out

        Expected terminal statuses:
        - completed
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

            if status == "completed":
                # Final fetch to ensure we have the output field
                return self.get_status(task_id)
            if status in ["failed", "canceled"]:
                if status == "failed" and not quiet:
                    logger.error(f"Task failed: {status_result.message}")
                raise Exception(f"Task {task_id} failed or was canceled: {status_result.message}")
            
            time.sleep(interval)
        
        raise TimeoutError(f"Task {task_id} timed out after {timeout} seconds")
