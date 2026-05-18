"""Cap and trim dataset query responses for MCP tool JSON."""

from __future__ import annotations

from typing import Any, Dict

DEFAULT_QUERY_LIMIT = 100
MAX_QUERY_LIMIT = 500


def clamp_query_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_QUERY_LIMIT
    return max(1, min(int(limit), MAX_QUERY_LIMIT))


def trim_feature_collection_for_mcp(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure feature query output stays bounded for LLM context."""
    if not isinstance(payload, dict):
        return payload

    out = dict(payload)
    features = out.get("features")
    if not isinstance(features, list):
        return out

    if len(features) > MAX_QUERY_LIMIT:
        out["features"] = features[:MAX_QUERY_LIMIT]
        out["featuresTruncated"] = True
        out["featuresTotal"] = len(features)

    out["featureCount"] = len(out.get("features") or [])
    return out
