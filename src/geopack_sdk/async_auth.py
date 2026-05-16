"""JWT authentication for :class:`~geopack_sdk.async_client.AsyncGeopackClient`."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, Optional

from .exceptions import GeopackAPIError

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncAuthManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None

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

        self.token = response.get("accessToken") or response.get("token")
        self.refresh_token = response.get("refreshToken")

        if self.token:
            self.client.session.headers["Authorization"] = f"Bearer {self.token}"
        return response

    def logout(self) -> None:
        self.token = None
        self.refresh_token = None
        self.client.session.headers.pop("Authorization", None)

    async def refresh(self) -> Dict[str, Any]:
        """Refresh the access token. REST API: ``POST /api/auth/refresh``."""
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
        self.token = data.get("accessToken") or data.get("token")
        self.refresh_token = data.get("refreshToken") or self.refresh_token

        if self.token:
            self.client.session.headers["Authorization"] = f"Bearer {self.token}"
        return data
