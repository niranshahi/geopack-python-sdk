"""Edit documents (slice 012): the validate -> preview -> apply ladder.

Editing can destroy data (D14), so the contract tests pin the safe defaults:
``validate`` is the default mode, ``apply`` refuses to invent an ``editRef``,
and an unknown grammar version never reaches the wire.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.edits import (
    DEFAULT_EDIT_MODE,
    SUPPORTED_EDIT_DOCUMENT_VERSIONS,
    EditDocumentManager,
    build_edit_document,
    new_edit_ref,
)
from geopack_sdk.exceptions import EditConflict, EditDocumentVersionError
from geopack_sdk.models import EditResult

CHANGES = [
    {
        "op": "update",
        "dataset": 7,
        "identity": {"field": "gid", "value": 42},
        "attributes": {"name": "Zone A"},
    }
]

VALIDATE_ANSWER = {
    "editRef": "11111111-1111-4111-8111-111111111111",
    "mode": "validate",
    "applied": False,
    "plan": {"mode": "validate", "phases": {"updates": []}, "warnings": []},
    "issues": [],
}

PREVIEW_ANSWER = {
    "editRef": "11111111-1111-4111-8111-111111111111",
    "mode": "preview",
    "applied": False,
    "plan": {"mode": "preview"},
    "previews": [{"opId": "op-1", "kind": "row-update", "datasetId": 7}],
    "issues": [{"level": "warning", "message": "geometry unchanged"}],
}

APPLY_ANSWER = {
    "editRef": "11111111-1111-4111-8111-111111111111",
    "mode": "apply",
    "applied": True,
    "counts": {"7": {"updates": 1}},
    "identities": {"op-1": {"gid": 42}},
    "warnings": [],
}


class EditDocumentBuildTest(unittest.TestCase):
    def test_build_mints_an_edit_ref_and_defaults_to_validate(self):
        document = build_edit_document(CHANGES)

        self.assertEqual(document["version"], "1.0")
        self.assertEqual(document["mode"], DEFAULT_EDIT_MODE)
        self.assertEqual(document["changes"], CHANGES)
        self.assertTrue(document["editRef"])
        self.assertNotEqual(document["editRef"], build_edit_document([])["editRef"])

    def test_build_keeps_a_caller_supplied_ref_and_options(self):
        document = build_edit_document(
            CHANGES, edit_ref="fixed-ref", mode="apply", options={"dryRun": False}
        )

        self.assertEqual(document["editRef"], "fixed-ref")
        self.assertEqual(document["mode"], "apply")
        self.assertEqual(document["options"], {"dryRun": False})

    def test_build_rejects_an_unknown_version_before_any_request(self):
        with self.assertRaises(EditDocumentVersionError) as caught:
            build_edit_document(CHANGES, version="2.0")

        self.assertEqual(caught.exception.version, "2.0")
        self.assertIn(SUPPORTED_EDIT_DOCUMENT_VERSIONS[0], str(caught.exception))

    def test_build_rejects_an_unknown_mode(self):
        with self.assertRaises(ValueError):
            build_edit_document(CHANGES, mode="commit")

    def test_new_edit_ref_is_a_uuid4_string(self):
        ref = new_edit_ref()

        self.assertEqual(len(ref), 36)
        self.assertEqual(ref.count("-"), 4)


class EditDocumentManagerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = EditDocumentManager(self.client)

    def test_validate_sends_the_validate_mode(self):
        self.client.post.return_value = VALIDATE_ANSWER
        document = build_edit_document(CHANGES)

        result = self.manager.validate(7, document)

        endpoint, kwargs = self.client.post.call_args.args[0], self.client.post.call_args.kwargs
        self.assertEqual(endpoint, "/datasets/7/edits")
        self.assertEqual(kwargs["json"]["mode"], "validate")
        self.assertEqual(kwargs["json"]["version"], "1.0")
        self.assertIsInstance(result, EditResult)
        self.assertTrue(result.ok)
        self.assertFalse(result.applied)

    def test_preview_sends_the_preview_mode_and_returns_previews(self):
        self.client.post.return_value = PREVIEW_ANSWER

        result = self.manager.preview(7, build_edit_document(CHANGES))

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["mode"], "preview"
        )
        self.assertEqual(len(result.previews), 1)
        self.assertEqual(result.previews[0]["opId"], "op-1")
        # preview findings ride `issues`, so notes must merge them.
        self.assertEqual(len(result.notes), 1)

    def test_apply_sends_the_apply_mode_and_reports_counts(self):
        self.client.post.return_value = APPLY_ANSWER
        document = build_edit_document(CHANGES, edit_ref=new_edit_ref())

        result = self.manager.apply(7, document)

        self.assertEqual(self.client.post.call_args.kwargs["json"]["mode"], "apply")
        self.assertTrue(result.applied)
        self.assertTrue(result.ok)
        self.assertEqual(result.counts, {"7": {"updates": 1}})
        self.assertEqual(result.identities, {"op-1": {"gid": 42}})

    def test_apply_without_an_edit_ref_is_refused_before_the_request(self):
        with self.assertRaises(ValueError) as caught:
            self.manager.apply(7, {"version": "1.0", "mode": "apply", "changes": []})

        self.assertIn("editRef", str(caught.exception))
        self.client.post.assert_not_called()

    def test_an_unknown_version_never_reaches_the_wire(self):
        with self.assertRaises(EditDocumentVersionError):
            self.manager.validate(7, {"version": "9.9", "changes": []})

        self.client.post.assert_not_called()

    def test_a_missing_version_is_rejected_client_side(self):
        with self.assertRaises(EditDocumentVersionError):
            self.manager.validate(7, {"changes": []})

        self.client.post.assert_not_called()

    def test_submit_keeps_the_document_mode_when_no_override_is_given(self):
        self.client.post.return_value = PREVIEW_ANSWER

        self.manager.submit(7, build_edit_document(CHANGES, mode="preview"))

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["mode"], "preview"
        )

    def test_submit_defaults_to_validate_for_a_modless_document(self):
        self.client.post.return_value = VALIDATE_ANSWER

        self.manager.submit(7, {"version": "1.0", "changes": CHANGES})

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["mode"], "validate"
        )

    def test_the_result_keeps_the_raw_answer(self):
        self.client.post.return_value = APPLY_ANSWER

        result = self.manager.apply(
            7, build_edit_document(CHANGES, edit_ref=new_edit_ref())
        )

        self.assertEqual(result.raw["editRef"], APPLY_ANSWER["editRef"])
        self.assertEqual(result.edit_ref, APPLY_ANSWER["editRef"])

    def test_supported_versions_is_explicit(self):
        self.assertEqual(self.manager.supported_versions(), ["1.0"])

    def test_a_409_edit_conflict_surfaces_the_server_issues(self):
        exc = EditConflict.from_http_status(
            409,
            reason="Conflict",
            text="",
            json_loader=lambda: {
                "code": "EDIT_CARDINALITY_VIOLATION",
                "message": "one-to-one violated",
                "editRef": "ref-9",
                "issues": [{"opId": "op-1", "code": "EDIT_CARDINALITY_VIOLATION"}],
            },
        )
        self.client.post.side_effect = exc

        with self.assertRaises(EditConflict) as caught:
            self.manager.apply(
                7, build_edit_document(CHANGES, edit_ref="ref-9")
            )

        self.assertEqual(caught.exception.code, "EDIT_CARDINALITY_VIOLATION")
        self.assertEqual(caught.exception.edit_ref, "ref-9")
        self.assertEqual(len(caught.exception.issues), 1)


if __name__ == "__main__":
    unittest.main()
