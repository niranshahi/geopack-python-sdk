import unittest
from unittest.mock import MagicMock

from geopack_sdk.quotas import QuotaManager
from geopack_sdk.models import QuotaSummary


SUMMARY_PAYLOAD = {
    "enabled": True,
    "reason": "ok",
    "plan": {
        "id": 1,
        "code": "default",
        "displayName": "Default",
        "tier": 3,
        "status": "ACTIVE",
    },
    "limits": [
        {
            "limitId": 10,
            "dimensionKey": "workflow.count.runs.daily",
            "limitType": "hard",
            "limitValue": 5,
            "warnThresholdPercent": 80,
            "window": "daily",
            "windowDays": 1,
            "currentValue": 4,
            "remaining": 1,
            "percentageUsed": 80,
        }
    ],
}


class TestQuotaManager(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.get.return_value = SUMMARY_PAYLOAD
        self.mgr = QuotaManager(self.client)

    def test_my_summary(self):
        summary = self.mgr.my_summary()
        self.assertIsInstance(summary, QuotaSummary)
        self.assertTrue(summary.enabled)
        self.client.get.assert_called_once_with("/quotas/me/summary")

    def test_is_over_limit_false_when_remaining(self):
        summary = QuotaSummary(**SUMMARY_PAYLOAD)
        self.assertFalse(
            self.mgr.is_over_limit("workflow.count.runs.daily", summary=summary)
        )

    def test_warn_limits(self):
        summary = QuotaSummary(**SUMMARY_PAYLOAD)
        warned = self.mgr.warn_limits(summary=summary)
        self.assertEqual(len(warned), 1)
        self.assertEqual(warned[0].dimensionKey, "workflow.count.runs.daily")


if __name__ == "__main__":
    unittest.main()
