import os
from typing import Optional
from .token_registry import TokenRegistry
from .exceptions import GeopackAPIError

class AuthManager:
    def __init__(self, client):
        self.client = client
        self._registry = TokenRegistry()

    @property
    def token(self) -> Optional[str]:
        return self._registry.access_token

    @token.setter
    def token(self, value: Optional[str]) -> None:
        self._registry.access_token = value

    @property
    def refresh_token(self) -> Optional[str]:
        return self._registry.refresh_token

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        self._registry.refresh_token = value


    def login(self, username: str = None, password: str = None):
        """
        Authenticate with the Geopack REST API.

        REST API: `POST /api/auth/login`

        Priority: explicit parameters > environment variables (GEOPACK_USERNAME, GEOPACK_PASSWORD)
        """
        user = username or os.getenv("GEOPACK_USERNAME")
        pwd = password or os.getenv("GEOPACK_PASSWORD")

        if not user or not pwd:
            raise ValueError(
                "Credentials must be provided either as parameters "
                "or via 'GEOPACK_USERNAME' and 'GEOPACK_PASSWORD' environment variables."
            )

        endpoint = "/auth/login"
        # API expects 'userName' (or 'email') and 'password'
        payload = {"userName": user, "password": pwd}
        
        try:
            response = self.client.post(endpoint, json=payload)
        except GeopackAPIError as e:
            if e.details:
                print(f"Server Error Detail: {e.details}")
            raise
        
        # In Geopack v2, login returns { accessToken, refreshToken, user }
        # We'll use accessToken for the Authorization header
        self.token = response.get("accessToken") or response.get("token")
        self.refresh_token = response.get("refreshToken")
        
        if self.token:
            self.client.session.headers.update({
                "Authorization": f"Bearer {self.token}"
            })
        return response

    def logout(self):
        self.token = None
        self.refresh_token = None
        if "Authorization" in self.client.session.headers:
            del self.client.session.headers["Authorization"]

    def refresh(self):
        """
        Refresh the access token using the refresh token.
        REST API: `POST /api/auth/refresh`
        """
        if not self.refresh_token:
            raise ValueError("No refresh token available. Please login again.")
        
        endpoint = "/auth/refresh"
        payload = {"token": self.refresh_token}
        
        # We use a direct request to avoid interceptors
        url = f"{self.client.base_url}/{endpoint.lstrip('/')}"
        response = self.client.session.post(url, json=payload, timeout=30)

        if not response.ok:
            raise GeopackAPIError.from_response(response)
        data = response.json()
        
        self.token = data.get("accessToken") or data.get("token")
        self.refresh_token = data.get("refreshToken") or self.refresh_token
        
        if self.token:
            self.client.session.headers.update({
                "Authorization": f"Bearer {self.token}"
            })
        return data
