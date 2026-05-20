"""
LangChain + Geopack MCP: tool discovery via langchain-mcp-adapters (stdio) or in-process fallback.

Install: pip install -e ".[langchain]"
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple, Union

from llm_env import create_langchain_chat_model, get_openai_settings

SDK_ROOT = Path(__file__).resolve().parents[2]

GEOPACK_SYSTEM_SIMPLE = (
    "You are a Geoportal assistant. Use Geopack MCP tools to answer the user. "
    "Prefer details_level=lite when listing datasets unless full metadata is required."
)

GEOPACK_SYSTEM_GEOCODE = (
    "You are a Geoportal GIS assistant. When the user mentions a place, city, or region, "
    "you MUST call geopack_sdk_geocode_place first, then use the returned bbox in "
    "geopack_sdk_list_datasets. Use data_type=raster or vector when the user specifies. "
    "Do not invent dataset ids."
)


def sdk_root() -> Path:
    return SDK_ROOT


def geopack_stdio_server_config(
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Connection dict for MultiServerMCPClient (stdio transport)."""
    command, args = _server_command()
    run_env = {**os.environ, **(env or {})}
    return {
        "geopack": {
            "transport": "stdio",
            "command": command,
            "args": args,
            "env": run_env,
            "cwd": str(cwd or SDK_ROOT),
        }
    }


def _server_command() -> Tuple[str, List[str]]:
    venv_python = SDK_ROOT / "venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python), ["-m", "geopack_sdk_mcp"]
    import sys

    return sys.executable, ["-m", "geopack_sdk_mcp"]


def _use_inprocess() -> bool:
    from inprocess_mcp import use_inprocess_mcp

    return use_inprocess_mcp()


def _json_schema_to_pydantic(model_name: str, schema: Dict[str, Any]):
    from pydantic import Field, create_model

    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields: Dict[str, Any] = {}
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, spec in props.items():
        py_type = type_map.get(spec.get("type", "string"), Any)
        if key in required:
            fields[key] = (py_type, Field(description=spec.get("description", "")))
        else:
            fields[key] = (
                Optional[py_type],
                Field(default=None, description=spec.get("description", "")),
            )
    if not fields:
        fields["payload"] = (Optional[dict], Field(default=None))
    return create_model(model_name, **fields)


async def langchain_tools_from_inprocess(session: Any) -> List[Any]:
    """Build LangChain tools from in-process MCP session (Jupyter-safe)."""
    from langchain_core.tools import StructuredTool

    listed = await session.list_tools()
    lc_tools: List[Any] = []

    for spec in listed.tools:
        schema = dict(spec.inputSchema)
        args_model = _json_schema_to_pydantic(
            f"{spec.name.replace('.', '_')}Args",
            schema,
        )
        name = spec.name

        async def _coro(
            _name: str = name,
            _session: Any = session,
            **kwargs: Any,
        ) -> str:
            clean = {k: v for k, v in kwargs.items() if v is not None}
            result = await _session.call_tool(_name, clean)
            return json.dumps(result, default=str)

        lc_tools.append(
            StructuredTool(
                name=name,
                description=spec.description or name,
                coroutine=_coro,
                args_schema=args_model,
            )
        )
    return lc_tools


async def load_geopack_langchain_tools_stdio() -> List[Any]:
    """Discover tools via langchain-mcp-adapters + stdio MCP server."""
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise ImportError('pip install -e ".[langchain]"') from exc

    client = MultiServerMCPClient(geopack_stdio_server_config())
    return await client.get_tools()


async def load_geopack_langchain_tools() -> Tuple[List[Any], str]:
    """
    Load LangChain tools and return (tools, transport_label).

    Uses in-process dispatch in Jupyter; stdio + langchain-mcp-adapters otherwise.
    """
    if _use_inprocess():
        from inprocess_mcp import open_inprocess_session

        session = await open_inprocess_session()
        return await langchain_tools_from_inprocess(session), "inprocess"

    tools = await load_geopack_langchain_tools_stdio()
    return tools, "stdio"


@asynccontextmanager
async def geopack_langchain_tools() -> AsyncIterator[Tuple[List[Any], str]]:
    """Context manager: yields (tools, transport). Keeps in-process session alive."""
    if _use_inprocess():
        from inprocess_mcp import open_inprocess_session

        session = await open_inprocess_session()
        try:
            tools = await langchain_tools_from_inprocess(session)
            yield tools, "inprocess"
        finally:
            pass
        return

    tools = await load_geopack_langchain_tools_stdio()
    try:
        yield tools, "stdio"
    finally:
        pass


def create_geopack_react_agent(
    tools: Sequence[Any],
    *,
    system_prompt: str = GEOPACK_SYSTEM_SIMPLE,
):
    """Single-step ReAct agent with discovered MCP tools."""
    try:
        from langchain.agents import create_agent
    except ImportError as exc:
        raise ImportError('pip install -e ".[langchain]"') from exc

    model = create_langchain_chat_model()
    return create_agent(
        model,
        tools,
        system_prompt=system_prompt,
    )


def build_geocode_then_search_graph(tools: Sequence[Any]):
    """
    LangGraph orchestration: geocode phase (geocode tool only) then search phase (all tools).

    Returns compiled graph. Invoke with {"messages": [("user", prompt)]}.
    """
    try:
        from langchain_core.messages import AIMessage, SystemMessage
        from langgraph.graph import END, START, MessagesState, StateGraph
        from langgraph.prebuilt import ToolNode, tools_condition
    except ImportError as exc:
        raise ImportError('pip install -e ".[langchain]"') from exc

    geocode_tools = [t for t in tools if getattr(t, "name", "") == "geopack_sdk_geocode_place"]
    if not geocode_tools:
        raise RuntimeError("geopack_sdk_geocode_place not in tool list")

    model = create_langchain_chat_model()
    model_geo = model.bind_tools(geocode_tools)
    model_all = model.bind_tools(tools)

    geo_tool_node = ToolNode(geocode_tools)
    all_tool_node = ToolNode(tools)

    def geocode_agent(state: MessagesState) -> Dict[str, Any]:
        sys_msg = SystemMessage(
            content=(
                "Call geopack_sdk_geocode_place for any place mentioned in the user request. "
                "Use a Nominatim-friendly query (e.g. 'Tehran, Iran'). "
                "If no place is mentioned, reply NO_PLACE."
            )
        )
        msgs = [sys_msg] + list(state["messages"])
        response = model_geo.invoke(msgs)
        return {"messages": [response]}

    def after_geocode(state: MessagesState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "geocode_tools"
        return "search_agent"

    def geocode_tools_node(state: MessagesState) -> Dict[str, Any]:
        return geo_tool_node.invoke(state)

    def search_agent(state: MessagesState) -> Dict[str, Any]:
        sys_msg = SystemMessage(content=GEOPACK_SYSTEM_GEOCODE)
        msgs = [sys_msg] + list(state["messages"])
        response = model_all.invoke(msgs)
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("geocode_agent", geocode_agent)
    builder.add_node("geocode_tools", geocode_tools_node)
    builder.add_node("search_agent", search_agent)
    builder.add_node("tools", all_tool_node)

    builder.add_edge(START, "geocode_agent")
    builder.add_conditional_edges(
        "geocode_agent",
        after_geocode,
        {"geocode_tools": "geocode_tools", "search_agent": "search_agent"},
    )
    builder.add_edge("geocode_tools", "search_agent")
    builder.add_conditional_edges("search_agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "search_agent")

    return builder.compile()


async def run_simple_agent(user_prompt: str, *, verbose: bool = False) -> Any:
    async with geopack_langchain_tools() as (tools, transport):
        if verbose:
            print(f"[langchain] transport={transport}, tools={len(tools)}")
            for t in tools:
                print(f"  - {getattr(t, 'name', t)}")
        agent = create_geopack_react_agent(tools, system_prompt=GEOPACK_SYSTEM_GEOCODE)
        return await agent.ainvoke({"messages": user_prompt})


async def run_geocode_graph(user_prompt: str, *, verbose: bool = False) -> Any:
    async with geopack_langchain_tools() as (tools, transport):
        if verbose:
            print(f"[langchain graph] transport={transport}, tools={len(tools)}")
        graph = build_geocode_then_search_graph(tools)
        from langchain_core.messages import HumanMessage

        return await graph.ainvoke({"messages": [HumanMessage(content=user_prompt)]})


def last_ai_text(result: Any) -> str:
    """Extract final assistant text from agent/graph result."""
    messages = result.get("messages") if isinstance(result, dict) else None
    if not messages:
        return str(result)
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        AIMessage = None  # type: ignore[misc, assignment]
        ToolMessage = None  # type: ignore[misc, assignment]

    for msg in reversed(messages):
        if ToolMessage is not None and isinstance(msg, ToolMessage):
            continue
        if AIMessage is not None and isinstance(msg, AIMessage):
            if msg.tool_calls:
                continue
            if msg.content:
                return str(msg.content)
        content = getattr(msg, "content", None)
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if content and role not in ("tool", "ToolMessage"):
            return str(content)
    return str(messages[-1])
