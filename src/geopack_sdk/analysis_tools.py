"""Analysis tools — the portal's workflow-as-tool surface (portal slice 030).

Boundary (030 §1): the portal owns the manifest and the catalog, this client owns
no derivation. Every shape read here comes straight from the server — the graph
is never parsed locally and no parameter default is invented client-side.

There is no "published as a tool" flag to filter on: a workflow is an analysis
tool for the caller exactly when they may run it, so the catalog IS the caller's
run set (ADR-0019 in the portal repo).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from .exceptions import (
    AnalysisParamError,
    AnalysisSurfaceUnavailable,
    AnalysisTimeout,
    GeopackAPIError,
)
from .models import (
    AnalysisResult,
    AnalysisTool,
    AnalysisToolListResponse,
    WorkflowRunSubmitResponse,
)

if TYPE_CHECKING:
    from .client import GeopackClient


#: Statuses after which a run will never change again.
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "failed", "canceled"})

_POLL_INITIAL_S = 1.0
_POLL_MAX_S = 5.0
_POLL_BACKOFF = 1.5
_POLL_FLOOR_S = 0.05


def _surface_unavailable(exc: GeopackAPIError, url: str) -> AnalysisSurfaceUnavailable:
    """Translate the catalog's 404 into the typed 'deploy 030' error."""
    return AnalysisSurfaceUnavailable(
        "The portal does not serve the analysis-tool surface "
        f"(GET {url} returned 404). Deploy a portal with slice 030.",
        details={"url": url},
    )


def _manifest_refusal(exc: GeopackAPIError, tool_id: int) -> GeopackAPIError:
    """Translate the manifest endpoint's refusals.

    The endpoint has exactly one 400 — the graph cannot describe itself
    (``TOOL_MANIFEST_INVALID``). 404 (no such workflow) and 403 (this caller may
    not run it) keep their HTTP identity: they are not argument problems, and
    re-labelling them would tell the caller to fix their inputs.
    """
    if exc.status_code != 400:
        return exc
    node_id = (exc.details or {}).get("nodeId")
    return AnalysisParamError(
        exc.message,
        tool_id=tool_id,
        node_id=node_id if isinstance(node_id, str) else None,
        reason=exc.message,
    )


class AnalysisToolManager:
    """Discover, run and read back the portal's analysis tools."""

    def __init__(self, client: "GeopackClient"):
        self.client = client
        self.base_url = "/workflows"
        self.runs_url = "/workflow-runs"

    def list(
        self,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AnalysisToolListResponse:
        """List the analysis tools *this caller may run*.

        REST API: ``GET /api/workflows/tools``

        Args:
            search: Free-text match over title, summary and tags.
            tag: Exact tag match.
            page: 1-based page number.
            page_size: Items per page (the server caps this at 100).

        Raises:
            AnalysisSurfaceUnavailable: the portal serves no catalog (no 030).
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["q"] = search
        if tag:
            params["tag"] = tag

        url = f"{self.base_url}/tools"
        try:
            data = self.client.get(url, params=params)
        except GeopackAPIError as exc:
            if exc.status_code == 404:
                raise _surface_unavailable(exc, url) from exc
            raise
        return AnalysisToolListResponse(**(data or {}))

    def get(self, tool_id: int) -> AnalysisTool:
        """Read one tool's full manifest: params, inputs, outputs, runtime.

        REST API: ``GET /api/workflows/:id/tool-manifest``

        Raises:
            AnalysisParamError: the workflow's graph cannot describe itself.
            GeopackAPIError: 404 when the workflow does not exist, 403 when this
                caller may not run it (a readable-but-unrunnable workflow is 403,
                never a silent 404).
        """
        url = f"{self.base_url}/{tool_id}/tool-manifest"
        try:
            data = self.client.get(url)
        except GeopackAPIError as exc:
            translated = _manifest_refusal(exc, tool_id)
            if translated is exc:
                raise
            raise translated from exc
        return AnalysisTool(**(data or {}))

    def run(
        self,
        tool_id: int,
        params: Optional[Dict[str, Any]] = None,
        *,
        wait: bool = True,
        timeout_s: float = 900.0,
        poll_interval_s: Optional[float] = None,
        override_datastore_id: Optional[int] = None,
    ) -> Union[AnalysisResult, WorkflowRunSubmitResponse]:
        """Run an analysis tool.

        REST API: ``POST /api/workflow-runs`` (+ ``GET .../result-summary`` when
        ``wait`` is true)

        Args:
            tool_id: ``toolId`` from :meth:`list`.
            params: Inputs keyed by the manifest's ``params[].key``.
            wait: When true, poll to a terminal status and return the run's
                :class:`AnalysisResult`. When false, return the submission ids
                immediately.
            timeout_s: Polling budget in seconds; the run is NOT cancelled when
                it expires (see :class:`AnalysisTimeout`).
            poll_interval_s: First polling delay; backs off 1.5x to a 5 s cap.
            override_datastore_id: Optional datastore override.

        Raises:
            AnalysisTimeout: ``wait`` exceeded ``timeout_s``; ``run_id`` is
                attached so the run can be read instead of restarted.
        """
        payload: Dict[str, Any] = {"workflowId": tool_id, "params": params or {}}
        if override_datastore_id is not None:
            payload["overrideDataStoreId"] = override_datastore_id

        # Attribution (030 §2) comes from the client-level default header set by
        # the MCP bootstrap — one source of truth (slice 016 §1.1).
        response = self.client.post(self.runs_url, json=payload)
        submission = WorkflowRunSubmitResponse(**(response or {}))
        if not wait:
            return submission
        return self.wait_for_result(
            submission.workflowRunId,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )

    def wait_for_result(
        self,
        run_id: int,
        *,
        timeout_s: float = 900.0,
        poll_interval_s: Optional[float] = None,
    ) -> AnalysisResult:
        """Poll one run to a terminal status, then read its summary.

        Reads ``GET /api/workflow-runs/:id`` directly rather than
        ``workflow_runs.get()``: the latter also probes the artifacts lane on
        every call, which is wasted work inside a polling loop.
        """
        deadline = time.monotonic() + timeout_s
        delay = _POLL_FLOOR_S if poll_interval_s is None else max(
            _POLL_FLOOR_S, float(poll_interval_s)
        )

        while True:
            data = self.client.get(f"{self.runs_url}/{run_id}") or {}
            status = data.get("status")
            if status in TERMINAL_RUN_STATUSES:
                return self.result(run_id)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AnalysisTimeout(
                    f"Run {run_id} is still '{status}' after {timeout_s:g}s. "
                    "The run keeps going: read it with get_analysis_result.",
                    run_id=run_id,
                    timeout=timeout_s,
                )
            time.sleep(min(delay, remaining))
            delay = min(delay * _POLL_BACKOFF, _POLL_MAX_S)

    def result(self, run_id: int) -> AnalysisResult:
        """Read a run's machine-readable summary.

        REST API: ``GET /api/workflow-runs/:id/result-summary``

        Metadata only — scalars, dataset names, artifact metadata, errors. The
        records themselves stay behind the artifact download lane.
        """
        data = self.client.get(f"{self.runs_url}/{run_id}/result-summary")
        return AnalysisResult(**(data or {}))
