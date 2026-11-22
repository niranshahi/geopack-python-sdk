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
    def __init__(self, details=None, data_type="vector", extra=None):
        self.calls = []
        self._details = details if details is not None else {}
        self._data_type = data_type
        self._extra = extra or {}

    def query(self, dataset_id, *args, **kwargs):
        self.calls.append({"dataset_id": dataset_id, "args": args, "kwargs": kwargs})
        return {"type": "FeatureCollection", "features": []}

    def get(self, dataset_id):
        record = {"id": dataset_id, "dataType": self._data_type, "details": self._details}
        record.update(self._extra)
        return record


class _Publications:
    def __init__(self, ids=(60,)):
        self._ids = set(ids)

    def get(self, publication_id):
        if publication_id not in self._ids:
            raise RuntimeError("Publication not found. (HTTP 404)")
        return {"id": publication_id, "datasetId": 7, "protocol": "wms"}


class _WrappedPublications:
    """Mirrors the SDK Publication model: the API payload nests under ``raw``."""

    def get(self, publication_id):
        return {"raw": {"id": publication_id, "datasetId": 2554, "protocol": "wms"}}


class _Client:
    base_url = PORTAL

    def __init__(self, publication_ids=(60,), details=None, data_type="vector", extra=None):
        self.auth = _Auth()
        self.session = _Session()
        self.datasets = _Datasets(details=details, data_type=data_type, extra=extra)
        self.publications = _Publications(publication_ids)


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

    def test_an_unknown_publication_id_fails_fast(self):
        with self.assertRaises(MapServiceError) as ctx:
            show_map(
                _Client(publication_ids=()),
                layers=[{"kind": "portal-publication", "publicationId": 999}],
            )
        self.assertEqual(ctx.exception.key, "publicationId")

    def test_a_known_publication_id_is_accepted(self):
        payload = show_map(
            _Client(publication_ids=(60,)),
            layers=[{"kind": "portal-publication", "publicationId": 60}],
        )
        self.assertEqual(payload["layersAdded"], 1)
        self.assertTrue(payload["layers"][0]["wmsUrl"].endswith("/proxy/publication/60/wms"))

    def test_a_publication_extent_comes_from_its_source_dataset(self):
        # The Publication model nests its payload under `raw`; the layer must
        # still borrow the source dataset's WGS84 extent for auto-fit.
        client = _Client(details={"geo_extent": [45.115, 25.354, 62.110, 38.067]})
        client.publications = _WrappedPublications()
        payload = show_map(
            client, layers=[{"kind": "portal-publication", "publicationId": 60}]
        )
        self.assertEqual(payload["layers"][0]["bbox"], [45.115, 25.354, 62.110, 38.067])
        self.assertEqual(payload["layers"][0]["bboxCrs"], "EPSG:4326")

    def test_a_dataset_extent_is_read_and_labelled(self):
        client = _Client(details={"geo_extent": [45.115, 25.354, 62.110, 38.067]})
        payload = show_map(client, layers=[{"kind": "portal-dataset", "datasetId": 2554}])
        layer = payload["layers"][0]

        self.assertEqual(layer["bbox"], [45.115, 25.354, 62.110, 38.067])
        self.assertEqual(layer["bboxCrs"], "EPSG:4326")
        self.assertEqual(layer["bboxAxisOrder"], "west,south,east,north")

    def test_a_projected_bbox_is_rejected_not_plotted(self):
        # A native-CRS (metre) extent would otherwise zoom the viewer to nowhere.
        payload = show_map(
            _Client(),
            layers=[
                {"kind": "inline-geometry", "geojson": SQUARE,
                 "bbox": [4218766, 30179983, 5712825, 31589775]}
            ],
        )
        self.assertNotIn("bbox", payload["layers"][0])
        self.assertTrue(any("bbox" in w for w in payload["templateWarnings"]))

    def test_a_swapped_bbox_is_replaced_by_the_dataset_extent(self):
        client = _Client(details={"geo_extent": [45.115, 25.354, 62.110, 38.067]})
        payload = show_map(
            client,
            layers=[
                {"kind": "portal-dataset", "datasetId": 2554,
                 "bbox": [25.354, 45.115, 38.067, 62.110]}  # lat/lon order — no overlap
            ],
        )
        self.assertEqual(payload["layers"][0]["bbox"], [45.115, 25.354, 62.110, 38.067])
        self.assertTrue(any("does not overlap" in w for w in payload["templateWarnings"]))

    def test_a_raster_dataset_layer_warns_to_use_a_publication(self):
        payload = show_map(
            _Client(data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1761}],
        )
        self.assertTrue(any("raster" in w for w in payload["templateWarnings"]))
        # The legend must treat it as raster rather than painting a vector fill.
        self.assertTrue(payload["layers"][0].get("raster"))

    def test_dataset_data_is_reprojected_to_wgs84(self):
        client = _Client()
        payload = show_map(client, layers=[{"kind": "portal-dataset", "datasetId": 7}])
        port = int(payload["serviceUrl"].rsplit(":", 1)[1])

        _get(port, f"/data/{payload['layers'][0]['id']}", payload["accessToken"])

        self.assertTrue(client.datasets.calls)
        self.assertEqual(client.datasets.calls[-1]["kwargs"].get("out_srid"), 4326)

    def test_string_details_extent_is_read_for_a_projected_dataset(self):
        # The portal answers `details` as a JSON string for most datasets; a
        # dict-only read found no extent, so a projected dataset got no bbox.
        details = json.dumps(
            {
                "geo_extent": [59.13, 36.52, 59.23, 36.61],
                "spatialReference": {"srid": 32640},
            }
        )
        payload = show_map(
            _Client(details=details),
            layers=[{"kind": "portal-dataset", "datasetId": 2436}],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["bbox"], [59.13, 36.52, 59.23, 36.61])
        self.assertEqual(layer["bboxCrs"], "EPSG:4326")
        self.assertEqual(layer["bboxAxisOrder"], "west,south,east,north")

    def test_ext_columns_fill_bbox_when_geo_extent_is_absent(self):
        client = _Client(
            details={"geo_extent": None},
            extra={"ext_west": 50.0, "ext_south": 33.0, "ext_east": 51.0, "ext_north": 34.0},
        )
        payload = show_map(
            client, layers=[{"kind": "portal-dataset", "datasetId": 2304}]
        )
        self.assertEqual(payload["layers"][0]["bbox"], [50.0, 33.0, 51.0, 34.0])

    def test_layers_without_a_style_get_distinct_palette_fills(self):
        payload = show_map(
            _Client(),
            layers=[
                {"kind": "inline-geometry", "geojson": SQUARE},
                {"kind": "portal-dataset", "datasetId": 7},
            ],
        )
        fills = [layer.get("style", {}).get("fill") for layer in payload["layers"]]
        self.assertTrue(all(fills))
        self.assertNotEqual(fills[0], fills[1])

    def test_an_explicit_layer_style_fill_is_honoured(self):
        payload = show_map(
            _Client(),
            layers=[
                {"kind": "inline-geometry", "geojson": SQUARE, "style": {"fill": "#ff0000"}},
                {"kind": "portal-dataset", "datasetId": 7},
            ],
        )
        self.assertEqual(payload["layers"][0]["style"]["fill"], "#ff0000")
        self.assertNotEqual(payload["layers"][1]["style"]["fill"], "#ff0000")

    def test_a_wms_layer_with_a_style_warns_it_cannot_recolour(self):
        payload = show_map(
            _Client(publication_ids=(60,)),
            layers=[
                {"kind": "portal-publication", "publicationId": 60, "style": {"fill": "#00ff00"}}
            ],
        )
        self.assertTrue(any("style does not affect" in w for w in payload["templateWarnings"]))


class SurfacePinTest(unittest.TestCase):
    def test_the_surface_is_thirty_one_tools(self):
        from geopack_sdk_mcp.server import mcp

        names = {tool.name for tool in mcp._tool_manager.list_tools()}  # noqa: SLF001
        self.assertEqual(len(names), 31)
        self.assertIn("geopack_sdk_show_map", names)
        self.assertIn("geopack_sdk_geometry_op", names)


if __name__ == "__main__":
    unittest.main()
