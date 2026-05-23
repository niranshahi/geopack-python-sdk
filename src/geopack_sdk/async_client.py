"""
Async HTTP client for the Geopack Python SDK (``httpx``).

Install with: ``pip install geopack-sdk[async]``
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

import httpx

from .async_auth import AsyncAuthManager
from .async_datastores import AsyncDataStoreManager
from .async_datasets import AsyncDatasetManager
from .async_generated_files import AsyncGeneratedFileManager
from .async_quotas import AsyncQuotaManager
from .async_resources import (
    AsyncGroupManager,
    AsyncOrganizationManager,
    AsyncUserManager,
    AsyncWorkgroupManager,
)
from .async_tasks import AsyncTaskManager
from .async_workflow_runs import AsyncWorkflowRunManager
from .async_workflows import AsyncWorkflowManager
from .exceptions import GeopackAPIError, GeopackAuthError, GeopackError, GeopackTimeoutError

_DEFAULT_RETRY_TOTAL = 3
_DEFAULT_RETRY_BACKOFF_FACTOR = 0.5
_DEFAULT_RETRY_STATUS_CODES = frozenset({502, 503, 504})
_DEFAULT_TIMEOUT = 30.0


class AsyncGeopackClient:
    """
    The async entry point for the Geopack Python SDK.

  Uses :class:`httpx.AsyncClient` for non-blocking I/O. Mirrors
  :class:`~geopack_sdk.client.GeopackClient` for JSON REST calls; multipart
  uploads and large streaming downloads remain on the sync client for now.

  Example::

      import asyncio
      from geopack_sdk import AsyncGeopackClient

      async def main():
          async with AsyncGeopackClient() as client:
              await client.auth.login()
              summary = await client.tasks.summary()
              tasks = await client.tasks.wait_for_tasks(
                  ["task-a", "task-b"], timeout=120
              )

      asyncio.run(main())
    """

    def __init__(
        self,
        base_url: str = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        enable_http_retries: bool = True,
        retry_total: int = _DEFAULT_RETRY_TOTAL,
        retry_backoff_factor: float = _DEFAULT_RETRY_BACKOFF_FACTOR,
        retry_status_codes: frozenset = _DEFAULT_RETRY_STATUS_CODES,
    ):
        self.base_url = (base_url or os.getenv("GEOPACK_API_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError(
                "Geopack API base URL must be provided either as 'base_url' "
                "or via GEOPACK_API_URL (example: http://localhost:3000/api)."
            )

        self._timeout = timeout
        self._enable_http_retries = enable_http_retries
        self._retry_total = retry_total
        self._retry_backoff_factor = retry_backoff_factor
        self._retry_status_codes = retry_status_codes

        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

        self.auth = AsyncAuthManager(self)
        self.datastores = AsyncDataStoreManager(self)
        self.datasets = AsyncDatasetManager(self)
        self.tasks = AsyncTaskManager(self)
        self.workflows = AsyncWorkflowManager(self)
        self.workflow_runs = AsyncWorkflowRunManager(self)
        self.generated_files = AsyncGeneratedFileManager(self)
        self.quotas = AsyncQuotaManager(self)
        self.workgroups = AsyncWorkgroupManager(self)
        self.groups = AsyncGroupManager(self)
        self.users = AsyncUserManager(self)
        self.organizations = AsyncOrganizationManager(self)

    @property
    def session(self) -> httpx.AsyncClient:
        """Underlying ``httpx`` client (e.g. for custom headers)."""
        return self._client

    async def __aenter__(self) -> "AsyncGeopackClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        # Sync session headers with centralized TokenRegistry
        token = getattr(self.auth, "token", None)
        if token:
            self._client.headers["Authorization"] = f"Bearer {token}"
        else:
            self._client.headers.pop("Authorization", None)

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        attempts = self._retry_total + 1 if self._enable_http_retries else 1


        last_response: Optional[httpx.Response] = None
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, url, **kwargs)
            except httpx.TimeoutException as e:
                raise GeopackTimeoutError(
                    f"Request to {endpoint} timed out after {self._timeout}s",
                    timeout=self._timeout,
                ) from e
            except httpx.HTTPError as e:
                raise GeopackError(f"Network error calling {endpoint}: {e}") from e

            last_response = response

            if (
                self._enable_http_retries
                and response.status_code in self._retry_status_codes
                and attempt < attempts - 1
            ):
                delay = self._retry_backoff_factor * (2**attempt)
                await asyncio.sleep(delay)
                continue

            break

        assert last_response is not None

        if (
            last_response.status_code == 401
            and getattr(self.auth, "refresh_token", None)
        ):
            try:
                await self.auth.refresh()
                last_response = await self._client.request(method, url, **kwargs)
            except (GeopackAuthError, GeopackAPIError):
                raise
            except Exception:
                pass

        if not last_response.is_success:
            raise GeopackAPIError.from_httpx_response(last_response)

        if last_response.status_code == 204 or not last_response.content:
            return None

        try:
            return last_response.json()
        except ValueError as e:
            raise GeopackError(f"Invalid JSON in response from {endpoint}") from e

    async def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> Any:
        return await self._request("GET", endpoint, params=params, **kwargs)

    async def post(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        return await self._request("POST", endpoint, json=json, **kwargs)

    async def put(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        return await self._request("PUT", endpoint, json=json, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> Any:
        return await self._request("DELETE", endpoint, **kwargs)
