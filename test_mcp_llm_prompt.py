"""
LLM + real MCP tools over stdio (notebook parity without Jupyter).

Usage (from python-sdk/, API running, .env with GEOPACK_* and OPENAI_*):
  python test_mcp_llm_prompt.py --staged "Find raster datasets in Tehran"
  python test_mcp_llm_prompt.py --loop "Find raster datasets in Tehran"

Requires: pip install -e ".[mcp,llm]"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
NOTEBOOKS_LIB = ROOT / "notebooks" / "lib"
if str(NOTEBOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS_LIB))

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "notebooks" / ".env")

from mcp_llm import (  # noqa: E402
    create_openai_client,
    mcp_session,
    run_mcp_tool_loop,
    staged_dataset_search,
)


async def _run_staged(prompt: str, verbose: bool) -> None:
    client = create_openai_client()
    async with mcp_session() as session:
        out = await staged_dataset_search(session, client, prompt, verbose=verbose)
    print(json.dumps(out, indent=2, default=str)[:8000])


async def _run_loop(prompt: str, verbose: bool) -> None:
    client = create_openai_client()
    async with mcp_session() as session:
        out = await run_mcp_tool_loop(session, client, prompt, verbose=verbose)
    print("--- assistant ---")
    print(out.get("assistant_text"))
    print("--- tool trace ---")
    for step in out.get("tool_trace", []):
        print(f"  {step['tool']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM + Geopack MCP stdio")
    parser.add_argument("prompt", nargs="?", default="Find raster datasets in the Tehran area.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true", help="Pattern A: LLM intent then MCP")
    group.add_argument("--loop", action="store_true", help="Pattern B: OpenAI MCP tool loop")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not os.getenv("GEOPACK_API_URL"):
        print("[ERROR] Missing GEOPACK_API_URL")
        raise SystemExit(1)

    if args.staged:
        asyncio.run(_run_staged(args.prompt, args.verbose))
    else:
        asyncio.run(_run_loop(args.prompt, args.verbose))


if __name__ == "__main__":
    main()
