"""Shared guard for destructive MCP tools (request → human approve → execute)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .confirmation import (
    ConfirmationRequest,
    compute_payload_fingerprint,
    get_confirmation_manager,
)


@dataclass
class GuardResult:
    """Outcome of a destructive-operation guard check."""

    should_execute: bool
    confirmation_id: Optional[str] = None
    response: Optional[Dict[str, Any]] = None


def _pending_response(req: ConfirmationRequest) -> Dict[str, Any]:
    return {
        "success": False,
        "needs_confirmation": True,
        "confirmation_id": req.id,
        "status": req.status,
        "message": (
            f"Destructive operation requires human approval. "
            f"Run: geopack-sdk-confirm approve {req.id}"
        ),
        "operator_command": f"geopack-sdk-confirm approve {req.id}",
        "poll_tool": "geopack_sdk_get_confirmation_status",
        "expires_at": req.expires_at.isoformat(),
    }


def _blocked_response(
    *,
    confirmation_id: Optional[str],
    message: str,
    status: str = "blocked",
) -> Dict[str, Any]:
    return {
        "success": False,
        "needs_confirmation": True,
        "confirmation_id": confirmation_id,
        "status": status,
        "message": message,
        "operator_command": (
            f"geopack-sdk-confirm approve {confirmation_id}"
            if confirmation_id
            else None
        ),
    }


def guard_destructive_operation(
    operation: str,
    resource_id: int | str,
    confirmation_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> GuardResult:
    """Return whether the tool may execute and any response payload for the agent."""
    manager = get_confirmation_manager()
    fingerprint = compute_payload_fingerprint(payload)

    if confirmation_id:
        req = manager.get_request(confirmation_id)
        if req is None:
            return GuardResult(
                False,
                confirmation_id=confirmation_id,
                response=_blocked_response(
                    confirmation_id=confirmation_id,
                    message="Confirmation not found or expired. Create a new request.",
                    status="not_found",
                ),
            )
        if req.operation != operation or str(req.resource_id) != str(resource_id):
            return GuardResult(
                False,
                confirmation_id=confirmation_id,
                response=_blocked_response(
                    confirmation_id=confirmation_id,
                    message="Confirmation does not match this operation/resource.",
                    status="mismatch",
                ),
            )
        if (
            fingerprint
            and req.payload_fingerprint
            and req.payload_fingerprint != fingerprint
        ):
            return GuardResult(
                False,
                confirmation_id=confirmation_id,
                response=_blocked_response(
                    confirmation_id=confirmation_id,
                    message=(
                        "Operation parameters changed since the confirmation was created. "
                        "Create a new confirmation request."
                    ),
                    status="payload_mismatch",
                ),
            )
        if req.status == "executed":
            return GuardResult(
                False,
                confirmation_id=confirmation_id,
                response=_blocked_response(
                    confirmation_id=confirmation_id,
                    message="Confirmation already used (single-use token).",
                    status="executed",
                ),
            )
        if req.status == "rejected":
            return GuardResult(
                False,
                confirmation_id=confirmation_id,
                response=_blocked_response(
                    confirmation_id=confirmation_id,
                    message=f"Confirmation was rejected: {req.rejection_reason}",
                    status="rejected",
                ),
            )
        if req.status == "pending":
            return GuardResult(
                False,
                confirmation_id=confirmation_id,
                response=_pending_response(req),
            )
        if req.status == "approved":
            return GuardResult(True, confirmation_id=confirmation_id)

        return GuardResult(
            False,
            confirmation_id=confirmation_id,
            response=_blocked_response(
                confirmation_id=confirmation_id,
                message=f"Unexpected confirmation status: {req.status}",
            ),
        )

    existing = manager.find_open_pending(operation, resource_id, fingerprint)
    req = existing or manager.create_request(
        operation, resource_id, payload_fingerprint=fingerprint
    )
    return GuardResult(False, confirmation_id=req.id, response=_pending_response(req))
