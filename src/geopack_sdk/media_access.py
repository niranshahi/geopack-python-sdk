"""
Scoped media access URLs (SEC-RT-001).

- **Mint (class A):** ``GET …/access-url`` with ``Authorization: Bearer`` only.
- **Resource (class B):** ``GET`` thumbnail/tile/avatar bytes with Bearer **or** signed ``media`` + ``sig`` query.

Do **not** put full JWT in URLs (legacy ``?auth_token=`` is deprecated).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from .client import GeopackClient
from .dataset_payload import dataset_thumbnail_api_path
from .exceptions import GeopackAPIError


@dataclass(frozen=True)
class MintedMediaAccess:
    """Response from a mint endpoint."""

    url: str
    expires_at: datetime
    media_query: Optional[str] = None


def dataset_thumbnail_mint_path(dataset_id: int) -> str:
    """Relative mint path: ``GET /datasets/{id}/thumbnail/access-url`` (Bearer only)."""
    return f"/datasets/{dataset_id}/thumbnail/access-url"


def dataset_tiles_mint_path(dataset_id: int) -> str:
    return f"/datasets/{dataset_id}/tiles/access-url"


def dataset_attachment_mint_path(dataset_id: int, attachment_id: int) -> str:
    return f"/datasets/{dataset_id}/attachment/{attachment_id}/access-url"


def map_thumbnail_mint_path(map_id: int) -> str:
    return f"/maps/{map_id}/thumbnail/access-url"


def workflow_thumbnail_mint_path(workflow_id: int) -> str:
    return f"/workflows/{workflow_id}/thumbnail/access-url"


def print_layout_thumbnail_mint_path(layout_id: int) -> str:
    return f"/print-layouts/{layout_id}/thumbnail/access-url"


def user_avatar_mint_path(user_id: int) -> str:
    return f"/users/{user_id}/avatar/access-url"


def _parse_expires_at(raw: str) -> datetime:
    text = (raw or "").strip()
    if not text:
        raise GeopackAPIError(502, "Mint response missing expiresAt.")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def mint_access_url(client: GeopackClient, mint_path: str) -> MintedMediaAccess:
    """
    Mint a signed resource URL (Bearer on mint endpoint).

    Use when a consumer cannot send ``Authorization`` headers (e.g. HTML ``<img src>``).
    For ``requests`` / MCP / notebooks, prefer :func:`fetch_dataset_thumbnail` with Bearer.
    """
    data = client.get(mint_path.lstrip("/"))
    if not isinstance(data, dict) or not data.get("url"):
        raise GeopackAPIError(502, f"Invalid mint response from {mint_path}")
    return MintedMediaAccess(
        url=str(data["url"]),
        expires_at=_parse_expires_at(str(data.get("expiresAt", ""))),
        media_query=data.get("mediaQuery"),
    )


def mint_dataset_thumbnail_url(client: GeopackClient, dataset_id: int) -> MintedMediaAccess:
    return mint_access_url(client, dataset_thumbnail_mint_path(dataset_id))


def fetch_binary_authenticated(
    client: GeopackClient,
    absolute_url: str,
    *,
    timeout: float = 60,
    stream: bool = False,
) -> Tuple[bytes, str]:
    """GET binary body using ``client.session`` (Bearer)."""
    response = client.session.get(absolute_url, timeout=timeout, stream=stream)
    if response.status_code == 404:
        raise GeopackAPIError(404, f"Resource not found: {absolute_url}")
    if not response.ok:
        raise GeopackAPIError.from_response(response)
    content = response.content
    if not content:
        raise GeopackAPIError(404, f"Empty response from {absolute_url}")
    mime_type = "application/octet-stream"
    if response.headers.get("Content-Type"):
        mime_type = response.headers.get("Content-Type", mime_type).split(";")[0].strip()
    return content, mime_type


def fetch_dataset_thumbnail(client: GeopackClient, dataset_id: int) -> Tuple[bytes, str]:
    """
    Fetch dataset thumbnail PNG/JPEG via ``GET /datasets/{id}/thumbnail`` with Bearer.

    Preferred for SDK, MCP ``resources/read``, and notebooks (no JWT in URL).
    """
    base = client.base_url.rstrip("/")
    url = f"{base}{dataset_thumbnail_api_path(dataset_id)}"
    return fetch_binary_authenticated(client, url, timeout=60)
