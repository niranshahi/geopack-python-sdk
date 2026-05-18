import unittest

from geopack_sdk_mcp.sanitize.task_results import (
    generated_file_download_path,
    sanitize_task_payload,
    sanitize_task_results,
)


class TestMcpTaskSanitize(unittest.TestCase):
    def test_sanitize_export_results_adds_download_path(self):
        raw = {
            "generatedFileId": 42,
            "downloadToken": "secret-uuid",
            "downloadPath": "/api/downloads/secret-uuid",
        }
        out = sanitize_task_results(raw)
        self.assertEqual(out["downloadApiPath"], "/generated-files/42/download")
        self.assertNotIn("downloadToken", out)
        self.assertNotIn("downloadPath", out)

    def test_sanitize_task_payload_truncates_messages(self):
        payload = {
            "taskId": "abc",
            "status": "completed",
            "messages": [{"level": "info", "message": f"m{i}"} for i in range(150)],
            "results": {"generatedFileId": 1},
        }
        out = sanitize_task_payload(payload)
        self.assertEqual(len(out["messages"]), 100)
        self.assertTrue(out["messagesTruncated"])
        self.assertEqual(out["messagesTotal"], 150)
        self.assertEqual(out["results"]["downloadApiPath"], "/generated-files/1/download")

    def test_generated_file_download_path(self):
        self.assertEqual(
            generated_file_download_path(9),
            "/generated-files/9/download",
        )


if __name__ == "__main__":
    unittest.main()
