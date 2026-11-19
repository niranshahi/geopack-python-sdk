"""Shape the dataset FIELD CONTRACT for ``geopack_sdk_get_dataset_schema`` (slice 020).

This module is deliberately a **whitelist**: only the keys below are copied out
of the dataset's ``details`` blob, so the heavy detail keys (tilejson, display,
thumbnail, pgisMetadata, raster metadata snapshots) can never leak into the
tool answer — the same keys :mod:`dataset_details` drops for other tools.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .dataset_details import _LIST_DROP_TOP_LEVEL, parse_details

# Domain value lists are capped: a coded-value domain can hold thousands of
# rows and the model only needs enough to write a filter.
MAX_DOMAIN_VALUES = 50
# Harness finding (slice 020 §9): models ignore nested hint objects — emit at
# most three plain sentences, most important first.
MAX_HINTS = 3

# Reused, not re-defined: one drop-list for every dataset-shaped tool payload.
DROPPED_DETAIL_KEYS = _LIST_DROP_TOP_LEVEL


def _coded_value_items(domain: Dict[str, Any]) -> Optional[List[Any]]:
    """The coded-value list of a domain, whichever key the provider used."""
    for key in ("items", "values", "codedValues"):
        values = domain.get(key)
        if isinstance(values, list):
            return values
    return None


def _domain_summary(domain: Any) -> Optional[Dict[str, Any]]:
    """Normalize one domain to ``{type:'codedValues', values[]}`` or a range.

    Two metadata shapes reach this module (see the portal's ``groupLabels``
    helper): an INLINE ``fields[].domain`` and a NAMED ``domainName`` resolved
    against ``details.domains``. Range/pattern domains are NOT value lists —
    they are reported as a range, never as invented values.
    """
    if not isinstance(domain, dict):
        return None

    kind = str(domain.get("type") or domain.get("kind") or "").strip().lower()
    items = _coded_value_items(domain)

    if items is not None or kind in ("codedvalues", "codedvalue", "enum", "items"):
        rows: List[Dict[str, Any]] = []
        for item in items or []:
            if isinstance(item, dict):
                row: Dict[str, Any] = {}
                if "code" in item:
                    row["code"] = item["code"]
                value = item.get("value", item.get("name", item.get("label")))
                if value is not None:
                    row["value"] = value
                if row:
                    rows.append(row)
            elif item is not None:
                rows.append({"code": item, "value": item})

        summary: Dict[str, Any] = {"type": "codedValues", "values": rows[:MAX_DOMAIN_VALUES]}
        if len(rows) > MAX_DOMAIN_VALUES:
            summary["valuesTruncated"] = True
            summary["valuesTotal"] = len(rows)
        return summary

    if kind == "range" or "minValue" in domain or "maxValue" in domain:
        return {
            "type": "range",
            "minValue": domain.get("minValue"),
            "maxValue": domain.get("maxValue"),
        }

    return None


def build_field_rows(
    fields: Any,
    domains: Any = None,
    *,
    include_domains: bool = False,
) -> List[Dict[str, Any]]:
    """Build the ``fields[]`` contract rows from ``details.fields``."""
    if not isinstance(fields, list):
        return []

    domains_map = domains if isinstance(domains, dict) else {}
    rows: List[Dict[str, Any]] = []

    for field in fields:
        if not isinstance(field, dict) or not field.get("name"):
            continue

        row: Dict[str, Any] = {"name": field["name"]}
        if field.get("alias"):
            row["alias"] = field["alias"]
        if field.get("type") is not None:
            row["type"] = field["type"]

        nullable = field.get("nullable")
        if nullable is None and isinstance(field.get("notNull"), bool):
            nullable = not field["notNull"]
        if isinstance(nullable, bool):
            row["nullable"] = nullable

        # Computed columns are stored as isExpression in details.fields; accept
        # an explicit isComputed too so a virtual-dataset payload reads right.
        row["isComputed"] = bool(field.get("isExpression") or field.get("isComputed"))

        domain_name = field.get("domainName")
        if domain_name:
            row["domainName"] = domain_name

        if include_domains:
            domain = field.get("domain")
            if not isinstance(domain, dict) and domain_name:
                domain = domains_map.get(domain_name)
            summary = _domain_summary(domain)
            if summary is not None:
                row["domainType"] = summary["type"]
                if summary["type"] == "codedValues":
                    row["values"] = summary["values"]
                    if summary.get("valuesTruncated"):
                        row["valuesTruncated"] = True
                        row["valuesTotal"] = summary["valuesTotal"]
                else:
                    row["minValue"] = summary.get("minValue")
                    row["maxValue"] = summary.get("maxValue")

        rows.append(row)

    return rows


def build_relationship_rows(descriptors: Any) -> List[Dict[str, Any]]:
    """Flatten relationship descriptors to names + target + cardinality.

    Enough for ``get_related_records`` to be called without a second read;
    everything else stays in the SDK's descriptor ``raw`` for programmatic use.
    """
    rows: List[Dict[str, Any]] = []
    for entry in descriptors or []:
        raw = getattr(entry, "raw", None)
        if not isinstance(raw, dict):
            raw = entry if isinstance(entry, dict) else {}
        name = getattr(entry, "name", None) or raw.get("name") or raw.get("relationshipName")
        if not name:
            continue

        destination = raw.get("destination") if isinstance(raw.get("destination"), dict) else {}
        capabilities = raw.get("capabilities") if isinstance(raw.get("capabilities"), dict) else {}

        row: Dict[str, Any] = {"name": name}
        target_id = destination.get("datasetId")
        if target_id is None:
            target_id = raw.get("relatedDatasetId")
        if target_id is not None:
            row["targetDatasetId"] = target_id
        target_name = destination.get("datasetName") or raw.get("relatedClassName")
        if target_name:
            row["targetDatasetName"] = target_name
        if raw.get("cardinality"):
            row["cardinality"] = raw["cardinality"]
        if raw.get("relationshipKind"):
            row["relationshipKind"] = raw["relationshipKind"]
        if raw.get("isAttributed"):
            row["isAttributed"] = True
        read_only = getattr(entry, "read_only", None)
        if read_only is None:
            read_only = capabilities.get("readOnly")
        row["readOnly"] = bool(read_only)
        rows.append(row)
    return rows


def build_dataset_schema(
    dataset: Dict[str, Any],
    *,
    include_domains: bool = False,
    relationships: Optional[List[Dict[str, Any]]] = None,
    field_access: Optional[Dict[str, Any]] = None,
    access_unavailable: bool = False,
    catalog_unavailable: bool = False,
    relationships_unavailable: bool = False,
) -> Dict[str, Any]:
    """Assemble the field-contract answer for one dataset (pure, no I/O)."""
    if not isinstance(dataset, dict):
        dataset = {}

    details = parse_details(dataset.get("details")) or {}
    data_type = dataset.get("dataType") or details.get("dataType")
    fields = build_field_rows(
        details.get("fields"),
        details.get("domains"),
        include_domains=include_domains,
    )

    oid_field = details.get("oidField")
    payload: Dict[str, Any] = {
        "datasetId": dataset.get("id"),
        "name": dataset.get("name"),
        "dataType": data_type,
        "geometryType": details.get("geometryType"),
        "oidField": oid_field,
        "fields": fields,
        "fieldAccess": field_access if isinstance(field_access, dict) else None,
        "relationships": relationships if isinstance(relationships, list) else [],
    }

    hints: List[str] = []
    if fields and include_domains and any(row.get("valuesTruncated") for row in fields):
        hints.append(
            f"Some domain value lists were truncated at {MAX_DOMAIN_VALUES} values; "
            "ask the user when a full domain is required."
        )
    if not fields and data_type == "raster":
        hints.append("This is a raster dataset: it has no attribute fields to filter on.")
    if not fields and data_type != "raster":
        hints.append(
            "No field list was reported for this dataset; call geopack_sdk_get_dataset "
            'with details_level="full" if you need the raw details blob.'
        )
    if access_unavailable:
        hints.append(
            "Effective field access could not be resolved; do not assume full visibility — "
            "a row read may answer 403."
        )
    if catalog_unavailable:
        hints.append(
            "This datastore has no authored relationship catalog; query the datasets directly."
        )
    elif relationships_unavailable:
        hints.append(
            "The relationship catalog could not be read; call "
            "geopack_sdk_get_dataset_relationships to see the coded error."
        )
    elif not payload["relationships"] and data_type == "vector":
        hints.append("No relationships are authored for this dataset; query it directly.")
    if data_type == "vector" and not oid_field:
        hints.append(
            "No OID field was reported; get_related_records needs OID values from a records query."
        )

    payload["hints"] = hints[:MAX_HINTS]
    return payload
