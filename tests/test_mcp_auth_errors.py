import os
import unittest

from geopack_sdk_mcp.auth_bootstrap import _missing_auth_error
from geopack_sdk_mcp.auth_errors import GeopackMCPAuthError


class TestMcpAuthErrors(unittest.TestCase):
    def test_missing_auth_message_is_actionable(self):
        err = _missing_auth_error("http://localhost:3000/api")
        msg = err.format_message()
        self.assertIn("authentication failed", msg)
        self.assertIn("geopack-sdk login", msg)
        self.assertIn("GEOPACK_ACCESS_TOKEN", msg)
        self.assertIn("GEOPACK_USERNAME", msg)
        self.assertIn("Checked (first match wins)", msg)

    def test_is_geopack_mcp_auth_error(self):
        err = _missing_auth_error("http://example.com/api")
        self.assertIsInstance(err, GeopackMCPAuthError)


if __name__ == "__main__":
    unittest.main()
