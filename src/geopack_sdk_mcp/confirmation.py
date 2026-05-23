"""Human-in-the-loop confirmation state for destructive MCP operations.

State is persisted on disk so a separate CLI process can approve/reject while the
MCP server runs in another process (e.g. Cursor stdio child).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_EXPIRATION_MINUTES = 15
DEFAULT_STORE_ENV = "GEOPACK_CONFIRM_STORE"


def default_store_path() -> Path:
    override = os.environ.get(DEFAULT_STORE_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".geopack" / "mcp_confirmations.json"


def compute_payload_fingerprint(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


@dataclass
class ConfirmationRequest:
    """Pending or resolved confirmation for one destructive operation."""

    id: str
    operation: str
    resource_id: int | str
    created_at: datetime
    expires_at: datetime
    status: str = "pending"  # pending | approved | rejected | executed
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    executed_at: Optional[datetime] = None
    payload_fingerprint: Optional[str] = None
    audit: List[Dict[str, Any]] = field(default_factory=list)

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    def _append_audit(self, event: str, **extra: Any) -> None:
        entry = {"event": event, "at": datetime.now().isoformat(), **extra}
        self.audit.append(entry)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "operation": self.operation,
            "resource_id": self.resource_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by,
            "rejection_reason": self.rejection_reason,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "payload_fingerprint": self.payload_fingerprint,
            "is_expired": self.is_expired(),
            "audit": list(self.audit),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfirmationRequest":
        def _parse_dt(key: str) -> Optional[datetime]:
            raw = data.get(key)
            if not raw:
                return None
            return datetime.fromisoformat(raw)

        return cls(
            id=data["id"],
            operation=data["operation"],
            resource_id=data["resource_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            status=data.get("status", "pending"),
            approved_at=_parse_dt("approved_at"),
            approved_by=data.get("approved_by"),
            rejection_reason=data.get("rejection_reason"),
            executed_at=_parse_dt("executed_at"),
            payload_fingerprint=data.get("payload_fingerprint"),
            audit=list(data.get("audit") or []),
        )


class _FileLock:
    """Cross-process exclusive lock via lock file (no extra dependencies)."""

    def __init__(self, path: Path, timeout_seconds: float = 5.0) -> None:
        self._lock_path = path.with_suffix(path.suffix + ".lock")
        self._timeout_seconds = timeout_seconds

    def __enter__(self) -> "_FileLock":
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire confirmation store lock: {self._lock_path}"
                    )
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError as err:
            logger.warning("Failed to release confirmation lock %s: %s", self._lock_path, err)


class ConfirmationManager:
    """Thread-safe confirmation registry with on-disk persistence."""

    def __init__(
        self,
        expiration_minutes: int = DEFAULT_EXPIRATION_MINUTES,
        store_path: Optional[Path] = None,
    ) -> None:
        self.expiration_minutes = expiration_minutes
        self.store_path = store_path or default_store_path()
        self._lock = threading.Lock()
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_unlocked(self) -> Dict[str, ConfirmationRequest]:
        if not self.store_path.exists():
            return {}
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read confirmation store %s: %s", self.store_path, exc)
            return {}
        items = raw.get("confirmations", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, dict):
            return {}
        loaded: Dict[str, ConfirmationRequest] = {}
        for cid, row in items.items():
            try:
                loaded[cid] = ConfirmationRequest.from_dict(row)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping corrupt confirmation %s: %s", cid, exc)
        return loaded

    def _save_unlocked(self, confirmations: Dict[str, ConfirmationRequest]) -> None:
        payload = {
            "confirmations": {cid: req.to_dict() for cid, req in confirmations.items()}
        }
        tmp_path = self.store_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.store_path)

    def _mutate(self, fn):
        with self._lock:
            with _FileLock(self.store_path):
                data = self._load_unlocked()
                self._purge_expired_unlocked(data)
                result = fn(data)
                self._save_unlocked(data)
                return result

    def _purge_expired_unlocked(self, data: Dict[str, ConfirmationRequest]) -> None:
        expired = [cid for cid, req in data.items() if req.is_expired()]
        for cid in expired:
            del data[cid]

    def create_request(
        self,
        operation: str,
        resource_id: int | str,
        *,
        payload_fingerprint: Optional[str] = None,
    ) -> ConfirmationRequest:
        confirmation_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(minutes=self.expiration_minutes)

        req = ConfirmationRequest(
            id=confirmation_id,
            operation=operation,
            resource_id=resource_id,
            created_at=now,
            expires_at=expires_at,
            payload_fingerprint=payload_fingerprint,
        )
        req._append_audit("created", operation=operation, resource_id=resource_id)

        def _create(data: Dict[str, ConfirmationRequest]) -> ConfirmationRequest:
            data[confirmation_id] = req
            return req

        created = self._mutate(_create)
        logger.info(
            "Created confirmation %s for %s #%s",
            confirmation_id,
            operation,
            resource_id,
        )
        return created

    def find_open_pending(
        self,
        operation: str,
        resource_id: int | str,
        payload_fingerprint: Optional[str] = None,
    ) -> Optional[ConfirmationRequest]:
        def _find(data: Dict[str, ConfirmationRequest]) -> Optional[ConfirmationRequest]:
            for req in data.values():
                if req.status != "pending" or req.is_expired():
                    continue
                if req.operation != operation or req.resource_id != resource_id:
                    continue
                if (
                    payload_fingerprint is not None
                    and req.payload_fingerprint is not None
                    and req.payload_fingerprint != payload_fingerprint
                ):
                    continue
                return req
            return None

        return self._mutate(_find)

    def get_request(self, confirmation_id: str) -> Optional[ConfirmationRequest]:
        def _get(data: Dict[str, ConfirmationRequest]) -> Optional[ConfirmationRequest]:
            req = data.get(confirmation_id)
            if req is None:
                return None
            if req.is_expired():
                data.pop(confirmation_id, None)
                return None
            return req

        return self._mutate(_get)

    def approve_request(
        self, confirmation_id: str, approved_by: str = "operator"
    ) -> bool:
        def _approve(data: Dict[str, ConfirmationRequest]) -> bool:
            req = data.get(confirmation_id)
            if req is None or req.is_expired():
                data.pop(confirmation_id, None)
                return False
            if req.status != "pending":
                return False
            req.status = "approved"
            req.approved_at = datetime.now()
            req.approved_by = approved_by
            req._append_audit("approved", approved_by=approved_by)
            return True

        ok = self._mutate(_approve)
        if ok:
            logger.info("Approved confirmation %s by %s", confirmation_id, approved_by)
        return ok

    def reject_request(
        self, confirmation_id: str, reason: str = "User rejected"
    ) -> bool:
        def _reject(data: Dict[str, ConfirmationRequest]) -> bool:
            req = data.get(confirmation_id)
            if req is None or req.is_expired():
                data.pop(confirmation_id, None)
                return False
            if req.status != "pending":
                return False
            req.status = "rejected"
            req.rejection_reason = reason
            req._append_audit("rejected", reason=reason)
            return True

        ok = self._mutate(_reject)
        if ok:
            logger.info("Rejected confirmation %s: %s", confirmation_id, reason)
        return ok

    def consume_request(self, confirmation_id: str) -> bool:
        """Mark an approved request as executed (single-use)."""

        def _consume(data: Dict[str, ConfirmationRequest]) -> bool:
            req = data.get(confirmation_id)
            if req is None or req.is_expired():
                data.pop(confirmation_id, None)
                return False
            if req.status != "approved":
                return False
            req.status = "executed"
            req.executed_at = datetime.now()
            req._append_audit("executed")
            return True

        return self._mutate(_consume)

    def list_pending(self) -> List[ConfirmationRequest]:
        def _list(data: Dict[str, ConfirmationRequest]) -> List[ConfirmationRequest]:
            return [req for req in data.values() if req.status == "pending"]

        return self._mutate(_list)

    def cleanup_expired(self) -> int:
        def _cleanup(data: Dict[str, ConfirmationRequest]) -> int:
            before = len(data)
            self._purge_expired_unlocked(data)
            return before - len(data)

        removed = self._mutate(_cleanup)
        if removed:
            logger.info("Removed %d expired confirmation requests", removed)
        return removed


_confirmation_manager: Optional[ConfirmationManager] = None
_manager_lock = threading.Lock()


def get_confirmation_manager() -> ConfirmationManager:
    global _confirmation_manager
    if _confirmation_manager is None:
        with _manager_lock:
            if _confirmation_manager is None:
                _confirmation_manager = ConfirmationManager()
    return _confirmation_manager
