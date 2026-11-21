"""SDK-001 / slice 032 F1 — the dataset response models must not reject a page.

A live Claude Desktop round (2026-11-21) showed `list_datasets` failing outright
on rows with `dataType="service"` and `dataStoreId=null`. These pins hold the
model open: advisory enumerations, nullable identity fields, and per-item soft
validation that degrades a single bad record instead of the whole page.
"""

import unittest

from geopack_sdk.models import Dataset, DatasetsApiResponse


SERVICE_ROW = {
    "id": 2973,
    "name": "external service layer",
    "dataType": "service",
    "ownerUserId": None,
    "workgroupId": None,
    "dataStoreId": None,
    "createdAt": None,
    "updatedAt": None,
}

VECTOR_ROW = {
    "id": 7,
    "name": "parcels",
    "dataType": "vector",
    "ownerUserId": 1,
    "workgroupId": 1,
    "dataStoreId": 3,
    "createdAt": "2024-01-01T00:00:00",
    "updatedAt": "2024-01-01T00:00:00",
}


class TestDatasetLeniency(unittest.TestCase):
    def test_service_row_parses(self):
        ds = Dataset(**SERVICE_ROW)
        self.assertEqual(ds.dataType, "service")
        self.assertIsNone(ds.dataStoreId)

    def test_page_with_a_service_row_survives(self):
        response = DatasetsApiResponse(
            **{
                "datasets": [dict(VECTOR_ROW), dict(SERVICE_ROW)],
                "totalCount": 2,
                "totalPages": 1,
                "currentPage": 1,
                "itemsPerPage": 20,
            }
        )

        self.assertEqual(len(response.datasets), 2)
        self.assertEqual(response.datasets[1].dataType, "service")
        self.assertFalse(getattr(response.datasets[1], "validationDegraded", False))

    def test_counters_default_when_absent(self):
        response = DatasetsApiResponse(**{"datasets": []})
        self.assertEqual(response.totalCount, 0)
        self.assertEqual(response.currentPage, 1)

    def test_one_malformed_item_is_degraded_not_fatal(self):
        response = DatasetsApiResponse(
            **{
                "datasets": [
                    dict(VECTOR_ROW),
                    {"id": 999, "name": "weird", "createdAt": {"not": "a date"}},
                ],
                "totalCount": 2,
            }
        )

        self.assertEqual(len(response.datasets), 2)
        degraded = response.datasets[1]
        self.assertTrue(getattr(degraded, "validationDegraded", False))
        dumped = degraded.model_dump(mode="json")
        self.assertTrue(dumped["validationErrors"])
        self.assertEqual(dumped["rawRecord"]["createdAt"], {"not": "a date"})

    def test_missing_identity_still_degrades_to_a_record(self):
        response = DatasetsApiResponse(**{"datasets": [{"name": "no id"}]})
        row = response.datasets[0]
        self.assertTrue(getattr(row, "validationDegraded", False))
        self.assertEqual(row.id, -1)


if __name__ == "__main__":
    unittest.main()
