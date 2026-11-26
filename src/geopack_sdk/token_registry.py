"""Per-client thread-safe token holder (slice 034).

Historically this class was a **process-wide singleton** that implicitly shared
tokens between every client in the process. Slice 034 removes the singleton so
each :class:`~geopack_sdk.client.GeopackClient` owns independent authentication
state; sharing is now explicit by passing the same
:class:`~geopack_sdk.auth_state.AuthState` to several clients.
"""

import os
import threading
from typing import Optional


class TokenRegistry:
    """Hold one client's access/refresh tokens, thread-safely.

    Not a singleton: ``TokenRegistry()`` returns a fresh, independent instance.
    """

    def __init__(self, *, env_fallback: bool = True) -> None:
        self._lock = threading.Lock()
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._env_fallback = env_fallback

    @property
    def access_token(self) -> Optional[str]:
        with self._lock:
            return self._access_token or (
                os.getenv("GEOPACK_ACCESS_TOKEN") if self._env_fallback else None
            )

    @access_token.setter
    def access_token(self, value: Optional[str]) -> None:
        with self._lock:
            self._access_token = value

    @property
    def refresh_token(self) -> Optional[str]:
        with self._lock:
            return self._refresh_token or (
                os.getenv("GEOPACK_REFRESH_TOKEN") if self._env_fallback else None
            )

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        with self._lock:
            self._refresh_token = value

    # Raw values ignore the environment fallback — used by write-through
    # persistence so an env-provided token is never copied onto disk.
    @property
    def raw_access_token(self) -> Optional[str]:
        with self._lock:
            return self._access_token

    @property
    def raw_refresh_token(self) -> Optional[str]:
        with self._lock:
            return self._refresh_token

    def clear(self) -> None:
        with self._lock:
            self._access_token = None
            self._refresh_token = None
