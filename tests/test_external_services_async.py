"""Async external-service manager (slice 014) — parity with the sync suite."""

import unittest
from unittest.mock import AsyncMock

from geopack_sdk.async_external_services import AsyncExternalServiceManager
from geopack_sdk.exceptions import GeopackAPIError

DTO = {"id": 5, "name": "city-wms", "protocol": "wms"}
STYLE = {"type": "wms-named-style", "bindings": [{"layer": "roads", "style": "line"}]}


class AsyncExternalServiceManagerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.manager = AsyncExternalServiceManager(self.client)

    async def test_registration_crud(self):
        self.client.get.return_value = {"items": [DTO], "total": 1}
        self.assertEqual((await self.manager.list(protocol="wms"))["items"][0]["id"], 5)

        self.client.post.return_value = {"ok": True, "summary": {}}
        await self.manager.validate({"url": "https://x/wms", "protocol": "wms"})
        self.client.post.assert_awaited_with(
            "/external-services/validate", json={"url": "https://x/wms", "protocol": "wms"}
        )

        self.client.post.return_value = DTO
        self.assertEqual((await self.manager.create({"name": "city-wms"}))["id"], 5)

        self.client.get.return_value = DTO
        await self.manager.get(5)
        await self.manager.get_edit(5)
        self.client.get.assert_awaited_with("/external-services/5/edit")

        self.client.patch.return_value = DTO
        await self.manager.update(5, {"title": "New"})
        self.client.patch.assert_awaited_once_with(
            "/external-services/5", json={"title": "New"}
        )

        await self.manager.delete(5)
        self.client.delete.assert_awaited_once_with("/external-services/5")

        self.client.post.return_value = DTO
        await self.manager.probe(5)
        self.client.post.assert_awaited_with("/external-services/5/probe")

    async def test_invalid_candidate_surfaces_the_400(self):
        self.client.post.side_effect = GeopackAPIError.from_http_status(
            400,
            reason="Bad Request",
            text="",
            json_loader=lambda: {"ok": False, "error": {"message": "upstream failed"}},
        )

        with self.assertRaises(GeopackAPIError):
            await self.manager.validate({"url": "https://bad/wms", "protocol": "wms"})

    async def test_style_lanes_refuse_sld(self):
        with self.assertRaises(ValueError):
            await self.manager.set_style(5, {"type": "client-renderer", "sld": "<x/>"})
        self.client.put.assert_not_awaited()

        self.client.put.return_value = {"externalStyle": STYLE}
        await self.manager.set_style(5, STYLE)
        self.client.put.assert_awaited_once_with("/external-services/5/style", json=STYLE)

        self.client.post.return_value = {"valid": True, "externalStyle": STYLE}
        self.assertTrue((await self.manager.validate_style(5, STYLE))["valid"])

        self.client.delete.return_value = {"cleared": True}
        self.assertTrue((await self.manager.clear_style(5))["cleared"])

    async def test_both_map_settings_scopes(self):
        self.client.get.return_value = {"mapSettings": None}
        await self.manager.get_map_settings(5)
        self.client.get.assert_awaited_with("/external-services/5/map-settings")

        await self.manager.get_publication_map_settings(41)
        self.client.get.assert_awaited_with(
            "/external-services/publications/41/map-settings"
        )

        settings = {"rootVisible": True, "featureType": "roads"}
        self.client.put.return_value = {"mapSettings": settings}
        await self.manager.set_map_settings(5, settings)
        self.client.put.assert_awaited_with(
            "/external-services/5/map-settings", json=settings
        )

        await self.manager.set_publication_map_settings(41, settings)
        self.client.put.assert_awaited_with(
            "/external-services/publications/41/map-settings", json=settings
        )


if __name__ == "__main__":
    unittest.main()
