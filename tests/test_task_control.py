"""Task control lanes (slice 015): types, stats, cancel vs delete-record.

The two DELETE verbs are different operations on different paths:

* ``DELETE /tasks/{id}``         — request cancellation (202, best effort)
* ``DELETE /tasks/{id}/delete``  — remove a TERMINAL record (204)

The SDK keeps them as two names, never a boolean flag.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import GeopackTaskError
from geopack_sdk.models import TaskResult
from geopack_sdk.tasks import TaskManager


TASK_TYPES = [
    {
        "taskType": "workflow:run",
        "description": "Run a workflow",
        "requiredPermission": "workflow:run",
        "inputSchemaInfo": {"workflowId": "number"},
    }
]

STATS_SUMMARY = {
    "created": 42,
    "completed": 30,
    "failed": 4,
    "canceled": 2,
    "partial_success": 6,
    "total": 42,
}

TIME_SERIES = [
    {
        "date": "2026-11-18",
        "created": 5,
        "completed": 3,
        "failed": 1,
        "canceled": 0,
        "partial_success": 1,
        "avgDurationSec": 12.5,
    }
]


class TaskControlTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = TaskManager(self.client)

    def test_get_types_returns_the_catalog(self):
        self.client.get.return_value = TASK_TYPES

        types = self.manager.get_types()

        self.client.get.assert_called_once_with("/tasks/types")
        self.assertEqual(types[0]["taskType"], "workflow:run")
        self.assertEqual(types[0]["requiredPermission"], "workflow:run")

    def test_get_stats_summary_is_not_the_active_panel(self):
        self.client.get.return_value = STATS_SUMMARY

        stats = self.manager.get_stats_summary()

        self.client.get.assert_called_once_with("/tasks/stats/summary", params=None)
        self.assertEqual(stats["created"], stats["total"])
        self.assertEqual(stats["completed"], 30)

    def test_get_stats_summary_passes_task_type(self):
        self.client.get.return_value = STATS_SUMMARY

        self.manager.get_stats_summary(task_type="workflow:run")

        self.assertEqual(
            self.client.get.call_args.kwargs["params"], {"taskType": "workflow:run"}
        )

    def test_get_stats_time_series_returns_buckets(self):
        self.client.get.return_value = TIME_SERIES

        series = self.manager.get_stats_time_series(days=7, status="failed")

        self.assertIsInstance(series, list)
        self.assertEqual(series[0]["date"], "2026-11-18")
        self.assertEqual(
            self.client.get.call_args.kwargs["params"],
            {"days": 7, "status": "failed"},
        )

    def test_get_stats_time_series_validates_locally(self):
        cases = (
            {"days": 0},
            {"days": 366},
            {"days": True},  # bool is an int subclass; still rejected
            {"days": "7"},
            {"status": "unknown"},
        )
        for kwargs in cases:
            with self.assertRaises(ValueError):
                self.manager.get_stats_time_series(**kwargs)
        self.client.get.assert_not_called()

    def test_cancel_task_returns_the_202_payload(self):
        self.client.delete.return_value = {"message": "Task cancellation requested"}

        payload = self.manager.cancel_task("task-1")

        self.client.delete.assert_called_once_with("/tasks/task-1")
        self.assertEqual(payload["message"], "Task cancellation requested")

    def test_delete_task_record_uses_the_delete_path_and_returns_none(self):
        result = self.manager.delete_task_record("task-1")

        self.client.delete.assert_called_once_with("/tasks/task-1/delete")
        self.assertIsNone(result)

    def test_cancel_and_delete_never_share_a_path(self):
        self.client.delete.return_value = {}

        self.manager.cancel_task("t9")
        self.manager.delete_task_record("t9")

        calls = [call.args[0] for call in self.client.delete.call_args_list]
        self.assertEqual(calls, ["/tasks/t9", "/tasks/t9/delete"])

    def test_wait_for_task_treats_canceled_as_terminal(self):
        self.manager.get_status = MagicMock(
            return_value=TaskResult(
                taskId="task-1",
                status="canceled",
                taskType="workflow:run",
                userId=1,
            )
        )

        with self.assertRaises(GeopackTaskError) as ctx:
            self.manager.wait_for_task("task-1", timeout=1, interval=0, quiet=True)

        self.assertEqual(ctx.exception.status, "canceled")
        self.assertEqual(self.manager.get_status.call_count, 1)


if __name__ == "__main__":
    unittest.main()
