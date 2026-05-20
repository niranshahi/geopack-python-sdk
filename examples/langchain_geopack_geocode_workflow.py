#!/usr/bin/env python3
"""
Sample: LangChain agent + Geopack MCP — geocoding then dataset search.

Demonstrates the common GIS pattern:
  1. geopack_sdk_geocode_place("Tehran, Iran")  → bbox
  2. geopack_sdk_list_datasets(bbox=..., data_type="raster", ...)

The LLM chooses tools automatically; the system prompt tells it to geocode first
when the user mentions a place. All tools still come from MCP discovery.

Prerequisites: same as langchain_geopack_agent.py (see examples/README.md).

Usage:
  python examples/langchain_geopack_geocode_workflow.py
  python examples/langchain_geopack_geocode_workflow.py "Rasters near Tehran since 2024"
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

SDK_ROOT = Path(__file__).resolve().parents[1]
if load_dotenv:
    load_dotenv(SDK_ROOT / ".env")
    load_dotenv(SDK_ROOT / "notebooks" / ".env")

GEOCODE_SYSTEM_PROMPT = """You are a Geoportal GIS assistant with Geopack MCP tools.

CRITICAL INSTRUCTIONS:
When the user mentions ANY place name (city, province, country, address):
  1. YOU MUST FIRST CALL: geopack_sdk_geocode_place(query="Place Name, Country")
  2. YOU MUST THEN CALL: geopack_sdk_list_datasets(bbox=[west, south, east, north], ...)
     - YOU MUST PASS THE EXACT bbox FROM geopack_sdk_geocode_place TO geopack_sdk_list_datasets
     - DO NOT OMIT THE bbox PARAMETER

DETAILED EXAMPLE:
User: "Find vector datasets in Tehran"
  → Your first action: geopack_sdk_geocode_place(query="Tehran, Iran")
  → Tool response includes: {"bbox": [51.0892219, 35.5682071, 51.6063007, 35.8284702], ...}
  → YOUR NEXT ACTION MUST BE: geopack_sdk_list_datasets(bbox=[51.0892219, 35.5682071, 51.6063007, 35.8284702], data_type="vector", details_level="lite", page_size=5)
  → YOU ARE NOT ALLOWED TO CALL geopack_sdk_list_datasets WITHOUT THE bbox IN THIS CASE

ANOTHER EXAMPLE:
User: "Rasters near Kerman"
  → First: geopack_sdk_geocode_place(query="Kerman, Iran")
  → Then: geopack_sdk_list_datasets(bbox=[54.3703076, 26.4449954, 59.7254961, 31.9569589], data_type="raster", details_level="lite", page_size=5)

ABSOLUTE RULES:
- ALWAYS use details_level=lite when calling list_datasets
- ALWAYS limit to max 5 items (use page_size=5)
- ALWAYS pass the bbox parameter to list_datasets after geocoding
- NEVER skip the bbox parameter when you have geocode results
- Keep responses concise
- Only include essential information"""


def _mcp_server_command() -> tuple[str, list[str]]:
    venv_python = SDK_ROOT / "venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python), ["-m", "geopack_sdk_mcp"]
    return sys.executable, ["-m", "geopack_sdk_mcp"]


def _chat_model():
    from langchain_openai import ChatOpenAI

    kwargs: dict = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "api_key": os.environ["OPENAI_API_KEY"],
        "temperature": 0,
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    return ChatOpenAI(**kwargs)


async def main(user_prompt: str) -> None:
    from langchain.agents import create_agent
    from langchain_mcp_adapters.client import MultiServerMCPClient

    command, args = _mcp_server_command()
    mcp_client = MultiServerMCPClient(
        {
            "geopack": {
                "transport": "stdio",
                "command": command,
                "args": args,
                "env": dict(os.environ),
                "cwd": str(SDK_ROOT),
            }
        }
    )

    tools = await mcp_client.get_tools()
    print(f"Discovered {len(tools)} tools (including geopack_sdk_geocode_place)")

    llm = _chat_model()
    agent = create_agent(
        llm,
        tools,
        system_prompt=GEOCODE_SYSTEM_PROMPT,
    )

    print("\n--- User ---")
    print(user_prompt)
    result = await agent.ainvoke({"messages": user_prompt})

    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
            print("\n--- Assistant ---")
            print(msg.content)
            return
    print(result)


if __name__ == "__main__":
    if not os.getenv("GEOPACK_API_URL"):
        sys.exit("[ERROR] Set GEOPACK_API_URL")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("[ERROR] Set OPENAI_API_KEY")

    prompt = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Find raster datasets in the Tehran area."
    )
    asyncio.run(main(prompt))
