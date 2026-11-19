"""Computed-column authoring: the catalog and the text-only preview.

Both lanes are PURE — nothing is executed and nothing is persisted:

* ``catalog`` returns the dialect's templates / measures / window functions for
  the field editor (safe to call freely);
* ``preview`` compiles either a free ``expression`` or a structured ``calc``
  descriptor against a CLIENT-SUPPLIED schema and answers in a 200 even when
  the expression is rejected (``code`` + ``message``). A rejected expression is
  a normal authoring answer, so :meth:`ComputedColumnManager.preview` returns it
  instead of raising.

The authoritative validation always re-runs server-side on dataset save
against the stored schema, so a preview success is not a guarantee.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import ComputedColumnPreview


def _build_preview_body(
    *,
    data_store_type: Optional[str],
    fields: Optional[List[Any]] = None,
    shape_field: Optional[str] = None,
    oid_field: Optional[str] = None,
    expression: Optional[str] = None,
    calc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compose the preview body and mirror the server's required-key rules."""
    if not isinstance(data_store_type, str) or not data_store_type.strip():
        raise ValueError("data_store_type must be a non-empty string.")

    has_expression = isinstance(expression, str) and expression.strip() != ""
    has_calc = isinstance(calc, dict) and bool(calc)
    if not has_expression and not has_calc:
        raise ValueError("Provide either an expression string or a calc descriptor.")

    body: Dict[str, Any] = {"dataStoreType": data_store_type}
    if fields is not None:
        body["fields"] = list(fields)
    if shape_field:
        body["shapeField"] = shape_field
    if oid_field:
        body["oidField"] = oid_field
    if has_expression:
        body["expression"] = expression
    if has_calc:
        body["calc"] = calc
    return body


class ComputedColumnManager:
    """Authoring helpers for computed (calculated) columns.

    REST API: ``GET /api/datasets/computed-column/catalog`` and
    ``POST /api/datasets/computed-column/preview``
    """

    def __init__(self, client):
        self.client = client

    def catalog(self, data_store_type: str) -> Dict[str, Any]:
        """The dialect's authoring catalog (templates, measures, windows).

        Pure and side-effect free. An unsupported store answers
        ``{"dialect": None, ...empty lists}`` — it does not raise.
        """
        if not isinstance(data_store_type, str) or not data_store_type.strip():
            raise ValueError("data_store_type must be a non-empty string.")
        response_data = self.client.get(
            "/datasets/computed-column/catalog",
            params={"dataStoreType": data_store_type},
        )
        return response_data if isinstance(response_data, dict) else {}

    def preview(
        self,
        *,
        data_store_type: str,
        fields: Optional[List[Any]] = None,
        shape_field: Optional[str] = None,
        oid_field: Optional[str] = None,
        expression: Optional[str] = None,
        calc: Optional[Dict[str, Any]] = None,
    ) -> ComputedColumnPreview:
        """Compile a free ``expression`` or a ``calc`` descriptor (no execution).

        A rejected expression comes back as ``ok=False`` with ``code``/
        ``message`` (and the catalog beside it) — it does not raise.
        """
        body = _build_preview_body(
            data_store_type=data_store_type,
            fields=fields,
            shape_field=shape_field,
            oid_field=oid_field,
            expression=expression,
            calc=calc,
        )
        response_data = self.client.post("/datasets/computed-column/preview", json=body)
        return ComputedColumnPreview(**(response_data or {}))
