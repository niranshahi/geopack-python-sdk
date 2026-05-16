import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from geopack_sdk.async_client import AsyncGeopackClient
from geopack_sdk.exceptions import GeopackAPIError


class TestAsyncGeopackClient(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncGeopackClient(
            base_url="http://example.com/api",
            enable_http_retries=False,
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    @patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock)
    async def test_delete_returns_none_on_204(self, mock_request):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.status_code = 204
        mock_response.content = b""
        mock_request.return_value = mock_response

        result = await self.client.delete("/datasets/1")
        self.assertIsNone(result)

    @patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock)
    async def test_get_json_on_200(self, mock_request):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'
        mock_response.json.return_value = {"ok": True}
        mock_request.return_value = mock_response

        result = await self.client.get("/datasets")
        self.assertEqual(result, {"ok": True})

    @patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock)
    async def test_raises_geopack_api_error_on_400(self, mock_request):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.reason_phrase = "Bad Request"
        mock_response.text = '{"message":"invalid"}'
        mock_response.json.return_value = {"message": "invalid"}
        mock_request.return_value = mock_response

        with self.assertRaises(GeopackAPIError) as ctx:
            await self.client.get("/datasets")
        self.assertEqual(ctx.exception.status_code, 400)


class TestAsyncTaskWaitForTasks(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_tasks_gather(self):
        client = AsyncGeopackClient(
            base_url="http://example.com/api",
            enable_http_retries=False,
        )
        try:
            calls = []

            async def fake_wait(task_id, **kwargs):
                calls.append(task_id)
                from geopack_sdk.models import TaskResult

                return TaskResult(
                    taskId=task_id,
                    status="completed",
                    taskType="test",
                    userId=1,
                )

            client.tasks.wait_for_task = fake_wait  # type: ignore[method-assign]
            results = await client.tasks.wait_for_tasks(["a", "b"], quiet=True)
            self.assertEqual(len(results), 2)
            self.assertEqual(sorted(calls), ["a", "b"])
        finally:
            await client.aclose()


if __name__ == "__main__":
    unittest.main()
