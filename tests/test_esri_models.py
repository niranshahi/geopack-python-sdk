"""Unit tests for ESRI geodatabase API response models."""

from geopack_sdk.models import (
    EsriBulkDeleteResponse,
    EsriDiscoverResponse,
    EsriGeodatabaseInfoResponse,
    EsriRegisterResponse,
    EsriSchemaUpdateResponse,
)


DISCOVER_FIXTURE = {
    "success": True,
    "data": [
        {
            "name": "Parcels",
            "aliasName": "Parcels",
            "type": "FeatureClass",
            "physicalName": "dbo.Parcels",
            "featureDataset": "Planning",
            "geometryType": "esriGeometryPolygon",
        },
        {
            "name": "Lookup",
            "type": "Table",
            "physicalName": "dbo.Lookup",
            "featureDataset": None,
            "geometryType": None,
        },
    ],
    "metadata": {"count": 2, "datastoreId": 7},
}

REGISTER_FIXTURE = {
    "success": True,
    "data": {
        "registered": [
            {
                "datasetName": "Parcels",
                "datasetId": 101,
                "message": "Dataset registered successfully",
            }
        ],
        "updated": [],
        "skipped": [
            {
                "datasetName": "Lookup",
                "datasetId": 99,
                "message": "Dataset already exists",
            }
        ],
        "errors": [{"datasetName": "BadLayer", "error": "Schema not found"}],
    },
    "metadata": {"totalProcessed": 3, "datastoreId": 7},
}

SCHEMA_FIXTURE = {
    "success": True,
    "data": {
        "updated": [
            {
                "datasetName": "Parcels",
                "datasetId": 101,
                "changes": ["Schema updated"],
            }
        ],
        "unchanged": [],
        "failed": [
            {
                "datasetName": "Broken",
                "datasetId": 102,
                "error": "Connection timeout",
            }
        ],
    },
    "metadata": {"totalProcessed": 2, "datastoreId": 7},
}

DELETE_FIXTURE = {
    "success": True,
    "data": {
        "deleted": [{"datasetName": "Parcels", "datasetId": 101}],
        "failed": [{"datasetName": "Locked", "datasetId": 102, "error": "In use"}],
    },
    "metadata": {"totalProcessed": 2, "datastoreId": 7},
}

INFO_FIXTURE = {
    "success": True,
    "data": {
        "datastore": {
            "id": 7,
            "name": "SDE Production",
            "type": "esri-geodatabase-mssql",
            "status": "active",
        },
        "geodatabase": {
            "version": "ESRI Geodatabase Detected",
            "isVersioned": True,
            "datasetCount": 42,
            "featureClassCount": 30,
            "tableCount": 12,
            "supportedGeometryTypes": ["Point", "Polygon"],
            "spatialReferences": [{"wkid": 4326, "name": "WGS84"}],
        },
    },
    "metadata": {"datastoreId": 7},
}


def test_esri_discover_response():
    resp = EsriDiscoverResponse(**DISCOVER_FIXTURE)
    assert resp.success is True
    assert len(resp.data) == 2
    assert resp.data[0].type == "FeatureClass"
    assert resp.metadata is not None
    assert resp.metadata.count == 2


def test_esri_register_response():
    resp = EsriRegisterResponse(**REGISTER_FIXTURE)
    assert len(resp.data.registered) == 1
    assert resp.data.registered[0].datasetId == 101
    assert len(resp.data.errors) == 1
    assert resp.data.errors[0].error == "Schema not found"


def test_esri_schema_update_response():
    resp = EsriSchemaUpdateResponse(**SCHEMA_FIXTURE)
    assert resp.data.updated[0].changes == ["Schema updated"]
    assert resp.data.failed[0].error == "Connection timeout"


def test_esri_bulk_delete_response():
    resp = EsriBulkDeleteResponse(**DELETE_FIXTURE)
    assert resp.data.deleted[0].datasetName == "Parcels"
    assert resp.data.failed[0].error == "In use"


def test_esri_geodatabase_info_response():
    resp = EsriGeodatabaseInfoResponse(**INFO_FIXTURE)
    assert resp.data.datastore.name == "SDE Production"
    assert resp.data.geodatabase.datasetCount == 42
    assert resp.data.geodatabase.spatialReferences[0].wkid == 4326
