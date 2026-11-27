"""Slice 033 Lane A/B handoff — show_map tool surface and geometry-to-map feed."""

from __future__ import annotations

import http.client
import json
import os
import unittest
from unittest.mock import patch

from geopack_sdk_mcp.maps import reset_for_tests
from geopack_sdk_mcp.maps.errors import MapServiceError
from geopack_sdk_mcp.maps.sources import (
    query_dataset_geojson,
    raster_tile_capable,
    reference_zoom_for_raster,
)
from geopack_sdk_mcp.tool_handlers.geometry import geometry_op
from geopack_sdk_mcp.tool_handlers.maps import show_map

PORTAL = "http://portal.example/api"
PORTAL_TOKEN = "PORTAL-SECRET-xyz"

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
}


def _feature(properties):
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
        },
        "properties": properties,
    }


def _sample_features():
    return {
        "type": "FeatureCollection",
        "features": [
            _feature({"Ownership": 1, "DB_SHAPE_Area": 100.0}),
            _feature({"Ownership": 2, "DB_SHAPE_Area": 200.0}),
            _feature({"Ownership": 1, "DB_SHAPE_Area": 300.0}),
        ],
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
    def __init__(self, details=None, data_type="vector", extra=None, feature_collection=None, feature_total=None):
        self.calls = []
        self._details = details if details is not None else {}
        self._data_type = data_type
        self._extra = extra or {}
        self._feature_total = feature_total
        self._feature_collection = feature_collection or {
            "type": "FeatureCollection",
            "features": [],
        }

    def query(self, dataset_id, *args, **kwargs):
        self.calls.append({"dataset_id": dataset_id, "args": args, "kwargs": kwargs})
        return self._feature_collection

    def query_paged(self, dataset_id, page=1, page_size=1, include_total_count=False):
        class _Pagination:
            total_count = self._feature_total

        class _Page:
            pagination = _Pagination()

        return _Page()

    def _field_values(self, field):
        values = []
        for feature in (self._feature_collection or {}).get("features") or []:
            props = feature.get("properties") if isinstance(feature, dict) else None
            if isinstance(props, dict) and field in props:
                values.append(props.get(field))
        return values

    def _distinct(self, field):
        seen = []
        for value in self._field_values(field):
            key = "" if value is None else str(value)
            if key not in [entry[0] for entry in seen]:
                seen.append((key, value))
        return [value for _key, value in seen]

    class _Aggregate:
        def __init__(self, rows):
            self.rows = rows

    def _percentile(self, numbers, p):
        if not numbers:
            return None
        index = max(0, min(len(numbers) - 1, int(float(p) * len(numbers))))
        return numbers[index]

    def _scalar_row(self, aggregation):
        row = {}
        for spec in aggregation.get("aggregates") or []:
            if not isinstance(spec, dict):
                continue
            alias = spec.get("alias") or spec.get("aggregate")
            field = spec.get("field")
            numbers = sorted(
                float(value)
                for value in self._field_values(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            )
            kind = spec.get("aggregate")
            if kind == "min":
                row[alias] = numbers[0] if numbers else None
            elif kind == "max":
                row[alias] = numbers[-1] if numbers else None
            elif kind == "percentile":
                row[alias] = self._percentile(numbers, spec.get("p"))
            else:
                row[alias] = None
        return row

    def aggregate(self, dataset_id, *, aggregation=None, filter=None, spatial_filter=None):
        self.calls.append(
            {"dataset_id": dataset_id, "aggregation": aggregation, "filter": filter}
        )
        aggregation = aggregation or {}
        group_by = aggregation.get("groupBy") or []
        if not group_by:
            return self._Aggregate([self._scalar_row(aggregation)])
        field = None
        for group in group_by:
            if isinstance(group, dict) and group.get("field"):
                field = group["field"]
                break
        rows = [{field: value, "n": 1} for value in self._distinct(field)]
        return self._Aggregate(rows)

    def count(self, dataset_id, *, filter=None, spatial_filter=None, field=None, distinct=False):
        if distinct and field:
            return len(self._distinct(field))
        return len((self._feature_collection or {}).get("features") or [])

    def get(self, dataset_id):
        record = {"id": dataset_id, "dataType": self._data_type, "details": self._details}
        record.update(self._extra)
        return record


class _Publications:
    def __init__(self, ids=(60,), dataset_publications=None):
        self._ids = set(ids)
        self._dataset_publications = dataset_publications or []

    def get(self, publication_id):
        if publication_id not in self._ids:
            raise RuntimeError("Publication not found. (HTTP 404)")
        return {"id": publication_id, "datasetId": 7, "protocol": "wms"}

    def list_for_dataset(self, dataset_id):
        return self._dataset_publications


class _WrappedPublications:
    """Mirrors the SDK Publication model: the API payload nests under ``raw``."""

    def get(self, publication_id):
        return {"raw": {"id": publication_id, "datasetId": 2554, "protocol": "wms"}}


class _Client:
    base_url = PORTAL

    def __init__(self, publication_ids=(60,), details=None, data_type="vector", extra=None, feature_collection=None, publication_list=None, feature_total=None):
        self.auth = _Auth()
        self.session = _Session()
        self.datasets = _Datasets(
            details=details,
            data_type=data_type,
            extra=extra,
            feature_collection=feature_collection,
            feature_total=feature_total,
        )
        self.publications = _Publications(publication_ids, publication_list)


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

    def test_a_viewer_link_with_a_bad_token_answers_an_expired_page(self):
        # A `?t=` token is visible to the server, so a stale/foreign one must 401
        # with a readable page — not 200 + a blank canvas (N6).
        payload = show_map(_Client(), layers=[{"kind": "inline-geometry", "geojson": SQUARE}])
        port = int(payload["serviceUrl"].rsplit(":", 1)[1])

        status, body = _get(port, f"/map/{payload['mapId']}", "not-the-token")

        self.assertEqual(status, 401)
        self.assertIn(b"no longer valid", body)
        self.assertIn(b"show_map", body)

    def test_a_viewer_link_with_a_valid_token_serves_the_shell(self):
        payload = show_map(_Client(), layers=[{"kind": "inline-geometry", "geojson": SQUARE}])
        port = int(payload["serviceUrl"].rsplit(":", 1)[1])

        status, body = _get(port, f"/map/{payload['mapId']}", payload["accessToken"])

        self.assertEqual(status, 200)
        self.assertIn(b"<html", body.lower())

    def test_an_unknown_map_id_answers_an_expired_page(self):
        payload = show_map(_Client(), layers=[{"kind": "inline-geometry", "geojson": SQUARE}])
        port = int(payload["serviceUrl"].rsplit(":", 1)[1])

        status, body = _get(port, "/map/map_does_not_exist", payload["accessToken"])

        self.assertEqual(status, 404)
        self.assertIn(b"no longer exists", body)

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
        # No usable raster-tile source is known for this dataset (no details at all),
        # so it still falls back to the vector footprint and warns.
        payload = show_map(
            _Client(data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1761}],
        )
        self.assertTrue(any("raster" in w for w in payload["templateWarnings"]))
        # The legend must treat it as raster rather than painting a vector fill.
        self.assertTrue(payload["layers"][0].get("raster"))

    def test_a_postgis_raster_dataset_uses_server_rendered_png_tiles(self):
        # A raster stored in PostGIS (dbTableName + rasterDbColumn) is NOT
        # vector-only: the portal's own PNG tile lane renders it — no publication
        # and no COG — and applies the dataset's saved display/colorMap.
        details = {
            "dbTableName": "rst_51251a8ba0c64e43a9fc8f5407f92a99",
            "rasterDbColumn": "rast",
            "srid": 32640,
            "rasterSize": {"x": 201, "y": 376},
            "geo_extent": [55.007, 30.387, 55.025, 30.409],
            "bands": [{"band": 1, "type": "Float32", "minimum": 0.501, "maximum": 14.282}],
            "display": {
                "displayType": "colorMap",
                "band": 1,
                "colorMap": "jet",
                "minimum": 0.501,
                "maximum": 14.282,
            },
        }
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 425, "title": "Ano_Mol_Raster"}],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["render"], "rastertile")
        self.assertTrue(layer["raster"])
        self.assertIn("/rasters/", layer["rasterTileUrl"])
        self.assertIn("{z}", layer["rasterTileUrl"])
        # The official raster display is applied by the server, so neither the
        # "no image" warning nor the saved-symbology disclosure may appear.
        self.assertFalse(any("will not show an image" in w for w in payload["templateWarnings"]))
        self.assertFalse(any("saved symbology" in w for w in payload["templateWarnings"]))

    def test_render_rastertile_on_a_non_tile_dataset_warns_and_falls_back(self):
        payload = show_map(
            _Client(data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1761, "render": "rastertile"}],
        )
        self.assertNotEqual(payload["layers"][0]["render"], "rastertile")
        self.assertTrue(any("rastertile" in w for w in payload["templateWarnings"]))

    def test_an_mbtiles_raster_is_served_by_the_raster_tile_lane(self):
        # The filesystem adapter's raster-tile path reads tiles from the MBTiles
        # container (flipping XYZ→TMS), so these rasters use the same lane.
        details = {"subType": "MBTiles", "mbtiles_metadata": {"minzoom": 0, "maxzoom": 12}}
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 900}],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["render"], "rastertile")
        self.assertIn("/rasters/", layer["rasterTileUrl"])

    def test_a_caller_raster_display_overrides_the_saved_one(self):
        # Unlike a COG, the raster-tile lane can change rendering: a caller
        # `display` overrides the dataset's saved bands/colorMap. It stays
        # server-side (the manifest exposes no display payload).
        from geopack_sdk_mcp.maps import get_service

        details = {
            "dbTableName": "rst_x",
            "rasterDbColumn": "rast",
            "display": {"displayType": "colorMap", "band": 1, "colorMap": "jet",
                        "minimum": 1.0, "maximum": 14.282},
        }
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{
                "kind": "portal-dataset",
                "datasetId": 425,
                "display": {"displayType": "colorMap", "band": 1, "colorMap": "fire",
                            "minimum": 0, "maximum": 100},
            }],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["render"], "rastertile")
        self.assertNotIn("rasterDisplay", layer)
        internal = get_service().find_layer(layer["id"])
        self.assertEqual(internal.raster_display["colorMap"], "fire")
        self.assertEqual(internal.raster_display["minimum"], 0)

    def test_a_friendly_raster_display_shape_is_normalized(self):
        # The harness-friendly forms an agent is likely to send are accepted:
        # bands {r,g,b} (RGB) and a customColorMap stop's color:[r,g,b,a]. The
        # portal panel sorts stops DESCENDING before rendering — ST_ColorMap is
        # order-sensitive and ascending stops yield a transparent tile — so the
        # MCP mirrors that sort.
        from geopack_sdk_mcp.maps import get_service

        details = {"dbTableName": "rst_x", "rasterDbColumn": "rast"}
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1,
                 "display": {"displayType": "RGB", "bands": {"r": 4, "g": 3, "b": 2}}},
                {"kind": "portal-dataset", "datasetId": 2,
                 "display": {"displayType": "colorMap", "band": 1, "colorMap": "custom",
                             "minimum": 0, "maximum": 100,
                             "customColorMap": [{"value": 0, "color": [255, 0, 0, 255]},
                                                {"value": "50%", "color": [0, 255, 0, 255]},
                                                {"value": 100, "color": [0, 0, 255]}]}},
            ],
        )
        service = get_service()
        rgb = service.find_layer(payload["layers"][0]["id"]).raster_display
        self.assertEqual((rgb["RBand"], rgb["GBand"], rgb["BBand"]), (4, 3, 2))
        self.assertNotIn("bands", rgb)
        ramp = service.find_layer(payload["layers"][1]["id"]).raster_display
        # Descending: 100 (absolute) → 50% (resolved to 50) → 0.
        self.assertEqual(
            [stop["value"] for stop in ramp["customColorMap"]], [100, "50%", 0]
        )
        self.assertEqual(
            ramp["customColorMap"][0], {"value": 100, "r": 0, "g": 0, "b": 255, "a": 255}
        )
        self.assertEqual(ramp["customColorMap"][2]["r"], 255)

    def test_a_custom_ramp_is_sorted_descending_for_st_colormap(self):
        # Regression for the 2026-11-27 report: ascending custom stops (the
        # natural way an agent writes them) made ST_ColorMap emit a transparent
        # tile. The portal panel sorts descending; the MCP must too.
        from geopack_sdk_mcp.maps import get_service

        payload = show_map(
            _Client(details={"dbTableName": "rst_x", "rasterDbColumn": "rast"},
                    data_type="raster"),
            layers=[{
                "kind": "portal-dataset",
                "datasetId": 426,
                "display": {
                    "displayType": "colorMap", "band": 1, "colorMap": "custom",
                    "minimum": 6.995, "maximum": 14096.542,
                    "customColorMap": [
                        {"value": 7, "r": 33, "g": 40, "b": 120, "a": 255},
                        {"value": "50%", "r": 240, "g": 240, "b": 240, "a": 255},
                        {"value": 14096, "r": 178, "g": 24, "b": 43, "a": 255},
                    ],
                },
            }],
        )
        internal = get_service().find_layer(payload["layers"][0]["id"])
        values = [stop["value"] for stop in internal.raster_display["customColorMap"]]
        self.assertEqual(values, [14096, "50%", 7])
        self.assertEqual(internal.raster_display["customColorMap"][0]["r"], 178)
        self.assertEqual(internal.raster_display["customColorMap"][2]["r"], 33)

    def test_a_saved_ascending_custom_ramp_is_sorted_before_forwarding(self):
        # Even a dataset saved by another client with ascending stops must not
        # render blank: the saved display is sorted (and color arrays flattened)
        # before it is forwarded to the portal.
        from geopack_sdk_mcp.maps import get_service

        details = {
            "dbTableName": "rst_x",
            "rasterDbColumn": "rast",
            "display": {
                "displayType": "colorMap", "band": 1, "colorMap": "custom",
                "minimum": 0, "maximum": 100,
                "customColorMap": [
                    {"value": 0, "color": [255, 0, 0, 255]},
                    {"value": 100, "color": [0, 0, 255, 255]},
                ],
            },
        }
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1}],
        )
        display = get_service().find_layer(payload["layers"][0]["id"]).raster_display
        self.assertEqual([stop["value"] for stop in display["customColorMap"]], [100, 0])
        self.assertEqual(display["customColorMap"][0]["b"], 255)

    def test_the_frontend_working_custom_sample_is_reproduced(self):
        # The exact panel sample (ascending `color:[r,g,b,a]`) becomes flat
        # r/g/b/a in descending order — the form the backend actually renders.
        from geopack_sdk_mcp.maps import get_service

        sample = {
            "displayType": "colorMap", "band": 1, "colorMap": "custom",
            "reclass": False, "minimum": 1.531, "maximum": 54.485,
            "customColorMap": [
                {"value": 1.5, "color": [27, 158, 119, 255]},
                {"value": 3, "color": [163, 98, 165, 255]},
                {"value": 10, "color": [191, 171, 15, 255]},
                {"value": 20, "color": [102, 102, 102, 255]},
            ],
        }
        payload = show_map(
            _Client(details={"dbTableName": "rst_x", "rasterDbColumn": "rast"},
                    data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 423, "display": sample}],
        )
        display = get_service().find_layer(payload["layers"][0]["id"]).raster_display
        self.assertEqual(
            [stop["value"] for stop in display["customColorMap"]], [20, 10, 3, 1.5]
        )
        self.assertEqual(
            display["customColorMap"][0],
            {"value": 20, "r": 102, "g": 102, "b": 102, "a": 255},
        )
        self.assertNotIn("color", display["customColorMap"][0])

    def test_a_reclass_object_warns_and_stays_boolean(self):
        # `reclass` is a boolean min→max stretch, not a class-break spec; an
        # object is turned into `true` WITH a warning (it used to 500).
        payload = show_map(
            _Client(details={"dbTableName": "rst_x", "rasterDbColumn": "rast"},
                    data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1,
                     "display": {"displayType": "colorMap", "band": 1,
                                 "colorMap": "grayscale",
                                 "reclass": {"type": "equalInterval", "classes": 5}}}],
        )
        self.assertTrue(
            any("reclass" in w and "boolean" in w for w in payload["templateWarnings"])
        )

    def test_reclass_on_a_custom_ramp_is_ignored_with_a_warning(self):
        # The backend disables reclass for custom ramps: it is a VALUE reclass
        # for named ramps, not a "stop colours blending" switch.
        from geopack_sdk_mcp.maps import get_service

        payload = show_map(
            _Client(details={"dbTableName": "rst_x", "rasterDbColumn": "rast"},
                    data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 426,
                     "display": {"displayType": "colorMap", "band": 1,
                                 "colorMap": "custom", "reclass": True,
                                 "minimum": 6.995, "maximum": 14096.542,
                                 "customColorMap": [
                                     {"value": "0%", "r": 178, "g": 24, "b": 43, "a": 255},
                                     {"value": "100%", "r": 21, "g": 99, "b": 33, "a": 255},
                                 ]}}],
        )
        self.assertTrue(
            any("no effect on a custom ramp" in w for w in payload["templateWarnings"])
        )
        internal = get_service().find_layer(payload["layers"][0]["id"])
        self.assertNotIn("reclass", internal.raster_display)

    def test_an_unknown_color_map_falls_back_with_a_warning(self):
        # `jet`/`viridis` are not portal ramps; the display is sanitized so the
        # tile request cannot fail, and the caller is told why.
        payload = show_map(
            _Client(details={"dbTableName": "rst_x", "rasterDbColumn": "rast"},
                    data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 425,
                     "display": {"displayType": "colorMap", "colorMap": "viridis"}}],
        )
        self.assertTrue(any("not a portal ramp" in w for w in payload["templateWarnings"]))

    def test_a_display_on_mbtiles_is_ignored_with_a_warning(self):
        # MBTiles stores finished pictures; the portal cannot recolour them.
        from geopack_sdk_mcp.maps import get_service

        details = {"subType": "MBTiles", "mbtiles_metadata": {"maxzoom": 12}}
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 900,
                     "display": {"displayType": "colorMap", "colorMap": "fire"}}],
        )
        self.assertTrue(any("pre-rendered" in w for w in payload["templateWarnings"]))
        self.assertIsNone(get_service().find_layer(payload["layers"][0]["id"]).raster_display)

    def test_raster_tile_capability_and_reference_zoom(self):
        # The native zoom is derived from the extent width / raster width when the
        # portal omits metadata_3857 (a common case for PostGIS rasters), so the
        # portal picks the right overview instead of the blurry default level.
        extent = [55.007, 30.387, 55.025, 30.409]
        details = {"dbTableName": "rst_x", "rasterDbColumn": "rast", "rasterSize": {"x": 201}}
        self.assertTrue(raster_tile_capable(details))
        self.assertEqual(reference_zoom_for_raster(details, extent), 14)
        # metadata_3857.scalex wins (frontend parity) when present.
        with_meta = {**details, "metadata_3857": {"scalex": 2.5}}
        self.assertEqual(reference_zoom_for_raster(with_meta, extent), 16)
        # A COG takes the direct byte lane; MBTiles is served by the raster-tile lane.
        self.assertFalse(raster_tile_capable({"hasCOG": True, "dbTableName": "rst_x"}))
        self.assertTrue(raster_tile_capable({"subType": "MBTiles", "mbtiles_metadata": {}}))

    def test_dataset_data_is_reprojected_to_wgs84(self):
        client = _Client()
        payload = show_map(client, layers=[{"kind": "portal-dataset", "datasetId": 7}])
        port = int(payload["serviceUrl"].rsplit(":", 1)[1])

        _get(port, f"/data/{payload['layers'][0]['id']}", payload["accessToken"])

        self.assertTrue(client.datasets.calls)
        self.assertEqual(client.datasets.calls[-1]["kwargs"].get("out_srid"), 4326)

    def test_a_projected_portal_answer_is_repaired_for_the_viewer(self):
        # The portal ignored outSRID and returned native metres; the viewer plots
        # coordinates directly, so the map lane must repair to lon/lat.
        client = _Client(
            details={"spatialReference": {"srid": 32640}},
            feature_collection={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {"type": "Point", "coordinates": [500000.0, 4000000.0]},
                    }
                ],
            },
        )

        fc = query_dataset_geojson(client, 2436)

        x, y = fc["features"][0]["geometry"]["coordinates"]
        self.assertLessEqual(abs(x), 180)
        self.assertLessEqual(abs(y), 90)

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

    def test_a_dataset_layer_with_a_saved_renderer_gets_the_portable_spec(self):
        # A translatable saved renderer is APPLIED (not merely warned): the layer
        # carries the portable symbology spec so the viewer draws the real colours.
        details = {
            "display": {
                "esri": {
                    "renderer": {
                        "type": "uniqueValue",
                        "field1": "Landuse_Group",
                        "uniqueValueInfos": [
                            {
                                "value": "1",
                                "label": "Residential",
                                "symbol": {
                                    "type": "esriSFS",
                                    "color": [27, 158, 119, 196],
                                    "outline": {"color": [131, 129, 126, 255], "width": 0.75},
                                },
                            }
                        ],
                        "defaultSymbol": {"type": "esriSFS", "color": [252, 0, 0, 196]},
                    }
                }
            }
        }
        payload = show_map(
            _Client(details=details),
            layers=[{"kind": "portal-dataset", "datasetId": 1577}],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["symbology"]["type"], "uniqueValue")
        self.assertEqual(layer["symbology"]["field"], "Landuse_Group")
        self.assertEqual(layer["symbology"]["unique"][0]["style"]["fill"], "#1b9e77")
        self.assertEqual(layer["symbology"]["legend"]["entries"][0]["label"], "Residential")
        # Applied, so no "saved symbology" disclosure warning.
        self.assertFalse(any("saved symbology" in w for w in payload["templateWarnings"]))

    def test_a_derived_symbology_layer_is_not_given_a_palette_style(self):
        # The palette fill must NOT be attached to a layer that carries a derived
        # spec: in the viewer an explicit `style` wins over `symbology`, so a
        # palette fill would silently override the dataset colours (the drawn map
        # stayed one flat colour while the legend showed every class).
        details = {
            "display": {
                "esri": {
                    "renderer": {
                        "type": "uniqueValue",
                        "field1": "Landuse_Group",
                        "uniqueValueInfos": [
                            {"value": "1", "label": "Residential",
                             "symbol": {"type": "esriSFS", "color": [27, 158, 119, 196]}}
                        ],
                    }
                }
            }
        }
        payload = show_map(
            _Client(details=details),
            layers=[{"kind": "portal-dataset", "datasetId": 1577}],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["symbology"]["type"], "uniqueValue")
        self.assertNotIn("style", layer)

    def test_an_explicit_style_disables_the_derived_symbology(self):
        details = {"display": {"esri": {"renderer": {"type": "uniqueValue", "field1": "x"}}}}
        payload = show_map(
            _Client(details=details),
            layers=[{"kind": "portal-dataset", "datasetId": 1577, "style": {"fill": "#ff0000"}}],
        )
        self.assertNotIn("symbology", payload["layers"][0])

    def test_an_untranslatable_renderer_still_warns(self):
        # pieChart is not translated yet → fall back to the disclosure warning.
        details = {"display": {"esri": {"renderer": {"type": "pieChart", "field1": "x"}}}}
        payload = show_map(
            _Client(details=details),
            layers=[{"kind": "portal-dataset", "datasetId": 1577}],
        )
        self.assertNotIn("symbology", payload["layers"][0])
        self.assertTrue(any("saved symbology" in w for w in payload["templateWarnings"]))

    def test_a_dataset_layer_with_a_styled_publication_names_it(self):
        client = _Client(
            publication_list=[
                {"raw": {"id": 204, "protocol": "wms", "canonicalStyleRevision": "rev"}}
            ]
        )
        payload = show_map(client, layers=[{"kind": "portal-dataset", "datasetId": 1577}])
        self.assertTrue(any("204" in w for w in payload["templateWarnings"]))

    def test_an_explicitly_styled_dataset_layer_is_not_warned(self):
        payload = show_map(
            _Client(details={"display": {"esri": {"renderer": {"type": "uniqueValue"}}}}),
            layers=[{"kind": "portal-dataset", "datasetId": 1577, "style": {"fill": "#ff0000"}}],
        )
        self.assertFalse(any("saved symbology" in w for w in payload["templateWarnings"]))

    def test_a_caller_symbology_shorthand_derives_unique_value_classes(self):
        # `symbology: {type, field}` is derived from the layer's own data: one
        # colour per distinct value, and NO palette `style` is attached (which
        # would override it in the viewer).
        payload = show_map(
            _Client(feature_collection=_sample_features()),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "uniqueValue", "field": "Ownership"}}
            ],
        )
        layer = payload["layers"][0]
        sym = layer["symbology"]
        self.assertEqual(sym["type"], "uniqueValue")
        self.assertEqual(sym["field"], "Ownership")
        self.assertEqual({e["value"] for e in sym["unique"]}, {1, 2})
        self.assertTrue(all(e["style"]["fill"] for e in sym["unique"]))
        self.assertNotIn("style", layer)

    def test_a_caller_symbology_labels_codes_with_the_field_domain(self):
        # A coded-value field's legend entry must read the human value (the domain
        # label), not the raw integer code, and the legend title is the field alias.
        details = {
            "fields": [
                {"name": "Ownership", "alias": "مالکیت",
                 "domain": {"type": "codedValues",
                            "items": [{"code": 1, "value": "اوقاف"},
                                      {"code": 2, "value": "مستثنیات"}]}}
            ]
        }
        payload = show_map(
            _Client(details=details, feature_collection=_sample_features()),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "uniqueValue", "field": "Ownership"}}
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual([e["label"] for e in sym["unique"]], ["اوقاف", "مستثنیات"])
        self.assertEqual(sym["legend"]["title"], "مالکیت")

    def test_a_complete_caller_unique_value_spec_gets_a_derived_legend(self):
        # A caller-supplied COMPLETE uniqueValue spec used to be passed through with
        # no legend, so the panel rendered a blank/grey row. It must now derive a
        # legend from its own classes (the same rule the dataset renderer follows).
        payload = show_map(
            _Client(),
            layers=[
                {
                    "kind": "portal-dataset",
                    "datasetId": 1577,
                    "symbology": {
                        "type": "uniqueValue",
                        "field": "Landuse_Group",
                        "unique": [
                            {"value": "1", "label": "مسکونی", "style": {"fill": "#e6194b"}},
                            {"value": "5", "label": "تجاری", "style": {"fill": "#0047ff"}},
                        ],
                        "default": {"fill": "#b0b0b0"},
                    },
                }
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(sym["type"], "uniqueValue")
        self.assertEqual([e["label"] for e in sym["legend"]["entries"]], ["مسکونی", "تجاری"])
        self.assertEqual(sym["legend"]["entries"][0]["style"]["fill"], "#e6194b")

    def test_a_complete_caller_spec_keeps_its_explicit_legend(self):
        payload = show_map(
            _Client(),
            layers=[
                {
                    "kind": "portal-dataset",
                    "datasetId": 1577,
                    "symbology": {
                        "type": "uniqueValue",
                        "field": "f",
                        "unique": [{"value": "1", "style": {"fill": "#111111"}}],
                        "legend": {
                            "title": "دستی",
                            "entries": [{"label": "mine", "style": {"fill": "#222222"}}],
                        },
                    },
                }
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(sym["legend"]["title"], "دستی")
        self.assertEqual(sym["legend"]["entries"][0]["label"], "mine")

    def test_a_dataset_layer_exposes_field_labels_and_domains_for_identify(self):
        # The manifest carries the dataset's field aliases + coded-value domains so
        # the viewer's identify popup can label a code with its human value.
        details = {
            "fields": [
                {"name": "Ownership", "alias": "مالکیت",
                 "domain": {"type": "codedValues",
                            "items": [{"code": 1, "value": "اوقاف"}]}},
                {"name": "Parcel_Number", "alias": "شماره قطعه"},
            ]
        }
        payload = show_map(
            _Client(details=details),
            layers=[{"kind": "portal-dataset", "datasetId": 1577}],
        )
        fields = {f["name"]: f for f in payload["layers"][0]["fields"]}
        self.assertEqual(fields["Ownership"]["alias"], "مالکیت")
        self.assertEqual(fields["Ownership"]["domain"]["1"], "اوقاف")
        self.assertEqual(fields["Parcel_Number"]["domain"], {})

    def test_a_dataset_without_field_metadata_carries_no_fields(self):
        payload = show_map(_Client(), layers=[{"kind": "portal-dataset", "datasetId": 7}])
        self.assertNotIn("fields", payload["layers"][0])

    def test_a_publication_layer_carries_its_queryable_wms_layer_name(self):
        # A WMS/WMTS image layer is identified with GetFeatureInfo, which must send
        # the publication's queryable GeoServer layer name as QUERY_LAYERS.
        class _NamedPublications(_Publications):
            def get(self, publication_id):
                return {"id": publication_id, "datasetId": 7, "protocol": "wms",
                        "canonicalName": "pub_1577_wms_direct_source"}

        client = _Client()
        client.publications = _NamedPublications()
        payload = show_map(client, layers=[{"kind": "portal-publication", "publicationId": 60}])
        self.assertEqual(
            payload["layers"][0]["identifyWmsLayers"], "pub_1577_wms_direct_source"
        )

    def test_a_publication_without_a_layer_name_has_no_identify_layers(self):
        payload = show_map(_Client(), layers=[{"kind": "portal-publication", "publicationId": 60}])
        self.assertNotIn("identifyWmsLayers", payload["layers"][0])

    def test_center_and_zoom_point_the_view_and_skip_autofit(self):
        # `center`/`zoom` are sugar for template.view and switch the mode to
        # 'center' so the viewer does not auto-fit away from the requested point.
        payload = show_map(_Client(), center=[59.26, 36.48], zoom=14)
        view = payload["options"]["view"]
        self.assertEqual(view["center"], [59.26, 36.48])
        self.assertEqual(view["zoom"], 14)
        self.assertEqual(view["mode"], "center")

    def test_an_invalid_center_is_warned_and_ignored(self):
        payload = show_map(_Client(), center=[999, 999])
        self.assertTrue(any("center" in w for w in payload["templateWarnings"]))
        self.assertNotEqual(payload["options"]["view"]["center"], [999, 999])

    def test_a_caller_symbology_shorthand_derives_class_breaks(self):
        payload = show_map(
            _Client(feature_collection=_sample_features()),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "classBreaks", "field": "DB_SHAPE_Area", "classes": 5}}
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(sym["type"], "classBreaks")
        self.assertEqual(len(sym["breaks"]), 5)
        self.assertEqual(sym["breaks"][0]["min"], 100.0)
        self.assertEqual(sym["breaks"][-1]["max"], 300.0)
        self.assertNotEqual(sym["breaks"][0]["style"]["fill"], sym["breaks"][-1]["style"]["fill"])

    def test_class_breaks_use_server_quantiles_honouring_the_layer_filter(self):
        # A filtered layer's breaks must describe the FILTERED column, not a local
        # sample: the layer's own filter is forwarded to the aggregate lane and the
        # breaks span the whole column (issue report 2026-11-24, N2 — a 356-row
        # filtered layer reproduced the whole 18,648-row dataset's sampled breaks).
        features = {
            "type": "FeatureCollection",
            "features": [
                _feature({"DB_SHAPE_Area": value})
                for value in (10000.0, 20000.0, 30000.0, 40000.0)
            ],
        }
        client = _Client(feature_collection=features)
        payload = show_map(
            client,
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "query": {"filter": {"field": "DB_SHAPE_Area", "operator": ">", "value": 1000}},
                 "symbology": {"type": "classBreaks", "field": "DB_SHAPE_Area", "classes": 2}}
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(len(sym["breaks"]), 2)
        self.assertEqual(sym["breaks"][0]["min"], 10000.0)
        self.assertEqual(sym["breaks"][-1]["max"], 40000.0)
        agg_calls = [call for call in client.datasets.calls if "aggregation" in call]
        self.assertTrue(agg_calls)
        sent_filter = agg_calls[-1]["filter"]
        self.assertEqual(sent_filter["type"], "rule")
        self.assertEqual(sent_filter["field"], "DB_SHAPE_Area")

    def test_class_breaks_fall_back_to_a_sample_with_a_warning(self):
        # When the store cannot aggregate, a sampled estimate is used BUT disclosed —
        # a sampled legend must never be passed off as exact.
        client = _Client(feature_collection=_sample_features())

        def _boom(*args, **kwargs):
            raise RuntimeError("aggregation unsupported")

        client.datasets.aggregate = _boom
        payload = show_map(
            client,
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "classBreaks", "field": "DB_SHAPE_Area", "classes": 5}}
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(sym["type"], "classBreaks")
        warning = next(w for w in payload["templateWarnings"] if "server-side" in w)
        self.assertIn("sample", warning)

    def test_a_class_breaks_count_is_capped_with_a_warning(self):
        payload = show_map(
            _Client(feature_collection=_sample_features()),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "classBreaks", "field": "DB_SHAPE_Area", "classes": 50}}
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(len(sym["breaks"]), 12)
        self.assertTrue(any("capped" in w for w in payload["templateWarnings"]))

    def test_a_unique_value_palette_does_not_repeat_under_the_cap(self):
        # 18 categories must get 18 DISTINCT colours; the palette used to cycle at
        # 12, drawing two unrelated categories the same (issue report 2026-11-24, N3).
        features = {
            "type": "FeatureCollection",
            "features": [_feature({"Landuse_Group": str(i)}) for i in range(18)],
        }
        payload = show_map(
            _Client(feature_collection=features),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "uniqueValue", "field": "Landuse_Group"}}
            ],
        )
        unique = payload["layers"][0]["symbology"]["unique"]
        fills = [entry["style"]["fill"] for entry in unique]
        self.assertEqual(len(fills), 18)
        self.assertEqual(len(set(fills)), 18)

    def test_a_caller_symbology_wins_over_the_dataset_renderer(self):
        details = {
            "display": {
                "esri": {
                    "renderer": {
                        "type": "uniqueValue",
                        "field1": "Landuse_Group",
                        "uniqueValueInfos": [
                            {"value": "9", "label": "X",
                             "symbol": {"type": "esriSFS", "color": [1, 2, 3]}}
                        ],
                    }
                }
            }
        }
        payload = show_map(
            _Client(details=details, feature_collection=_sample_features()),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "uniqueValue", "field": "Ownership"}}
            ],
        )
        self.assertEqual(payload["layers"][0]["symbology"]["field"], "Ownership")

    def test_a_high_cardinality_shorthand_styles_up_to_the_cap_and_warns(self):
        # A field above the documented cap is styled up to the cap (the distinct
        # values are counted by grouping the column, not by a feature sample) and
        # the remainder is disclosed — never silently under-styled.
        features = {
            "type": "FeatureCollection",
            "features": [_feature({"Parcel_Number": str(i)}) for i in range(40)],
        }
        payload = show_map(
            _Client(feature_collection=features),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "uniqueValue", "field": "Parcel_Number"}}
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(sym["type"], "uniqueValue")
        self.assertEqual(len(sym["unique"]), 30)
        warning = next(w for w in payload["templateWarnings"] if "distinct values" in w)
        self.assertIn("40", warning)

    def test_a_unique_value_shorthand_counts_all_categories_not_a_sample(self):
        # 18 categories, but the first 1000 features only carried 7 of them: a
        # feature sample under-counts, so the shorthand groups the whole column.
        properties = [{"Landuse_Group": str(i % 18)} for i in range(1200)]
        features = {
            "type": "FeatureCollection",
            "features": [_feature(props) for props in properties],
        }
        payload = show_map(
            _Client(feature_collection=features),
            layers=[
                {"kind": "portal-dataset", "datasetId": 1577,
                 "symbology": {"type": "uniqueValue", "field": "Landuse_Group"}}
            ],
        )
        sym = payload["layers"][0]["symbology"]
        self.assertEqual(len(sym["unique"]), 18)

    def test_replace_layers_rebuilds_an_existing_map(self):
        first = show_map(
            _Client(),
            layers=[
                {"kind": "inline-geometry", "geojson": SQUARE},
                {"kind": "inline-geometry", "geojson": SQUARE},
            ],
        )
        second = show_map(
            _Client(),
            map_id=first["mapId"],
            layers=[{"kind": "inline-geometry", "geojson": SQUARE}],
            replace_layers=True,
        )
        self.assertEqual(second["mapId"], first["mapId"])
        self.assertEqual(len(second["layers"]), 1)
        self.assertTrue(second["layersReplaced"])

    def test_remove_layers_drops_named_layers(self):
        first = show_map(
            _Client(),
            layers=[
                {"kind": "inline-geometry", "geojson": SQUARE},
                {"kind": "inline-geometry", "geojson": SQUARE},
            ],
        )
        victim = first["layers"][0]["id"]
        second = show_map(_Client(), map_id=first["mapId"], remove_layers=[victim])
        self.assertEqual([layer["id"] for layer in second["layers"]], [first["layers"][1]["id"]])
        self.assertIn(victim, second["removedLayers"])

    def test_removing_an_unknown_layer_warns(self):
        first = show_map(_Client(), layers=[{"kind": "inline-geometry", "geojson": SQUARE}])
        second = show_map(_Client(), map_id=first["mapId"], remove_layers=["layer_missing"])
        self.assertEqual(len(second["layers"]), 1)
        self.assertTrue(any("unknown layer id" in w for w in second["templateWarnings"]))

    def test_a_symbology_on_an_image_render_warns(self):
        payload = show_map(
            _Client(),
            layers=[
                {"kind": "portal-publication", "publicationId": 60, "render": "wms",
                 "symbology": {"type": "uniqueValue", "field": "x"}}
            ],
        )
        self.assertTrue(any("does not affect" in w for w in payload["templateWarnings"]))

    def test_a_cog_dataset_layer_gets_a_cog_renderer_and_url(self):
        # A raster dataset with a Cloud-Optimized GeoTIFF is drawn directly (the
        # viewer streams bytes via /cog), not vectorised and not warned about.
        payload = show_map(
            _Client(details={"hasCOG": True}, data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1949}],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["render"], "cog")
        self.assertTrue(layer["raster"])
        self.assertTrue(layer["cogUrl"].endswith("/cog/1949"))
        self.assertFalse(any("is raster" in w for w in payload["templateWarnings"]))

    def test_a_cog_layer_carries_band_metadata_for_value_lookup(self):
        # Band metadata (type, no-data) lets the viewer label the value read at a
        # click and mask the no-data sentinel.
        details = {
            "hasCOG": True,
            "bands": [
                {"band": 1, "type": "Int32", "colorInterpretation": "Gray",
                 "minimum": 1123, "maximum": 1404, "noDataValue": -2147483647},
            ],
        }
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1949}],
        )
        bands = payload["layers"][0]["rasterBands"]
        self.assertEqual(bands[0]["band"], 1)
        self.assertEqual(bands[0]["noDataValue"], -2147483647)
        self.assertEqual(bands[0]["minimum"], 1123)

    def test_a_layer_without_bands_carries_no_raster_bands(self):
        payload = show_map(_Client(), layers=[{"kind": "portal-dataset", "datasetId": 7}])
        self.assertNotIn("rasterBands", payload["layers"][0])

    def test_a_cog_layer_applies_its_saved_display_as_an_ol_style(self):
        # A COG is drawn client-side, so the MCP translates the saved `display`
        # into an OpenLayers WebGL style instead of warning that it is unapplied.
        details = {
            "hasCOG": True,
            "bands": [{"band": 1, "type": "Float32", "minimum": 0, "maximum": 100}],
            "display": {
                "displayType": "colorMap", "band": 1, "colorMap": "custom",
                "minimum": 0, "maximum": 100,
                "customColorMap": [
                    {"value": 0, "r": 255, "g": 0, "b": 0, "a": 255},
                    {"value": 100, "r": 0, "g": 0, "b": 255, "a": 255},
                ],
            },
        }
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{"kind": "portal-dataset", "datasetId": 1949}],
        )
        layer = payload["layers"][0]
        self.assertEqual(layer["render"], "cog")
        self.assertEqual(
            layer["rasterStyle"]["color"][:6],
            ["interpolate", ["linear"], ["band", 1], 0, [255, 0, 0, 1.0], 100],
        )
        self.assertFalse(any("saved symbology" in w for w in payload["templateWarnings"]))

    def test_a_caller_display_overrides_a_cog_saved_display(self):
        details = {
            "hasCOG": True,
            "bands": [{"band": 1, "type": "Byte", "minimum": 0, "maximum": 100}],
            "display": {"displayType": "colorMap", "band": 1, "colorMap": "grayscale"},
        }
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{
                "kind": "portal-dataset", "datasetId": 1949,
                "display": {"displayType": "colorMap", "band": 1, "colorMap": "fire",
                            "minimum": 0, "maximum": 100},
            }],
        )
        color = payload["layers"][0]["rasterStyle"]["color"]
        self.assertEqual(color[4], [0, 0, 0, 1.0])
        self.assertEqual(color[-1], [243, 255, 221, 1.0])

    def test_a_cog_display_that_cannot_be_styled_warns_and_keeps_default(self):
        details = {"hasCOG": True, "bands": [{"band": 1, "type": "Float32"}]}
        payload = show_map(
            _Client(details=details, data_type="raster"),
            layers=[{
                "kind": "portal-dataset", "datasetId": 1949,
                "display": {"displayType": "colorMap", "band": 1, "colorMap": "custom",
                            "customColorMap": [
                                {"value": "50%", "r": 1, "g": 2, "b": 3, "a": 255}
                            ]},
            }],
        )
        layer = payload["layers"][0]
        self.assertNotIn("rasterStyle", layer)
        self.assertTrue(
            any("COG cannot apply" in w for w in payload["templateWarnings"])
        )

    def test_render_cog_on_a_non_cog_dataset_warns_and_falls_back(self):
        payload = show_map(
            _Client(),
            layers=[{"kind": "portal-dataset", "datasetId": 7, "render": "cog"}],
        )
        self.assertNotEqual(payload["layers"][0]["render"], "cog")
        self.assertTrue(
            any("Cloud-Optimized GeoTIFF" in w for w in payload["templateWarnings"])
        )

    def test_a_large_dataset_layer_warns_about_the_geojson_cap(self):
        payload = show_map(
            _Client(feature_total=18648),
            layers=[{"kind": "portal-dataset", "datasetId": 1577}],
        )
        warning = next(w for w in payload["templateWarnings"] if "18648" in w)
        self.assertIn("1000", warning)
        self.assertIn("limit", warning)
        self.assertIn("mvt", warning)

    def test_a_layer_limit_of_zero_is_not_warned_about_truncation(self):
        payload = show_map(
            _Client(feature_total=18648),
            layers=[{"kind": "portal-dataset", "datasetId": 1577, "limit": 0}],
        )
        self.assertFalse(any("18648" in w for w in payload["templateWarnings"]))

    def test_an_mvt_layer_warns_that_its_data_url_is_truncated(self):
        # An MVT layer's MAP is full coverage, but its advertised `dataUrl` still
        # comes from the GeoJSON lane and is capped at 1,000 (issue report
        # 2026-11-24, N5). The warning must disclose the dataUrl truncation — not
        # claim the map is truncated.
        payload = show_map(
            _Client(feature_total=18648),
            layers=[{"kind": "portal-dataset", "datasetId": 1577, "render": "mvt"}],
        )
        warning = next(w for w in payload["templateWarnings"] if "18648" in w)
        self.assertIn("dataUrl", warning)
        self.assertIn("1000", warning)
        self.assertNotIn("a GeoJSON layer", warning)

    def test_an_mvt_layer_with_full_limit_does_not_warn_about_truncation(self):
        payload = show_map(
            _Client(feature_total=18648),
            layers=[{"kind": "portal-dataset", "datasetId": 1577, "render": "mvt", "limit": 0}],
        )
        self.assertFalse(any("18648" in w for w in payload["templateWarnings"]))

    def test_a_dataset_within_the_cap_is_not_warned(self):
        payload = show_map(
            _Client(feature_total=500),
            layers=[{"kind": "portal-dataset", "datasetId": 1577}],
        )
        self.assertFalse(any("500 features" in w for w in payload["templateWarnings"]))

    def test_an_explicit_limit_above_the_total_is_not_warned(self):
        payload = show_map(
            _Client(feature_total=18648),
            layers=[{"kind": "portal-dataset", "datasetId": 1577, "limit": 30000}],
        )
        self.assertFalse(any("18648" in w for w in payload["templateWarnings"]))


class SurfacePinTest(unittest.TestCase):
    def test_the_surface_is_thirty_two_tools(self):
        from geopack_sdk_mcp.server import mcp

        names = {tool.name for tool in mcp._tool_manager.list_tools()}  # noqa: SLF001
        self.assertEqual(len(names), 32)
        self.assertIn("geopack_sdk_show_map", names)
        self.assertIn("geopack_sdk_geometry_op", names)
        self.assertIn("geopack_sdk_auth_status", names)
        self.assertNotIn("geopack_sdk_render_chart", names)


if __name__ == "__main__":
    unittest.main()
