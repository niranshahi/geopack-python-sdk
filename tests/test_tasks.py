import unittest
from unittest.mock import MagicMock

from geopack_sdk.models import TaskResult
from geopack_sdk.tasks import TaskManager


class TestTaskManager(unittest.TestCase):
    def test_wait_for_task_returns_partial_success(self):
        client = MagicMock()
        manager = TaskManager(client)

        task = TaskResult(
            taskId="task-1",
            status="partial_success",
            taskType="dataset:export",
            userId=1,
        )
        manager.get_status = MagicMock(return_value=task)

        result = manager.wait_for_task("task-1", timeout=1, interval=0, quiet=True)

        self.assertEqual(result.status, "partial_success")
        self.assertEqual(manager.get_status.call_count, 2)


if __name__ == "__main__":
    unittest.main()
