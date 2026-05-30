import unittest
from unittest.mock import MagicMock

from geopack_sdk_mcp.bbox import normalize_bbox
from geopack_sdk_mcp.tool_handlers.datasets import list_datasets


class TestNormalizeBbox(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(normalize_bbox(None))

    def test_list_of_floats(self):
        self.assertEqual(
            normalize_bbox([51.0892219, 35.5682071, 51.6063007, 35.8284702]),
            [51.0892219, 35.5682071, 51.6063007, 35.8284702],
        )

    def test_comma_delimited_string(self):
        self.assertEqual(
            normalize_bbox("51.0892219, 35.5682071, 51.6063007, 35.8284702"),
            [51.0892219, 35.5682071, 51.6063007, 35.8284702],
        )

    def test_json_array_string(self):
        self.assertEqual(
            normalize_bbox("[50.3327898, 34.8652387, 53.1569031, 36.1016137]"),
            [50.3327898, 34.8652387, 53.1569031, 36.1016137],
        )

    def test_invalid_length_raises(self):
        with self.assertRaises(ValueError):
            normalize_bbox([1.0, 2.0, 3.0])

    def test_list_datasets_passes_normalized_bbox_to_client(self):
        client = MagicMock()
        client.datasets.list.return_value = {
            "datasets": [],
            "totalCount": 0,
            "totalPages": 0,
            "currentPage": 1,
            "itemsPerPage": 5,
        }

        list_datasets(
            client,
            page=1,
            page_size=5,
            bbox="51.0892219, 35.5682071, 51.6063007, 35.8284702",
            data_type="raster",
        )

        call_kwargs = client.datasets.list.call_args.kwargs
        self.assertEqual(
            call_kwargs["active_filters"]["bbox"],
            [51.0892219, 35.5682071, 51.6063007, 35.8284702],
        )
        self.assertEqual(call_kwargs["active_filters"]["dataType"], "raster")


if __name__ == "__main__":
    unittest.main()
