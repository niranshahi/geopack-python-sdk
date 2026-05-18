"""
Live integration test for Geopack SDK MCP handlers (requires running API + .env).

This script exercises the same code paths as MCP tools, without starting stdio MCP.
Use it before wiring Cursor mcp.json.

Usage (from python-sdk/ with venv activated):
  python test_mcp_sdk.py

Optional:
  TEST_DATASET_ID=1
  TEST_TASK_ID=<uuid>
  TEST_WORKFLOW_RUN_ID=10
  MCP_CHECK_SERVER=1   — import server and list registered tool names
  TEST_EXPORT_DATASET_ID=1  TEST_EXPORT_FORMAT=geojson  TEST_EXPORT_SAVE_DIR=./tmp
      — optional full export → wait → download (requires permissions)
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _ensure_src_path() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _check_mcp_installed() -> None:
    try:
        import mcp  # noqa: F401
    except ImportError:
        print(
            "[ERROR] mcp package not installed.\n"
            "  venv\\Scripts\\activate\n"
            "  pip install -e \".[mcp]\""
        )
        raise SystemExit(1)


def _check_server_tools() -> None:
    from geopack_sdk_mcp.server import mcp

    tools = mcp._tool_manager.list_tools()  # noqa: SLF001 — test introspection
    names = sorted(t.name for t in tools)
    print(f"[OK] MCP server registered {len(names)} tools:")
    for name in names:
        print(f"  - {name}")


def main() -> None:
    _ensure_src_path()
    _check_mcp_installed()

    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    print("--- Geopack SDK MCP live test ---")
    print(f"Target API: {api_url}")

    if os.getenv("MCP_CHECK_SERVER", "").strip() in ("1", "true", "yes"):
        print("\n[0] Verifying MCP server module loads and tools register...")
        _check_server_tools()

    from geopack_sdk_mcp.auth_bootstrap import bootstrap_geopack_client
    from geopack_sdk_mcp.tool_handlers.datasets import export_dataset, get_dataset, list_datasets
    from geopack_sdk_mcp.tool_handlers.generated_files import download_generated_file
    from geopack_sdk_mcp.tool_handlers.tasks import get_task, wait_for_task
    from geopack_sdk_mcp.tool_handlers.workflow_runs import get_workflow_run
    from geopack_sdk_mcp.tool_handlers.workflows import list_workflows

    print("\n[1] Bootstrap client (env login)...")
    client = bootstrap_geopack_client()
    print("[OK] Authenticated.")

    print("\n[2] geopack_sdk_list_datasets (handler)...")
    listed = list_datasets(client, page=1, page_size=5)
    datasets = listed.get("datasets") or []
    print(f"[OK] datasets returned: {len(datasets)} (totalCount={listed.get('totalCount')})")
    for row in datasets[:5]:
        print(f"  - {row.get('name')} [id={row.get('id')}]")

    dataset_id = os.getenv("TEST_DATASET_ID")
    if not dataset_id and datasets:
        dataset_id = str(datasets[0].get("id"))
    if dataset_id:
        print(f"\n[3] geopack_sdk_get_dataset id={dataset_id}...")
        detail = get_dataset(client, int(dataset_id))
        print(f"[OK] {detail.get('name')} type={detail.get('dataType')}")

    print("\n[4] geopack_sdk_list_workflows (handler)...")
    flows = list_workflows(client, page_size=5)
    print(f"[OK] workflows: {len(flows)}")
    for wf in flows[:5]:
        print(f"  - {wf.get('name')} [id={wf.get('id')}]")

    task_id = os.getenv("TEST_TASK_ID")
    if task_id:
        print(f"\n[5] geopack_sdk_get_task id={task_id}...")
        task = get_task(client, task_id)
        print(f"[OK] status={task.get('status')} type={task.get('taskType')}")

    run_id = os.getenv("TEST_WORKFLOW_RUN_ID")
    if run_id:
        print(f"\n[6] geopack_sdk_get_workflow_run id={run_id}...")
        run = get_workflow_run(client, int(run_id))
        print(f"[OK] status={run.get('status')} workflowId={run.get('workflowId')}")

    export_dataset_id = os.getenv("TEST_EXPORT_DATASET_ID")
    export_format = os.getenv("TEST_EXPORT_FORMAT", "geojson")
    export_save_dir = os.getenv("TEST_EXPORT_SAVE_DIR", "./tmp")
    if export_dataset_id:
        print(
            f"\n[7] export → wait → download dataset={export_dataset_id} format={export_format}..."
        )
        started = export_dataset(client, int(export_dataset_id), export_format)
        task_id = started.get("taskId")
        if not task_id:
            print(f"[SKIP] export did not return taskId: {started}")
        else:
            print(f"  taskId={task_id}")
            finished = wait_for_task(client, task_id, timeout=600, interval=3)
            print(f"  status={finished.get('status')}")
            results = finished.get("results") or {}
            file_id = results.get("generatedFileId")
            if finished.get("status") == "completed" and file_id:
                os.makedirs(export_save_dir, exist_ok=True)
                saved = download_generated_file(
                    client, int(file_id), export_save_dir
                )
                print(f"[OK] saved: {saved.get('savedPath')}")
            else:
                print(f"[SKIP] no generatedFileId in results: {results}")

    print("\nDone. For Cursor, run: geopack-sdk-mcp (stdio; keep process alive).")


if __name__ == "__main__":
    main()
