"""Analysis-tool handlers: catalog, run, result (portal slice 030).

Every shape comes from the portal. The handler adds two things only: the
single-tool selector on the catalog call, and the sanitizer on the way out.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from geopack_sdk import GeopackClient

from ..sanitize.analysis_result import sanitize_analysis_result
from ..serialize import to_jsonable

#: Omitted from CATALOG CARDS only — an empty list here would read as "this tool
#: takes no arguments", which is exactly the wrong hint before a run.
_CARD_OMIT_IF_NONE = ("params", "inputs")


def list_analysis_tools(
    client: GeopackClient,
    *,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    tool_id: Optional[int] = None,
) -> Dict[str, Any]:
    """The caller's runnable tools, or ONE tool's full manifest.

    ``tool_id`` is a selector rather than a fourth tool: the catalog is a
    homogeneous space, so discovery + one runner beats one tool per workflow
    (ADR-0011 §3).
    """
    if tool_id is not None:
        return to_jsonable(client.analysis_tools.get(tool_id))

    payload = to_jsonable(
        client.analysis_tools.list(
            search=search,
            tag=tag,
            page=page,
            page_size=page_size,
        )
    )
    items: List[Dict[str, Any]] = payload.get("items") or []
    for item in items:
        for key in _CARD_OMIT_IF_NONE:
            if item.get(key) is None:
                item.pop(key, None)
    return payload


def run_analysis(
    client: GeopackClient,
    tool_id: int,
    params: Optional[Dict[str, Any]] = None,
    *,
    wait: bool = True,
    timeout_s: int = 900,
    poll_interval_s: Optional[float] = None,
    override_datastore_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one analysis tool and (optionally) wait for its result."""
    result = client.analysis_tools.run(
        tool_id,
        params=params or {},
        wait=wait,
        timeout_s=float(timeout_s),
        poll_interval_s=poll_interval_s,
        override_datastore_id=override_datastore_id,
    )
    return sanitize_analysis_result(to_jsonable(result))


def get_analysis_result(client: GeopackClient, run_id: int) -> Dict[str, Any]:
    """Read a run's machine-readable summary (never records or geometry)."""
    return sanitize_analysis_result(to_jsonable(client.analysis_tools.result(run_id)))
