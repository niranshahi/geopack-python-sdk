"""Typed exceptions for the Geopack Python SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional

from typing import TYPE_CHECKING, Callable, Optional as TypingOptional

import requests

if TYPE_CHECKING:
    import httpx


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

        exc_type = GeopackAuthError if status_code in (401, 403) else cls
        return exc_type(status_code, message, details, response=response)

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
