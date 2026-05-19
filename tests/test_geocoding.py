import unittest
from unittest.mock import MagicMock, patch

from geopack_sdk.geocoding import geocode_place


class TestGeocoding(unittest.TestCase):
    @patch("geopack_sdk.geocoding.requests.get")
    def test_geocode_place_parses_bbox(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            ok=True,
            json=lambda: [
                {
                    "display_name": "Tehran, Iran",
                    "lat": "35.69",
                    "lon": "51.42",
                    "boundingbox": ["35.5", "35.8", "51.0", "51.6"],
                }
            ],
        )
        out = geocode_place("Tehran")
        self.assertEqual(out["bbox"], [51.0, 35.5, 51.6, 35.8])


if __name__ == "__main__":
    unittest.main()
