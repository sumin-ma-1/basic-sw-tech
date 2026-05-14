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
        f"Ollama에 연결하지 못했습니다: `{base_url}`\n\n"
        "**가능한 원인**\n"
        "- 이 PC에서 **Ollama가 실행 중이 아님** (기본 주소 `http://127.0.0.1:11434`).\n"
        "- Base URL이 잘못됨 (다른 머신이면 `http://IP주소:11434` 등).\n"
        "- 방화벽이 **11434** 포트를 차단함.\n\n"
        "**조치**\n"
        "1. [Ollama](https://ollama.com) 설치 후 앱을 실행하거나, 터미널에서 `ollama serve`가 떠 있는지 확인합니다.\n"
        "2. `ollama pull <모델명>` 으로 모델을 받은 뒤, 사이드바의 모델 이름과 맞춥니다.\n"
        "3. 원격 GPU 서버를 쓰는 경우 그 서버의 Ollama 주소로 Base URL을 바꿉니다."
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
