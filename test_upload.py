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
    test_file_path = os.getenv("TEST_GEOJSON_PATH", "")

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
        print("[OK] Login successful!")

        # 3. Resolve target datastore and workgroup
        print("\n[2/4] Resolving target datastore and workgroup...")
        # Get the first datastore and first workgroup for testing
        ds_response = client.datastores.list()
        datastores = ds_response.datastores
        if not datastores:
            print("[ERROR] No datastores found. Cannot proceed with upload test.")
            return
        
        target_ds = datastores[0]
        ds_id = target_ds.id
        ds_name = target_ds.name
        
        # Use the new workgroups manager
        wg_response = client.workgroups.list()
        workgroups = wg_response.workgroups
        if not workgroups:
            print("[ERROR] No workgroups found. Cannot proceed with upload test.")
            return
        
        target_wg = workgroups[0]
        wg_id = target_wg.id
        wg_name = target_wg.name
        
        print(f"[OK] Target: DataStore '{ds_name}' (ID: {ds_id}), Workgroup '{wg_name}' (ID: {wg_id})")

        # 3. Upload File
        print(f"[3/4] Uploading file: {test_file_path} ...")
        start_time = time.time()
        
        # This will upload the file and start a background task
        # We pass wait=False to manage the 'quiet' waiting ourselves
        task_response = client.datasets.upload(
            file_path=test_file_path,
            data_store_id=ds_id,
            workgroup_id=wg_id,
            wait=False
        )
        
        task_id = task_response.task_id
        if not task_id:
            raise ValueError("Task response missing task_id")
        print(f"[OK] File uploaded. Processing Task ID: {task_id}")
        print(f"  Waiting for processing to complete...")
        
        # Use quiet=True to avoid interleaving, and show our own progress if needed
        task_result = client.tasks.wait(task_id, quiet=True)
        
        duration = time.time() - start_time
        print(f"[OK] Upload and processing complete in {duration:.1f}s")

        # 4. Verify Results
        print("\n[4/4] Verifying results...")
        # The task results for dataset:upload contains a list of created datasets
        created_datasets = task_result.results or []
        if isinstance(created_datasets, list) and len(created_datasets) > 0:
            print(f"[OK] Successfully created {len(created_datasets)} dataset(s):")
            for res in created_datasets:
                created_ds_id = res.get('createdDatasetId') if isinstance(res, dict) else getattr(res, 'createdDatasetId', 'N/A')
                ds_name = res.get('datasetName') if isinstance(res, dict) else getattr(res, 'datasetName', 'N/A')
                print(f"  - {ds_name} [ID: {created_ds_id}]")
        else:
            print("[!] Task finished but results field is empty or missing dataset IDs.")
            print(f"  Full Task Response: {task_result}")

        print("\n--- Upload Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] Test Failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
