"""Dataset upload tool handler (MCP host local files only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from geopack_sdk import GeopackClient

from ..sanitize.task_results import sanitize_async_task_start
from ..serialize import to_jsonable

_DEFAULT_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MiB


def validate_upload_file_path(
    file_path: str,
    *,
    upload_root: Optional[str] = None,
    max_bytes: Optional[int] = None,
) -> Path:
    """Ensure file_path is a safe local file on the MCP host."""
    if not file_path or not str(file_path).strip():
        raise ValueError("file_path is required")

    raw = str(file_path).strip()
    if "://" in raw:
        raise ValueError("file_path must be a local path on the MCP host, not a URL")

    path = Path(raw)
    if ".." in path.parts:
        raise ValueError("file_path must not contain '..' path segments")

    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"file_path is not a readable file: {resolved}")

    if upload_root:
        root = Path(upload_root).resolve()
        if not root.is_dir():
            raise ValueError(f"GEOPACK_MCP_UPLOAD_ROOT is not a directory: {root}")
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"file_path must be under GEOPACK_MCP_UPLOAD_ROOT ({root})"
            ) from exc

    limit = max_bytes
    if limit is None:
        env_limit = os.getenv("GEOPACK_MCP_MAX_UPLOAD_BYTES", "").strip()
        if env_limit:
            limit = int(env_limit)
        else:
            limit = _DEFAULT_MAX_UPLOAD_BYTES

    size = resolved.stat().st_size
    if size > limit:
        raise ValueError(
            f"file size {size} bytes exceeds GEOPACK_MCP_MAX_UPLOAD_BYTES ({limit})"
        )

    return resolved


def upload_dataset(
    client: GeopackClient,
    file_path: str,
    data_store_id: int,
    workgroup_id: int,
    *,
    declared_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Start dataset:upload without blocking MCP stdio."""
    resolved = validate_upload_file_path(
        file_path,
        upload_root=os.getenv("GEOPACK_MCP_UPLOAD_ROOT") or None,
    )

    task = client.datasets.upload(
        str(resolved),
        data_store_id,
        workgroup_id,
        declared_type=declared_type,
        metadata=metadata,
        wait=False,
    )

    out = sanitize_async_task_start(to_jsonable(task))
    out["fileName"] = resolved.name
    out["dataStoreId"] = data_store_id
    out["workgroupId"] = workgroup_id
    if declared_type:
        out["declaredType"] = declared_type
    if metadata and metadata.get("name"):
        out["datasetName"] = metadata["name"]
    return out
