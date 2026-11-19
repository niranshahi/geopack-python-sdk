"""Structured-output envelopes for the stable read lanes (slice 022 §3).

Only tools whose payload is stable declare one: ``get_dataset_schema``,
``aggregate_dataset``, ``get_quota_summary``, ``list_workflow_runs`` and
``list_generated_files``. Pass-through payloads (dataset details, analysis
results, edit plans, record pages) deliberately declare **no** schema — a rigid
schema there is a regression generator.

Every envelope is ``total=False`` on purpose. FastMCP validates a returned
``CallToolResult.structuredContent`` against the model and ignores extra keys
(the returned dict is *not* rewritten); an error payload or a server-added key
must therefore not fail validation. The envelope documents the stable top-level
keys, not an exhaustive contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class DatasetSchemaEnvelope(TypedDict, total=False):
    """``geopack_sdk_get_dataset_schema`` — the field contract answer."""

    datasetId: Optional[int]
    name: Optional[str]
    dataType: Optional[str]
    oidField: Optional[str]
    fields: List[Dict[str, Any]]
    fieldAccess: Optional[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    hints: List[str]


class AggregateEnvelope(TypedDict, total=False):
    """``geopack_sdk_aggregate_dataset`` — buckets, never rows or geometry."""

    datasetId: Optional[int]
    rows: List[Dict[str, Any]]
    columns: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    aggregationApplied: Dict[str, Any]
    rowCount: int


class QuotaSummaryEnvelope(TypedDict, total=False):
    """``geopack_sdk_get_quota_summary`` — usage per dimension plus a hint."""

    enabled: bool
    reason: Optional[str]
    plan: Optional[Dict[str, Any]]
    limits: List[Dict[str, Any]]
    hint: str


class PageEnvelope(TypedDict, total=False):
    """``list_workflow_runs`` / ``list_generated_files`` — one stable page."""

    items: List[Dict[str, Any]]
    totalItems: int
    currentPage: int
    totalPages: int
    pageSize: int
    hint: str
