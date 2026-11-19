"""External OGC services — the registration CONTROL PLANE (slice 014).

An external service is a cataloged WMS/WMTS/WFS endpoint the portal proxies.
This manager registers, edits, probes and deletes those records, and owns the
two small configuration lanes attached to them: the external **style payload**
and the **map-settings** defaults.

Rules worth knowing before calling:

* The upstream URL and credentials are **never returned** by any endpoint; the
  DTO is sanitized server-side. ``get_edit`` is the closest thing to a raw
  record, and even it masks secrets.
* ``validate`` (no id) probes a candidate registration *before* create;
  ``probe(id)`` re-probes an existing one. Both are live network operations and
  can be slow — give them a longer timeout than a JSON read.
* **SLD is not supported here** (``EXTERNAL_SLD_UNSUPPORTED``). A style payload
  is either ``{type: "client-renderer", renderer: {...}}`` or
  ``{type: "wms-named-style", bindings: [...]}``; the SDK refuses an ``sld``
  key client-side rather than shipping a request the server will 400.
* ``validate`` and ``validate_style`` answer **HTTP 400 when invalid**, so an
  invalid candidate raises :class:`~geopack_sdk.exceptions.GeopackAPIError`
  with the field errors in its details. A 200 means valid.
* Map settings are stored on the Dataset-bound publication. The write is a
  Dataset management act (owner or admin), not just ``external_service:update``.

REST API: ``/api/external-services``
"""

from __future__ import annotations

from typing import Any, Dict, Optional

#: Style payload types the portal accepts (SLD is deliberately absent).
_STYLE_TYPES = frozenset({"client-renderer", "wms-named-style"})


def _dict(data: Any) -> Dict[str, Any]:
    return data if isinstance(data, dict) else {}


def _style_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reject SLD early; otherwise pass the envelope through unchanged."""
    if not isinstance(payload, dict):
        raise ValueError("A style payload must be a dict.")
    if "sld" in payload:
        raise ValueError(
            "SLD is not supported for external services (EXTERNAL_SLD_UNSUPPORTED): "
            "use {type: 'client-renderer', renderer} or "
            "{type: 'wms-named-style', bindings}."
        )
    if payload.get("type") not in _STYLE_TYPES:
        raise ValueError(
            "type must be one of " + ", ".join(sorted(_STYLE_TYPES)) + "."
        )
    return payload


class ExternalServiceManager:
    """External OGC service registrations, probes, styles and map defaults.

    REST API (all under ``/api/external-services``):
        GET    /
        POST   /validate
        POST   /
        GET    /:id
        GET    /:id/edit
        PATCH  /:id
        DELETE /:id                                   (204)
        POST   /:id/probe
        GET    /:id/style                             (``{externalStyle}``)
        PUT    /:id/style
        POST   /:id/style/validate
        DELETE /:id/style
        GET    /:id/map-settings                      (``{mapSettings}``)
        PUT    /:id/map-settings
        GET    /publications/:publicationId/map-settings
        PUT    /publications/:publicationId/map-settings
    """

    def __init__(self, client):
        self.client = client

    # --- Registrations -----------------------------------------------------

    def list(
        self,
        page: int = 1,
        page_size: int = 25,
        *,
        protocol: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Paginated registrations of the caller's organization.

        Answers ``{items, total, page, pageSize}`` with sanitized DTOs.
        ``page_size`` is capped at 100 by the route.
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if protocol:
            params["protocol"] = protocol
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        return _dict(self.client.get("/external-services", params=params))

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Probe a candidate endpoint WITHOUT persisting anything.

        Requires ``url`` and ``protocol`` (plus optional ``authType`` and
        ``credentials``). An invalid or unreachable endpoint answers HTTP 400
        and therefore raises :class:`GeopackAPIError`; a 200 carries
        ``{ok: true, summary}`` with the normalized capabilities.
        """
        if not isinstance(payload, dict):
            raise ValueError("A validation payload must be a dict.")
        return _dict(self.client.post("/external-services/validate", json=payload))

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Register an external service (201, sanitized DTO).

        Required: ``name``, ``title``, ``url``, ``protocol``. Optional:
        ``description``, ``keywords``, ``authType``, ``credentials``,
        ``workgroupId``, ``visibility``, ``sourceDatasetId`` and ``mapSettings``
        (validated against the freshly-fetched capabilities). The server
        re-validates the upstream before committing.
        """
        if not isinstance(payload, dict):
            raise ValueError("A registration payload must be a dict.")
        return _dict(self.client.post("/external-services", json=payload))

    def get(self, service_id: int) -> Dict[str, Any]:
        """One registration (sanitized — no upstream URL, no credentials)."""
        return _dict(self.client.get(f"/external-services/{service_id}"))

    def get_edit(self, service_id: int) -> Dict[str, Any]:
        """The edit DTO (closest to raw; secrets stay masked server-side)."""
        return _dict(self.client.get(f"/external-services/{service_id}/edit"))

    def update(
        self, service_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Patch mutable fields; a ``url``/``authType`` change re-validates.

        Server-managed fields (``upstreamUrl``, ``credentialPayload``,
        ``capabilitiesCache``) must not be sent.
        """
        if not isinstance(payload, dict):
            raise ValueError("An update payload must be a dict.")
        return _dict(self.client.patch(f"/external-services/{service_id}", json=payload))

    def delete(self, service_id: int) -> None:
        """Delete the registration and its linked publications (204)."""
        self.client.delete(f"/external-services/{service_id}")

    def probe(self, service_id: int) -> Dict[str, Any]:
        """Re-probe upstream capabilities and refresh health state.

        Live network operation — it can be slow. The answer is the refreshed
        DTO including ``healthState``.
        """
        return _dict(self.client.post(f"/external-services/{service_id}/probe"))

    # --- Style payload (no SLD) -------------------------------------------

    def get_style(self, service_id: int) -> Dict[str, Any]:
        """Stored style payload: ``{externalStyle}`` (null when none)."""
        return _dict(self.client.get(f"/external-services/{service_id}/style"))

    def set_style(
        self, service_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and persist the style payload on the linked publication.

        ``payload`` is ``{type: "client-renderer", renderer: {...}}`` or
        ``{type: "wms-named-style", bindings: [...]}``. SLD is refused both
        here and server-side (``EXTERNAL_SLD_UNSUPPORTED``).
        """
        body = _style_payload(payload)
        return _dict(
            self.client.put(f"/external-services/{service_id}/style", json=body)
        )

    def validate_style(
        self, service_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check a style payload against the cached capabilities (no persist).

        A 200 answers ``{valid: true, externalStyle}``; a 400 answers
        ``{valid: false, errors}`` and therefore raises ``GeopackAPIError``.
        """
        body = _style_payload(payload)
        return _dict(
            self.client.post(
                f"/external-services/{service_id}/style/validate", json=body
            )
        )

    def clear_style(self, service_id: int) -> Dict[str, Any]:
        """Clear the stored style payload: ``{cleared: bool}``."""
        return _dict(self.client.delete(f"/external-services/{service_id}/style"))

    # --- Map-settings defaults (two scopes) --------------------------------

    def get_map_settings(self, service_id: int) -> Dict[str, Any]:
        """Saved map-layer defaults of a registration: ``{mapSettings}``."""
        return _dict(
            self.client.get(f"/external-services/{service_id}/map-settings")
        )

    def set_map_settings(
        self, service_id: int, map_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save map-layer defaults (WMS/WMTS: ``{rootVisible, layers, groups,
        order}``; WFS: ``{rootVisible, featureType}``).

        The body is the map-settings object itself, not a wrapper. Names are
        checked against the cached capabilities server-side.
        """
        if not isinstance(map_settings, dict):
            raise ValueError("Map settings must be a dict.")
        return _dict(
            self.client.put(
                f"/external-services/{service_id}/map-settings",
                json=map_settings,
            )
        )

    def get_publication_map_settings(
        self, publication_id: int
    ) -> Dict[str, Any]:
        """Map defaults keyed by the external publication id (map layers know
        the publication, not the legacy registration id)."""
        return _dict(
            self.client.get(
                f"/external-services/publications/{publication_id}/map-settings"
            )
        )

    def set_publication_map_settings(
        self, publication_id: int, map_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save map defaults via the publication scope (same body shape)."""
        if not isinstance(map_settings, dict):
            raise ValueError("Map settings must be a dict.")
        return _dict(
            self.client.put(
                f"/external-services/publications/{publication_id}/map-settings",
                json=map_settings,
            )
        )
