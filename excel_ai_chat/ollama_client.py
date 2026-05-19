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


def _chat_http_error_message(status_code: int, url: str, body_preview: str, model: str) -> str:
    """Explain chat failures (tags/list can work while chat returns 4xx)."""
    snippet = body_preview.strip()[:600] if body_preview else "(empty body)"
    if status_code == 404:
        return (
            f"HTTP 404 from `{url}`.\n\n"
            "**Why Test connection can still succeed**\n"
            "- **Test connection** uses `GET /api/tags` (list models).\n"
            "- Chat uses `POST /api/chat`. A 404 here usually means a **wrong or missing model "
            f"name** (`{model}`) or the server is **not full Ollama** on that URL.\n\n"
            "**What to try**\n"
            "1. Click **List models** and set **Model** to an **exact** name from the list "
            "(e.g. `llama3.2:latest`, not a typo).\n"
            "2. On the server run `ollama pull <that-name>` if the model is not installed.\n"
            "3. If this is a proxy / gateway, confirm it supports Ollama’s `/api/chat`.\n\n"
            f"Response snippet: `{snippet}`"
        )
    return (
        f"HTTP {status_code} from `{url}`.\n\n"
        f"Model: `{model}`\n"
        f"Response snippet: `{snippet}`"
    )


def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    temperature: float = 0.7,
    timeout_s: float = 120.0,
) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    api_messages = list(messages)
    if system and system.strip():
        api_messages = [
            {"role": "system", "content": system.strip()},
            *[
                m
                for m in messages
                if not (m.get("role") == "system" and isinstance(m.get("content"), str))
            ],
        ]
    payload: dict[str, Any] = {
        "model": model,
        "messages": api_messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                raise RuntimeError(
                    _chat_http_error_message(r.status_code, url, r.text or "", model)
                )
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
