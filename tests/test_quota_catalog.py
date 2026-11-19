"""Quota catalog reads and the ``QUOTA_EXCEEDED`` carve-out (slice 015).

Reality on the wire today: a refusal is an *uncoded* ``400`` whose message
starts with ``Quota exceeded:``, and the global error handler drops ``code`` /
``details`` — so no typed exception can fire from a real refusal yet. The
carve-out below is what makes the intended contract work the day the server
emits a coded body (400 or 403) instead of plain text.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import GeopackAPIError, GeopackAuthError, QuotaExceeded
from geopack_sdk.quotas import QuotaManager
from tests.test_quotas import SUMMARY_PAYLOAD


DIMENSIONS = [
    {
        "category": "workflow",
        "key": "workflow.count.runs.daily",
        "unit": "runs",
        "window": "daily",
    }
]

PLAN = {
    "id": 1,
    "code": "default",
    "displayName": "Default",
    "tier": 3,
    "status": "ACTIVE",
}

PLAN_LIMITS = [
    {
        "limitId": 10,
        "dimensionKey": "workflow.count.runs.daily",
        "limitType": "hard",
        "limitValue": 5,
        "warnThresholdPercent": 80,
        "window": "daily",
        "windowDays": 1,
    }
]

QUOTA_BODY = {
    "code": "QUOTA_EXCEEDED",
    "message": "Quota exceeded: workflow.count.runs.daily (5 of 5)",
    "dimension": "workflow.count.runs.daily",
    "limit": 5,
    "used": 5,
}


class QuotaCatalogTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = QuotaManager(self.client)

    def test_get_my_quota_summary_is_the_canonical_name(self):
        self.client.get.return_value = SUMMARY_PAYLOAD

        summary = self.manager.get_my_quota_summary()

        self.client.get.assert_called_once_with("/quotas/me/summary")
        self.assertEqual(summary.plan.code, "default")

    def test_get_dimensions(self):
        self.client.get.return_value = DIMENSIONS

        dimensions = self.manager.get_dimensions()

        self.client.get.assert_called_once_with("/quotas/dimensions")
        self.assertEqual(dimensions[0]["key"], "workflow.count.runs.daily")

    def test_get_plans(self):
        self.client.get.return_value = [PLAN]

        plans = self.manager.get_plans()

        self.client.get.assert_called_once_with("/quotas/plans")
        self.assertEqual(plans[0]["tier"], 3)

    def test_get_plan(self):
        self.client.get.return_value = PLAN

        plan = self.manager.get_plan(1)

        self.client.get.assert_called_once_with("/quotas/plans/1")
        self.assertEqual(plan["code"], "default")

    def test_get_plan_limits(self):
        self.client.get.return_value = PLAN_LIMITS

        limits = self.manager.get_plan_limits(1)

        self.client.get.assert_called_once_with("/quotas/plans/1/limits")
        self.assertEqual(limits[0]["limitValue"], 5)

    def test_uncoded_400_refusal_stays_a_plain_api_error(self):
        """What a refusal looks like TODAY: 400 + message text, no code."""
        error = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text='{"message":"Quota exceeded: workflow.count.runs.daily (5 of 5)"}',
            json_loader=lambda: {
                "message": "Quota exceeded: workflow.count.runs.daily (5 of 5)"
            },
        )

        self.assertNotIsInstance(error, QuotaExceeded)
        self.assertIs(type(error), GeopackAPIError)
        self.assertIsNone(error.code)


class QuotaExceededCarveOutTest(unittest.TestCase):
    def _error(self, status):
        return GeopackAPIError.from_http_status(
            status, reason="Error", text="", json_loader=lambda: QUOTA_BODY
        )

    def test_coded_403_is_a_quota_error_not_an_auth_error(self):
        error = self._error(403)

        self.assertIsInstance(error, QuotaExceeded)
        self.assertNotIsInstance(error, GeopackAuthError)
        self.assertEqual(error.dimension, "workflow.count.runs.daily")
        self.assertEqual(error.limit, 5)
        self.assertEqual(error.used, 5)

    def test_coded_400_is_also_a_quota_error(self):
        error = self._error(400)

        self.assertIsInstance(error, QuotaExceeded)
        self.assertEqual(error.status_code, 400)

    def test_403_without_the_quota_code_stays_an_auth_error(self):
        error = GeopackAPIError.from_http_status(
            403,
            reason="Forbidden",
            text="",
            json_loader=lambda: {"code": "SOMETHING_ELSE"},
        )

        self.assertIsInstance(error, GeopackAuthError)
        self.assertNotIsInstance(error, QuotaExceeded)


if __name__ == "__main__":
    unittest.main()
