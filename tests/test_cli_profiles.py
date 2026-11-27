"""CLI login/logout/status/profiles over the credential store (slice 034).

Network is stubbed by replacing ``cli.GeopackClient`` with a fake whose auth
manager drives a real :class:`~geopack_sdk.auth_state.AuthState`, so the CLI's
store/profile wiring is exercised end to end.
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from geopack_sdk.auth_state import AuthState, store_key
from geopack_sdk.credentials import MemoryStore, ProfileRegistry, StoredProfile, resolve_store
from geopack_sdk.cli import main as cli


class _FakeAuth:
    def __init__(self, state: AuthState):
        self._state = state

    @property
    def token(self):
        return self._state.access_token

    @property
    def refresh_token(self):
        return self._state.refresh_token

    @refresh_token.setter
    def refresh_token(self, value):
        self._state.refresh_token = value

    def login(self, username=None, password=None):
        self._state.set_tokens("access-1", "refresh-1")
        return {"user": {"userName": username}}

    def refresh(self):
        return {}


class _FakeClient:
    def __init__(self, base_url=None, credential_store=None, auth_profile="default", **kwargs):
        self.base_url = base_url
        self.auth_state = AuthState(
            base_url=base_url or "", profile=auth_profile, store=credential_store
        )
        self.auth = _FakeAuth(self.auth_state)

    def post(self, *args, **kwargs):
        return {}


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = self._tmp.name
        self._env = patch.dict(
            os.environ,
            {
                "GEOPACK_CONFIG_DIR": d,
                "GEOPACK_CREDENTIALS_FILE": str(Path(d) / "credentials.json"),
                "GEOPACK_API_URL": "http://example.test/api",
            },
            clear=False,
        )
        self._env.start()
        self._patch = patch.object(cli, "GeopackClient", _FakeClient)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_login_persists_profile_and_refresh_token(self):
        code, out, _ = self._run(
            ["login", "--api-url", "http://x/api", "--username", "u", "--password", "p", "--store", "memory"]
        )
        self.assertEqual(code, 0)
        self.assertIn("Logged in as u", out)

        entry = ProfileRegistry().get("default")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.api_url, "http://x/api")
        self.assertEqual(entry.store, "memory")

    def test_status_never_prints_token(self):
        # Seed a token via login, then read it back through a shared store.
        store = resolve_store("memory")
        state = AuthState(base_url="http://x/api", store=store)
        state.set_tokens("access-1", "refresh-1")
        ProfileRegistry().upsert(
            StoredProfile(profile="default", api_url="http://x/api", username="u", store="memory")
        )
        # Point status' store resolution at this instance.
        with patch.object(cli, "resolve_store", lambda _=None: store):
            code, out, _ = self._run(["status", "--profile", "default"])
        self.assertEqual(code, 0)
        self.assertIn("refresh token present", out)
        self.assertNotIn("refresh-1", out)
        self.assertNotIn("access-1", out)

    def test_logout_clears_profile_and_token(self):
        store = MemoryStore()
        state = AuthState(base_url="http://example.test/api", store=store)
        state.set_tokens("access-1", "refresh-1")
        ProfileRegistry().upsert(
            StoredProfile(
                profile="default", api_url="http://example.test/api", username="u", store="memory"
            )
        )
        with patch.object(cli, "resolve_store", lambda _=None: store):
            code, out, _ = self._run(["logout", "--profile", "default"])
        self.assertEqual(code, 0)
        self.assertIsNone(store.get_refresh_token(store_key("http://example.test/api", "default")))
        self.assertIsNone(ProfileRegistry().get("default"))

    def test_profiles_lists_saved(self):
        self._run(["login", "--api-url", "http://x/api", "--username", "u", "--password", "p", "--store", "memory"])
        code, out, _ = self._run(["profiles"])
        self.assertEqual(code, 0)
        self.assertIn("default", out)
        self.assertIn("http://x/api", out)


if __name__ == "__main__":
    unittest.main()
