"""Persist hub conversations as JSON under outputs/chats/."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from excel_ai_chat.excel_chat_files import delete_chat_workspace
from excel_ai_chat.paths import chats_dir

_MODE_CHAT = "chat"
_MODE_EXCEL = "excel"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def chat_file_path(chat_id: str) -> Path:
    return chats_dir() / f"{chat_id}.json"


def _last_active_path(mode: str) -> Path:
    return chats_dir() / f"_last_{mode}.txt"


def get_last_active_id(mode: str) -> str | None:
    path = _last_active_path(mode)
    if not path.is_file():
        return None
    try:
        chat_id = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return chat_id if chat_id and load_conversation(chat_id) else None


def set_last_active_id(mode: str, chat_id: str) -> None:
    _last_active_path(mode).write_text(chat_id, encoding="utf-8")


def clear_last_active_id(mode: str) -> None:
    path = _last_active_path(mode)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def create_conversation_id() -> str:
    return str(uuid.uuid4())


def public_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop hidden / system rows; keep only user and assistant turns for storage."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.get("_hidden"):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        row: dict[str, Any] = {"role": str(role), "content": str(m.get("content", ""))}
        att = m.get("attached_files")
        if isinstance(att, list) and att:
            row["attached_files"] = [str(x) for x in att]
        out.append(row)
    return out


def title_from_messages(messages: list[dict[str, Any]]) -> str:
    for m in messages:
        if m.get("role") == "user" and not m.get("_hidden"):
            text = str(m.get("content", "")).strip().replace("\n", " ")
            if text:
                return text[:60] + ("…" if len(text) > 60 else "")
    return "New chat"


def list_conversations(*, mode: str | None = None) -> list[dict[str, Any]]:
    """Summaries newest first."""
    root = chats_dir()
    rows: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if mode is not None and data.get("mode") != mode:
            continue
        cid = str(data.get("id") or path.stem)
        rows.append(
            {
                "id": cid,
                "title": str(data.get("title") or title_from_messages(data.get("messages", []))),
                "mode": str(data.get("mode") or _MODE_CHAT),
                "updated_at": str(data.get("updated_at") or ""),
                "created_at": str(data.get("created_at") or ""),
                "message_count": len(data.get("messages") or []),
                "excel_file_names": list(data.get("excel_file_names") or []),
            }
        )
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return rows


def load_conversation(chat_id: str) -> dict[str, Any] | None:
    path = chat_file_path(chat_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("id", chat_id)
    msgs = data.get("messages")
    if not isinstance(msgs, list):
        data["messages"] = []
    return data


def save_conversation(
    chat_id: str,
    *,
    mode: str,
    messages: list[dict[str, Any]],
    model: str,
    temperature: float,
    excel_file_names: list[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    path = chat_file_path(chat_id)
    existing: dict[str, Any] = {}
    if path.is_file():
        loaded = load_conversation(chat_id)
        if loaded:
            existing = loaded
    stored = public_messages(messages)
    now = _now_iso()
    payload: dict[str, Any] = {
        "id": chat_id,
        "title": title or title_from_messages(messages),
        "mode": mode,
        "model": model,
        "temperature": temperature,
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "messages": stored,
    }
    if mode == _MODE_EXCEL and excel_file_names is not None:
        payload["excel_file_names"] = sorted(excel_file_names)
    elif existing.get("excel_file_names"):
        payload["excel_file_names"] = existing["excel_file_names"]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    set_last_active_id(mode, chat_id)
    return payload


def rename_conversation(chat_id: str, title: str) -> bool:
    data = load_conversation(chat_id)
    if not data:
        return False
    clean = title.strip()[:120] or "New chat"
    data["title"] = clean
    data["updated_at"] = _now_iso()
    try:
        chat_file_path(chat_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def delete_all_conversations(*, mode: str) -> int:
    """Delete every saved conversation for *mode* (and each chat workspace). Returns count removed."""
    removed = 0
    for row in list_conversations(mode=mode):
        cid = str(row.get("id") or "")
        if cid and delete_conversation(cid):
            removed += 1
    clear_last_active_id(mode)
    return removed


def delete_conversation(chat_id: str) -> bool:
    path = chat_file_path(chat_id)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mode = data.get("mode") if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        mode = None
    path.unlink()
    delete_chat_workspace(chat_id)
    if isinstance(mode, str):
        last_path = _last_active_path(mode)
        if last_path.is_file():
            try:
                if last_path.read_text(encoding="utf-8").strip() == chat_id:
                    last_path.unlink()
            except OSError:
                pass
    return True
