"""Load ``GEOPACK_*`` variables from ``python-sdk/.env`` (CLI, notebooks, MCP)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# python-sdk/src/geopack_sdk/env_loader.py -> parents[2] == python-sdk/
_SDK_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = _SDK_ROOT / ".env"


def sdk_root_dir() -> Path:
    """Absolute path to the ``python-sdk`` package root (contains ``.env``, ``pyproject.toml``)."""
    return _SDK_ROOT


def load_geopack_env() -> Optional[Path]:
    """Load dotenv files for local development.

    Order:
      1. Current working directory ``.env`` (``load_dotenv()`` default)
      2. ``python-sdk/.env`` next to the installed package source tree

    Returns the path that was loaded, or ``None`` if nothing was loaded.

    MCP: set ``GEOPACK_MCP_SKIP_DOTENV=1`` in ``mcp.json`` to skip this entirely.
    """
    if os.getenv("GEOPACK_MCP_SKIP_DOTENV", "").lower() in ("1", "true", "yes"):
        return None

    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    if load_dotenv():
        return Path.cwd() / ".env"

    if DEFAULT_ENV_FILE.is_file():
        load_dotenv(DEFAULT_ENV_FILE)
        return DEFAULT_ENV_FILE

    return None
