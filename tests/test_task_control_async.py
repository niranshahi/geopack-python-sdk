"""Async twins of the task control lanes (slice 015)."""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_tasks import AsyncTaskManager
from geopack_sdk.exceptions import GeopackTaskError
from geopack_sdk.models import TaskResult
from tests.test_task_control import STATS_SUMMARY, TASK_TYPES, TIME_SERIES


class AsyncTaskControlTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncTaskManager(self.client)

    async def test_get_types(self):
        self.client.get.return_value = TASK_TYPES

        types = await self.manager.get_types()

        self.client.get.assert_awaited_once_with("/tasks/types")
        self.assertEqual(types[0]["taskType"], "workflow:run")

    async def test_stats_summary_and_series(self):
        self.client.get.return_value = STATS_SUMMARY

        stats = await self.manager.get_stats_summary(task_type="workflow:run")

        self.assertEqual(stats["total"], 42)
        self.assertEqual(
            self.client.get.call_args.kwargs["params"], {"taskType": "workflow:run"}
        )

        self.client.get.return_value = TIME_SERIES
        series = await self.manager.get_stats_time_series(days=30)

        self.assertEqual(series[0]["date"], "2026-11-18")
        self.assertEqual(self.client.get.call_args.kwargs["params"], {"days": 30})

    async def test_stats_time_series_validates_locally(self):
        for kwargs in ({"days": 0}, {"days": 366}, {"status": "nope"}):
            with self.assertRaises(ValueError):
                await self.manager.get_stats_time_series(**kwargs)
        self.client.get.assert_not_awaited()

    async def test_cancel_and_delete_use_distinct_paths(self):
        self.client.delete.return_value = {"message": "Task cancellation requested"}

        payload = await self.manager.cancel_task("t1")
        result = await self.manager.delete_task_record("t1")

        self.assertEqual(payload["message"], "Task cancellation requested")
        self.assertIsNone(result)
        calls = [call.args[0] for call in self.client.delete.call_args_list]
        self.assertEqual(calls, ["/tasks/t1", "/tasks/t1/delete"])

    async def test_wait_for_task_treats_canceled_as_terminal(self):
        self.manager.get_status = AsyncMock(
            return_value=TaskResult(
                taskId="t1", status="canceled", taskType="workflow:run", userId=1
            )
        )

        with self.assertRaises(GeopackTaskError) as ctx:
            await self.manager.wait_for_task("t1", timeout=1, interval=0, quiet=True)

        self.assertEqual(ctx.exception.status, "canceled")
        self.assertEqual(self.manager.get_status.await_count, 1)


if __name__ == "__main__":
    unittest.main()
