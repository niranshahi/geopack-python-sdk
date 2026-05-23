import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .auth import AuthManager
from .datastores import DataStoreManager
from .datasets import DatasetManager
from .tasks import TaskManager
from .workflows import WorkflowManager
from .workflow_runs import WorkflowRunManager
from .generated_files import GeneratedFileManager
from .quotas import QuotaManager
from .resources import WorkgroupManager, GroupManager, UserManager, OrganizationManager
from .exceptions import GeopackAPIError, GeopackAuthError, GeopackError, GeopackTimeoutError

# Default transport retries for transient gateway / overload responses
_DEFAULT_RETRY_TOTAL = 3
_DEFAULT_RETRY_BACKOFF_FACTOR = 0.5
_DEFAULT_RETRY_STATUS_CODES = (502, 503, 504)
_RETRY_ALLOWED_METHODS = frozenset(
    ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)


def _attach_retry_adapter(
    session: requests.Session,
    *,
    total: int,
    backoff_factor: float,
    status_forcelist: tuple,
) -> None:
    """Mount urllib3 Retry on a requests session for transient HTTP failures."""
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=_RETRY_ALLOWED_METHODS,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)


class GeopackClient:
    """
    The main entry point for the Geopack Python SDK.

    `base_url` should typically point to the REST API base, e.g.:
    - http://localhost:3000/api
    - https://your-domain.com/api

    HTTP transport retries (urllib3) are enabled by default for connection errors
    and responses with status 502, 503, or 504. Application-level 401 refresh
    is handled separately in :meth:`_request`. Disable with ``enable_http_retries=False``.
    """
    def __init__(
        self,
        base_url: str = None,
        *,
        enable_http_retries: bool = True,
        retry_total: int = _DEFAULT_RETRY_TOTAL,
        retry_backoff_factor: float = _DEFAULT_RETRY_BACKOFF_FACTOR,
        retry_status_codes: tuple = _DEFAULT_RETRY_STATUS_CODES,
    ):
        # Priority: explicit parameter > environment variable
        self.base_url = (base_url or os.getenv("GEOPACK_API_URL", "")).rstrip('/')
        
        if not self.base_url:
            raise ValueError(
                "Geopack API base URL must be provided either as a parameter 'base_url' "
                "or via the 'GEOPACK_API_URL' environment variable (example: http://localhost:3000/api)."
            )

        self.session = requests.Session()
        if enable_http_retries:
            _attach_retry_adapter(
                self.session,
                total=retry_total,
                backoff_factor=retry_backoff_factor,
                status_forcelist=retry_status_codes,
            )
        
        # Initialize managers
        self.auth = AuthManager(self)
        self.datastores = DataStoreManager(self)
        self.datasets = DatasetManager(self)
        self.tasks = TaskManager(self)
        self.workflows = WorkflowManager(self)
        self.workflow_runs = WorkflowRunManager(self)
        self.generated_files = GeneratedFileManager(self)
        self.quotas = QuotaManager(self)
        
        # Identity and Access Management
        self.workgroups = WorkgroupManager(self)
        self.groups = GroupManager(self)
        self.users = UserManager(self)
        self.organizations = OrganizationManager(self)

    def _request(self, method, endpoint, **kwargs):
        # Sync session headers with centralized TokenRegistry
        token = getattr(self.auth, "token", None)
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.headers.pop("Authorization", None)

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if "timeout" not in kwargs:
            kwargs["timeout"] = 30

        try:

            response = self.session.request(method, url, **kwargs)
        except requests.Timeout as e:
            timeout = kwargs.get("timeout")
            raise GeopackTimeoutError(
                f"Request to {endpoint} timed out after {timeout}s",
                timeout=float(timeout) if isinstance(timeout, (int, float)) else None,
            ) from e
        except requests.RequestException as e:
            raise GeopackError(f"Network error calling {endpoint}: {e}") from e

        # Automatic token refresh
        if (
            response.status_code == 401
            and hasattr(self, "auth")
            and getattr(self.auth, "refresh_token", None)
        ):
            try:
                self.auth.refresh()
                response = self.session.request(method, url, **kwargs)
            except (GeopackAuthError, GeopackAPIError):
                raise
            except Exception:
                pass

        if not response.ok:
            raise GeopackAPIError.from_response(response)

        if response.status_code == 204 or not response.content:
            return None

        try:
            return response.json()
        except ValueError as e:
            raise GeopackError(f"Invalid JSON in response from {endpoint}") from e

    def get(self, endpoint, params=None, **kwargs):
        return self._request("GET", endpoint, params=params, **kwargs)

    def post(self, endpoint, json=None, **kwargs):
        return self._request("POST", endpoint, json=json, **kwargs)

    def put(self, endpoint, json=None, **kwargs):
        return self._request("PUT", endpoint, json=json, **kwargs)

    def delete(self, endpoint, **kwargs):
        return self._request("DELETE", endpoint, **kwargs)
