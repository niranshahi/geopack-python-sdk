"""Dataset saved-symbology disclosure (slice 033 / owner report 2026-11-23)."""

from __future__ import annotations

import json
import unittest

from geopack_sdk_mcp.sanitize.dataset_symbology import (
    resolve_esri_display,
    resolve_raster_display,
    styled_publications,
    summarise_symbology,
)


class VectorSymbologyTest(unittest.TestCase):
    def test_a_saved_esri_renderer_is_disclosed(self):
        dataset = {
            "dataType": "vector",
            "details": {
                "display": {
                    "esri": {
                        "renderer": {
                            "type": "uniqueValue",
                            "field1": "LANDUSE",
                            "uniqueValueGroups": [
                                {"classes": [{"value": "a"}, {"value": "b"}, {"value": "c"}]}
                            ],
                        }
                    }
                }
            },
        }

        summary = summarise_symbology(dataset)

        self.assertTrue(summary["hasSavedStyle"])
        self.assertEqual(summary["kind"], "vector")
        self.assertEqual(summary["rendererFamily"], "esri")
        self.assertEqual(summary["rendererType"], "uniqueValue")
        self.assertEqual(summary["rendererLabel"], "unique-value")
        self.assertEqual(summary["fields"], ["LANDUSE"])
        self.assertEqual(summary["classCount"], 3)

    def test_a_legacy_flat_esri_display_is_resolved(self):
        details = {"esri": {"renderer": {"type": "simple"}}}
        summary = summarise_symbology({"dataType": "vector", "details": details})
        self.assertTrue(summary["hasSavedStyle"])
        self.assertEqual(summary["rendererType"], "simple")

    def test_details_as_a_json_string_is_parsed(self):
        dataset = {
            "dataType": "vector",
            "details": json.dumps(
                {"display": {"esri": {"renderer": {"type": "classBreaks", "classBreakInfos": [1, 2]}}}}
            ),
        }
        summary = summarise_symbology(dataset)
        self.assertEqual(summary["rendererType"], "classBreaks")
        self.assertEqual(summary["classCount"], 2)

    def test_a_labeling_only_display_still_counts(self):
        details = {"display": {"esri": {"labelsVisible": True, "labelingInfo": [{}]}}}
        summary = summarise_symbology({"dataType": "vector", "details": details})
        self.assertTrue(summary["hasSavedStyle"])
        self.assertEqual(summary["labelingCount"], 1)


class RasterSymbologyTest(unittest.TestCase):
    def test_an_rgb_display_is_disclosed_as_raster(self):
        details = {"display": {"displayType": "RGB", "RBand": 1, "GBand": 2, "BBand": 3}}
        summary = summarise_symbology({"dataType": "raster", "details": details})
        self.assertEqual(summary["kind"], "raster")
        self.assertEqual(summary["rasterDisplayType"], "RGB")
        self.assertEqual(summary["bands"], {"RBand": 1, "GBand": 2, "BBand": 3})

    def test_a_colormap_display_is_disclosed(self):
        details = {"display": {"displayType": "colorMap", "band": 1, "colorMap": "pseudocolor"}}
        summary = summarise_symbology({"dataType": "raster", "details": details})
        self.assertEqual(summary["rasterDisplayType"], "colorMap")
        self.assertEqual(summary["band"], 1)
        self.assertEqual(summary["colorMap"], "pseudocolor")

    def test_an_esri_raster_renderer_is_classified_raster(self):
        details = {"display": {"esri": {"renderer": {"type": "rasterStretch"}}}}
        summary = summarise_symbology({"dataType": "raster", "details": details})
        self.assertEqual(summary["kind"], "raster")
        self.assertEqual(summary["rendererType"], "rasterStretch")


class NoSymbologyTest(unittest.TestCase):
    def test_a_plain_dataset_reports_none(self):
        summary = summarise_symbology({"dataType": "vector", "details": {}})
        self.assertEqual(summary, {"hasSavedStyle": False, "kind": "none"})

    def test_the_raster_placeholder_resolves_to_none(self):
        # The adapter writes `display: { esri: { display: null } }` — no style.
        details = {"display": {"esri": {"display": None}}}
        self.assertIsNone(resolve_esri_display(details))
        self.assertIsNone(resolve_raster_display(details))
        self.assertFalse(summarise_symbology({"dataType": "raster", "details": details})["hasSavedStyle"])


class _Publications:
    def __init__(self, rows=None, error=False):
        self._rows = rows or []
        self._error = error

    def list_for_dataset(self, dataset_id):
        if self._error:
            raise RuntimeError("boom")
        return self._rows


class _Client:
    def __init__(self, publications):
        self.publications = publications


class StyledPublicationsTest(unittest.TestCase):
    def test_a_canonical_revision_marks_a_publication_styled(self):
        client = _Client(_Publications([{"raw": {"id": 204, "protocol": "wms", "canonicalStyleRevision": "abc"}}]))
        rows = styled_publications(client, 1577)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["hasStyle"])
        self.assertEqual(rows[0]["publicationId"], 204)

    def test_a_style_override_marks_a_publication_styled(self):
        client = _Client(_Publications([{"raw": {"id": 7, "configuration": {"styleOverride": "<sld/>"}}}]))
        self.assertTrue(styled_publications(client, 1)[0]["hasStyle"])

    def test_an_unstyled_publication_is_flagged_false(self):
        client = _Client(_Publications([{"raw": {"id": 7, "protocol": "wms"}}]))
        self.assertFalse(styled_publications(client, 1)[0]["hasStyle"])

    def test_a_probe_failure_is_an_empty_list_never_an_error(self):
        self.assertEqual(styled_publications(_Client(_Publications(error=True)), 1), [])


if __name__ == "__main__":
    unittest.main()
