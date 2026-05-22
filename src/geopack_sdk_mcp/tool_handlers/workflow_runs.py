"""Workflow run tool handlers."""

from __future__ import annotations

import os
from typing import Any, Dict

from geopack_sdk import GeopackClient

from ..sanitize.workflow_payload import sanitize_workflow_run_for_mcp
from ..serialize import to_jsonable


def get_workflow_run(client: GeopackClient, run_id: int) -> Dict[str, Any]:
    result = client.workflow_runs.get(run_id)
    return sanitize_workflow_run_for_mcp(to_jsonable(result))


def download_workflow_artifact(
    client: GeopackClient,
    run_id: int,
    artifact_id: int,
    save_path: str,
) -> Dict[str, Any]:
    """Download a workflow artifact (output file) to local disk.
    
    Args:
        client: Authenticated GeopackClient
        run_id: ID of the workflow run
        artifact_id: ID of the artifact to download
        save_path: Local directory or file path to save to
        
    Returns:
        Dict with savedPath (resolved absolute path) and file metadata
    """
    resolved_path = os.path.abspath(
        client.workflow_runs.download_artifact(run_id, artifact_id, save_path)
    )
    return {
        "workflowRunId": run_id,
        "artifactId": artifact_id,
        "savedPath": resolved_path,
    }
