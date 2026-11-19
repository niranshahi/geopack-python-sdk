"""Typed exceptions for the Geopack Python SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional

from typing import TYPE_CHECKING, Callable, Optional as TypingOptional

import requests

if TYPE_CHECKING:
    import httpx


def _error_code_from_details(details: Optional[Dict[str, Any]]) -> TypingOptional[str]:
    """Extract the machine-readable ``code`` from a server error body.

    Lookup order (slice 016 §1.2): ``body.code`` -> ``body.error.code`` ->
    ``body.errors[0].code``. Message text is never inspected: messages are
    user-facing and change without notice.
    """
    if not isinstance(details, dict):
        return None
    code = details.get("code")
    if isinstance(code, str) and code:
        return code
    nested = details.get("error")
    if isinstance(nested, dict):
        code = nested.get("code")
        if isinstance(code, str) and code:
            return code
    errors = details.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        code = errors[0].get("code")
        if isinstance(code, str) and code:
            return code
    return None


def _lookup_detail(details: Optional[Dict[str, Any]], name: str) -> Any:
    """Read ``name`` from an error body, accepting the camelCase twin."""
    if not isinstance(details, dict):
        return None
    if name in details:
        return details[name]
    parts = name.split("_")
    camel = parts[0] + "".join(part.capitalize() for part in parts[1:])
    return details.get(camel)


class GeopackError(Exception):
    """Base exception for all Geopack SDK errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class GeopackAPIError(GeopackError):
    """Raised when the Geopack API returns an HTTP error status."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        *,
        response: Optional[requests.Response] = None,
    ):
        self.status_code = status_code
        self.response = response
        self.code = _error_code_from_details(details)
        super().__init__(message, details)

    @classmethod
    def from_http_status(
        cls,
        status_code: int,
        *,
        reason: TypingOptional[str] = None,
        text: TypingOptional[str] = None,
        json_loader: TypingOptional[Callable[[], Any]] = None,
        response: TypingOptional[Any] = None,
    ) -> GeopackAPIError:
        """Build an API or auth error from HTTP status and optional body."""
        details: Dict[str, Any] = {}
        message = reason or f"HTTP {status_code}"

        if json_loader is not None:
            try:
                error_data = json_loader()
                if isinstance(error_data, dict):
                    details = error_data
                    raw = (
                        error_data.get("message")
                        or error_data.get("error")
                        or error_data.get("errors")
                    )
                    if raw is None:
                        message = str(error_data)
                    elif isinstance(raw, str):
                        message = raw
                    else:
                        message = str(raw)
                else:
                    message = str(error_data)
            except ValueError:
                pass

        if message == (reason or f"HTTP {status_code}") and text:
            stripped = text.strip()
            if stripped:
                message = stripped[:500]

        if status_code in (401, 403) and _error_code_from_details(details) != "QUOTA_EXCEEDED":
            return GeopackAuthError(status_code, message, details, response=response)

        typed = _typed_error_class(status_code, details)
        if typed is None:
            return cls(status_code, message, details, response=response)

        extras = {
            name: _lookup_detail(details, name) for name in getattr(typed, "_extras", ())
        }
        return typed(status_code, message, details, response=response, **extras)

    @classmethod
    def from_response(cls, response: requests.Response) -> GeopackAPIError:
        """Build an API or auth error from a ``requests`` response."""
        return cls.from_http_status(
            response.status_code,
            reason=response.reason,
            text=response.text,
            json_loader=response.json,
            response=response,
        )

    @classmethod
    def from_httpx_response(cls, response: "httpx.Response") -> GeopackAPIError:
        """Build an API or auth error from an ``httpx`` response."""
        return cls.from_http_status(
            response.status_code,
            reason=response.reason_phrase,
            text=response.text,
            json_loader=response.json,
            response=response,
        )


class GeopackAuthError(GeopackAPIError):
    """Raised on authentication or authorization failures (401, 403)."""


# --- Coded 4xx errors (slice 016 §1.2) ---------------------------------------
#
# The server answers request-shape problems with a stable ``code``. Callers must
# branch on the class (and its named fields) instead of parsing message text.


class _CodedAPIError(GeopackAPIError):
    """Base for coded 4xx errors whose extras are lifted out of the body."""

    _extras: tuple = ()

    def __init__(
        self,
        status_code: int = 400,
        message: TypingOptional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        *,
        response: TypingOptional[Any] = None,
        **extras: Any,
    ):
        details = dict(details or {})
        for name in self._extras:
            value = extras.get(name, _lookup_detail(details, name))
            setattr(self, name, value)
            if value is not None:
                details.setdefault(name, value)
        super().__init__(
            status_code, message or f"HTTP {status_code}", details, response=response
        )


class PagedUnsupported(_CodedAPIError):
    """``PAGED_UNSUPPORTED`` — the store cannot page this query."""

    _extras = ("data_store_type",)


class AggregationUnsupported(_CodedAPIError):
    """``AGGREGATION_UNSUPPORTED`` — the store cannot aggregate this lane."""

    _extras = ("data_store_type",)


class AggregationInvalidArgs(_CodedAPIError):
    """``AGGREGATION_INVALID_ARGS`` — ``key`` names the offending argument."""

    _extras = ("key",)


class QueryValidationError(_CodedAPIError):
    """``QUERY_PAGED_*`` — request-shape problem other than supportability.

    Deliberately an :class:`GeopackAPIError` (not ``GeopackValidationError``,
    which stays pydantic-only) so ``except GeopackAPIError`` keeps working.
    """


class FieldPolicyError(_CodedAPIError):
    """``FIELD_POLICY_INVALID`` / ``FIELD_POLICY_PROTECTED_FIELD``."""


class QuotaExceeded(_CodedAPIError):
    """``QUOTA_EXCEEDED`` — carries the dimension, its limit and current usage.

    The one exception to the "401/403 means auth" rule: a quota refusal answers
    with one of those statuses but a coded ``QUOTA_EXCEEDED`` body, and it is
    not an authentication problem. Everything else on 401/403 stays
    :class:`GeopackAuthError`.
    """

    _extras = ("dimension", "limit", "used")


class DatasetReadOnly(_CodedAPIError):
    """HTTP 423 — the dataset is archived or locked against edits."""

    def __init__(
        self,
        status_code: int = 423,
        message: TypingOptional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        *,
        response: TypingOptional[Any] = None,
        **extras: Any,
    ):
        super().__init__(status_code, message, details, response=response, **extras)


class EditConflict(_CodedAPIError):
    """409 on the edits lane — the server names the losing operations.

    The edits controller reports the offending operations as ``issues`` (and
    echoes ``editRef`` / ``precheckId``); ``conflicts`` is accepted too so a
    future response can carry it without an SDK change.
    """

    _extras = ("issues", "conflicts", "edit_ref", "precheck_id")


class PublicationStateConflict(_CodedAPIError):
    """409 on publication transitions — ``state`` is the current state."""

    _extras = ("state",)


class RelationshipCatalogUnavailable(_CodedAPIError):
    """409 on the relationship catalog — it is busy or not built yet."""


class EditDocumentVersionError(GeopackError):
    """Client-side: the caller's edit document declares an unknown version.

    Raised before any network call, so the caller learns the supported shape
    instead of collecting a server 400.
    """

    def __init__(self, message: str, *, version: TypingOptional[str] = None):
        self.version = version
        details: Dict[str, Any] = {}
        if version is not None:
            details["version"] = version
        super().__init__(message, details)


def _typed_error_class(
    status_code: int, details: Optional[Dict[str, Any]]
) -> TypingOptional[type]:
    """Map ``(status, code)`` to a typed class; ``None`` keeps the legacy class."""
    if status_code == 423:
        return DatasetReadOnly

    code = (_error_code_from_details(details) or "").upper()

    if status_code == 409:
        if code.startswith(("EDIT", "EDITS")):
            return EditConflict
        if code.startswith("PUBLICATION"):
            return PublicationStateConflict
        if code.startswith("RELATIONSHIP"):
            return RelationshipCatalogUnavailable
        return None

    if status_code in (400, 422) and code.startswith("RELATIONSHIP_"):
        # Coded 400s from the related-records lane (unknown relationship, an
        # unregistered related dataset): the message names the field.
        return QueryValidationError

    if code == "PAGED_UNSUPPORTED":
        return PagedUnsupported
    if code == "AGGREGATION_UNSUPPORTED":
        return AggregationUnsupported
    if code == "AGGREGATION_INVALID_ARGS":
        return AggregationInvalidArgs
    if code.startswith("QUERY_PAGED"):
        return QueryValidationError
    if code in ("FIELD_POLICY_INVALID", "FIELD_POLICY_PROTECTED_FIELD"):
        return FieldPolicyError
    if code == "QUOTA_EXCEEDED":
        return QuotaExceeded
    return None


class GeopackValidationError(GeopackError):
    """Raised when a response fails Pydantic validation."""

    def __init__(self, message: str, errors: Any = None):
        self.errors = errors
        details = {"errors": errors} if errors is not None else None
        super().__init__(message, details)


class GeopackTimeoutError(GeopackError):
    """Raised when an HTTP request or task wait exceeds its timeout."""

    def __init__(self, message: str, *, timeout: Optional[float] = None):
        self.timeout = timeout
        super().__init__(message)


class GeopackTaskError(GeopackError):
    """Raised when a background task fails or is canceled."""

    def __init__(self, task_id: str, status: str, message: Optional[str] = None):
        self.task_id = task_id
        self.status = status
        text = message or f"Task {task_id} {status}"
        super().__init__(text, details={"task_id": task_id, "status": status})


# --- Analysis-tool surface (portal slices 030 / 031) -------------------------


class AnalysisSurfaceUnavailable(GeopackAPIError):
    """Raised when the portal does not serve the analysis-tool surface.

    The catalog endpoint (``GET /api/workflows/tools``) answering 404 means the
    portal predates the surface. There is deliberately **no** fallback to
    ``list_workflows`` / ``get_workflow``: a silent downgrade would hand the
    caller an untyped workflow and hide the deployment gap.
    """

    def __init__(
        self,
        message: str = (
            "The portal does not serve the analysis-tool surface "
            "(GET /api/workflows/tools returned 404). Deploy a portal with slice 030."
        ),
        *,
        status_code: int = 404,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code, message, details)


class AnalysisParamError(GeopackError):
    """Raised when a workflow cannot describe itself as a tool.

    Carries the server's ``TOOL_MANIFEST_INVALID`` reason and the offending node
    id, so the caller can report *which* node broke the manifest instead of
    guessing. The SDK never repairs a manifest client-side (030 §1).
    """

    def __init__(
        self,
        message: str,
        *,
        tool_id: Optional[int] = None,
        node_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        self.tool_id = tool_id
        self.node_id = node_id
        self.reason = reason or message
        details: Dict[str, Any] = {"reason": self.reason}
        if tool_id is not None:
            details["tool_id"] = tool_id
        if node_id is not None:
            details["node_id"] = node_id
        super().__init__(message, details)


class AnalysisTimeout(GeopackTimeoutError):
    """Raised when ``wait`` polling exceeds ``timeout_s``.

    The run keeps going on the server: ``run_id`` is attached so the caller can
    resume with :meth:`get_analysis_result` instead of starting a second run.
    """

    def __init__(
        self,
        message: str,
        *,
        run_id: Optional[int] = None,
        timeout: Optional[float] = None,
    ):
        self.run_id = run_id
        super().__init__(message, timeout=timeout)
        if run_id is not None:
            self.details["run_id"] = run_id
