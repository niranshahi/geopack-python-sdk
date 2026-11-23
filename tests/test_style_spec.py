"""Slice 033 §12 — the portable style spec derived from an ESRI renderer."""

from __future__ import annotations

import json
import unittest

from geopack_sdk_mcp.sanitize.dataset_symbology import field_meta_from_details
from geopack_sdk_mcp.sanitize.style_spec import (
    breaks_spec,
    categorical_spec,
    dataset_style_spec,
    esri_renderer_to_spec,
    field_values_from_geojson,
    quantile_breaks,
)


def _polygon_symbol(fill, alpha=196, stroke=(131, 129, 126, 255), width=0.75):
    return {
        "type": "esriSFS",
        "color": [fill[0], fill[1], fill[2], alpha],
        "outline": {"type": "esriSLS", "color": list(stroke), "width": width},
    }


class RendererToSpecTest(unittest.TestCase):
    def test_unique_value_infos_become_unique_entries(self):
        renderer = {
            "type": "uniqueValue",
            "field1": "Landuse_Group",
            "uniqueValueInfos": [
                {"value": "1", "label": "Residential", "symbol": _polygon_symbol((27, 158, 119))},
                {"value": "3", "label": "Educational", "symbol": _polygon_symbol((125, 144, 89))},
            ],
            "defaultSymbol": _polygon_symbol((252, 0, 0)),
        }
        spec = esri_renderer_to_spec(renderer)

        self.assertEqual(spec["type"], "uniqueValue")
        self.assertEqual(spec["geometry"], "polygon")
        self.assertEqual(spec["field"], "Landuse_Group")
        self.assertEqual(spec["unique"][0]["value"], "1")
        self.assertEqual(spec["unique"][0]["style"]["fill"], "#1b9e77")
        self.assertEqual(spec["unique"][1]["style"]["fill"], "#7d9059")
        # alpha 196/255 -> opacity ~0.769
        self.assertAlmostEqual(spec["unique"][0]["style"]["opacity"], 0.769, places=3)
        self.assertEqual(spec["unique"][0]["style"]["stroke"], "#83817e")
        self.assertEqual(spec["unique"][0]["style"]["weight"], 0.75)
        self.assertEqual(spec["default"]["fill"], "#fc0000")
        self.assertEqual(spec["legend"]["title"], "Landuse_Group")
        self.assertEqual(spec["legend"]["entries"][0]["label"], "Residential")
        self.assertEqual(spec["legend"]["entries"][0]["style"]["fill"], "#1b9e77")

    def test_unique_value_groups_are_used_when_infos_absent(self):
        renderer = {
            "type": "uniqueValue",
            "field1": "kind",
            "uniqueValueGroups": [
                {"classes": [{"label": "A", "values": [["x"]], "symbol": _polygon_symbol((10, 20, 30))}]}
            ],
        }
        spec = esri_renderer_to_spec(renderer)
        self.assertEqual(spec["unique"][0]["value"], "x")
        self.assertEqual(spec["unique"][0]["style"]["fill"], "#0a141e")

    def test_class_breaks_become_breaks(self):
        renderer = {
            "type": "classBreaks",
            "field": "pop",
            "classBreakInfos": [
                {"classMinValue": 0, "classMaxValue": 100, "label": "0-100",
                 "symbol": _polygon_symbol((200, 0, 0))},
                {"classMinValue": 100, "classMaxValue": 500, "label": "100-500",
                 "symbol": _polygon_symbol((0, 200, 0))},
            ],
        }
        spec = esri_renderer_to_spec(renderer)
        self.assertEqual(spec["type"], "classBreaks")
        self.assertEqual(spec["field"], "pop")
        self.assertEqual(spec["breaks"][0]["min"], 0)
        self.assertEqual(spec["breaks"][0]["max"], 100)
        self.assertEqual(spec["breaks"][1]["style"]["fill"], "#00c800")
        self.assertEqual(spec["legend"]["entries"][1]["label"], "100-500")

    def test_simple_renderer_becomes_a_simple_spec(self):
        renderer = {"type": "simple", "symbol": _polygon_symbol((59, 167, 118))}
        spec = esri_renderer_to_spec(renderer)
        self.assertEqual(spec["type"], "simple")
        self.assertNotIn("legend", spec)
        self.assertEqual(spec["simple"]["fill"], "#3ba776")

    def test_a_line_symbol_maps_to_stroke(self):
        renderer = {"type": "simple", "symbol": {"type": "esriSLS", "color": [255, 0, 0, 255], "width": 3}}
        spec = esri_renderer_to_spec(renderer)
        self.assertEqual(spec["geometry"], "line")
        self.assertEqual(spec["simple"]["stroke"], "#ff0000")
        self.assertEqual(spec["simple"]["weight"], 3)

    def test_a_marker_symbol_maps_to_a_point_radius(self):
        renderer = {"type": "simple", "symbol": {"type": "esriSMS", "color": [0, 0, 255, 255], "size": 8}}
        spec = esri_renderer_to_spec(renderer)
        self.assertEqual(spec["geometry"], "point")
        self.assertEqual(spec["simple"]["radius"], 4)

    def test_an_unknown_renderer_returns_none(self):
        self.assertIsNone(esri_renderer_to_spec({"type": "pieChart"}))
        self.assertIsNone(esri_renderer_to_spec({}))
        self.assertIsNone(esri_renderer_to_spec(None))


class DatasetStyleSpecTest(unittest.TestCase):
    def _record(self, details, data_type="vector"):
        return {"id": 1577, "dataType": data_type, "details": details}

    def test_reads_a_renderer_from_a_string_details(self):
        details = json.dumps({"display": {"esri": {"renderer": {
            "type": "uniqueValue", "field1": "landuse",
            "uniqueValueInfos": [{"value": "1", "label": "one", "symbol": _polygon_symbol((1, 2, 3))}],
        }}}})
        spec = dataset_style_spec(self._record(details))
        self.assertEqual(spec["field"], "landuse")

    def test_legacy_esri_display_is_honoured(self):
        details = {"esri": {"renderer": {"type": "simple", "symbol": _polygon_symbol((9, 9, 9))}}}
        spec = dataset_style_spec(self._record(details))
        self.assertEqual(spec["type"], "simple")

    def test_unique_value_labels_fall_back_to_the_field_domain(self):
        details = {
            "fields": [
                {"name": "Landuse_Group",
                 "domain": {"type": "codedValues",
                            "items": [{"code": 1, "value": "مسکونی"}]}}
            ],
            "display": {"esri": {"renderer": {
                "type": "uniqueValue", "field1": "Landuse_Group",
                "uniqueValueInfos": [{"value": "1", "symbol": _polygon_symbol((1, 2, 3))}],
            }}},
        }
        spec = dataset_style_spec(self._record(details))
        self.assertEqual(spec["unique"][0]["label"], "مسکونی")
        self.assertEqual(spec["legend"]["entries"][0]["label"], "مسکونی")

    def test_a_raster_dataset_has_no_client_spec(self):
        details = {"display": {"displayType": "RGB", "RBand": 1, "GBand": 2, "BBand": 3}}
        self.assertIsNone(dataset_style_spec(self._record(details, data_type="raster")))

    def test_no_display_returns_none(self):
        self.assertIsNone(dataset_style_spec(self._record({})))
        self.assertIsNone(dataset_style_spec({}))


class DerivedSymbologyTest(unittest.TestCase):
    def test_field_values_are_read_in_feature_order(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {"properties": {"a": 1, "b": "x"}},
                {"properties": {"a": 2}},
                {"properties": {"b": "y"}},
            ],
        }
        self.assertEqual(field_values_from_geojson(geojson, "a"), [1, 2])
        self.assertEqual(field_values_from_geojson(geojson, "b"), ["x", "y"])

    def test_categorical_spec_assigns_one_distinct_colour_per_value(self):
        spec = categorical_spec("Ownership", [1, 2, 1, None, 3])
        self.assertEqual(spec["type"], "uniqueValue")
        self.assertEqual(spec["field"], "Ownership")
        self.assertEqual(len(spec["unique"]), 4)  # 1, 2, None, 3 (deduped)
        fills = [e["style"]["fill"] for e in spec["unique"]]
        self.assertEqual(len(set(fills)), 4)
        self.assertEqual(len(spec["legend"]["entries"]), 4)

    def test_categorical_spec_labels_codes_with_the_domain(self):
        # A coded-value field must show the human value in the legend, not the code.
        spec = categorical_spec(
            "Ownership",
            [1, 2, 1],
            domain={"1": "اوقاف", "2": "مستثنیات"},
            title="مالکیت",
        )
        self.assertEqual([e["label"] for e in spec["unique"]], ["اوقاف", "مستثنیات"])
        self.assertEqual(spec["legend"]["title"], "مالکیت")
        self.assertEqual(spec["legend"]["entries"][0]["label"], "اوقاف")

    def test_breaks_spec_uses_the_alias_as_the_title(self):
        spec = breaks_spec("DB_SHAPE_Area", quantile_breaks(list(range(1, 11)), 5),
                           title="مساحت")
        self.assertEqual(spec["legend"]["title"], "مساحت")

    def test_field_meta_from_details_reads_a_coded_value_domain(self):
        details = {
            "fields": [
                {"name": "Ownership", "alias": "مالکیت",
                 "domain": {"type": "codedValues",
                            "items": [{"code": 1, "value": "اوقاف"},
                                      {"code": 2, "value": "مستثنیات"}]}},
                {"name": "DB_SHAPE_Area"},
                {"name": "NoMeta"},
            ]
        }
        meta = field_meta_from_details(details)
        self.assertEqual(meta["Ownership"]["alias"], "مالکیت")
        self.assertEqual(meta["Ownership"]["domain"], {"1": "اوقاف", "2": "مستثنیات"})
        self.assertNotIn("DB_SHAPE_Area", meta)  # no alias and no domain

    def test_quantile_breaks_span_the_values_and_are_contiguous(self):
        breaks = quantile_breaks([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5)
        self.assertEqual(len(breaks), 5)
        self.assertEqual(breaks[0][0], 1.0)
        self.assertEqual(breaks[-1][1], 10.0)
        for (_, high), (low, _) in zip(breaks, breaks[1:]):
            self.assertEqual(high, low)

    def test_quantile_breaks_ignore_non_numeric_values(self):
        self.assertEqual(quantile_breaks([], 5), [])
        self.assertEqual(quantile_breaks(["a", None], 5), [])

    def test_breaks_spec_uses_a_sequential_ramp(self):
        breaks = quantile_breaks(list(range(1, 11)), 5)
        spec = breaks_spec("DB_SHAPE_Area", breaks)
        self.assertEqual(spec["type"], "classBreaks")
        self.assertEqual(len(spec["breaks"]), 5)
        fills = [b["style"]["fill"] for b in spec["breaks"]]
        self.assertEqual(len(set(fills)), 5)
        self.assertEqual(len(spec["legend"]["entries"]), 5)


if __name__ == "__main__":
    unittest.main()
