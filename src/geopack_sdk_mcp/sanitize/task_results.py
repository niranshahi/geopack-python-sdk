"""Normalize task status/results for MCP tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

_MAX_TASK_MESSAGES = 100


def generated_file_download_path(generated_file_id: int) -> str:
    """Relative API path for authenticated download (no host, no token)."""
    return f"/generated-files/{generated_file_id}/download"


def sanitize_task_results(results: Any) -> Any:
    """
    Strip capability tokens from export output; add Bearer-friendly download path.
    """
    if not isinstance(results, dict):
        return results

    out = dict(results)
    generated_file_id = out.get("generatedFileId")

    if generated_file_id is not None:
        try:
            file_id = int(generated_file_id)
        except (TypeError, ValueError):
            file_id = None
        if file_id is not None:
            out["downloadApiPath"] = generated_file_download_path(file_id)

    # Avoid leaking download tokens into LLM context when generated file id exists
    if generated_file_id is not None:
        out.pop("downloadToken", None)
        out.pop("downloadPath", None)

    return out


def sanitize_task_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy safe for MCP tool JSON (truncate logs, sanitize results)."""
    if not isinstance(payload, dict):
        return payload

    out = dict(payload)

    messages = out.get("messages")
    if isinstance(messages, list) and len(messages) > _MAX_TASK_MESSAGES:
        out["messages"] = messages[:_MAX_TASK_MESSAGES]
        out["messagesTruncated"] = True
        out["messagesTotal"] = len(messages)

    if out.get("results") is not None:
        out["results"] = sanitize_task_results(out["results"])

    return out
