"""Test TokenRegistry singleton and token sharing between sync/async clients."""

import unittest
from unittest.mock import MagicMock, patch

from geopack_sdk.token_registry import TokenRegistry
from geopack_sdk.auth import AuthManager
from geopack_sdk.async_auth import AsyncAuthManager


class TestTokenRegistry(unittest.TestCase):
    """Test TokenRegistry singleton behavior."""

    def setUp(self):
        """Clear TokenRegistry between tests."""
        TokenRegistry._instance = None

    def tearDown(self):
        """Clear TokenRegistry after tests."""
        TokenRegistry._instance = None

    def test_singleton_pattern(self):
        """TokenRegistry should return the same instance."""
        registry1 = TokenRegistry()
        registry2 = TokenRegistry()
        self.assertIs(registry1, registry2)

    def test_token_sharing_within_instance(self):
        """Token set on one reference should be readable from another."""
        registry1 = TokenRegistry()
        registry2 = TokenRegistry()

        registry1.access_token = "test_token_123"
        self.assertEqual(registry2.access_token, "test_token_123")

    def test_refresh_token_sharing(self):
        """Refresh token should also be shared."""
        registry1 = TokenRegistry()
        registry2 = TokenRegistry()

        registry1.refresh_token = "refresh_123"
        self.assertEqual(registry2.refresh_token, "refresh_123")

    def test_sync_async_token_sharing(self):
        """Sync AuthManager and AsyncAuthManager should share tokens via TokenRegistry."""
        sync_mock_client = MagicMock()
        async_mock_client = MagicMock()

        sync_auth = AuthManager(sync_mock_client)
        async_auth = AsyncAuthManager(async_mock_client)

        # Set token via sync auth
        sync_auth.token = "shared_token_456"

        # Should be readable via async auth
        self.assertEqual(async_auth.token, "shared_token_456")

        # Set refresh token via async auth
        async_auth.refresh_token = "refresh_456"

        # Should be readable via sync auth
        self.assertEqual(sync_auth.refresh_token, "refresh_456")

    def test_environment_variable_fallback(self):
        """If no token set, should fall back to env var."""
        with patch.dict("os.environ", {"GEOPACK_ACCESS_TOKEN": "env_token"}):
            registry = TokenRegistry()
            # No internal token set, should read from env
            self.assertEqual(registry.access_token, "env_token")

    def test_internal_token_overrides_env(self):
        """Internal token should override env var."""
        with patch.dict("os.environ", {"GEOPACK_ACCESS_TOKEN": "env_token"}):
            registry = TokenRegistry()
            registry.access_token = "internal_token"
            self.assertEqual(registry.access_token, "internal_token")

    def test_clear_tokens(self):
        """clear() should reset tokens."""
        registry = TokenRegistry()
        registry.access_token = "token_x"
        registry.refresh_token = "refresh_x"

        registry.clear()

        self.assertIsNone(registry.access_token or None)  # Will be None or read from env
        self.assertIsNone(registry.refresh_token or None)

    def test_thread_safety(self):
        """TokenRegistry should handle concurrent access safely."""
        import threading

        registry = TokenRegistry()
        tokens = []

        def set_and_read_token(token_value):
            registry.access_token = token_value
            tokens.append(registry.access_token)

        threads = [
            threading.Thread(target=set_and_read_token, args=(f"token_{i}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All tokens should be one of the values we set (no corruption)
        self.assertTrue(all(t.startswith("token_") for t in tokens))


if __name__ == "__main__":
    unittest.main()
