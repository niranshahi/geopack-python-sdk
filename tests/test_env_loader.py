import unittest
from pathlib import Path

from geopack_sdk.env_loader import DEFAULT_ENV_FILE, sdk_root_dir


class TestEnvLoader(unittest.TestCase):
    def test_default_env_file_under_sdk_root(self):
        root = sdk_root_dir()
        self.assertTrue(root.is_dir())
        self.assertEqual(DEFAULT_ENV_FILE, root / ".env")
        self.assertEqual(DEFAULT_ENV_FILE.parent, Path(root))


if __name__ == "__main__":
    unittest.main()
