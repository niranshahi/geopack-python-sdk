"""JWT authentication for :class:`~geopack_sdk.async_client.AsyncGeopackClient`."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, Optional

from .exceptions import GeopackAPIError

from .auth_state import AsyncAuthState

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncAuthManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client
        state = getattr(client, "auth_state", None)
        if not isinstance(state, AsyncAuthState):
            state = AsyncAuthState(
                base_url=getattr(client, "base_url", "") or "",
                profile=getattr(client, "auth_profile", "default") or "default",
                store=getattr(client, "credential_store", None),
            )
            try:
                client.auth_state = state
            except Exception:
                pass
        self._state = state

    @property
    def _registry(self):
        """Backward-compatible accessor for the underlying token registry."""
        return self._state._registry

    @property
    def token(self) -> Optional[str]:
        return self._state.access_token

    @token.setter
    def token(self, value: Optional[str]) -> None:
        self._state.access_token = value

    @property
    def refresh_token(self) -> Optional[str]:
        return self._state.refresh_token

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        self._state.refresh_token = value

    async def login(self, username: str = None, password: str = None) -> Dict[str, Any]:
        """
        Authenticate with the Geopack REST API.

        REST API: ``POST /api/auth/login``
        """
        user = username or os.getenv("GEOPACK_USERNAME")
        pwd = password or os.getenv("GEOPACK_PASSWORD")

        if not user or not pwd:
            raise ValueError(
                "Credentials must be provided as parameters or via "
                "GEOPACK_USERNAME and GEOPACK_PASSWORD."
            )

        payload = {"userName": user, "password": pwd}
        response = await self.client.post("/auth/login", json=payload)

        self._state.set_tokens(
            response.get("accessToken") or response.get("token"),
            response.get("refreshToken"),
        )

        if self.token:
            self.client.session.headers["Authorization"] = f"Bearer {self.token}"
        return response

    def logout(self) -> None:
        self.token = None
        self.refresh_token = None
        self.client.session.headers.pop("Authorization", None)

    async def refresh(self, stale_token: Optional[str] = None) -> Dict[str, Any]:
        """Refresh the access token. REST API: ``POST /api/auth/refresh``.

        Single-flight (slice 034): serialized on the state's asyncio lock; a
        caller whose token was already rotated while waiting skips the refresh.
        """
        async with self._state.lock():
            if (
                stale_token is not None
                and self.token
                and self.token != stale_token
            ):
                return {"accessToken": self.token, "refreshToken": self.refresh_token}

            if not self.refresh_token:
                raise ValueError("No refresh token available. Please login again.")

            url = f"{self.client.base_url}/auth/refresh"
            response = await self.client.session.post(
                url,
                json={"token": self.refresh_token},
                timeout=self.client._timeout,
            )

            if not response.is_success:
                raise GeopackAPIError.from_httpx_response(response)

            data = response.json()
            self._state.set_tokens(
                data.get("accessToken") or data.get("token"),
                data.get("refreshToken") or self.refresh_token,
            )

            if self.token:
                self.client.session.headers["Authorization"] = f"Bearer {self.token}"
            return data
