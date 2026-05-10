from typing import Any, Dict, List, Optional


class WorkgroupManager:
    """Manages Workgroup resources via the Geopack REST API.

    Endpoints:
        GET    /workgroups        — List workgroups (paginated)
        GET    /workgroups/:id    — Get by ID
    """

    def __init__(self, client):
        self.client = client

    def list(self, page: int = 1, page_size: int = 10) -> List[Dict[str, Any]]:
        """List workgroups the user has access to.

        REST API: `GET /api/workgroups`

        Returns:
            List of workgroup objects extracted from the response.
        """
        params = {"page": page, "pageSize": page_size}
        response = self.client.get("/workgroups", params=params)
        # Handle wrapping if API returns { workgroups: [...], totalItems: ... }
        if isinstance(response, dict) and "workgroups" in response:
            return response["workgroups"]
        return response

    def get(self, workgroup_id: int) -> Dict[str, Any]:
        """Get a single workgroup by ID.

        REST API: `GET /api/workgroups/:id`
        """
        return self.client.get(f"/workgroups/{workgroup_id}")


class GroupManager:
    """Manages User Group resources via the Geopack REST API.

    Endpoints:
        GET    /groups        — List groups
        GET    /groups/:id    — Get by ID
    """

    def __init__(self, client):
        self.client = client

    def list(self) -> List[Dict[str, Any]]:
        """List all groups.

        REST API: `GET /api/groups`
        """
        response = self.client.get("/groups")
        if isinstance(response, dict) and "groups" in response:
            return response["groups"]
        return response

    def get(self, group_id: int) -> Dict[str, Any]:
        """Get a single group by ID.

        REST API: `GET /api/groups/{id}`
        """
        return self.client.get(f"/groups/{group_id}")


class UserManager:
    """Manages User resources via the Geopack REST API.

    Endpoints:
        GET    /users        — List users
        GET    /users/:id    — Get by ID
        GET    /users/me     — Current user profile
    """

    def __init__(self, client):
        self.client = client

    def list(self) -> List[Dict[str, Any]]:
        """List users.

        REST API: `GET /api/users`
        """
        response = self.client.get("/users")
        if isinstance(response, dict) and "users" in response:
            return response["users"]
        return response

    def get(self, user_id: int) -> Dict[str, Any]:
        """Get a single user by ID.

        REST API: `GET /api/users/{id}`
        """
        return self.client.get(f"/users/{user_id}")

    def me(self) -> Dict[str, Any]:
        """Get current authenticated user profile.

        REST API: `GET /api/users/me`
        """
        return self.client.get("/users/me")


class OrganizationManager:
    """Manages Organization resources via the Geopack REST API.

    Endpoints:
        GET    /organizations        — List organizations
        GET    /organizations/:id    — Get by ID
    """

    def __init__(self, client):
        self.client = client

    def list(self) -> List[Dict[str, Any]]:
        """List all organizations.

        REST API: `GET /api/organizations`
        """
        response = self.client.get("/organizations")
        if isinstance(response, dict) and "organizations" in response:
            return response["organizations"]
        return response

    def get(self, org_id: int) -> Dict[str, Any]:
        """Get a single organization by ID.

        REST API: `GET /api/organizations/{id}`
        """
        return self.client.get(f"/organizations/{org_id}")
