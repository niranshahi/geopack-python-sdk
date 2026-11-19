"""Async analysis tool manager — mirrors :mod:`geopack_sdk.analysis_tools`."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

# The refusal translation and polling constants live beside the sync manager on
# purpose: both lanes must raise the SAME exceptions for the same server answer.
from .analysis_tools import (
    _POLL_BACKOFF,
    _POLL_FLOOR_S,
    _POLL_MAX_S,
    TERMINAL_RUN_STATUSES,
    _manifest_refusal,
    _surface_unavailable,
)
from .exceptions import AnalysisTimeout, GeopackAPIError
from .models import (
    AnalysisResult,
    AnalysisTool,
    AnalysisToolListResponse,
    WorkflowRunSubmitResponse,
)

if TYPE_CHECKING:
    from .async_client import AsyncGeopackClient


class AsyncAnalysisToolManager:
    """Async peer of :class:`~geopack_sdk.analysis_tools.AnalysisToolManager`."""

    def __init__(self, client: "AsyncGeopackClient"):
        self.client = client
        self.base_url = "/workflows"
        self.runs_url = "/workflow-runs"

    async def list(
        self,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AnalysisToolListResponse:
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["q"] = search
        if tag:
            params["tag"] = tag

        url = f"{self.base_url}/tools"
        try:
            data = await self.client.get(url, params=params)
        except GeopackAPIError as exc:
            if exc.status_code == 404:
                raise _surface_unavailable(exc, url) from exc
            raise
        return AnalysisToolListResponse(**(data or {}))

    async def get(self, tool_id: int) -> AnalysisTool:
        url = f"{self.base_url}/{tool_id}/tool-manifest"
        try:
            data = await self.client.get(url)
        except GeopackAPIError as exc:
            translated = _manifest_refusal(exc, tool_id)
            if translated is exc:
                raise
            raise translated from exc
        return AnalysisTool(**(data or {}))

    async def run(
        self,
        tool_id: int,
        params: Optional[Dict[str, Any]] = None,
        *,
        wait: bool = True,
        timeout_s: float = 900.0,
        poll_interval_s: Optional[float] = None,
        override_datastore_id: Optional[int] = None,
    ) -> Union[AnalysisResult, WorkflowRunSubmitResponse]:
        payload: Dict[str, Any] = {"workflowId": tool_id, "params": params or {}}
        if override_datastore_id is not None:
            payload["overrideDataStoreId"] = override_datastore_id

        # Attribution (030 §2) comes from the client-level default header set by
        # the MCP bootstrap — one source of truth (slice 016 §1.1).
        response = await self.client.post(self.runs_url, json=payload)
        submission = WorkflowRunSubmitResponse(**(response or {}))
        if not wait:
            return submission
        return await self.wait_for_result(
            submission.workflowRunId,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )

    async def wait_for_result(
        self,
        run_id: int,
        *,
        timeout_s: float = 900.0,
        poll_interval_s: Optional[float] = None,
    ) -> AnalysisResult:
        deadline = time.monotonic() + timeout_s
        delay = _POLL_FLOOR_S if poll_interval_s is None else max(
            _POLL_FLOOR_S, float(poll_interval_s)
        )

        while True:
            data = await self.client.get(f"{self.runs_url}/{run_id}") or {}
            status = data.get("status")
            if status in TERMINAL_RUN_STATUSES:
                return await self.result(run_id)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AnalysisTimeout(
                    f"Run {run_id} is still '{status}' after {timeout_s:g}s. "
                    "The run keeps going: read it with get_analysis_result.",
                    run_id=run_id,
                    timeout=timeout_s,
                )
            await asyncio.sleep(min(delay, remaining))
            delay = min(delay * _POLL_BACKOFF, _POLL_MAX_S)

    async def result(self, run_id: int) -> AnalysisResult:
        data = await self.client.get(f"{self.runs_url}/{run_id}/result-summary")
        return AnalysisResult(**(data or {}))
