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
        print("✓ Login successful!")
        # print(f"Debug Info: {login_response.get('user', {}).get('userName')} authenticated.")

        # 3. List Datasets
        print("\n[2/5] Fetching datasets list...")
        datasets = client.datasets.list(page_size=5)
        
        if datasets:
            print(f"✓ Found {len(datasets)} datasets (showing top 5):")
            for ds in datasets:
                # API returns objects, SDK list() extracts the 'datasets' array
                name = ds.get('name', 'N/A')
                ds_id = ds.get('id', 'N/A')
                data_type = ds.get('dataType', 'unknown')
                print(f"  - {name} [ID: {ds_id}, Type: {data_type}]")
        else:
            print("! No datasets found or access restricted.")

        # Dataset filter statistics
        print("\n[2.5/5] Fetching dataset filter statistics...")
        stats = client.datasets.get_statistics()
        if isinstance(stats, dict):
            org_count = len(stats.get('organizations', []) or [])
            keyword_count = len(stats.get('keywords', []) or [])
            print(f"✓ Statistics loaded (organizations={org_count}, keywords={keyword_count})")
        else:
            print("! Statistics endpoint returned unexpected format")

        # 4. List DataStores
        print("\n[3/5] Fetching datastores...")
        try:
            datastores = client.datastores.list()
            if isinstance(datastores, list):
                print(f"✓ Found {len(datastores)} datastores:")
                for ds in datastores[:5]:
                    ds_name = ds.get('name', 'N/A')
                    ds_type = ds.get('type', 'unknown')
                    ds_status = ds.get('status', '?')
                    caps = ds.get('capabilities', [])
                    print(f"  - {ds_name} [type={ds_type}, status={ds_status}, caps={len(caps)}]")
            else:
                print("! DataStores endpoint returned unexpected format")
        except Exception as ds_err:
            print(f"! DataStores list failed: {ds_err}")

        # 5. DataStores by capabilities
        print("\n[4/5] Fetching datastores by capabilities (dataset-creation)...")
        try:
            ds_caps = client.datastores.list_by_capabilities(purpose='dataset-creation')
            if isinstance(ds_caps, dict) and 'data' in ds_caps:
                count = len(ds_caps['data'])
                print(f"✓ dataset-creation datastores: {count}")
            else:
                print("! by-capabilities returned unexpected format")
        except Exception as cap_err:
            print(f"! by-capabilities failed: {cap_err}")

        # 6. Check Tasks (Optional)
        print("\n[5/5] Testing task system connectivity...")
        try:
            client.get("/tasks/summary")
            print("✓ Task system is reachable.")
        except:
            print("! Task summary endpoint not reachable (might be permissions).")

        print("\n--- Test Completed Successfully ---")

    except Exception as e:
        print(f"\n✖ Test Failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
