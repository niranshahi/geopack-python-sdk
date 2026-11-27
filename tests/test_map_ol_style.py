"""`display` → OpenLayers WebGL style translation for the COG lane."""

from __future__ import annotations

import unittest

from geopack_sdk_mcp.maps.ol_style import build_cog_style


def _bands(*entries):
    return [
        {"band": number, "type": data_type, "minimum": minimum, "maximum": maximum}
        for number, data_type, minimum, maximum in entries
    ]


class ColorMapStyleTest(unittest.TestCase):
    def test_custom_stops_become_an_ascending_interpolate(self):
        display = {
            "displayType": "colorMap",
            "band": 1,
            "colorMap": "custom",
            "minimum": 0,
            "maximum": 100,
            "customColorMap": [
                {"value": 100, "r": 0, "g": 0, "b": 255, "a": 255},
                {"value": 50, "r": 0, "g": 255, "b": 0, "a": 255},
                {"value": 0, "r": 255, "g": 0, "b": 0, "a": 255},
            ],
        }
        style, reason = build_cog_style(display, _bands((1, "Byte", 0, 100)))

        self.assertIsNone(reason)
        self.assertEqual(
            style["color"],
            [
                "interpolate", ["linear"], ["band", 1],
                0, [255, 0, 0, 1.0],
                50, [0, 255, 0, 1.0],
                100, [0, 0, 255, 1.0],
            ],
        )

    def test_percent_stops_resolve_against_min_max(self):
        display = {
            "displayType": "colorMap",
            "band": 1,
            "colorMap": "custom",
            "minimum": 6.995,
            "maximum": 14096.542,
            "customColorMap": [
                {"value": "100%", "color": [21, 99, 33, 255]},
                {"value": "0%", "color": [178, 24, 43, 255]},
            ],
        }
        style, reason = build_cog_style(display, _bands((1, "Float32", 6.995, 14096.542)))

        self.assertIsNone(reason)
        color = style["color"]
        self.assertAlmostEqual(color[3], 6.995, places=3)
        self.assertAlmostEqual(color[5], 14096.542, places=3)
        self.assertEqual(color[4], [178, 24, 43, 1.0])
        self.assertEqual(color[6], [21, 99, 33, 1.0])

    def test_named_ramp_mirrors_the_portal_preset(self):
        display = {
            "displayType": "colorMap", "band": 1, "colorMap": "pseudocolor",
            "minimum": 0, "maximum": 100,
        }
        style, reason = build_cog_style(display, _bands((1, "Byte", 0, 100)))

        self.assertIsNone(reason)
        self.assertEqual(
            style["color"],
            [
                "interpolate", ["linear"], ["band", 1],
                0, [0, 0, 0, 1.0],
                50, [0, 255, 0, 1.0],
                100, [255, 0, 0, 1.0],
            ],
        )

    def test_paired_boundary_stops_stay_strictly_increasing(self):
        # The owner's discrete-class recipe: 24.99% and 25% must remain two
        # distinct stops (OL's interpolate requires increasing values).
        display = {
            "displayType": "colorMap", "band": 1, "colorMap": "custom",
            "minimum": 0, "maximum": 100,
            "customColorMap": [
                {"value": "25%", "r": 0, "g": 255, "b": 0, "a": 255},
                {"value": "24.99%", "r": 255, "g": 0, "b": 0, "a": 255},
            ],
        }
        style, reason = build_cog_style(display, _bands((1, "Byte", 0, 100)))

        self.assertIsNone(reason)
        color = style["color"]
        self.assertEqual(color[3], 24.99)
        self.assertGreater(color[5], color[3])
        self.assertEqual(color[4], [255, 0, 0, 1.0])
        self.assertEqual(color[6], [0, 255, 0, 1.0])

    def test_alpha_is_0_to_1_not_0_to_255(self):
        # OpenLayers colors use RGB 0..255 but alpha 0..1; a 255 alpha is
        # multiplied into RGB by the fragment shader and blows colours out.
        display = {
            "displayType": "colorMap", "band": 1, "colorMap": "custom",
            "minimum": 0, "maximum": 100,
            "customColorMap": [
                {"value": 0, "r": 0, "g": 14, "b": 174, "a": 255}
            ],
        }
        style, reason = build_cog_style(display, _bands((1, "Byte", 0, 100)))

        self.assertIsNone(reason)
        self.assertEqual(style["color"], [0, 14, 174, 1.0])

    def test_nodata_is_transparent(self):
        # A declared no-data sentinel must not receive the first class colour.
        display = {
            "displayType": "colorMap", "band": 1, "colorMap": "custom",
            "minimum": 0, "maximum": 100,
            "customColorMap": [
                {"value": 0, "r": 255, "g": 0, "b": 0, "a": 255},
                {"value": 100, "r": 0, "g": 0, "b": 255, "a": 255},
            ],
        }
        bands = [{"band": 1, "type": "Byte", "minimum": 0, "maximum": 100,
                  "noDataValue": 0}]
        style, reason = build_cog_style(display, bands)

        self.assertIsNone(reason)
        color = style["color"]
        self.assertEqual(color[0], "case")
        self.assertEqual(color[1], ["==", ["band", 1], 0.0])
        self.assertEqual(color[2], [0, 0, 0, 0])
        self.assertEqual(color[3][0], "interpolate")

    def test_a_ramp_without_min_max_is_refused_with_a_reason(self):
        display = {
            "displayType": "colorMap", "band": 1, "colorMap": "custom",
            "customColorMap": [{"value": "50%", "r": 1, "g": 2, "b": 3, "a": 255}],
        }
        style, reason = build_cog_style(display, [])

        self.assertIsNone(style)
        self.assertIn("no usable colour stops", reason)

    def test_unknown_color_map_is_refused(self):
        display = {"displayType": "colorMap", "band": 1, "colorMap": "terrain"}
        style, reason = build_cog_style(display, _bands((1, "Byte", 0, 100)))

        self.assertIsNone(style)
        self.assertIn("not supported", reason)


class RgbStyleTest(unittest.TestCase):
    def test_rgb_builds_a_unit_stretch_array(self):
        display = {"displayType": "RGB", "RBand": 4, "GBand": 3, "BBand": 2}
        style, reason = build_cog_style(
            display, _bands((2, "Byte", 0, 255), (3, "Byte", 0, 255), (4, "Byte", 0, 255))
        )

        self.assertIsNone(reason)
        self.assertEqual(
            style["color"],
            [
                "array",
                ["/", ["band", 4], 255.0],
                ["/", ["band", 3], 255.0],
                ["/", ["band", 2], 255.0],
                1,
            ],
        )

    def test_rgb_stretches_a_16bit_band(self):
        display = {"displayType": "RGB", "RBand": 1, "GBand": 2, "BBand": 3}
        style, reason = build_cog_style(
            display,
            _bands((1, "UInt16", 0, 65535), (2, "UInt16", 0, 65535), (3, "UInt16", 0, 65535)),
        )

        self.assertIsNone(reason)
        self.assertEqual(style["color"][1], ["/", ["band", 1], 65535.0])

    def test_rgb_nodata_is_transparent_when_all_bands_share_it(self):
        display = {"displayType": "RGB", "RBand": 1, "GBand": 2, "BBand": 3}
        bands = [
            {"band": number, "type": "Byte", "minimum": 0, "maximum": 255,
             "noDataValue": 0}
            for number in (1, 2, 3)
        ]
        style, reason = build_cog_style(display, bands)

        self.assertIsNone(reason)
        self.assertEqual(style["color"][0], "case")
        self.assertEqual(style["color"][2], [0, 0, 0, 0])

    def test_rgb_without_band_range_is_refused(self):
        display = {"displayType": "RGB", "RBand": 1, "GBand": 2, "BBand": 3}
        style, reason = build_cog_style(display, [])

        self.assertIsNone(style)
        self.assertIn("min/max", reason)


if __name__ == "__main__":
    unittest.main()