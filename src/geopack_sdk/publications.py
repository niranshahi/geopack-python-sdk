"""Dataset publications — the OGC publication LIFECYCLE control plane (slice 014).

A publication is a portal-owned record with a status state machine
(``draft`` → ``sync_pending`` → ``active``/``degraded`` → ``disabled`` →
``deleting``). This manager drives that machine and mints render scopes; it
never touches the byte lanes (tile/WMS/WFS/WMTS ``GET`` transport is not SDK
data — see slice 014 §1.4).

Rules that shape the methods below:

* **Creation and listing live under the dataset** (``/datasets/{id}/publications``);
  every other operation targets ``/publications/{id}``. The SDK never guesses a
  publication id from a dataset id.
* ``enable``/``disable``/``reconcile`` are **state transitions, not patches**.
  A failure carries the provider's reason in the body; surface it verbatim and
  do not retry ``enable`` — the audit trail should show one attempt.
* ``style/*`` payloads are **opaque strings/dicts**: SLD is never parsed here.
* ``*/mint-access-url`` is **bearer-only** and answers a render descriptor whose
  URL key is protocol-specific (``tileUrl``/``wmsUrl``/``wfsUrl``/``wmtsUrl``),
  not a flat :class:`~geopack_sdk.models.MintedUrl`. Treat the URL like a
  credential: never log it, never reuse it across publications.
* ``delete(force=True)`` is the escape hatch for a row pinned in ``deleting``;
  it is an explicit argument, never an automatic retry.

REST API: ``/api/datasets/:datasetId/publications`` and ``/api/publications``
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .exceptions import GeopackAPIError
from .models import Publication

#: Mint endpoint suffix → the response key carrying the signed URL.
_MINT_URL_KEYS = {
    "tiles": "tileUrl",
    "wms": "wmsUrl",
    "wfs": "wfsUrl",
    "wmts": "wmtsUrl",
}


def _publication_rows(data: Any) -> List[Publication]:
    """List answers are bare arrays of records (never wrapped)."""
    if not isinstance(data, list):
        return []
    return [
        Publication.from_api(row) for row in data if isinstance(row, dict)
    ]


def _dict(data: Any) -> Dict[str, Any]:
    return data if isinstance(data, dict) else {}


class PublicationManager:
    """Dataset publications: lifecycle transitions, styles, render scopes.

    REST API:
        GET    /api/datasets/:datasetId/publications
        POST   /api/datasets/:datasetId/publications
        GET    /api/publications/:id
        PATCH  /api/publications/:id
        DELETE /api/publications/:id                   (204 or 202 deleting)
        DELETE /api/publications/:id/force             (200)
        POST   /api/publications/:id/enable
        POST   /api/publications/:id/disable
        POST   /api/publications/:id/reconcile         (202)
        POST   /api/publications/:id/public-token/rotate
        POST   /api/publications/:id/style/validate
        POST   /api/publications/:id/style/preview
        POST   /api/publications/:id/style/from-dataset
        POST   /api/publications/:id/render-scopes     (201)
        POST   /api/publications/:id/{tiles,wms,wfs,wmts}/mint-access-url  (201)
    """

    def __init__(self, client):
        self.client = client

    # --- Dataset mount: create and list only ------------------------------

    def list_for_dataset(self, dataset_id: int) -> List[Publication]:
        """Publications of one dataset (bare array; provider fields omitted)."""
        response_data = self.client.get(f"/datasets/{dataset_id}/publications")
        return _publication_rows(response_data)

    def create(
        self, dataset_id: int, payload: Dict[str, Any]
    ) -> Publication:
        """Create a publication record (starts in ``draft``).

        Useful keys: ``provider`` (``geoserver``/``portal-native``), ``kind``,
        ``protocol``, ``visibility``, ``sourceStrategy``, ``providerProfile``,
        ``configuration``, ``canonicalStyleRevision``. Provider catalog fields
        are server-generated.
        """
        if not isinstance(payload, dict):
            raise ValueError("A publication payload must be a dict.")
        response_data = self.client.post(
            f"/datasets/{dataset_id}/publications", json=payload
        )
        return Publication.from_api(response_data)

    # --- One publication ---------------------------------------------------

    def get(self, publication_id: int) -> Publication:
        """One publication by id (404 when missing or not accessible)."""
        response_data = self.client.get(f"/publications/{publication_id}")
        return Publication.from_api(response_data)

    def update(
        self, publication_id: int, payload: Dict[str, Any]
    ) -> Publication:
        """Patch mutable fields only (``PATCH``, not a full replace).

        The server accepts ``visibility``, ``configuration``,
        ``canonicalStyleRevision``, ``style``, ``publicTimeEnabled``; anything
        else is rejected rather than ignored.
        """
        if not isinstance(payload, dict):
            raise ValueError("A publication payload must be a dict.")
        response_data = self.client.patch(
            f"/publications/{publication_id}", json=payload
        )
        return Publication.from_api(response_data)

    def delete(
        self, publication_id: int, *, force: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Delete the record.

        Normally answers ``None`` (204). When a provider cleanup was enqueued
        the row stays behind and the answer is ``{"status": "deleting"}`` (202)
        — call :meth:`force_delete` only if that task is stuck. With
        ``force=True`` the row is removed regardless (200, dict ack).
        """
        if force:
            return _dict(
                self.client.delete(f"/publications/{publication_id}/force")
            )
        response_data = self.client.delete(f"/publications/{publication_id}")
        return _dict(response_data) or None

    # --- State transitions -------------------------------------------------

    def enable(self, publication_id: int) -> Publication:
        """Enable: native/proxy publications activate now, GeoServer ones go
        ``sync_pending`` until a provider task lands. No automatic retry."""
        response_data = self.client.post(f"/publications/{publication_id}/enable")
        return Publication.from_api(response_data)

    def disable(self, publication_id: int) -> Publication:
        """Disable (status becomes ``disabled``; existing links stop working)."""
        response_data = self.client.post(f"/publications/{publication_id}/disable")
        return Publication.from_api(response_data)

    def reconcile(self, publication_id: int) -> Dict[str, Any]:
        """Enqueue an async reconcile (202) → ``{publication, taskId}``.

        Provider-backed publications only; requires
        ``PUBLICATION_PROVIDERS_ENABLED=true`` (503 otherwise).
        """
        return _dict(
            self.client.post(f"/publications/{publication_id}/reconcile")
        )

    def rotate_public_token(self, publication_id: int) -> Publication:
        """Rotate the durable public access token (public publications only).

        Every previously shared public URL stops working immediately; the
        answer carries the replacement token.
        """
        response_data = self.client.post(
            f"/publications/{publication_id}/public-token/rotate"
        )
        return Publication.from_api(response_data)

    # --- Styles (opaque documents) -----------------------------------------

    def validate_style(self, publication_id: int, sld: str) -> Dict[str, Any]:
        """Server-side SLD check (``{valid, errors}``) — nothing is persisted.

        The document is sent as-is; the SDK never parses XML.
        """
        if not isinstance(sld, str) or not sld.strip():
            raise ValueError("sld must be a non-empty SLD document string.")
        return _dict(
            self.client.post(
                f"/publications/{publication_id}/style/validate",
                json={"sld": sld},
            )
        )

    def preview_style(
        self, publication_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve a per-layer style payload to its effective SLD (editor).

        ``payload`` is ``{"style": {...}}`` — the same ``{type: sld, sld}`` or
        ``{type: esri, display}`` shape the mint endpoints accept. Problems come
        back as ``{valid: false, errors}`` with HTTP 200, so the editor can
        render them inline; the SLD is returned as an opaque string.
        """
        if not isinstance(payload, dict):
            raise ValueError("A style preview payload must be a dict.")
        return _dict(
            self.client.post(
                f"/publications/{publication_id}/style/preview", json=payload
            )
        )

    def style_from_dataset(self, publication_id: int) -> Dict[str, Any]:
        """Seed an SLD editor from the dataset's portal style.

        Answers ``{sld, supported, warnings}``; ``sld`` is null when the ESRI
        renderer cannot be projected. Nothing is persisted or written back.
        """
        return _dict(
            self.client.post(
                f"/publications/{publication_id}/style/from-dataset"
            )
        )

    # --- Render scopes and minted URLs -------------------------------------

    def create_render_scope(
        self, publication_id: int, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Mint an opaque render scope (201).

        ``payload`` may carry ``queryDsl``, ``renderOptions`` and
        ``ttlSeconds`` (60–14400). The answer is a runtime descriptor holding
        the signed scope and a gateway tile URL template; provider filters are
        composed server-side and never accepted from the client.
        """
        body = payload if payload is not None else {}
        if not isinstance(body, dict):
            raise ValueError("A render-scope payload must be a dict.")
        return _dict(
            self.client.post(
                f"/publications/{publication_id}/render-scopes", json=body
            )
        )

    def _mint(
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
            self.client.post(
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

    def mint_tiles_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Mint a signed MVT tile URL template (bearer-only, 201).

        Answers the descriptor plus ``tileUrl`` and ``mediaExpiresAt``. The
        media token never outlives the render scope.
        """
        return self._mint(publication_id, "tiles", scope)

    def mint_wms_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Mint a signed WMS gateway URL (bearer-only, 201)."""
        return self._mint(publication_id, "wms", scope)

    def mint_wfs_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Mint a signed WFS gateway URL (bearer-only, 201).

        ``renderOptions.style`` is rejected server-side: WFS features are
        styled client-side.
        """
        return self._mint(publication_id, "wfs", scope)

    def mint_wmts_url(
        self, publication_id: int, scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Mint a signed WMTS gateway URL (bearer-only, 201)."""
        return self._mint(publication_id, "wmts", scope)
