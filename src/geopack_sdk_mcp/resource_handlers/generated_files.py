"""Generated file download resource handler."""

from __future__ import annotations

from typing import Tuple

from geopack_sdk import GeopackClient
from geopack_sdk.exceptions import GeopackAPIError


def fetch_generated_file_bytes(
    client: GeopackClient,
    generated_file_id: int,
) -> Tuple[bytes, str]:
    """Stream file body via GET /generated-files/{id}/download (Bearer auth)."""
    base = client.base_url.rstrip("/")
    url = f"{base}/generated-files/{generated_file_id}/download"
    response = client.session.get(url, stream=True, timeout=300)

    if response.status_code == 404:
        raise GeopackAPIError(404, f"Generated file {generated_file_id} not found.")

    if not response.ok:
        raise GeopackAPIError.from_response(response)

    content = response.content
    if not content:
        raise GeopackAPIError(404, f"Generated file {generated_file_id} is empty.")

    mime_type = "application/octet-stream"
    if response.headers.get("Content-Type"):
        mime_type = response.headers.get("Content-Type", mime_type).split(";")[0].strip()

    return content, mime_type
