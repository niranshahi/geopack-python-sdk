"""Generated file tool handlers."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from geopack_sdk import GeopackClient

from ..sanitize.task_results import generated_file_download_path

FILE_DEFAULT_LIMIT = 20
FILE_MAX_LIMIT = 100


def _file_row(item: Any) -> Dict[str, Any]:
    row = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
    entry: Dict[str, Any] = {
        "id": row.get("id"),
        "name": row.get("fileName"),
        "sizeBytes": row.get("fileSize"),
    }
    for key in ("createdAt", "expiresAt", "taskId", "sharingPolicy"):
        if row.get(key) is not None:
            entry[key] = row[key]
    return entry


def list_generated_files(
    client: GeopackClient,
    *,
    limit: int = FILE_DEFAULT_LIMIT,
    offset: int = 0,
) -> Dict[str, Any]:
    """List downloadable files; the model then calls download_generated_file.

    The portal pages by ``page``/``pageSize`` only, so an unaligned ``offset``
    fetches one extra page and slices the window — the caller still gets the
    rows it asked for.
    """
    page_size = max(1, min(int(limit), FILE_MAX_LIMIT))
    effective_offset = max(0, int(offset))
    page = effective_offset // page_size + 1
    start = effective_offset % page_size

    response = client.generated_files.list(page=page, page_size=page_size)
    rows: List[Any] = list(response.items)
    if start and len(rows) == page_size:
        rows += list(client.generated_files.list(page=page + 1, page_size=page_size).items)
    rows = rows[start : start + page_size]

    items = [_file_row(item) for item in rows]
    total = getattr(response, "totalItems", 0) or len(items)
    return {
        "items": items,
        "totalItems": total,
        "currentPage": page,
        "totalPages": max(1, -(-total // page_size)),
        "pageSize": page_size,
        "hint": "Pass one of these ids to geopack_sdk_download_generated_file.",
    }


def download_generated_file(
    client: GeopackClient,
    generated_file_id: int,
    save_path: str,
) -> Dict[str, Any]:
    """
    Stream a generated file to disk using MCP server session auth (not in tool JSON).
    """
    resolved_path = os.path.abspath(
        client.generated_files.download(generated_file_id, save_path)
    )
    return {
        "generatedFileId": generated_file_id,
        "savedPath": resolved_path,
        "downloadApiPath": generated_file_download_path(generated_file_id),
    }


def delete_generated_file(
    client: GeopackClient,
    generated_file_id: int,
) -> Dict[str, Any]:
    """
    Delete a generated file record and its storage.
    
    REST API: `DELETE /api/generated-files/{id}`
    """
    client.generated_files.delete(generated_file_id)
    return {
        "success": True,
        "message": f"Generated file #{generated_file_id} deleted successfully.",
        "generatedFileId": generated_file_id,
    }
