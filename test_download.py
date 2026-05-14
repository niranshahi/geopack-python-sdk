import os
import sys
from dotenv import load_dotenv
from geopack_sdk import GeopackClient

# Load configuration from .env file if it exists
load_dotenv()

def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")
    
    # Try to find a dataset or use a provided ID
    dataset_id = os.getenv("TEST_DATASET_ID")
   
    try:
        # 1. Initialize Client
        client = GeopackClient(base_url=api_url)

        # 2. Authenticate
        print("\n[1/4] Logging in...")
        client.auth.login(username=username, password=password)
        print("✓ Login successful!")

        # 3. Resolve Dataset ID and Info
        dataset_type = "vector" # Default
        workgroup_id = 1        # Default for testing
        
        if not dataset_id:
            # Find the latest raster dataset
            response = client.datasets.list(active_filters={"dataType": "raster"}, page_size=1)
            datasets = response.datasets
            if not datasets:
                print("! No raster datasets found. Falling back to latest any dataset.")
                response = client.datasets.list(page_size=1)
                datasets = response.datasets
            
            if not datasets:
                print("✖ No datasets found in the portal.")
                return
            
            target_ds = datasets[0]
            dataset_id = target_ds.id
            dataset_name = target_ds.name
            dataset_type = target_ds.dataType
            workgroup_id = target_ds.workgroupId or 1
            print(f"✓ Target Dataset: {dataset_name} (ID: {dataset_id}, Type: {dataset_type})")
        else:
            dataset_id = int(dataset_id)
            # Fetch dataset info to get its type and workgroup
            target_ds = client.datasets.get(dataset_id)
            dataset_type = target_ds.dataType or 'vector'
            workgroup_id = target_ds.workgroupId or 1
            print(f"✓ Using provided Dataset ID: {dataset_id} (Type: {dataset_type})")

        # 4. Request Export
        # Match formats with DatasetExportDialog.vue (GTiff/geotiff, GPKG/gpkg)
        target_format = "geotiff" if dataset_type == "raster" else "gpkg"
        wg_id = workgroup_id
        print(f"\n[2/4] Requesting export to {target_format} (Workgroup: {wg_id})...")
        export_task = client.datasets.export(
            dataset_id=dataset_id,
            workgroup_id=wg_id,
            format=target_format,
            wait=False # We handle wait ourselves to be quiet
        )
        
        task_id = export_task.taskId or export_task.id
        if not task_id:
            raise ValueError("Task response missing taskId and id")
        print(f"✓ Export task started (Task ID: {task_id}). Waiting...")
        
        # Wait quietly
        task_result = client.tasks.wait(task_id, quiet=True)
        print("✓ Export task completed successfully!")

        # 5. Download Result
        print("\n[3/4] Downloading exported file...")
        os.makedirs("downloads", exist_ok=True)
        
        # task_result is a TaskResult Pydantic model, convert to dict for download
        task_result_dict = task_result.model_dump()
        local_file = client.datasets.download(task_result_dict, "downloads/")
        print(f"✓ File saved to: {local_file}")
        
        file_size = os.path.getsize(local_file) / (1024 * 1024)
        print(f"✓ File size: {file_size:.2f} MB")

        # 6. Verification
        print("\n[4/4] Verification:")
        if os.path.exists(local_file):
            size_mb = os.path.getsize(local_file) / (1024 * 1024)
            print(f"✓ File downloaded to: {local_file}")
            print(f"✓ File size: {size_mb:.2f} MB")
            print("\n--- Export & Download Test Successful ---")
        else:
            print("✖ File download failed or file not found.")

    except Exception as e:
        print(f"\n✖ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
