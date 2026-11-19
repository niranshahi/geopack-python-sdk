from .client import GeopackClient
from .edits import build_edit_document, new_edit_ref
from .exceptions import (
    AggregationInvalidArgs,
    AggregationUnsupported,
    AnalysisParamError,
    AnalysisSurfaceUnavailable,
    AnalysisTimeout,
    DatasetReadOnly,
    EditConflict,
    EditDocumentVersionError,
    FieldPolicyError,
    GeopackAPIError,
    GeopackAuthError,
    GeopackError,
    GeopackTaskError,
    GeopackTimeoutError,
    GeopackValidationError,
    PagedUnsupported,
    PublicationStateConflict,
    QueryValidationError,
    QuotaExceeded,
    RelationshipCatalogUnavailable,
    WorkflowHasActiveRuns,
    WorkflowHasRuns,
)
from .tasks import (
    TaskMessageInfo,
    task_log_entries_needing_review,
    task_may_have_hidden_issues,
    task_message_badge_severity,
    task_message_info,
)
from .workflow_runs import inspect_workflow_run_outcome

__version__ = "0.8.0"
__all__ = [
    "AsyncGeopackClient",
    "GeopackClient",
    "GeopackError",
    "GeopackAPIError",
    "GeopackAuthError",
    "GeopackValidationError",
    "GeopackTimeoutError",
    "GeopackTaskError",
    "AnalysisSurfaceUnavailable",
    "AnalysisParamError",
    "AnalysisTimeout",
    "PagedUnsupported",
    "AggregationUnsupported",
    "AggregationInvalidArgs",
    "QueryValidationError",
    "FieldPolicyError",
    "QuotaExceeded",
    "DatasetReadOnly",
    "EditConflict",
    "EditDocumentVersionError",
    "PublicationStateConflict",
    "RelationshipCatalogUnavailable",
    "WorkflowHasRuns",
    "WorkflowHasActiveRuns",
    "new_edit_ref",
    "build_edit_document",
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
