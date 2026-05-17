"""Workflow run tool handlers."""

from __future__ import annotations

from typing import Any, Dict

from geopack_sdk import GeopackClient

from ..serialize import to_jsonable


def get_workflow_run(client: GeopackClient, run_id: int) -> Dict[str, Any]:
    result = client.workflow_runs.get(run_id)
    return to_jsonable(result)
