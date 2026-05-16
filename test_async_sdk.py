"""
Live integration test for AsyncGeopackClient (requires running API + .env).

Usage (from python-sdk/):
  python test_async_sdk.py

Environment (.env):
  GEOPACK_API_URL=http://localhost:3000/api
  GEOPACK_USERNAME=admin
  GEOPACK_PASSWORD=...

Optional:
  TEST_TASK_ID=<uuid>           — poll one task with wait_for_task
  TEST_TASK_IDS=id1,id2         — parallel poll with wait_for_tasks
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()


async def _run() -> None:
    try:
        from geopack_sdk import AsyncGeopackClient
    except ImportError as exc:
        print(
            "[ERROR] geopack_sdk not found. Set PYTHONPATH=src or pip install -e ."
        )
        raise SystemExit(1) from exc

    try:
        import httpx  # noqa: F401
    except ImportError:
        print("[ERROR] httpx is required: pip install httpx  (or pip install geopack-sdk[async])")
        raise SystemExit(1)

    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")

    print("--- Geopack Async SDK Connection Test ---")
    print(f"Target API: {api_url}")
    print(f"User: {username}")

    async with AsyncGeopackClient(base_url=api_url) as client:
        print("\n[1/6] Login...")
        await client.auth.login(username=username, password=password)
        me = await client.users.me()
        print(f"[OK] Login successful (user={me.userName}, id={me.id})")

        print("\n[2/6] Parallel reads (asyncio.gather)...")
        t0 = time.perf_counter()
        summary, datasets_resp, stores_resp, quota = await asyncio.gather(
            client.tasks.summary(),
            client.datasets.list(page_size=5),
            client.datastores.list(),
            client.quotas.my_summary(),
        )
        gather_sec = time.perf_counter() - t0
        print(
            f"[OK] tasks: pending={summary.pending}, processing={summary.processing}"
        )
        print(f"     datasets (page): {len(datasets_resp.datasets)}")
        print(f"     datastores: {len(stores_resp.datastores)}")
        print(f"     quotas enabled: {quota.enabled}")
        print(f"     gather elapsed: {gather_sec:.2f}s")

        print("\n[3/6] Sequential reads (comparison)...")
        t0 = time.perf_counter()
        await client.tasks.summary()
        await client.datasets.list(page_size=5)
        await client.datastores.list()
        await client.quotas.my_summary()
        seq_sec = time.perf_counter() - t0
        print(f"[OK] sequential elapsed: {seq_sec:.2f}s")

        print("\n[4/6] Workflows list...")
        workflows = await client.workflows.list(page_size=3)
        print(f"[OK] workflows (sample): {len(workflows)}")
        for wf in workflows[:3]:
            print(f"  - {wf.name} [id={wf.id}]")

        task_id = os.getenv("TEST_TASK_ID", "").strip()
        if task_id:
            print(f"\n[5/6] wait_for_task ({task_id})...")
            result = await client.tasks.wait_for_task(
                task_id, timeout=300, interval=2, quiet=False
            )
            print(f"[OK] status={result.status}, type={result.taskType}")
        else:
            print("\n[5/6] wait_for_task — skipped (set TEST_TASK_ID in .env)")

        task_ids = [
            x.strip() for x in os.getenv("TEST_TASK_IDS", "").split(",") if x.strip()
        ]
        if len(task_ids) >= 2:
            print(f"\n[6/6] wait_for_tasks ({len(task_ids)} ids)...")
            results = await client.tasks.wait_for_tasks(
                task_ids, timeout=300, interval=2, quiet=True
            )
            for r in results:
                print(f"  - {r.taskId}: {r.status}")
            print("[OK] parallel task polling finished")
        else:
            print("\n[6/6] wait_for_tasks — skipped (set TEST_TASK_IDS=id1,id2 in .env)")

    print("\n--- Async Test Completed Successfully ---")


def main() -> None:
    try:
        asyncio.run(_run())
    except Exception as exc:
        print(f"\n[ERROR] Test Failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
