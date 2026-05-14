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
        print("✓ Login successful!")

        # 1. Fetch available workflows FIRST
        workflows = client.workflows.list()
        print(f"✓ Found {len(workflows)} workflows.")
        
        if not workflows:
            print("! No workflows found.")
            return

        # 2. Select a target workflow (Hillshade or first)
        target_wf = next((w for w in workflows if w.id == 31), workflows[0])
        wf_id = target_wf.id
        wf_details = client.workflows.get(wf_id)
        print(f"✓ Selected Workflow: {wf_details.name} (ID: {wf_id})")

        # 3. Extract parameters
        params = client.workflows.extract_params(wf_details)
        run_params = {p.key: p.default for p in params if p.required and p.default is not None}

        # 4. Execute and WAIT
        print(f"✓ Executing workflow '{wf_details.name}'... (waiting for completion)")
        run_result = client.workflow_runs.submit(workflow_id=wf_id, params=run_params, wait=True)
        
        # 5. PRINT FINAL RESULTS
        print("\n" + "="*60)
        print(f"WORKFLOW RUN #{run_result.get('id')} RESULTS")
        print("="*60)
        print(f"Status: {run_result.get('status', '').upper()}")
        
        # Artifacts & Files (Matching Portal UI)
        artifacts = run_result.get('artifacts', [])
        if artifacts:
            print("\nProduced Artifacts & Files:")
            for art in artifacts:
                art_id = art.get('id')
                node_id = art.get('nodeId') or "N/A"
                file_path = art.get('filePath')
                dataset_id = art.get('datasetId')
                
                if dataset_id:
                    print(f"  - [Dataset] ID: {dataset_id} (Ref: {art_id}) | Node: {node_id}")
                elif file_path:
                    print(f"  - [File] {file_path}")
                    print(f"    Artifact ID: {art_id} | Node: {node_id}")

        # Node Progress (Moved to bottom to avoid cutting the artifact list)
        logs = run_result.get('logs', {})
        if logs.get('nodeStatuses'):
            print("\nNode Execution Summary:")
            for node_id, status_info in logs['nodeStatuses'].items():
                status = status_info.get('status') if isinstance(status_info, dict) else status_info
                duration = f" ({status_info.get('durationMs')}ms)" if isinstance(status_info, dict) and 'durationMs' in status_info else ""
                print(f"  - {node_id}: {status}{duration}")

        if any(a.get('filePath') for a in artifacts):
            file_art = next(a for a in artifacts if a.get('filePath'))
            print(f"\n💡 To download the file above, use:")
            print(f"   client.workflow_runs.download_artifact({run_result.get('id')}, {file_art.get('id')}, './')")
        
        print("="*60)
        print("\n--- Workflow SDK Test Completed Successfully ---")

    except Exception as e:
        print(f"\n✖ SDK Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
