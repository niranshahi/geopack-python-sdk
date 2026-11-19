"""External OGC service control plane (slice 014 §1.4 / §2.3).

Pins the registration CRUD + probe paths, the fact that ``validate`` and
``validate_style`` answer 400 when the candidate is invalid (so the SDK raises),
that SLD is refused client-side as well as server-side, and both map-settings
scopes.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import GeopackAPIError
from geopack_sdk.external_services import ExternalServiceManager

DTO = {
    "id": 5,
    "name": "city-wms",
    "title": "City WMS",
    "protocol": "wms",
    "status": "active",
    "healthState": {"state": "healthy"},
    "mapSettings": None,
}

STYLE = {
    "type": "client-renderer",
    "renderer": {"type": "simple", "symbol": {"color": "#3388ff"}},
}


class ExternalServiceManagerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = ExternalServiceManager(self.client)

    # --- registrations -----------------------------------------------------

    def test_list_sends_the_supported_query_keys(self):
        self.client.get.return_value = {
            "items": [DTO],
            "total": 1,
            "page": 2,
            "pageSize": 10,
        }

        result = self.manager.list(page=2, page_size=10, protocol="wms", status="active", search="city")

        params = self.client.get.call_args.kwargs["params"]
        self.assertEqual(
            params,
            {"page": 2, "pageSize": 10, "protocol": "wms", "status": "active", "search": "city"},
        )
        self.assertEqual(result["items"][0]["name"], "city-wms")

    def test_validate_posts_the_candidate_and_returns_the_summary(self):
        payload = {"url": "https://example.com/wms", "protocol": "wms"}
        self.client.post.return_value = {"ok": True, "summary": {"layers": []}}

        result = self.manager.validate(payload)

        self.client.post.assert_called_once_with(
            "/external-services/validate", json=payload
        )
        self.assertTrue(result["ok"])

    def test_an_invalid_candidate_surfaces_the_400(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "ok": False,
                "error": {"message": "GetCapabilities failed.", "code": "EXTERNAL_PROBE_FAILED"},
            },
        )

        with self.assertRaises(GeopackAPIError) as ctx:
            self.manager.validate({"url": "https://bad.example/wms", "protocol": "wms"})

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.code, "EXTERNAL_PROBE_FAILED")

    def test_create_targets_the_collection(self):
        self.client.post.return_value = DTO
        payload = {
            "name": "city-wms",
            "title": "City WMS",
            "url": "https://example.com/wms",
            "protocol": "wms",
        }

        created = self.manager.create(payload)

        self.client.post.assert_called_once_with("/external-services", json=payload)
        self.assertEqual(created["id"], 5)

    def test_get_edit_update_delete_and_probe_paths(self):
        self.client.get.return_value = DTO
        self.assertEqual(self.manager.get(5)["id"], 5)
        self.client.get.assert_called_with("/external-services/5")

        self.client.get.return_value = {**DTO, "upstreamUrlMasked": "https://…"}
        self.manager.get_edit(5)
        self.client.get.assert_called_with("/external-services/5/edit")

        self.client.patch.return_value = {**DTO, "title": "New"}
        self.manager.update(5, {"title": "New"})
        self.client.patch.assert_called_once_with(
            "/external-services/5", json={"title": "New"}
        )

        self.manager.delete(5)
        self.client.delete.assert_called_once_with("/external-services/5")

        self.client.post.return_value = DTO
        self.manager.probe(5)
        self.client.post.assert_called_once_with("/external-services/5/probe")

    # --- style payload (no SLD) -------------------------------------------

    def test_get_style_returns_the_stored_payload(self):
        self.client.get.return_value = {"externalStyle": STYLE}

        result = self.manager.get_style(5)

        self.client.get.assert_called_once_with("/external-services/5/style")
        self.assertEqual(result["externalStyle"]["type"], "client-renderer")

    def test_set_style_puts_the_envelope(self):
        self.client.put.return_value = {"externalStyle": STYLE}

        result = self.manager.set_style(5, STYLE)

        self.client.put.assert_called_once_with("/external-services/5/style", json=STYLE)
        self.assertEqual(result["externalStyle"], STYLE)

    def test_sld_is_refused_before_any_request(self):
        with self.assertRaises(ValueError) as ctx:
            self.manager.set_style(
                5, {"type": "client-renderer", "sld": "<StyledLayerDescriptor/>"}
            )
        self.assertIn("EXTERNAL_SLD_UNSUPPORTED", str(ctx.exception))
        self.client.put.assert_not_called()

    def test_an_unknown_style_type_is_refused(self):
        with self.assertRaises(ValueError):
            self.manager.set_style(5, {"type": "sld"})
        self.client.put.assert_not_called()

    def test_validate_style_success_and_failure(self):
        self.client.post.return_value = {"valid": True, "externalStyle": STYLE}
        self.assertTrue(self.manager.validate_style(5, STYLE)["valid"])

        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {
                "valid": False,
                "errors": ["Layer 'roads' is not advertised by the external service."],
            },
        )
        with self.assertRaises(GeopackAPIError) as ctx:
            self.manager.validate_style(5, STYLE)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_clear_style_reports_whether_anything_was_cleared(self):
        self.client.delete.return_value = {"cleared": False}

        self.assertEqual(self.manager.clear_style(5), {"cleared": False})
        self.client.delete.assert_called_once_with("/external-services/5/style")

    # --- map settings at both scopes ---------------------------------------

    def test_registration_scope_map_settings(self):
        self.client.get.return_value = {"mapSettings": {"rootVisible": True}}

        result = self.manager.get_map_settings(5)

        self.client.get.assert_called_once_with("/external-services/5/map-settings")
        self.assertTrue(result["mapSettings"]["rootVisible"])

        settings = {
            "rootVisible": True,
            "layers": {"roads": True, "buildings": False},
            "order": {"root": ["roads", "buildings"]},
        }
        self.client.put.return_value = {"mapSettings": settings}
        self.manager.set_map_settings(5, settings)
        self.client.put.assert_called_once_with(
            "/external-services/5/map-settings", json=settings
        )

    def test_publication_scope_map_settings(self):
        self.client.get.return_value = {"mapSettings": None}
        self.manager.get_publication_map_settings(41)
        self.client.get.assert_called_once_with(
            "/external-services/publications/41/map-settings"
        )

        wfs_settings = {"rootVisible": False, "featureType": "roads"}
        self.client.put.return_value = {"mapSettings": wfs_settings}
        self.manager.set_publication_map_settings(41, wfs_settings)
        self.client.put.assert_called_once_with(
            "/external-services/publications/41/map-settings", json=wfs_settings
        )

    def test_map_settings_must_be_a_dict(self):
        with self.assertRaises(ValueError):
            self.manager.set_map_settings(5, ["nope"])
        with self.assertRaises(ValueError):
            self.manager.set_publication_map_settings(41, "nope")
        self.client.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
