import unittest

from geopack_sdk.dataset_payload import (
    dataset_thumbnail_api_path,
    normalize_dataset_dict,
)
from geopack_sdk.models import Dataset, DatasetsApiResponse


class TestDatasetPayload(unittest.TestCase):
    def test_strip_thumbnail_blob_sets_has_thumbnail(self):
        raw = {
            "id": 7,
            "name": "roads",
            "dataType": "vector",
            "ownerUserId": 1,
            "workgroupId": 1,
            "dataStoreId": 1,
            "createdAt": "2024-01-01T00:00:00",
            "updatedAt": "2024-01-01T00:00:00",
            "thumbnail": {"type": "Buffer", "data": [1, 2, 3]},
        }
        normalized = normalize_dataset_dict(raw)
        self.assertNotIn("thumbnail", normalized)
        self.assertTrue(normalized["hasThumbnail"])
        self.assertEqual(normalized["thumbnailApiPath"], "/datasets/7/thumbnail")
        self.assertEqual(normalized["thumbnailMintPath"], "/datasets/7/thumbnail/access-url")
        self.assertEqual(normalized["thumbnailResourceUri"], "dataset://7/thumbnail")

    def test_has_thumbnail_from_api_adds_path(self):
        raw = {
            "id": 3,
            "name": "x",
            "dataType": "raster",
            "ownerUserId": 1,
            "workgroupId": 1,
            "dataStoreId": 1,
            "createdAt": "2024-01-01T00:00:00",
            "updatedAt": "2024-01-01T00:00:00",
            "hasThumbnail": True,
        }
        model = Dataset(**raw)
        self.assertTrue(model.hasThumbnail)
        self.assertEqual(model.thumbnailApiPath, dataset_thumbnail_api_path(3))

    def test_list_response_via_model(self):
        response = DatasetsApiResponse(
            datasets=[
                Dataset(
                    id=1,
                    name="a",
                    dataType="vector",
                    ownerUserId=1,
                    workgroupId=1,
                    dataStoreId=1,
                    createdAt="2024-01-01T00:00:00",
                    updatedAt="2024-01-01T00:00:00",
                    hasThumbnail=False,
                )
            ],
            totalCount=1,
            totalPages=1,
            currentPage=1,
            itemsPerPage=10,
        )
        dumped = response.model_dump(mode="json")
        self.assertNotIn("thumbnail", dumped["datasets"][0])
        self.assertFalse(dumped["datasets"][0]["hasThumbnail"])


if __name__ == "__main__":
    unittest.main()
