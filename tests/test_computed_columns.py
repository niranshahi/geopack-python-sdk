"""Computed-column authoring: catalog + text-only preview (slice 013).

The preview is an AUTHORING answer, not a validation gate:

* a rejected expression arrives in a ``200`` with ``ok: false`` plus a coded
  ``code``/``message`` — the SDK returns it and does not raise;
* nothing is compiled client-side and nothing is executed server-side;
* the authoritative validation re-runs on dataset save against the stored
  schema, so a green preview is not a guarantee.
"""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.computed_columns import ComputedColumnManager
from geopack_sdk.models import ComputedColumnPreview

CATALOG = {
    "dialect": "postgres",
    "templates": [{"id": "concat", "sql": "${a} || ${b}"}],
    "measures": [{"id": "area", "sql": "ST_Area(${shape})"}],
    "windows": [{"id": "row_number"}],
}

COMPILED = {
    "ok": True,
    "dialect": "postgres",
    "expression": '"owner"::text || \' / \' || "parcel_id"::text',
    "resultType": "text",
    "isWindow": False,
    "code": None,
    "message": None,
    "templates": CATALOG["templates"],
    "measures": CATALOG["measures"],
}

REJECTED = {
    "ok": False,
    "dialect": "postgres",
    "expression": None,
    "resultType": None,
    "isWindow": False,
    "code": "EXPR_UNKNOWN_IDENTIFIER",
    "message": 'Unknown field "nope".',
    "templates": CATALOG["templates"],
    "measures": CATALOG["measures"],
}


class ComputedColumnsTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.manager = ComputedColumnManager(self.client)

    def test_catalog_sends_the_query_param(self):
        self.client.get.return_value = CATALOG

        result = self.manager.catalog("postgres")

        self.assertEqual(
            self.client.get.call_args.args[0], "/datasets/computed-column/catalog"
        )
        self.assertEqual(
            self.client.get.call_args.kwargs["params"], {"dataStoreType": "postgres"}
        )
        self.assertEqual(result["dialect"], "postgres")

    def test_catalog_on_an_unsupported_store_does_not_raise(self):
        self.client.get.return_value = {
            "dialect": None,
            "templates": [],
            "measures": [],
            "windows": [],
        }

        result = self.manager.catalog("filesystem")

        self.assertIsNone(result["dialect"])
        self.assertEqual(result["templates"], [])

    def test_catalog_requires_a_store_type(self):
        for bad in ("", "  ", None):
            with self.assertRaises(ValueError):
                self.manager.catalog(bad)
        self.client.get.assert_not_called()

    def test_preview_compiles_a_free_expression(self):
        self.client.post.return_value = COMPILED

        result = self.manager.preview(
            data_store_type="postgres",
            fields=[{"name": "owner"}, {"name": "parcel_id"}],
            shape_field="shape",
            oid_field="parcel_id",
            expression='${owner} || \' / \' || ${parcel_id}',
        )

        self.assertIsInstance(result, ComputedColumnPreview)
        self.assertTrue(result.ok)
        self.assertEqual(result.compiled_sql, COMPILED["expression"])
        self.assertIsNone(result.error)
        self.assertEqual(
            self.client.post.call_args.args[0], "/datasets/computed-column/preview"
        )
        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(body["dataStoreType"], "postgres")
        self.assertEqual(body["shapeField"], "shape")
        self.assertEqual(body["oidField"], "parcel_id")
        self.assertIn("expression", body)
        self.assertNotIn("calc", body)

    def test_preview_compiles_a_calc_descriptor(self):
        self.client.post.return_value = {
            **COMPILED,
            "isWindow": True,
        }
        calc = {"kind": "window", "fn": "row_number", "orderBy": [{"field": "parcel_id"}]}

        result = self.manager.preview(
            data_store_type="postgres",
            fields=[{"name": "parcel_id"}],
            calc=calc,
        )

        self.assertTrue(result.isWindow)
        body = self.client.post.call_args.kwargs["json"]
        self.assertEqual(body["calc"], calc)
        self.assertNotIn("expression", body)
        # Optional schema keys are omitted, never sent as null.
        self.assertNotIn("shapeField", body)
        self.assertNotIn("oidField", body)

    def test_rejected_expression_is_an_answer_not_an_exception(self):
        self.client.post.return_value = REJECTED

        result = self.manager.preview(data_store_type="postgres", expression="nope")

        self.assertFalse(result.ok)
        self.assertIsNone(result.compiled_sql)
        self.assertEqual(result.error["code"], "EXPR_UNKNOWN_IDENTIFIER")
        self.assertIn("nope", result.error["message"])
        # The catalog rides along so the editor can re-render its pickers.
        self.assertEqual(result.catalog["dialect"], "postgres")
        self.assertEqual(result.catalog["templates"], CATALOG["templates"])

    def test_preview_needs_a_body(self):
        with self.assertRaises(ValueError):
            self.manager.preview(data_store_type="postgres")
        with self.assertRaises(ValueError):
            self.manager.preview(data_store_type="postgres", expression="   ")
        with self.assertRaises(ValueError):
            self.manager.preview(data_store_type="postgres", calc={})
        self.client.post.assert_not_called()

    def test_preview_needs_a_store_type(self):
        with self.assertRaises(ValueError):
            self.manager.preview(data_store_type="", expression="1 + 1")
        self.client.post.assert_not_called()

    def test_raw_body_is_kept_for_forward_compatibility(self):
        self.client.post.return_value = {**COMPILED, "futureKey": "kept"}

        result = self.manager.preview(data_store_type="postgres", expression="1 + 1")

        self.assertEqual(result.raw["futureKey"], "kept")


if __name__ == "__main__":
    unittest.main()
