"""MCP auth bootstrap over the credential store (slice 034, P4)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geopack_sdk.auth_state import store_key
from geopack_sdk.credentials import FileStore, StoredCredentials, save_credentials
from geopack_sdk_mcp import auth_bootstrap
from geopack_sdk_mcp.auth_errors import GeopackMCPAuthError


class McpBootstrapTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = self._tmp.name
        self._env = patch.dict(
            os.environ,
            {
                "GEOPACK_API_URL": "http://x/api",
                "GEOPACK_CONFIG_DIR": d,
                "GEOPACK_CREDENTIALS_FILE": str(Path(d) / "credentials.json"),
                "GEOPACK_CREDENTIAL_STORE": "file",
                "GEOPACK_MCP_SKIP_DOTENV": "1",
            },
            clear=False,
        )
        self._env.start()
        for key in ("GEOPACK_ACCESS_TOKEN", "GEOPACK_REFRESH_TOKEN", "GEOPACK_USERNAME",
                    "GEOPACK_PASSWORD", "GEOPACK_PROFILE", "GEOPACK_API_KEY"):
            os.environ.pop(key, None)
        auth_bootstrap._precached_client = None

    def tearDown(self):
        auth_bootstrap._precached_client = None
        self._env.stop()
        self._tmp.cleanup()

    def test_stored_profile_refreshes_at_startup(self):
        store = FileStore(Path(self._tmp.name) / "refresh-tokens.json")
        store.set_refresh_token(store_key("http://x/api", "default"), "refresh-1")

        with patch("geopack_sdk.auth.AuthManager.refresh") as refresh:
            refresh.side_effect = lambda *a, **k: {}
            client = auth_bootstrap.bootstrap_geopack_client()

        refresh.assert_called_once()
        self.assertEqual(client.base_url, "http://x/api")

    def test_missing_credentials_raises_actionable_error(self):
        with self.assertRaises(GeopackMCPAuthError):
            auth_bootstrap.bootstrap_geopack_client()

    def test_legacy_token_file_still_used(self):
        save_credentials(
            StoredCredentials(
                api_url="http://x/api",
                access_token="legacy-access",
                refresh_token="legacy-refresh",
                username="u",
            )
        )
        client = auth_bootstrap.bootstrap_geopack_client()
        self.assertEqual(client.auth.token, "legacy-access")

    def test_env_username_password_still_authenticates(self):
        os.environ["GEOPACK_USERNAME"] = "u"
        os.environ["GEOPACK_PASSWORD"] = "p"
        with patch("geopack_sdk.auth.AuthManager.login") as login:
            login.return_value = {}
            client = auth_bootstrap.bootstrap_geopack_client()
        login.assert_called_once()
        self.assertEqual(client.base_url, "http://x/api")


if __name__ == "__main__":
    unittest.main()
