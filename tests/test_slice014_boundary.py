"""Slice 014 §0 boundary + sync/async parity.

The portal stores maps, publications, layouts and external services — it has no
render/export/generate endpoint. This suite asserts that the SDK matches: no
manager exposes such a method, the sync and async managers carry the same
public surface, both clients register all four, and stored documents survive a
round trip without the SDK parsing them.
"""

import unittest

from geopack_sdk import GeopackClient
from geopack_sdk.async_client import AsyncGeopackClient
from geopack_sdk.async_external_services import AsyncExternalServiceManager
from geopack_sdk.async_maps import AsyncMapManager
from geopack_sdk.async_print_layouts import AsyncPrintLayoutManager
from geopack_sdk.async_publications import AsyncPublicationManager
from geopack_sdk.external_services import ExternalServiceManager
from geopack_sdk.maps import MapManager
from geopack_sdk.models import MapDocument, Publication, StoredDocument, ThumbnailFile
from geopack_sdk.print_layouts import PrintLayoutManager
from geopack_sdk.publications import PublicationManager

MANAGER_PAIRS = (
    (MapManager, AsyncMapManager),
    (PublicationManager, AsyncPublicationManager),
    (PrintLayoutManager, AsyncPrintLayoutManager),
    (ExternalServiceManager, AsyncExternalServiceManager),
)

FORBIDDEN_PREFIXES = (
    "render_",
    "export_",
    "generate_",
    "print_",
    "compose_",
    "rasterize_",
    "produce_",
    "pdf_",
)


def _public_names(cls):
    names = set()
    for name in dir(cls):
        if name.startswith("_"):
            continue
        names.add(name)
    return names


class BoundaryTest(unittest.TestCase):
    def test_no_manager_offers_layout_or_map_production(self):
        for sync_cls, async_cls in MANAGER_PAIRS:
            for cls in (sync_cls, async_cls):
                with self.subTest(manager=cls.__name__):
                    offenders = sorted(
                        name
                        for name in _public_names(cls)
                        if name.startswith(FORBIDDEN_PREFIXES)
                    )
                    self.assertEqual(offenders, [])

    def test_sync_and_async_surfaces_match(self):
        for sync_cls, async_cls in MANAGER_PAIRS:
            with self.subTest(manager=sync_cls.__name__):
                self.assertEqual(
                    _public_names(sync_cls), _public_names(async_cls)
                )

    def test_the_four_managers_are_registered_on_both_clients(self):
        client = GeopackClient(
            "http://localhost:3000/api", enable_http_retries=False
        )
        try:
            self.assertIsInstance(client.maps, MapManager)
            self.assertIsInstance(client.publications, PublicationManager)
            self.assertIsInstance(client.print_layouts, PrintLayoutManager)
            self.assertIsInstance(client.external_services, ExternalServiceManager)
        finally:
            client.session.close()

    def test_documents_are_passed_through_without_parsing(self):
        document = {
            "id": 1,
            "name": "m",
            "details": {
                "view": {"center": [1, 2], "zoom": "not-a-number"},
                "futureKey": {"nested": [1, {"deep": True}]},
            },
        }

        wrapped = MapDocument.from_api(document)

        self.assertEqual(wrapped.raw, document)
        self.assertEqual(wrapped.id, 1)
        self.assertEqual(wrapped.raw["details"]["futureKey"]["nested"][1]["deep"], True)

    def test_a_non_dict_answer_wraps_to_an_empty_record(self):
        self.assertEqual(StoredDocument.from_api(["unexpected"]).raw, {})
        self.assertIsNone(Publication.from_api(None).status)
        self.assertEqual(Publication.from_api({"status": "active"}).status, "active")

    def test_thumbnail_model_has_no_byte_field(self):
        fields = set(ThumbnailFile.model_fields)
        self.assertEqual(fields, {"savedPath", "mimeType", "sizeBytes"})


class AsyncClientRegistrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_client_exposes_the_four_managers(self):
        async with AsyncGeopackClient(
            "http://localhost:3000/api", enable_http_retries=False
        ) as client:
            self.assertIsInstance(client.maps, AsyncMapManager)
            self.assertIsInstance(client.publications, AsyncPublicationManager)
            self.assertIsInstance(client.print_layouts, AsyncPrintLayoutManager)
            self.assertIsInstance(
                client.external_services, AsyncExternalServiceManager
            )


if __name__ == "__main__":
    unittest.main()
