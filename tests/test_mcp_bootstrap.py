import os
import unittest
from unittest.mock import MagicMock, patch

from geopack_sdk_mcp.auth_bootstrap import bootstrap_geopack_client


class TestMcpBootstrap(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "GEOPACK_API_URL": "http://example.com/api",
            "GEOPACK_ACCESS_TOKEN": "test-token",
        },
        clear=False,
    )
    @patch("geopack_sdk_mcp.auth_bootstrap.GeopackClient")
    def test_bootstrap_uses_access_token_from_env(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        client = bootstrap_geopack_client()

        self.assertIs(client, mock_client)
        mock_client.auth.login.assert_not_called()
        self.assertEqual(mock_client.auth.token, "test-token")
        mock_client.session.headers.update.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "GEOPACK_API_URL": "http://example.com/api",
            "GEOPACK_USERNAME": "alice",
            "GEOPACK_PASSWORD": "secret",
        },
        clear=False,
    )
    @patch("geopack_sdk_mcp.auth_bootstrap.GeopackClient")
    def test_bootstrap_logs_in_with_username_password(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        env = os.environ.copy()
        env.pop("GEOPACK_ACCESS_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            os.environ["GEOPACK_API_URL"] = "http://example.com/api"
            os.environ["GEOPACK_USERNAME"] = "alice"
            os.environ["GEOPACK_PASSWORD"] = "secret"
            client = bootstrap_geopack_client()

        self.assertIs(client, mock_client)
        mock_client.auth.login.assert_called_once_with(username="alice", password="secret")

    @patch.dict(
        os.environ,
        {"GEOPACK_API_URL": "http://example.com/api"},
        clear=False,
    )
    @patch("geopack_sdk_mcp.auth_bootstrap.load_credentials")
    @patch("geopack_sdk_mcp.auth_bootstrap.GeopackClient")
    def test_bootstrap_uses_stored_credentials(
        self, mock_client_cls, mock_load_creds
    ):
        from geopack_sdk.credentials import StoredCredentials

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_load_creds.return_value = StoredCredentials(
            api_url="http://example.com/api",
            access_token="stored-token",
            refresh_token="stored-refresh",
            username="bob",
        )
        env = {k: v for k, v in os.environ.items() if k not in (
            "GEOPACK_ACCESS_TOKEN",
            "GEOPACK_USERNAME",
            "GEOPACK_PASSWORD",
            "GEOPACK_API_KEY",
        )}
        with patch.dict(os.environ, env, clear=True):
            os.environ["GEOPACK_API_URL"] = "http://example.com/api"
            bootstrap_geopack_client()

        mock_client.auth.login.assert_not_called()
        self.assertEqual(mock_client.auth.token, "stored-token")


if __name__ == "__main__":
    unittest.main()
