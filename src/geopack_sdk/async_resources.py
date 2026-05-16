"""Async IAM resource managers (list / me)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from .models import GroupListResponse, OrganizationListResponse, UserResponse, WorkgroupListResponse
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


class AsyncGroupManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def list(self) -> GroupListResponse:
        """List groups. REST API returns a bare array (no pagination)."""
        response_data = await self.client.get("/groups")
        return parse_group_list_response(response_data)


class AsyncUserManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def me(self) -> UserResponse:
        response_data = await self.client.get("/users/me")
        return UserResponse(**response_data)


class AsyncOrganizationManager:
    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client

    async def list(self) -> OrganizationListResponse:
        """List organizations. REST API returns a bare array (no pagination)."""
        response_data = await self.client.get("/organizations")
        return parse_organization_list_response(response_data)
