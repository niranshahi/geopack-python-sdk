import os
import sys
import time
from dotenv import load_dotenv
from geopack_sdk import GeopackClient

# Load configuration from .env file if it exists
load_dotenv()

def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")
    
    # Check for test file path in env, or use a default
    test_file_path = os.getenv("TEST_GEOJSON_PATH", r"d:\Works\Data\GeoJSON\Rural_District.shp.geojson")

    print(f"--- Geopack SDK Upload Test ---")
    print(f"Target API: {api_url}")
    
    if not test_file_path:
        print("\n! No TEST_GEOJSON_PATH found in environment.")
        print("! Skipping actual upload. To test for real, set TEST_GEOJSON_PATH in .env")
        return

    try:
        # 1. Initialize Client
        client = GeopackClient(base_url=api_url)

        # 2. Authenticate
        print("\n[1/4] Logging in...")
        client.auth.login(username=username, password=password)
        print("✓ Login successful!")

        # 3. Resolve target datastore and workgroup
        print("\n[2/4] Resolving target datastore and workgroup...")
        # Get the first datastore and first workgroup for testing
        datastores = client.datastores.list()
        if not datastores:
            print("✖ No datastores found. Cannot proceed with upload test.")
            return
        
        target_ds = datastores[0]
        ds_id = target_ds['id']
        ds_name = target_ds['name']
        
        # Use the new workgroups manager
        workgroups = client.workgroups.list()
        if not workgroups:
            print("✖ No workgroups found. Cannot proceed with upload test.")
            return
        
        target_wg = workgroups[0]
        wg_id = target_wg['id']
        wg_name = target_wg['name']
        
        print(f"✓ Target: DataStore '{ds_name}' (ID: {ds_id}), Workgroup '{wg_name}' (ID: {wg_id})")

        # 4. Upload file
        print(f"\n[3/4] Uploading file: {test_file_path} ...")
        # This will upload then wait for the background task to complete
        start_time = time.time()
        results = client.datasets.upload(
            file_path=test_file_path,
            data_store_id=ds_id,
            workgroup_id=wg_id,
            wait=True
        )
        duration = time.time() - start_time
        
        print(f"✓ Upload and processing complete in {duration:.1f}s")
        
        # 5. Verify results
        print("\n[4/4] Verifying results...")
        # Task results are stored in the 'results' field (confirmed via debug output)
        task_results = results.get('results')
        if isinstance(task_results, list) and len(task_results) > 0:
            print(f"✓ Successfully created {len(task_results)} dataset(s):")
            for res in task_results:
                created_ds_id = res.get('createdDatasetId')
                ds_name = res.get('datasetName', 'N/A')
                print(f"  - {ds_name} [ID: {created_ds_id}]")
        else:
            print("! Task finished but results field is empty or missing dataset IDs.")
            print(f"  Full Task Response: {results}")

        print("\n--- Upload Test Completed Successfully ---")

    except Exception as e:
        print(f"\n✖ Test Failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
