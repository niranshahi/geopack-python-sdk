"""Dataset thumbnail resource handler."""

from __future__ import annotations

from typing import Tuple

from geopack_sdk import GeopackClient
from geopack_sdk.media_access import fetch_dataset_thumbnail as sdk_fetch_dataset_thumbnail


def fetch_dataset_thumbnail(
    client: GeopackClient,
    dataset_id: int,
) -> Tuple[bytes, str]:
    """
    Fetch thumbnail bytes via Bearer-authenticated GET /datasets/{id}/thumbnail.

    Returns:
        (body, mime_type) e.g. (png_bytes, "image/png")
    """
    return sdk_fetch_dataset_thumbnail(client, dataset_id)
