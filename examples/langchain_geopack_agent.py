#!/usr/bin/env python3
"""
Sample: LangChain agent + Geopack SDK MCP (tool auto-discovery).

This is the minimal pattern external developers should copy.
It spawns the Geopack MCP server over stdio (same as Cursor mcp.json) and
loads all geopack_sdk_* tools via langchain-mcp-adapters.

Prerequisites:
  pip install "geopack-sdk[mcp,langchain]"
  Geoportal API running
  .env with GEOPACK_* and OPENAI_* (see examples/README.md)

Usage:
  cd python-sdk
  python examples/langchain_geopack_agent.py
  python examples/langchain_geopack_agent.py "List my raster datasets"
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Load environment (Geopack API + OpenAI)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

SDK_ROOT = Path(__file__).resolve().parents[1]
if load_dotenv:
    load_dotenv(SDK_ROOT / ".env")
    load_dotenv(SDK_ROOT / "notebooks" / ".env")


def _mcp_server_command() -> tuple[str, list[str]]:
    """Python executable that runs geopack-sdk-mcp (use your venv if needed)."""
    venv_python = SDK_ROOT / "venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python), ["-m", "geopack_sdk_mcp"]
    return sys.executable, ["-m", "geopack_sdk_mcp"]


def _chat_model():
    """OpenAI-compatible chat model from OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL."""
    from langchain_openai import ChatOpenAI

    api_key = os.environ["OPENAI_API_KEY"]
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    kwargs: dict = {"model": model, "api_key": api_key, "temperature": 0}
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    return ChatOpenAI(**kwargs)


async def main(user_prompt: str) -> None:
    # -----------------------------------------------------------------------
    # 2. Connect to Geopack MCP server (stdio) and discover tools
    # -----------------------------------------------------------------------
    from langchain.agents import create_agent
    from langchain_mcp_adapters.client import MultiServerMCPClient

    command, args = _mcp_server_command()
    print(f"MCP server: {command} {' '.join(args)}")
    print(f"Geopack API: {os.getenv('GEOPACK_API_URL', '(not set)')}")

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

    # Tools are discovered from the running MCP server — same names as in Cursor
    tools = await mcp_client.get_tools()
    print(f"Discovered {len(tools)} MCP tools:")
    for tool in tools:
        print(f"  - {tool.name}")

    # -----------------------------------------------------------------------
    # 3. Build LangChain ReAct agent and run user prompt
    # -----------------------------------------------------------------------
    from langchain.agents.middleware import AgentMiddleware

    # Custom middleware to trim tool outputs to prevent 413 errors
    class TrimToolOutputsMiddleware(AgentMiddleware):
        async def awrap_model_call(self, request, next_fn):
            # ModelRequest object has 'messages' attribute, not .get()
            messages = request.messages if hasattr(request, 'messages') else []
            for msg in messages:
                if hasattr(msg, "content") and isinstance(msg.content, str):
                    # Trim large tool outputs to prevent token overflow
                    if len(msg.content) > 2000:
                        msg.content = msg.content[:2000] + "... [truncated]"
            return await next_fn(request)

    llm = _chat_model()
    agent = create_agent(
        llm,
        tools,
        system_prompt=(
            "You are a Geoportal assistant. Use the Geopack MCP tools to answer "
            "the user. Prefer details_level=lite when listing datasets."
        ),
        middleware=[TrimToolOutputsMiddleware()],
    )

    print("\n--- User ---")
    print(user_prompt)
    result = await agent.ainvoke({"messages": user_prompt})

    # -----------------------------------------------------------------------
    # 4. Print assistant reply
    # -----------------------------------------------------------------------
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
            print("\n--- Assistant ---")
            print(msg.content)
            return
    print("\n--- Result ---")
    print(result)


if __name__ == "__main__":
    if not os.getenv("GEOPACK_API_URL"):
        sys.exit("[ERROR] Set GEOPACK_API_URL in .env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("[ERROR] Set OPENAI_API_KEY in .env")

    prompt = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Find raster datasets in the Tehran area."
    )
    asyncio.run(main(prompt))
