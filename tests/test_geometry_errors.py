"""Slice 033 Lane C — geometry error contract (codes, refusals, rendering)."""

from __future__ import annotations

import unittest

from geopack_sdk_mcp.errors import tool_error_result
from geopack_sdk_mcp.geometry import GeometryOpError
from geopack_sdk_mcp.geometry.errors import engine_failed
from geopack_sdk_mcp.geometry.select import set_engine_for_tests
from geopack_sdk_mcp.tool_handlers.geometry import geometry_op

SQUARE_A = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
}
FAR = {
    "type": "Polygon",
    "coordinates": [[[10, 10], [10.1, 10], [10.1, 10.1], [10, 10.1], [10, 10]]],
}


class _NoEnvelopeEngine:
    id = "stub"
    capabilities = frozenset({"buffer"})

    def supports(self, op):
        return op in self.capabilities


class GeometryErrorTest(unittest.TestCase):
    def tearDown(self):
        set_engine_for_tests(None)

    def test_unknown_units_are_rejected_not_defaulted(self):
        with self.assertRaises(GeometryOpError) as ctx:
            geometry_op(
                "buffer", geojson={"type": "Point", "coordinates": [51.4, 35.7]},
                distance=100, units="furlongs", wkid=32639,
            )
        self.assertEqual(ctx.exception.code, "INVALID_ARGS")
        self.assertEqual(ctx.exception.invalid_args, ["units"])

    def test_buffer_without_distance_is_refused(self):
        with self.assertRaises(GeometryOpError) as ctx:
            geometry_op("buffer", geojson=SQUARE_A)
        self.assertEqual(ctx.exception.code, "INVALID_ARGS")
        self.assertEqual(ctx.exception.invalid_args, ["distance"])

    def test_empty_output_is_an_error_not_an_empty_geometry(self):
        with self.assertRaises(GeometryOpError) as ctx:
            geometry_op("overlay", geojson=SQUARE_A, b=FAR, overlay_op="intersection", wkid=32631)
        self.assertEqual(ctx.exception.code, "GEOMETRY_EMPTY_RESULT")

    def test_an_unsupported_op_names_the_legal_set(self):
        set_engine_for_tests(_NoEnvelopeEngine())
        with self.assertRaises(GeometryOpError) as ctx:
            geometry_op("envelope", geojson=SQUARE_A)
        self.assertEqual(ctx.exception.code, "GEOMETRY_UNSUPPORTED_OP")
        self.assertEqual(ctx.exception.extra["engine"], "stub")

    def test_engine_failure_helper_is_coded(self):
        exc = engine_failed("overlay", "topology exploded")
        self.assertEqual(exc.code, "GEOMETRY_ENGINE_FAILED")
        self.assertIn("topology exploded", exc.message)

    def test_non_finite_distance_is_refused(self):
        with self.assertRaises(GeometryOpError) as ctx:
            geometry_op(
                "buffer", geojson={"type": "Point", "coordinates": [51.4, 35.7]},
                distance=float("nan"), wkid=32639,
            )
        self.assertEqual(ctx.exception.code, "INVALID_ARGS")

    def test_create_without_coordinates_is_refused(self):
        with self.assertRaises(GeometryOpError) as ctx:
            geometry_op("create", geometry_type="Point")
        self.assertEqual(ctx.exception.invalid_args, ["coordinates"])


class ErrorRenderingTest(unittest.TestCase):
    def test_a_geometry_error_renders_code_hint_and_invalid_args(self):
        result = tool_error_result(
            GeometryOpError(
                "INVALID_ARGS", "bad units", key="units", hint="Use m|km|ft|mi."
            )
        )
        payload = result.structuredContent

        self.assertTrue(result.isError)
        self.assertEqual(payload["code"], "INVALID_ARGS")
        self.assertEqual(payload["invalidArgs"], ["units"])
        self.assertEqual(payload["hint"], "Use m|km|ft|mi.")

    def test_extra_fields_flow_into_the_error_payload(self):
        result = tool_error_result(
            GeometryOpError("GEOMETRY_UNSUPPORTED_OP", "nope", engine="stub", legalOps=["buffer"])
        )
        payload = result.structuredContent

        self.assertEqual(payload["engine"], "stub")
        self.assertEqual(payload["legalOps"], ["buffer"])


if __name__ == "__main__":
    unittest.main()