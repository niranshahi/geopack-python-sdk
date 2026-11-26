"""Local token store for CLI login and MCP bootstrap (no passwords on disk)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

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


# --------------------------------------------------------------------------- #
# Slice 034 — pluggable credential stores (refresh token only; access is memory)
# --------------------------------------------------------------------------- #

KEYRING_SERVICE = "geopack"
DEFAULT_CONFIG_DIR = Path.home() / ".geopack"


class CredentialStoreError(RuntimeError):
    """Raised when no usable credential store can be created (D7)."""


def config_dir() -> Path:
    override = os.getenv("GEOPACK_CONFIG_DIR")
    return Path(override).expanduser() if override else DEFAULT_CONFIG_DIR


def profiles_file_path() -> Path:
    return config_dir() / "profiles.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, text: str, *, mode: int = 0o600) -> None:
    """Write ``text`` atomically (temp file + ``os.replace``) with mode 0600 (D16)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
    try:
        path.chmod(mode)
    except (OSError, NotImplementedError):
        pass


class CredentialStore(Protocol):
    """Refresh-token storage backend. Keys are ``<api_url>|<profile>``."""

    name: str

    def get_refresh_token(self, key: str) -> Optional[str]: ...

    def set_refresh_token(self, key: str, token: str) -> None: ...

    def delete_refresh_token(self, key: str) -> None: ...


@dataclass
class StoredProfile:
    """Non-secret profile metadata (never holds a token)."""

    profile: str
    api_url: str
    username: Optional[str] = None
    store: str = "keyring"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


class ProfileRegistry:
    """``~/.geopack/profiles.json`` — profile -> api_url/username/store."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or profiles_file_path()

    def load(self) -> Dict[str, StoredProfile]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        out: Dict[str, StoredProfile] = {}
        for name, entry in raw.items():
            if isinstance(entry, dict):
                out[name] = StoredProfile(
                    profile=entry.get("profile", name),
                    api_url=entry.get("api_url", ""),
                    username=entry.get("username"),
                    store=entry.get("store", "keyring"),
                    created_at=entry.get("created_at"),
                    updated_at=entry.get("updated_at"),
                )
        return out

    def get(self, profile: str) -> Optional[StoredProfile]:
        return self.load().get(profile)

    def upsert(self, entry: StoredProfile) -> None:
        data = self.load()
        existing = data.get(entry.profile)
        if existing and not entry.created_at:
            entry.created_at = existing.created_at
        entry.updated_at = entry.updated_at or _now_iso()
        data[entry.profile] = entry
        payload = {name: p.to_dict() for name, p in data.items()}
        _atomic_write(self._path, json.dumps(payload, indent=2) + "\n")

    def remove(self, profile: str) -> bool:
        data = self.load()
        if profile not in data:
            return False
        del data[profile]
        payload = {name: p.to_dict() for name, p in data.items()}
        _atomic_write(self._path, json.dumps(payload, indent=2) + "\n")
        return True


class MemoryStore:
    """In-memory store for tests."""

    name = "memory"

    def __init__(self) -> None:
        self._data: Dict[str, str] = {}

    def get_refresh_token(self, key: str) -> Optional[str]:
        return self._data.get(key)

    def set_refresh_token(self, key: str, token: str) -> None:
        self._data[key] = token

    def delete_refresh_token(self, key: str) -> None:
        self._data.pop(key, None)


class FileStore:
    """Explicit plaintext fallback (``GEOPACK_CREDENTIAL_STORE=file`` / ``--store file``).

    Never selected silently (D7). Stores ``{key: refresh_token}`` in a 0600 JSON
    file; callers must warn the user that this is less safe than the OS store.
    """

    name = "file"

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or (config_dir() / "refresh-tokens.json")

    def _load(self) -> Dict[str, str]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def get_refresh_token(self, key: str) -> Optional[str]:
        value = self._load().get(key)
        return value if isinstance(value, str) else None

    def set_refresh_token(self, key: str, token: str) -> None:
        data = self._load()
        data[key] = token
        _atomic_write(self._path, json.dumps(data, indent=2) + "\n")

    def delete_refresh_token(self, key: str) -> None:
        data = self._load()
        if key in data:
            del data[key]
            _atomic_write(self._path, json.dumps(data, indent=2) + "\n")


class KeyringStore:
    """OS secret store via the optional ``keyring`` package (D5/D6)."""

    name = "keyring"

    def __init__(self, service: str = KEYRING_SERVICE) -> None:
        try:
            import keyring  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on environment
            raise CredentialStoreError(
                "The 'keyring' package is not installed. Install 'geopack-sdk[keyring]' "
                "or select the plaintext fallback with --store file."
            ) from exc
        self._keyring = keyring
        self._service = service

    def get_refresh_token(self, key: str) -> Optional[str]:
        try:
            return self._keyring.get_password(self._service, key)
        except Exception as exc:  # pragma: no cover - backend specific
            raise CredentialStoreError(f"keyring read failed: {exc}") from exc

    def set_refresh_token(self, key: str, token: str) -> None:
        try:
            self._keyring.set_password(self._service, key, token)
        except Exception as exc:  # pragma: no cover - backend specific
            raise CredentialStoreError(f"keyring write failed: {exc}") from exc

    def delete_refresh_token(self, key: str) -> None:
        try:
            self._keyring.delete_password(self._service, key)
        except Exception:
            # Missing entries raise; deletion is best-effort.
            pass


def resolve_store(preferred: Optional[str] = None) -> CredentialStore:
    """Pick a store: explicit -> ``GEOPACK_CREDENTIAL_STORE`` -> keyring, else error (D7)."""
    name = preferred or os.getenv("GEOPACK_CREDENTIAL_STORE")
    if name == "memory":
        return MemoryStore()
    if name == "file":
        print(
            "WARNING: GEOPACK_CREDENTIAL_STORE=file stores the refresh token in "
            f"plaintext at {config_dir() / 'refresh-tokens.json'} (0600). Prefer the OS keyring."
        )
        return FileStore()
    if name in (None, "", "keyring"):
        try:
            return KeyringStore()
        except CredentialStoreError:
            if name == "keyring":
                raise
            raise CredentialStoreError(
                "No OS secret store is available. Install 'geopack-sdk[keyring]' or "
                "explicitly select the plaintext fallback with "
                "--store file / GEOPACK_CREDENTIAL_STORE=file."
            )
    raise CredentialStoreError(f"Unknown credential store: {name!r}")
