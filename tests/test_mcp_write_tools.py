"""Slice 021 — MCP write lanes: the EditDoc ladder, task cancel, the policy registry.

The handler tests use REAL SDK models and a ``MagicMock`` client (the 2026-11-02
lesson: never mock ``model_dump()``). The policy tests compare the registry
against the LIVE FastMCP surface, so an unclassified tool fails the suite —
that is the point of the slice (the registry is the contract).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import DatasetReadOnly, EditConflict
from geopack_sdk.models import EditResult, UploadLimits
from geopack_sdk_mcp.tool_handlers.edits import submit_edit_document
from geopack_sdk_mcp.tool_handlers.tasks import cancel_task
from geopack_sdk_mcp.tools.policy import (
    TOOL_POLICY,
    UNAVAILABLE_OPERATIONS,
    build_policy_payload,
)

DOCUMENT = {
    "version": "1.0",
    "changes": [{"operation": "update", "dataset": 12, "records": [{"gid": 1, "zone": "A"}]}],
}


def _result(**overrides):
    fields = {
        "editRef": "0b3f3a2e-0000-4000-8000-000000000001",
        "mode": "validate",
        "applied": False,
        "plan": {"operations": 1},
        "previews": [],
        "issues": [],
        "warnings": [],
        "counts": None,
        "identities": None,
    }
    fields.update(overrides)
    return EditResult(**fields)


class EditDocumentHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    # --- rule 1/3: the dry-run modes never write and may mint a ref --------

    def test_validate_is_the_default_and_mints_an_edit_ref(self):
        self.client.edit_documents.submit.return_value = _result()

        payload = submit_edit_document(self.client, 12, dict(DOCUMENT))

        kwargs = self.client.edit_documents.submit.call_args
        self.assertEqual(kwargs.kwargs["mode"], "validate")
        sent = kwargs.args[1]
        self.assertTrue(sent["editRef"])
        self.assertEqual(len(sent["editRef"]), len("0b3f3a2e-0000-4000-8000-000000000001"))
        self.assertNotIn("error", payload)
        self.assertEqual(payload["mode"], "validate")
        self.assertFalse(payload["writesApplied"])

    def test_the_callers_document_is_not_mutated_by_minting(self):
        self.client.edit_documents.submit.return_value = _result()

        submit_edit_document(self.client, 12, DOCUMENT)

        self.assertNotIn("editRef", DOCUMENT)

    def test_preview_keeps_the_callers_own_edit_ref(self):
        document = dict(DOCUMENT, editRef="caller-ref")
        self.client.edit_documents.submit.return_value = _result(editRef="caller-ref")

        payload = submit_edit_document(self.client, 12, document, mode="preview")

        sent = self.client.edit_documents.submit.call_args.args[1]
        self.assertEqual(sent["editRef"], "caller-ref")
        self.assertEqual(payload["editRef"], "caller-ref")
        self.assertEqual(payload["mode"], "preview")

    # --- rule 3: apply refuses to invent its audit anchor ------------------

    def test_apply_without_an_edit_ref_is_refused_before_the_network(self):
        payload = submit_edit_document(self.client, 12, dict(DOCUMENT), mode="apply")

        self.client.edit_documents.submit.assert_not_called()
        self.assertTrue(payload["error"])
        self.assertEqual(payload["type"], "invalid_args")
        self.assertEqual(payload["invalidArgs"], ["editRef"])
        self.assertIn("validate", payload["hint"])

    def test_apply_with_an_edit_ref_writes(self):
        document = dict(DOCUMENT, editRef="caller-ref")
        self.client.edit_documents.submit.return_value = _result(
            editRef="caller-ref", mode="apply", applied=True, counts={"updated": 1}
        )

        payload = submit_edit_document(self.client, 12, document, mode="apply")

        self.assertEqual(self.client.edit_documents.submit.call_args.kwargs["mode"], "apply")
        self.assertTrue(payload["writesApplied"])
        self.assertEqual(payload["counts"], {"updated": 1})
        self.assertNotIn("raw", payload)

    # --- rule 4: enumerations are named, before any network call -----------

    def test_unknown_mode_names_the_ladder(self):
        payload = submit_edit_document(self.client, 12, dict(DOCUMENT), mode="commit")

        self.client.edit_documents.submit.assert_not_called()
        self.assertEqual(payload["invalidArgs"], ["mode"])
        for mode in ("validate", "preview", "apply"):
            self.assertIn(mode, payload["hint"])

    def test_unknown_version_names_the_supported_list(self):
        document = dict(DOCUMENT, version="2.0")

        payload = submit_edit_document(self.client, 12, document)

        self.client.edit_documents.submit.assert_not_called()
        self.assertEqual(payload["invalidArgs"], ["version"])
        self.assertEqual(payload["supportedVersions"], ["1.0"])

    def test_a_non_envelope_document_is_refused(self):
        payload = submit_edit_document(self.client, 12, "not-a-dict")  # type: ignore[arg-type]

        self.client.edit_documents.submit.assert_not_called()
        self.assertEqual(payload["invalidArgs"], ["document"])

    def test_empty_changes_are_refused(self):
        payload = submit_edit_document(self.client, 12, {"version": "1.0", "changes": []})

        self.client.edit_documents.submit.assert_not_called()
        self.assertEqual(payload["invalidArgs"], ["changes"])

    # --- failure mapping ---------------------------------------------------

    def test_423_maps_to_dataset_read_only_with_a_next_step(self):
        self.client.edit_documents.submit.side_effect = DatasetReadOnly(
            423, "Dataset is read-only", {"code": "DATASET_READ_ONLY"}
        )

        payload = submit_edit_document(self.client, 12, dict(DOCUMENT))

        self.assertEqual(payload["type"], "DatasetReadOnly")
        self.assertEqual(payload["status_code"], 423)
        self.assertEqual(payload["code"], "DATASET_READ_ONLY")
        self.assertIn("plan", payload["hint"])

    def test_409_maps_to_edit_conflict_and_lists_the_issues(self):
        self.client.edit_documents.submit.side_effect = EditConflict(
            409,
            "Edit conflict",
            {
                "code": "EDIT_CONFLICT",
                "issues": [{"index": 0, "reason": "stale version"}],
                "editRef": "caller-ref",
            },
        )

        payload = submit_edit_document(self.client, 12, dict(DOCUMENT, editRef="caller-ref"))

        self.assertEqual(payload["type"], "EditConflict")
        self.assertEqual(payload["issues"], [{"index": 0, "reason": "stale version"}])
        self.assertEqual(payload["editRef"], "caller-ref")
        self.assertIn("validate", payload["hint"])


class CancelTaskHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_cancel_returns_the_server_answer_and_a_polling_hint(self):
        self.client.tasks.cancel_task.return_value = {"message": "Cancellation requested"}

        payload = cancel_task(self.client, "task-7")

        self.client.tasks.cancel_task.assert_called_once_with("task-7")
        self.assertEqual(payload["message"], "Cancellation requested")
        self.assertEqual(payload["taskId"], "task-7")
        self.assertTrue(payload["cancelRequested"])
        self.assertIn("canceled", payload["hint"])
        # Never the delete verb: D7 keeps record deletion SDK-only.
        self.client.tasks.delete_task_record.assert_not_called()

    def test_a_non_dict_server_answer_still_answers(self):
        self.client.tasks.cancel_task.return_value = None

        payload = cancel_task(self.client, "task-7")

        self.assertEqual(payload["taskId"], "task-7")


class PolicyRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from geopack_sdk_mcp.server import mcp

        cls.tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}  # noqa: SLF001

    def test_the_registry_classifies_every_registered_tool(self):
        self.assertEqual(set(TOOL_POLICY), set(self.tools))

    def test_exactly_five_mutating_tools(self):
        payload = build_policy_payload(None)
        self.assertEqual(
            set(payload["mutatingTools"]),
            {
                "geopack_sdk_upload_dataset",
                "geopack_sdk_submit_workflow",
                "geopack_sdk_run_analysis",
                "geopack_sdk_submit_edit_document",
                "geopack_sdk_cancel_task",
            },
        )

    def test_the_edit_lane_declares_its_dry_run_and_the_cancel_its_brief_consent(self):
        payload = build_policy_payload(None)
        edit = payload["mutatingTools"]["geopack_sdk_submit_edit_document"]
        cancel = payload["mutatingTools"]["geopack_sdk_cancel_task"]

        self.assertEqual(edit["dryRun"], "validate")
        self.assertEqual(edit["consent"], "explicit")
        self.assertEqual(cancel["consent"], "brief")
        self.assertFalse(cancel["dryRun"])

    def test_seven_operations_are_stated_unavailable(self):
        # 031 added delete_workflow_run beside delete_workflow: no create, no delete.
        payload = build_policy_payload(None)

        self.assertEqual(len(payload["unavailable"]), 7)
        self.assertEqual(tuple(payload["unavailable"]), UNAVAILABLE_OPERATIONS)
        self.assertFalse(
            [name for name in self.tools if "delete" in name],
            "no delete tool may be registered",
        )

    def test_local_writes_are_named_but_not_mutating(self):
        payload = build_policy_payload(None)

        self.assertEqual(
            set(payload["localWrites"]),
            {
                "geopack_sdk_get_dataset_thumbnail",
                "geopack_sdk_download_generated_file",
                "geopack_sdk_download_workflow_artifact",
            },
        )
        for name in payload["localWrites"]:
            self.assertFalse(TOOL_POLICY[name]["mutating"], name)

    def test_read_only_tools_do_not_overlap_the_mutating_list(self):
        payload = build_policy_payload(None)

        overlap = set(payload["readOnlyTools"]) & set(payload["mutatingTools"])
        self.assertEqual(overlap, set())
        self.assertEqual(
            len(payload["readOnlyTools"]) + len(payload["mutatingTools"]),
            len(self.tools),
        )

    def test_upload_limits_come_from_the_server(self):
        client = MagicMock()
        client.uploads.get_limits.return_value = UploadLimits(
            maxFileSizeMb=3, maxFilesPerUpload=5
        )

        payload = build_policy_payload(client)

        self.assertEqual(payload["uploadLimits"]["maxFileSizeMb"], 3)
        self.assertEqual(payload["uploadLimits"]["maxFilesPerUpload"], 5)
        self.assertEqual(payload["uploadLimits"]["maxBytes"], 3 * 1024 * 1024)
        self.assertNotIn("extensions", payload["uploadLimits"])

    def test_a_failing_upload_limits_call_degrades_the_field_not_the_tool(self):
        client = MagicMock()
        client.uploads.get_limits.side_effect = RuntimeError("boom")

        payload = build_policy_payload(client)

        self.assertTrue(payload["uploadLimits"]["unavailable"])
        self.assertEqual(payload["uploadLimits"]["reason"], "RuntimeError")
        self.assertEqual(payload["version"], 2)


if __name__ == "__main__":
    unittest.main()
