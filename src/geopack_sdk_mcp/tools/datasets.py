"""MCP tool registration: datasets."""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.datasets import get_dataset, list_datasets


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_list_datasets(
        ctx: Context[ServerSession, AppContext],
        page: int = 1,
        page_size: int = 20,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List datasets visible to the authenticated user (paginated)."""
        try:
            return list_datasets(
                get_client(ctx),
                page=page,
                page_size=page_size,
                search_query=search_query,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool()
    def geopack_sdk_get_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: int,
    ) -> Dict[str, Any]:
        """Get one dataset by numeric id."""
        try:
            return get_dataset(get_client(ctx), dataset_id)
        except Exception as exc:
            return tool_error_payload(exc)
