from typing import Any, Dict, List, Optional
from .models import (
    WorkgroupResponse,
    WorkgroupListResponse,
    UserResponse,
    UserListResponse,
    OrganizationResponse,
    OrganizationListResponse,
    GroupResponse,
    GroupListResponse,
)


class WorkgroupManager:
    """Manages Workgroup resources via the Geopack REST API.

    Endpoints:
        GET    /workgroups        — List workgroups (paginated)
        GET    /workgroups/:id    — Get by ID
    """

    def __init__(self, client):
        self.client = client

    def list(self, page: int = 1, page_size: int = 10) -> WorkgroupListResponse:
        """List workgroups the user has access to.

        REST API: `GET /api/workgroups`

        Returns:
            WorkgroupListResponse: Validated response with workgroups array and pagination info.
        """
        params = {"page": page, "pageSize": page_size}
        response_data = self.client.get("/workgroups", params=params)
        return WorkgroupListResponse(**response_data)

    def get(self, workgroup_id: int) -> WorkgroupResponse:
        """Get a single workgroup by ID with type-safe response.

        REST API: `GET /api/workgroups/:id`
        """
        response_data = self.client.get(f"/workgroups/{workgroup_id}")
        return WorkgroupResponse(**response_data)


class GroupManager:
    """Manages User Group resources via the Geopack REST API.

    Endpoints:
        GET    /groups        — List groups
        GET    /groups/:id    — Get by ID
    """

    def __init__(self, client):
        self.client = client

    def list(self) -> GroupListResponse:
        """List all groups with type-safe response.

        REST API: `GET /api/groups`
        """
        response_data = self.client.get("/groups")
        return GroupListResponse(**response_data)

    def get(self, group_id: int) -> GroupResponse:
        """Get a single group by ID with type-safe response.

        REST API: `GET /api/groups/{id}`
        """
        response_data = self.client.get(f"/groups/{group_id}")
        return GroupResponse(**response_data)


class UserManager:
    """Manages User resources via the Geopack REST API.

    Endpoints:
        GET    /users        — List users
        GET    /users/:id    — Get by ID
        GET    /users/me     — Current user profile
    """

    def __init__(self, client):
        self.client = client

    def list(self) -> UserListResponse:
        """List users with type-safe response.

        REST API: `GET /api/users`
        """
        response_data = self.client.get("/users")
        return UserListResponse(**response_data)

    def get(self, user_id: int) -> UserResponse:
        """Get a single user by ID with type-safe response.

        REST API: `GET /api/users/{id}`
        """
        response_data = self.client.get(f"/users/{user_id}")
        return UserResponse(**response_data)

    def me(self) -> UserResponse:
        """Get current authenticated user profile with type-safe response.

        REST API: `GET /api/users/me`
        """
        response_data = self.client.get("/users/me")
        return UserResponse(**response_data)


class OrganizationManager:
    """Manages Organization resources via the Geopack REST API.

    Endpoints:
        GET    /organizations        — List organizations
        GET    /organizations/:id    — Get by ID
    """

    def __init__(self, client):
        self.client = client

    def list(self) -> OrganizationListResponse:
        """List all organizations with type-safe response.

        REST API: `GET /api/organizations`
        """
        response_data = self.client.get("/organizations")
        return OrganizationListResponse(**response_data)

    def get(self, org_id: int) -> OrganizationResponse:
        """Get a single organization by ID with type-safe response.

        REST API: `GET /api/organizations/{id}`
        """
        response_data = self.client.get(f"/organizations/{org_id}")
        return OrganizationResponse(**response_data)
