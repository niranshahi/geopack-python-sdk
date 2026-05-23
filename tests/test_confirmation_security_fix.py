"""Security tests for human-in-the-loop destructive operation confirmations."""

import os
import tempfile
import unittest
from pathlib import Path

import geopack_sdk_mcp.confirmation as confirmation_module
from geopack_sdk_mcp.confirmation import compute_payload_fingerprint, get_confirmation_manager
from geopack_sdk_mcp.destructive_guard import guard_destructive_operation


class ConfirmationSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store_path = Path(self._tmpdir.name) / "confirmations.json"
        confirmation_module._confirmation_manager = None
        os.environ["GEOPACK_CONFIRM_STORE"] = str(self.store_path)
        self.manager = get_confirmation_manager()

    def tearDown(self) -> None:
        confirmation_module._confirmation_manager = None
        os.environ.pop("GEOPACK_CONFIRM_STORE", None)
        self._tmpdir.cleanup()

    def test_agent_cannot_execute_without_human_approval(self) -> None:
        guard = guard_destructive_operation("delete_dataset", 2432)
        self.assertFalse(guard.should_execute)
        self.assertIsNotNone(guard.confirmation_id)
        self.assertTrue(guard.response["needs_confirmation"])

        execute = guard_destructive_operation(
            "delete_dataset", 2432, confirmation_id=guard.confirmation_id
        )
        self.assertFalse(execute.should_execute)
        self.assertEqual(execute.response["status"], "pending")

    def test_approval_workflow_and_single_use(self) -> None:
        guard = guard_destructive_operation("delete_dataset", 99)
        cid = guard.confirmation_id
        assert cid is not None

        self.assertTrue(self.manager.approve_request(cid, approved_by="human"))

        ready = guard_destructive_operation(
            "delete_dataset", 99, confirmation_id=cid
        )
        self.assertTrue(ready.should_execute)

        self.assertTrue(self.manager.consume_request(cid))

        reused = guard_destructive_operation(
            "delete_dataset", 99, confirmation_id=cid
        )
        self.assertFalse(reused.should_execute)
        self.assertEqual(reused.response["status"], "executed")

    def test_rejection_blocks_execution(self) -> None:
        guard = guard_destructive_operation("upload_dataset", "/tmp/a.geojson")
        cid = guard.confirmation_id
        assert cid is not None

        self.manager.reject_request(cid, reason="not allowed")
        blocked = guard_destructive_operation(
            "upload_dataset", "/tmp/a.geojson", confirmation_id=cid
        )
        self.assertFalse(blocked.should_execute)
        self.assertEqual(blocked.response["status"], "rejected")

    def test_payload_mismatch_blocks_execution(self) -> None:
        payload_a = {"workflow_id": 1, "params": {"x": 1}}
        payload_b = {"workflow_id": 1, "params": {"x": 2}}
        fp_a = compute_payload_fingerprint(payload_a)
        fp_b = compute_payload_fingerprint(payload_b)
        self.assertNotEqual(fp_a, fp_b)

        guard = guard_destructive_operation(
            "submit_workflow", 1, payload=payload_a
        )
        cid = guard.confirmation_id
        assert cid is not None
        self.manager.approve_request(cid)

        blocked = guard_destructive_operation(
            "submit_workflow", 1, confirmation_id=cid, payload=payload_b
        )
        self.assertFalse(blocked.should_execute)
        self.assertEqual(blocked.response["status"], "payload_mismatch")

    def test_resource_specific_approval(self) -> None:
        g1 = guard_destructive_operation("delete_dataset", 1)
        g2 = guard_destructive_operation("delete_dataset", 2)
        assert g1.confirmation_id and g2.confirmation_id
        self.manager.approve_request(g1.confirmation_id)

        only_first = guard_destructive_operation(
            "delete_dataset", 1, confirmation_id=g1.confirmation_id
        )
        second = guard_destructive_operation(
            "delete_dataset", 2, confirmation_id=g1.confirmation_id
        )
        self.assertTrue(only_first.should_execute)
        self.assertFalse(second.should_execute)
        self.assertEqual(second.response["status"], "mismatch")


if __name__ == "__main__":
    unittest.main()
