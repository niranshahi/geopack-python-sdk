import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geopack_sdk.credentials import (
    StoredCredentials,
    clear_credentials,
    load_credentials,
    save_credentials,
)


class TestCredentials(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.creds_path = Path(self._tmpdir.name) / "credentials.json"

    @patch.dict(os.environ, {"GEOPACK_CREDENTIALS_FILE": ""}, clear=False)
    def test_save_load_and_clear(self):
        with patch.dict(os.environ, {"GEOPACK_CREDENTIALS_FILE": str(self.creds_path)}):
            save_credentials(
                StoredCredentials(
                    api_url="http://localhost:3000/api",
                    access_token="access-abc",
                    refresh_token="refresh-xyz",
                    username="alice",
                )
            )
            loaded = load_credentials(api_url="http://localhost:3000/api")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.access_token, "access-abc")
            self.assertEqual(loaded.refresh_token, "refresh-xyz")
            self.assertTrue(self.creds_path.is_file())
            raw = json.loads(self.creds_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["access_token"], "access-abc")
            self.assertTrue(clear_credentials())
            self.assertFalse(self.creds_path.is_file())

    @patch.dict(os.environ, {"GEOPACK_CREDENTIALS_FILE": ""}, clear=False)
    def test_load_mismatched_api_url_returns_none(self):
        with patch.dict(os.environ, {"GEOPACK_CREDENTIALS_FILE": str(self.creds_path)}):
            save_credentials(
                StoredCredentials(
                    api_url="http://localhost:3000/api",
                    access_token="token",
                )
            )
            self.assertIsNone(load_credentials(api_url="http://other.example/api"))


if __name__ == "__main__":
    unittest.main()
