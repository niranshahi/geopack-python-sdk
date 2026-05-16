"""
Live integration test: dataset ACL (GET / POST / DELETE)

By default read-only (GET). Mutations require explicit env flags.

Usage (.env):
  TEST_DATASET_ID — target dataset (required for create/delete)
  RUN_DATASET_ACL_CREATE=1  — grant dataset:read to TEST_ACL_USER_ID
  RUN_DATASET_ACL_DELETE=1  — delete TEST_DATASET_ACL_ID
  TEST_ACL_USER_ID, TEST_DATASET_ACL_ID

  python test_dataset_acl.py
"""
import os
import sys

from dotenv import load_dotenv

from geopack_sdk import GeopackClient

load_dotenv()


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")
    dataset_id = os.getenv("TEST_DATASET_ID", "").strip()

    print("--- Geopack SDK Dataset ACL Test ---")
    print(f"Target API: {api_url}")

    try:
        client = GeopackClient(base_url=api_url)

        print("\n[1/3] Logging in...")
        client.auth.login(username=username, password=password)
        print("[OK] Login successful!")

        if not dataset_id:
            response = client.datasets.list(page_size=1)
            if not response.datasets:
                print("[ERROR] No datasets found.")
                return
            ds_id = response.datasets[0].id
            print(f"[OK] Using latest dataset ID: {ds_id}")
        else:
            ds_id = int(dataset_id)
            print(f"[OK] Using TEST_DATASET_ID={ds_id}")

        print("\n[2/3] GET /datasets/{id}/acl ...")
        acls = client.datasets.get_acls(ds_id)
        print(f"[OK] {len(acls)} ACL entry(ies):")
        for acl in acls[:20]:
            perm = acl.permissionName or acl.permissionId
            principal = acl.principalName or f"{acl.principalType}#{acl.principalId}"
            print(f"  - [{acl.id}] {principal} -> {perm} ({acl.effect})")

        if _env_flag("RUN_DATASET_ACL_CREATE"):
            user_id = os.getenv("TEST_ACL_USER_ID", "").strip()
            if not user_id:
                print("[ERROR] RUN_DATASET_ACL_CREATE requires TEST_ACL_USER_ID.")
                sys.exit(1)
            print("\n[3/3] POST /datasets/{id}/acl (create)...")
            created = client.datasets.create_acls(
                ds_id,
                principals=[{"principalType": "USER", "principalId": int(user_id)}],
                permissions=["dataset:read"],
                effect="Allow",
            )
            print(f"[OK] Created {len(created)} ACL row(s).")
            for row in created:
                print(f"  - new acl id={row.id}")

        elif _env_flag("RUN_DATASET_ACL_DELETE"):
            acl_id = os.getenv("TEST_DATASET_ACL_ID", "").strip()
            if not acl_id:
                print("[ERROR] RUN_DATASET_ACL_DELETE requires TEST_DATASET_ACL_ID.")
                sys.exit(1)
            print(f"\n[3/3] DELETE /datasets/{ds_id}/acl/{acl_id} ...")
            client.datasets.delete_acl(ds_id, int(acl_id))
            print("[OK] ACL deleted (204).")
        else:
            print(
                "\n[3/3] Skipping ACL mutations. "
                "Set RUN_DATASET_ACL_CREATE or RUN_DATASET_ACL_DELETE to test writes."
            )

        print("\n--- Dataset ACL Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] Test Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
