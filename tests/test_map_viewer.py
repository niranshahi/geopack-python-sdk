"""Slice 033 Lane B — the built-in viewer and the user-editable template."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from geopack_sdk_mcp.maps import viewer
from geopack_sdk_mcp.maps.manifest import layer_from_spec
from geopack_sdk_mcp.maps.service import LocalService, resolve_assets
from geopack_sdk_mcp.maps.sources import merge_query
from geopack_sdk_mcp.tool_handlers.maps import show_map

PORTAL = "http://portal.example/api"


class _Response:
    content = b"\x1a\x00tile"
    headers = {"Content-Type": "application/vnd.mapbox-vector-tile"}
    status_code = 200
    ok = True


class _Auth:
    token = "PORTAL-SECRET"


class _Session:
    def get(self, url, headers=None, params=None, timeout=None):
        return _Response()


class _Datasets:
    def query(self, dataset_id, *args, **kwargs):
        return {"type": "FeatureCollection", "features": []}

    def get(self, dataset_id):
        return {"id": dataset_id, "dataType": "vector", "details": {}}


class _Publications:
    def get(self, publication_id):
        return {"id": publication_id, "datasetId": 7, "protocol": "wms"}


class _Client:
    base_url = PORTAL

    def __init__(self):
        self.auth = _Auth()
        self.session = _Session()
        self.datasets = _Datasets()
        self.publications = _Publications()


def _http(port, path, token=None, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    target = path if token is None else f"{path}{'&' if '?' in path else '?'}t={token}"
    conn.request(method, target)
    response = conn.getresponse()
    body = response.read()
    headers = dict(response.getheaders())
    status = response.status
    conn.close()
    return status, body, headers


class TemplateMergeTest(unittest.TestCase):
    def test_default_source(self):
        template, warnings, source = viewer.load_template(None)
        self.assertEqual(source, "default")
        self.assertEqual(warnings, [])
        self.assertEqual(template["basemap"], "osm")
        self.assertIsInstance(template["basemaps"], list)

    def test_user_template_wins_and_unknown_keys_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "template.json"), "w", encoding="utf-8") as handle:
                json.dump({"title": "Mine", "nope": 1}, handle)
            template, warnings, source = viewer.load_template(tmp)

        self.assertEqual(source, "user")
        self.assertEqual(template["title"], "Mine")
        self.assertTrue(any("'nope'" in w for w in warnings))

    def test_a_wrong_type_falls_back_for_that_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "template.json"), "w", encoding="utf-8") as handle:
                json.dump({"title": 42, "palette": {"accent": "#123456"}}, handle)
            template, warnings, source = viewer.load_template(tmp)

        self.assertEqual(source, "user")
        self.assertEqual(template["title"], viewer.default_template()["title"])
        self.assertEqual(template["palette"]["accent"], "#123456")
        self.assertTrue(any("title" in w for w in warnings))

    def test_per_call_wins_over_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "template.json"), "w", encoding="utf-8") as handle:
                json.dump({"title": "User"}, handle)
            template, _, source = viewer.load_template(tmp, {"title": "Call"})

        self.assertEqual(source, "user")
        self.assertEqual(template["title"], "Call")

    def test_unreadable_template_is_lenient(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "template.json"), "w", encoding="utf-8") as handle:
                handle.write("{not json")
            template, warnings, source = viewer.load_template(tmp)

        self.assertEqual(source, "default")
        self.assertEqual(template["title"], viewer.default_template()["title"])
        self.assertTrue(warnings)


class BasemapTest(unittest.TestCase):
    def test_resolve_named_and_missing(self):
        template = viewer.default_template()
        self.assertEqual(viewer.resolve_basemap(template, "blank")["type"], "none")
        self.assertEqual(viewer.resolve_basemap(template, "osm")["id"], "osm")
        self.assertIsNotNone(viewer.resolve_basemap(template, "missing"))


class RenderHtmlTest(unittest.TestCase):
    def test_html_carries_manifest_and_runtime(self):
        template = viewer.default_template()
        template["title"] = "Demo <x>"
        html = viewer.render_viewer_html(
            title="Demo <x>",
            manifest_url="http://127.0.0.1:9/map/m1/manifest.json",
            template=template,
            assets={"ol_js": "/v/ol.js", "ol_css": "/v/ol.css"},
        )

        self.assertIn("/v/ol.js", html)
        self.assertIn("/v/ol.css", html)
        self.assertIn("/map/m1/manifest.json", html)
        self.assertIn("Demo &lt;x&gt;", html)
        self.assertIn("new ol.Map", html)

    def test_the_page_is_a_resource_file_not_an_embedded_string(self):
        # The shipped page lives on disk so it is editable without touching code.
        path = os.path.join(viewer.DEFAULT_TEMPLATES_DIR, "viewer.html")
        self.assertTrue(os.path.isfile(path))
        self.assertIn("__TEMPLATE_JSON__", viewer.default_viewer_html())

    def test_osm_tiles_override_the_document_referrer_policy(self):
        # OSM answers "access blocked" when a tile has no Referer; the page sets a
        # per-element referrerPolicy on every XYZ tile <img>.
        html = viewer.render_viewer_html(
            title="t",
            manifest_url="http://127.0.0.1:9/map/m1/manifest.json",
            template=viewer.default_template(),
            assets={"ol_js": "/v/ol.js", "ol_css": "/v/ol.css"},
        )
        self.assertIn("strict-origin-when-cross-origin", html)
        self.assertIn("referrerPolicy", html)
        self.assertIn("tileLoadFunction", html)

    def test_layer_list_and_legend_render_data_layers(self):
        # Regression: the list iterated basemaps only (empty) and the legend was
        # drawn before the panel reset — data layers now drive both.
        html = viewer.default_viewer_html()
        self.assertIn("dataLayers", html)
        self.assertIn("renderPanel(map, baseLayers, dataLayers)", html)
        self.assertNotIn("baseLayers.filter(", html)
        self.assertIn("validWgs84BBox", html)


class ViewerHtmlTest(unittest.TestCase):
    def test_default_source_when_no_user_page(self):
        html, source, warnings = viewer.load_viewer_html(None)
        self.assertEqual(source, "default")
        self.assertEqual(warnings, [])
        self.assertIn("__TEMPLATE_JSON__", html)

    def test_user_page_wins_when_required_placeholders_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = viewer.default_viewer_html().replace("<title>__TITLE__</title>", "<title>Mine</title>")
            with open(os.path.join(tmp, "viewer.html"), "w", encoding="utf-8") as handle:
                handle.write(page)
            html, source, warnings = viewer.load_viewer_html(tmp)

        self.assertEqual(source, "user")
        self.assertEqual(warnings, [])
        self.assertIn("<title>Mine</title>", html)

    def test_a_user_page_missing_required_placeholders_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "viewer.html"), "w", encoding="utf-8") as handle:
                handle.write("<!DOCTYPE html><html><body>no placeholders</body></html>")
            html, source, warnings = viewer.load_viewer_html(tmp)

        self.assertEqual(source, "default")
        self.assertEqual(html, viewer.default_viewer_html())
        self.assertTrue(any("__TEMPLATE_JSON__" in w for w in warnings))


class LayerRenderTest(unittest.TestCase):
    def test_publication_layer_exposes_ogc_urls(self):
        layer = layer_from_spec({"kind": "portal-publication", "publicationId": 5})
        public = layer.public("http://127.0.0.1:9")

        self.assertEqual(public["render"], "wms")
        self.assertTrue(public["wmsUrl"].endswith("/proxy/publication/5/wms"))
        self.assertTrue(public["wmtsUrl"].endswith("/proxy/publication/5/wmts"))
        self.assertTrue(public["wfsUrl"].endswith("/proxy/publication/5/wfs"))

    def test_render_override_is_honoured(self):
        layer = layer_from_spec({
            "kind": "inline-geometry",
            "geojson": {"type": "Point", "coordinates": [0, 0]},
            "render": "mvt",
        })
        self.assertEqual(layer.public("http://x")["render"], "mvt")

    def test_unknown_render_is_refused(self):
        from geopack_sdk_mcp.maps.errors import MapServiceError

        with self.assertRaises(MapServiceError):
            layer_from_spec({
                "kind": "inline-geometry",
                "geojson": {"type": "Point", "coordinates": [0, 0]},
                "render": "nope",
            })


class MergeQueryTest(unittest.TestCase):
    def test_browser_params_win_and_are_merged(self):
        merged = merge_query(
            "http://geo.example/wms?token=abc&layers=w:l1",
            {"REQUEST": ["GetMap"], "BBOX": ["0,0,1,1"]},
        )
        self.assertIn("token=abc", merged)
        self.assertIn("BBOX=", merged)
        self.assertIn("REQUEST=GetMap", merged)
        self.assertIn("layers=w%3Al1", merged)


class AssetsTest(unittest.TestCase):
    def test_vendored_dir_switches_to_local_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"GEOPACK_MCP_MAP_ASSETS": tmp}):
                urls, directory = resolve_assets()
        self.assertEqual(urls["ol_js"], "/viewer/asset/ol.js")
        self.assertEqual(directory, os.path.realpath(tmp))

    def test_default_is_the_cdn(self):
        urls, directory = resolve_assets()
        self.assertIn("cdn.jsdelivr.net", urls["ol_js"])
        self.assertIsNone(directory)


class ViewerRoutesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.service = LocalService(
            _Client(),
            token="localtoken",
            templates_dir=self._tmp.name,
            assets={"ol_js": "/viewer/asset/ol.js", "ol_css": "/viewer/asset/ol.css"},
        )
        self.service.start()
        self.addCleanup(self.service.stop)
        self.manifest = self.service.create_map("Demo")
        self.port = self.service.port

    def test_the_shell_is_served_without_a_token_and_sets_csp(self):
        status, body, headers = _http(self.port, f"/map/{self.manifest.map_id}")

        self.assertEqual(status, 200)
        self.assertIn("<html", body.decode("utf-8"))
        self.assertIn("Content-Security-Policy", headers)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        # Origin-only (not no-referrer): OSM needs a Referer but the token must not leak.
        self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")

    def test_a_user_viewer_page_is_served(self):
        page = viewer.default_viewer_html().replace(
            "<title>__TITLE__</title>", "<title>House page</title>"
        )
        with open(os.path.join(self._tmp.name, "viewer.html"), "w", encoding="utf-8") as handle:
            handle.write(page)
        status, body, _ = _http(self.port, f"/map/{self.manifest.map_id}")

        self.assertEqual(status, 200)
        self.assertIn("<title>House page</title>", body.decode("utf-8"))

    def test_a_valid_query_token_is_embedded_in_the_shell(self):
        status, body, _ = _http(self.port, f"/map/{self.manifest.map_id}", token="localtoken")
        self.assertEqual(status, 200)
        self.assertIn('TOKEN_EMBEDDED = "localtoken"', body.decode("utf-8"))

    def test_an_invalid_query_token_is_not_embedded(self):
        status, body, _ = _http(self.port, f"/map/{self.manifest.map_id}", token="wrong")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn('TOKEN_EMBEDDED = ""', text)
        self.assertNotIn('TOKEN_EMBEDDED = "wrong"', text)

    def test_the_manifest_route_requires_the_token(self):
        status, _, _ = _http(self.port, f"/map/{self.manifest.map_id}/manifest.json")
        self.assertEqual(status, 401)

        status, body, _ = _http(
            self.port, f"/map/{self.manifest.map_id}/manifest.json", token="localtoken"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["mapId"], self.manifest.map_id)

    def test_user_viewer_css_is_served(self):
        with open(os.path.join(self._tmp.name, "viewer.css"), "w", encoding="utf-8") as handle:
            handle.write(".gp { color: red }")
        self.assertIsNotNone(self.service.user_css_url())

        status, body, headers = _http(self.port, "/viewer/asset/viewer.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("Content-Type", ""))
        self.assertIn(b".gp", body)

    def test_unknown_viewer_asset_is_refused(self):
        status, _, _ = _http(self.port, "/viewer/asset/secret.txt")
        self.assertNotEqual(status, 200)


class ShowMapTemplateTest(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {"GEOPACK_MCP_MAP_SERVICE": "1"})
        self._env.start()
        self.addCleanup(self._env.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._tpl = patch.dict(os.environ, {"GEOPACK_MCP_MAP_TEMPLATES": self._tmp.name})
        self._tpl.start()
        self.addCleanup(self._tpl.stop)
        from geopack_sdk_mcp.maps import reset_for_tests

        self.addCleanup(reset_for_tests)
        reset_for_tests()

    def test_per_call_template_and_basemap(self):
        payload = show_map(
            _Client(),
            title="X",
            basemap="blank",
            template={"palette": {"accent": "#ff0000"}, "subtitle": "hello"},
            style={"fill": "#0000ff"},
        )

        self.assertEqual(payload["templateUsed"], "call")
        self.assertEqual(payload["basemap"], "blank")
        self.assertIn("templatePath", payload)
        self.assertTrue(payload["viewerHtmlPath"].endswith("viewer.html"))
        self.assertEqual(payload["viewerHtmlUsed"], "default")
        self.assertTrue(payload["viewerUrl"].startswith("http://127.0.0.1:"))
        self.assertIn("/map/", payload["viewerUrl"])
        self.assertIn("?t=", payload["viewerUrl"])
        options = payload["options"]
        self.assertEqual(options["palette"]["accent"], "#ff0000")
        self.assertEqual(options["subtitle"], "hello")
        self.assertEqual(options["layerStyle"]["fill"], "#0000ff")

    def test_user_template_is_discovered(self):
        with open(os.path.join(self._tmp.name, "template.json"), "w", encoding="utf-8") as handle:
            json.dump({"title": "House style", "nope": True}, handle)
        payload = show_map(_Client())

        self.assertEqual(payload["templateUsed"], "user")
        self.assertEqual(payload["options"]["title"], "House style")
        self.assertTrue(payload["templateWarnings"])


if __name__ == "__main__":
    unittest.main()
