# Geopack MCP — Python agent examples

Sample code for building an **LLM agent in Python** that uses **Geopack SDK MCP** tools (`geopack_sdk_*`).

Same MCP server as Cursor (`geopack-sdk-mcp`). Tools are **discovered automatically** via [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) — you do not define tool schemas yourself.

## Prerequisites

1. Geoportal API running (e.g. `http://localhost:3000/api`).
2. Install:

```bash
pip install "geopack-sdk[mcp,langchain]"
```

3. Environment (`.env` in `python-sdk/` or export):

```env
GEOPACK_API_URL=http://localhost:3000/api
GEOPACK_USERNAME=your_user
GEOPACK_PASSWORD=your_password

OPENAI_API_KEY=sk-...
# Optional — OpenAI-compatible providers:
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

## Examples

| File | What it shows |
|------|----------------|
| [`langchain_geopack_agent.py`](langchain_geopack_agent.py) | **Start here.** One ReAct agent; MCP tools discovered via stdio; user prompt in natural language. |
| [`langchain_geopack_geocode_workflow.py`](langchain_geopack_geocode_workflow.py) | Geocode → list workflow: agent with MCP tools; system prompt requires `geopack_sdk_geocode_place` before spatial list. |

## Run

From `python-sdk/` (with venv activated):

```bash
python examples/langchain_geopack_agent.py
python examples/langchain_geopack_agent.py "List raster datasets overlapping Tehran"

python examples/langchain_geopack_geocode_workflow.py
```

## How it works

```text
Your Python script
    → langchain-mcp-adapters MultiServerMCPClient (stdio)
    → spawns: python -m geopack_sdk_mcp   (same as Cursor mcp.json)
    → list_tools / call_tool
    → Geopack REST API
```

## Cursor vs Python

| | Cursor | These examples |
|--|--------|----------------|
| MCP host | Cursor IDE | Your Python process |
| Tool discovery | Cursor | `await client.get_tools()` |
| LLM | Cursor model settings | `OPENAI_*` env vars |

## Jupyter (educational notebooks)

| Notebook | Content |
|----------|---------|
| `notebooks/09_LangChain_MCP_Simple.ipynb` | Step-by-step agent + HTML/thumbnail results |
| `notebooks/10_LangChain_MCP_Geocode_Graph.ipynb` | Geocode → list workflow + rich display |

Notebooks use **in-process** MCP (no `asyncio.run`). Terminal scripts use stdio + `MultiServerMCPClient` as shown above.

## More docs

- [LangChain + MCP agents design](../../docs/09-sdk/mcp-design/langchain-integration.md)
- [Geopack SDK MCP design](../../docs/09-sdk/mcp-design/mcp-architecture.md)
