"""Async twins of the quota catalog reads (slice 015)."""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_quotas import AsyncQuotaManager
from tests.test_quota_catalog import DIMENSIONS, PLAN, PLAN_LIMITS
from tests.test_quotas import SUMMARY_PAYLOAD


class AsyncQuotaCatalogTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncQuotaManager(self.client)

    async def test_get_my_quota_summary(self):
        self.client.get.return_value = SUMMARY_PAYLOAD

        summary = await self.manager.get_my_quota_summary()

        self.client.get.assert_awaited_once_with("/quotas/me/summary")
        self.assertTrue(summary.enabled)

    async def test_catalog_reads(self):
        self.client.get.return_value = DIMENSIONS
        dimensions = await self.manager.get_dimensions()
        self.assertEqual(dimensions[0]["key"], "workflow.count.runs.daily")

        self.client.get.return_value = [PLAN]
        plans = await self.manager.get_plans()
        self.assertEqual(plans[0]["code"], "default")

        self.client.get.return_value = PLAN
        plan = await self.manager.get_plan(1)
        self.assertEqual(plan["tier"], 3)

        self.client.get.return_value = PLAN_LIMITS
        limits = await self.manager.get_plan_limits(1)
        self.assertEqual(limits[0]["limitValue"], 5)


if __name__ == "__main__":
    unittest.main()
