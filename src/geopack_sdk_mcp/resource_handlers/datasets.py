"""Dataset thumbnail resource handler."""

from __future__ import annotations

from typing import Tuple

from geopack_sdk import GeopackClient
from geopack_sdk.exceptions import GeopackAPIError


def fetch_dataset_thumbnail(
    client: GeopackClient,
    dataset_id: int,
) -> Tuple[bytes, str]:
    """
    Fetch thumbnail bytes via authenticated GET /datasets/{id}/thumbnail.

    Returns:
        (body, mime_type) e.g. (png_bytes, "image/png")
    """
    url = f"{client.base_url}/datasets/{dataset_id}/thumbnail"
    response = client.session.get(url, timeout=60)

    if response.status_code == 404:
        raise GeopackAPIError(404, f"Dataset {dataset_id} has no thumbnail or was not found.")

    if not response.ok:
        raise GeopackAPIError.from_response(response)

    content = response.content
    if not content:
        raise GeopackAPIError(404, f"Dataset {dataset_id} thumbnail is empty.")

    mime_type = "image/png"
    if response.headers.get("Content-Type"):
        mime_type = response.headers.get("Content-Type", mime_type).split(";")[0].strip()

    return content, mime_type
