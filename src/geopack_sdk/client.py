import os
import requests
from .auth import AuthManager
from .datasets import DatasetManager
from .tasks import TaskManager

class GeopackClient:
    """
    The main entry point for the Geopack Python SDK.
    """
    def __init__(self, base_url: str = None):
        # Priority: explicit parameter > environment variable
        self.base_url = (base_url or os.getenv("GEOPACK_API_URL", "")).rstrip('/')
        
        if not self.base_url:
            raise ValueError(
                "Geopack API URL must be provided either as a parameter 'base_url' "
                "or via the 'GEOPACK_API_URL' environment variable."
            )

        self.session = requests.Session()
        
        # Initialize managers
        self.auth = AuthManager(self)
        self.datasets = DatasetManager(self)
        self.tasks = TaskManager(self)

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get(self, endpoint, params=None, **kwargs):
        return self._request("GET", endpoint, params=params, **kwargs)

    def post(self, endpoint, json=None, **kwargs):
        return self._request("POST", endpoint, json=json, **kwargs)

    def put(self, endpoint, json=None, **kwargs):
        return self._request("PUT", endpoint, json=json, **kwargs)

    def delete(self, endpoint, **kwargs):
        return self._request("DELETE", endpoint, **kwargs)
