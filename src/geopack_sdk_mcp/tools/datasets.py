"""MCP tool registration: datasets."""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from ..auth_bootstrap import AppContext
from ..context import get_client
from ..errors import tool_error_payload
from ..tool_handlers.datasets import (
    export_dataset,
    get_dataset,
    get_dataset_thumbnail,
    list_datasets,
    query_dataset,
)


def register(mcp: Any) -> None:
    @mcp.tool()
    def geopack_sdk_list_datasets(
        ctx: Context[ServerSession, AppContext],
        page: int = 1,
        page_size: int = 20,
        search_query: Optional[str] = None,
        details_level: str = "lite",
        data_type: Optional[str] = None,
        bbox: Optional[list] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List datasets visible to the authenticated user (paginated).

        details_level: lite (default) | standard | full.
        For spatial search use bbox from geopack_sdk_geocode_place: [west, south, east, north] WGS84.
        data_type: vector | raster. start_date/end_date: ISO YYYY-MM-DD.
        """
        try:
            return list_datasets(
                get_client(ctx),
                page=page,
                page_size=page_size,
                search_query=search_query,
                details_level=details_level,
                data_type=data_type,
                bbox=bbox,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool()
    def geopack_sdk_get_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: int,
        details_level: str = "full",
    ) -> Dict[str, Any]:
        """
        Get one dataset by numeric id.

        details_level: full (default) | standard | lite — trims heavy ``details`` (tilejson, WKT).
        """
        try:
            return get_dataset(
                get_client(ctx),
                dataset_id,
                details_level=details_level,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool()
    def geopack_sdk_query_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: int,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = 100,
        offset: int = 0,
        return_geometry: bool = True,
        out_srid: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Query dataset features (POST /datasets/{id}/query).

        Pass a FeatureQuery DSL in ``query``, or omit it and use limit/offset/return_geometry.
        Response is capped at 500 features for MCP context safety.
        """
        try:
            return query_dataset(
                get_client(ctx),
                dataset_id,
                query,
                limit=limit,
                offset=offset,
                return_geometry=return_geometry,
                out_srid=out_srid,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool()
    def geopack_sdk_get_dataset_thumbnail(
        ctx: Context[ServerSession, AppContext],
        dataset_id: int,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Download dataset preview PNG to a local path on the MCP host.

        Use when the chat host cannot render MCP resources. Default path:
        downloads/dataset_{id}_thumbnail.png (relative to MCP process cwd).
        """
        try:
            return get_dataset_thumbnail(
                get_client(ctx),
                dataset_id,
                save_path=save_path,
            )
        except Exception as exc:
            return tool_error_payload(exc)

    @mcp.tool()
    def geopack_sdk_export_dataset(
        ctx: Context[ServerSession, AppContext],
        dataset_id: int,
        format: str,
        workgroup_id: Optional[int] = None,
        sharing_policy: str = "private",
    ) -> Dict[str, Any]:
        """
        Start an async dataset export (vector or raster). Returns taskId immediately.

        Use geopack_sdk_wait_for_task, then geopack_sdk_download_generated_file.
        workgroup_id defaults to the dataset owner workgroup when omitted.
        """
        try:
            return export_dataset(
                get_client(ctx),
                dataset_id,
                format,
                workgroup_id=workgroup_id,
                sharing_policy=sharing_policy,
            )
        except Exception as exc:
            return tool_error_payload(exc)
