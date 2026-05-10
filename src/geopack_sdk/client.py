import os
import requests
from .auth import AuthManager
from .datastores import DataStoreManager
from .datasets import DatasetManager
from .tasks import TaskManager
from .resources import WorkgroupManager, GroupManager, UserManager, OrganizationManager

class GeopackClient:
    """
    The main entry point for the Geopack Python SDK.

    `base_url` should typically point to the REST API base, e.g.:
    - http://localhost:3000/api
    - https://your-domain.com/api
    """
    def __init__(self, base_url: str = None):
        # Priority: explicit parameter > environment variable
        self.base_url = (base_url or os.getenv("GEOPACK_API_URL", "")).rstrip('/')
        
        if not self.base_url:
            raise ValueError(
                "Geopack API base URL must be provided either as a parameter 'base_url' "
                "or via the 'GEOPACK_API_URL' environment variable (example: http://localhost:3000/api)."
            )

        self.session = requests.Session()
        
        # Initialize managers
        self.auth = AuthManager(self)
        self.datastores = DataStoreManager(self)
        self.datasets = DatasetManager(self)
        self.tasks = TaskManager(self)
        self.workgroups = WorkgroupManager(self)
        self.groups = GroupManager(self)
        self.users = UserManager(self)
        self.organizations = OrganizationManager(self)

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.request(method, url, **kwargs)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # Try to extract detailed error from response body
            try:
                error_data = response.json()
                msg = error_data.get("message") or error_data.get("errors") or str(error_data)
                raise Exception(f"Geopack API Error ({response.status_code}): {msg}") from e
            except (ValueError, KeyError):
                # Fallback to original HTTPError
                raise e
        return response.json()

    def get(self, endpoint, params=None, **kwargs):
        return self._request("GET", endpoint, params=params, **kwargs)

    def post(self, endpoint, json=None, **kwargs):
        return self._request("POST", endpoint, json=json, **kwargs)

    def put(self, endpoint, json=None, **kwargs):
        return self._request("PUT", endpoint, json=json, **kwargs)

    def delete(self, endpoint, **kwargs):
        return self._request("DELETE", endpoint, **kwargs)
