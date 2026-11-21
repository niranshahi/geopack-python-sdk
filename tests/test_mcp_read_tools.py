"""Slice 020 — MCP read lanes: schema, aggregate, relationships, quota, lists.

Handler-level tests use REAL SDK models (the 2026-11-02 lesson: a mocked
``model_dump()`` hides contract drift) and a ``MagicMock`` client that returns
them. The registration test asserts the whole 29-tool surface and the policy
registry, so a name collision or a missing policy entry fails here. (Slice 031
grew the surface to 29; the seven names below are slice 020's.)
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from geopack_sdk.exceptions import (
    AggregationInvalidArgs,
    AggregationUnsupported,
    GeopackAuthError,
    QueryValidationError,
    RelationshipCatalogUnavailable,
)
from geopack_sdk.models import (
    AggregateResult,
    Dataset,
    GeneratedFile,
    GeneratedFileListResponse,
    QuotaSummary,
    QuotaSummaryLimit,
    RelatedRecordsResult,
    RelationshipDescriptor,
    WorkflowRun,
    WorkflowRunListResponse,
)
from geopack_sdk_mcp.sanitize.dataset_schema import (
    MAX_DOMAIN_VALUES,
    MAX_HINTS,
    build_dataset_schema,
    build_field_rows,
    build_relationship_rows,
)
from geopack_sdk_mcp.tool_handlers.datasets import (
    AGGREGATE_KINDS,
    aggregate_dataset,
    get_dataset_relationships,
    get_dataset_schema,
    get_related_records,
)
from geopack_sdk_mcp.tool_handlers.generated_files import list_generated_files
from geopack_sdk_mcp.tool_handlers.quotas import get_quota_summary
from geopack_sdk_mcp.tool_handlers.workflow_runs import list_workflow_runs
from geopack_sdk_mcp.tool_handlers.workflows import get_workflow_spec
from geopack_sdk_mcp.tools.policy import TOOL_POLICY

EXPECTED_TOOL_NAMES = {
    "geopack_sdk_list_datasets",
    "geopack_sdk_get_dataset",
    "geopack_sdk_get_dataset_schema",
    "geopack_sdk_query_dataset",
    "geopack_sdk_aggregate_dataset",
    "geopack_sdk_get_dataset_relationships",
    "geopack_sdk_get_related_records",
    "geopack_sdk_get_dataset_thumbnail",
    "geopack_sdk_upload_dataset",
    "geopack_sdk_export_dataset",
    "geopack_sdk_get_task",
    "geopack_sdk_wait_for_task",
    "geopack_sdk_get_quota_summary",
    "geopack_sdk_list_generated_files",
    "geopack_sdk_download_generated_file",
    "geopack_sdk_geocode_place",
    "geopack_sdk_get_mcp_safety_policy",
    "geopack_sdk_list_workflows",
    "geopack_sdk_get_workflow",
    "geopack_sdk_get_workflow_spec",
    "geopack_sdk_submit_workflow",
    "geopack_sdk_list_workflow_runs",
    "geopack_sdk_get_workflow_run",
    "geopack_sdk_download_workflow_artifact",
    "geopack_sdk_list_analysis_tools",
    "geopack_sdk_run_analysis",
    "geopack_sdk_get_analysis_result",
    "geopack_sdk_submit_edit_document",
    "geopack_sdk_cancel_task",
}

#: The seven tools slice 020 added (021 added two more, 031 one).
READ_LANES = {
    "geopack_sdk_get_dataset_schema",
    "geopack_sdk_aggregate_dataset",
    "geopack_sdk_get_dataset_relationships",
    "geopack_sdk_get_related_records",
    "geopack_sdk_get_quota_summary",
    "geopack_sdk_list_workflow_runs",
    "geopack_sdk_list_generated_files",
}

DATASET_DETAILS = {
    "oidField": "gid",
    "geometryType": "esriGeometryPolygon",
    "tableName": "parcels",
    "tilejson": {"tiles": ["https://example/{z}/{x}/{y}.pbf"], "tilestats": {"layers": []}},
    "display": {"esri": {"renderer": {"type": "simple"}}},
    "thumbnail": {"data": "AAAA"},
    "pgisMetadata": {"blob": True},
    "fields": [
        {
            "name": "gid",
            "type": "integer",
            "nullable": False,
            "isPrimaryKey": True,
        },
        {
            "name": "zone",
            "alias": "Zone",
            "type": "varchar",
            "nullable": True,
            "domainName": "ZoneDomain",
        },
        {
            "name": "area_ha",
            "type": "numeric",
            "nullable": True,
            "isExpression": True,
            "expression": "ST_Area(geom)/10000",
        },
    ],
    "domains": {
        "ZoneDomain": {
            "type": "codedValues",
            "items": [{"code": str(i), "value": f"Zone {i}"} for i in range(60)],
        },
        "RangeDomain": {"type": "range", "minValue": 0, "maxValue": 100},
    },
}


def _dataset(**overrides):
    payload = {
        "id": 7,
        "name": "parcels",
        "dataType": "vector",
        "ownerUserId": 1,
        "workgroupId": 1,
        "dataStoreId": 3,
        "createdAt": "2024-01-01T00:00:00",
        "updatedAt": "2024-01-01T00:00:00",
        "details": dict(DATASET_DETAILS),
    }
    payload.update(overrides)
    return Dataset(**payload)


def _descriptor(name="parcels_buildings", **raw_overrides):
    raw = {
        "relationshipUuid": "rel-1",
        "name": name,
        "aliasName": name,
        "relationshipKind": "foreignKey",
        "cardinality": "oneToMany",
        "destination": {"datasetId": 8, "datasetName": "buildings", "qualifiedName": "public.buildings"},
        "capabilities": {"canEdit": True, "readOnly": False},
    }
    raw.update(raw_overrides)
    return RelationshipDescriptor(**raw)


class SchemaSanitizerTest(unittest.TestCase):
    def test_domain_values_are_capped(self):
        rows = build_field_rows(DATASET_DETAILS["fields"], DATASET_DETAILS["domains"], include_domains=True)
        zone = next(row for row in rows if row["name"] == "zone")

        self.assertEqual(len(zone["values"]), MAX_DOMAIN_VALUES)
        self.assertTrue(zone["valuesTruncated"])
        self.assertEqual(zone["valuesTotal"], 60)
        self.assertEqual(zone["domainType"], "codedValues")
        self.assertEqual(zone["domainName"], "ZoneDomain")

    def test_domains_are_omitted_unless_requested(self):
        rows = build_field_rows(DATASET_DETAILS["fields"], DATASET_DETAILS["domains"], include_domains=False)
        zone = next(row for row in rows if row["name"] == "zone")

        self.assertNotIn("values", zone)
        self.assertNotIn("valuesTruncated", zone)

    def test_computed_flag_and_nullable(self):
        rows = build_field_rows(DATASET_DETAILS["fields"], DATASET_DETAILS["domains"])
        by_name = {row["name"]: row for row in rows}

        self.assertTrue(by_name["area_ha"]["isComputed"])
        self.assertFalse(by_name["gid"]["isComputed"])
        self.assertFalse(by_name["gid"]["nullable"])
        self.assertTrue(by_name["zone"]["nullable"])
        self.assertEqual(by_name["zone"]["alias"], "Zone")

    def test_range_domain_reports_bounds_not_values(self):
        rows = build_field_rows(
            [{"name": "score", "type": "integer", "domainName": "RangeDomain"}],
            DATASET_DETAILS["domains"],
            include_domains=True,
        )
        row = rows[0]

        self.assertEqual(row["domainType"], "range")
        self.assertEqual(row["minValue"], 0)
        self.assertEqual(row["maxValue"], 100)
        self.assertNotIn("values", row)

    def test_heavy_detail_keys_never_reach_the_payload(self):
        payload = build_dataset_schema({"id": 7, "name": "parcels", "dataType": "vector", "details": DATASET_DETAILS})

        serialized = str(payload)
        for dropped in ("tilejson", "tilestats", "display", "pgisMetadata", "thumbnail", "AAAA"):
            self.assertNotIn(dropped, serialized)

    def test_hints_are_plain_sentences_and_capped(self):
        payload = build_dataset_schema(
            {"id": 7, "name": "parcels", "dataType": "vector", "details": DATASET_DETAILS},
            include_domains=True,
            access_unavailable=True,
            catalog_unavailable=True,
        )

        self.assertLessEqual(len(payload["hints"]), MAX_HINTS)
        self.assertTrue(payload["hints"])
        for hint in payload["hints"]:
            self.assertIsInstance(hint, str)
            self.assertGreater(len(hint), 20)

    def test_relationship_rows_keep_target_and_read_only(self):
        esri = RelationshipDescriptor(
            relationshipName="buildings_owner",
            readOnly=True,
            raw={
                "name": "buildings_owner",
                "cardinality": "manyToMany",
                "relationshipKind": "junction",
                "isAttributed": True,
                "relatedDatasetId": 12,
                "relatedClassName": "owner",
            },
        )

        rows = build_relationship_rows([_descriptor(), esri])

        self.assertEqual(rows[0]["name"], "parcels_buildings")
        self.assertEqual(rows[0]["targetDatasetId"], 8)
        self.assertEqual(rows[0]["targetDatasetName"], "buildings")
        self.assertEqual(rows[0]["cardinality"], "oneToMany")
        self.assertFalse(rows[0]["readOnly"])

        self.assertEqual(rows[1]["name"], "buildings_owner")
        self.assertEqual(rows[1]["targetDatasetId"], 12)
        self.assertEqual(rows[1]["targetDatasetName"], "owner")
        self.assertTrue(rows[1]["readOnly"])
        self.assertTrue(rows[1]["isAttributed"])


class DatasetSchemaHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.datasets.get.return_value = _dataset()
        self.client.datasets.get_access_context.return_value = {
            "rowScope": {"kind": "all"},
            "fieldAccess": {"visible": ["gid", "zone"]},
        }
        self.client.datasets.get_relationships.return_value = [_descriptor()]

    def test_schema_reads_unslimmed_fields_with_domains(self):
        payload = get_dataset_schema(self.client, 7, include_domains=True)

        self.assertEqual(payload["datasetId"], 7)
        self.assertEqual(payload["oidField"], "gid")
        self.assertEqual(payload["geometryType"], "esriGeometryPolygon")
        zone = next(row for row in payload["fields"] if row["name"] == "zone")
        self.assertEqual(len(zone["values"]), MAX_DOMAIN_VALUES)
        self.assertEqual(payload["fieldAccess"]["rowScope"], {"kind": "all"})
        self.assertEqual(payload["relationships"][0]["name"], "parcels_buildings")

    def test_access_context_failure_is_best_effort(self):
        self.client.datasets.get_access_context.side_effect = GeopackAuthError(403, "denied")

        payload = get_dataset_schema(self.client, 7)

        self.assertIsNone(payload["fieldAccess"])
        self.assertTrue(any("access" in hint.lower() for hint in payload["hints"]))

    def test_catalog_unavailable_is_a_hint_not_an_error(self):
        self.client.datasets.get_relationships.side_effect = RelationshipCatalogUnavailable(
            409, "catalog unavailable", {"code": "RELATIONSHIP_CATALOG_UNAVAILABLE"}
        )

        payload = get_dataset_schema(self.client, 7)

        self.assertEqual(payload["relationships"], [])
        self.assertTrue(any("relationship catalog" in hint.lower() for hint in payload["hints"]))

    def test_relationships_can_be_skipped(self):
        payload = get_dataset_schema(self.client, 7, include_relationships=False)

        self.assertEqual(payload["relationships"], [])
        self.client.datasets.get_relationships.assert_not_called()

    def test_raster_dataset_has_no_fields(self):
        self.client.datasets.get.return_value = _dataset(
            dataType="raster",
            details={"srid": 3857, "width": 100, "height": 100},
        )
        self.client.datasets.get_relationships.return_value = []

        payload = get_dataset_schema(self.client, 7)

        self.assertEqual(payload["fields"], [])
        self.assertTrue(any("raster" in hint.lower() for hint in payload["hints"]))


class AggregateHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.datasets.aggregate.return_value = AggregateResult(
            datasetId=7,
            rows=[{"zone": "A", "total": 12.5}, {"zone": "B", "total": 7.0}],
            columns=[{"type": "string", "key": "zone"}],
            metadata={"queryMode": "aggregate"},
        )

    def test_rows_are_returned_verbatim_with_echo(self):
        payload = aggregate_dataset(
            self.client,
            7,
            aggregates=[{"aggregate": "sum", "field": "area_ha", "alias": "total"}],
            group_by=["zone"],
        )

        self.assertEqual(payload["rows"], [{"zone": "A", "total": 12.5}, {"zone": "B", "total": 7.0}])
        self.assertEqual(payload["rowCount"], 2)
        self.assertEqual(payload["aggregationApplied"]["limit"], 20)
        self.assertEqual(
            payload["aggregationApplied"]["aggregates"],
            [{"aggregate": "sum", "field": "area_ha", "alias": "total"}],
        )
        self.assertEqual(payload["aggregationApplied"]["groupBy"], [{"field": "zone"}])

    def test_default_is_count(self):
        aggregate_dataset(self.client, 7)
        kwargs = self.client.datasets.aggregate.call_args.kwargs

        self.assertEqual(kwargs["aggregation"]["aggregates"], [{"aggregate": "count"}])

    def test_percentile_requires_p_before_any_call(self):
        with self.assertRaises(ValueError):
            aggregate_dataset(self.client, 7, aggregates=[{"aggregate": "percentile", "field": "area_ha"}])

        self.client.datasets.aggregate.assert_not_called()

    def test_percentile_p_is_range_checked(self):
        with self.assertRaises(ValueError):
            aggregate_dataset(
                self.client,
                7,
                aggregates=[{"aggregate": "percentile", "field": "area_ha", "p": 1.5}],
            )

        self.client.datasets.aggregate.assert_not_called()

    def test_unknown_kind_names_the_enumeration(self):
        with self.assertRaises(ValueError) as ctx:
            aggregate_dataset(self.client, 7, aggregates=[{"aggregate": "mode", "field": "zone"}])

        message = str(ctx.exception)
        for kind in AGGREGATE_KINDS:
            self.assertIn(kind, message)

    def test_field_is_required_for_measure_aggregates(self):
        with self.assertRaises(ValueError):
            aggregate_dataset(self.client, 7, aggregates=[{"aggregate": "avg"}])

    def test_group_by_is_capped_at_three(self):
        with self.assertRaises(ValueError):
            aggregate_dataset(self.client, 7, group_by=["a", "b", "c", "d"])

    def test_unsupported_store_points_at_query_dataset(self):
        self.client.datasets.aggregate.side_effect = AggregationUnsupported(
            400, "cannot aggregate", {"code": "AGGREGATION_UNSUPPORTED"}
        )

        payload = aggregate_dataset(self.client, 7)

        self.assertTrue(payload["error"])
        self.assertIn("query_dataset", payload["hint"])

    def test_invalid_key_names_the_key(self):
        self.client.datasets.aggregate.side_effect = AggregationInvalidArgs(
            400, "unknown key", {"code": "AGGREGATION_INVALID_ARGS", "key": "area"}
        )

        payload = aggregate_dataset(self.client, 7)

        self.assertTrue(payload["error"])
        self.assertEqual(payload["key"], "area")
        self.assertIn("get_dataset_schema", payload["hint"])

    def test_count_alias_is_translated_to_aggregate_count(self):
        """A count aggregate's alias is ignored by the adapter (F3)."""
        aggregate_dataset(
            self.client,
            7,
            aggregates=[{"aggregate": "count", "alias": "n"}],
            group_by=["landuse_group"],
            order_by=[{"key": "n", "direction": "desc"}],
        )

        order = self.client.datasets.aggregate.call_args.kwargs["aggregation"]["orderBy"]
        self.assertEqual(order, [{"key": "aggregate_count", "direction": "desc"}])

    def test_measure_alias_and_group_field_are_accepted(self):
        aggregate_dataset(
            self.client,
            7,
            aggregates=[{"aggregate": "sum", "field": "area_ha", "alias": "total"}],
            group_by=["zone"],
            order_by=[{"key": "total", "direction": "desc"}, {"key": "zone"}],
        )

        order = self.client.datasets.aggregate.call_args.kwargs["aggregation"]["orderBy"]
        self.assertEqual(order[0]["key"], "total")
        self.assertEqual(order[1]["key"], "zone")

    def test_unknown_order_key_is_refused_with_the_legal_list(self):
        with self.assertRaises(ValueError) as ctx:
            aggregate_dataset(
                self.client,
                7,
                aggregates=[{"aggregate": "count", "alias": "n"}],
                group_by=["landuse_group"],
                order_by=[{"key": "bogus"}],
            )

        message = str(ctx.exception)
        self.assertIn("bogus", message)
        self.assertIn("aggregate_count", ctx.exception.hint)
        self.assertIn("landuse_group", ctx.exception.hint)
        self.client.datasets.aggregate.assert_not_called()

    def test_order_by_wrong_by_value_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            aggregate_dataset(
                self.client,
                7,
                group_by=["zone"],
                order_by=[{"key": "zone", "by": "label_name"}],
            )

        self.assertIn("value", str(ctx.exception))
        self.assertIn("label", str(ctx.exception))
        self.client.datasets.aggregate.assert_not_called()

    def test_order_by_by_label_is_forwarded(self):
        aggregate_dataset(
            self.client,
            7,
            group_by=["zone"],
            order_by=[{"key": "zone", "by": "Label"}],
        )

        order = self.client.datasets.aggregate.call_args.kwargs["aggregation"]["orderBy"]
        self.assertEqual(order, [{"key": "zone", "direction": "asc", "by": "label"}])


class RelationshipHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.datasets.get_relationships.return_value = [_descriptor()]

    def test_list_names_target_and_cardinality(self):
        payload = get_dataset_relationships(self.client, 7)

        self.assertFalse(payload["catalogUnavailable"])
        self.assertEqual(payload["relationships"][0]["targetDatasetName"], "buildings")
        self.assertIn("get_related_records", payload["hint"])

    def test_catalog_409_degrades_instead_of_raising(self):
        self.client.datasets.get_relationships.side_effect = RelationshipCatalogUnavailable(
            409, "catalog unavailable", {"code": "RELATIONSHIP_CATALOG_UNAVAILABLE"}
        )

        payload = get_dataset_relationships(self.client, 7)

        self.assertEqual(payload["relationships"], [])
        self.assertTrue(payload["catalogUnavailable"])
        self.assertNotIn("error", payload)
        self.assertIn("no authored relationship catalog", payload["hint"])

    def test_empty_catalog_has_a_hint(self):
        self.client.datasets.get_relationships.return_value = []

        payload = get_dataset_relationships(self.client, 7)

        self.assertEqual(payload["relationships"], [])
        self.assertIn("No relationships", payload["hint"])


class RelatedRecordsHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.datasets.get_related_records.return_value = RelatedRecordsResult(
            type="FeatureCollection",
            features=[{"id": 3, "properties": {"name": "B1", "__jct__oid": 9}}],
            metadata={"count": 1, "groups": {"5": [3]}, "relationshipName": "parcels_buildings"},
        )

    def test_geometry_is_off_by_default(self):
        payload = get_related_records(self.client, 7, "parcels_buildings", [5])

        kwargs = self.client.datasets.get_related_records.call_args.kwargs
        self.assertFalse(kwargs["return_geometry"])
        self.assertEqual(payload["queryLimitApplied"], 50)
        self.assertEqual(payload["queryOffsetApplied"], 0)
        self.assertEqual(payload["groups"], {"5": [3]})
        self.assertEqual(payload["features"][0]["properties"]["__jct__oid"], 9)

    def test_full_page_flags_more_available(self):
        self.client.datasets.get_related_records.return_value = RelatedRecordsResult(
            features=[{"id": 1, "properties": {}}] * 3,
            metadata={"count": 3},
        )

        payload = get_related_records(self.client, 7, "parcels_buildings", [5], limit=3)

        self.assertTrue(payload["featuresTruncated"])
        self.assertIn("offset", payload["hint"])

    def test_origin_ids_are_capped(self):
        with self.assertRaises(ValueError):
            get_related_records(self.client, 7, "parcels_buildings", list(range(101)))

        self.client.datasets.get_related_records.assert_not_called()

    def test_empty_origin_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            get_related_records(self.client, 7, "parcels_buildings", [])

    def test_blank_relationship_name_is_rejected(self):
        with self.assertRaises(ValueError):
            get_related_records(self.client, 7, "  ", [5])

    def test_403_names_the_related_leg(self):
        self.client.datasets.get_related_records.side_effect = GeopackAuthError(403, "Forbidden")

        payload = get_related_records(self.client, 7, "parcels_buildings", [5])

        self.assertTrue(payload["error"])
        self.assertIn("RELATED dataset", payload["hint"])
        self.assertIn("origin", payload["hint"])

    def test_non_403_auth_error_is_not_relabelled(self):
        self.client.datasets.get_related_records.side_effect = GeopackAuthError(401, "No session")

        with self.assertRaises(GeopackAuthError):
            get_related_records(self.client, 7, "parcels_buildings", [5])

    def test_coded_400_points_at_the_catalog_tool(self):
        self.client.datasets.get_related_records.side_effect = QueryValidationError(
            400,
            "unknown relationship",
            {"code": "RELATIONSHIP_UNKNOWN"},
        )

        payload = get_related_records(self.client, 7, "nope", [5])

        self.assertTrue(payload["error"])
        self.assertEqual(payload["code"], "RELATIONSHIP_UNKNOWN")
        self.assertIn("get_dataset_relationships", payload["hint"])


class QuotaHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_near_limit_dimension_is_called_out(self):
        self.client.quotas.get_my_quota_summary.return_value = QuotaSummary(
            enabled=True,
            plan={"id": 1, "code": "free", "displayName": "Free"},
            limits=[
                QuotaSummaryLimit(
                    limitId=1,
                    dimensionKey="storage.bytes",
                    limitType="max",
                    limitValue=1000,
                    window="month",
                    currentValue=950,
                    percentageUsed=95.0,
                )
            ],
        )

        payload = get_quota_summary(self.client)

        self.assertEqual(payload["limits"][0]["dimensionKey"], "storage.bytes")
        self.assertIn("storage.bytes", payload["hint"])
        self.assertIn("95%", payload["hint"])

    def test_healthy_dimensions_add_no_hint(self):
        self.client.quotas.get_my_quota_summary.return_value = QuotaSummary(
            enabled=True,
            limits=[
                QuotaSummaryLimit(
                    limitId=2,
                    dimensionKey="upload.count.daily",
                    limitType="max",
                    limitValue=50,
                    window="day",
                    currentValue=1,
                    percentageUsed=2.0,
                )
            ],
        )

        payload = get_quota_summary(self.client)

        self.assertNotIn("hint", payload)

    def test_disabled_quotas_explain_themselves(self):
        self.client.quotas.get_my_quota_summary.return_value = QuotaSummary(enabled=False)

        payload = get_quota_summary(self.client)

        self.assertFalse(payload["enabled"])
        self.assertIn("disabled", payload["hint"])


class ListLanesHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_workflow_runs_are_trimmed_and_offset_passed_raw(self):
        self.client.workflow_runs.list.return_value = WorkflowRunListResponse(
            items=[
                WorkflowRun(
                    id=9,
                    workflowId=2,
                    status="succeeded",
                    submittedBy=4,
                    input={"huge": "payload"},
                    logs={"steps": [{"message": "x"}]},
                    createdAt="2024-01-01T00:00:00",
                    updatedAt="2024-01-01T00:05:00",
                )
            ],
            total=41,
        )

        payload = list_workflow_runs(self.client, workflow_id=2, status="succeeded", limit=10, offset=20)

        filters = self.client.workflow_runs.list.call_args.kwargs["filters"]
        self.assertEqual(filters["offset"], 20)
        self.assertEqual(filters["workflowId"], 2)
        self.assertEqual(filters["status"], "succeeded")

        row = payload["items"][0]
        self.assertEqual(row["id"], 9)
        self.assertEqual(row["submittedBy"], 4)
        self.assertNotIn("input", row)
        self.assertNotIn("logs", row)
        self.assertNotIn("artifacts", row)
        self.assertEqual(payload["totalItems"], 41)
        self.assertEqual(payload["currentPage"], 3)
        self.assertEqual(payload["totalPages"], 5)

    def test_generated_files_expose_download_ids(self):
        self.client.generated_files.list.return_value = GeneratedFileListResponse(
            items=[
                GeneratedFile(
                    id=3,
                    fileName="parcels.zip",
                    fileSize=2048,
                    sharingPolicy="private",
                    createdAt="2024-01-02T00:00:00",
                    taskId="task-1",
                )
            ],
            totalItems=1,
            totalPages=1,
            currentPage=1,
            pageSize=20,
        )

        payload = list_generated_files(self.client)

        row = payload["items"][0]
        self.assertEqual(row["id"], 3)
        self.assertEqual(row["name"], "parcels.zip")
        self.assertEqual(row["sizeBytes"], 2048)
        self.assertNotIn("metadata", row)
        self.assertIn("download_generated_file", payload["hint"])

    def test_unaligned_offset_fetches_one_more_page(self):
        first = GeneratedFileListResponse(
            items=[GeneratedFile(id=i, fileName=f"f{i}.zip", fileSize=1) for i in range(1, 4)],
            totalItems=6,
            totalPages=2,
            currentPage=1,
            pageSize=3,
        )
        second = GeneratedFileListResponse(
            items=[GeneratedFile(id=i, fileName=f"f{i}.zip", fileSize=1) for i in range(4, 7)],
            totalItems=6,
            totalPages=2,
            currentPage=2,
            pageSize=3,
        )
        self.client.generated_files.list.side_effect = [first, second]

        payload = list_generated_files(self.client, limit=3, offset=1)

        self.assertEqual([row["id"] for row in payload["items"]], [2, 3, 4])
        self.assertEqual(self.client.generated_files.list.call_count, 2)


class WorkflowSpecLaneTest(unittest.TestCase):
    """Slice 031 — the spec lane returns the projection, never canvas state."""

    def setUp(self):
        self.client = MagicMock()

    def test_ui_keys_are_stripped_and_semantics_survive(self):
        # The projection is position-free today; this fixture plants canvas keys so a
        # future payload change cannot smuggle them through the MCP edge.
        self.client.workflows.compile_spec.return_value = {
            "ok": True,
            "mode": "project",
            "workflow": {"id": 12, "name": "buffer", "position": {"x": 1, "y": 2}},
            "projected": {
                "schemaVersion": 1,
                "nodes": [
                    {
                        "id": "buffer_1",
                        "op": "buffer",
                        "label": "Buffer 100m",
                        "position": {"x": 120, "y": 40},
                        "ui": {"measured": {"width": 180, "height": 60}},
                        "config": {"distance": 100, "width": 250, "height": 400},
                    }
                ],
                "edges": [{"from": "src", "to": "buffer_1", "sourcePosition": "right"}],
            },
            "summary": {"nodes": 1, "edges": 1},
            "issues": [],
            "compacted": {"level": 1, "budgetChars": None},
        }

        payload = get_workflow_spec(self.client, workflow_id=12)

        rendered = json.dumps(payload)
        self.assertNotIn("position", rendered)
        self.assertNotIn("measured", rendered)
        self.assertNotIn("sourcePosition", rendered)
        node = payload["projected"]["nodes"][0]
        # An operator's own width/height is run-form semantics, not canvas state.
        self.assertEqual(node["config"]["width"], 250)
        self.assertEqual(node["label"], "Buffer 100m")
        self.assertEqual(payload["summary"]["nodes"], 1)

    def test_a_budget_is_forwarded_and_none_is_the_default(self):
        self.client.workflows.compile_spec.return_value = {"ok": True, "mode": "project"}

        get_workflow_spec(self.client, workflow_id=12)
        self.assertIsNone(self.client.workflows.compile_spec.call_args.kwargs["budget_chars"])

        get_workflow_spec(self.client, workflow_id=12, budget_chars=4000)
        self.assertEqual(
            self.client.workflows.compile_spec.call_args.kwargs["budget_chars"], 4000
        )


class ToolSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from geopack_sdk_mcp.server import mcp

        cls.tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}  # noqa: SLF001

    def test_surface_is_twenty_nine_tools(self):
        self.assertEqual(len(self.tools), 29)
        self.assertEqual(set(self.tools), EXPECTED_TOOL_NAMES)

    def test_no_tool_name_collides(self):
        names = [tool.name for tool in self.tools.values()]
        self.assertEqual(len(names), len(set(names)))

    def test_every_tool_is_classified_by_the_policy_registry(self):
        self.assertEqual(set(TOOL_POLICY), EXPECTED_TOOL_NAMES)
        for name in READ_LANES:
            self.assertIn(name, TOOL_POLICY)
            self.assertFalse(TOOL_POLICY[name]["mutating"], name)

    def test_new_tools_carry_use_when_descriptions(self):
        for name in READ_LANES:
            description = self.tools[name].description or ""
            self.assertGreater(len(description), 80, f"{name} description is too thin")

    def test_aggregate_tool_documents_the_enumeration(self):
        description = self.tools["geopack_sdk_aggregate_dataset"].description
        for kind in AGGREGATE_KINDS:
            self.assertIn(kind, description)


if __name__ == "__main__":
    unittest.main()
