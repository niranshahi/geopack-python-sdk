"""
Rich dataset list display for notebooks (HTML table + thumbnail images).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from IPython.display import HTML, display


def _img_data_uri(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


async def fetch_thumbnail_path(
    session: Any,
    dataset_id: int,
    *,
    save_dir: Path,
) -> Optional[Path]:
    """Call MCP thumbnail tool via in-process session; return local PNG path."""
    save_dir.mkdir(parents=True, exist_ok=True)
    target = save_dir / f"dataset_{dataset_id}_thumbnail.png"
    result = await session.call_tool(
        "geopack_sdk_get_dataset_thumbnail",
        {"dataset_id": dataset_id, "save_path": str(target)},
    )
    if isinstance(result, dict) and result.get("error"):
        return None
    saved = result.get("savedPath") if isinstance(result, dict) else None
    if saved and Path(saved).is_file():
        return Path(saved)
    if target.is_file():
        return target
    return None


def datasets_to_html_table(
    datasets: List[Dict[str, Any]],
    *,
    thumb_paths: Optional[Dict[int, Path]] = None,
    max_rows: int = 12,
) -> str:
    """Build an HTML table with optional thumbnail column."""
    thumb_paths = thumb_paths or {}
    head = """
    <style>
    .gp-ds-table { border-collapse: collapse; font-family: system-ui, sans-serif; font-size: 14px; }
    .gp-ds-table th, .gp-ds-table td { border: 1px solid #ccc; padding: 8px 12px; vertical-align: middle; }
    .gp-ds-table th { background: #f0f4f8; text-align: left; }
    .gp-ds-table tr:nth-child(even) { background: #fafafa; }
    .gp-ds-thumb { max-width: 140px; max-height: 100px; border-radius: 4px; }
    .gp-ds-none { color: #888; font-size: 12px; }
    </style>
    <table class="gp-ds-table">
    <thead><tr>
      <th>Preview</th><th>ID</th><th>Name</th><th>Type</th><th>Updated</th>
    </tr></thead><tbody>
    """
    rows_html: List[str] = []
    for row in datasets[:max_rows]:
        did = row.get("id")
        name = row.get("name") or "—"
        dtype = row.get("dataType") or row.get("data_type") or "—"
        updated = row.get("updatedAt") or row.get("updated_at") or "—"
        thumb_cell = '<span class="gp-ds-none">—</span>'
        if did is not None and did in thumb_paths:
            uri = _img_data_uri(thumb_paths[did])
            if uri:
                thumb_cell = f'<img class="gp-ds-thumb" src="{uri}" alt="dataset {did}"/>'
        elif row.get("hasThumbnail"):
            thumb_cell = '<span class="gp-ds-none">(fetch failed)</span>'
        rows_html.append(
            f"<tr><td>{thumb_cell}</td><td>{did}</td><td>{name}</td>"
            f"<td>{dtype}</td><td>{updated}</td></tr>"
        )
    foot = "</tbody></table>"
    if len(datasets) > max_rows:
        foot += f"<p><em>Showing {max_rows} of {len(datasets)} datasets.</em></p>"
    return head + "\n".join(rows_html) + foot


async def display_datasets_rich(
    datasets: List[Dict[str, Any]],
    mcp_session: Any,
    *,
    thumb_dir: Optional[Path] = None,
    max_rows: int = 8,
    fetch_thumbnails: bool = True,
) -> None:
    """
    Show HTML table + inline PNG thumbnails (requires in-process mcp_session).
    """
    if not datasets:
        display(HTML("<p><em>No datasets in tool output.</em></p>"))
        return

    thumb_paths: Dict[int, Path] = {}
    if fetch_thumbnails and mcp_session is not None:
        save_dir = thumb_dir or Path("downloads") / "notebook_thumbnails"
        for row in datasets[:max_rows]:
            did = row.get("id")
            if did is None:
                continue
            if not row.get("hasThumbnail"):
                continue
            path = await fetch_thumbnail_path(mcp_session, int(did), save_dir=save_dir)
            if path:
                thumb_paths[int(did)] = path

    html = datasets_to_html_table(datasets, thumb_paths=thumb_paths, max_rows=max_rows)
    display(HTML(html))


def print_tool_trace(messages: List[Any], max_tools: int = 8) -> None:
    """Print MCP tool calls from agent message history (educational)."""
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        print("(langchain_core not available)")
        return

    print("--- Tool trace ---")
    n = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                n += 1
                if n > max_tools:
                    return
                if isinstance(tc, dict):
                    name = tc.get("name", "?")
                    args = tc.get("args", {})
                else:
                    name = getattr(tc, "name", "?")
                    args = getattr(tc, "args", None) or {}
                print(f"  → {name}({json.dumps(args, default=str)[:200]})")
        if isinstance(msg, ToolMessage):
            preview = (msg.content or "")[:120]
            print(f"    ← {preview}...")

