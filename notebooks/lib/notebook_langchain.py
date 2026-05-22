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
- ALWAYS use include_params=true when getting workflow definition (parameters[] replaces graphJson in MCP output)
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
