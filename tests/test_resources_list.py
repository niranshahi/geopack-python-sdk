import unittest

from geopack_sdk.resources import (
    parse_group_list_response,
    parse_organization_list_response,
)


class TestParseGroupListResponse(unittest.TestCase):
    def test_bare_array(self):
        raw = [{"id": 1, "name": "Admins", "status": "active"}]
        resp = parse_group_list_response(raw)
        self.assertEqual(len(resp.groups), 1)
        self.assertEqual(resp.totalItems, 1)
        self.assertEqual(resp.groups[0].name, "Admins")

    def test_wrapped_object(self):
        raw = {
            "groups": [{"id": 2, "name": "Editors", "status": "active"}],
            "totalItems": 1,
        }
        resp = parse_group_list_response(raw)
        self.assertEqual(len(resp.groups), 1)


class TestParseOrganizationListResponse(unittest.TestCase):
    def test_bare_array(self):
        raw = [{"id": 10, "name": "Org A", "status": "active"}]
        resp = parse_organization_list_response(raw)
        self.assertEqual(len(resp.organizations), 1)
        self.assertEqual(resp.totalItems, 1)

    def test_wrapped_object(self):
        raw = {
            "organizations": [{"id": 11, "name": "Org B", "status": "active"}],
            "totalItems": 1,
        }
        resp = parse_organization_list_response(raw)
        self.assertEqual(resp.organizations[0].name, "Org B")


if __name__ == "__main__":
    unittest.main()
