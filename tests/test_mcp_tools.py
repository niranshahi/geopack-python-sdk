import unittest
from unittest.mock import MagicMock

from geopack_sdk.models import (
    Dataset,
    DatasetsApiResponse,
    FeatureCollection,
    TaskResult,
    Workflow,
    WorkflowRun,
)
from geopack_sdk_mcp.tool_handlers.datasets import get_dataset, list_datasets, query_dataset
from geopack_sdk_mcp.tool_handlers.tasks import get_task
from geopack_sdk_mcp.tool_handlers.workflow_runs import get_workflow_run
from geopack_sdk_mcp.tool_handlers.workflows import list_workflows


class TestMcpToolHandlers(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()

    def test_list_datasets_returns_jsonable_dict(self):
        self.client.datasets.list.return_value = DatasetsApiResponse(
            datasets=[
                Dataset(
                    id=1,
                    name="demo",
                    dataType="vector",
                    ownerUserId=1,
                    workgroupId=1,
                    dataStoreId=1,
                    createdAt="2024-01-01T00:00:00",
                    updatedAt="2024-01-01T00:00:00",
                )
            ],
            totalCount=1,
            totalPages=1,
            currentPage=1,
            itemsPerPage=10,
        )

        result = list_datasets(self.client, page=1, page_size=10)

        self.assertIn("datasets", result)
        self.assertEqual(result["datasets"][0]["name"], "demo")
        self.assertNotIn("thumbnail", result["datasets"][0])
        self.client.datasets.list.assert_called_once()

    def _dataset_with_details(self):
        return Dataset(
            id=4,
            name="parcels",
            dataType="vector",
            ownerUserId=1,
            workgroupId=1,
            dataStoreId=3,
            createdAt="2024-01-01T00:00:00",
            updatedAt="2024-01-01T00:00:00",
            details={"tilejson": {"tiles": ["/mvt"]}, "fields": [{"name": "a"}]},
        )

    def test_list_lite_drops_the_details_blob(self):
        self.client.datasets.list.return_value = DatasetsApiResponse(
            datasets=[self._dataset_with_details()], totalCount=1
        )

        result = list_datasets(self.client, page_size=10)

        row = result["datasets"][0]
        self.assertNotIn("details", row)
        self.assertTrue(row["detailsOmitted"])

    def test_list_fields_projects_requested_keys(self):
        self.client.datasets.list.return_value = DatasetsApiResponse(
            datasets=[self._dataset_with_details()], totalCount=1
        )

        result = list_datasets(
            self.client, page_size=10, fields=["name", "dataType", "createdAt"]
        )

        self.assertEqual(
            set(result["datasets"][0]), {"id", "name", "dataType", "createdAt"}
        )

    def test_list_unknown_field_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            list_datasets(self.client, fields=["not_a_key"])

        self.assertIn("not_a_key", str(ctx.exception))
        self.client.datasets.list.assert_not_called()

    def test_list_order_is_forwarded_and_validated(self):
        self.client.datasets.list.return_value = DatasetsApiResponse(datasets=[])

        list_datasets(self.client, page_size=10, order_by="createdAt", order_direction="desc")
        kwargs = self.client.datasets.list.call_args.kwargs
        self.assertEqual(kwargs["order_by"], "createdAt")
        self.assertEqual(kwargs["order_direction"], "desc")

        with self.assertRaises(ValueError):
            list_datasets(self.client, order_by="password")

    def test_bbox_result_states_the_filter_basis(self):
        self.client.datasets.list.return_value = DatasetsApiResponse(datasets=[])

        result = list_datasets(self.client, bbox=[51.0, 35.0, 52.0, 36.0])

        self.assertIn("extentFilterNote", result)
        self.assertIn("STORED", result["extentFilterNote"].upper())

    def test_get_task_returns_task_result(self):
        self.client.tasks.get_status.return_value = TaskResult(
            taskId="abc",
            status="completed",
            taskType="upload",
        )

        result = get_task(self.client, "abc")

        self.assertEqual(result["taskId"], "abc")
        self.assertEqual(result["status"], "completed")

    def test_list_workflows_returns_list(self):
        self.client.workflows.list.return_value = [
            Workflow(
                id=5,
                name="Buffer",
                graphJson={"nodes": [], "connections": []},
                createdAt="2024-01-01T00:00:00",
                updatedAt="2024-01-01T00:00:00",
            )
        ]

        result = list_workflows(self.client)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Buffer")

    def test_get_workflow_run(self):
        self.client.workflow_runs.get.return_value = WorkflowRun(
            id=99,
            workflowId=5,
            status="succeeded",
            createdAt="2024-01-01T00:00:00",
            updatedAt="2024-01-01T00:00:00",
        )

        result = get_workflow_run(self.client, 99)

        self.assertEqual(result["id"], 99)
        self.assertEqual(result["status"], "succeeded")

    def test_get_dataset(self):
        self.client.datasets.get.return_value = Dataset(
            id=2,
            name="roads",
            dataType="vector",
            ownerUserId=1,
            workgroupId=1,
            dataStoreId=1,
            createdAt="2024-01-01T00:00:00",
            updatedAt="2024-01-01T00:00:00",
            hasThumbnail=True,
        )

        result = get_dataset(self.client, 2)

        self.assertEqual(result["name"], "roads")
        self.assertEqual(result["thumbnailApiPath"], "/datasets/2/thumbnail")
        self.assertNotIn("thumbnail", result)

    def test_get_dataset_discloses_a_saved_renderer(self):
        self.client.datasets.get.return_value = {
            "id": 1577,
            "dataType": "vector",
            "details": {"display": {"esri": {"renderer": {"type": "uniqueValue", "field1": "LANDUSE"}}}},
        }

        result = get_dataset(self.client, 1577)

        self.assertTrue(result["symbology"]["hasSavedStyle"])
        self.assertEqual(result["symbology"]["rendererType"], "uniqueValue")

    def test_get_dataset_styled_publications_field_is_opt_in(self):
        self.client.datasets.get.return_value = {"id": 1577, "dataType": "vector", "details": {}}
        self.client.publications.list_for_dataset.return_value = [
            {"raw": {"id": 204, "protocol": "wms", "canonicalStyleRevision": "rev"}}
        ]

        result = get_dataset(self.client, 1577, fields=["symbology", "styledPublications"])

        self.assertEqual(result["styledPublications"][0]["publicationId"], 204)
        self.assertTrue(result["styledPublications"][0]["hasStyle"])

    def test_get_dataset_skips_the_publication_probe_by_default(self):
        self.client.datasets.get.return_value = {"id": 1577, "dataType": "vector", "details": {}}

        result = get_dataset(self.client, 1577)

        self.assertNotIn("styledPublications", result)
        self.client.publications.list_for_dataset.assert_not_called()

    def test_query_dataset_applies_limit(self):
        self.client.datasets.query.return_value = FeatureCollection(
            type="FeatureCollection",
            features=[],
        )

        result = query_dataset(self.client, 10, limit=50)

        self.assertEqual(result["queryLimitApplied"], 50)
        self.client.datasets.query.assert_called_once()
        call_kwargs = self.client.datasets.query.call_args.kwargs
        self.assertEqual(call_kwargs["limit"], 50)

    def test_query_dataset_warns_when_geometry_is_projected(self):
        self.client.datasets.query.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [5463069.52, 31409125.08]},
                }
            ],
        }

        result = query_dataset(self.client, 2554, limit=1)

        self.assertIn("crsNote", result)
        self.assertIn("out_srid=4326", result["crsNote"])

    def test_query_dataset_does_not_warn_for_wgs84(self):
        self.client.datasets.query.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [51.4, 35.7]},
                }
            ],
        }

        result = query_dataset(self.client, 2580, limit=1)

        self.assertNotIn("crsNote", result)

    def test_query_dataset_does_not_warn_when_reprojection_requested(self):
        # A portal that honours out_srid=4326 returns lon/lat: no warning.
        self.client.datasets.query.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [59.173, 36.587]},
                }
            ],
        }

        result = query_dataset(self.client, 2554, limit=1, out_srid=4326)

        self.assertNotIn("crsNote", result)
        self.assertEqual(result["outSridApplied"], 4326)

    def test_query_dataset_defaults_to_wgs84(self):
        self.client.datasets.query.return_value = {"type": "FeatureCollection", "features": []}

        result = query_dataset(self.client, 2554, limit=1)

        call_kwargs = self.client.datasets.query.call_args.kwargs
        self.assertEqual(call_kwargs["out_srid"], 4326)
        self.assertEqual(result["outSridApplied"], 4326)

    def test_query_dataset_applies_out_srid_in_the_query_dsl_lane(self):
        self.client.datasets.query.return_value = {"type": "FeatureCollection", "features": []}

        query_dataset(self.client, 2554, {"pagination": {"limit": 5}})

        dsl = self.client.datasets.query.call_args.args[1]
        self.assertEqual(dsl["projection"]["outSRID"], 4326)

    def test_query_dataset_repairs_a_ignored_out_srid_locally(self):
        # The portal ignored out_srid=4326 and returned native metres; the dataset
        # declares a UTM SRID, so the handler reprojects and reports the real CRS.
        self.client.datasets.query.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [500000.0, 4000000.0]},
                }
            ],
        }
        self.client.datasets.get.return_value = {"id": 2436, "details": {"spatialReference": {"srid": 32640}}}

        result = query_dataset(self.client, 2436, limit=1)

        self.assertEqual(result["outSridApplied"], 4326)
        self.assertIn("reprojected", result.get("crsNote", ""))
        x, y = result["features"][0]["geometry"]["coordinates"]
        self.assertLessEqual(abs(x), 180)
        self.assertLessEqual(abs(y), 90)


if __name__ == "__main__":
    unittest.main()
