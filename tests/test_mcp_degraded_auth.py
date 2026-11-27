"""Degraded auth mode + AUTH_REQUIRED contract (slice 034 P6)."""

import asyncio
import os
import unittest
from unittest.mock import patch

from geopack_sdk_mcp import context
from geopack_sdk_mcp.auth_bootstrap import AppContext, authentication_required
from geopack_sdk_mcp.auth_errors import GeopackMCPAuthError
from geopack_sdk_mcp.errors import tool_error_payload
from geopack_sdk_mcp.tools import auth as auth_tool


class DegradedAuthTest(unittest.TestCase):
    def setUp(self):
        self._saved = context._lifespan_client
        context.set_lifespan_client(None)
        self._env = patch.dict(os.environ, {"GEOPACK_API_URL": "http://x/api"}, clear=False)
        self._env.start()

    def tearDown(self):
        context.set_lifespan_client(self._saved)
        self._env.stop()

    def test_get_client_raises_auth_required(self):
        with self.assertRaises(GeopackMCPAuthError):
            context.get_client(object())

    def test_get_lifespan_client_raises_auth_required(self):
        with self.assertRaises(GeopackMCPAuthError):
            context.get_lifespan_client()

    def test_error_payload_maps_to_auth_required(self):
        payload = tool_error_payload(authentication_required())
        self.assertTrue(payload["error"])
        self.assertEqual(payload["code"], "AUTH_REQUIRED")
        self.assertIn("geopack-sdk login", payload["hint"])
        self.assertTrue(payload["checks"])

    def test_auth_status_reports_unauthenticated(self):
        status = auth_tool.build_auth_status(None)
        self.assertFalse(status["authenticated"])
        self.assertIn("geopack-sdk login", status["nextStep"])
        self.assertTrue(status["checks"])

    def test_lifespan_starts_in_degraded_mode(self):
        from geopack_sdk_mcp import server

        with patch(
            "geopack_sdk_mcp.server.bootstrap_geopack_client",
            side_effect=authentication_required(),
        ):
            async def run():
                async with server._app_lifespan(None) as app_ctx:
                    return app_ctx

            app_ctx = asyncio.run(run())

        self.assertIsInstance(app_ctx, AppContext)
        self.assertIsNone(app_ctx.client)


if __name__ == "__main__":
    unittest.main()