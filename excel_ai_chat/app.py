"""Streamlit: Ollama chat, Excel uploads, merge (mean by keys), Markdown export."""

from __future__ import annotations

import html
import io
import json
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from excel_ai_chat.chat_store import (
    clear_last_active_id,
    create_conversation_id,
    delete_all_conversations,
    delete_conversation,
    get_last_active_id,
    load_conversation,
    list_conversations,
    rename_conversation,
    save_conversation,
)
from excel_ai_chat.excel_tools import merge_mean_by_keys, read_table
from excel_ai_chat.history_ui import (
    history_widget_key,
    render_history_row,
    sidebar_history_row_bind,
)
from excel_ai_chat.excel_agent import (
    excel_first_model_response,
    excel_proposal_from_response,
    excel_run_approved_blocks,
)
from excel_ai_chat.ollama_client import chat, list_models
from excel_ai_chat.excel_chat_files import (
    append_exports,
    list_export_download_items,
    load_attachments,
    save_attachments,
)
from excel_ai_chat.paths import default_ollama_base, outputs_dir, uploads_dir
from excel_ai_chat.personalization import (
    PersonalizationSettings,
    load_personalization,
    save_personalization,
    personalization_system_block,
    merge_system_with_personalization,
    _hydrate_personalization_widgets,
    _personalization_from_session,
    _process_profile_save_pending,
    _render_sidebar_personalization,
    _render_floating_profile_control,
    _system_prompt_for_hub,
)
from excel_ai_chat.prompts import (
    build_ollama_messages,
    build_spreadsheet_data_block,
)
from excel_ai_chat.theme import inject_hub_theme

_ALLOWED = {".csv", ".xlsx", ".xlsm", ".xls"}

NAV_HUB = "hub"
NAV_FILE_MANAGER = "file_manager"

MODE_CHAT = "chat"
MODE_EXCEL = "excel"

CHAT_COMPOSER_KEY = "hub_composer"

BST_INSTALLED_MODEL_PICK_KEY = "bst_installed_model_pick"
_ACTIVE_CHAT_ID_CHAT = "active_chat_id_chat"
_ACTIVE_CHAT_ID_EXCEL = "active_excel_chat_id"

# Drain chat_input into messages before the thread renders (avoids default Streamlit chat
# chrome before messages are inside the themed thread; hub bubble CSS keys off #bst-hub-chat-styling-root).
_BST_PENDING_CHAT_GEN = "_bst_pending_chat_gen"
_BST_PENDING_EXCEL_GEN = "_bst_pending_excel_gen"
_BST_EXCEL_CODE_PENDING = "_bst_excel_code_pending"
_BST_EXCEL_EXEC_ACTION = "_bst_excel_exec_action"
_EXCEL_FILES_BY_CHAT = "_excel_files_by_chat"
_EXCEL_PENDING_FILES = "_excel_pending_files"
_EXCEL_PENDING_UPLOAD_N = "excel_pending_upload_n"
_BST_HISTORY_RENAME_ID = "_bst_history_rename_chat_id"
_BST_HISTORY_CLIPBOARD = "_bst_history_clipboard_text"
_BST_HISTORY_NOTICE = "_bst_history_notice"
_BST_HISTORY_NOTICE_AT = "_bst_history_notice_at"
_HISTORY_NOTICE_TTL_SEC = 3.0
_BST_EXCEL_WELCOME_ONCE = "_bst_excel_welcome_once"

# Not in Streamlit PresetNames → avatar=None yields no icon (see chat._process_avatar_input).
_HUB_CHAT_USER_DISPLAY_NAME = "You"


@contextmanager
def _hub_chat_message(role: str):
    """Hub chat bubbles + hidden role marker for CSS (left = assistant, right = user)."""
    # Avoid BEM-style "--" in class names: some HTML sanitizers strip them, breaking :has(...) selectors.
    marker = "bst-msg-marker-user" if role == "user" else "bst-msg-marker-assistant"
    fav = Path(__file__).resolve().parent / "static" / "favicon.png"
    fav_path = fav.resolve().as_posix() if fav.is_file() else None

    if role == "user":
        with st.chat_message(_HUB_CHAT_USER_DISPLAY_NAME, avatar=None, width="stretch"):
            st.markdown(
                f'<span class="bst-msg-marker {marker}" hidden aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
            yield
    else:
        avatar = fav_path if fav_path else ":material/auto_awesome:"
        with st.chat_message("assistant", avatar=avatar, width="stretch"):
            st.markdown(
                f'<span class="bst-msg-marker {marker}" hidden aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
            yield


def _hub_message_body_markdown(
    text: str,
    *,
    role: str,
    attached_files: list[str] | None = None,
) -> None:
    """Hub thread message body: layout width must match role.

    ``stretch`` fills the chat column; on the user row that column is often narrow in
    flex layout, so short lines wrap. ``content`` keeps intrinsic width; CSS caps max.
    """
    if attached_files:
        if role == "user":
            _render_excel_message_attachments(attached_files)
        else:
            st.markdown(_excel_message_files_html(attached_files), unsafe_allow_html=True)
    if role == "user":
        st.markdown(text, width="content")
    else:
        st.markdown(text, width="stretch")


WELCOME_HEADING = "Welcome to our basic software technology"
CHAT_TAGLINES: tuple[str, ...] = (
    "How can I help you today?",
    "Ask me anything — I'm here to assist.",
    "Try a question or open Analyze Excel for spreadsheets.",
)

EXCEL_WELCOME_HEADING = "Analyze your spreadsheets with AI"
EXCEL_TAGLINES: tuple[str, ...] = (
    "Attach CSV or Excel files, then ask in plain language.",
    "Find duplicates, summarize columns, or export cleaned sheets.",
    "Use the paperclip beside the input to add one or more files.",
)

_EXCEL_MSG_PREVIEW_ROWS = 6

FLATICON_OTTER_ATTR_HTML = (
    '<a href="https://www.flaticon.com/free-icons/otter" title="otter">'
    "otter icons created by iconfield - Flaticon</a>"
)

_FAVICON = Path(__file__).resolve().parent / "static" / "favicon.png"

_WAITING_PHRASE_STEP_SEC = 3.2
_WAITING_DOTS_HTML = '<span class="bst-wait-dots"><b>·</b><b>·</b><b>·</b></span>'
# (label, animation-delay seconds) — Swimming first
_WAITING_PHRASES: tuple[tuple[str, float], ...] = (
    ("Floating while I think", 0.0),
    ("Cracking open a fresh answer", -3.2),
    ("Gathering shiny little thoughts", -6.4),
    ("Splishing up a clever answer", -9.6),
    ("Hold on, the otter is consulting its pebble", -12.8),
)


def _waiting_html() -> str:
    """Rotating status; hidden sizer keeps the bubble wide enough for the longest phrase + dots."""
    n = len(_WAITING_PHRASES)
    cycle = n * _WAITING_PHRASE_STEP_SEC
    longest = max(_WAITING_PHRASES, key=lambda item: len(item[0]))[0]
    sizer = (
        f'<span class="bst-wait-sizer" aria-hidden="true">'
        f"{html.escape(longest)}{_WAITING_DOTS_HTML}</span>"
    )
    phrases = "".join(
        f'<span class="bst-wait-phrase" style="animation-delay:{delay}s">'
        f"{html.escape(label)}{_WAITING_DOTS_HTML}</span>"
        for label, delay in _WAITING_PHRASES
    )
    parts = [
        f'<div class="bst-wait-wrap" style="--bst-wait-cycle:{cycle}s">',
        f'<div class="bst-wait-line">{sizer}',
        f'<span class="bst-wait-phrases" aria-live="polite">{phrases}</span>',
        "</div></div>",
    ]
    return "".join(parts)



_SUGGEST_CHIPS: list[tuple[str, str]] = [
    ("Average & sum",    "Calculate the mean and sum of every numeric column."),
    ("Find duplicates",  "Find and list any duplicate rows."),
    ("Filter rows",      "I'll describe a condition — filter the rows that match."),
    ("Sort descending",  "Sort the data by the first column in descending order."),
]


# ── State ─────────────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    base = Path(name).name
    if not base or base.startswith(".") or ".." in base:
        raise ValueError("Invalid file name.")
    if Path(base).suffix.lower() not in _ALLOWED:
        raise ValueError(f"Allowed types: {', '.join(sorted(_ALLOWED))}")
    return base


def _fm_del_button_key(filename: str) -> str:
    """Streamlit 1.57 exposes widget keys as .st-key-<key> for CSS targeting."""
    token = re.sub(r"[^\w]+", "_", Path(filename).name).strip("_")
    return f"bst_fm_del_{token}"[:80]


_FM_DELETE_JS = (
    Path(__file__).resolve().parent / "static" / "js" / "fm_delete.js"
)

def _fm_library_delete_styles() -> None:
    """Red Delete button JS paint (static/js/fm_delete.js)."""
    js = _FM_DELETE_JS.read_text(encoding="utf-8")
    components.html(f"<script>{js}</script>", height=0, scrolling=False)


_CHIP_STYLES_JS = (
    Path(__file__).resolve().parent / "static" / "js" / "chip_styles.js"
)


def _hub_excel_chip_styles() -> None:
    """Teal Excel chips + × exit — JS paint (static/js/chip_styles.js)."""
    js = _CHIP_STYLES_JS.read_text(encoding="utf-8")
    components.html(f"<script>{js}</script>", height=0, scrolling=False)


def _purge_hub_widget_keys() -> None:
    """Remove hub input / uploader widget state so the next paint matches a fresh load."""
    drop = {
        CHAT_COMPOSER_KEY,
        _EXCEL_PENDING_FILES,
        _EXCEL_PENDING_UPLOAD_N,
        _BST_PENDING_CHAT_GEN,
        _BST_PENDING_EXCEL_GEN,
    }
    for key in list(st.session_state.keys()):
        if not isinstance(key, str):
            continue
        if (
            key in drop
            or key.startswith(("hub_composer", "hub_chat_", "excel_pending_uploader_"))
        ):
            del st.session_state[key]


def _restore_main_hub() -> None:
    """Excel exit → chat home; keep chat history id, reset excel in-memory cache."""
    st.session_state.hub_mode = MODE_CHAT
    _excel_files_cache_clear_all()
    _clear_excel_pending_files()
    st.session_state.excel_ai_messages = []
    st.session_state.excel_ai_chip_text = ""
    st.session_state.excel_ai_input_counter = 0
    st.session_state.chat_input_counter = 0
    _purge_hub_widget_keys()
    _ensure_chat_session(MODE_CHAT)


def _enter_excel_mode() -> None:
    """Open Excel mode on a fresh conversation (do not resume last Excel chat)."""
    st.session_state.hub_mode = MODE_EXCEL
    st.session_state.excel_ai_messages = []
    _set_active_chat_id(MODE_EXCEL, None)
    clear_last_active_id(MODE_EXCEL)
    _clear_excel_pending_files()
    _excel_files_cache_clear_all()
    st.session_state.excel_ai_chip_text = ""
    st.session_state.pop(_BST_EXCEL_CODE_PENDING, None)
    st.session_state.pop(_BST_EXCEL_EXEC_ACTION, None)
    st.session_state.excel_ai_input_counter += 1
    st.session_state[_BST_EXCEL_WELCOME_ONCE] = True
    _purge_hub_widget_keys()


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "messages":               [],
        "ollama_base":            default_ollama_base(),
        "nav_page":               NAV_HUB,
        "hub_mode":               MODE_CHAT,
        "chat_input_counter":     0,
        "excel_ai_messages":      [],
        "excel_ai_input_counter": 0,
        "excel_ai_chip_text":     "",
        _EXCEL_PENDING_UPLOAD_N:  0,
        "model_name":             "llama3.2",
        _ACTIVE_CHAT_ID_CHAT:     None,
        _ACTIVE_CHAT_ID_EXCEL:    None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    _hydrate_personalization_widgets()


# ── Chat history (outputs/chats/*.json) ───────────────────────────────────────

def _active_chat_id_key(mode: str) -> str:
    return _ACTIVE_CHAT_ID_CHAT if mode == MODE_CHAT else _ACTIVE_CHAT_ID_EXCEL


def _messages_state_key(mode: str) -> str:
    return "messages" if mode == MODE_CHAT else "excel_ai_messages"


def _get_active_chat_id(mode: str) -> str | None:
    val = st.session_state.get(_active_chat_id_key(mode))
    return val if isinstance(val, str) and val else None


def _set_active_chat_id(mode: str, chat_id: str | None) -> None:
    st.session_state[_active_chat_id_key(mode)] = chat_id


def _ensure_active_chat_id(mode: str) -> str:
    chat_id = _get_active_chat_id(mode)
    if chat_id and load_conversation(chat_id):
        return chat_id
    new_id = create_conversation_id()
    _set_active_chat_id(mode, new_id)
    return new_id


def _messages_from_stored_conversation(data: dict[str, Any]) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for m in data.get("messages", []):
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        row: dict[str, Any] = {
            "role": str(m["role"]),
            "content": str(m.get("content", "")),
        }
        att = m.get("attached_files")
        if isinstance(att, list) and att:
            row["attached_files"] = [str(x) for x in att]
        loaded.append(row)
    return loaded


def _ensure_chat_session(mode: str) -> None:
    """Load the active conversation from disk when the in-memory thread is empty."""
    msg_key = _messages_state_key(mode)
    if st.session_state.get(msg_key):
        return
    chat_id = _get_active_chat_id(mode)
    if not chat_id:
        chat_id = get_last_active_id(mode)
        if chat_id:
            _set_active_chat_id(mode, chat_id)
    if not chat_id:
        return
    data = load_conversation(chat_id)
    if not data or data.get("mode") != mode:
        return
    st.session_state[msg_key] = _messages_from_stored_conversation(data)


def _persist_current_chat(mode: str, model: str, temperature: float) -> None:
    msg_key = _messages_state_key(mode)
    messages: list[dict[str, Any]] = st.session_state.get(msg_key) or []
    if not messages:
        return
    chat_id = _ensure_active_chat_id(mode)
    if mode == MODE_EXCEL:
        files = _excel_files_for_chat(chat_id)
        save_attachments(chat_id, files)
        excel_names = sorted(files.keys())
    else:
        excel_names = None
    save_conversation(
        chat_id,
        mode=mode,
        messages=messages,
        model=model,
        temperature=temperature,
        excel_file_names=excel_names,
    )


def _start_new_chat(mode: str) -> None:
    st.session_state[_messages_state_key(mode)] = []
    _set_active_chat_id(mode, None)
    clear_last_active_id(mode)
    st.session_state.pop(_BST_EXCEL_CODE_PENDING, None)
    st.session_state.pop(_BST_EXCEL_EXEC_ACTION, None)
    st.session_state.nav_page = NAV_HUB
    if mode == MODE_EXCEL:
        _clear_excel_pending_files()
        st.session_state.excel_ai_input_counter += 1
    else:
        st.session_state.chat_input_counter += 1
    _purge_hub_widget_keys()


def _load_chat_into_session(mode: str, chat_id: str) -> None:
    data = load_conversation(chat_id)
    if not data or data.get("mode") != mode:
        return
    st.session_state.nav_page = NAV_HUB
    st.session_state[_messages_state_key(mode)] = _messages_from_stored_conversation(data)
    _set_active_chat_id(mode, chat_id)
    if mode == MODE_EXCEL:
        cache = _excel_files_cache()
        cache.pop(chat_id, None)
        cache[chat_id] = load_attachments(chat_id)
        _clear_excel_pending_files()
        st.session_state.excel_ai_input_counter += 1
    else:
        st.session_state.chat_input_counter += 1
    st.session_state.pop(_BST_EXCEL_CODE_PENDING, None)
    st.session_state.pop(_BST_EXCEL_EXEC_ACTION, None)
    _purge_hub_widget_keys()


def _on_sidebar_new_chat(mode: str) -> None:
    _start_new_chat(mode)


def _set_history_notice(message: str) -> None:
    st.session_state[_BST_HISTORY_NOTICE] = message
    st.session_state[_BST_HISTORY_NOTICE_AT] = time.time()


def _peek_history_notice() -> str | None:
    message = st.session_state.get(_BST_HISTORY_NOTICE)
    if not message:
        return None
    shown_at = float(st.session_state.get(_BST_HISTORY_NOTICE_AT, 0))
    if time.time() - shown_at > _HISTORY_NOTICE_TTL_SEC:
        st.session_state.pop(_BST_HISTORY_NOTICE, None)
        st.session_state.pop(_BST_HISTORY_NOTICE_AT, None)
        return None
    return str(message)


def _on_sidebar_clear_all_history(mode: str) -> None:
    """Delete all conversations for the current hub mode and reset the active thread."""
    delete_all_conversations(mode=mode)
    st.session_state.pop(_BST_HISTORY_RENAME_ID, None)
    _set_history_notice("All conversations deleted.")
    _start_new_chat(mode)


def _on_sidebar_open_chat(mode: str, chat_id: str) -> None:
    if chat_id != _get_active_chat_id(mode):
        _load_chat_into_session(mode, chat_id)


def _on_sidebar_delete_chat(mode: str, chat_id: str) -> None:
    delete_conversation(chat_id)
    if chat_id == _get_active_chat_id(mode):
        _start_new_chat(mode)


def _conversation_share_text(chat_id: str) -> str:
    data = load_conversation(chat_id)
    if not data:
        return ""
    title = str(data.get("title") or "New chat")
    lines = [title, ""]
    for m in data.get("messages") or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        if role not in ("user", "assistant"):
            continue
        label = "You" if role == "user" else "Assistant"
        body = str(m.get("content") or "").strip()
        if body:
            lines.append(f"{label}:\n{body}\n")
    return "\n".join(lines).strip()


def _on_hist_menu_share(_mode: str, chat_id: str) -> None:
    text = _conversation_share_text(chat_id)
    if text:
        st.session_state[_BST_HISTORY_CLIPBOARD] = text
        _set_history_notice("Conversation copied to clipboard.")


def _on_hist_menu_rename(_mode: str, chat_id: str) -> None:
    st.session_state[_BST_HISTORY_RENAME_ID] = chat_id


def _flush_history_clipboard(text: str) -> None:
    payload = json.dumps(text)
    components.html(
        f"<script>(function(){{"
        f"const t={payload};"
        f"const d=window.parent.document;"
        f"try{{navigator.clipboard.writeText(t);}}catch(e){{"
        f"const ta=d.createElement('textarea');ta.value=t;"
        f"ta.style.cssText='position:fixed;left:-9999px;';"
        f"d.body.appendChild(ta);ta.select();"
        f"try{{d.execCommand('copy');}}catch(err){{}}"
        f"d.body.removeChild(ta);"
        f"}}"
        f"}})();</script>",
        height=0,
    )


def _render_history_rename_panel(mode: str) -> None:
    rename_id = st.session_state.get(_BST_HISTORY_RENAME_ID)
    if not isinstance(rename_id, str) or not rename_id:
        return
    data = load_conversation(rename_id)
    if not data or data.get("mode") != mode:
        st.session_state.pop(_BST_HISTORY_RENAME_ID, None)
        return
    wkey = history_widget_key(rename_id)
    current = str(data.get("title") or "New chat")
    with st.form(f"history_rename_{mode}_{wkey}"):
        st.markdown("**Rename conversation**")
        new_title = st.text_input("Name", value=current, label_visibility="collapsed")
        save_col, cancel_col = st.columns(2)
        with save_col:
            submitted = st.form_submit_button("Save", use_container_width=True)
        with cancel_col:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)
    if cancelled:
        st.session_state.pop(_BST_HISTORY_RENAME_ID, None)
        st.rerun()
    if submitted:
        rename_conversation(rename_id, new_title)
        st.session_state.pop(_BST_HISTORY_RENAME_ID, None)
        _set_history_notice("Conversation renamed.")
        st.rerun()


def _render_sidebar_chat_history() -> None:
    if st.session_state.nav_page != NAV_HUB:
        return
    mode = st.session_state.hub_mode
    active_id = _get_active_chat_id(mode)

    notice = _peek_history_notice()
    clipboard = st.session_state.pop(_BST_HISTORY_CLIPBOARD, None)
    if clipboard:
        _flush_history_clipboard(clipboard)

    st.markdown(
        '<p class="bst-sidebar-fm-kicker bst-sidebar-history-kicker">Chat history</p>'
        '<span id="bst-sidebar-history-root" class="bst-sidebar-history-anchor" '
        'aria-hidden="true"></span>'
        '<span class="bst-sidebar-new-chat-anchor" aria-hidden="true"></span>'
        '<span class="bst-sidebar-clear-all-anchor" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    pill_new, pill_clear = st.columns(2, gap="small", vertical_alignment="center")
    with pill_new:
        st.button(
            "New chat",
            key=f"sidebar_new_chat_{mode}",
            type="secondary",
            use_container_width=True,
            on_click=_on_sidebar_new_chat,
            args=(mode,),
        )
    with pill_clear:
        st.button(
            "Clear all",
            key=f"sidebar_clear_all_{mode}",
            type="secondary",
            use_container_width=True,
            on_click=_on_sidebar_clear_all_history,
            args=(mode,),
        )

    _render_history_rename_panel(mode)

    convos = list_conversations(mode=mode)
    if not convos:
        if notice:
            st.markdown(
                f'<p class="bst-sidebar-archive-empty bst-sidebar-archive-notice">'
                f"{html.escape(notice)}</p>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<p class="bst-sidebar-archive-empty">No saved conversations yet.</p>',
                unsafe_allow_html=True,
            )
        return

    if notice:
        st.markdown(
            f'<p class="bst-sidebar-archive-notice bst-sidebar-archive-notice--inline">'
            f"{html.escape(notice)}</p>",
            unsafe_allow_html=True,
        )

    for row in convos:
        cid = str(row["id"])
        render_history_row(
            mode=mode,
            chat_id=cid,
            title=str(row.get("title") or "New chat"),
            is_active=cid == active_id,
            on_open=_on_sidebar_open_chat,
            on_share=_on_hist_menu_share,
            on_rename=_on_hist_menu_rename,
            on_delete=_on_sidebar_delete_chat,
        )
    sidebar_history_row_bind()


def _on_installed_model_pick_change() -> None:
    """Copy Installed models selectbox → Model text field."""
    st.session_state.model_name = st.session_state[BST_INSTALLED_MODEL_PICK_KEY]


# ── Excel helpers (per chat_id) ───────────────────────────────────────────────

def _excel_files_cache() -> dict[str, dict[str, pd.DataFrame]]:
    cache = st.session_state.get(_EXCEL_FILES_BY_CHAT)
    if not isinstance(cache, dict):
        cache = {}
        st.session_state[_EXCEL_FILES_BY_CHAT] = cache
    return cache


def _excel_files_cache_clear_all() -> None:
    st.session_state.pop(_EXCEL_FILES_BY_CHAT, None)


def _excel_files_for_chat(chat_id: str) -> dict[str, pd.DataFrame]:
    cache = _excel_files_cache()
    if chat_id in cache:
        return cache[chat_id]
    loaded = load_attachments(chat_id)
    cache[chat_id] = loaded
    return loaded


def _excel_files() -> dict[str, pd.DataFrame]:
    """Spreadsheets attached to the active Excel-mode chat."""
    chat_id = _get_active_chat_id(MODE_EXCEL)
    if not chat_id:
        return {}
    return _excel_files_for_chat(chat_id)


def _sync_excel_files_to_disk(chat_id: str, files: dict[str, pd.DataFrame]) -> None:
    _excel_files_cache()[chat_id] = dict(files)
    save_attachments(chat_id, files)


def _read_uploaded_dataframe(uploaded: Any) -> pd.DataFrame:
    """Read an UploadedFile into a DataFrame (BytesIO — reliable after seek)."""
    suffix = Path(uploaded.name).suffix.lower()
    if hasattr(uploaded, "getvalue"):
        raw = uploaded.getvalue()
    else:
        uploaded.seek(0)
        raw = uploaded.read()
    buf = io.BytesIO(raw)
    if suffix == ".csv":
        return pd.read_csv(buf)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(buf, engine="openpyxl")
    return pd.read_excel(buf)


def _clear_excel_pending_files() -> None:
    st.session_state.pop(_EXCEL_PENDING_FILES, None)


def _excel_pending_files() -> dict[str, pd.DataFrame]:
    raw = st.session_state.get(_EXCEL_PENDING_FILES)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, pd.DataFrame] = {}
    for name, df in raw.items():
        if isinstance(name, str) and isinstance(df, pd.DataFrame):
            out[name] = df
    return out


def _set_excel_pending_files(files: dict[str, pd.DataFrame]) -> None:
    st.session_state[_EXCEL_PENDING_FILES] = dict(files)


def _pending_uploader_key() -> str:
    n = st.session_state.get(_EXCEL_PENDING_UPLOAD_N, 0)
    return f"excel_pending_uploader_{n}"


def _ingest_pending_uploads(uploaded: Any) -> bool:
    """Stage selected files above the composer until the user sends a message."""
    if uploaded is None:
        return False
    uploaded_list = uploaded if isinstance(uploaded, list) else [uploaded]
    if not uploaded_list:
        return False

    pending = dict(_excel_pending_files())
    errors: list[str] = []
    changed = False

    for item in uploaded_list:
        try:
            name = _safe_name(item.name)
        except ValueError as e:
            errors.append(f"{item.name}: {e}")
            continue
        try:
            if hasattr(item, "seek"):
                item.seek(0)
            pending[name] = _read_uploaded_dataframe(item)
            changed = True
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")

    for msg in errors:
        st.error(f"파일을 읽을 수 없습니다: {msg}")

    if changed:
        _set_excel_pending_files(pending)
    return changed


def _excel_commit_pending_files() -> list[str]:
    """Merge staged uploads into the active chat; return newly attached names."""
    pending = _excel_pending_files()
    if not pending:
        return []
    chat_id = _ensure_active_chat_id(MODE_EXCEL)
    merged = dict(_excel_files_for_chat(chat_id))
    merged.update(pending)
    _sync_excel_files_to_disk(chat_id, merged)
    _clear_excel_pending_files()
    st.session_state[_EXCEL_PENDING_UPLOAD_N] = (
        int(st.session_state.get(_EXCEL_PENDING_UPLOAD_N, 0)) + 1
    )
    return sorted(pending.keys())


def _excel_file_kind_class(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".csv":
        return "csv"
    return "xlsx"


def _excel_file_kind_label(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".csv":
        return "CSV"
    if ext in {".xlsx", ".xlsm"}:
        return "XLSX"
    if ext == ".xls":
        return "XLS"
    return ext.lstrip(".").upper() or "FILE"


def _excel_attachments_html(
    files: dict[str, pd.DataFrame],
    *,
    variant: str = "banner",
) -> str:
    """Card grid of spreadsheets (composer variant = staged files above input)."""
    if not files:
        return ""
    n = len(files)
    cards: list[str] = []
    for name in sorted(files):
        df = files[name]
        kind = _excel_file_kind_class(name)
        kind_label = _excel_file_kind_label(name)
        cards.append(
            f'<article class="bst-excel-attach-card bst-excel-attach-card--{kind}">'
            f'<div class="bst-excel-attach-card__icon" aria-hidden="true">'
            f"{html.escape(kind_label)}</div>"
            f'<div class="bst-excel-attach-card__body">'
            f'<div class="bst-excel-attach-card__name" title="{html.escape(name)}">'
            f"{html.escape(name)}</div>"
            f'<div class="bst-excel-attach-card__meta">'
            f"{len(df):,}행 · {len(df.columns)}열"
            f"</div></div></article>"
        )
    grid = "\n".join(cards)
    if variant in {"composer", "composer-inbox"}:
        return (
            '<span id="bst-excel-pending-root" aria-hidden="true"></span>'
            '<section class="bst-excel-attachments bst-excel-attachments--composer'
            f'{" bst-excel-attachments--composer-inbox" if variant == "composer-inbox" else ""}" '
            'aria-label="첨부된 파일 (전송 전)">'
            f'<div class="bst-excel-attachments__grid">{grid}</div>'
            "</section>"
        )
    return (
        '<span id="bst-excel-attachments-root" aria-hidden="true"></span>'
        '<section class="bst-excel-attachments" aria-label="Attached spreadsheets">'
        '<header class="bst-excel-attachments__head">'
        '<span class="bst-excel-attachments__title">첨부된 파일</span>'
        f'<span class="bst-excel-attachments__count">{n}개</span>'
        "</header>"
        f'<div class="bst-excel-attachments__grid">{grid}</div>'
        "</section>"
    )


def _excel_message_files_html(names: list[str]) -> str:
    chips = "".join(
        f'<span class="bst-excel-msg-file">{html.escape(n)}</span>' for n in sorted(names)
    )
    return f'<div class="bst-excel-msg-files">{chips}</div>'


def _render_excel_message_attachments(names: list[str]) -> None:
    """Compact spreadsheet previews inside the user message bubble."""
    files = _excel_files()
    st.markdown('<div class="bst-excel-msg-previews">', unsafe_allow_html=True)
    for name in sorted(names):
        df = files.get(name)
        kind = _excel_file_kind_label(name)
        kind_cls = _excel_file_kind_class(name)
        if df is None:
            st.markdown(
                f'<article class="bst-excel-msg-preview bst-excel-msg-preview--missing">'
                f'<span class="bst-excel-msg-preview__badge bst-excel-msg-preview__badge--{kind_cls}">'
                f"{html.escape(kind)}</span>"
                f'<span class="bst-excel-msg-preview__name">{html.escape(name)}</span>'
                f"</article>",
                unsafe_allow_html=True,
            )
            continue
        preview = df.head(_EXCEL_MSG_PREVIEW_ROWS)
        st.markdown(
            f'<article class="bst-excel-msg-preview">'
            f'<header class="bst-excel-msg-preview__head">'
            f'<span class="bst-excel-msg-preview__badge bst-excel-msg-preview__badge--{kind_cls}">'
            f"{html.escape(kind)}</span>"
            f'<span class="bst-excel-msg-preview__name" title="{html.escape(name)}">'
            f"{html.escape(name)}</span>"
            f'<span class="bst-excel-msg-preview__meta">'
            f"{len(df):,} rows · {len(df.columns)} cols</span>"
            f"</header></article>",
            unsafe_allow_html=True,
        )
        row_h = min(len(preview), _EXCEL_MSG_PREVIEW_ROWS)
        st.dataframe(
            preview,
            use_container_width=True,
            hide_index=True,
            height=min(52 + row_h * 35, 240),
            column_config=_preview_column_config(preview),
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _pending_remove_widget_key(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return f"excel_rm_pending_{safe[:48]}"


def _remove_excel_pending_file(name: str) -> None:
    pending = dict(_excel_pending_files())
    pending.pop(name, None)
    _set_excel_pending_files(pending)


def _excel_pending_chip_html(name: str, df: pd.DataFrame) -> str:
    kind = _excel_file_kind_label(name)
    kind_cls = _excel_file_kind_class(name)
    return (
        f'<div class="bst-excel-pending-chip bst-excel-pending-chip--{kind_cls}">'
        f'<span class="bst-excel-pending-chip__icon" aria-hidden="true">'
        f"{html.escape(kind)}</span>"
        f'<span class="bst-excel-pending-chip__name" title="{html.escape(name)}">'
        f"{html.escape(name)}</span>"
        f'<span class="bst-excel-pending-chip__meta">'
        f"{len(df):,} rows</span>"
        f"</div>"
    )


def _render_excel_pending_inbox() -> None:
    """Staged files inside the composer shell until the user presses Enter."""
    pending = _excel_pending_files()
    if not pending:
        return
    st.markdown('<span id="bst-excel-pending-root" aria-hidden="true"></span>', unsafe_allow_html=True)
    st.markdown(
        '<div class="bst-excel-composer-inbox"><div class="bst-excel-composer-inbox__grid">',
        unsafe_allow_html=True,
    )
    names = sorted(pending.keys())
    for row_start in range(0, len(names), 4):
        batch = names[row_start : row_start + 4]
        cols = st.columns(len(batch))
        for col, name in zip(cols, batch):
            with col:
                st.markdown(
                    f'<div class="bst-excel-pending-chip-wrap">'
                    f"{_excel_pending_chip_html(name, pending[name])}</div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "×",
                    key=_pending_remove_widget_key(name),
                    type="tertiary",
                    help=f"Remove {name}",
                ):
                    _remove_excel_pending_file(name)
                    st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)


_COMPOSER_BIND_JS = Path(__file__).resolve().parent / "static" / "js" / "composer_bind.js"


def _composer_bind() -> None:
    """Pill-style chat input (Excel + main chat) — static/js/composer_bind.js."""
    js = _COMPOSER_BIND_JS.read_text(encoding="utf-8")
    components.html(f"<script>{js}</script>", height=0, scrolling=False)


def _render_excel_clip_button() -> None:
    """Fragment rerun only — keeps Excel welcome / tagline when clip is tapped."""
    st.button(
        "",
        icon=":material/attach_file:",
        key="excel_clip_btn",
        type="secondary",
        use_container_width=True,
    )


def _render_excel_composer_row(
    placeholder: str,
    widget_key: str,
) -> tuple[Any, bool]:
    """
    Pending blocks live in the composer shell; clip opens the file explorer via hidden uploader.
    Returns (chat_input value, True if new files were staged and caller should rerun).
    """
    st.markdown('<span id="bst-excel-composer"></span>', unsafe_allow_html=True)
    _render_excel_pending_inbox()

    uploaded = st.file_uploader(
        "Attach",
        type=["csv", "xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
        key=_pending_uploader_key(),
        label_visibility="collapsed",
    )
    clip_col, input_col = st.columns([0.065, 0.935], gap="small", vertical_alignment="center")
    with clip_col:
        _render_excel_clip_button()
    with input_col:
        prompt = st.chat_input(placeholder, key=widget_key, width="stretch")
    _composer_bind()

    staged = False
    if _ingest_pending_uploads(uploaded):
        st.session_state[_EXCEL_PENDING_UPLOAD_N] = (
            int(st.session_state.get(_EXCEL_PENDING_UPLOAD_N, 0)) + 1
        )
        staged = True
    return prompt, staged


def _render_chat_composer_row(placeholder: str, widget_key: str) -> Any:
    """Main chat — pill on chat_input only (no clip column / spacer)."""
    st.markdown('<span id="bst-chat-composer"></span>', unsafe_allow_html=True)
    prompt = st.chat_input(placeholder, key=widget_key, width="stretch")
    _composer_bind()
    return prompt


_PREVIEW_SCROLL_HEIGHT_PX = 440
_PREVIEW_MAX_DISPLAY_ROWS = 5000
_PREVIEW_COL_WIDTH_PX = 150


def _preview_column_config(df: pd.DataFrame) -> dict[str, st.column_config.Column]:
    """Keep columns wide enough that the grid scrolls horizontally when needed."""
    return {
        str(col): st.column_config.Column(width=_PREVIEW_COL_WIDTH_PX) for col in df.columns
    }


def _render_scrollable_dataframe(df: pd.DataFrame) -> None:
    """Full preview in a fixed-height table — scroll inside to see all rows/columns."""
    total = len(df)
    view = df.head(_PREVIEW_MAX_DISPLAY_ROWS) if total > _PREVIEW_MAX_DISPLAY_ROWS else df
    st.dataframe(
        view,
        width="stretch",
        height=_PREVIEW_SCROLL_HEIGHT_PX,
        column_config=_preview_column_config(view),
    )
    if total > _PREVIEW_MAX_DISPLAY_ROWS:
        st.caption(
            f"Showing the first {_PREVIEW_MAX_DISPLAY_ROWS:,} of {total:,} rows. "
            "Scroll inside the table (vertical and horizontal) for the rest of this preview."
        )


def _on_excel_suggest_pill_change() -> None:
    picked = st.session_state.get("excel_suggest_pill")
    if not picked:
        return
    for label, prompt in _SUGGEST_CHIPS:
        if label == picked:
            st.session_state.excel_ai_chip_text = prompt
            st.session_state.excel_ai_input_counter += 1
            st.rerun()
            return


def _render_suggest_chips() -> None:
    st.markdown('<span id="bst-suggest-chips"></span>', unsafe_allow_html=True)
    st.pills(
        "Suggestions",
        options=[label for label, _ in _SUGGEST_CHIPS],
        key="excel_suggest_pill",
        label_visibility="collapsed",
        on_change=_on_excel_suggest_pill_change,
        width="content",
    )


def _render_excel_context_empty() -> None:
    """Suggestion chips on empty Excel hub (attach via in-input paperclip)."""
    _render_suggest_chips()
    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)


# ── Submission handlers ───────────────────────────────────────────────────────

def _hub_drain_pending_chat_submit(model: str, temperature: float) -> None:
    """If the hub chat_input has a value, record the user message and flag generation."""
    if st.session_state.hub_mode != MODE_CHAT:
        return
    key = _composer_widget_key()
    val = st.session_state.get(key)
    if not isinstance(val, str) or not val.strip():
        return
    text = val.strip()
    _ensure_active_chat_id(MODE_CHAT)
    st.session_state.messages.append({"role": "user", "content": text})
    _persist_current_chat(MODE_CHAT, model, temperature)
    st.session_state[_BST_PENDING_CHAT_GEN] = (model, temperature)
    st.session_state.chat_input_counter += 1


def _hub_complete_pending_chat_generation(model: str, temperature: float) -> None:
    """Inside the hub thread: assistant bubble shows wait dots, then the reply."""
    if _BST_PENDING_CHAT_GEN not in st.session_state:
        return
    st.session_state.pop(_BST_PENDING_CHAT_GEN, None)

    with _hub_chat_message("assistant"):
        slot = st.empty()
        slot.markdown(_waiting_html(), unsafe_allow_html=True, width="content")
        try:
            reply = chat(
                st.session_state.ollama_base,
                model,
                build_ollama_messages(
                    st.session_state.messages,
                    system=_system_prompt_for_hub(MODE_CHAT),
                ),
                temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            reply = f"**Error**\n\n{e}"
        finally:
            slot.empty()
        _hub_message_body_markdown(reply, role="assistant")

    st.session_state.messages.append({"role": "assistant", "content": reply})
    _persist_current_chat(MODE_CHAT, model, temperature)
    st.rerun()


def _excel_api_messages() -> list[dict[str, str]]:
    """Thread for Ollama: includes hidden spreadsheet block; strips internal keys only."""
    return [
        {"role": str(m["role"]), "content": str(m["content"])}
        for m in st.session_state.excel_ai_messages
        if m.get("role") in ("user", "assistant") and m.get("content") is not None
    ]


def _excel_sync_spreadsheet_context(files: dict[str, pd.DataFrame]) -> None:
    """Refresh hidden <spreadsheet_data> user message (UI hides it; API always sends it)."""
    msgs = st.session_state.excel_ai_messages
    st.session_state.excel_ai_messages = [m for m in msgs if not m.get("_hidden")]
    if not files:
        return
    st.session_state.excel_ai_messages.insert(
        0,
        {
            "role": "user",
            "content": build_spreadsheet_data_block(files),
            "_hidden": True,
        },
    )


def _excel_api_messages_built() -> list[dict[str, str]]:
    return build_ollama_messages(
        _excel_api_messages(),
        system=_system_prompt_for_hub(MODE_EXCEL),
    )


def _append_excel_assistant_reply(reply: str, model: str, temperature: float) -> None:
    st.session_state.excel_ai_messages.append({"role": "assistant", "content": reply})
    _persist_current_chat(MODE_EXCEL, model, temperature)


def _set_excel_downloads(exports: list[tuple[str, pd.DataFrame]]) -> None:
    """Append tabular execution results to the active chat's export folder."""
    if not exports:
        return
    chat_id = _get_active_chat_id(MODE_EXCEL)
    if not chat_id:
        return
    append_exports(chat_id, exports)


def _render_excel_downloads() -> None:
    chat_id = _get_active_chat_id(MODE_EXCEL)
    if not chat_id:
        return
    items = list_export_download_items(chat_id)
    if not items:
        return
    st.markdown(
        '<span id="bst-excel-downloads" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    st.markdown("**Download results (Excel)**")
    cols = st.columns(min(len(items), 3))
    for i, item in enumerate(items):
        with cols[i % len(cols)]:
            st.download_button(
                str(item["label"]),
                data=item["data"],
                file_name=str(item["file_name"]),
                mime=str(item["mime"]),
                key=f"bst_excel_dl_{i}_{item['file_name']}",
                use_container_width=True,
            )


def _render_excel_code_confirmation() -> None:
    """Show proposed Python + summary; Run / Cancel set _BST_EXCEL_EXEC_ACTION and rerun."""
    proposal = st.session_state.get(_BST_EXCEL_CODE_PENDING)
    if not proposal:
        return
    st.markdown(
        '<span id="bst-excel-code-confirm" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    preamble = str(proposal.get("assistant_preamble") or "").strip()
    if preamble:
        st.markdown(preamble)
    st.markdown("**What this code will do**")
    st.info(str(proposal.get("summary") or "Runs a pandas analysis on your uploaded file(s)."))
    st.markdown("**Code preview**")
    for code in proposal.get("blocks") or []:
        st.code(str(code), language="python")
    st.caption("The code runs locally on your uploaded data only after you approve.")
    run_col, cancel_col = st.columns(2)
    with run_col:
        if st.button("Run analysis", type="primary", key="bst_excel_run_code", use_container_width=True):
            st.session_state[_BST_EXCEL_EXEC_ACTION] = "run"
            st.rerun()
    with cancel_col:
        if st.button("Cancel", type="secondary", key="bst_excel_cancel_code", use_container_width=True):
            st.session_state[_BST_EXCEL_EXEC_ACTION] = "cancel"
            st.rerun()


def _excel_handle_exec_action(model: str, temperature: float) -> None:
    """Process Run / Cancel from the code confirmation panel."""
    action = st.session_state.pop(_BST_EXCEL_EXEC_ACTION, None)
    if not action:
        return
    proposal = st.session_state.pop(_BST_EXCEL_CODE_PENDING, None)
    if not proposal:
        return

    if action == "cancel":
        _append_excel_assistant_reply(
            "Code execution was cancelled. You can ask another question or request different analysis.",
            model,
            temperature,
        )
        st.rerun()
        return

    files = _excel_files()
    with _hub_chat_message("assistant"):
        slot = st.empty()
        slot.markdown(_waiting_html(), unsafe_allow_html=True, width="content")
        try:
            outcome, exports = excel_run_approved_blocks(proposal, files)
            _set_excel_downloads(exports)
            if isinstance(outcome, dict):
                st.session_state[_BST_EXCEL_CODE_PENDING] = outcome
                slot.empty()
                st.rerun()
            reply = str(outcome)
        except Exception as e:  # noqa: BLE001
            reply = f"**Error**\n\n{e}"
        finally:
            slot.empty()
        _hub_message_body_markdown(reply, role="assistant")

    _append_excel_assistant_reply(reply, model, temperature)
    st.rerun()


def _hub_complete_pending_excel_generation(model: str, temperature: float) -> None:
    """Ask the model; if it proposes Python, show confirmation instead of running immediately."""
    if _BST_PENDING_EXCEL_GEN not in st.session_state:
        return
    st.session_state.pop(_BST_PENDING_EXCEL_GEN, None)
    files = _excel_files()
    _excel_sync_spreadsheet_context(files)
    base = st.session_state.ollama_base
    api_messages = _excel_api_messages_built()

    slot = st.empty()
    slot.markdown(_waiting_html(), unsafe_allow_html=True, width="content")
    try:
        response = excel_first_model_response(
            base,
            model,
            api_messages,
            temperature=temperature,
        )
    except Exception as e:  # noqa: BLE001
        slot.empty()
        _append_excel_assistant_reply(f"**Error**\n\n{e}", model, temperature)
        st.rerun()
        return
    slot.empty()

    proposal = excel_proposal_from_response(
        response,
        api_messages,
        ollama_base=base,
        model=model,
        temperature=temperature,
    )
    if proposal is None:
        with _hub_chat_message("assistant"):
            _hub_message_body_markdown(response, role="assistant")
        _append_excel_assistant_reply(response, model, temperature)
        st.rerun()
        return

    st.session_state[_BST_EXCEL_CODE_PENDING] = proposal
    st.rerun()


# ── Hub (single layout; main home == after Excel exit) ─────────────────────────

def _render_welcome_heading(heading: str, *, excel: bool = False) -> None:
    n = len(heading)
    excel_cls = " bst-welcome-type--excel" if excel else ""
    st.markdown(
        f'<h1 class="bst-welcome-type{excel_cls}" aria-label="{html.escape(heading)}" '
        f'style="--bst-welcome-chars:{n}">'
        f'<span class="bst-welcome-type__text">{html.escape(heading)}</span>'
        '<span class="bst-welcome-type__caret" aria-hidden="true"></span>'
        "</h1>",
        unsafe_allow_html=True,
    )


def _render_tagline_cycle(taglines: tuple[str, ...], *, excel: bool = False) -> None:
    tagline_lines = "".join(
        f'<span class="bst-tagline-cycle__line">{html.escape(line)}</span>'
        for line in taglines
    )
    excel_cls = " bst-hub-tagline--excel" if excel else ""
    st.markdown(
        f'<p class="bst-hub-tagline bst-tagline-cycle{excel_cls}" aria-live="polite">'
        f"{tagline_lines}</p>",
        unsafe_allow_html=True,
    )


def _render_chat_welcome() -> None:
    _render_welcome_heading(WELCOME_HEADING)
    _render_tagline_cycle(CHAT_TAGLINES)


def _render_excel_welcome() -> None:
    st.markdown(
        '<span id="bst-hub-excel-welcome" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    _render_welcome_heading(EXCEL_WELCOME_HEADING, excel=True)
    _render_tagline_cycle(EXCEL_TAGLINES, excel=True)


def _hub_scroll_to_bottom() -> None:
    """Keep the chat thread scrolled to the latest message (bottom-anchored)."""
    components.html(
        "<script>(function(){"
        "const run=()=>{try{const w=window.parent,d=w.document,end=d.getElementById('bst-hub-thread-end');"
        "if(!end)return;"
        "let n=end;for(let i=0;i<14&&n;i++){"
        "const oy=w.getComputedStyle(n).overflowY;"
        "if((oy==='auto'||oy==='scroll')&&n.scrollHeight>n.clientHeight+1){"
        "n.scrollTop=n.scrollHeight;}"
        "n=n.parentElement;}"
        "const a=d.getElementById('bst-hub-thread');"
        "const wrap=a&&a.nextElementSibling;"
        "if(wrap){wrap.scrollTop=wrap.scrollHeight;"
        "wrap.querySelectorAll('[data-testid=stVerticalBlock]').forEach((el)=>{"
        "if(el.scrollHeight>el.clientHeight+1)el.scrollTop=el.scrollHeight;});}"
        "}catch(e){}};"
        "run();requestAnimationFrame(run);setTimeout(run,80);setTimeout(run,280);"
        "setTimeout(run,650);})();</script>",
        height=0,
        scrolling=False,
    )


def _composer_widget_key() -> str:
    n = st.session_state.chat_input_counter
    return CHAT_COMPOSER_KEY if n == 0 else f"{CHAT_COMPOSER_KEY}_{n}"


def _render_hub_composer(mode: str, model: str, temperature: float) -> None:
    """One chat_input for the hub — same key on main home and after leaving Excel."""
    widget_key = _composer_widget_key()

    if mode == MODE_CHAT:
        has_msgs = bool(st.session_state.messages)
        placeholder = "Message the model…"
    else:
        chip = st.session_state.excel_ai_chip_text
        st.session_state.excel_ai_chip_text = ""
        if chip:
            st.session_state[widget_key] = chip
        has_msgs = bool(st.session_state.excel_ai_messages)
        placeholder = "Ask about your spreadsheet(s)…"

    if has_msgs:
        st.markdown('<span id="bst-clear-chat-row"></span>', unsafe_allow_html=True)
        _, clear_col, _ = st.columns([1, 1.5, 1])
        with clear_col:
            if st.button(
                "Clear chat",
                key="hub_clear_chat" if mode == MODE_CHAT else "hub_clear_excel",
                use_container_width=True,
            ):
                _start_new_chat(mode)
                st.rerun()

    st.markdown(
        '<p class="bst-input-hint">Enter to send · Shift+Enter for a new line</p>',
        unsafe_allow_html=True,
    )

    if mode == MODE_EXCEL:
        prompt, staged = _render_excel_composer_row(placeholder, widget_key)
        if staged:
            st.rerun()
        # File picker reruns must not send — only Enter submits chat_input.
        if prompt is None:
            return
    else:
        prompt = _render_chat_composer_row(placeholder, widget_key)

    text = str(prompt).strip() if prompt else ""
    if mode == MODE_EXCEL:
        if not text and not _excel_pending_files() and not _excel_files():
            return
    elif not text:
        return

    if mode == MODE_CHAT:
        msgs = st.session_state.messages
        if not msgs or msgs[-1]["role"] != "user" or msgs[-1]["content"] != text:
            _ensure_active_chat_id(MODE_CHAT)
            st.session_state.messages.append({"role": "user", "content": text})
            _persist_current_chat(MODE_CHAT, model, temperature)
            st.session_state[_BST_PENDING_CHAT_GEN] = (model, temperature)
            st.session_state.chat_input_counter += 1
            st.rerun()
        return
    attached_turn = _excel_commit_pending_files()
    files = _excel_files()
    if not files:
        st.warning("Upload at least one spreadsheet first.")
        return
    if not text:
        text = "첨부한 파일을 분석해 주세요."
    msgs = st.session_state.excel_ai_messages
    user_msg: dict[str, Any] = {"role": "user", "content": text}
    if attached_turn:
        user_msg["attached_files"] = attached_turn
    if not (
        msgs
        and msgs[-1]["role"] == "user"
        and msgs[-1]["content"] == text
        and not msgs[-1].get("_hidden")
        and msgs[-1].get("attached_files") == user_msg.get("attached_files")
    ):
        _ensure_active_chat_id(MODE_EXCEL)
        st.session_state.excel_ai_messages.append(user_msg)
        _persist_current_chat(MODE_EXCEL, model, temperature)
    st.session_state[_BST_PENDING_EXCEL_GEN] = (model, temperature)
    st.session_state.excel_ai_input_counter += 1
    st.rerun()


# ── Mode toggle (below input) ─────────────────────────────────────────────────

def _render_mode_toggle(mode: str) -> None:
    """
    Chat mode  → compact pill to enter Excel (narrow center column, not a full-width bar).
    Excel mode → small "×" circle.  Click → exit.
    """
    st.markdown("<div style='height:.3rem'></div>", unsafe_allow_html=True)

    if mode == MODE_CHAT:
        st.markdown('<span id="bst-mode-toggle-chat"></span>', unsafe_allow_html=True)
        _, c, _ = st.columns([2.5, 0.8, 2.5])
        with c:
            if st.button(
                "Excel Agent",
                key="hub_enter_excel",
                type="secondary",
                use_container_width=True,
            ):
                _enter_excel_mode()
                st.rerun()
    else:
        st.markdown('<span id="bst-mode-toggle-excel"></span>', unsafe_allow_html=True)
        # Center the small icon button
        _, c, _ = st.columns([1, 0.18, 1])
        with c:
            if st.button(
                "×",
                key="hub_exit_excel",
                type="secondary",
                help="Back to main chat",
            ):
                _restore_main_hub()
                st.rerun()

    _hub_excel_chip_styles()


# ── Hub page ──────────────────────────────────────────────────────────────────

def _render_hub(model: str, temperature: float) -> None:
    mode = st.session_state.hub_mode
    _ensure_chat_session(mode)

    st.markdown('<span id="bst-hub-page"></span>', unsafe_allow_html=True)

    _, mid, _ = st.columns([0.35, 8, 0.35])
    with mid:
        st.markdown('<span id="bst-hub-anchor"></span>', unsafe_allow_html=True)
        st.markdown(
            '<span id="bst-hub-chat-styling-root" aria-hidden="true"></span>',
            unsafe_allow_html=True,
        )
        _hub_drain_pending_chat_submit(model, temperature)

        if mode == MODE_EXCEL:
            _excel_handle_exec_action(model, temperature)

        if mode == MODE_CHAT:
            visible_msgs = st.session_state.messages
        else:
            visible_msgs = [
                m for m in st.session_state.excel_ai_messages if not m.get("_hidden")
            ]

        has_msgs = bool(visible_msgs)

        if has_msgs:
            st.markdown('<span id="bst-hub-has-msgs"></span>', unsafe_allow_html=True)

        if mode == MODE_EXCEL and has_msgs:
            st.markdown(
                '<span id="bst-hub-excel-mode" aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
        elif mode == MODE_EXCEL:
            st.session_state.pop(_BST_EXCEL_WELCOME_ONCE, None)
            _render_excel_welcome()
            _render_excel_context_empty()
        elif not has_msgs:
            _render_chat_welcome()

        if has_msgs:
            st.markdown('<span id="bst-hub-thread"></span>', unsafe_allow_html=True)
            with st.container(height=520, border=False):
                for m in visible_msgs:
                    with _hub_chat_message(m["role"]):
                        att = m.get("attached_files")
                        names = att if isinstance(att, list) else None
                        _hub_message_body_markdown(
                            m["content"],
                            role=m["role"],
                            attached_files=names,
                        )
                if mode == MODE_EXCEL and st.session_state.get(_BST_EXCEL_CODE_PENDING):
                    _render_excel_code_confirmation()
                elif mode == MODE_CHAT and st.session_state.get(_BST_PENDING_CHAT_GEN):
                    _hub_complete_pending_chat_generation(model, temperature)
                elif mode == MODE_EXCEL and st.session_state.get(_BST_PENDING_EXCEL_GEN):
                    _hub_complete_pending_excel_generation(model, temperature)
            st.markdown('<span id="bst-hub-thread-end"></span>', unsafe_allow_html=True)
            _hub_scroll_to_bottom()

        if mode == MODE_EXCEL:
            _render_excel_downloads()

        _render_hub_composer(mode, model, temperature)
        _render_mode_toggle(mode)


# ── File manager page ─────────────────────────────────────────────────────────

def _fm_file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".csv":
        return "CSV"
    if ext in {".xlsx", ".xlsm"}:
        return "Excel"
    if ext == ".xls":
        return "Excel (legacy)"
    return ext.lstrip(".") or "file"


def _fm_file_size(path: Path) -> str:
    try:
        n = path.stat().st_size
    except OSError:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1_048_576:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1_048_576:.1f} MB"


def _fm_spreadsheet_output_files(out_dir: Path) -> list[Path]:
    """Merge outputs under outputs/ — exclude chats/, personalization.json, etc."""
    return sorted(
        [
            p
            for p in out_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _ALLOWED
        ],
        key=lambda p: p.name.lower(),
    )


_FM_LIB_ICON_SVG = {
    "csv": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm0 1.5L18.5 9H15a1 1 0 0 1-1-1V3.5zM8 12h8v1.5H8V12zm0 3.5h6V17H8v-1.5z"/>'
        "</svg>"
    ),
    "xlsx": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm0 1.5L18.5 9H15a1 1 0 0 1-1-1V3.5zM7 11h3v3H7v-3zm4 0h3v3h-3v-3zm4 0h3v3h-3v-3zM7 15h3v3H7v-3zm4 0h3v3h-3v-3z"/>'
        "</svg>"
    ),
    "xls": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm0 1.5L18.5 9H15a1 1 0 0 1-1-1V3.5zM8 11h8v1.5H8V11zm0 3.5h5V16H8v-1.5z"/>'
        "</svg>"
    ),
    "file": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="currentColor" d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-7-7zm0 2.4L16.6 10H14a1 1 0 0 1-1-1V4.4z"/>'
        "</svg>"
    ),
}


def _fm_library_icon_key(kind: str) -> str:
    low = kind.lower()
    if "csv" in low:
        return "csv"
    if "legacy" in low:
        return "xls"
    if "excel" in low:
        return "xlsx"
    return "file"


def _fm_library_row_html(path: Path, kind: str, size: str, *, is_open: bool) -> str:
    icon_key = _fm_library_icon_key(kind)
    icon_svg = _FM_LIB_ICON_SVG[icon_key]
    safe_name = html.escape(path.name)
    safe_kind = html.escape(kind)
    safe_size = html.escape(size) if size else ""
    meta = f"{safe_kind} · {safe_size}" if safe_size else safe_kind
    open_cls = " bst-lib-card--open" if is_open else ""
    return (
        f'<div class="bst-lib-card{open_cls}">'
        f'<div class="bst-lib-card__icon bst-lib-card__icon--{icon_key}" aria-hidden="true">'
        f"{icon_svg}</div>"
        f'<div class="bst-lib-card__body">'
        f'<div class="bst-lib-card__name" title="{safe_name}">{safe_name}</div>'
        f'<div class="bst-lib-card__meta">{meta}</div>'
        f"</div></div>"
    )


def _fm_library_header(count: int) -> None:
    pill = "0" if count == 0 else str(count)
    desc = (
        "Upload spreadsheets above to build your library."
        if count == 0
        else f"{count} file{'s' if count != 1 else ''} ready to preview or merge."
    )
    st.markdown(
        '<div class="bst-lib-head bst-fm-section bst-fm-section--spaced-top">'
        '<div class="bst-lib-head__text">'
        '<h3 class="bst-lib-head__title">Library</h3>'
        f'<p class="bst-lib-head__desc">{html.escape(desc)}</p>'
        "</div>"
        f'<span class="bst-lib-head__pill" aria-label="File count">{pill}</span>'
        "</div>",
        unsafe_allow_html=True,
    )


def _fm_clear_all_style_hook() -> None:
    """Red Clear-all button JS paint (base styles from hub_theme.css via <head>)."""
    components.html(
        "<script>(function(){"
        "const d=window.parent.document;"
        "const paint=()=>{try{"
        "const root=d.querySelector('#bst-file-manager-content');"
        "const scope=root?.closest('[data-testid=column]')||d;"
        "scope.querySelectorAll('.stButton button,button').forEach((btn)=>{"
        "const label=(btn.innerText||btn.textContent||'').replace(/\\s+/g,' ').trim();"
        "if(label!=='Clear all')return;"
        "btn.classList.add('bst-fm-clear-all-btn');"
        "const s=(k,v)=>btn.style.setProperty(k,v,'important');"
        "s('color','#b91c1c');s('background-color','rgba(239,68,68,0.14)');"
        "s('border','1px solid rgba(220,38,38,0.58)');s('border-radius','10px');"
        "s('font-weight','600');"
        "s('box-shadow','0 1px 3px rgba(239,68,68,0.15)');"
        "btn.querySelectorAll('p,span').forEach((n)=>s('color','inherit'));});"
        "}catch(e){}};"
        "paint();"
        "new MutationObserver(paint).observe(d.body,{childList:true,subtree:true});"
        "setTimeout(paint,40);setTimeout(paint,200);setTimeout(paint,600);"
        "})();</script>",
        height=0,
        scrolling=False,
    )


def _fm_outputs_header(count: int) -> None:
    desc = (
        "Run a merge to generate a file."
        if count == 0
        else f"{count} merged file{'s' if count != 1 else ''} ready to download."
    )
    if count == 0:
        pill_text = "No outputs"
        pill_cls = ""
    else:
        pill_text = f"{count} file{'s' if count != 1 else ''}"
        pill_cls = " bst-merge-head__pill--ready"
    st.markdown(
        '<div class="bst-merge-head bst-fm-section bst-fm-section--spaced-top">'
        '<div class="bst-merge-head__text">'
        '<h3 class="bst-merge-head__title">Outputs</h3>'
        f'<p class="bst-merge-head__desc">{html.escape(desc)}</p>'
        "</div>"
        f'<span class="bst-merge-head__pill{pill_cls}" aria-label="Output count">'
        f"{html.escape(pill_text)}</span>"
        "</div>",
        unsafe_allow_html=True,
    )


def _fm_merge_header(file_count: int) -> None:
    ready = file_count >= 2
    status = "Ready to merge" if ready else "Need 2+ files"
    pill_cls = " bst-merge-head__pill--ready" if ready else ""
    st.markdown(
        '<div class="bst-merge-head bst-fm-section bst-fm-section--spaced-top">'
        '<div class="bst-merge-head__text">'
        '<h3 class="bst-merge-head__title">Merge</h3>'
        '<p class="bst-merge-head__desc">'
        "Combine spreadsheets by key columns. Numeric values are averaged."
        "</p></div>"
        f'<span class="bst-merge-head__pill{pill_cls}" aria-label="Merge status">'
        f"{html.escape(status)} · {file_count} files</span>"
        "</div>",
        unsafe_allow_html=True,
    )


def _fm_merge_step(number: int, title: str, description: str) -> None:
    first = " bst-merge-step--first" if number == 1 else ""
    st.markdown(
        f'<div class="bst-merge-step{first}">'
        f'<span class="bst-merge-step__badge" aria-hidden="true">{number}</span>'
        '<div class="bst-merge-step__text">'
        f'<h4 class="bst-merge-step__title">{html.escape(title)}</h4>'
        f'<p class="bst-merge-step__desc">{html.escape(description)}</p>'
        "</div></div>",
        unsafe_allow_html=True,
    )


def _sidebar_fm_popover_bind() -> None:
    """Merge-tab-style hover popover on the sidebar File Manager button (not Streamlit help)."""
    popover_html = (
        "<strong>Excel File Manager</strong>"
        "<p>Work manually: upload spreadsheets, preview data, merge by keys "
        "with averaging, and download results—without using chat.</p>"
    )
    body_js = popover_html.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "")
    components.html(
        "<script>(function(){"
        "const d=window.parent.document;"
        "const body='" + body_js + "';"
        "let boundBtn=null;let hideTimer=null;"
        "const findBtn=()=>{"
        "const byKey=d.querySelector('[class*=\"st-key-sidebar_open_file_manager\"] button');"
        "if(byKey)return byKey;"
        "const wrap=d.querySelector('[class*=\"st-key-sidebar_open_file_manager\"]');"
        "if(wrap){const b=wrap.querySelector('button');if(b)return b;}"
        "const anchor=d.getElementById('bst-sidebar-fm-nav');"
        "if(!anchor)return null;"
        "let sib=anchor;"
        "for(let j=0;j<8&&sib;j++){"
        "sib=sib.nextElementSibling;"
        "const b=sib&&sib.querySelector?sib.querySelector('button'):null;"
        "if(b)return b;}"
        "return null;};"
        "const ensure=()=>{let p=d.getElementById('bst-sidebar-fm-popover');"
        "if(!p){p=d.createElement('div');p.id='bst-sidebar-fm-popover';"
        "p.className='bst-sidebar-fm-popover';"
        "p.setAttribute('role','tooltip');p.innerHTML=body;"
        "(d.querySelector('.stApp')||d.body).appendChild(p);}"
        "return p;};"
        "const bind=()=>{"
        "const btn=findBtn();const pop=ensure();"
        "if(!btn||btn===boundBtn)return;"
        "boundBtn=btn;"
        "const show=()=>{"
        "if(hideTimer){clearTimeout(hideTimer);hideTimer=null;}"
        "const r=btn.getBoundingClientRect();"
        "const w=Math.min(352,Math.max(260,r.width+40));"
        "pop.style.width=w+'px';"
        "pop.style.left=Math.min(Math.max(8,r.right+10),window.parent.innerWidth-w-8)+'px';"
        "pop.style.top=Math.max(8,r.top)+'px';"
        "pop.classList.add('is-visible');};"
        "const hide=()=>{hideTimer=setTimeout(()=>pop.classList.remove('is-visible'),140);};"
        "btn.addEventListener('mouseenter',show);"
        "btn.addEventListener('mouseleave',hide);"
        "btn.addEventListener('focus',show);"
        "btn.addEventListener('blur',hide);"
        "pop.addEventListener('mouseenter',show);"
        "pop.addEventListener('mouseleave',hide);};"
        "bind();"
        "new MutationObserver(bind).observe(d.body,{childList:true,subtree:true});"
        "[30,120,350,700,1200].forEach((ms)=>setTimeout(bind,ms));"
        "})();</script>",
        height=0,
        scrolling=False,
    )


def _render_sidebar_file_manager_nav() -> None:
    """Sidebar entry for manual upload / merge / download (distinct from hub chat)."""
    active = st.session_state.nav_page == NAV_FILE_MANAGER
    active_cls = " bst-sidebar-fm-anchor--active" if active else ""
    st.markdown(
        '<p class="bst-sidebar-fm-kicker">Prefer manual control?</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<span id="bst-sidebar-fm-nav" class="bst-sidebar-fm-anchor{active_cls}" '
        'aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    if st.button(
        "Excel File Manager",
        key="sidebar_open_file_manager",
        type="secondary",
        use_container_width=True,
    ):
        st.session_state.nav_page = NAV_FILE_MANAGER
        st.rerun()
    st.caption("Upload · preview · merge · download")
    _sidebar_fm_popover_bind()


def _sidebar_show_error(title: str, exc: Exception) -> None:
    st.error(title)
    with st.expander("Error details"):
        st.code(str(exc))


def _fm_ui_enhance() -> None:
    """Tab font-size override + library row card hover (Streamlit 1.57 DOM)."""
    components.html(
        "<script>(function(){"
        "const d=window.parent.document;"
        "const col=()=>d.querySelector('#bst-file-manager-content')"
        "?.closest('[data-testid=column]');"
        "const tabSize='23px';"
        "const styleTabs=()=>{try{"
        "const c=col();if(!c)return;"
        "c.querySelectorAll('[data-testid=stTabs] button[role=tab],"
        "[data-testid=stTabs] [role=tab],[data-testid=stTabs] [data-baseweb=tab]').forEach((el)=>{"
        "el.style.setProperty('font-size',tabSize,'important');"
        "el.style.setProperty('font-weight','600','important');"
        "});"
        "c.querySelectorAll('[data-testid=stTabs] p,[data-testid=stTabs] span').forEach((n)=>{"
        "if(n.closest('[data-testid=stTabs] [data-baseweb=tab-panel]'))return;"
        "n.style.setProperty('font-size',tabSize,'important');"
        "n.style.setProperty('font-weight','600','important');"
        "});}catch(e){}};"
        "const findRow=(anchor)=>{"
        "const inRow=anchor.closest('[data-testid=stHorizontalBlock]');"
        "if(inRow)return inRow;"
        "const box=anchor.closest('[data-testid=stElementContainer]');"
        "if(!box)return null;"
        "let n=box.nextElementSibling;"
        "for(let i=0;i<8&&n;i++){"
        "if(n.matches?.('[data-testid=stHorizontalBlock]'))return n;"
        "const hb=n.querySelector?.('[data-testid=stHorizontalBlock]');"
        "if(hb)return hb;"
        "n=n.nextElementSibling;"
        "}"
        "return null;"
        "};"
        "const bindRows=()=>{try{"
        "const c=col();if(!c)return;"
        "c.querySelectorAll('.bst-fm-file-row').forEach((anchor)=>{"
        "const row=findRow(anchor);if(!row||row.dataset.bstFmBound)return;"
        "row.classList.add('bst-fm-row-card');"
        "if(anchor.classList.contains('bst-fm-library-row')"
        "||anchor.classList.contains('bst-fm-output-row'))"
        "row.classList.add('bst-fm-library-row-card');"
        "row.dataset.bstFmBound='1';"
        "const on=()=>row.classList.add('bst-fm-row--hover');"
        "const off=()=>row.classList.remove('bst-fm-row--hover');"
        "row.addEventListener('mouseenter',on);"
        "row.addEventListener('mouseleave',off);"
        "});}catch(e){}};"
        "const run=()=>{styleTabs();bindRows();};"
        "run();"
        "const root=col();"
        "if(root&&!window.__bstFmUiObs){"
        "window.__bstFmUiObs=new MutationObserver(run);"
        "window.__bstFmUiObs.observe(root,{childList:true,subtree:true});"
        "}"
        "setTimeout(run,40);setTimeout(run,180);setTimeout(run,500);"
        "})();</script>",
        height=0,
        scrolling=False,
    )


def _render_fm_files_tab(up: Path) -> None:
    _fm_section("Upload", "CSV, XLSX, XLSM, or XLS.")
    files = st.file_uploader(
        "Drop files here",
        type=["csv", "xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if files:
        for f in files:
            try:
                name = _safe_name(f.name)
            except ValueError as e:
                st.warning(f"{f.name}: {e}")
                continue
            (up / name).write_bytes(f.getvalue())
            st.success(f"Saved **{name}**")

    st.divider()
    paths = sorted(
        [p for p in up.iterdir() if p.is_file()],
        key=lambda p: p.name.lower(),
    )
    _render_fm_file_list(paths)
    _fm_ui_enhance()


def _render_fm_merge_tab(up: Path, out: Path) -> None:
    st.markdown(
        '<div id="bst-fm-merge-panel" class="bst-merge-panel" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )

    all_files = sorted(
        [p for p in up.iterdir() if p.is_file()],
        key=lambda p: p.name.lower(),
    )
    _fm_merge_header(len(all_files))

    st.markdown(
        '<div class="bst-merge-tip">'
        '<div class="bst-fm-merge-hint">'
        '<span class="bst-fm-merge-hint__trigger" tabindex="0">How merge works</span>'
        '<div class="bst-fm-merge-hint__popover" role="tooltip">'
        "<strong>How merge works</strong>"
        "<p>Rows with the same key columns are grouped. "
        "Numeric columns are averaged; other columns keep the first value.</p>"
        "</div></div>"
        '<ul class="bst-merge-tip__list">'
        "<li>Pick two or more files from your library</li>"
        "<li>Choose key columns to match rows</li>"
        "<li>Run merge — result appears in Outputs</li>"
        "</ul></div>",
        unsafe_allow_html=True,
    )

    if len(all_files) < 2:
        st.markdown(
            '<div class="bst-merge-empty">'
            '<div class="bst-merge-empty__icon" aria-hidden="true">'
            '<svg viewBox="0 0 24 24"><path fill="currentColor" '
            'd="M4 7h7v2H4V7zm9 0h7v2h-7V7zM4 11h4v2H4v-2zm6 0h10v2H10v-2zM4 15h7v2H4v-2zm9 0h7v2h-7v-2z"/></svg>'
            "</div>"
            "<p><strong>Not enough files</strong></p>"
            "<p>Upload at least two spreadsheets on the Files tab, then return here.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        _fm_merge_step(1, "Select files", "Choose inputs and which sheet to read from each workbook.")
        chosen = st.multiselect(
            "Files to merge",
            options=[p.name for p in all_files],
            default=[p.name for p in all_files[: min(5, len(all_files))]],
            label_visibility="collapsed",
        )
        sheet = st.text_input(
            "Sheet name or index (0 = first sheet)",
            value="0",
            label_visibility="visible",
        )
        sheet_val: str | int
        if re.fullmatch(r"\d+", sheet.strip()):
            sheet_val = int(sheet.strip())
        else:
            sheet_val = sheet.strip()

        ref_name = chosen[0] if chosen else all_files[0].name
        cols_preview: list[str] = []
        try:
            cols_preview = list(
                read_table(up / ref_name, sheet_name=sheet_val).columns.astype(str)
            )
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read columns: {e}")

        _fm_merge_step(2, "Keys & output", "Group rows by these columns; set the merged file name.")
        keys = st.multiselect(
            "Key columns",
            options=cols_preview,
            default=cols_preview[:1] if cols_preview else [],
            label_visibility="collapsed",
        )
        out_name = st.text_input("Output filename", value="merged.xlsx")

        _, merge_btn_c, _ = st.columns([4.5, 2, 4.5])
        with merge_btn_c:
            run_merge = st.button(
                "Run merge",
                type="primary",
                use_container_width=True,
                key="fm_run_merge",
            )

        if run_merge:
            if len(chosen) < 2:
                st.error("Select at least two files.")
            elif not keys:
                st.error("Select at least one key column.")
            else:
                try:
                    merged = merge_mean_by_keys(
                        [up / n for n in chosen], keys, sheet_name=sheet_val
                    )
                    p_out = Path((out_name or "merged").strip())
                    if p_out.suffix.lower() != ".xlsx":
                        p_out = Path(p_out.stem + ".xlsx")
                    dest = out / _safe_name(p_out.name)
                    merged.to_excel(dest, index=False, engine="openpyxl")
                    st.markdown(
                        '<div class="bst-merge-result">'
                        '<span class="bst-merge-result__label">Merge complete</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.success(f"Saved **{dest.name}** — {len(merged):,} rows")
                    st.dataframe(merged.head(50), use_container_width=True)
                    st.download_button(
                        "Download result",
                        data=dest.read_bytes(),
                        file_name=dest.name,
                        mime=(
                            "application/vnd.openxmlformats-officedocument"
                            ".spreadsheetml.sheet"
                        ),
                        key=f"dl_{dest.name}",
                    )
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))

    outs = _fm_spreadsheet_output_files(out)
    st.markdown(
        '<hr class="bst-fm-sep bst-fm-merge-outputs-sep" aria-hidden="true">',
        unsafe_allow_html=True,
    )
    _render_fm_outputs(outs, out)


def _fm_spacer(size: str = "md") -> None:
    st.markdown(
        f'<div class="bst-fm-spacer bst-fm-spacer--{size}" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )


def _fm_section(title: str, description: str = "", *, spaced_top: bool = False) -> None:
    top = " bst-fm-section--spaced-top" if spaced_top else ""
    desc = f'<p class="bst-fm-section__desc">{description}</p>' if description else ""
    st.markdown(
        f'<div class="bst-fm-section{top}">'
        f'<h3 class="bst-fm-section__title">{title}</h3>{desc}</div>',
        unsafe_allow_html=True,
    )


def _render_fm_file_list(paths: list[Path]) -> None:
    preview: str | None = st.session_state.get("fm_preview")
    count = len(paths)
    _fm_library_header(count)
    if not paths:
        st.markdown(
            '<div class="bst-lib-empty">'
            '<div class="bst-lib-empty__icon" aria-hidden="true">'
            '<svg viewBox="0 0 24 24"><path fill="currentColor" '
            'd="M4 6h16v12H4V6zm2 2v8h12V8H6zm2 2h8v1.5H8V10zm0 2.5h5V14H8v-1.5z"/></svg>'
            "</div>"
            "<p><strong>No files yet</strong></p>"
            "<p>Drop spreadsheets in the uploader above.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<div id="bst-fm-library-list" class="bst-fm-library-list" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    _fm_library_delete_styles()

    for p in paths:
        kind = _fm_file_kind(p)
        size = _fm_file_size(p)
        is_open = preview == p.name
        info_c, pv_c, del_c = st.columns(
            [5.35, 1.125, 1.125], vertical_alignment="center"
        )
        with info_c:
            st.markdown(
                '<span class="bst-fm-row-anchor bst-fm-file-row bst-fm-library-row" '
                'aria-hidden="true"></span>'
                + _fm_library_row_html(p, kind, size, is_open=is_open),
                unsafe_allow_html=True,
            )
        with pv_c:
            if st.button(
                "Hide" if is_open else "Preview",
                key=f"pv_{p.name}",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state.fm_preview = None if is_open else p.name
                st.rerun()
        with del_c:
            if st.button(
                "Delete",
                key=_fm_del_button_key(p.name),
                type="secondary",
                use_container_width=True,
            ):
                p.unlink(missing_ok=True)
                if st.session_state.get("fm_preview") == p.name:
                    st.session_state.fm_preview = None
                st.rerun()

        if is_open and p.suffix.lower() in _ALLOWED:
            st.markdown(
                '<div class="bst-fm-preview-anchor"></div>'
                '<div class="bst-lib-preview">'
                '<span class="bst-lib-preview__label">Preview</span></div>',
                unsafe_allow_html=True,
            )
            try:
                _render_scrollable_dataframe(read_table(p))
            except Exception as e:  # noqa: BLE001
                st.error(str(e))


def _render_fm_outputs(outs: list[Path], out_dir: Path) -> None:
    count = len(outs)
    st.markdown(
        '<span id="bst-fm-outputs-head" class="bst-fm-outputs-head-anchor" '
        'aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    _fm_outputs_header(count)

    if not outs:
        st.markdown(
            '<div class="bst-lib-empty">'
            '<div class="bst-lib-empty__icon" aria-hidden="true">'
            '<svg viewBox="0 0 24 24"><path fill="currentColor" '
            'd="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-7-7zm0 2.4L16.6 10H14a1 1 0 0 1-1-1V4.4z"/></svg>'
            "</div>"
            "<p><strong>No outputs yet</strong></p>"
            "<p>Run a merge above to save a file here.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<div id="bst-fm-outputs-list" class="bst-fm-outputs-list" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )

    for p in outs:
        kind = _fm_file_kind(p)
        size = _fm_file_size(p)
        info_c, act_c = st.columns([5.4, 2.2], vertical_alignment="center")
        with info_c:
            st.markdown(
                '<span class="bst-fm-row-anchor bst-fm-file-row bst-fm-library-row '
                'bst-fm-output-row" aria-hidden="true"></span>'
                + _fm_library_row_html(p, kind, size, is_open=False),
                unsafe_allow_html=True,
            )
        with act_c:
            if p.suffix.lower() == ".xlsx":
                st.download_button(
                    "Download",
                    data=p.read_bytes(),
                    file_name=p.name,
                    mime=(
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet"
                    ),
                    key=f"dl_out_{p.name}",
                    use_container_width=True,
                )

    _fm_spacer("sm")
    st.markdown(
        '<span id="bst-fm-clear-all-row" class="bst-fm-clear-all-row" '
        'aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    _, clear_c = st.columns([7.05, 1.5])
    with clear_c:
        if st.button(
            "Clear all",
            type="secondary",
            use_container_width=True,
            key="fm_clear_outputs",
        ):
            for p in _fm_spreadsheet_output_files(out_dir):
                p.unlink(missing_ok=True)
            st.success("Outputs cleared.")
            st.rerun()
    _fm_clear_all_style_hook()


def _render_file_manager(up: Path, out: Path) -> None:
    st.markdown('<span id="bst-file-manager-page"></span>', unsafe_allow_html=True)
    components.html(
        "<script>try{const d=window.parent.document;"
        "const main=d.querySelector('section[data-testid=stMain]');"
        "const s=()=>{d.documentElement.scrollTop=0;d.body.scrollTop=0;main?.scrollTo(0,0);};"
        "s();requestAnimationFrame(s);}catch(e){}</script>",
        height=0, scrolling=False,
    )

    if "fm_preview" not in st.session_state:
        st.session_state.fm_preview = None

    _, mid, _ = st.columns([0.7, 3, 0.7])
    with mid:
        st.markdown('<span id="bst-file-manager-content"></span>', unsafe_allow_html=True)
        st.markdown('<div class="bst-fm-top-pad" aria-hidden="true"></div>', unsafe_allow_html=True)

        if st.button("← Back to Hub", key="fm_back_hub", type="secondary"):
            st.session_state.nav_page = NAV_HUB
            st.rerun()

        st.markdown(
            '<header class="bst-fm-header">'
            "<h2>Excel File Manager</h2>"
            "<p>Upload, preview, merge spreadsheets, and download results.</p>"
            "</header>",
            unsafe_allow_html=True,
        )
        st.markdown('<div class="bst-fm-header-gap" aria-hidden="true"></div>', unsafe_allow_html=True)

        st.markdown('<span id="bst-fm-tabs-anchor"></span>', unsafe_allow_html=True)
        st.markdown(
            "<style>"
            "section[data-testid=stMain]:has(#bst-file-manager-page) "
            "div[data-testid=column]:has(#bst-file-manager-content) "
            "[data-testid=stTabs] button[role=tab],"
            "section[data-testid=stMain]:has(#bst-file-manager-page) "
            "div[data-testid=column]:has(#bst-file-manager-content) "
            "[data-testid=stTabs] [role=tab]{"
            "font-size:23px!important;font-weight:600!important;"
            "}"
            "section[data-testid=stMain]:has(#bst-file-manager-page) "
            "div[data-testid=column]:has(#bst-file-manager-content) "
            "[data-testid=stTabs] [role=tab] p{"
            "font-size:23px!important;font-weight:600!important;"
            "}"
            "</style>",
            unsafe_allow_html=True,
        )
        tab_files, tab_merge = st.tabs(["Files", "Merge"])
        _fm_ui_enhance()
        with tab_files:
            _render_fm_files_tab(up)
        with tab_merge:
            _render_fm_merge_tab(up, out)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    page_icon: str = str(_FAVICON) if _FAVICON.is_file() else "🦦"
    st.set_page_config(
        page_title="Basic Software Technology",
        page_icon=page_icon,
        layout="wide",
    )
    # Profile modal saves queue here; run before hydrate so disk reload cannot win.
    _process_profile_save_pending()
    _init_state()
    inject_hub_theme()

    up = uploads_dir()
    out = outputs_dir()

    with st.sidebar:
        st.header("Ollama")
        st.session_state.ollama_base = st.text_input(
            "Base URL", value=st.session_state.ollama_base
        )
        st.caption(
            "Default: `http://127.0.0.1:11434`  \n"
            "WinError 10061 = Ollama not running."
        )

        if st.button("Test connection", use_container_width=True, key="ollama_test"):
            try:
                list_models(st.session_state.ollama_base)
                st.success("Connection OK")
            except Exception as e:  # noqa: BLE001
                _sidebar_show_error("Could not reach Ollama.", e)

        if st.button("List models", use_container_width=True, key="ollama_models_btn"):
            try:
                st.session_state.ollama_models = list_models(st.session_state.ollama_base)
                models = st.session_state.ollama_models
                cur = st.session_state.model_name
                if cur in models:
                    st.session_state[BST_INSTALLED_MODEL_PICK_KEY] = cur
                elif models:
                    first = models[0]
                    st.session_state[BST_INSTALLED_MODEL_PICK_KEY] = first
                    st.session_state.model_name = first
                st.success(f"Found {len(st.session_state.ollama_models)} model(s)")
            except Exception as e:  # noqa: BLE001
                _sidebar_show_error("Could not list models.", e)

        if st.session_state.get("ollama_models"):
            models = st.session_state.ollama_models
            pick = st.session_state.get(BST_INSTALLED_MODEL_PICK_KEY)
            if pick not in models:
                cur = st.session_state.model_name
                if cur in models:
                    st.session_state[BST_INSTALLED_MODEL_PICK_KEY] = cur
                else:
                    st.session_state[BST_INSTALLED_MODEL_PICK_KEY] = models[0]
                    st.session_state.model_name = models[0]
            st.selectbox(
                "Installed models",
                options=models,
                key=BST_INSTALLED_MODEL_PICK_KEY,
                on_change=_on_installed_model_pick_change,
            )

        st.text_input("Model", key="model_name")
        temperature = st.slider("Temperature", 0.0, 1.5, 0.7, 0.05)

        st.divider()
        _render_sidebar_personalization()

        st.divider()
        _render_sidebar_chat_history()

        st.divider()
        _render_sidebar_file_manager_nav()

        st.divider()
        st.caption("Favicon attribution")
        st.markdown(
            f'<p style="font-size:0.8rem;margin:0;">{FLATICON_OTTER_ATTR_HTML}</p>',
            unsafe_allow_html=True,
        )

    _render_floating_profile_control()

    if st.session_state.nav_page == NAV_HUB:
        _render_hub(st.session_state.model_name, temperature)
    else:
        _render_file_manager(up, out)


if __name__ == "__main__":
    main()
