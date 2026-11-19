"""Async half of the edit-document ladder — parity with the sync manager."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from geopack_sdk.async_edits import AsyncEditDocumentManager
from geopack_sdk.edits import build_edit_document, new_edit_ref
from geopack_sdk.exceptions import EditDocumentVersionError
from geopack_sdk.models import EditResult

from tests.test_edit_documents import (
    APPLY_ANSWER,
    CHANGES,
    PREVIEW_ANSWER,
    VALIDATE_ANSWER,
)


class AsyncEditDocumentManagerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.post = AsyncMock()
        self.manager = AsyncEditDocumentManager(self.client)

    async def test_validate_sends_the_validate_mode(self):
        self.client.post.return_value = VALIDATE_ANSWER

        result = await self.manager.validate(7, build_edit_document(CHANGES))

        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["mode"], "validate"
        )
        self.assertIsInstance(result, EditResult)
        self.assertTrue(result.ok)

    async def test_preview_and_apply_match_the_sync_ladder(self):
        self.client.post.return_value = PREVIEW_ANSWER
        preview = await self.manager.preview(7, build_edit_document(CHANGES))
        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["mode"], "preview"
        )
        self.assertEqual(preview.previews[0]["opId"], "op-1")

        self.client.post.return_value = APPLY_ANSWER
        applied = await self.manager.apply(
            7, build_edit_document(CHANGES, edit_ref=new_edit_ref())
        )
        self.assertEqual(
            self.client.post.call_args.kwargs["json"]["mode"], "apply"
        )
        self.assertTrue(applied.applied)

    async def test_apply_without_an_edit_ref_is_refused_client_side(self):
        with self.assertRaises(ValueError):
            await self.manager.apply(
                7, {"version": "1.0", "mode": "apply", "changes": []}
            )

        self.client.post.assert_not_called()

    async def test_an_unknown_version_never_reaches_the_wire(self):
        with self.assertRaises(EditDocumentVersionError):
            await self.manager.validate(7, {"version": "2.0", "changes": []})

        self.client.post.assert_not_called()

    async def test_supported_versions_matches_sync(self):
        self.assertEqual(self.manager.supported_versions(), ["1.0"])


if __name__ == "__main__":
    unittest.main()
