"""The local map data service (slice 033, Lane A).

A stdlib ``ThreadingHTTPServer`` bound to **loopback only** on an ephemeral port,
one per MCP process, started lazily and stopped on idle or lifespan exit. It is
**opt-in** (``GEOPACK_MCP_MAP_SERVICE=1``) and always requires a per-process
token plus a strict ``Host`` check (anti-DNS-rebinding).

Endpoints (token required on every one):

``GET /``                              service index
``GET /manifest/{mapId}``              the public layer manifest
``GET /data/{layerId}``                GeoJSON (portal dataset / inline) or a local file
``GET /tiles/{layerId}/{z}/{x}/{y}.pbf`` portal-native MVT or a minted publication tile
``GET /rasters/{layerId}/{z}/{x}/{y}.png`` portal-rendered raster PNG tile (PostGIS / filesystem)
``GET /local/{layerId}``               an allow-listed local file
``GET /proxy/publication/{id}/{proto}`` minted WMS/WMTS/MVT/WFS passthrough
``POST /shutdown``                     stop the server

The portal credential stays inside the proxy; only this low-sensitivity session
token crosses to the browser (N5).
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from .errors import SERVICE_BLOCKED, SERVICE_ERROR, MapServiceError
from .manifest import MapLayer, MapManifest, new_id
from . import viewer
from .sources import (
    allowed_upstream,
    dataset_cog_url,
    dataset_raster_tile_url,
    dataset_tile_url,
    merge_query,
    mint_publication_url,
    portal_get_bytes,
    portal_range_get,
    query_dataset_geojson,
    read_local_file,
)

logger = logging.getLogger(__name__)

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

#: Content-Security-Policy for the built-in viewer page (local-only page).
VIEWER_CSP = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:"
)


def _expired_link_html(message: str) -> bytes:
    """A tiny, self-contained page shown when a viewer link is stale/invalid.

    The viewer shell is token-free by design (the token rides ``?t=`` or the URL
    fragment), so an expired/foreign link used to answer 200 and leave the page
    blank with only a small banner. Answering a clear page instead makes the
    failure legible (issue report 2026-11-24, N6).
    """
    body = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Geopack map - link expired</title>"
        "<style>body{font-family:system-ui,'Segoe UI',Arial,sans-serif;margin:0;"
        "padding:2rem;color:#111827;background:#f9fafb}h1{font-size:1.15rem;margin:0 0 .6rem}"
        "p{max-width:46rem;line-height:1.55;color:#374151}"
        "code{background:#eef2f7;padding:.05rem .35rem;border-radius:.25rem}</style>"
        "</head><body><h1>This map link is no longer valid</h1>"
        f"<p>{message}</p></body></html>"
    )
    return body.encode("utf-8")


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def service_enabled() -> bool:
    """``GEOPACK_MCP_MAP_SERVICE=1`` opts the process into the local service."""
    return _env_flag("GEOPACK_MCP_MAP_SERVICE")


def resolve_assets(
    assets: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, str], Optional[str]]:
    """Return ``(asset_urls, vendored_dir)`` for the viewer runtime.

    Default = the pinned OpenLayers CDN (no build step). A directory at
    ``GEOPACK_MCP_MAP_ASSETS`` (holding ``ol.js`` + ``ol.css``) is served
    locally instead — the offline/airgapped mode.
    """
    if assets is not None:
        return assets, None
    configured = (os.getenv("GEOPACK_MCP_MAP_ASSETS") or "").strip()
    if configured and os.path.isdir(configured):
        return (
            {
                "ol_js": "/viewer/asset/ol.js",
                "ol_css": "/viewer/asset/ol.css",
                "gt_js": "/viewer/asset/geotiff.js",
            },
            os.path.realpath(configured),
        )
    return dict(viewer.CDN_ASSETS), None


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    #: A fixed GEOPACK_MCP_MAP_PORT must be re-bindable after an idle restart;
    #: the token + Host guard (not SO_REUSEADDR) is the real protection.
    allow_reuse_address = True


class LocalService:
    """Owns the loopback server, the token and the in-memory map manifests."""

    host = "127.0.0.1"

    def __init__(
        self,
        client: Any,
        *,
        token: Optional[str] = None,
        cors: Optional[bool] = None,
        map_root: Optional[str] = None,
        proxy_hosts: Optional[List[str]] = None,
        idle_timeout: Optional[int] = None,
        port: Optional[int] = None,
        templates_dir: Optional[str] = None,
        assets: Optional[Dict[str, str]] = None,
    ):
        self.client = client
        self.token = token or secrets.token_urlsafe(32)
        self.cors = _env_flag("GEOPACK_MCP_MAP_CORS") if cors is None else bool(cors)
        self.map_root = map_root if map_root is not None else os.getenv("GEOPACK_MCP_MAP_ROOT")
        if proxy_hosts is None:
            raw = os.getenv("GEOPACK_MCP_PROXY_HOSTS", "")
            proxy_hosts = [part.strip() for part in raw.split(",") if part.strip()]
        self.proxy_hosts = list(proxy_hosts)
        if idle_timeout is None:
            try:
                idle_timeout = int(os.getenv("GEOPACK_MCP_MAP_IDLE_TIMEOUT", "1800"))
            except ValueError:
                idle_timeout = 1800
        self.idle_timeout = max(0, idle_timeout)
        if port is None:
            try:
                port = int(os.getenv("GEOPACK_MCP_MAP_PORT", "0") or "0")
            except ValueError:
                port = 0
        self.requested_port = max(0, min(int(port), 65535))
        self.templates_dir = (
            templates_dir if templates_dir is not None else viewer.user_templates_dir()
        )
        self.assets, self.assets_dir = resolve_assets(assets)
        self.maps: Dict[str, MapManifest] = {}
        self._server: Optional[_Server] = None
        self._thread: Optional[threading.Thread] = None
        self._idle_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_activity = 0.0
        self.port: Optional[int] = None

    # --- lifecycle ---------------------------------------------------------

    @property
    def base_url(self) -> str:
        if self.port is None:
            raise MapServiceError(SERVICE_ERROR, "the map service has not started.")
        return f"http://{self.host}:{self.port}"

    def start(self) -> str:
        if self._server is not None:
            return self.base_url
        try:
            server = _Server((self.host, self.requested_port), _Handler)
        except OSError as exc:
            raise MapServiceError(
                SERVICE_BLOCKED,
                f"cannot bind a loopback socket on port {self.requested_port}: "
                f"{exc.strerror or 'OS refused the bind'}",
            ) from exc
        server.service = self  # type: ignore[attr-defined]
        self._server = server
        self.port = int(server.server_address[1])
        self.touch()
        self._thread = threading.Thread(
            target=server.serve_forever, name="geopack-map-service", daemon=True
        )
        self._thread.start()
        if self.idle_timeout > 0:
            self._idle_thread = threading.Thread(
                target=self._idle_loop, name="geopack-map-idle", daemon=True
            )
            self._idle_thread.start()
        return self.base_url

    def stop(self) -> None:
        self._stop_event.set()
        server = self._server
        self._server = None
        if server is not None:
            server.shutdown()
            server.server_close()
        self.port = None

    def touch(self) -> None:
        import time

        self._last_activity = time.monotonic()

    def _idle_loop(self) -> None:
        import time

        while not self._stop_event.wait(min(60, max(5, self.idle_timeout // 2))):
            if time.monotonic() - self._last_activity >= self.idle_timeout:
                logger.info("Map service idle for %ss — stopping", self.idle_timeout)
                self.stop()
                return

    # --- maps & layers -----------------------------------------------------

    def create_map(self, title: str = "Geopack map") -> MapManifest:
        manifest = MapManifest(map_id=new_id("map"), title=title or "Geopack map")
        self.maps[manifest.map_id] = manifest
        return manifest

    def find_map(self, map_id: str) -> Optional[MapManifest]:
        return self.maps.get(map_id)

    def find_layer(self, layer_id: str) -> Optional[MapLayer]:
        for manifest in self.maps.values():
            if layer_id in manifest.layers:
                return manifest.layers[layer_id]
        return None

    # --- helpers used by the handler --------------------------------------

    def _proxy(self, url: str) -> Any:
        if not allowed_upstream(url, str(getattr(self.client, "base_url", "")), self.proxy_hosts):
            raise MapServiceError(
                SERVICE_ERROR,
                "the upstream host is not allow-listed (set GEOPACK_MCP_PROXY_HOSTS).",
            )
        return portal_get_bytes(self.client, url)

    def layer_data(self, layer: MapLayer) -> Any:
        if layer.kind == "portal-dataset":
            return (
                "json",
                query_dataset_geojson(
                    self.client,
                    int(layer.dataset_id),
                    query=layer.query,
                    limit=layer.limit,
                ),
            )
        if layer.kind == "inline-geometry":
            return ("json", layer.geojson or {})
        if layer.kind == "local-file":
            body, content_type = read_local_file(self.map_root, str(layer.path))
            return ("bytes", (content_type, body))
        raise MapServiceError(
            SERVICE_ERROR,
            "a portal-publication layer is served by /tiles, not /data.",
            key="layer",
        )

    def layer_tile(self, layer: MapLayer, z: int, x: int, y: int) -> Any:
        if layer.kind == "portal-dataset":
            url = dataset_tile_url(self.client, int(layer.dataset_id), z, x, y)
            return self._proxy(url)
        if layer.kind == "portal-publication":
            template = mint_publication_url(self.client, int(layer.publication_id), "tiles")
            url = (
                template.replace("{z}", str(z))
                .replace("{x}", str(x))
                .replace("{y}", str(y))
            )
            return self._proxy(url)
        raise MapServiceError(
            SERVICE_ERROR, "this layer kind has no tile endpoint.", key="layer"
        )

    def layer_raster_tile(self, layer: MapLayer, z: int, x: int, y: int) -> Any:
        """Proxy one PNG raster tile from the portal's raster-tile lane.

        The portal renders a PostGIS (or filesystem) raster server-side — applying
        the dataset's saved ``display`` — so the browser never sees the raw pixels
        or the portal credential. This is the lane for a raster that is neither
        published (no WMS/WMTS) nor a COG.
        """
        if layer.kind != "portal-dataset" or layer.dataset_id is None:
            raise MapServiceError(
                SERVICE_ERROR,
                "an HTTP raster-tile layer must be a portal-dataset.",
                key="layer",
            )
        url = dataset_raster_tile_url(
            self.client,
            int(layer.dataset_id),
            z,
            x,
            y,
            display=layer.raster_display,
            ref_zoom=layer.ref_zoom,
        )
        return self._proxy(url)

    def cog_resource(
        self, ref: str, range_header: Optional[str]
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Byte-serve a dataset's COG through the portal, forwarding a ``Range``."""
        try:
            dataset_id = int(str(ref).split("/", 1)[0])
        except (TypeError, ValueError) as exc:
            raise MapServiceError(
                SERVICE_ERROR, "the COG path must be /cog/{datasetId}.", key="cog"
            ) from exc
        url = dataset_cog_url(self.client, dataset_id)
        if not allowed_upstream(
            url, str(getattr(self.client, "base_url", "")), self.proxy_hosts
        ):
            raise MapServiceError(
                SERVICE_ERROR,
                "the upstream host is not allow-listed (set GEOPACK_MCP_PROXY_HOSTS).",
            )
        return portal_range_get(self.client, url, range_header=range_header)

    # --- viewer assets & templates (Lane B) -------------------------------

    def user_css_url(self) -> Optional[str]:
        if self.templates_dir and os.path.isfile(
            os.path.join(self.templates_dir, viewer._USER_CSS_FILE)
        ):
            return f"{self.base_url}/viewer/asset/viewer.css"
        return None

    def viewer_asset(self, name: str) -> Tuple[bytes, str]:
        """An allow-listed viewer asset.

        ``ol.js``/``ol.css`` come from the vendored asset dir. ``viewer.css`` and the
        shared ``viewer.js`` runtime prefer a Tier-2 user file and fall back to the
        shipped default (the runtime ships with the package, so it is always served).
        """
        if name not in {"ol.js", "ol.css", "geotiff.js", "viewer.css", "viewer.js"}:
            raise MapServiceError(SERVICE_ERROR, "unknown viewer asset.", key="asset")
        content_type = "text/css" if name.endswith(".css") else "text/javascript"
        if name in {"viewer.css", "viewer.js"}:
            for base in (self.templates_dir, viewer.DEFAULT_TEMPLATES_DIR):
                if not base:
                    continue
                base_real = os.path.realpath(base)
                path = os.path.realpath(os.path.join(base_real, name))
                if os.path.commonpath([base_real, path]) == base_real and os.path.isfile(path):
                    with open(path, "rb") as handle:
                        return handle.read(), content_type
            raise MapServiceError(SERVICE_ERROR, "viewer asset not found.", key="asset")
        if not self.assets_dir:
            raise MapServiceError(
                SERVICE_ERROR, "viewer assets are not vendored locally.", key="asset"
            )
        base_real = os.path.realpath(self.assets_dir)
        path = os.path.realpath(os.path.join(base_real, name))
        if os.path.commonpath([base_real, path]) != base_real or not os.path.isfile(path):
            raise MapServiceError(SERVICE_ERROR, "viewer asset not found.", key="asset")
        with open(path, "rb") as handle:
            return handle.read(), content_type


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "GeopackMapService/1"

    # Never log a request line: it may carry the session token.
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    @property
    def service(self) -> LocalService:
        return self.server.service  # type: ignore[attr-defined]

    # --- plumbing ----------------------------------------------------------

    def _is_cors_path(self, path: str) -> bool:
        return (
            path.startswith("/data/")
            or path.startswith("/tiles/")
            or path.startswith("/rasters/")
            or path.startswith("/cog/")
        )

    def _is_public_path(self, path: str) -> bool:
        """The viewer shell and its assets carry no secret; the token travels in
        the URL query (``?t=``, validated and re-embedded by the server) or the
        fragment (``#t=``) and is used by the page for the token-gated
        manifest/data calls."""
        if path.startswith("/viewer/"):
            return True
        return path.startswith("/map/") and not path.endswith("/manifest.json")

    def _headers_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        hostname = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        if hostname.startswith("[") and "]" in hostname:
            hostname = hostname[: hostname.index("]") + 1]
        return hostname.lower() in _ALLOWED_HOSTS

    def _token_ok(self, query: Dict[str, List[str]]) -> bool:
        supplied = None
        if query.get("t"):
            supplied = query["t"][0]
        if not supplied:
            supplied = self.headers.get("X-Geopack-Map-Token")
        return bool(supplied) and hmac.compare_digest(str(supplied), self.service.token)

    def _send(self, status: int, body: bytes, content_type: str, *,
              cors: bool = False, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if cors and self.service.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "X-Geopack-Map-Token")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any, *, cors: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", cors=cors)

    def _error(self, exc: BaseException, *, cors: bool = False) -> None:
        if isinstance(exc, MapServiceError):
            payload = {"error": True, "code": exc.code, "message": exc.message}
            if exc.hint:
                payload["hint"] = exc.hint
            status = 404 if exc.code == SERVICE_ERROR else 503
        else:
            payload = {"error": True, "code": SERVICE_ERROR, "message": "local map service error"}
            status = 500
        self._json(status, payload, cors=cors)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.service.touch()
        self.send_response(204)
        if self.service.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Geopack-Map-Token")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # --- dispatch ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self.service.touch()
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        cors = self._is_cors_path(parts.path)
        if not self._headers_ok():
            self._json(403, {"error": True, "code": SERVICE_ERROR, "message": "host not allowed"})
            return
        if not self._is_public_path(parts.path) and not self._token_ok(query):
            self._json(401, {"error": True, "code": SERVICE_ERROR, "message": "missing or invalid token"}, cors=cors)
            return
        try:
            self._route_get(parts.path, cors, query)
        except MapServiceError as exc:
            self._error(exc, cors=cors)
        except Exception:  # noqa: BLE001 - never leak a traceback
            self._error(MapServiceError(SERVICE_ERROR, "unexpected map-service error"), cors=cors)

    def do_POST(self) -> None:  # noqa: N802
        self.service.touch()
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        if not self._headers_ok() or not self._token_ok(query):
            self._json(401, {"error": True, "code": SERVICE_ERROR, "message": "unauthorized"})
            return
        if parts.path == "/shutdown":
            self._json(200, {"stopped": True})
            threading.Thread(target=self.service.stop, daemon=True).start()
            return
        self._json(404, {"error": True, "code": SERVICE_ERROR, "message": "not found"})

    def _route_get(self, path: str, cors: bool, query: Optional[Dict[str, List[str]]] = None) -> None:
        service = self.service
        query = query or {}
        if path == "/" or path == "":
            self._json(
                200,
                {
                    "service": "geopack-map-service",
                    "maps": [
                        {"mapId": m.map_id, "title": m.title, "layers": len(m.layers)}
                        for m in service.maps.values()
                    ],
                },
                cors=cors,
            )
            return

        if path.startswith("/manifest/"):
            manifest = service.find_map(path[len("/manifest/"):])
            if manifest is None:
                raise MapServiceError(SERVICE_ERROR, "unknown map id.")
            self._json(200, manifest.public(service.base_url), cors=cors)
            return

        if path.startswith("/map/"):
            self._route_map(path[len("/map/"):], cors, query)
            return

        if path.startswith("/viewer/"):
            self._route_viewer_asset(path[len("/viewer/"):])
            return

        if path.startswith("/data/"):
            layer = service.find_layer(path[len("/data/"):])
            if layer is None:
                raise MapServiceError(SERVICE_ERROR, "unknown layer id.")
            kind, value = service.layer_data(layer)
            if kind == "json":
                self._json(200, value, cors=cors)
            else:
                content_type, body = value
                self._send(200, body, content_type, cors=cors)
            return

        if path.startswith("/local/"):
            layer = service.find_layer(path[len("/local/"):])
            if layer is None or layer.kind != "local-file":
                raise MapServiceError(SERVICE_ERROR, "unknown local layer id.")
            content_type, body = read_local_file(service.map_root, str(layer.path))
            self._send(200, body, content_type)
            return

        if path.startswith("/tiles/"):
            self._route_tiles(path[len("/tiles/"):], cors)
            return

        if path.startswith("/rasters/"):
            self._route_rasters(path[len("/rasters/"):], cors)
            return

        if path.startswith("/cog/"):
            self._route_cog(path[len("/cog/"):], cors)
            return

        if path.startswith("/proxy/publication/"):
            self._route_publication(path[len("/proxy/publication/"):], cors, query)
            return

        self._json(404, {"error": True, "code": SERVICE_ERROR, "message": "not found"}, cors=cors)

    def _route_map(self, rest: str, cors: bool,
                   query: Optional[Dict[str, List[str]]] = None) -> None:
        service = self.service
        if rest.endswith("/manifest.json"):
            manifest = service.find_map(rest[: -len("/manifest.json")])
            if manifest is None:
                raise MapServiceError(SERVICE_ERROR, "unknown map id.")
            self._json(200, manifest.public(service.base_url), cors=cors)
            return
        map_id = rest.strip("/")
        manifest = service.find_map(map_id)
        if manifest is None:
            # The shell route answers a readable "expired" page, not a JSON 404 —
            # a human opened this link in a browser (N6).
            self._send(
                404,
                _expired_link_html(
                    "This map no longer exists. Maps are held in memory by the local map "
                    "service and are re-created each time it starts. Run "
                    "<code>geopack_sdk_show_map</code> again to get a fresh link."
                ),
                "text/html; charset=utf-8",
            )
            return
        template = manifest.options or viewer.load_template(service.templates_dir)[0]
        html_template, _viewer_source, _viewer_warnings = viewer.load_viewer_html(
            service.templates_dir
        )
        # A query token is embedded only when it is VALID (no reflected XSS); this
        # keeps the viewer working when a host drops the URL fragment.
        embedded = None
        supplied = (query.get("t") or [None])[0] if query else None
        if supplied:
            if hmac.compare_digest(str(supplied), service.token):
                embedded = str(supplied)
            else:
                # A `?t=` token is VISIBLE to the server, so a wrong/expired one is
                # refused here (401 + a readable page) instead of serving a shell
                # that would only fail its manifest fetch (N6). A fragment token
                # (#t=) never reaches the server; the viewer's own 401 handling
                # covers that case.
                self._send(
                    401,
                    _expired_link_html(
                        "The session token in this link is invalid or has expired. The local "
                        "map service issues a fresh token on every start (and after its idle "
                        "timeout), so a saved link stops working after a restart. Run "
                        "<code>geopack_sdk_show_map</code> again to get a fresh link."
                    ),
                    "text/html; charset=utf-8",
                )
                return
        html = viewer.render_viewer_html(
            title=manifest.title or template.get("title") or "Geopack map",
            manifest_url=f"{service.base_url}/map/{map_id}/manifest.json",
            template=template,
            assets=service.assets,
            user_css=service.user_css_url(),
            embedded_token=embedded,
            html_template=html_template,
        )
        self._send(
            200,
            html.encode("utf-8"),
            "text/html; charset=utf-8",
            extra={
                "Content-Security-Policy": VIEWER_CSP,
                # Origin-only on cross-origin requests: OSM gets the Referer it
                # requires while the `?t=` token (path/query) is never sent out.
                "Referrer-Policy": "strict-origin-when-cross-origin",
            },
        )

    def _route_viewer_asset(self, rest: str) -> None:
        name = rest.strip("/")
        if name.startswith("asset/"):
            name = name[len("asset/"):]
        body, content_type = self.service.viewer_asset(name)
        self._send(200, body, content_type)

    def _route_cog(self, rest: str, cors: bool) -> None:
        """Proxy a COG byte range. The browser (ol/source/GeoTIFF) sends Range. """
        range_header = self.headers.get("Range")
        status, headers, body = self.service.cog_resource(rest, range_header)
        content_type = headers.get("Content-Type", "image/tiff")
        extra = {key: value for key, value in headers.items() if key != "Content-Type"}
        self._send(status, body, content_type, cors=cors, extra=extra)

    def _route_tiles(self, rest: str, cors: bool) -> None:
        pieces = rest.split("/")
        if len(pieces) != 4:
            raise MapServiceError(SERVICE_ERROR, "tile path must be /tiles/{layer}/{z}/{x}/{y}.pbf")
        layer_id, z, x, y_ext = pieces
        y = y_ext.rsplit(".", 1)[0]
        layer = self.service.find_layer(layer_id)
        if layer is None:
            raise MapServiceError(SERVICE_ERROR, "unknown layer id.")
        try:
            tile = self.service.layer_tile(layer, int(z), int(x), int(y))
        except ValueError as exc:
            raise MapServiceError(SERVICE_ERROR, "tile coordinates must be integers.") from exc
        status, content_type, body = tile
        self._send(status, body, content_type or "application/vnd.mapbox-vector-tile", cors=cors)

    def _route_rasters(self, rest: str, cors: bool) -> None:
        """Proxy one portal-rendered PNG raster tile (XYZ grid)."""
        pieces = rest.split("/")
        if len(pieces) != 4:
            raise MapServiceError(
                SERVICE_ERROR, "raster tile path must be /rasters/{layer}/{z}/{x}/{y}.png"
            )
        layer_id, z, x, y_ext = pieces
        y = y_ext.rsplit(".", 1)[0]
        layer = self.service.find_layer(layer_id)
        if layer is None:
            raise MapServiceError(SERVICE_ERROR, "unknown layer id.")
        try:
            tile = self.service.layer_raster_tile(layer, int(z), int(x), int(y))
        except ValueError as exc:
            raise MapServiceError(SERVICE_ERROR, "tile coordinates must be integers.") from exc
        status, content_type, body = tile
        self._send(status, body, content_type or "image/png", cors=cors)

    def _route_publication(self, rest: str, cors: bool,
                           query: Optional[Dict[str, List[str]]] = None) -> None:
        pieces = rest.split("/")
        if len(pieces) != 2:
            raise MapServiceError(SERVICE_ERROR, "path must be /proxy/publication/{id}/{protocol}")
        publication_id, protocol = pieces
        try:
            pub_id = int(publication_id)
        except ValueError as exc:
            raise MapServiceError(SERVICE_ERROR, "publication id must be an integer.") from exc
        url = mint_publication_url(self.service.client, pub_id, protocol.lower())
        forwarded = {k: v for k, v in (query or {}).items() if k != "t"}
        url = merge_query(url, forwarded)
        status, content_type, body = self.service._proxy(url)
        self._send(status, body, content_type, cors=cors)