"""Coded 4xx -> typed exception mapping (slice 016 §1.2).

Callers must be able to branch on the class and its named fields. The bodies
below are the shapes the real validators answer with; message text is never
inspected, only ``code``.
"""

import unittest

from geopack_sdk import (
    AggregationInvalidArgs,
    AggregationUnsupported,
    DatasetReadOnly,
    EditConflict,
    EditDocumentVersionError,
    FieldPolicyError,
    GeopackAPIError,
    GeopackAuthError,
    PagedUnsupported,
    PublicationStateConflict,
    QueryValidationError,
    QuotaExceeded,
    RelationshipCatalogUnavailable,
)


def _error(status, body):
    return GeopackAPIError.from_http_status(
        status, reason="Error", text="", json_loader=lambda: body
    )


class CodedErrorMappingTest(unittest.TestCase):
    def test_paged_unsupported_reads_data_store_type(self):
        error = _error(
            400,
            {
                "code": "PAGED_UNSUPPORTED",
                "message": "Store cannot page this query",
                "dataStoreType": "mssql",
            },
        )

        self.assertIsInstance(error, PagedUnsupported)
        self.assertIsInstance(error, GeopackAPIError)
        self.assertEqual(error.data_store_type, "mssql")
        self.assertEqual(error.code, "PAGED_UNSUPPORTED")

    def test_aggregation_unsupported(self):
        error = _error(
            400, {"code": "AGGREGATION_UNSUPPORTED", "data_store_type": "filesystem"}
        )

        self.assertIsInstance(error, AggregationUnsupported)
        self.assertEqual(error.data_store_type, "filesystem")

    def test_aggregation_invalid_args_names_the_key(self):
        error = _error(
            400, {"code": "AGGREGATION_INVALID_ARGS", "key": "aggregations[0].kind"}
        )

        self.assertIsInstance(error, AggregationInvalidArgs)
        self.assertEqual(error.key, "aggregations[0].kind")

    def test_other_query_paged_codes_stay_validation(self):
        error = _error(400, {"code": "QUERY_PAGED_INVALID_LIMIT", "message": "bad limit"})

        self.assertIsInstance(error, QueryValidationError)
        self.assertEqual(error.message, "bad limit")

    def test_field_policy_codes(self):
        for code in ("FIELD_POLICY_INVALID", "FIELD_POLICY_PROTECTED_FIELD"):
            error = _error(403 if code.endswith("PROTECTED_FIELD") else 400, {"code": code})
            if code.endswith("PROTECTED_FIELD"):
                # 403 is auth-rated and must stay an auth error.
                self.assertIsInstance(error, GeopackAuthError)
            else:
                self.assertIsInstance(error, FieldPolicyError)
                self.assertEqual(error.code, code)

    def test_quota_exceeded_carries_dimension_limit_and_usage(self):
        error = _error(
            429,
            {
                "code": "QUOTA_EXCEEDED",
                "dimension": "datasets",
                "limit": 50,
                "used": 50,
            },
        )

        self.assertIsInstance(error, QuotaExceeded)
        self.assertEqual(error.dimension, "datasets")
        self.assertEqual(error.limit, 50)
        self.assertEqual(error.used, 50)

    def test_423_is_dataset_read_only(self):
        error = _error(423, {"message": "Dataset is archived"})

        self.assertIsInstance(error, DatasetReadOnly)
        self.assertEqual(error.status_code, 423)

    def test_409_edit_conflict_carries_conflicts(self):
        error = _error(
            409,
            {"code": "EDIT_CONFLICT", "conflicts": [{"featureId": 7, "reason": "stale"}]},
        )

        self.assertIsInstance(error, EditConflict)
        self.assertEqual(error.conflicts[0]["featureId"], 7)

    def test_409_publication_state_conflict(self):
        error = _error(409, {"code": "PUBLICATION_STATE_INVALID", "state": "draft"})

        self.assertIsInstance(error, PublicationStateConflict)
        self.assertEqual(error.state, "draft")

    def test_409_relationship_catalog_unavailable(self):
        error = _error(409, {"code": "RELATIONSHIP_CATALOG_STALE"})

        self.assertIsInstance(error, RelationshipCatalogUnavailable)

    def test_409_without_a_known_code_keeps_the_legacy_class(self):
        error = _error(409, {"message": "Conflict"})

        self.assertIs(type(error), GeopackAPIError)
        self.assertEqual(error.status_code, 409)

    def test_unknown_codes_keep_the_legacy_class(self):
        for status in (400, 422, 500):
            error = _error(status, {"code": "SOMETHING_NEW", "message": "m"})
            self.assertIs(type(error), GeopackAPIError)
            self.assertEqual(error.status_code, status)

    def test_code_is_read_from_nested_error_and_errors_list(self):
        nested = _error(400, {"error": {"code": "PAGED_UNSUPPORTED"}})
        listed = _error(400, {"errors": [{"code": "AGGREGATION_UNSUPPORTED"}]})

        self.assertIsInstance(nested, PagedUnsupported)
        self.assertIsInstance(listed, AggregationUnsupported)

    def test_401_with_a_code_stays_an_auth_error(self):
        error = _error(401, {"code": "PAGED_UNSUPPORTED"})

        self.assertIsInstance(error, GeopackAuthError)
        self.assertNotIsInstance(error, PagedUnsupported)

    def test_edit_document_version_error_is_client_side(self):
        error = EditDocumentVersionError("unsupported edit document", version="2")

        self.assertEqual(error.version, "2")
        self.assertEqual(error.details["version"], "2")


if __name__ == "__main__":
    unittest.main()
