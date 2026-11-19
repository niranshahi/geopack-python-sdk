"""Map SDK exceptions to MCP tool results — the error contract (slice 022 §1).

A failed call answers with a ``CallToolResult`` whose ``isError`` is ``True``
(mcp 1.27.1 — verified by the §0 capability probe) and whose
``structuredContent`` is::

    {"error": true, "code": "AGGREGATION_UNSUPPORTED", "type": "AggregationUnsupported",
     "statusCode": 400, "message": "...", "hint": "...", "invalidArgs": [...]}

* ``code`` mirrors the server's coded error body when present, otherwise it is
  derived from the exception class (``_CLASS_CODES``), otherwise from the HTTP
  status. ``code`` values are a public contract: adding one is fine, renaming
  one is a breaking change for every host that branches on it.
* ``hint`` names the **next tool** when there is one, so a refusal ends the
  loop instead of costing a turn.
* ``invalidArgs`` lists the argument keys a client-side validator rejected
  before any network call (``ToolArgumentError``).
* ``status_code`` is the pre-022 snake_case alias of ``statusCode``; hosts
  should branch on ``code``.

Never included: stack traces, request headers, tokens, URLs, SQL bodies or
absolute host paths outside ``savedPath``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult, TextContent

from geopack_sdk.exceptions import (
    AggregationInvalidArgs,
    AggregationUnsupported,
    AnalysisParamError,
    AnalysisSurfaceUnavailable,
    AnalysisTimeout,
    DatasetReadOnly,
    EditConflict,
    FieldPolicyError,
    GeopackAPIError,
    GeopackError,
    GeopackTaskError,
    GeopackTimeoutError,
    GeopackValidationError,
    PagedUnsupported,
    PublicationStateConflict,
    QueryValidationError,
    QuotaExceeded,
    RelationshipCatalogUnavailable,
)


class ToolArgumentError(ValueError):
    """A client-side validation refusal — raised before any network call.

    Subclasses :class:`ValueError` so pre-022 callers and tests that expect
    ``ValueError`` keep working (slice 022 §1.2). ``key`` names the offending
    argument (``aggregates.0.p``); ``hint`` says how to fix it.
    """

    def __init__(
        self,
        message: str,
        *,
        key: Optional[str] = None,
        hint: Optional[str] = None,
        invalid_args: Optional[List[str]] = None,
        **extra: Any,
    ):
        super().__init__(message)
        self.message = message
        self.key = key
        self.hint = hint
        if invalid_args is not None:
            self.invalid_args = [str(name) for name in invalid_args]
        elif key:
            self.invalid_args = [str(key)]
        else:
            self.invalid_args = []
        self.extra = dict(extra)


# --- Code tables ------------------------------------------------------------
#
# Class keys are looked up along ``type(exc).__mro__`` so a subclass inherits
# its parent's code without an entry of its own.

_CLASS_CODES: Dict[type, str] = {
    ToolArgumentError: "INVALID_ARGS",
    DatasetReadOnly: "DATASET_READ_ONLY",
    EditConflict: "EDIT_CONFLICT",
    RelationshipCatalogUnavailable: "RELATIONSHIP_CATALOG_UNAVAILABLE",
    PublicationStateConflict: "PUBLICATION_STATE_CONFLICT",
    PagedUnsupported: "PAGED_UNSUPPORTED",
    AggregationUnsupported: "AGGREGATION_UNSUPPORTED",
    AggregationInvalidArgs: "AGGREGATION_INVALID_ARGS",
    QueryValidationError: "QUERY_VALIDATION_ERROR",
    FieldPolicyError: "FIELD_POLICY_ERROR",
    QuotaExceeded: "QUOTA_EXCEEDED",
    AnalysisSurfaceUnavailable: "ANALYSIS_SURFACE_UNAVAILABLE",
    AnalysisParamError: "TOOL_MANIFEST_INVALID",
    AnalysisTimeout: "ANALYSIS_TIMEOUT",
    GeopackTimeoutError: "TIMEOUT",
    GeopackTaskError: "TASK_FAILED",
    GeopackValidationError: "RESPONSE_VALIDATION_ERROR",
}
_CLASS_CODES_BY_NAME: Dict[str, str] = {
    cls.__name__: code for cls, code in _CLASS_CODES.items()
}

_STATUS_CODES: Dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "UNPROCESSABLE_ENTITY",
    423: "DATASET_READ_ONLY",
    429: "RATE_LIMITED",
}

# --- Hint tables ------------------------------------------------------------
#
# Every actionable 4xx gets a hint; the class hint wins over the status hint.

_CLASS_HINTS: Dict[type, str] = {
    AggregationUnsupported: (
        "This datastore cannot aggregate server-side. Use geopack_sdk_query_dataset and "
        "page the records, or aggregate another dataset."
    ),
    AggregationInvalidArgs: (
        "Call geopack_sdk_get_dataset_schema and use an exact field name or alias."
    ),
    PagedUnsupported: (
        "This datastore cannot page this query. Narrow the filter or raise the limit."
    ),
    QueryValidationError: (
        "Check the argument names and values against geopack_sdk_get_dataset_schema, "
        "then retry."
    ),
    FieldPolicyError: (
        "The field is protected by policy. Call geopack_sdk_get_dataset_schema and use "
        "fields whose access is readable."
    ),
    QuotaExceeded: (
        "The quota dimension is exhausted; retrying will not help. Report the dimension "
        "and ask the user to free quota or raise the plan."
    ),
    DatasetReadOnly: (
        "The dataset is archived or locked against edits. Read it instead, or ask the "
        "user to unlock it."
    ),
    EditConflict: (
        "The document conflicts with another change. Re-read with geopack_sdk_query_dataset, "
        "fix the named operations and resubmit with mode='validate' first."
    ),
    RelationshipCatalogUnavailable: (
        "This datastore has no authored relationship catalog; query the datasets directly "
        "with geopack_sdk_query_dataset."
    ),
    PublicationStateConflict: (
        "Re-read the publication's current state before retrying the transition."
    ),
    AnalysisSurfaceUnavailable: (
        "The portal predates the analysis-tool surface. Report the deployment gap; there "
        "is no fallback and retrying will not help."
    ),
    AnalysisParamError: (
        "The workflow cannot describe itself as a tool. Report the named node id; do not "
        "repair the manifest client-side."
    ),
    AnalysisTimeout: (
        "The run is still executing. Resume with geopack_sdk_get_analysis_result using the "
        "run id instead of starting a second run."
    ),
    GeopackTimeoutError: "The request timed out. Retry once, then report the failure.",
    GeopackTaskError: (
        "Read the task with geopack_sdk_get_task for its final status; do not resubmit "
        "blindly."
    ),
    GeopackValidationError: (
        "The portal answered with a shape this SDK cannot parse. Report it; do not retry."
    ),
}

_STATUS_HINTS: Dict[int, str] = {
    400: "The request was rejected as malformed. Fix the named argument and retry.",
    401: (
        "Credentials were rejected. Re-authenticate (or check GEOPACK_* variables); do not "
        "retry the same call."
    ),
    403: (
        "The token lacks access to this resource. Ask the user for access; do not retry "
        "other names."
    ),
    404: (
        "Nothing matched. Use the matching list tool (for example geopack_sdk_list_datasets) "
        "to find a valid id."
    ),
    409: "The resource is in a conflicting state. Re-read it, then retry once.",
    413: "The payload is too large. Split the request into smaller parts.",
    423: "The dataset is read-only (archived or locked). Edits are refused.",
    429: "Rate limited. Wait before retrying.",
}
_SERVER_ERROR_HINT = "The portal failed. Retry once, then report the failure."
_TRANSPORT_CODE = "TRANSPORT_ERROR"
_TRANSPORT_HINT = (
    "The portal API is unreachable. Check that the Geoportal is running and GEOPACK_API_URL "
    "points at its /api base, then retry."
)
_TRANSPORT_MESSAGE = "Cannot reach the portal API at the configured base URL."


def _is_transport_failure(exc: BaseException) -> bool:
    """True when the SDK wrapped a ``requests`` transport error (API down, DNS, reset).

    ``GeopackClient._request`` raises ``GeopackError("Network error calling <path>: …")``
    from a ``requests.RequestException``; that message embeds the host and port, which the
    contract forbids, so the edge replaces it with a fixed sentence.
    """
    cause = exc.__cause__
    return cause is not None and type(cause).__module__.split(".")[0] == "requests"


def _code_for(exc: BaseException) -> str:
    """Server code -> exception class -> HTTP status, in that order."""
    server_code = getattr(exc, "code", None)
    if isinstance(server_code, str) and server_code:
        return server_code
    for cls in type(exc).__mro__:
        code = _CLASS_CODES.get(cls)
        if code:
            return code
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return _STATUS_CODES.get(status, "SERVER_ERROR" if status >= 500 else "HTTP_ERROR")
    return "UNKNOWN_ERROR"


def _hint_for(exc: BaseException) -> Optional[str]:
    own = getattr(exc, "hint", None)
    if isinstance(own, str) and own:
        return own
    for cls in type(exc).__mro__:
        hint = _CLASS_HINTS.get(cls)
        if hint:
            return hint
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status >= 500:
            return _SERVER_ERROR_HINT
        return _STATUS_HINTS.get(status)
    return None


def _code_from_type_name(name: Any) -> str:
    """Code for a handler-built ``{"type": ...}`` dict (no exception object)."""
    if isinstance(name, str):
        return _CLASS_CODES_BY_NAME.get(name, "UNKNOWN_ERROR")
    return "UNKNOWN_ERROR"


def _hint_from_type_name(name: Any) -> Optional[str]:
    for cls, hint in _CLASS_HINTS.items():
        if cls.__name__ == name:
            return hint
    return None


def tool_error_payload(exc: BaseException) -> Dict[str, Any]:
    """The data-only error payload; :func:`tool_error_result` wraps it."""
    if isinstance(exc, ToolArgumentError):
        payload: Dict[str, Any] = {
            "error": True,
            "type": "ToolArgumentError",
            "code": "INVALID_ARGS",
            "message": exc.message,
            "invalidArgs": list(exc.invalid_args),
        }
        hint = _hint_for(exc) or (
            "Correct the named argument(s) and retry; the message lists the accepted values."
        )
        payload["hint"] = hint
        payload.update(exc.extra)
        return payload

    if isinstance(exc, GeopackAPIError):
        payload = {
            "error": True,
            "type": type(exc).__name__,
            "code": _code_for(exc),
            "statusCode": exc.status_code,
            "status_code": exc.status_code,
            "message": exc.message,
        }
        if isinstance(exc, AggregationInvalidArgs):
            key = getattr(exc, "key", None)
            if key:
                payload["invalidArgs"] = [str(key)]
        if isinstance(exc, EditConflict):
            for attribute, name in (("issues", "issues"), ("conflicts", "conflicts")):
                value = getattr(exc, attribute, None)
                if value:
                    payload[name] = value
            edit_ref = getattr(exc, "edit_ref", None)
            if edit_ref:
                payload["editRef"] = edit_ref
        if isinstance(exc, QuotaExceeded):
            payload["quota"] = {
                "dimension": getattr(exc, "dimension", None),
                "limit": getattr(exc, "limit", None),
                "used": getattr(exc, "used", None),
            }
    elif isinstance(exc, GeopackTaskError):
        payload = {
            "error": True,
            "type": type(exc).__name__,
            "code": _code_for(exc),
            "task_id": exc.task_id,
            "status": exc.status,
            "message": exc.message,
        }
    elif isinstance(exc, GeopackTimeoutError):
        payload = {
            "error": True,
            "type": type(exc).__name__,
            "code": _code_for(exc),
            "message": exc.message,
            "timeout": exc.timeout,
        }
    elif isinstance(exc, GeopackError) and _is_transport_failure(exc):
        payload = {
            "error": True,
            "type": type(exc).__name__,
            "code": _TRANSPORT_CODE,
            "message": _TRANSPORT_MESSAGE,
            "hint": _TRANSPORT_HINT,
        }
    elif isinstance(exc, GeopackError):
        payload = {
            "error": True,
            "type": type(exc).__name__,
            "code": _code_for(exc),
            "message": exc.message,
        }
    else:
        payload = {
            "error": True,
            "type": type(exc).__name__,
            "code": "UNKNOWN_ERROR",
            "message": str(exc),
        }

    hint = _hint_for(exc)
    if hint:
        payload["hint"] = hint
    return payload


def _complete_handler_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fill ``code``/``hint`` on a handler-built error dict (020/021 lanes)."""
    completed = dict(payload)
    code = completed.get("code")
    if not isinstance(code, str) or not code:
        completed["code"] = _code_from_type_name(completed.get("type"))
    if not completed.get("hint"):
        hint = _hint_from_type_name(completed.get("type"))
        if hint:
            completed["hint"] = hint
    status = completed.get("statusCode", completed.get("status_code"))
    if isinstance(status, int):
        completed["statusCode"] = status
        completed.setdefault("status_code", status)
    return completed


def _text(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(payload)


def tool_error_result(exc: BaseException) -> CallToolResult:
    """A failed tool call: ``isError=True`` plus the structured error payload."""
    payload = tool_error_payload(exc)
    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=_text(payload))],
        structuredContent=payload,
    )


def tool_result(payload: Any) -> CallToolResult:
    """Wrap a handler payload; a ``{"error": true}`` dict becomes ``isError``."""
    if isinstance(payload, dict) and payload.get("error") is True:
        completed = _complete_handler_payload(payload)
        return CallToolResult(
            isError=True,
            content=[TextContent(type="text", text=_text(completed))],
            structuredContent=completed,
        )
    if isinstance(payload, dict):
        return CallToolResult(
            content=[TextContent(type="text", text=_text(payload))],
            structuredContent=payload,
        )
    return CallToolResult(content=[TextContent(type="text", text=_text(payload))])
