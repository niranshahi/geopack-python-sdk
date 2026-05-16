"""Unit tests for esri_geodatabase grouping helpers."""

from geopack_sdk.esri_geodatabase import (
    filter_datasets,
    group_datasets_by_feature_dataset,
)
from geopack_sdk.models import EsriDatasetDiscovered


def _ds(name, **kwargs):
    return EsriDatasetDiscovered(
        name=name,
        type=kwargs.get("type", "FeatureClass"),
        physicalName=kwargs.get("physicalName", f"DBO.{name}"),
        featureDataset=kwargs.get("featureDataset"),
        geometryType=kwargs.get("geometryType"),
    )


def test_filter_datasets_by_physical_name():
    items = [
        _ds("A", physicalName="DBO.BTS"),
        _ds("B", physicalName="DBO.Roads"),
    ]
    assert len(filter_datasets(items, "bts")) == 1


def test_group_by_feature_dataset():
    items = [
        _ds("x", featureDataset="Communication"),
        _ds("y", featureDataset="Communication"),
        _ds("z", featureDataset=None),
    ]
    cats = group_datasets_by_feature_dataset(items)
    names = [c.name for c in cats]
    assert "Communication" in names
    assert "Uncategorized" in names
    comm = next(c for c in cats if c.name == "Communication")
    assert len(comm.datasets) == 2
