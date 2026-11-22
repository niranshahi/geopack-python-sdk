"""Slice 033 Lane A/B handoff — show_map tool surface and geometry-to-map feed."""

from __future__ import annotations

import http.client
import json
import os
import unittest
from unittest.mock import patch

from geopack_sdk_mcp.maps import reset_for_tests
from geopack_sdk_mcp.maps.errors import MapServiceError
from geopack_sdk_mcp.tool_handlers.geometry import geometry_op
from geopack_sdk_mcp.tool_handlers.maps import show_map

PORTAL = "http://portal.example/api"
PORTAL_TOKEN = "PORTAL-SECRET-xyz"

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
}


class _Response:
    content = b"\x1a\x00tile"
    headers = {"Content-Type": "application/vnd.mapbox-vector-tile"}
    status_code = 200
    ok = True


class _Auth:
    token = PORTAL_TOKEN


class _Session:
    def get(self, url, headers=None, params=None, timeout=None):
        return _Response()


class _Datasets:
    def query(self, dataset_id, *args, **kwargs):
        return {"type": "FeatureCollection", "features": []}


class _Client:
    base_url = PORTAL

    def __init__(self):
        self.auth = _Auth()
        self.session = _Session()
        self.datasets = _Datasets()


def _free_port():
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _get(port, path, token):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", f"{path}?t={token}")
    response = conn.getresponse()
    body = response.read()
    status = response.status
    conn.close()
    return status, body


class ShowMapTest(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {"GEOPACK_MCP_MAP_SERVICE": "1"})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.addCleanup(reset_for_tests)

    def test_show_map_returns_stable_urls_and_a_manifest(self):
        payload = show_map(
            _Client(),
            title="Demo",
            layers=[
                {"kind": "inline-geometry", "title": "inline", "geojson": SQUARE},
                {"kind": "portal-dataset", "datasetId": 7},
            ],
        )

        self.assertTrue(payload["serviceUrl"].startswith("http://127.0.0.1:"))
        self.assertIn("/map/", payload["manifestUrl"])
        self.assertIn("?t=", payload["viewerUrl"])
        self.assertEqual(len(payload["layers"]), 2)
        self.assertTrue(payload["layers"][0]["dataUrl"].endswith("/data/" + payload["layers"][0]["id"]))
        self.assertTrue(payload["layers"][1]["tileUrl"].endswith("/tiles/" + payload["layers"][1]["id"] + "/{z}/{x}/{y}.pbf"))
        self.assertIsNotNone(payload["viewerUrl"])
        self.assertEqual(payload["layersAdded"], 2)

    def test_the_portal_credential_never_appears_in_the_payload(self):
        payload = show_map(_Client(), layers=[{"kind": "inline-geometry", "geojson": SQUARE}])
        blob = json.dumps(payload)

        self.assertNotIn(PORTAL_TOKEN, blob)
        self.assertNotEqual(payload["accessToken"], PORTAL_TOKEN)

    def test_a_declared_layer_is_fetchable_by_url(self):
        payload = show_map(_Client(), layers=[{"kind": "inline-geometry", "geojson": SQUARE}])
        port = int(payload["serviceUrl"].rsplit(":", 1)[1])
        layer = payload["layers"][0]

        status, body = _get(port, f"/data/{layer['id']}", payload["accessToken"])

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["type"], "Polygon")

    def test_updating_a_map_by_id_keeps_the_same_id(self):
        first = show_map(_Client(), layers=[{"kind": "inline-geometry", "geojson": SQUARE}])
        second = show_map(
            _Client(),
            map_id=first["mapId"],
            layers=[{"kind": "inline-geometry", "geojson": SQUARE}],
        )

        self.assertEqual(second["mapId"], first["mapId"])
        self.assertEqual(len(second["layers"]), 2)

    def test_an_unknown_map_id_is_refused(self):
        with self.assertRaises(MapServiceError):
            show_map(_Client(), map_id="map_missing")

    def test_open_browser_opens_the_viewer_url(self):
        with patch("webbrowser.open", return_value=True) as opener:
            payload = show_map(_Client(), open_browser=True)

        opener.assert_called_once()
        opened = opener.call_args.args[0]
        self.assertIn("/map/", opened)
        self.assertIn("?t=", opened)
        self.assertTrue(payload["browserOpened"])

    def test_open_browser_failing_is_never_fatal(self):
        with patch("webbrowser.open", side_effect=RuntimeError("no spawn")):
            payload = show_map(_Client(), open_browser=True)

        self.assertFalse(payload["browserOpened"])
        self.assertIn("?t=", payload["viewerUrl"])

    def test_a_fixed_port_is_honoured(self):
        port = _free_port()
        with patch.dict(os.environ, {"GEOPACK_MCP_MAP_PORT": str(port)}):
            reset_for_tests()
            payload = show_map(_Client())

        self.assertTrue(payload["serviceUrl"].endswith(f":{port}"))

    def test_a_geometry_result_feeds_an_inline_layer(self):
        buffer = geometry_op(
            "buffer",
            geojson={"type": "Point", "coordinates": [51.4, 35.7]},
            distance=100,
            wkid=32639,
        )
        self.assertIn("geojson", buffer)

        payload = show_map(
            _Client(),
            layers=[{"kind": "inline-geometry", "title": "buffer", "geojson": buffer["geojson"]}],
        )

        self.assertEqual(payload["layers"][0]["title"], "buffer")


class SurfacePinTest(unittest.TestCase):
    def test_the_surface_is_thirty_one_tools(self):
        from geopack_sdk_mcp.server import mcp

        names = {tool.name for tool in mcp._tool_manager.list_tools()}  # noqa: SLF001
        self.assertEqual(len(names), 31)
        self.assertIn("geopack_sdk_show_map", names)
        self.assertIn("geopack_sdk_geometry_op", names)


if __name__ == "__main__":
    unittest.main()
