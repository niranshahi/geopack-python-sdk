from .client import GeopackClient
from .exceptions import (
    GeopackAPIError,
    GeopackAuthError,
    GeopackError,
    GeopackTaskError,
    GeopackTimeoutError,
    GeopackValidationError,
)
from .tasks import (
    TaskMessageInfo,
    task_log_entries_needing_review,
    task_may_have_hidden_issues,
    task_message_badge_severity,
    task_message_info,
)
from .workflow_runs import inspect_workflow_run_outcome

__version__ = "0.2.0"
__all__ = [
    "AsyncGeopackClient",
    "GeopackClient",
    "GeopackError",
    "GeopackAPIError",
    "GeopackAuthError",
    "GeopackValidationError",
    "GeopackTimeoutError",
    "GeopackTaskError",
    "TaskMessageInfo",
    "inspect_workflow_run_outcome",
    "task_log_entries_needing_review",
    "task_may_have_hidden_issues",
    "task_message_badge_severity",
    "task_message_info",
]


def __getattr__(name: str):
    if name == "AsyncGeopackClient":
        from .async_client import AsyncGeopackClient

        return AsyncGeopackClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
