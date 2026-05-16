"""
Live integration test: generated files list / download / delete

Usage (.env):
  GEOPACK_API_URL, GEOPACK_USERNAME, GEOPACK_PASSWORD
  TEST_GENERATED_FILE_ID   — optional; download this file id
  RUN_GENERATED_FILE_DOWNLOAD=1 — download first listed file if no id set
  RUN_GENERATED_FILE_DELETE=1   — delete TEST_GENERATED_FILE_ID (destructive)

  python test_generated_files.py
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
    file_id_env = os.getenv("TEST_GENERATED_FILE_ID", "").strip()
    do_download = _env_flag("RUN_GENERATED_FILE_DOWNLOAD")
    do_delete = _env_flag("RUN_GENERATED_FILE_DELETE")

    print("--- Geopack SDK Generated Files Test ---")
    print(f"Target API: {api_url}")

    try:
        client = GeopackClient(base_url=api_url)

        print("\n[1/3] Logging in...")
        client.auth.login(username=username, password=password)
        print("[OK] Login successful!")

        print("\n[2/3] Listing generated files...")
        listing = client.generated_files.list(page_size=10)
        print(f"[OK] totalItems={listing.totalItems}, page={listing.currentPage}")

        if not listing.items:
            print("[!] No generated files for this user.")
            print("    Run test_download.py or test_workflow.py first to create outputs.")
            return

        for f in listing.items:
            print(
                f"  - [{f.id}] {f.fileName} "
                f"({f.fileSize} bytes, policy={f.sharingPolicy})"
            )

        target_id = int(file_id_env) if file_id_env else None
        if target_id is None and do_download:
            target_id = listing.items[0].id
            print(f"[OK] Using first file id for download: {target_id}")

        if target_id and (do_download or file_id_env):
            print(f"\n[3/3] Downloading file #{target_id}...")
            os.makedirs("downloads", exist_ok=True)
            path = client.generated_files.download(target_id, "downloads/")
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"[OK] Saved: {path} ({size_mb:.2f} MB)")
        else:
            print(
                "\n[3/3] Skipping download. "
                "Set RUN_GENERATED_FILE_DOWNLOAD=1 or TEST_GENERATED_FILE_ID."
            )

        if do_delete:
            if not target_id:
                print("[ERROR] RUN_GENERATED_FILE_DELETE requires TEST_GENERATED_FILE_ID.")
                sys.exit(1)
            print(f"\n[!] Deleting generated file #{target_id}...")
            client.generated_files.delete(target_id)
            print("[OK] Deleted (204).")
        elif _env_flag("RUN_GENERATED_FILE_DELETE"):
            print("[!] Delete skipped: set TEST_GENERATED_FILE_ID.")

        print("\n--- Generated Files Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] Test Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
