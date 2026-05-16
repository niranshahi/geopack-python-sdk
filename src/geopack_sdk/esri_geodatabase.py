"""
Helpers for ESRI Geodatabase datastore management (portal UI parity).

Mirrors grouping/search in ``EsriGeodatabaseDataStoreManager.vue``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Union

from .models import (
    EsriBulkDeleteResponse,
    EsriDatasetDiscovered,
    EsriDiscoverResponse,
    EsriRegisterResponse,
    EsriRegistrationResults,
    EsriSchemaUpdateResponse,
)

UNCATEGORIZED = "Uncategorized"


@dataclass
class EsriDatasetCategory:
    """Datasets grouped by feature dataset (like the portal table categories)."""

    name: str
    category_type: str
    datasets: List[EsriDatasetDiscovered]


def filter_datasets(
    datasets: Sequence[EsriDatasetDiscovered],
    query: str = "",
) -> List[EsriDatasetDiscovered]:
    """Filter by name, alias, physical name, or feature dataset (portal search box)."""
    q = (query or "").strip().lower()
    if not q:
        return list(datasets)
    out: List[EsriDatasetDiscovered] = []
    for ds in datasets:
        haystack = " ".join(
            filter(
                None,
                [
                    ds.name,
                    ds.aliasName,
                    ds.physicalName,
                    ds.featureDataset,
                ],
            )
        ).lower()
        if q in haystack:
            out.append(ds)
    return out


def group_datasets_by_feature_dataset(
    datasets: Sequence[EsriDatasetDiscovered],
    uncategorized_label: str = UNCATEGORIZED,
) -> List[EsriDatasetCategory]:
    """Group discovered datasets like the portal UI (feature dataset folders)."""
    buckets: dict[str, List[EsriDatasetDiscovered]] = defaultdict(list)
    for ds in datasets:
        key = (ds.featureDataset or "").strip() or uncategorized_label
        buckets[key].append(ds)

    categories: List[EsriDatasetCategory] = []
    for name in sorted(buckets.keys(), key=lambda n: (n == uncategorized_label, n.lower())):
        items = sorted(buckets[name], key=lambda d: d.name.lower())
        category_type = (
            "Feature Classes"
            if any(d.type == "FeatureClass" for d in items)
            else "Tables"
        )
        categories.append(
            EsriDatasetCategory(name=name, category_type=category_type, datasets=items)
        )
    return categories


def print_discovery_table(
    discovery: EsriDiscoverResponse,
    *,
    query: str = "",
    max_rows_per_category: Optional[int] = 10,
) -> None:
    """Print a text summary similar to the ESRI Geodatabase Manager table."""
    datasets = filter_datasets(discovery.data, query)
    meta = discovery.metadata
    print(f"Discovered: {len(datasets)} dataset(s)", end="")
    if meta and meta.count is not None:
        print(f" (API metadata count={meta.count})", end="")
    print()

    for cat in group_datasets_by_feature_dataset(datasets):
        print(f"\n▶ {cat.name} ({len(cat.datasets)}) — {cat.category_type}")
        rows = cat.datasets
        if max_rows_per_category is not None:
            rows = rows[:max_rows_per_category]
        for ds in rows:
            geom = ds.geometryType or "—"
            print(
                f"    • {ds.aliasName or ds.name}  "
                f"[{ds.type}]  {geom}  →  {ds.physicalName}"
            )
        if max_rows_per_category and len(cat.datasets) > max_rows_per_category:
            print(f"    … +{len(cat.datasets) - max_rows_per_category} more")


def print_registration_summary(result: Union[EsriRegisterResponse, EsriRegistrationResults]) -> None:
    """Print register / register-all outcome."""
    data = result.data if isinstance(result, EsriRegisterResponse) else result
    print(
        f"Registered: {len(data.registered)}, "
        f"Updated: {len(data.updated)}, "
        f"Skipped: {len(data.skipped)}, "
        f"Errors: {len(data.errors)}"
    )
    for row in data.errors[:10]:
        print(f"  ✗ {row.datasetName}: {row.error}")
    for row in data.registered[:5]:
        print(f"  ✓ {row.datasetName} → dataset #{row.datasetId}")


def print_schema_update_summary(result: EsriSchemaUpdateResponse) -> None:
    data = result.data
    print(
        f"Updated: {len(data.updated)}, "
        f"Unchanged: {len(data.unchanged)}, "
        f"Failed: {len(data.failed)}"
    )


def print_bulk_delete_summary(result: EsriBulkDeleteResponse) -> None:
    data = result.data
    print(f"Deleted: {len(data.deleted)}, Failed: {len(data.failed)}")
    for row in data.failed[:10]:
        print(f"  ✗ {row.datasetName}: {row.error}")
