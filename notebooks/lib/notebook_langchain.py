"""
Jupyter helpers: LangChain + Geopack MCP (in-process or stdio) without asyncio.run().
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

SDK_ROOT = Path(__file__).resolve().parents[2]


def setup_notebook_paths() -> Path:
    sys.path.insert(0, str(SDK_ROOT / "src"))
    sys.path.insert(0, str(SDK_ROOT / "notebooks" / "lib"))
    return SDK_ROOT


def load_env(sdk_root: Path) -> None:
    from dotenv import load_dotenv

    load_dotenv(sdk_root / "notebooks" / ".env")
    load_dotenv(sdk_root / ".env")


def mcp_server_command() -> Tuple[str, List[str]]:
    venv_python = SDK_ROOT / "venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python), ["-m", "geopack_sdk_mcp"]
    return sys.executable, ["-m", "geopack_sdk_mcp"]


def geopack_stdio_config() -> Dict[str, Any]:
    command, args = mcp_server_command()
    return {
        "geopack": {
            "transport": "stdio",
            "command": command,
            "args": args,
            "env": dict(os.environ),
            "cwd": str(SDK_ROOT),
        }
    }


@asynccontextmanager
async def notebook_mcp_langchain_tools() -> AsyncIterator[Tuple[List[Any], Any, str]]:
    """
    Yields (langchain_tools, mcp_session_or_none, transport).

    Jupyter uses in-process MCP (no stdio subprocess). Terminal can set GEOPACK_MCP_MODE=stdio.
    """
    from inprocess_mcp import open_inprocess_session, use_inprocess_mcp
    from langchain_mcp import langchain_tools_from_inprocess

    if use_inprocess_mcp():
        session = await open_inprocess_session()
        tools = await langchain_tools_from_inprocess(session)
        try:
            yield tools, session, "inprocess"
        finally:
            pass
        return

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(geopack_stdio_config())
    tools = await client.get_tools()
    yield tools, None, "stdio"


def create_chat_model():
    from llm_env import create_langchain_chat_model

    return create_langchain_chat_model()


def extract_list_datasets_from_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """Collect dataset rows from geopack_sdk_list_datasets tool outputs in agent history."""
    rows: List[Dict[str, Any]] = []
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        ToolMessage = None  # type: ignore[misc, assignment]

    for msg in messages or []:
        if ToolMessage is None or not isinstance(msg, ToolMessage):
            continue
        raw = getattr(msg, "content", None)
        if not raw:
            continue
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("error"):
            continue
        datasets = payload.get("datasets")
        if isinstance(datasets, list):
            rows.extend(datasets)
    return rows


def last_assistant_text(result: Dict[str, Any]) -> str:
    messages = result.get("messages", [])
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        return str(result)

    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            return str(msg.content)
    return "(no text reply)"


SIMPLE_SYSTEM_PROMPT = """You are a Geoportal assistant. Use the Geopack MCP tools to answer the user.

IMPORTANT RULES:
- ALWAYS use details_level=lite when calling list_datasets
- ALWAYS limit to maximum 5 items unless explicitly asked for more
- Use page_size=5 when listing datasets
- Keep all responses extremely concise
- Only include essential information in your answers"""


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
