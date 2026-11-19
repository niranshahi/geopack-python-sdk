"""Async publication manager — thin twin of :mod:`geopack_sdk.publications`.

State transitions stay one-shot calls: nothing here retries ``enable`` or
``reconcile`` (the audit trail should show one attempt).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .exceptions import GeopackAPIError
from .models import Publication
from .publications import _MINT_URL_KEYS, _dict, _publication_rows


class AsyncPublicationManager:
    """Dataset publications: lifecycle transitions, styles, render scopes."""

    def __init__(self, client):
        self.client = client

    async def list_for_dataset(self, dataset_id: int) -> List[Publication]:
        response_data = await self.client.get(
            f"/datasets/{dataset_id}/publications"
        )
        return _publication_rows(response_data)

    async def create(
        self, dataset_id: int, payload: Dict[str, Any]
    ) -> Publication:
        if not isinstance(payload, dict):
            raise ValueError("A publication payload must be a dict.")
        response_data = await self.client.post(
            f"/datasets/{dataset_id}/publications", json=payload
        )
        return Publication.from_api(response_data)

    async def get(self, publication_id: int) -> Publication:
        response_data = await self.client.get(f"/publications/{publication_id}")
        return Publication.from_api(response_data)

    async def update(
        self, publication_id: int, payload: Dict[str, Any]
    ) -> Publication:
        if not isinstance(payload, dict):
            raise ValueError("A publication payload must be a dict.")
        response_data = await self.client.patch(
            f"/publications/{publication_id}", json=payload
        )
        return Publication.from_api(response_data)

    async def delete(
        self, publication_id: int, *, force: bool = False
    ) -> Optional[Dict[str, Any]]:
        if force:
            return _dict(
                await self.client.delete(
                    f"/publications/{publication_id}/force"
                )
            )
        response_data = await self.client.delete(
            f"/publications/{publication_id}"
        )
        return _dict(response_data) or None

    async def enable(self, publication_id: int) -> Publication:
        response_data = await self.client.post(
            f"/publications/{publication_id}/enable"
        )
        return Publication.from_api(response_data)

    async def disable(self, publication_id: int) -> Publication:
        response_data = await self.client.post(
            f"/publications/{publication_id}/disable"
        )
        return Publication.from_api(response_data)

    async def reconcile(self, publication_id: int) -> Dict[str, Any]:
        return _dict(
            await self.client.post(f"/publications/{publication_id}/reconcile")
        )

    async def rotate_public_token(self, publication_id: int) -> Publication:
        response_data = await self.client.post(
            f"/publications/{publication_id}/public-token/rotate"
        )
        return Publication.from_api(response_data)

    async def validate_style(
        self, publication_id: int, sld: str
    ) -> Dict[str, Any]:
        if not isinstance(sld, str) or not sld.strip():
            raise ValueError("sld must be a non-empty SLD document string.")
        return _dict(
            await self.client.post(
                f"/publications/{publication_id}/style/validate",
                json={"sld": sld},
            )
        )

    async def preview_style(
        self, publication_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("A style preview payload must be a dict.")
        return _dict(
            await self.client.post(
                f"/publications/{publication_id}/style/preview", json=payload
            )
        )

    async def style_from_dataset(self, publication_id: int) -> Dict[str, Any]:
        return _dict(
            await self.client.post(
                f"/publications/{publication_id}/style/from-dataset"
            )
        )

    async def create_render_scope(
        self, publication_id: int, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        body = payload if payload is not None else {}
        if not isinstance(body, dict):
            raise ValueError("A render-scope payload must be a dict.")
        return _dict(
            await self.client.post(
                f"/publications/{publication_id}/render-scopes", json=body
            )
        )

    async def _mint(
        self,
        publication_id: int,
        protocol: str,
        payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if protocol not in _MINT_URL_KEYS:
            raise ValueError(
                "protocol must be one of " + ", ".join(_MINT_URL_KEYS) + "."
            )
        body = payload if payload is not None else {}
        if not isinstance(body, dict):
            raise ValueError("A mint payload must be a dict.")
        data = _dict(
            await self.client.post(
                f"/publications/{publication_id}/{protocol}/mint-access-url",
                json=body,
            )
        )
        url_key = _MINT_URL_KEYS[protocol]
        if not data.get(url_key):
            raise GeopackAPIError(
                502,
                f"The mint answer carried no {url_key}; the portal contract "
                "changed — do not fabricate a URL client-side.",
            )
        return data

    async def mint_tiles_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await self._mint(publication_id, "tiles", scope)

    async def mint_wms_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await self._mint(publication_id, "wms", scope)

    async def mint_wfs_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await self._mint(publication_id, "wfs", scope)

    async def mint_wmts_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await self._mint(publication_id, "wmts", scope)
