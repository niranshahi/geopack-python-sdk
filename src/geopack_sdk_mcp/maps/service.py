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
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

from .errors import SERVICE_BLOCKED, SERVICE_ERROR, MapServiceError
from .manifest import MapLayer, MapManifest, new_id
from .sources import (
    allowed_upstream,
    dataset_tile_url,
    mint_publication_url,
    portal_get_bytes,
    query_dataset_geojson,
    read_local_file,
)

logger = logging.getLogger(__name__)

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def service_enabled() -> bool:
    """``GEOPACK_MCP_MAP_SERVICE=1`` opts the process into the local service."""
    return _env_flag("GEOPACK_MCP_MAP_SERVICE")


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
            return ("json", query_dataset_geojson(self.client, int(layer.dataset_id), query=layer.query))
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
        return path.startswith("/data/") or path.startswith("/tiles/")

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
        if not self._token_ok(query):
            self._json(401, {"error": True, "code": SERVICE_ERROR, "message": "missing or invalid token"}, cors=cors)
            return
        try:
            self._route_get(parts.path, cors)
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

    def _route_get(self, path: str, cors: bool) -> None:
        service = self.service
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

        if path.startswith("/proxy/publication/"):
            self._route_publication(path[len("/proxy/publication/"):], cors)
            return

        self._json(404, {"error": True, "code": SERVICE_ERROR, "message": "not found"}, cors=cors)

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

    def _route_publication(self, rest: str, cors: bool) -> None:
        pieces = rest.split("/")
        if len(pieces) != 2:
            raise MapServiceError(SERVICE_ERROR, "path must be /proxy/publication/{id}/{protocol}")
        publication_id, protocol = pieces
        try:
            pub_id = int(publication_id)
        except ValueError as exc:
            raise MapServiceError(SERVICE_ERROR, "publication id must be an integer.") from exc
        url = mint_publication_url(self.service.client, pub_id, protocol.lower())
        status, content_type, body = self.service._proxy(url)
        self._send(status, body, content_type, cors=cors)