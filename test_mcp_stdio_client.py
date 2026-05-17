"""
End-to-end test: spawn the MCP server subprocess and call tools over stdio.

Unlike test_mcp_sdk.py, this uses the real MCP protocol (same path as Cursor).

Usage (from python-sdk/, venv activated, API running):
  python test_mcp_stdio_client.py

Do not run as .\\test_mcp_stdio_client.py on Windows — that may use the wrong
Python. Always use the venv interpreter explicitly if needed:
  .\\venv\\Scripts\\python.exe test_mcp_stdio_client.py

Requires: pip install -e ".[mcp]"
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent

if sys.version_info < (3, 9):
    print(
        "[ERROR] Python 3.9+ required (geopack-sdk).\n"
        "  .\\venv\\Scripts\\python.exe test_mcp_stdio_client.py"
    )
    raise SystemExit(1)


def _server_command() -> Tuple[str, List[str]]:
    venv_python = ROOT / "venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python), ["-m", "geopack_sdk_mcp"]
    return sys.executable, ["-m", "geopack_sdk_mcp"]


def _tool_result_payload(result) -> object:
    if result.isError:
        return {"error": True, "content": [c.model_dump() for c in result.content]}
    for block in result.content:
        if hasattr(block, "text") and block.text:
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return block.text
        if hasattr(block, "type") and block.type == "json" and hasattr(block, "data"):
            return block.data
    return [c.model_dump() for c in result.content]


async def _run() -> None:
    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError as exc:
        print("[ERROR] mcp package required: pip install -e \".[mcp]\"")
        raise SystemExit(1) from exc

    for key in ("GEOPACK_API_URL",):
        if not os.getenv(key):
            print(f"[ERROR] Missing {key}. Set it in .env or the environment.")
            raise SystemExit(1)

    command, args = _server_command()
    print("--- Geopack SDK MCP stdio E2E test ---")
    print(f"Spawning: {command} {' '.join(args)}")
    print(f"API: {os.getenv('GEOPACK_API_URL')}")

    env = {**os.environ}
    params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = sorted(t.name for t in listed.tools)
            print(f"\n[1] list_tools: {len(names)} tools")
            for name in names:
                print(f"  - {name}")

            print("\n[2] call_tool geopack_sdk_list_datasets ...")
            result = await session.call_tool(
                "geopack_sdk_list_datasets",
                {"page": 1, "page_size": 3},
            )
            payload = _tool_result_payload(result)
            if isinstance(payload, dict) and payload.get("error"):
                print("[FAIL]", payload)
                raise SystemExit(1)
            datasets = payload.get("datasets", []) if isinstance(payload, dict) else payload
            count = len(datasets) if isinstance(datasets, list) else "?"
            print(f"[OK] received {count} dataset(s)")
            if isinstance(datasets, list):
                for row in datasets[:3]:
                    print(f"  - {row.get('name')} [id={row.get('id')}]")

            dataset_id = os.getenv("TEST_DATASET_ID")
            if not dataset_id and isinstance(datasets, list) and datasets:
                dataset_id = str(datasets[0].get("id"))
            if dataset_id:
                print(f"\n[3] call_tool geopack_sdk_get_dataset id={dataset_id} ...")
                result2 = await session.call_tool(
                    "geopack_sdk_get_dataset",
                    {"dataset_id": int(dataset_id)},
                )
                payload2 = _tool_result_payload(result2)
                if isinstance(payload2, dict) and payload2.get("error"):
                    print("[FAIL]", payload2)
                    raise SystemExit(1)
                print(f"[OK] {payload2.get('name')} type={payload2.get('dataType')}")

    print("\n--- MCP stdio E2E test passed ---")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
