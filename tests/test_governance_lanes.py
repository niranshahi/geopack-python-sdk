"""Governance lanes (slice 015): upload caps, workflow admin reads, run delete.

Three separate contracts are pinned here:

* ``GET /uploads/limits`` carries exactly two caps — there is no
  allowed-extension or declared-type list on the wire, so the model does not
  invent one.
* ``POST /workflows/compile-spec`` is read-only: an unpublishable spec is a
  ``200`` with ``ok=False`` + ``issues``, not an exception.
* ``GET /workflows/{id}/tool-manifest`` is returned verbatim (ADR-0019: run
  exposure stays the runtime ACL).
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.models import UploadLimits
from geopack_sdk.uploads import UploadManager
from geopack_sdk.workflow_runs import WorkflowRunManager
from geopack_sdk.workflows import WorkflowManager


LIMITS = {"maxFileSizeMb": 500, "maxFilesPerUpload": 20}

STATISTICS = {
    "keywords": [{"value": "buffer", "count": 3}],
    "workgroups": [{"id": 1, "name": "GIS", "count": 2}],
    "owners": [{"id": 4, "displayName": "Ada", "count": 5}],
    "organizations": [{"id": 2, "name": "Org", "count": 5}],
    "dateRange": {"min": "2026-01-01", "max": "2026-11-19"},
}

COMPILED_OK = {"ok": True, "graph": {"nodes": []}, "issues": []}
COMPILED_NOT_PUBLISHABLE = {
    "ok": False,
    "graph": {"nodes": []},
    "issues": [{"code": "SPEC_MISSING_OUTPUT", "message": "no output node"}],
}

TOOL_MANIFEST = {
    "workflowId": 12,
    "tools": [{"name": "buffer", "parameters": {"distance": "number"}}],
}


class UploadLimitsTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = UploadManager(self.client)

    def test_caps_are_parsed_and_max_bytes_is_derived(self):
        self.client.get.return_value = LIMITS

        limits = self.manager.get_limits()

        self.client.get.assert_called_once_with("/uploads/limits")
        self.assertIsInstance(limits, UploadLimits)
        self.assertEqual(limits.maxFileSizeMb, 500)
        self.assertEqual(limits.maxFilesPerUpload, 20)
        self.assertEqual(limits.max_bytes, 500 * 1024 * 1024)

    def test_a_success_envelope_is_tolerated(self):
        self.client.get.return_value = {"success": True, "data": LIMITS}

        limits = self.manager.get_limits()

        self.assertEqual(limits.maxFileSizeMb, 500)

    def test_a_missing_cap_surfaces_instead_of_defaulting(self):
        self.client.get.return_value = {"maxFileSizeMb": 500}

        with self.assertRaises(Exception):
            self.manager.get_limits()


class WorkflowAdminTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = WorkflowManager(self.client)

    def test_get_statistics_is_a_passthrough(self):
        self.client.get.return_value = STATISTICS

        stats = self.manager.get_statistics()

        self.client.get.assert_called_once_with("/workflows/statistics")
        self.assertEqual(stats["workgroups"][0]["name"], "GIS")

    def test_compile_spec_posts_the_spec_mode(self):
        self.client.post.return_value = COMPILED_OK

        result = self.manager.compile_spec({"nodes": [], "edges": []})

        self.client.post.assert_called_once_with(
            "/workflows/compile-spec", json={"spec": {"nodes": [], "edges": []}}
        )
        self.assertTrue(result["ok"])

    def test_compile_spec_project_mode_uses_workflow_id(self):
        self.client.post.return_value = COMPILED_OK

        self.manager.compile_spec(workflow_id=12)

        self.assertEqual(
            self.client.post.call_args.kwargs["json"], {"workflowId": 12}
        )

    def test_compile_spec_forwards_the_budget_when_given(self):
        # Slice 031: the MCP spec lane asks for a compacted projection by budget.
        self.client.post.return_value = COMPILED_OK

        self.manager.compile_spec(workflow_id=12, budget_chars=4000)

        self.assertEqual(
            self.client.post.call_args.kwargs["json"],
            {"workflowId": 12, "budgetChars": 4000},
        )

    def test_unpublishable_spec_is_an_answer_not_an_exception(self):
        self.client.post.return_value = COMPILED_NOT_PUBLISHABLE

        result = self.manager.compile_spec({"nodes": []})

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "SPEC_MISSING_OUTPUT")

    def test_compile_spec_requires_exactly_one_mode(self):
        for kwargs in ({}, {"spec": {"nodes": []}, "workflow_id": 1}):
            with self.assertRaises(ValueError):
                self.manager.compile_spec(**kwargs)
        self.client.post.assert_not_called()

    def test_tool_manifest_is_verbatim(self):
        self.client.get.return_value = TOOL_MANIFEST

        manifest = self.manager.get_tool_manifest(12)

        self.client.get.assert_called_once_with("/workflows/12/tool-manifest")
        self.assertIs(manifest, TOOL_MANIFEST)

    def test_delete_without_runs_sends_no_flag(self):
        # Slice 033: the default lane is the safe one — the server refuses when
        # runs exist, so the SDK must not opt into the cascade by accident.
        self.client.delete.return_value = {"id": 12, "deleted": True, "runsDeleted": 0}

        outcome = self.manager.delete(12)

        self.client.delete.assert_called_once_with("/workflows/12")
        self.assertEqual(outcome["runsDeleted"], 0)

    def test_delete_with_runs_asks_for_the_cascade(self):
        self.client.delete.return_value = {"id": 12, "deleted": True, "runsDeleted": 4}

        outcome = self.manager.delete(12, with_runs=True)

        self.client.delete.assert_called_once_with(
            "/workflows/12", params={"withRuns": "true"}
        )
        self.assertEqual(outcome["runsDeleted"], 4)


class WorkflowRunDeleteTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = WorkflowRunManager(self.client)

    def test_delete_is_a_record_delete_not_a_cancel(self):
        self.client.delete.return_value = {"id": 9, "deleted": True}

        result = self.manager.delete(9)

        self.client.delete.assert_called_once_with("/workflow-runs/9")
        self.assertIsNone(result)
        self.client.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
