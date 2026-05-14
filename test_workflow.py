import os
import sys
import json
import time
from dotenv import load_dotenv
from geopack_sdk import GeopackClient

# Load configuration from .env file if it exists
load_dotenv()

def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")
    
    try:
        client = GeopackClient(base_url=api_url)
        client.auth.login(username=username, password=password)
        print("[OK] Login successful!")

        # 1. Fetch available workflows FIRST
        workflows = client.workflows.list()
        print(f"[OK] Found {len(workflows)} workflows.")
        
        if not workflows:
            print("! No workflows found.")
            return

        # 2. Select a target workflow (Hillshade or first)
        target_wf = next((w for w in workflows if w.id == 31), workflows[0])
        wf_id = target_wf.id
        wf_details = client.workflows.get(wf_id)
        print(f"[OK] Selected Workflow: {wf_details.name} (ID: {wf_id})")

        # 3. Extract parameters
        params = client.workflows.extract_params(wf_details)
        run_params = {p.key: p.default for p in params if p.required and p.default is not None}

        # 4. Execute and WAIT
        print(f"[OK] Executing workflow '{wf_details.name}'... (waiting for completion)")
        run_result = client.workflow_runs.submit(workflow_id=wf_id, params=run_params, wait=True)
        
        # 5. PRINT FINAL RESULTS
        print("\n" + "="*60)
        print(f"WORKFLOW RUN #{run_result.id} RESULTS")
        print("="*60)
        print(f"Status: {run_result.status.upper()}")
        
        # Artifacts & Files (Matching Portal UI)
        artifacts = run_result.artifacts or []
        if artifacts:
            print("\nProduced Artifacts & Files:")
            for art in artifacts:
                art_id = art.id
                node_id = art.nodeId or "N/A"
                file_path = art.filePath
                dataset_id = art.datasetId
                
                if dataset_id:
                    print(f"  - [Dataset] ID: {dataset_id} (Ref: {art_id}) | Node: {node_id}")
                elif file_path:
                    print(f"  - [File] {file_path}")
                    print(f"    Artifact ID: {art_id} | Node: {node_id}")

        # Node Progress (Moved to bottom to avoid cutting the artifact list)
        logs = run_result.logs or {}
        node_statuses = logs.get('nodeStatuses') if isinstance(logs, dict) else getattr(logs, 'nodeStatuses', None)
        if node_statuses:
            print("\nNode Execution Summary:")
            for node_id, status_info in node_statuses.items():
                status = status_info.get('status') if isinstance(status_info, dict) else status_info
                duration = f" ({status_info.get('durationMs')}ms)" if isinstance(status_info, dict) and 'durationMs' in status_info else ""
                print(f"  - {node_id}: {status}{duration}")

        if any(a.filePath for a in artifacts if a.filePath):
            file_art = next(a for a in artifacts if a.filePath)
            print(f"\n[TIP] To download the file above, use:")
            print(f"   client.workflow_runs.download_artifact({run_result.id}, {file_art.id}, './')")
        
        print("="*60)
        print("\n--- Workflow SDK Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] SDK Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
