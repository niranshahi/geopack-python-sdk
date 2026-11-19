"""Upload limits — the pre-flight lane for file uploads.

The portal enforces a per-file size cap and a per-upload file count. Reading
them first turns "my 900 MB upload failed" into a check the caller makes before
moving a byte::

    limits = client.uploads.get_limits()
    if size > limits.max_bytes:
        raise SystemExit(f"{size} exceeds {limits.maxFileSizeMb} MB")

The endpoint carries exactly these two caps; there is no allowed-extension or
declared-type list on the wire, so the SDK does not pretend to know one.
"""

from typing import Any

from .models import UploadLimits


def _parse_upload_limits(response_data: Any) -> UploadLimits:
    """Normalize the payload — the route answers the caps at the top level.

    A wrapper (``{success, data}``) is tolerated because other routes use one,
    but the caps themselves are never synthesized: a missing key stays missing
    on the wire and surfaces as a validation error instead of a silent default.
    """
    if isinstance(response_data, dict):
        data = response_data.get("data", response_data)
        if isinstance(data, dict):
            return UploadLimits(**data)
    return UploadLimits(**(response_data or {}))


class UploadManager:
    """Upload caps for the current server.

    REST API: ``GET /api/uploads/limits``
    """

    def __init__(self, client):
        self.client = client

    def get_limits(self) -> UploadLimits:
        """Read ``maxFileSizeMb`` / ``maxFilesPerUpload`` before uploading.

        Pure and side-effect free. Upload the files themselves through the
        existing upload helpers; this manager only answers the caps.
        """
        response_data = self.client.get("/uploads/limits")
        return _parse_upload_limits(response_data)
