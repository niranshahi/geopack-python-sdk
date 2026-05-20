"""
Shared LLM environment (OpenAI-compatible) for notebooks and test scripts.

Uses the same variables as Cursor / test_mcp_llm_prompt.py:
  OPENAI_API_KEY, OPENAI_BASE_URL (optional), OPENAI_MODEL (optional)
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def get_openai_settings() -> Dict[str, Optional[str]]:
    return {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL") or None,
        "model": os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
    }


def require_openai_api_key() -> str:
    key = get_openai_settings()["api_key"]
    if not key:
        raise ValueError(
            "Missing OPENAI_API_KEY. Set it in python-sdk/.env or notebooks/.env"
        )
    return key


def create_openai_sdk_client(
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """Raw OpenAI Python SDK client (used by mcp_llm.py)."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError('pip install openai (or pip install -e ".[llm]")') from exc

    settings = get_openai_settings()
    key = api_key or settings["api_key"]
    if not key:
        raise ValueError("Missing OPENAI_API_KEY")

    url = base_url if base_url is not None else settings["base_url"]
    kwargs: Dict[str, Any] = {"api_key": key}
    if url:
        kwargs["base_url"] = url.rstrip("/")
    return OpenAI(**kwargs)


def create_langchain_chat_model(
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0,
):
    """LangChain ChatOpenAI configured from environment."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ImportError(
            'pip install -e ".[langchain]" (langchain-openai, langchain-mcp-adapters, langgraph)'
        ) from exc

    settings = get_openai_settings()
    key = api_key or settings["api_key"]
    if not key:
        raise ValueError("Missing OPENAI_API_KEY")

    model_name = model or settings["model"] or DEFAULT_OPENAI_MODEL
    url = base_url if base_url is not None else settings["base_url"]

    kwargs: Dict[str, Any] = {
        "model": model_name,
        "api_key": key,
        "temperature": temperature,
    }
    if url:
        kwargs["base_url"] = url.rstrip("/")
    return ChatOpenAI(**kwargs)


def langchain_model_id() -> str:
    """Model id string for create_agent when a string is required."""
    settings = get_openai_settings()
    model = settings["model"] or DEFAULT_OPENAI_MODEL
    if settings["base_url"]:
        return model
    return f"openai:{model}"
