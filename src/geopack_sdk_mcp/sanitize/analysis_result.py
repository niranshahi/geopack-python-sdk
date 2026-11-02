"""Keep analysis-tool output metadata-only (030 §5 defensive layer).

The portal already projects the result summary, so this is belt-and-braces: if a
server regresses and starts leaking a record payload, a geometry or a filesystem
path, it is dropped here before an LLM host ever sees it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

#: Keys that must never reach a model, at any depth of the server payload.
FORBIDDEN_KEYS = frozenset(
    {
        # record payloads
        "records",
        "features",
        "geometry",
        "geometries",
        "graphJson",
        "graphSnapshot",
        # filesystem / storage locations
        "path",
        "pathOrUri",
        "filePath",
        "absolutePath",
        "localPath",
    }
)

#: The one subtree copied verbatim: the caller's own inputs. A workflow may
#: legitimately declare a parameter keyed `geometry` or `path`, and stripping it
#: would hide the caller's own value from them.
ECHO_SUBTREE = "params"


def _strip(value: Any, dropped: List[str]) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if key in FORBIDDEN_KEYS:
                dropped.append(key)
                continue
            out[key] = item if key == ECHO_SUBTREE else _strip(item, dropped)
        return out
    if isinstance(value, list):
        return [_strip(item, dropped) for item in value]
    return value


def sanitize_analysis_result(payload: Any) -> Dict[str, Any]:
    """Return the payload with every forbidden key removed (logged on sight)."""
    if not isinstance(payload, dict):
        return {"status": str(payload)}

    dropped: List[str] = []
    cleaned = _strip(dict(payload), dropped)
    if dropped:
        logger.warning(
            "analysis result contained forbidden keys, dropped: %s",
            sorted(set(dropped)),
        )
    return cleaned


def find_forbidden_keys(payload: Any) -> List[str]:
    """Keys from :data:`FORBIDDEN_KEYS` still present — a test canary."""
    found: List[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in FORBIDDEN_KEYS:
                    found.append(key)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return found
