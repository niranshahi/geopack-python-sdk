"""Parity fence between the sync and async SDK surfaces (slice 016 P4a).

The package promises sync/async symmetry. This suite is the regression fence:
every public method of every sync manager must have an async twin with a
compatible signature, and the async-only helpers must be a known set. When a
new sync method lands without a twin, this file fails — that is the point.

Deliberate exceptions live in ``SYNC_ONLY`` / ``ASYNC_ONLY`` with a reason each.
"""

import inspect
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

import httpx

from geopack_sdk import GeopackClient
from geopack_sdk.async_client import AsyncGeopackClient
from geopack_sdk.async_datasets import AsyncDatasetManager
from geopack_sdk.async_generated_files import AsyncGeneratedFileManager
from geopack_sdk.async_quotas import AsyncQuotaManager
from geopack_sdk.async_tasks import AsyncTaskManager
from geopack_sdk.async_workflows import AsyncWorkflowManager
from geopack_sdk.workflows import WorkflowManager

#: ``(client attribute, async module, async class)``
PARITY_PAIRS = [
    ("datasets", "geopack_sdk.async_datasets", "AsyncDatasetManager"),
    ("datastores", "geopack_sdk.async_datastores", "AsyncDataStoreManager"),
    ("workflows", "geopack_sdk.async_workflows", "AsyncWorkflowManager"),
    ("workflow_runs", "geopack_sdk.async_workflow_runs", "AsyncWorkflowRunManager"),
    ("analysis_tools", "geopack_sdk.async_analysis_tools", "AsyncAnalysisToolManager"),
    ("tasks", "geopack_sdk.async_tasks", "AsyncTaskManager"),
    ("generated_files", "geopack_sdk.async_generated_files", "AsyncGeneratedFileManager"),
    ("quotas", "geopack_sdk.async_quotas", "AsyncQuotaManager"),
    ("uploads", "geopack_sdk.async_uploads", "AsyncUploadManager"),
    ("maps", "geopack_sdk.async_maps", "AsyncMapManager"),
    ("publications", "geopack_sdk.async_publications", "AsyncPublicationManager"),
    ("print_layouts", "geopack_sdk.async_print_layouts", "AsyncPrintLayoutManager"),
    ("external_services", "geopack_sdk.async_external_services", "AsyncExternalServiceManager"),
    ("workgroups", "geopack_sdk.async_resources", "AsyncWorkgroupManager"),
    ("groups", "geopack_sdk.async_resources", "AsyncGroupManager"),
    ("users", "geopack_sdk.async_resources", "AsyncUserManager"),
    ("organizations", "geopack_sdk.async_resources", "AsyncOrganizationManager"),
    ("computed_columns", "geopack_sdk.async_computed_columns", "AsyncComputedColumnManager"),
    ("edit_documents", "geopack_sdk.async_edits", "AsyncEditDocumentManager"),
]

#: Sync methods with no async twin, with the reason. Empty as of 0.7.0.
SYNC_ONLY = {}

#: Async-only helpers, with the reason they have no sync twin.
ASYNC_ONLY = {
    "tasks": {
        "wait_for_tasks": (
            "parallel polling over several tasks; the sync twin is a loop the "
            "caller writes (or client.tasks.wait per id) and has no extra value"
        )
    }
}

_SRC = os.path.join(os.path.dirname(__file__), "..", "src", "geopack_sdk")


def _import_async_class(module_name, class_name):
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def _public_callables(cls):
    names = set()
    for name in dir(cls):
        if name.startswith("_"):
            continue
        if callable(getattr(cls, name, None)):
            names.add(name)
    return names


def _params(func):
    signature = inspect.signature(func)
    return [
        (name, parameter)
        for name, parameter in signature.parameters.items()
        if name != "self"
        and parameter.kind
        in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY)
    ]


class AsyncParitySurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = GeopackClient("http://example.test/api")
        cls.pairs = {
            attribute: _import_async_class(module, name)
            for attribute, module, name in PARITY_PAIRS
        }

    def test_every_sync_manager_has_an_async_twin(self):
        for attribute, _module, _name in PARITY_PAIRS:
            self.assertTrue(
                hasattr(self.client, attribute),
                f"sync client lost the {attribute} manager",
            )
            self.assertIn(attribute, self.pairs)

    def test_every_sync_public_method_has_an_async_twin(self):
        missing = {}
        for attribute, async_cls in self.pairs.items():
            sync_cls = type(getattr(self.client, attribute))
            gaps = _public_callables(sync_cls) - _public_callables(async_cls)
            gaps -= set(SYNC_ONLY.get(attribute, {}))
            if gaps:
                missing[attribute] = sorted(gaps)

        self.assertEqual(
            missing,
            {},
            "sync methods without an async twin — add the twin or record the "
            f"exception in SYNC_ONLY with a reason: {missing}",
        )

    def test_async_twins_accept_the_same_arguments(self):
        problems = []
        for attribute, async_cls in self.pairs.items():
            sync_cls = type(getattr(self.client, attribute))
            for name in sorted(_public_callables(sync_cls) & _public_callables(async_cls)):
                sync_params = dict(_params(getattr(sync_cls, name)))
                async_params = dict(_params(getattr(async_cls, name)))
                for param_name, parameter in sync_params.items():
                    if param_name not in async_params:
                        problems.append(
                            f"{attribute}.{name}: async twin is missing '{param_name}'"
                        )
                        continue
                    sync_required = parameter.default is inspect.Parameter.empty
                    async_required = (
                        async_params[param_name].default is inspect.Parameter.empty
                    )
                    if sync_required != async_required:
                        problems.append(
                            f"{attribute}.{name}: '{param_name}' is "
                            f"{'required' if sync_required else 'optional'} in sync "
                            f"but {'required' if async_required else 'optional'} in async"
                        )

        self.assertEqual(problems, [])

    def test_async_only_helpers_are_recorded(self):
        recorded = {
            attribute: set(names) for attribute, names in ASYNC_ONLY.items()
        }
        for attribute, async_cls in self.pairs.items():
            sync_cls = type(getattr(self.client, attribute))
            extras = _public_callables(async_cls) - _public_callables(sync_cls)
            self.assertEqual(
                extras,
                recorded.get(attribute, set()),
                f"{attribute}: async-only helpers must be recorded in ASYNC_ONLY "
                "with a reason (or get a sync twin)",
            )

    def test_allow_lists_carry_reasons(self):
        for attribute, entries in SYNC_ONLY.items():
            for name, reason in entries.items():
                self.assertTrue(reason, f"SYNC_ONLY[{attribute}][{name}] has no reason")
        for attribute, entries in ASYNC_ONLY.items():
            for name, reason in entries.items():
                self.assertTrue(reason, f"ASYNC_ONLY[{attribute}][{name}] has no reason")

    def test_async_modules_never_use_requests(self):
        offenders = []
        for filename in os.listdir(_SRC):
            if not filename.startswith("async_") or not filename.endswith(".py"):
                continue
            with open(os.path.join(_SRC, filename), encoding="utf-8") as handle:
                source = handle.read()
            if "import requests" in source:
                offenders.append(filename)

        self.assertEqual(
            offenders,
            [],
            "async code must use httpx; `requests` inside a coroutine blocks the loop",
        )


class AsyncParityBehaviourTest(unittest.IsolatedAsyncioTestCase):
    async def test_extract_params_matches_the_sync_manager(self):
        graph = {
            "graphJson": {
                "nodes": [
                    {
                        "type": "paramNode",
                        "config": {"key": "distance", "type": "number", "default": 5},
                        "position": {"x": 10, "y": 20},
                    },
                    {
                        "type": "datasetSelectorParamNode",
                        "config": {"key": "source", "dataType": "vector"},
                        "position": {"x": 5, "y": 10},
                    },
                ]
            }
        }

        sync_params = WorkflowManager(None).extract_params(graph)
        # Deliberately a plain call: the twin is pure computation, not a coroutine.
        async_params = AsyncWorkflowManager(MagicMock()).extract_params(graph)

        self.assertEqual(
            [p.model_dump() for p in async_params],
            [p.model_dump() for p in sync_params],
        )
        self.assertEqual([p.key for p in async_params], ["source", "distance"])

    async def test_generated_file_download_streams_and_keeps_headers(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(
                200,
                content=b"a,b\n1,2\n",
                headers={"Content-Disposition": 'attachment; filename="rows.csv"'},
            )

        client = AsyncGeopackClient("http://example.test/api")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client.auth.token = "tok"
        manager = AsyncGeneratedFileManager(client)

        with tempfile.TemporaryDirectory() as directory:
            try:
                saved = await manager.download(7, directory)
            finally:
                await client.aclose()

            self.assertEqual(saved, os.path.join(directory, "rows.csv"))
            with open(saved, "rb") as handle:
                self.assertEqual(handle.read(), b"a,b\n1,2\n")

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].url.path, "/api/generated-files/7/download")
        self.assertEqual(seen[0].headers["authorization"], "Bearer tok")

    async def test_dataset_download_resolves_the_task_results(self):
        client = AsyncMock()
        client._stream_to_file.return_value = "/tmp/out.geojson"
        manager = AsyncDatasetManager(client)

        saved = await manager.download(
            {"results": {"downloadToken": "tok-1"}}, "/tmp/out.geojson"
        )

        self.assertEqual(saved, "/tmp/out.geojson")
        client._stream_to_file.assert_awaited_once_with(
            "downloads/tok-1",
            "/tmp/out.geojson",
            fallback_filename="exported_data",
            chunk_size=8192,
        )

        with self.assertRaises(ValueError):
            await manager.download({"results": {}}, "/tmp/out.geojson")

    async def test_dataset_upload_reads_the_file_and_queues_the_task(self):
        class FakeTasks:
            def __init__(self):
                self.created = []
                self.waited = []

            async def create(self, payload):
                self.created.append(payload)
                return MagicMock(taskId="task-1", task_id="task-1")

            async def wait(self, task_id, interval=2, quiet=False):
                self.waited.append((task_id, interval, quiet))
                return "completed"

        client = MagicMock()
        client.tasks = FakeTasks()
        client._request = AsyncMock(
            return_value={
                "uploadSessionId": "sess-1",
                "files": [{"relativePath": "uploads/wells.gpkg"}],
            }
        )
        manager = AsyncDatasetManager(client)

        with tempfile.NamedTemporaryFile("wb", suffix=".gpkg", delete=False) as handle:
            handle.write(b"gpkg-bytes")
            path = handle.name

        try:
            result = await manager.upload(path, 3, 9, metadata={"name": "Wells"})
        finally:
            os.unlink(path)

        self.assertEqual(result, "completed")
        upload_call = client._request.await_args
        self.assertEqual(upload_call.args, ("POST", "/uploads/temp"))
        filename, content = upload_call.kwargs["files"]["files"]
        self.assertEqual(filename, os.path.basename(path))
        self.assertEqual(content, b"gpkg-bytes")

        task = client.tasks.created[0]
        self.assertEqual(task["taskType"], "dataset:upload")
        self.assertEqual(task["workgroupId"], 9)
        self.assertEqual(task["inputParameters"]["dataStoreId"], 3)
        self.assertEqual(task["inputParameters"]["metadata"], {"name": "Wells"})
        self.assertEqual(
            task["inputParameters"]["sourceFiles"][0]["sessionId"], "sess-1"
        )
        self.assertEqual(client.tasks.waited, [("task-1", 2, True)])

    async def test_quota_helpers_fetch_the_summary_when_omitted(self):
        from tests.test_quotas import SUMMARY_PAYLOAD

        client = AsyncMock()
        client.get.return_value = SUMMARY_PAYLOAD
        manager = AsyncQuotaManager(client)

        remaining = await manager.remaining_for("workflow.count.runs.daily")
        warned = await manager.warn_limits()

        self.assertIsNotNone(remaining)
        self.assertEqual(len(warned), 1)
        client.get.assert_awaited_with("/quotas/me/summary")

    async def test_task_create_posts_the_payload(self):
        client = AsyncMock()
        client.post.return_value = {"taskId": "task-9", "status": "pending"}
        manager = AsyncTaskManager(client)

        result = await manager.create({"taskType": "dataset:export"})

        client.post.assert_awaited_once_with(
            "/tasks", json={"taskType": "dataset:export"}
        )
        self.assertEqual(result.taskId, "task-9")


if __name__ == "__main__":
    unittest.main()
