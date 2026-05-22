"""Tests for WorkflowManager.extract_params ordering."""

import unittest
from unittest.mock import MagicMock

from geopack_sdk.workflows import WorkflowManager


class TestWorkflowExtractParams(unittest.TestCase):
    def test_sorts_by_each_param_node_position(self):
        client = MagicMock()
        manager = WorkflowManager(client)
        workflow = {
            "graphJson": {
                "nodes": [
                    {
                        "type": "paramNode",
                        "kind": "param",
                        "position": {"x": 10, "y": 200},
                        "config": {"key": "second", "type": "string", "nullable": True},
                    },
                    {
                        "type": "paramNode",
                        "kind": "param",
                        "position": {"x": 5, "y": 100},
                        "config": {"key": "first", "type": "string", "nullable": True},
                    },
                ],
            },
        }
        params = manager.extract_params(workflow)
        keys = [p.key for p in params]
        self.assertEqual(keys, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
