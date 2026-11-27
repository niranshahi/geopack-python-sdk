"""Slice 033 Lane A — the local map data service (binding, auth, endpoints)."""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from geopack_sdk_mcp.maps import get_or_start_service, reset_for_tests
from geopack_sdk_mcp.maps.errors import MapServiceError
from geopack_sdk_mcp.maps.manifest import layer_from_spec
from geopack_sdk_mcp.maps.service import LocalService

PORTAL = "http://portal.example/api"
PORTAL_TOKEN = "PORTAL-SECRET-xyz"


class _FakeResponse:
    def __init__(self, body=b"\x1a\x00tile", content_type="application/vnd.mapbox-vector-tile",
                 status=200, ok=True):
        self.content = body
        self.headers = {"Content-Type": content_type}
        self.status_code = status
        self.ok = ok


class _Auth:
    token = PORTAL_TOKEN


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}})
        if (headers or {}).get("Range"):
            response = _FakeResponse(body=b"II*\x00", content_type="image/tiff", status=206)
            response.headers = {
                "Content-Type": "image/tiff",
                "Content-Range": "bytes 0-4/1000",
                "Accept-Ranges": "bytes",
            }
            return response
        return _FakeResponse()


class _Datasets:
    def __init__(self):
        self.queries = []

    def query(self, dataset_id, *args, **kwargs):
        self.queries.append({"dataset_id": dataset_id, "args": args, "kwargs": kwargs})
        return {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"id": 1}, "geometry": None}
            ],
        }


class _Publications:
    def __init__(self, template):
        self.template = template

    def mint_tiles_url(self, publication_id):
        return {"tileUrl": self.template, "mediaExpiresAt": "2099-01-01T00:00:00Z"}


class _FakeClient:
    base_url = PORTAL

    def __init__(self, mint_template=f"{PORTAL}/geo/{{z}}/{{x}}/{{y}}.pbf"):
        self.auth = _Auth()
        self.session = _Session()
        self.datasets = _Datasets()
        self.publications = _Publications(mint_template)


def _request(port, path, *, token=None, host=None, method="GET", range_header=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if token:
        headers["X-Geopack-Map-Token"] = token
    if host:
        headers["Host"] = host
    if range_header:
        headers["Range"] = range_header
    conn.request(method, path, headers=headers)
    response = conn.getresponse()
    body = response.read()
    status = response.status
    got = dict(response.getheaders())
    conn.close()
    return status, got, body


def _service(**kwargs):
    mint_template = kwargs.pop("mint_template", f"{PORTAL}/geo/{{z}}/{{x}}/{{y}}.pbf")
    client = _FakeClient(mint_template=mint_template)
    options = {"idle_timeout": 0, "cors": False}
    options.update(kwargs)
    service = LocalService(client, **options)
    service.start()
    return service


INLINE = {"type": "Point", "coordinates": [51.4, 35.7]}


class BindingTest(unittest.TestCase):
    def test_binds_loopback_only_on_an_ephemeral_port(self):
        service = _service()
        try:
            self.assertEqual(service._server.server_address[0], "127.0.0.1")
            self.assertGreater(service.port, 0)
            self.assertTrue(service.base_url.startswith("http://127.0.0.1:"))
        finally:
            service.stop()

    def test_stop_is_idempotent(self):
        service = _service()
        service.stop()
        service.stop()


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.service = _service()
        self.addCleanup(self.service.stop)

    def test_every_endpoint_requires_the_token(self):
        status, _, _ = _request(self.service.port, "/")
        self.assertEqual(status, 401)

        status, _, body = _request(self.service.port, "/", token=self.service.token)
        self.assertEqual(status, 200)
        self.assertIn(b"geopack-map-service", body)

    def test_query_token_is_accepted(self):
        status, _, _ = _request(self.service.port, f"/?t={self.service.token}")
        self.assertEqual(status, 200)

    def test_a_foreign_host_header_is_refused_anti_rebinding(self):
        status, _, _ = _request(
            self.service.port, "/", token=self.service.token, host="evil.example"
        )
        self.assertEqual(status, 403)

    def test_a_wrong_token_is_refused(self):
        status, _, _ = _request(self.service.port, "/", token="not-the-token")
        self.assertEqual(status, 401)


class EndpointTest(unittest.TestCase):
    def setUp(self):
        self.service = _service()
        self.addCleanup(self.service.stop)
        self.manifest = self.service.create_map("test")

    def test_inline_geometry_is_served_as_geojson(self):
        layer = self.manifest.add_layer(layer_from_spec({"kind": "inline-geometry", "geojson": INLINE}))

        status, _, body = _request(self.service.port, f"/data/{layer.id}", token=self.service.token)

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["type"], "Point")

    def test_manifest_exposes_urls_not_paths(self):
        layer = self.manifest.add_layer(layer_from_spec({"kind": "inline-geometry", "geojson": INLINE}))

        status, _, body = _request(
            self.service.port, f"/manifest/{self.manifest.map_id}", token=self.service.token
        )

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["layers"][0]["id"], layer.id)
        self.assertIn("/data/", payload["layers"][0]["dataUrl"])

    def test_portal_dataset_data_and_tile_use_the_portal_credential(self):
        layer = self.manifest.add_layer(layer_from_spec({"kind": "portal-dataset", "datasetId": 7}))

        status, _, body = _request(self.service.port, f"/data/{layer.id}", token=self.service.token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["type"], "FeatureCollection")

        status, headers, tile = _request(
            self.service.port, f"/tiles/{layer.id}/3/4/5.pbf", token=self.service.token
        )
        self.assertEqual(status, 200)
        self.assertIn(b"tile", tile)
        sent = self.service.client.session.calls[-1]
        self.assertEqual(sent["headers"]["Authorization"], f"Bearer {PORTAL_TOKEN}")
        self.assertNotIn(PORTAL_TOKEN.encode(), tile)

    def test_dataset_geojson_defaults_to_a_1000_feature_cap(self):
        layer = self.manifest.add_layer(layer_from_spec({"kind": "portal-dataset", "datasetId": 7}))
        self.assertIsNone(layer.limit)

        _request(self.service.port, f"/data/{layer.id}", token=self.service.token)

        sent = self.service.client.datasets.queries[-1]
        self.assertEqual(sent["kwargs"].get("limit"), 1000)

    def test_a_layer_limit_of_zero_requests_the_whole_dataset(self):
        layer = self.manifest.add_layer(
            layer_from_spec({"kind": "portal-dataset", "datasetId": 7, "limit": 0})
        )
        self.assertEqual(layer.limit, 0)

        _request(self.service.port, f"/data/{layer.id}", token=self.service.token)

        sent = self.service.client.datasets.queries[-1]
        # Unbounded: a projection is sent with NO pagination limit.
        self.assertNotIn("limit", sent["kwargs"])
        projection = sent["args"][0]["projection"]
        self.assertNotIn("limit", projection)
        self.assertEqual(projection["outSRID"], 4326)

    def test_an_explicit_layer_limit_is_passed_through(self):
        layer = self.manifest.add_layer(
            layer_from_spec({"kind": "portal-dataset", "datasetId": 7, "limit": 5000})
        )

        _request(self.service.port, f"/data/{layer.id}", token=self.service.token)

        sent = self.service.client.datasets.queries[-1]
        self.assertEqual(sent["kwargs"].get("limit"), 5000)

    def test_a_minted_publication_tile_is_proxied(self):
        layer = self.manifest.add_layer(
            layer_from_spec({"kind": "portal-publication", "publicationId": 3})
        )

        status, _, _ = _request(
            self.service.port, f"/tiles/{layer.id}/1/2/3.pbf", token=self.service.token
        )
        self.assertEqual(status, 200)
        self.assertIn("{z}", str(self.service.client.publications.template))

    def test_a_raster_tile_is_proxied_from_the_portal_raster_lane(self):
        # A PostGIS raster with no publication and no COG is served by the portal's
        # own raster-tile endpoint; the local proxy adds the credential and forwards
        # the saved `display` + `ref_z` so the official symbology is applied.
        layer = self.manifest.add_layer(
            layer_from_spec({"kind": "portal-dataset", "datasetId": 426})
        )
        layer.raster_tile = True
        layer.raster_display = {"displayType": "colorMap", "band": 1, "colorMap": "jet"}
        layer.ref_zoom = 14

        status, _, body = _request(
            self.service.port,
            f"/rasters/{layer.id}/12/2385/1630.png",
            token=self.service.token,
        )

        self.assertEqual(status, 200)
        self.assertIn(b"tile", body)
        sent = self.service.client.session.calls[-1]
        self.assertIn("/datasets/426/rastertile/12/2385/1630.png", sent["url"])
        self.assertEqual(sent["headers"]["Authorization"], f"Bearer {PORTAL_TOKEN}")
        self.assertIn("ref_z=14", sent["url"])
        self.assertIn("display=", sent["url"])
        self.assertNotIn(PORTAL_TOKEN.encode(), body)

    def test_a_cog_byte_range_is_proxied_with_the_range_forwarded(self):
        status, headers, _ = _request(
            self.service.port, "/cog/1949", token=self.service.token, range_header="bytes=0-4"
        )
        self.assertEqual(status, 206)
        self.assertEqual(headers.get("Content-Range"), "bytes 0-4/1000")
        self.assertEqual(headers.get("Accept-Ranges"), "bytes")
        self.assertEqual(headers.get("Content-Type"), "image/tiff")
        sent = self.service.client.session.calls[-1]
        self.assertEqual(sent["headers"].get("Range"), "bytes=0-4")
        self.assertIn("/datasets/1949/cog", sent["url"])

    def test_a_cog_path_needs_a_numeric_dataset_id(self):
        status, _, _ = _request(self.service.port, "/cog/abc", token=self.service.token)
        self.assertNotEqual(status, 200)

    def test_a_minted_foreign_host_is_refused(self):
        service = _service(mint_template="http://evil.example/{z}/{x}/{y}.pbf")
        self.addCleanup(service.stop)
        manifest = service.create_map("evil")
        layer = manifest.add_layer(
            layer_from_spec({"kind": "portal-publication", "publicationId": 9})
        )

        status, _, body = _request(
            service.port, f"/tiles/{layer.id}/1/2/3.pbf", token=service.token
        )
        self.assertEqual(status, 404)
        self.assertIn("allow-listed", json.loads(body)["message"])


class LocalFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pathlib.Path(self.tmp.name, "ok.geojson").write_text(
            json.dumps(INLINE), encoding="utf-8"
        )
        pathlib.Path(self.tmp.name, "bad.txt").write_text("no", encoding="utf-8")
        self.service = _service(map_root=self.tmp.name)
        self.addCleanup(self.service.stop)
        self.manifest = self.service.create_map("local")

    def test_an_allow_listed_file_is_served(self):
        layer = self.manifest.add_layer(layer_from_spec({"kind": "local-file", "path": "ok.geojson"}))

        status, headers, body = _request(
            self.service.port, f"/data/{layer.id}", token=self.service.token
        )
        self.assertEqual(status, 200)
        self.assertIn("geo+json", headers["Content-Type"])

    def test_traversal_is_refused(self):
        layer = self.manifest.add_layer(layer_from_spec({"kind": "local-file", "path": "../escape.geojson"}))

        status, _, body = _request(self.service.port, f"/data/{layer.id}", token=self.service.token)
        self.assertEqual(status, 404)
        self.assertIn("root", json.loads(body)["message"])

    def test_a_non_allow_listed_extension_is_refused(self):
        layer = self.manifest.add_layer(layer_from_spec({"kind": "local-file", "path": "bad.txt"}))

        status, _, body = _request(self.service.port, f"/data/{layer.id}", token=self.service.token)
        self.assertEqual(status, 404)
        self.assertIn("allow-listed", json.loads(body)["message"])


class CorsTest(unittest.TestCase):
    def test_cors_headers_only_appear_when_enabled(self):
        enabled = _service(cors=True)
        self.addCleanup(enabled.stop)
        manifest = enabled.create_map("cors")
        layer = manifest.add_layer(layer_from_spec({"kind": "inline-geometry", "geojson": INLINE}))
        status, headers, _ = _request(enabled.port, f"/data/{layer.id}", token=enabled.token)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")

        disabled = _service(cors=False)
        self.addCleanup(disabled.stop)
        manifest = disabled.create_map("no-cors")
        layer = manifest.add_layer(layer_from_spec({"kind": "inline-geometry", "geojson": INLINE}))
        _, headers, _ = _request(disabled.port, f"/data/{layer.id}", token=disabled.token)
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))


class BindingBlockedTest(unittest.TestCase):
    def test_a_forbidden_bind_answers_map_service_blocked(self):
        class _Boom:
            def __init__(self, *args, **kwargs):
                raise OSError(13, "bind forbidden")

        with patch("geopack_sdk_mcp.maps.service._Server", _Boom):
            service = LocalService(_FakeClient(), idle_timeout=0)
            with self.assertRaises(MapServiceError) as ctx:
                service.start()
        self.assertEqual(ctx.exception.code, "MAP_SERVICE_BLOCKED")


class OptInTest(unittest.TestCase):
    def tearDown(self):
        reset_for_tests()

    def test_the_service_is_opt_in(self):
        with patch.dict(os.environ, {"GEOPACK_MCP_MAP_SERVICE": ""}):
            with self.assertRaises(MapServiceError) as ctx:
                get_or_start_service(_FakeClient())
        self.assertEqual(ctx.exception.code, "MAP_SERVICE_BLOCKED")

    def test_force_bypasses_the_flag_for_tests(self):
        with patch.dict(os.environ, {"GEOPACK_MCP_MAP_SERVICE": ""}):
            service = get_or_start_service(_FakeClient(), force=True, idle_timeout=0)
        self.assertGreater(service.port, 0)


if __name__ == "__main__":
    unittest.main()