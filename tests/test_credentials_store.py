"""Credential stores, profile registry and write-through persistence (slice 034)."""

import os
import tempfile
import unittest
from pathlib import Path

from geopack_sdk.auth_state import AuthState, store_key
from geopack_sdk.credentials import (
    CredentialStoreError,
    FileStore,
    MemoryStore,
    ProfileRegistry,
    StoredProfile,
    resolve_store,
)


class TestMemoryStore(unittest.TestCase):
    def test_roundtrip(self):
        store = MemoryStore()
        self.assertIsNone(store.get_refresh_token("k"))
        store.set_refresh_token("k", "t")
        self.assertEqual(store.get_refresh_token("k"), "t")
        store.delete_refresh_token("k")
        self.assertIsNone(store.get_refresh_token("k"))


class TestFileStore(unittest.TestCase):
    def test_roundtrip_is_isolated_per_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tokens.json"
            store = FileStore(path)
            store.set_refresh_token("a|default", "tok1")
            store.set_refresh_token("b|default", "tok2")
            self.assertEqual(FileStore(path).get_refresh_token("a|default"), "tok1")
            store.delete_refresh_token("a|default")
            self.assertIsNone(FileStore(path).get_refresh_token("a|default"))
            self.assertEqual(FileStore(path).get_refresh_token("b|default"), "tok2")


class TestProfileRegistry(unittest.TestCase):
    def test_upsert_get_remove(self):
        with tempfile.TemporaryDirectory() as d:
            registry = ProfileRegistry(Path(d) / "profiles.json")
            registry.upsert(
                StoredProfile(profile="default", api_url="http://x/api", username="u", store="file")
            )
            got = registry.get("default")
            self.assertIsNotNone(got)
            self.assertEqual(got.api_url, "http://x/api")
            self.assertTrue(registry.remove("default"))
            self.assertIsNone(registry.get("default"))


class TestStoreSelection(unittest.TestCase):
    def test_memory_and_file_are_explicit(self):
        self.assertEqual(resolve_store("memory").name, "memory")
        self.assertEqual(resolve_store("file").name, "file")

    def test_unknown_store_raises(self):
        with self.assertRaises(CredentialStoreError):
            resolve_store("bogus")

    def test_env_selects_file(self):
        os.environ["GEOPACK_CREDENTIAL_STORE"] = "file"
        try:
            self.assertEqual(resolve_store().name, "file")
        finally:
            del os.environ["GEOPACK_CREDENTIAL_STORE"]


class TestStoreKey(unittest.TestCase):
    def test_composite_key_normalizes_trailing_slash(self):
        self.assertEqual(store_key("http://x/api/", "default"), "http://x/api|default")


class TestWriteThrough(unittest.TestCase):
    def test_set_tokens_persists_refresh(self):
        store = MemoryStore()
        state = AuthState(base_url="http://x/api", store=store)
        state.set_tokens("access", "refresh")
        self.assertEqual(
            store.get_refresh_token(store_key("http://x/api", "default")), "refresh"
        )

    def test_env_token_is_not_persisted(self):
        store = MemoryStore()
        with_unused = AuthState(base_url="http://x/api", store=store, env_fallback=True)
        # Only the in-memory token is persisted; nothing was set here.
        with_unused.persist()
        self.assertIsNone(store.get_refresh_token(store_key("http://x/api", "default")))

    def test_clear_persisted_removes_token(self):
        store = MemoryStore()
        state = AuthState(base_url="http://x/api", store=store)
        state.set_tokens("access", "refresh")
        state.clear(clear_persisted=True)
        self.assertIsNone(store.get_refresh_token(store_key("http://x/api", "default")))


if __name__ == "__main__":
    unittest.main()
