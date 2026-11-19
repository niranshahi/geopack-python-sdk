"""Publication lifecycle control plane (slice 014 §2.1).

Pins the two path families (dataset mount for create/list, ``/publications/{id}``
for everything else), the state transitions as one-shot calls, the delete
204/202 distinction, and the mint family: bearer-only, one protocol-specific URL
key, never a fabricated URL.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import GeopackAPIError, PublicationStateConflict
from geopack_sdk.publications import PublicationManager

PUBLICATION = {
    "id": 41,
    "datasetId": 7,
    "provider": "geoserver",
    "kind": "direct",
    "protocol": "wms",
    "visibility": "private",
    "status": "draft",
    "canonicalName": "gp_ds_7_wms",
    "createdAt": "2026-11-19T09:00:00.000Z",
    "updatedAt": "2026-11-19T09:30:00.000Z",
}

DESCRIPTOR = {
    "scope": "eyJzY29wZSI6MX0",
    "expiresAt": "2026-11-19T10:30:00.000Z",
    "strategy": "filter_pushdown",
    "style": None,
    "time": None,
}


class PublicationManagerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = PublicationManager(self.client)

    # --- dataset mount -----------------------------------------------------

    def test_list_for_dataset_reads_the_mount(self):
        self.client.get.return_value = [PUBLICATION]

        rows = self.manager.list_for_dataset(7)

        self.client.get.assert_called_once_with("/datasets/7/publications")
        self.assertEqual(rows[0].id, 41)
        self.assertEqual(rows[0].status, "draft")

    def test_list_for_dataset_tolerates_a_non_array_answer(self):
        self.client.get.return_value = {"unexpected": True}
        self.assertEqual(self.manager.list_for_dataset(7), [])

    def test_create_posts_under_the_dataset(self):
        self.client.post.return_value = PUBLICATION
        payload = {
            "provider": "geoserver",
            "kind": "direct",
            "protocol": "wms",
            "visibility": "private",
            "sourceStrategy": "direct_source",
        }

        created = self.manager.create(7, payload)

        self.client.post.assert_called_once_with(
            "/datasets/7/publications", json=payload
        )
        self.assertEqual(created.raw["datasetId"], 7)

    def test_create_rejects_a_non_dict_payload(self):
        with self.assertRaises(ValueError):
            self.manager.create(7, "nope")
        self.client.post.assert_not_called()

    # --- one publication ---------------------------------------------------

    def test_get_and_patch_target_the_publication(self):
        self.client.get.return_value = PUBLICATION
        self.assertEqual(self.manager.get(41).id, 41)

        self.client.patch.return_value = {**PUBLICATION, "visibility": "shared"}
        updated = self.manager.update(41, {"visibility": "shared"})

        self.client.patch.assert_called_once_with(
            "/publications/41", json={"visibility": "shared"}
        )
        self.assertEqual(updated.raw["visibility"], "shared")

    def test_delete_returns_none_on_204(self):
        self.client.delete.return_value = None

        self.assertIsNone(self.manager.delete(41))
        self.client.delete.assert_called_once_with("/publications/41")

    def test_delete_returns_the_202_ack_when_cleanup_is_queued(self):
        self.client.delete.return_value = {"status": "deleting"}

        self.assertEqual(self.manager.delete(41), {"status": "deleting"})

    def test_force_delete_is_an_explicit_argument(self):
        self.client.delete.return_value = {"id": 41, "deleted": True}

        ack = self.manager.delete(41, force=True)

        self.client.delete.assert_called_once_with("/publications/41/force")
        self.assertTrue(ack["deleted"])

    # --- state transitions -------------------------------------------------

    def test_enable_and_disable_are_one_shot_posts(self):
        self.client.post.side_effect = [
            {**PUBLICATION, "status": "sync_pending"},
            {**PUBLICATION, "status": "disabled"},
        ]

        enabled = self.manager.enable(41)
        disabled = self.manager.disable(41)

        self.assertEqual(
            [call.args[0] for call in self.client.post.call_args_list],
            ["/publications/41/enable", "/publications/41/disable"],
        )
        self.assertEqual(enabled.status, "sync_pending")
        self.assertEqual(disabled.status, "disabled")
        self.assertEqual(self.client.post.call_count, 2)

    def test_reconcile_answers_the_task_envelope(self):
        self.client.post.return_value = {
            "publication": {**PUBLICATION, "status": "sync_pending"},
            "taskId": "task-9",
        }

        result = self.manager.reconcile(41)

        self.client.post.assert_called_once_with("/publications/41/reconcile")
        self.assertEqual(result["taskId"], "task-9")
        self.assertEqual(result["publication"]["status"], "sync_pending")

    def test_rotate_public_token_reads_the_new_token(self):
        self.client.post.return_value = {
            **PUBLICATION,
            "visibility": "public",
            "publicAccessToken": "tok-new",
        }

        rotated = self.manager.rotate_public_token(41)

        self.client.post.assert_called_once_with(
            "/publications/41/public-token/rotate"
        )
        self.assertEqual(rotated.raw["publicAccessToken"], "tok-new")

    def test_state_conflict_maps_to_the_typed_error(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            409,
            reason="Conflict",
            text="",
            json_loader=lambda: {
                "error": {
                    "code": "PUBLICATION_STATE_CONFLICT",
                    "message": "Publication is being deleted.",
                    "state": "deleting",
                }
            },
        )

        with self.assertRaises(PublicationStateConflict) as ctx:
            self.manager.enable(41)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "PUBLICATION_STATE_CONFLICT")
        self.assertEqual(self.client.post.call_count, 1)

    # --- styles ------------------------------------------------------------

    def test_validate_style_posts_the_document_verbatim(self):
        sld = "<StyledLayerDescriptor version='1.0.0'/>"
        self.client.post.return_value = {"valid": True, "errors": []}

        result = self.manager.validate_style(41, sld)

        self.client.post.assert_called_once_with(
            "/publications/41/style/validate", json={"sld": sld}
        )
        self.assertTrue(result["valid"])

    def test_validate_style_rejects_an_empty_document(self):
        with self.assertRaises(ValueError):
            self.manager.validate_style(41, "   ")
        self.client.post.assert_not_called()

    def test_preview_style_returns_the_resolved_payload(self):
        payload = {"style": {"type": "sld", "sld": "<sld/>"}}
        self.client.post.return_value = {
            "valid": True,
            "sld": "<sld/>",
            "styleName": "gp_sty_abc",
            "warnings": [],
        }

        result = self.manager.preview_style(41, payload)

        self.client.post.assert_called_once_with(
            "/publications/41/style/preview", json=payload
        )
        self.assertEqual(result["styleName"], "gp_sty_abc")

    def test_style_from_dataset_returns_the_seed(self):
        self.client.post.return_value = {"sld": "<sld/>", "supported": True, "warnings": []}

        result = self.manager.style_from_dataset(41)

        self.client.post.assert_called_once_with(
            "/publications/41/style/from-dataset"
        )
        self.assertTrue(result["supported"])

    # --- render scopes and minted URLs -------------------------------------

    def test_create_render_scope_posts_the_validated_body(self):
        body = {"queryDsl": {"where": []}, "renderOptions": {}, "ttlSeconds": 900}
        self.client.post.return_value = DESCRIPTOR

        descriptor = self.manager.create_render_scope(41, body)

        self.client.post.assert_called_once_with(
            "/publications/41/render-scopes", json=body
        )
        self.assertEqual(descriptor["scope"], DESCRIPTOR["scope"])

    def test_create_render_scope_defaults_to_an_empty_body(self):
        self.client.post.return_value = DESCRIPTOR
        self.manager.create_render_scope(41)
        self.client.post.assert_called_once_with(
            "/publications/41/render-scopes", json={}
        )

    def test_each_mint_uses_its_own_url_key(self):
        expectations = {
            "mint_tiles_url": ("tiles", "tileUrl"),
            "mint_wms_url": ("wms", "wmsUrl"),
            "mint_wfs_url": ("wfs", "wfsUrl"),
            "mint_wmts_url": ("wmts", "wmtsUrl"),
        }
        for method_name, (protocol, url_key) in expectations.items():
            with self.subTest(method=method_name):
                self.client.post.reset_mock()
                self.client.post.return_value = {
                    **DESCRIPTOR,
                    url_key: f"http://localhost:3000/api/publications/41/{protocol}?scope=x",
                    "mediaExpiresAt": "2026-11-19T10:00:00.000Z",
                }

                data = getattr(self.manager, method_name)(41, {"ttlSeconds": 600})

                self.client.post.assert_called_once_with(
                    f"/publications/41/{protocol}/mint-access-url",
                    json={"ttlSeconds": 600},
                )
                self.assertIn(url_key, data)

    def test_a_mint_without_its_url_raises_instead_of_inventing_one(self):
        self.client.post.return_value = DESCRIPTOR

        with self.assertRaises(GeopackAPIError) as ctx:
            self.manager.mint_tiles_url(41)

        self.assertEqual(ctx.exception.status_code, 502)

    def test_mint_rejects_an_unknown_protocol(self):
        with self.assertRaises(ValueError):
            self.manager._mint(41, "other", {})
        self.client.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
