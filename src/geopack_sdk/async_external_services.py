"""Async external-service manager — twin of :mod:`geopack_sdk.external_services`."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .external_services import _dict, _style_payload


class AsyncExternalServiceManager:
    """External OGC service registrations, probes, styles and map defaults."""

    def __init__(self, client):
        self.client = client

    async def list(
        self,
        page: int = 1,
        page_size: int = 25,
        *,
        protocol: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if protocol:
            params["protocol"] = protocol
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        return _dict(await self.client.get("/external-services", params=params))

    async def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("A validation payload must be a dict.")
        return _dict(
            await self.client.post("/external-services/validate", json=payload)
        )

    async def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("A registration payload must be a dict.")
        return _dict(await self.client.post("/external-services", json=payload))

    async def get(self, service_id: int) -> Dict[str, Any]:
        return _dict(await self.client.get(f"/external-services/{service_id}"))

    async def get_edit(self, service_id: int) -> Dict[str, Any]:
        return _dict(
            await self.client.get(f"/external-services/{service_id}/edit")
        )

    async def update(
        self, service_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("An update payload must be a dict.")
        return _dict(
            await self.client.patch(f"/external-services/{service_id}", json=payload)
        )

    async def delete(self, service_id: int) -> None:
        await self.client.delete(f"/external-services/{service_id}")

    async def probe(self, service_id: int) -> Dict[str, Any]:
        return _dict(
            await self.client.post(f"/external-services/{service_id}/probe")
        )

    async def get_style(self, service_id: int) -> Dict[str, Any]:
        return _dict(
            await self.client.get(f"/external-services/{service_id}/style")
        )

    async def set_style(
        self, service_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = _style_payload(payload)
        return _dict(
            await self.client.put(
                f"/external-services/{service_id}/style", json=body
            )
        )

    async def validate_style(
        self, service_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = _style_payload(payload)
        return _dict(
            await self.client.post(
                f"/external-services/{service_id}/style/validate", json=body
            )
        )

    async def clear_style(self, service_id: int) -> Dict[str, Any]:
        return _dict(
            await self.client.delete(f"/external-services/{service_id}/style")
        )

    async def get_map_settings(self, service_id: int) -> Dict[str, Any]:
        return _dict(
            await self.client.get(
                f"/external-services/{service_id}/map-settings"
            )
        )

    async def set_map_settings(
        self, service_id: int, map_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(map_settings, dict):
            raise ValueError("Map settings must be a dict.")
        return _dict(
            await self.client.put(
                f"/external-services/{service_id}/map-settings",
                json=map_settings,
            )
        )

    async def get_publication_map_settings(
        self, publication_id: int
    ) -> Dict[str, Any]:
        return _dict(
            await self.client.get(
                f"/external-services/publications/{publication_id}/map-settings"
            )
        )

    async def set_publication_map_settings(
        self, publication_id: int, map_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(map_settings, dict):
            raise ValueError("Map settings must be a dict.")
        return _dict(
            await self.client.put(
                f"/external-services/publications/{publication_id}/map-settings",
                json=map_settings,
            )
        )
