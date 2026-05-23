"""Generated file tool handlers."""

from __future__ import annotations

import os
from typing import Any, Dict

from geopack_sdk import GeopackClient

from ..sanitize.task_results import generated_file_download_path


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
