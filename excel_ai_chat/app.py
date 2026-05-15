"""Streamlit: Ollama chat, Excel uploads, merge (mean by keys), Markdown export."""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from excel_ai_chat.excel_tools import merge_mean_by_keys, read_table
from excel_ai_chat.ollama_client import chat, list_models
from excel_ai_chat.paths import default_ollama_base, outputs_dir, uploads_dir
from excel_ai_chat.theme import inject_hub_theme

_ALLOWED = {".csv", ".xlsx", ".xlsm", ".xls"}

NAV_HUB = "hub"
NAV_FILE_MANAGER = "file_manager"

MODE_CHAT = "chat"
MODE_EXCEL = "excel"

CHAT_COMPOSER_KEY = "hub_composer"

WELCOME_HEADING = "Welcome to our basic software technology"
CHAT_TAGLINES: tuple[str, ...] = (
    "How can I help you today?",
    "Ask me anything — I'm here to assist.",
    "Try a question or open Analyze Excel for spreadsheets.",
)

FLATICON_OTTER_ATTR_HTML = (
    '<a href="https://www.flaticon.com/free-icons/otter" title="otter">'
    "otter icons created by iconfield - Flaticon</a>"
)

_FAVICON = Path(__file__).resolve().parent / "static" / "favicon.png"

_WAITING_HTML = """<div class="bst-wait-wrap"><div class="bst-wait-line">
<span class="bst-wait-label">Generating a reply</span>
<span class="bst-wait-dots"><b>·</b><b>·</b><b>·</b></span>
</div></div>"""

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


_FM_LIB_DELETE_BTN_CSS = (
    '.stApp [class*="st-key-bst_fm_del_"] .stButton>button[kind="secondary"]{'
    "color:#b91c1c!important;"
    "background-color:rgba(239,68,68,0.12)!important;"
    "border:1px solid rgba(220,38,38,0.55)!important;"
    "border-radius:8px!important;"
    "font-weight:600!important;"
    "box-shadow:0 1px 2px rgba(239,68,68,0.1)!important;"
    "}"
    '.stApp [class*="st-key-bst_fm_del_"] .stButton>button[kind="secondary"] p,'
    '.stApp [class*="st-key-bst_fm_del_"] .stButton>button[kind="secondary"] span{'
    "color:inherit!important;"
    "}"
    '.stApp [class*="st-key-bst_fm_del_"] .stButton>button[kind="secondary"]:hover,'
    '.stApp [class*="st-key-bst_fm_del_"] .stButton>button[kind="secondary"]:focus-visible{'
    "color:#fff!important;"
    "background-color:#dc2626!important;"
    "border-color:#b91c1c!important;"
    "box-shadow:0 3px 10px rgba(220,38,38,0.32)!important;"
    "}"
)


def _fm_library_delete_styles() -> None:
    """Red Delete buttons via Streamlit .st-key-* classes (works on 1.57)."""
    st.html(f"<style>{_FM_LIB_DELETE_BTN_CSS}</style>")
    css_js = _FM_LIB_DELETE_BTN_CSS.replace("\\", "\\\\").replace("'", "\\'")
    components.html(
        "<script>(function(){"
        "const d=window.parent.document;"
        "const id='bst-lib-delete-style';"
        "if(!d.getElementById(id)){"
        "const el=d.createElement('style');el.id=id;"
        f"el.textContent='{css_js}';"
        "d.head.appendChild(el);}"
        "const paint=(btn)=>{if(!btn)return;"
        "const s=(k,v)=>btn.style.setProperty(k,v,'important');"
        "const base=()=>{"
        "s('color','#b91c1c');s('background-color','rgba(239,68,68,0.12)');"
        "s('border','1px solid rgba(220,38,38,0.55)');"
        "s('font-weight','600');"
        "s('box-shadow','0 1px 2px rgba(239,68,68,0.1)');"
        "btn.querySelectorAll('p,span').forEach((n)=>s('color','inherit'));};"
        "const hover=()=>{"
        "s('color','#fff');s('background-color','#dc2626');"
        "s('border-color','#b91c1c');"
        "s('box-shadow','0 3px 10px rgba(220,38,38,0.32)');};"
        "base();"
        "if(!btn.dataset.bstDelFx){btn.dataset.bstDelFx='1';"
        "btn.addEventListener('mouseenter',hover);"
        "btn.addEventListener('mouseleave',base);}};"
        "const run=()=>{"
        "d.querySelectorAll('[class*=\"st-key-bst_fm_del_\"]').forEach((w)=>{"
        "const btn=w.matches('button')?w:w.querySelector('button');"
        "paint(btn);});};"
        "run();"
        "new MutationObserver(run).observe(d.body,{childList:true,subtree:true});"
        "setTimeout(run,30);setTimeout(run,200);setTimeout(run,700);"
        "})();</script>",
        height=0,
        scrolling=False,
    )


def _purge_hub_widget_keys() -> None:
    """Remove hub input / uploader widget state so the next paint matches a fresh load."""
    drop = {CHAT_COMPOSER_KEY, "excel_ai_uploader"}
    for key in list(st.session_state.keys()):
        if not isinstance(key, str):
            continue
        if key in drop or key.startswith(("hub_composer", "hub_chat_")):
            del st.session_state[key]


def _restore_main_hub() -> None:
    """Excel exit → identical to first-load main hub (chat home)."""
    st.session_state.hub_mode = MODE_CHAT
    st.session_state.excel_ai_df = None
    st.session_state.excel_ai_file_name = ""
    st.session_state.excel_ai_messages = []
    st.session_state.excel_ai_chip_text = ""
    st.session_state.excel_ai_input_counter = 0
    st.session_state.chat_input_counter = 0
    _purge_hub_widget_keys()


def _enter_excel_mode() -> None:
    st.session_state.hub_mode = MODE_EXCEL
    _purge_hub_widget_keys()


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "messages":               [],
        "ollama_base":            default_ollama_base(),
        "nav_page":               NAV_HUB,
        "hub_mode":               MODE_CHAT,
        "chat_input_counter":     0,
        "excel_ai_df":            None,
        "excel_ai_file_name":     "",
        "excel_ai_messages":      [],
        "excel_ai_input_counter": 0,
        "excel_ai_chip_text":     "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Excel helpers ─────────────────────────────────────────────────────────────

def _process_upload(uploaded: Any) -> None:
    if uploaded is None or st.session_state.excel_ai_file_name == uploaded.name:
        return
    try:
        suffix = Path(uploaded.name).suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(uploaded)
        elif suffix in {".xlsx", ".xlsm"}:
            df = pd.read_excel(uploaded, engine="openpyxl")
        else:
            df = pd.read_excel(uploaded)
        st.session_state.excel_ai_df = df
        st.session_state.excel_ai_file_name = uploaded.name
        st.session_state.excel_ai_messages = []
        st.session_state.excel_ai_input_counter += 1
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not read file: {e}")


def _render_suggest_chips() -> None:
    st.markdown('<span id="bst-suggest-chips"></span>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    for i, (label, prompt) in enumerate(_SUGGEST_CHIPS):
        with c1 if i % 2 == 0 else c2:
            if st.button(label, key=f"chip_{i}", use_container_width=True):
                st.session_state.excel_ai_chip_text = prompt
                st.session_state.excel_ai_input_counter += 1
                st.rerun()


def _render_excel_context_empty() -> None:
    """File uploader + file badge + chips — shown in empty state."""
    df: pd.DataFrame | None = st.session_state.excel_ai_df

    badge = (
        f"<p style='text-align:center;color:#6b7280;font-size:.88rem;"
        f"margin:.2rem 0 .5rem;'>{st.session_state.excel_ai_file_name}"
        f" &nbsp;·&nbsp; {len(df):,} rows &times; {len(df.columns)} cols</p>"
        if df is not None
        else "<p style='text-align:center;color:#9ca3af;font-size:.88rem;"
             "margin:.2rem 0 .65rem;'>Upload a spreadsheet to get started</p>"
    )
    st.markdown(badge, unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "CSV / Excel",
        type=["csv", "xlsx", "xlsm", "xls"],
        key="excel_ai_uploader",
        label_visibility="collapsed",
    )
    _process_upload(uploaded)

    if df is not None:
        _render_suggest_chips()

    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)


def _render_excel_context_compact() -> None:
    """Minimal file info + optional preview — shown above messages."""
    df: pd.DataFrame | None = st.session_state.excel_ai_df
    uploaded = st.file_uploader(
        "Replace file",
        type=["csv", "xlsx", "xlsm", "xls"],
        key="excel_ai_uploader",
        label_visibility="collapsed",
    )
    _process_upload(uploaded)
    if df is not None:
        st.caption(
            f"**{st.session_state.excel_ai_file_name}**"
            f" &nbsp;·&nbsp; {len(df):,} rows × {len(df.columns)} cols"
        )
        with st.expander("Data preview"):
            st.dataframe(df.head(10), use_container_width=True)


# ── Submission handlers ───────────────────────────────────────────────────────

def _submit_chat(model: str, temperature: float, prompt: str) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        slot = st.empty()
        slot.markdown(_WAITING_HTML, unsafe_allow_html=True)
        try:
            reply = chat(
                st.session_state.ollama_base,
                model,
                st.session_state.messages,
                temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            reply = f"**Error**\n\n{e}"
        finally:
            slot.empty()
        st.markdown(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.rerun()


def _submit_excel(model: str, temperature: float, df: pd.DataFrame, prompt: str) -> None:
    with st.chat_message("user"):
        st.markdown(prompt)

    if not st.session_state.excel_ai_messages:
        csv_str = df.head(50).to_csv(index=False)
        first = (
            f"Here is the data from '{st.session_state.excel_ai_file_name}' "
            f"({len(df):,} rows × {len(df.columns)} cols, CSV format):\n\n"
            f"```\n{csv_str}```\n\n"
            f"Using the data above, please handle this request:\n\n{prompt}"
        )
        st.session_state.excel_ai_messages.append(
            {"role": "user", "content": first, "_hidden": True}
        )
    else:
        st.session_state.excel_ai_messages.append({"role": "user", "content": prompt})

    api_msgs = [
        {k: v for k, v in m.items() if k != "_hidden"}
        for m in st.session_state.excel_ai_messages
    ]

    with st.chat_message("assistant"):
        slot = st.empty()
        slot.markdown(_WAITING_HTML, unsafe_allow_html=True)
        try:
            reply = chat(
                st.session_state.ollama_base, model, api_msgs, temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            reply = f"**Error**\n\n{e}"
        finally:
            slot.empty()
        st.markdown(reply)

    st.session_state.excel_ai_messages.append({"role": "assistant", "content": reply})
    st.rerun()


# ── Hub (single layout; main home == after Excel exit) ─────────────────────────

def _render_chat_welcome() -> None:
    st.markdown(
        f'<h1 class="bst-welcome-type" aria-label="{html.escape(WELCOME_HEADING)}">'
        f'<span class="bst-welcome-type__text">{html.escape(WELCOME_HEADING)}</span>'
        '<span class="bst-welcome-type__caret" aria-hidden="true"></span>'
        "</h1>",
        unsafe_allow_html=True,
    )
    tagline_lines = "".join(
        f'<span class="bst-tagline-cycle__line">{html.escape(line)}</span>'
        for line in CHAT_TAGLINES
    )
    st.markdown(
        f'<p class="bst-hub-tagline bst-tagline-cycle" aria-live="polite">'
        f"{tagline_lines}</p>",
        unsafe_allow_html=True,
    )


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
        placeholder = "Ask about your spreadsheet…"

    if has_msgs:
        st.markdown('<span id="bst-clear-chat-row"></span>', unsafe_allow_html=True)
        _, clear_col, _ = st.columns([1, 1.5, 1])
        with clear_col:
            if st.button(
                "Clear chat",
                key="hub_clear_chat" if mode == MODE_CHAT else "hub_clear_excel",
                use_container_width=True,
            ):
                if mode == MODE_CHAT:
                    st.session_state.messages = []
                    st.session_state.chat_input_counter += 1
                else:
                    st.session_state.excel_ai_messages = []
                    st.session_state.excel_ai_input_counter += 1
                _purge_hub_widget_keys()
                st.rerun()

    st.markdown(
        '<p class="bst-input-hint">Enter to send · Shift+Enter for a new line</p>',
        unsafe_allow_html=True,
    )
    prompt = st.chat_input(placeholder, key=widget_key, width="stretch")

    if not prompt or not str(prompt).strip():
        return
    text = str(prompt).strip()
    if mode == MODE_CHAT:
        _submit_chat(model, temperature, text)
        return
    df: pd.DataFrame | None = st.session_state.excel_ai_df
    if df is None:
        st.warning("Upload a spreadsheet first.")
    else:
        _submit_excel(model, temperature, df, text)


# ── Mode toggle (below input) ─────────────────────────────────────────────────

def _render_mode_toggle(mode: str) -> None:
    """
    Chat mode  → "Analyze Excel" pill.  Click → enter Excel mode.
    Excel mode → small "×" circle.  Click → exit.
    Both are centered below the input bar.
    """
    st.markdown("<div style='height:.3rem'></div>", unsafe_allow_html=True)

    if mode == MODE_CHAT:
        st.markdown('<span id="bst-mode-toggle-chat"></span>', unsafe_allow_html=True)
        _, c, _ = st.columns([0.7, 3, 0.7])
        with c:
            if st.button(
                "Analyze Excel",
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


# ── Hub page ──────────────────────────────────────────────────────────────────

def _render_hub(model: str, temperature: float) -> None:
    mode = st.session_state.hub_mode

    if mode == MODE_CHAT:
        visible_msgs = st.session_state.messages
    else:
        visible_msgs = [
            m for m in st.session_state.excel_ai_messages if not m.get("_hidden")
        ]

    has_msgs = bool(visible_msgs)

    st.markdown('<span id="bst-hub-page"></span>', unsafe_allow_html=True)

    _, mid, _ = st.columns([0.7, 3, 0.7])
    with mid:
        st.markdown('<span id="bst-hub-anchor"></span>', unsafe_allow_html=True)
        if has_msgs:
            st.markdown('<span id="bst-hub-has-msgs"></span>', unsafe_allow_html=True)

        if mode == MODE_EXCEL and has_msgs:
            _render_excel_context_compact()
        elif mode == MODE_EXCEL:
            st.markdown(f"# {WELCOME_HEADING}")
            st.markdown(
                '<p class="bst-hub-tagline">'
                "Excel mode — upload a file and ask about its data."
                "</p>",
                unsafe_allow_html=True,
            )
            _render_excel_context_empty()
        elif not has_msgs:
            _render_chat_welcome()

        if has_msgs:
            st.markdown('<span id="bst-hub-thread"></span>', unsafe_allow_html=True)
            with st.container(height=520, border=False):
                for m in visible_msgs:
                    with st.chat_message(m["role"]):
                        st.markdown(m["content"])
            st.markdown('<span id="bst-hub-thread-end"></span>', unsafe_allow_html=True)
            _hub_scroll_to_bottom()

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
    """Inject red Clear-all styles into parent document (CSS + direct button paint)."""
    components.html(
        "<script>(function(){"
        "const d=window.parent.document;"
        "const css='.stApp button.bst-fm-clear-all-btn,'"
        "'.stApp div:has(#bst-fm-clear-all-row)~div .stButton>button{"
        "color:#b91c1c!important;background-color:rgba(239,68,68,0.14)!important;"
        "border:1px solid rgba(220,38,38,0.58)!important;border-radius:10px!important;"
        "font-weight:600!important;box-shadow:0 1px 3px rgba(239,68,68,0.15)!important;}"
        "'.stApp button.bst-fm-clear-all-btn:hover,'"
        "'.stApp div:has(#bst-fm-clear-all-row)~div .stButton>button:hover{"
        "color:#fff!important;background-color:#dc2626!important;"
        "border-color:#b91c1c!important;"
        "box-shadow:0 3px 10px rgba(220,38,38,0.35)!important;}"
        "'.stApp button.bst-fm-clear-all-btn p{color:inherit!important;}';"
        "if(!d.getElementById('bst-clear-all-red-css')){"
        "const el=d.createElement('style');el.id='bst-clear-all-red-css';"
        "el.textContent=css;d.head.appendChild(el);}"
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

    outs = sorted(
        [p for p in out.iterdir() if p.is_file()],
        key=lambda p: p.name.lower(),
    )
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
                st.dataframe(read_table(p).head(10), use_container_width=True)
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
            for p in list(out_dir.iterdir()):
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
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
            "<h2>File Manager</h2>"
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
    _init_state()
    inject_hub_theme()

    up = uploads_dir()
    out = outputs_dir()

    with st.sidebar:
        st.header("Ollama")
        st.session_state.ollama_base = st.text_input(
            "Base URL", value=st.session_state.ollama_base
        )
        model_default = st.session_state.get("model_name", "llama3.2")
        model = st.text_input("Model", value=model_default)
        st.session_state.model_name = model
        temperature = st.slider("Temperature", 0.0, 1.5, 0.7, 0.05)
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
                st.success(f"Found {len(st.session_state.ollama_models)} model(s)")
            except Exception as e:  # noqa: BLE001
                _sidebar_show_error("Could not list models.", e)

        if "ollama_models" in st.session_state and st.session_state.ollama_models:
            st.selectbox(
                "Installed models",
                options=st.session_state.ollama_models,
                key="_model_pick",
            )

        st.divider()
        if st.button("File Manager", use_container_width=True):
            st.session_state.nav_page = NAV_FILE_MANAGER
            st.rerun()

        st.divider()
        st.caption("Favicon attribution")
        st.markdown(
            f'<p style="font-size:0.8rem;margin:0;">{FLATICON_OTTER_ATTR_HTML}</p>',
            unsafe_allow_html=True,
        )

    if st.session_state.nav_page == NAV_HUB:
        _render_hub(model, temperature)
    else:
        _render_file_manager(up, out)


if __name__ == "__main__":
    main()
