"""Per-client authentication state (slice 034).

An :class:`AuthState` bundles, for a single client:

* the access/refresh tokens (:class:`~geopack_sdk.token_registry.TokenRegistry`),
* a **single-flight** refresh lock, so concurrent ``401``s trigger one refresh, and
* an optional :class:`~geopack_sdk.credentials.CredentialStore` used to
  **write through** the rotated refresh token whenever the tokens change.

It is deliberately *not* a process-wide singleton; two clients are independent
unless they are handed the same ``AuthState`` instance.

:class:`AsyncAuthState` is the async twin and uses an ``asyncio.Lock`` created
lazily inside the running event loop. The sync lock is never used on the async
path and vice-versa.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Optional

from .token_registry import TokenRegistry

if TYPE_CHECKING:  # pragma: no cover
    from .credentials import CredentialStore


def store_key(base_url: str, profile: str) -> str:
    """Composite credential key: ``<api_url>|<profile>`` (D5)."""
    return f"{(base_url or '').rstrip('/')}|{profile or 'default'}"


class AuthState:
    """Synchronous per-client authentication state."""

    def __init__(
        self,
        *,
        base_url: str = "",
        profile: str = "default",
        store: "Optional[CredentialStore]" = None,
        env_fallback: bool = True,
    ) -> None:
        self.base_url = base_url
        self.profile = profile
        self.store = store
        self._registry = TokenRegistry(env_fallback=env_fallback)
        self._refresh_lock = threading.RLock()

    # --- tokens -----------------------------------------------------------
    @property
    def access_token(self) -> Optional[str]:
        return self._registry.access_token

    @access_token.setter
    def access_token(self, value: Optional[str]) -> None:
        self._registry.access_token = value

    @property
    def refresh_token(self) -> Optional[str]:
        return self._registry.refresh_token

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        self._registry.refresh_token = value

    # --- coordination -----------------------------------------------------
    @property
    def refresh_lock(self) -> threading.RLock:
        return self._refresh_lock

    # --- storage ----------------------------------------------------------
    def _key(self) -> str:
        return store_key(self.base_url, self.profile)

    def set_tokens(
        self,
        access: Optional[str],
        refresh: Optional[str] = None,
        *,
        persist: bool = True,
    ) -> None:
        """Set tokens in memory and (by default) persist the refresh token."""
        self._registry.access_token = access
        if refresh is not None:
            self._registry.refresh_token = refresh
        if persist:
            self.persist()

    def persist(self) -> bool:
        """Write-through the in-memory refresh token to the store (D4).

        Best-effort: a missing/broken backend must never fail a login or a
        refresh (the tokens stay valid in memory for this process).
        """
        if self.store is None:
            return False
        raw = self._registry.raw_refresh_token
        if not raw:
            return False
        try:
            self.store.set_refresh_token(self._key(), raw)
            return True
        except Exception:  # noqa: BLE001 - persistence is best-effort
            return False

    def load_from_store(self) -> bool:
        """Seed the refresh token from the store. Returns True when found.

        A store error is treated as "no stored token" so callers fall back to the
        legacy file / environment credentials instead of crashing.
        """
        if self.store is None:
            return False
        try:
            token = self.store.get_refresh_token(self._key())
        except Exception:  # noqa: BLE001 - treat as absent
            return False
        if token:
            self._registry.refresh_token = token
            return True
        return False

    def clear(self, *, clear_persisted: bool = False) -> None:
        self._registry.clear()
        if clear_persisted and self.store is not None:
            try:
                self.store.delete_refresh_token(self._key())
            except Exception:  # noqa: BLE001 - deletion is best-effort
                pass


class AsyncAuthState:
    """Asynchronous per-client authentication state."""

    def __init__(
        self,
        *,
        base_url: str = "",
        profile: str = "default",
        store: "Optional[CredentialStore]" = None,
        env_fallback: bool = True,
    ) -> None:
        self.base_url = base_url
        self.profile = profile
        self.store = store
        self._registry = TokenRegistry(env_fallback=env_fallback)
        self._lock: Optional[asyncio.Lock] = None

    # --- tokens -----------------------------------------------------------
    @property
    def access_token(self) -> Optional[str]:
        return self._registry.access_token

    @access_token.setter
    def access_token(self, value: Optional[str]) -> None:
        self._registry.access_token = value

    @property
    def refresh_token(self) -> Optional[str]:
        return self._registry.refresh_token

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        self._registry.refresh_token = value

    # --- coordination -----------------------------------------------------
    def lock(self) -> asyncio.Lock:
        """Return the single-flight lock, created inside the running loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # --- storage ----------------------------------------------------------
    def _key(self) -> str:
        return store_key(self.base_url, self.profile)

    def set_tokens(
        self,
        access: Optional[str],
        refresh: Optional[str] = None,
        *,
        persist: bool = True,
    ) -> None:
        self._registry.access_token = access
        if refresh is not None:
            self._registry.refresh_token = refresh
        if persist:
            self.persist()

    def persist(self) -> bool:
        if self.store is None:
            return False
        raw = self._registry.raw_refresh_token
        if not raw:
            return False
        try:
            self.store.set_refresh_token(self._key(), raw)
            return True
        except Exception:  # noqa: BLE001 - best-effort
            return False

    def load_from_store(self) -> bool:
        if self.store is None:
            return False
        try:
            token = self.store.get_refresh_token(self._key())
        except Exception:  # noqa: BLE001 - treat as absent
            return False
        if token:
            self._registry.refresh_token = token
            return True
        return False

    def clear(self, *, clear_persisted: bool = False) -> None:
        self._registry.clear()
        if clear_persisted and self.store is not None:
            try:
                self.store.delete_refresh_token(self._key())
            except Exception:  # noqa: BLE001 - best-effort
                pass
