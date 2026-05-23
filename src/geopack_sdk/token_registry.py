import os
import threading
from typing import Optional

class TokenRegistry:
    """A centralized thread-safe token registry for sharing access/refresh token states.
    
    Can be used to share tokens between synchronous and asynchronous clients,
    and supports automatic loading from environment variables.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(TokenRegistry, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._lock = threading.Lock()
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._initialized = True

    @property
    def access_token(self) -> Optional[str]:
        with self._lock:
            return self._access_token or os.getenv("GEOPACK_ACCESS_TOKEN")

    @access_token.setter
    def access_token(self, value: Optional[str]) -> None:
        with self._lock:
            self._access_token = value

    @property
    def refresh_token(self) -> Optional[str]:
        with self._lock:
            return self._refresh_token or os.getenv("GEOPACK_REFRESH_TOKEN")

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        with self._lock:
            self._refresh_token = value

    def clear(self) -> None:
        with self._lock:
            self._access_token = None
            self._refresh_token = None
