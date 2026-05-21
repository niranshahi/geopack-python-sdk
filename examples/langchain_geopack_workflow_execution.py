#!/usr/bin/env python3
"""
Sample: LangChain agent + Geopack MCP — Execute workflow on dataset.

Demonstrates the workflow execution pattern:
  1. User specifies: "Execute [WORKFLOW] on dataset [ID]"
  2. LLM agent automatically:
     - Gets dataset metadata (columns, geometry, etc.)
     - Finds and retrieves workflow definition + parameters
     - Extracts parameter values from dataset metadata
     - Submits workflow with auto-mapped parameters
     - Waits for completion
     - Shows results (output dataset/files)

This is different from direct SDK usage: the LLM intelligently maps dataset
metadata to workflow parameters. No hardcoding needed.

Prerequisites:
  pip install "geopack-sdk[mcp,langchain]"
  Geoportal API running
  .env with GEOPACK_* and OPENAI_* (see examples/README.md)

Usage:
  cd python-sdk
  python examples/langchain_geopack_workflow_execution.py
  python examples/langchain_geopack_workflow_execution.py "Execute X/Y to Point on dataset 2421"
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

WORKFLOW_EXECUTION_SYSTEM_PROMPT = """You are a Geoportal workflow execution assistant with Geopack MCP tools.

Your job: Execute a workflow on a dataset by extracting parameter values from dataset metadata.

WORKFLOW EXECUTION PATTERN:
When user requests: "Execute [WORKFLOW_NAME] workflow on dataset [DATASET_ID]"

YOU MUST FOLLOW THIS EXACT SEQUENCE:

  STEP 1 — Get dataset metadata (to extract parameter values from it):
    → geopack_sdk_get_dataset(dataset_id={DATASET_ID}, details_level="full")
    → Extract metadata: column names, geometry type, CRS, extent, feature count, etc.

  STEP 2 — Find and get workflow definition:
    → geopack_sdk_list_workflows(search_query="{WORKFLOW_NAME}")  
    → Find the correct workflow ID from results
    → geopack_sdk_get_workflow(workflow_id={ID}, include_params=true)
    → Extract workflow parameters and their types (e.g., "input_field", "output_field", "input_layer")

  STEP 3 — Map dataset metadata to workflow parameters:
    → Analyze the dataset columns, geometry, and workflow parameters
    → Build a params dict: {"param_key_1": "extracted_value_1", "param_key_2": "extracted_value_2", ...}
    → Example: If workflow needs "x_column" and "y_column", extract from dataset columns

  STEP 4 — Submit workflow with extracted parameters:
    → geopack_sdk_submit_workflow(workflow_id={ID}, params={mapped_params})
    → This returns taskId and workflowRunId
    → Save these IDs for polling

  STEP 5 — Wait for completion:
    → geopack_sdk_wait_for_task(task_id={TASKID}, timeout=600)
    → Poll and wait until status = "completed" or "failed"

  STEP 6 — Inspect results:
    → geopack_sdk_get_workflow_run(run_id={RUN_ID})
    → Check artifacts: output datasets or files
    → Display results

CRITICAL RULES:
- ALWAYS use details_level="full" when getting dataset (need full column info)
- ALWAYS use include_params=true when getting workflow definition
- NEVER guess parameter values — extract them from dataset metadata
- ALWAYS wait for task completion before showing results
- If output has artifactId, optionally download it: geopack_sdk_download_workflow_artifact()
- Keep responses clear: show what dataset you chose, what workflow, what parameters were mapped
- Only include essential information

EXAMPLE TRACE:
User: "Run X/Y to Point on dataset 2421"
  1. geopack_sdk_get_dataset(2421, details_level="full")
  2. (extract columns from metadata)
  3. geopack_sdk_list_workflows(search_query="X/Y to Point")
  4. geopack_sdk_get_workflow(workflow_id=123, include_params=true)
  5. (extract params like "x_field", "y_field", "output_field")
  6. geopack_sdk_submit_workflow(123, {"x_field": "x_col", "y_field": "y_col", ...})
  7. geopack_sdk_wait_for_task(task_id=999, timeout=600)
  8. geopack_sdk_get_workflow_run(run_id=555)
  9. Display: "✓ Workflow completed. Output dataset ID: 9999"
"""


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
    # 1. Connect to Geopack MCP server (stdio) and discover tools
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

    # Tools are discovered from the running MCP server
    tools = await mcp_client.get_tools()
    print(f"Discovered {len(tools)} MCP tools:")
    for tool in tools:
        if any(kw in tool.name.lower() for kw in ["workflow", "submit", "dataset", "wait"]):
            print(f"  - {tool.name} ⭐")
        else:
            print(f"  - {tool.name}")

    # -----------------------------------------------------------------------
    # 2. Build LangChain ReAct agent with workflow execution system prompt
    # -----------------------------------------------------------------------
    llm = _chat_model()
    agent = create_agent(
        llm,
        tools,
        system_prompt=WORKFLOW_EXECUTION_SYSTEM_PROMPT,
    )

    print("\n--- User ---")
    print(user_prompt)
    result = await agent.ainvoke({"messages": user_prompt})

    # -----------------------------------------------------------------------
    # 3. Print assistant reply
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
        else "Execute X/Y to Point workflow on dataset 2421."
    )
    asyncio.run(main(prompt))
