"""
Notebook helpers: OpenAI + real Geopack MCP tools over stdio (same tools as Cursor).

Tool schemas come from session.list_tools() — not duplicated in geopack_sdk.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

SDK_ROOT = Path(__file__).resolve().parents[2]

STAGE_A_SYSTEM = """You extract dataset search intent from the user message.
Reply with JSON only (no markdown), using this schema:
{
  "place_query": string or null,
  "data_type": "vector" | "raster" | null,
  "start_date": "YYYY-MM-DD" or null,
  "end_date": "YYYY-MM-DD" or null,
  "search_query": string or null,
  "page_size": number
}
If the user mentions a city, region, or address, set place_query to a Nominatim-friendly query (e.g. "Tehran, Iran").
Default page_size to 20 if not specified."""

LOOP_SYSTEM = """You are a Geoportal assistant with MCP tools.
When the user mentions a place or area, call geopack_sdk_geocode_place first, then pass bbox to geopack_sdk_list_datasets.
Use details_level=lite for list unless the user needs full metadata.
Do not invent dataset ids."""

from llm_env import (  # noqa: E402
    DEFAULT_OPENAI_MODEL,
    create_openai_sdk_client,
    get_openai_settings,
)


def sdk_root() -> Path:
    return SDK_ROOT


def server_command() -> Tuple[str, List[str]]:
    venv_python = SDK_ROOT / "venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python), ["-m", "geopack_sdk_mcp"]
    import sys

    return sys.executable, ["-m", "geopack_sdk_mcp"]


def tool_result_payload(result: Any) -> Any:
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


def create_openai_client(
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """OpenAI SDK client (see llm_env.create_openai_sdk_client)."""
    return create_openai_sdk_client(api_key=api_key, base_url=base_url)


def mcp_tools_to_openai(listed_tools: Any) -> List[Dict[str, Any]]:
    """Map MCP list_tools() output to OpenAI chat tools format."""
    openai_tools: List[Dict[str, Any]] = []
    for tool in listed_tools.tools:
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "parameters", None)
        if hasattr(schema, "model_dump"):
            parameters = schema.model_dump(by_alias=True, exclude_none=True)
        elif isinstance(schema, dict):
            parameters = schema
        else:
            parameters = {"type": "object", "properties": {}}
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters,
                },
            }
        )
    return openai_tools


def _parse_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def mcp_transport_mode() -> str:
    """Return ``inprocess`` (Jupyter) or ``stdio`` (CLI / terminal)."""
    from inprocess_mcp import use_inprocess_mcp

    return "inprocess" if use_inprocess_mcp() else "stdio"


@asynccontextmanager
async def mcp_session(
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    transport: Optional[str] = None,
) -> AsyncIterator[Any]:
    """
    MCP tool session.

    - **inprocess** (default in Jupyter): same handlers as geopack-sdk-mcp, no subprocess.
    - **stdio** (default in terminal): spawns ``python -m geopack_sdk_mcp`` like Cursor.

    Override with ``GEOPACK_MCP_MODE=inprocess|stdio`` or ``transport=`` argument.
    """
    mode = (transport or os.getenv("GEOPACK_MCP_MODE") or "").strip().lower()
    if not mode:
        from inprocess_mcp import use_inprocess_mcp

        mode = "inprocess" if use_inprocess_mcp() else "stdio"
    elif mode in ("in-process",):
        mode = "inprocess"

    if mode == "inprocess":
        from inprocess_mcp import open_inprocess_session

        session = await open_inprocess_session()
        try:
            yield session
        finally:
            pass
        return

    if mode != "stdio":
        raise ValueError(f"Unknown MCP transport: {mode!r} (use inprocess or stdio)")

    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    command, args = server_command()
    run_env = {**os.environ, **(env or {})}
    params = StdioServerParameters(
        command=command,
        args=args,
        env=run_env,
        cwd=str(cwd or SDK_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_mcp_tool(session: Any, name: str, arguments: Dict[str, Any]) -> Any:
    if hasattr(session, "_client"):
        return await session.call_tool(name, arguments)
    result = await session.call_tool(name, arguments)
    return tool_result_payload(result)


async def deterministic_geocode_and_list(
    session: Any,
    *,
    place_query: str = "Tehran, Iran",
    data_type: str = "raster",
    start_date: Optional[str] = "2024-01-01",
    page_size: int = 10,
) -> Dict[str, Any]:
    """No LLM: geocode then list (same as test_mcp_stdio_client steps 2–3)."""
    geo = await call_mcp_tool(
        session, "geopack_sdk_geocode_place", {"query": place_query}
    )
    if isinstance(geo, dict) and geo.get("error"):
        return {"geocode": geo, "list": None}

    list_args: Dict[str, Any] = {
        "page": 1,
        "page_size": page_size,
        "details_level": "lite",
        "bbox": geo.get("bbox") if isinstance(geo, dict) else None,
    }
    if data_type:
        list_args["data_type"] = data_type
    if start_date:
        list_args["start_date"] = start_date

    listed = await call_mcp_tool(session, "geopack_sdk_list_datasets", list_args)
    return {"geocode": geo, "list": listed}


async def staged_dataset_search(
    session: Any,
    openai_client: Any,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Pattern A: LLM extracts JSON intent → MCP geocode → MCP list_datasets.
    """
    settings = get_openai_settings()
    model_name = model or settings["model"] or DEFAULT_OPENAI_MODEL

    completion = openai_client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": STAGE_A_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    raw = completion.choices[0].message.content or "{}"
    if verbose:
        print("[stage A] intent JSON:", raw)

    intent = _parse_json_object(raw)
    place_query = intent.get("place_query")
    page_size = int(intent.get("page_size") or 20)

    geocode_result = None
    if place_query:
        geocode_result = await call_mcp_tool(
            session,
            "geopack_sdk_geocode_place",
            {"query": str(place_query)},
        )
        if verbose:
            print("[stage B] geocode:", geocode_result)

    list_args: Dict[str, Any] = {
        "page": 1,
        "page_size": page_size,
        "details_level": "lite",
    }
    if intent.get("data_type"):
        list_args["data_type"] = intent["data_type"]
    if intent.get("start_date"):
        list_args["start_date"] = intent["start_date"]
    if intent.get("end_date"):
        list_args["end_date"] = intent["end_date"]
    if intent.get("search_query"):
        list_args["search_query"] = intent["search_query"]
    if isinstance(geocode_result, dict) and geocode_result.get("bbox"):
        list_args["bbox"] = geocode_result["bbox"]

    list_result = await call_mcp_tool(session, "geopack_sdk_list_datasets", list_args)
    if verbose:
        print("[stage C] list_datasets done")

    return {
        "intent": intent,
        "geocode": geocode_result,
        "list": list_result,
        "assistant_text": None,
    }


async def run_mcp_tool_loop(
    session: Any,
    openai_client: Any,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    max_rounds: int = 8,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Pattern B: OpenAI tool loop dispatching to real MCP tools (like Cursor Agent).
    """
    settings = get_openai_settings()
    model_name = model or settings["model"] or DEFAULT_OPENAI_MODEL

    listed = await session.list_tools()
    tools = mcp_tools_to_openai(listed)
    if verbose:
        print(f"[loop] {len(tools)} MCP tools:", [t["function"]["name"] for t in tools])

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": LOOP_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    tool_trace: List[Dict[str, Any]] = []

    for round_idx in range(max_rounds):
        completion = openai_client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
            temperature=0,
        )
        choice = completion.choices[0].message
        if choice.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in choice.tool_calls
                    ],
                }
            )
            for tc in choice.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                if verbose:
                    print(f"[loop round {round_idx + 1}] {fn_name}({fn_args})")
                result = await call_mcp_tool(session, fn_name, fn_args)
                tool_trace.append({"tool": fn_name, "arguments": fn_args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            continue

        text = choice.content or ""
        if verbose:
            print(f"[loop] final answer ({round_idx + 1} rounds)")
        return {
            "assistant_text": text,
            "tool_trace": tool_trace,
            "messages": messages,
        }

    return {
        "assistant_text": None,
        "tool_trace": tool_trace,
        "error": f"max_rounds ({max_rounds}) exceeded",
    }


def run_async(coro: Any) -> Any:
    """Run async helper from sync notebook cells."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Use await in an async notebook cell, or nest_asyncio.apply()")
