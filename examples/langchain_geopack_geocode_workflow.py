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

When the user mentions a city, region, or address:
  1. Call geopack_sdk_geocode_place with a Nominatim-friendly query (e.g. "Tehran, Iran").
  2. Pass the returned bbox [west, south, east, north] to geopack_sdk_list_datasets.

Use data_type "raster" or "vector" when the user specifies. Use start_date/end_date as
ISO YYYY-MM-DD when the user mentions time. Use details_level=lite for lists unless
the user needs full metadata. Do not invent dataset ids.

IMPORTANT:
- ALWAYS use details_level=lite when calling list_datasets
- ALWAYS limit to maximum 5 items unless explicitly asked for more
- Use page_size=5 when listing datasets
- Keep all responses extremely concise
- Only include essential information in your answers"""


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
