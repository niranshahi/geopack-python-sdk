"""
Live integration test: ESRI Geodatabase datastore manager (portal parity)

Mirrors ``EsriGeodatabaseDataStoreManager.vue``:
  - Load datastore + geodatabase info
  - Discover datasets (Refresh Discovery)
  - Register one / all (needs workgroup)
  - Update all schemas
  - Delete all portal datasets for this datastore (destructive)

Usage (.env):
  TEST_ESRI_DATASTORE_ID=31          # e.g. GDB_Golbahar
  TEST_WORKGROUP_ID=1                # required for registration

Read-only (default):
  python test_esri_datastore.py

Optional mutations (explicit flags):
  RUN_ESRI_REGISTER_ONE=1
  TEST_ESRI_DATASET_NAME=GDB_Golbahar.DBO.BTS   # logical name from discovery

  RUN_ESRI_REGISTER_ALL=1          # registers every discovered dataset
  RUN_ESRI_UPDATE_SCHEMAS=1
  RUN_ESRI_UPDATE_SCHEMAS_FORCE=1  # with forceUpdate=true

  RUN_ESRI_DELETE_ALL=1
  RUN_ESRI_DELETE_ALL_CONFIRM=1    # second safety flag
"""
import os
import sys

from dotenv import load_dotenv

from geopack_sdk import GeopackClient
from geopack_sdk.esri_geodatabase import (
    print_bulk_delete_summary,
    print_discovery_table,
    print_registration_summary,
    print_schema_update_summary,
)

load_dotenv()


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _resolve_esri_datastore_id(client: GeopackClient) -> int:
    raw = os.getenv("TEST_ESRI_DATASTORE_ID", "").strip()
    if raw:
        return int(raw)

    stores = client.datastores.list()
    for ds in stores.datastores:
        if "esri" in (ds.type or "").lower():
            print(f"[OK] Auto-selected ESRI datastore #{ds.id} ({ds.name})")
            return ds.id

    print("[ERROR] No ESRI datastore found. Set TEST_ESRI_DATASTORE_ID.")
    sys.exit(1)


def _resolve_workgroup_id(client: GeopackClient) -> int:
    raw = os.getenv("TEST_WORKGROUP_ID", "").strip()
    if raw:
        return int(raw)
    wgs = client.workgroups.list(page=1, page_size=20)
    if not wgs.workgroups:
        print("[ERROR] No workgroups. Set TEST_WORKGROUP_ID.")
        sys.exit(1)
    wg = wgs.workgroups[0]
    print(f"[OK] Using workgroup #{wg.id} ({wg.name})")
    return wg.id


def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")

    print("--- Geopack SDK ESRI Geodatabase Manager Test ---")
    print(f"Target API: {api_url}")

    try:
        client = GeopackClient(base_url=api_url)

        print("\n[1/5] Logging in...")
        client.auth.login(username=username, password=password)
        print("[OK] Login successful!")

        ds_id = _resolve_esri_datastore_id(client)
        print(f"\n[2/5] Datastore #{ds_id} ...")
        store = client.datastores.get(ds_id)
        print(f"  Name: {store.name}")
        print(f"  Type: {store.type}")
        print(f"  Status: {store.status}")

        print("\n[3/5] Geodatabase info (GET …/esri/info) ...")
        info = client.datastores.get_esri_geodatabase_info(ds_id)
        gdb = info.data.geodatabase
        print(f"  Version: {gdb.version}")
        print(
            f"  Counts: datasets={gdb.datasetCount}, "
            f"featureClasses={gdb.featureClassCount}, tables={gdb.tableCount}"
        )

        print("\n[4/5] Discover datasets (Refresh Discovery) ...")
        discovery = client.datastores.discover_esri_datasets(ds_id)
        print_discovery_table(discovery, max_rows_per_category=5)

        if _env_flag("RUN_ESRI_REGISTER_ONE"):
            name = os.getenv("TEST_ESRI_DATASET_NAME", "").strip()
            if not name:
                print("[ERROR] RUN_ESRI_REGISTER_ONE requires TEST_ESRI_DATASET_NAME.")
                sys.exit(1)
            wg_id = _resolve_workgroup_id(client)
            print(f"\n[5/5] Register single dataset '{name}' → workgroup #{wg_id} ...")
            result = client.datastores.register_esri_datasets(
                ds_id,
                workgroup_id=wg_id,
                dataset_names=[name],
            )
            print_registration_summary(result)

        elif _env_flag("RUN_ESRI_REGISTER_ALL"):
            wg_id = _resolve_workgroup_id(client)
            print(f"\n[5/5] Register ALL discovered datasets → workgroup #{wg_id} ...")
            result = client.datastores.register_esri_datasets(ds_id, workgroup_id=wg_id)
            print_registration_summary(result)
            print("\nRe-discovering after registration ...")
            discovery = client.datastores.discover_esri_datasets(ds_id)
            print_discovery_table(discovery, max_rows_per_category=3)

        elif _env_flag("RUN_ESRI_UPDATE_SCHEMAS"):
            force = _env_flag("RUN_ESRI_UPDATE_SCHEMAS_FORCE")
            print(f"\n[5/5] Update all schemas (forceUpdate={force}) ...")
            result = client.datastores.update_esri_dataset_schemas(ds_id, force_update=force)
            print_schema_update_summary(result)

        elif _env_flag("RUN_ESRI_DELETE_ALL"):
            if not _env_flag("RUN_ESRI_DELETE_ALL_CONFIRM"):
                print(
                    "[ERROR] RUN_ESRI_DELETE_ALL also requires "
                    "RUN_ESRI_DELETE_ALL_CONFIRM=1 (destructive)."
                )
                sys.exit(1)
            print("\n[5/5] DELETE all portal datasets for this datastore ...")
            result = client.datastores.delete_all_esri_datasets(ds_id, confirm=True)
            print_bulk_delete_summary(result)

        else:
            print(
                "\n[5/5] Skipping mutations (read-only). "
                "Set RUN_ESRI_REGISTER_ONE, RUN_ESRI_REGISTER_ALL, "
                "RUN_ESRI_UPDATE_SCHEMAS, or RUN_ESRI_DELETE_ALL to test writes."
            )

        print("\n--- ESRI Geodatabase Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] Test Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
