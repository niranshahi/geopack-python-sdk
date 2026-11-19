"""Async IAM resource managers (list / me)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from .models import (
    GroupListResponse,
    GroupResponse,
    OrganizationListResponse,
    OrganizationResponse,
    UserListResponse,
    UserResponse,
    WorkgroupListResponse,
    WorkgroupResponse,
)
from .resources import parse_group_list_response, parse_organization_list_response

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncWorkgroupManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        search_query: Optional[str] = None,
    ) -> WorkgroupListResponse:
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if search_query:
            params["searchQuery"] = search_query.strip()
        response_data = await self.client.get("/workgroups", params=params)
        return WorkgroupListResponse(**response_data)

    async def get(self, workgroup_id: int) -> WorkgroupResponse:
        """Async twin of :meth:`WorkgroupManager.get`."""
        response_data = await self.client.get(f"/workgroups/{workgroup_id}")
        return WorkgroupResponse(**response_data)


class AsyncGroupManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def list(self) -> GroupListResponse:
        """List groups. REST API returns a bare array (no pagination)."""
        response_data = await self.client.get("/groups")
        return parse_group_list_response(response_data)

    async def get(self, group_id: int) -> GroupResponse:
        """Async twin of :meth:`GroupManager.get`."""
        response_data = await self.client.get(f"/groups/{group_id}")
        return GroupResponse(**response_data)


class AsyncUserManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def me(self) -> UserResponse:
        response_data = await self.client.get("/users/me")
        return UserResponse(**response_data)

    async def list(self) -> UserListResponse:
        """Async twin of :meth:`UserManager.list`."""
        response_data = await self.client.get("/users")
        return UserListResponse(**response_data)

    async def get(self, user_id: int) -> UserResponse:
        """Async twin of :meth:`UserManager.get`."""
        response_data = await self.client.get(f"/users/{user_id}")
        return UserResponse(**response_data)


class AsyncOrganizationManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def list(self) -> OrganizationListResponse:
        """List organizations. REST API returns a bare array (no pagination)."""
        response_data = await self.client.get("/organizations")
        return parse_organization_list_response(response_data)

    async def get(self, org_id: int) -> OrganizationResponse:
        """Async twin of :meth:`OrganizationManager.get`."""
        response_data = await self.client.get(f"/organizations/{org_id}")
        return OrganizationResponse(**response_data)
