"""Local token store for CLI login and MCP bootstrap (no passwords on disk)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CREDENTIALS_DIR = Path.home() / ".geopack"
DEFAULT_CREDENTIALS_FILE = DEFAULT_CREDENTIALS_DIR / "credentials.json"


@dataclass
class StoredCredentials:
    """Tokens persisted by ``geopack-sdk login``."""

    api_url: str
    access_token: str
    refresh_token: Optional[str] = None
    username: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def credentials_file_path() -> Path:
    override = os.getenv("GEOPACK_CREDENTIALS_FILE")
    if override:
        return Path(override).expanduser()
    return DEFAULT_CREDENTIALS_FILE


def load_credentials(api_url: Optional[str] = None) -> Optional[StoredCredentials]:
    """Load stored tokens if the file exists and optional ``api_url`` matches."""
    path = credentials_file_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    access = raw.get("access_token") or raw.get("accessToken")
    stored_url = raw.get("api_url") or raw.get("apiUrl")
    if not access or not stored_url:
        return None
    if api_url and _normalize_api_url(api_url) != _normalize_api_url(stored_url):
        return None
    return StoredCredentials(
        api_url=stored_url,
        access_token=access,
        refresh_token=raw.get("refresh_token") or raw.get("refreshToken"),
        username=raw.get("username"),
    )


def save_credentials(creds: StoredCredentials) -> Path:
    """Write credentials with restrictive permissions (POSIX 0600)."""
    path = credentials_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(creds.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
        path.parent.chmod(0o700)
    except (OSError, NotImplementedError):
        pass
    return path


def clear_credentials() -> bool:
    """Remove the credentials file. Returns True if a file was removed."""
    path = credentials_file_path()
    if path.is_file():
        path.unlink()
        return True
    return False


def _normalize_api_url(url: str) -> str:
    return url.rstrip("/")
