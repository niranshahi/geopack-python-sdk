import os
import sys
from dotenv import load_dotenv
from geopack_sdk import GeopackClient

# Load configuration from .env file if it exists
load_dotenv()

def main():
    # Priority: ENV variables or defaults
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")

    print(f"--- Geopack SDK Connection Test ---")
    print(f"Target API: {api_url}")
    print(f"User: {username}")
    
    try:
        # 1. Initialize Client
        client = GeopackClient(base_url=api_url)

        # 2. Authenticate
        print("\n[1/5] Attempting login...")
        login_response = client.auth.login(username=username, password=password)
        print("[OK] Login successful!")
        # print(f"Debug Info: {login_response.get('user', {}).get('userName')} authenticated.")

        # 3. List Datasets
        print("\n[2/5] Fetching datasets list...")
        response = client.datasets.list(page_size=5)
        datasets = response.datasets
        
        if datasets:
            print(f"[OK] Found {len(datasets)} datasets (showing top 5):")
            for ds in datasets:
                name = ds.name
                ds_id = ds.id
                data_type = ds.dataType
                print(f"  - {name} [ID: {ds_id}, Type: {data_type}]")
        else:
            print("! No datasets found or access restricted.")

        # Dataset filter statistics
        print("\n[2.5/5] Fetching dataset filter statistics...")
        stats = client.datasets.get_statistics()
        org_count = len(stats.organizations or [])
        keyword_count = len(stats.keywords or [])
        owner_count = len(stats.owners or [])
        print(f"[OK] Statistics loaded (organizations={org_count}, keywords={keyword_count}, owners={owner_count})")

        # 4. List DataStores
        print("\n[3/5] Fetching datastores...")
        try:
            ds_response = client.datastores.list()
            datastores = ds_response.datastores
            print(f"[OK] Found {len(datastores)} datastores:")
            for ds in datastores[:5]:
                ds_name = ds.name
                ds_type = ds.type
                ds_status = ds.status
                caps = ds.capabilities
                print(f"  - {ds_name} [type={ds_type}, status={ds_status}, caps={len(caps)}]")
        except Exception as ds_err:
            print(f"! DataStores list failed: {ds_err}")

        # 5. DataStores by capabilities
        print("\n[4/5] Fetching datastores by capabilities (dataset-creation)...")
        try:
            ds_caps_response = client.datastores.list_by_capabilities(purpose='dataset-creation')
            ds_caps = ds_caps_response.datastores
            print(f"[OK] dataset-creation datastores: {len(ds_caps)}")
        except Exception as cap_err:
            print(f"! by-capabilities failed: {cap_err}")

        # 6. Check Tasks (Optional)
        print("\n[5/5] Testing task system connectivity...")
        try:
            client.get("/tasks/summary")
            print("[OK] Task system is reachable.")
        except:
            print("! Task summary endpoint not reachable (might be permissions).")

        print("\n--- Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] Test Failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
