"""Authentication errors with actionable messages for MCP hosts (Cursor, etc.)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AuthCheck:
    """One row in the startup auth checklist."""

    label: str
    ok: bool
    detail: str = ""


class GeopackMCPAuthError(Exception):
    """MCP could not authenticate to the Geoportal API."""

    def __init__(
        self,
        summary: str,
        checks: Optional[List[AuthCheck]] = None,
        fixes: Optional[List[str]] = None,
    ) -> None:
        self.summary = summary
        self.checks = checks or []
        self.fixes = fixes or []
        super().__init__(summary)

    def format_message(self) -> str:
        lines = [
            "",
            "==============================================================",
            "  Geopack SDK MCP - authentication failed",
            "==============================================================",
            "",
            f"  {self.summary}",
            "",
        ]
        if self.checks:
            lines.append("  Checked (first match wins):")
            for check in self.checks:
                mark = "OK" if check.ok else "MISSING"
                line = f"    [{mark}] {check.label}"
                if check.detail:
                    line += f" — {check.detail}"
                lines.append(line)
            lines.append("")
        if self.fixes:
            lines.append("  Fix — choose one:")
            for idx, fix in enumerate(self.fixes, start=1):
                lines.append(f"    {idx}. {fix}")
            lines.append("")
        lines.extend(
            [
                "  Docs: docs/04_development/sdk/mcp_auth_options.md",
                "==============================================================",
                "",
            ]
        )
        return "\n".join(lines)
