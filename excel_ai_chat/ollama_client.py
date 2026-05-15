"""Minimal Ollama HTTP client (non-streaming for simpler Streamlit integration)."""

from __future__ import annotations

from typing import Any

import httpx


def explain_connection_error(base_url: str, exc: BaseException) -> str:
    """Human-readable hint when Ollama is unreachable (e.g. WinError 10061)."""
    raw = str(exc).lower()
    refused = (
        "10061" in str(exc)
        or "actively refused" in raw
        or "connection refused" in raw
        or isinstance(exc, httpx.ConnectError)
        or isinstance(exc, ConnectionRefusedError)
    )
    if not refused:
        return str(exc)
    return (
        f"Could not connect to Ollama at `{base_url}`.\n\n"
        "**Likely causes**\n"
        "- **Ollama is not running** on this machine (default `http://127.0.0.1:11434`).\n"
        "- **Wrong Base URL** (for a remote host use `http://<host-ip>:11434`, etc.).\n"
        "- **Firewall** blocking port **11434**.\n\n"
        "**What to do**\n"
        "1. Install [Ollama](https://ollama.com), start the app, or ensure `ollama serve` is running.\n"
        "2. Run `ollama pull <model>` and match the **Model name** in the sidebar.\n"
        "3. If Ollama runs on another machine/GPU server, set Base URL to that server’s address."
    )


def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    timeout_s: float = 120.0,
) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
    except (httpx.ConnectError, ConnectionRefusedError, OSError) as e:
        raise RuntimeError(explain_connection_error(base_url, e)) from e
    msg = data.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"Unexpected Ollama response: {data!r}")
    return content


def list_models(base_url: str, *, timeout_s: float = 15.0) -> list[str]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except (httpx.ConnectError, ConnectionRefusedError, OSError) as e:
        raise RuntimeError(explain_connection_error(base_url, e)) from e
    models = data.get("models") or []
    names: list[str] = []
    for m in models:
        if isinstance(m, dict) and isinstance(m.get("name"), str):
            names.append(m["name"])
    return sorted(names)
