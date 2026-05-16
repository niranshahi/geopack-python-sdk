"""
Live integration test: POST /api/datasets/{id}/query

Usage (.env):
  GEOPACK_API_URL, GEOPACK_USERNAME, GEOPACK_PASSWORD
  TEST_DATASET_ID — optional; defaults to first vector dataset

  python test_dataset_query.py
"""
import os
import sys

from dotenv import load_dotenv

from geopack_sdk import GeopackClient

load_dotenv()


def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")
    dataset_id = os.getenv("TEST_DATASET_ID", "").strip()
    query_limit = int(os.getenv("TEST_QUERY_LIMIT", "5"))

    print("--- Geopack SDK Dataset Query Test ---")
    print(f"Target API: {api_url}")

    try:
        client = GeopackClient(base_url=api_url)

        print("\n[1/3] Logging in...")
        client.auth.login(username=username, password=password)
        print("[OK] Login successful!")

        print("\n[2/3] Resolving dataset...")
        if dataset_id:
            ds_id = int(dataset_id)
            meta = client.datasets.get(ds_id)
            print(f"[OK] Using TEST_DATASET_ID={ds_id} ({meta.name}, type={meta.dataType})")
        else:
            response = client.datasets.list(
                page_size=20, active_filters={"dataType": "vector"}
            )
            vector_ds = [d for d in response.datasets if d.dataType == "vector"]
            if not vector_ds:
                print("[ERROR] No vector datasets found for query demo.")
                return
            target = vector_ds[0]
            ds_id = target.id
            print(f"[OK] Using vector dataset: {target.name} (ID: {ds_id})")

        print(f"\n[3/3] Running structured query (limit={query_limit})...")
        from geopack_sdk.datasets import build_simple_query

        fc = client.datasets.query(ds_id, build_simple_query(limit=query_limit, offset=0))

        print(f"[OK] FeatureCollection type: {fc.type}")
        count = len(fc.features)
        print(f"[OK] Features returned: {count}")
        if count > query_limit:
            print(
                f"[!] Note: expected at most {query_limit} features; "
                "server may ignore pagination on some adapters."
            )
        if fc.features:
            first = fc.features[0]
            props = first.properties or {}
            keys = list(props.keys())[:8]
            print(f"[OK] Sample property keys: {keys}")
            if first.geometry:
                print(f"[OK] First feature geometry type: {first.geometry.type}")

        print("\n--- Dataset Query Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] Test Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
