"""Normalize a caller-supplied attribute filter node (slice 033 follow-up).

The portal's FeatureQuery DSL accepts exactly two node shapes:

* **rule** — ``{"type": "rule", "field": ..., "operator": ..., "value": ...}``
* **group** — ``{"type": "group", "operator": "AND" | "OR", "children": [rule | group, ...]}``

A caller (and therefore a model) very often sends a *flat* rule
(``{"field": ..., "operator": ..., "value": ...}``), a bare list of rules, or a
Mongo-ish ``{"field": {"$eq": 5}}``. The portal answers those with an opaque
HTTP 500 (``QUERY_EXECUTION_FAILED``) that reads like a server bug and costs
several turns. This module coerces the common shorthand into the typed shape
client-side and refuses anything else with a coded 4xx (``invalid_args``) that
NAMES the accepted shapes — so the caller fixes the call instead of chasing a
phantom server error. A well-formed typed tree is passed through unchanged (its
children are still validated).

The operator **tokens** are deliberately not enumerated: the server validator
owns that vocabulary (``=``, ``$ilike``, ``IN``, ...) and the MCP must never
narrow it — the same rule the aggregate kinds follow.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..errors import ToolArgumentError

GROUP_OPERATORS = ("AND", "OR")

_ACCEPTED_SHAPES = (
    'a filter node must be a rule {"type":"rule","field":...,"operator":...,"value":...} '
    'or a group {"type":"group","operator":"AND"|"OR","children":[...]}. A flat '
    '{"field":...,"operator":...,"value":...} rule and a bare list of rules '
    "(combined with AND) are also accepted and normalized."
)


def _is_flat_rule(node: Dict[str, Any]) -> bool:
    return "field" in node and "operator" in node


def _has_group_keys(node: Dict[str, Any]) -> bool:
    return "children" in node and "operator" in node


def _looks_like_mongo(node: Dict[str, Any]) -> bool:
    """True for ``{"field": {"$eq": 5}}``-style nodes (a common wrong turn)."""
    for value in node.values():
        if isinstance(value, dict) and any(
            str(key).startswith("$") for key in value
        ):
            return True
    return False


def _normalize_rule(node: Dict[str, Any], *, key: str) -> Dict[str, Any]:
    field = node.get("field")
    if not isinstance(field, str) or not field.strip():
        raise ToolArgumentError(
            "a filter rule needs a non-empty 'field'",
            key=key,
            hint=(
                "Call geopack_sdk_get_dataset_schema for the exact field name; "
                + _ACCEPTED_SHAPES
            ),
        )
    operator = node.get("operator")
    if not isinstance(operator, str) or not operator.strip():
        raise ToolArgumentError(
            "a filter rule needs an 'operator' (for example '=', '$ilike', 'IN')",
            key=key,
            hint=_ACCEPTED_SHAPES,
        )
    rule: Dict[str, Any] = {"type": "rule", "field": field, "operator": operator}
    if "value" in node:
        rule["value"] = node["value"]
    return rule


def _normalize_group(node: Dict[str, Any], *, key: str) -> Dict[str, Any]:
    operator = str(node.get("operator") or "AND").strip().upper()
    if operator not in GROUP_OPERATORS:
        raise ToolArgumentError(
            f"a filter group 'operator' must be one of: {', '.join(GROUP_OPERATORS)}",
            key=key,
            hint=_ACCEPTED_SHAPES,
        )
    children_raw = node.get("children")
    if not isinstance(children_raw, list) or not children_raw:
        raise ToolArgumentError(
            "a filter group needs a non-empty 'children' list",
            key=key,
            hint=_ACCEPTED_SHAPES,
        )
    return {
        "type": "group",
        "operator": operator,
        "children": [normalize_filter_node(child, key=key) for child in children_raw],
    }


def normalize_filter_node(
    node: Optional[Any], *, key: str = "filter"
) -> Optional[Any]:
    """Coerce a caller filter node into the portal's typed DSL shape (or ``None``).

    Accepts a typed rule/group, a flat rule, a group without ``type``, and a list
    of rules; anything else raises :class:`ToolArgumentError` (``invalid_args``)
    naming the accepted shapes. ``None`` is passed through (no filter).
    """
    if node is None:
        return None
    if isinstance(node, (list, tuple)):
        if not node:
            raise ToolArgumentError(
                "a filter list must not be empty",
                key=key,
                hint=_ACCEPTED_SHAPES,
            )
        return {
            "type": "group",
            "operator": "AND",
            "children": [normalize_filter_node(child, key=key) for child in node],
        }
    if not isinstance(node, dict):
        raise ToolArgumentError(
            f"a filter node must be an object, not {type(node).__name__}",
            key=key,
            hint=_ACCEPTED_SHAPES,
        )

    node_type = node.get("type")
    if node_type == "group" or (
        node_type is None and _has_group_keys(node) and not _is_flat_rule(node)
    ):
        return _normalize_group(node, key=key)
    if node_type == "rule" or (node_type is None and _is_flat_rule(node)):
        return _normalize_rule(node, key=key)
    if node_type is None and _looks_like_mongo(node):
        raise ToolArgumentError(
            "this looks like a MongoDB-style filter; the portal DSL needs typed nodes",
            key=key,
            hint=_ACCEPTED_SHAPES,
        )
    raise ToolArgumentError(
        f"unknown filter node type {node_type!r}",
        key=key,
        hint=_ACCEPTED_SHAPES,
    )
