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
        print("\n[1/3] Attempting login...")
        login_response = client.auth.login(username=username, password=password)
        print("✓ Login successful!")
        # print(f"Debug Info: {login_response.get('user', {}).get('userName')} authenticated.")

        # 3. List Datasets
        print("\n[2/3] Fetching datasets list...")
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

        # 4. Check Tasks (Optional)
        print("\n[3/3] Testing task system connectivity...")
        # Just a ping to the tasks endpoint
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
