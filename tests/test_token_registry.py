"""Per-client token handling and single-flight refresh (slice 034).

Replaces the old singleton assertions: ``TokenRegistry`` is no longer a
process-wide singleton, sync/async clients are independent unless they share an
``AuthState`` explicitly, and concurrent refreshes run exactly once.
"""

import threading
import unittest
from unittest.mock import patch

from geopack_sdk.token_registry import TokenRegistry
from geopack_sdk.auth import AuthManager
from geopack_sdk.auth_state import AuthState


class _FakeResponse:
    def __init__(self, data):
        self._data = data
        self.ok = True

    def json(self):
        return self._data


class _FakeSession:
    def __init__(self, refresh_payloads):
        self.headers = {}
        self._refresh_payloads = list(refresh_payloads)
        self.refresh_calls = 0
        self._lock = threading.Lock()

    def post(self, url, json=None, timeout=None):
        with self._lock:
            self.refresh_calls += 1
            idx = min(self.refresh_calls - 1, len(self._refresh_payloads) - 1)
            payload = self._refresh_payloads[idx]
        return _FakeResponse(payload)


class _FakeClient:
    def __init__(self, base_url="http://localhost:3000/api", refresh_payloads=None):
        self.base_url = base_url
        self.session = _FakeSession(
            refresh_payloads or [{"accessToken": "new_access", "refreshToken": "new_refresh"}]
        )


class TestTokenRegistry(unittest.TestCase):
    def test_not_a_singleton(self):
        self.assertIsNot(TokenRegistry(), TokenRegistry())

    def test_instances_are_isolated(self):
        r1, r2 = TokenRegistry(), TokenRegistry()
        r1.access_token = "a"
        self.assertEqual(r1.access_token, "a")
        self.assertIsNone(r2.access_token)

    def test_environment_variable_fallback(self):
        with patch.dict("os.environ", {"GEOPACK_ACCESS_TOKEN": "env_token"}):
            self.assertEqual(TokenRegistry().access_token, "env_token")

    def test_env_fallback_can_be_disabled(self):
        with patch.dict("os.environ", {"GEOPACK_ACCESS_TOKEN": "env_token"}):
            self.assertIsNone(TokenRegistry(env_fallback=False).access_token)

    def test_internal_token_overrides_env(self):
        with patch.dict("os.environ", {"GEOPACK_ACCESS_TOKEN": "env_token"}):
            r = TokenRegistry()
            r.access_token = "internal_token"
            self.assertEqual(r.access_token, "internal_token")

    def test_clear_tokens(self):
        r = TokenRegistry()
        r.access_token = "x"
        r.refresh_token = "y"
        r.clear()
        self.assertIsNone(r.access_token)
        self.assertIsNone(r.refresh_token)

    def test_thread_safety(self):
        registry = TokenRegistry()
        seen = []

        def work(value):
            registry.access_token = value
            seen.append(registry.access_token)

        threads = [threading.Thread(target=work, args=(f"token_{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(s.startswith("token_") for s in seen))


class TestAuthStateIsolation(unittest.TestCase):
    def test_clients_are_independent(self):
        a = AuthManager(_FakeClient())
        b = AuthManager(_FakeClient())
        a.token = "a_token"
        self.assertEqual(a.token, "a_token")
        self.assertIsNone(b.token)

    def test_explicit_state_sharing(self):
        shared = AuthState(base_url="http://x/api")
        c1, c2 = _FakeClient(), _FakeClient()
        c1.auth_state = shared
        c2.auth_state = shared
        a1, a2 = AuthManager(c1), AuthManager(c2)
        a1.token = "shared_token"
        self.assertEqual(a2.token, "shared_token")


class TestSingleFlightRefresh(unittest.TestCase):
    def test_concurrent_refresh_runs_once(self):
        client = _FakeClient(refresh_payloads=[{"accessToken": "n", "refreshToken": "r"}])
        auth = AuthManager(client)
        auth.token = "stale"
        auth.refresh_token = "old_refresh"

        errors = []

        def worker():
            try:
                auth.refresh(stale_token="stale")
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(client.session.refresh_calls, 1)

    def test_rotation_updates_refresh_token(self):
        client = _FakeClient(refresh_payloads=[{"accessToken": "n2", "refreshToken": "r2"}])
        auth = AuthManager(client)
        auth.token = "stale"
        auth.refresh_token = "r1"
        auth.refresh(stale_token="stale")
        self.assertEqual(auth.token, "n2")
        self.assertEqual(auth.refresh_token, "r2")


if __name__ == "__main__":
    unittest.main()
