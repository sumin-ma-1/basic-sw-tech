"""Streamlit: Ollama chat, Excel uploads, merge (mean by keys), Markdown export."""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from excel_ai_chat.excel_tools import merge_mean_by_keys, read_table
from excel_ai_chat.ollama_client import chat, list_models
from excel_ai_chat.paths import default_ollama_base, outputs_dir, uploads_dir

_ALLOWED = {".csv", ".xlsx", ".xlsm", ".xls"}


def _safe_name(name: str) -> str:
    base = Path(name).name
    if not base or base.startswith(".") or ".." in base:
        raise ValueError("Invalid file name.")
    if Path(base).suffix.lower() not in _ALLOWED:
        raise ValueError(f"Allowed types: {', '.join(sorted(_ALLOWED))}")
    return base


def _init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "ollama_base" not in st.session_state:
        st.session_state.ollama_base = default_ollama_base()
    if "_welcome_typed" not in st.session_state:
        st.session_state._welcome_typed = False


WELCOME_HEADING = "Welcome to our basic software technology"

# Flaticon otter (수달) icon attribution
FLATICON_OTTER_ATTR_HTML = (
    '<a href="https://www.flaticon.com/free-icons/otter" title="otter icons">'
    "otter icons created by iconfield - Flaticon</a>"
)


def _inject_chat_wait_styles() -> None:
    """Inject CSS for the chat-tab waiting dots (once per session)."""
    if st.session_state.get("_bst_chat_wait_css"):
        return
    st.markdown(
        """
<style>
@keyframes bst-wait-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}
@keyframes bst-wait-dot {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
  30% { transform: translateY(-6px); opacity: 1; }
}
.bst-wait-wrap {
  font-size: 0.95rem;
  color: #5c6570;
  margin: 0.1rem 0 0.5rem 0;
}
.bst-wait-line {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}
.bst-wait-label {
  animation: bst-wait-pulse 1.25s ease-in-out infinite;
}
.bst-wait-dots {
  display: inline-flex;
  gap: 1px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.bst-wait-dots b {
  display: inline-block;
  width: 0.45em;
  text-align: center;
  font-weight: 700;
  animation: bst-wait-dot 0.95s ease-in-out infinite;
}
.bst-wait-dots b:nth-child(2) { animation-delay: 0.12s; }
.bst-wait-dots b:nth-child(3) { animation-delay: 0.24s; }
</style>
""",
        unsafe_allow_html=True,
    )
    st.session_state._bst_chat_wait_css = True


_ASSISTANT_WAITING_HTML = """<div class="bst-wait-wrap">
<div class="bst-wait-line">
<span class="bst-wait-label">Generating a reply</span>
<span class="bst-wait-dots"><b>·</b><b>·</b><b>·</b></span>
</div>
</div>"""


def _welcome_stream() -> Iterator[str]:
    """Markdown H1, one character at a time for st.write_stream."""
    yield "# "
    for ch in WELCOME_HEADING:
        yield ch
        time.sleep(0.028)


def _fill_welcome_heading_slot(welcome_slot: Any) -> None:
    """Type into the top placeholder only; call after the rest of the layout is built."""
    with welcome_slot:
        if st.session_state._welcome_typed:
            st.markdown(f"# {WELCOME_HEADING}\n")
            return
        st.write_stream(_welcome_stream)
        st.session_state._welcome_typed = True


def _messages_to_markdown(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        label = "User" if role == "user" else "Assistant" if role == "assistant" else role
        parts.append(f"## {label}\n\n{content}\n")
    return "\n".join(parts).strip() + "\n"


_FAVICON = Path(__file__).resolve().parent / "static" / "favicon.png"


def main() -> None:
    page_icon: str = str(_FAVICON) if _FAVICON.is_file() else "🦦"
    st.set_page_config(
        page_title="Basic Software Technology",
        page_icon=page_icon,
        layout="wide",
    )
    _init_state()

    welcome_slot = st.empty()

    st.caption(
        "Use a venv, then `pip install -e .` and run `excel-ai-chat` (default port **8502**), or from the repo root: "
        "`python -m streamlit run excel_ai_chat/app.py` (see `.streamlit/config.toml`)."
    )

    up = uploads_dir()
    out = outputs_dir()

    with st.sidebar:
        st.header("Ollama")
        st.session_state.ollama_base = st.text_input("Base URL", value=st.session_state.ollama_base)
        model_default = st.session_state.get("model_name", "llama3.2")
        model = st.text_input("Model name", value=model_default)
        st.session_state.model_name = model
        temperature = st.slider("temperature", 0.0, 1.5, 0.7, 0.05)
        st.caption(
            "Default API base is `http://127.0.0.1:11434`. "
            "WinError 10061 usually means Ollama is not running, the URL is wrong, or a firewall is blocking the port."
        )
        if st.button("Test connection", help="GET /api/tags — verify Ollama responds"):
            try:
                list_models(st.session_state.ollama_base)
                st.success("Connected to Ollama.")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
        if st.button("Refresh model list"):
            try:
                models = list_models(st.session_state.ollama_base)
                st.session_state["ollama_models"] = models
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
        if "ollama_models" in st.session_state and st.session_state.ollama_models:
            st.selectbox("Installed models (reference)", options=st.session_state.ollama_models, key="_model_pick")

        st.divider()
        st.caption("Favicon attribution")
        st.markdown(
            f'<p style="font-size:0.8rem;margin:0;">{FLATICON_OTTER_ATTR_HTML}</p>',
            unsafe_allow_html=True,
        )

    tab_chat, tab_files, tab_merge = st.tabs(["Chat", "Files", "Merge sheets"])

    with tab_chat:
        _inject_chat_wait_styles()
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        prompt = st.chat_input("Type a message…")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                wait_slot = st.empty()
                wait_slot.markdown(_ASSISTANT_WAITING_HTML, unsafe_allow_html=True)
                try:
                    with st.spinner("Waiting for the model…"):
                        reply = chat(
                            st.session_state.ollama_base,
                            model,
                            st.session_state.messages,
                            temperature=temperature,
                        )
                except Exception as e:  # noqa: BLE001
                    reply = f"**Error**\n\n{e}"
                finally:
                    wait_slot.empty()
                st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

        st.divider()
        md = _messages_to_markdown(st.session_state.messages)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "Download chat as .md",
                data=md.encode("utf-8"),
                file_name="chat.md",
                mime="text/markdown",
                disabled=not st.session_state.messages,
            )
        with c2:
            if st.button("Save chat to outputs", disabled=not st.session_state.messages):
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                p = out / f"chat_{ts}.md"
                p.write_text(md, encoding="utf-8")
                st.success(f"Saved: {p}")
        with c3:
            if st.button("Clear chat"):
                st.session_state.messages = []
                st.rerun()

    with tab_files:
        st.subheader("Upload")
        files = st.file_uploader(
            "CSV / Excel",
            type=["csv", "xlsx", "xlsm", "xls"],
            accept_multiple_files=True,
        )
        if files:
            for f in files:
                try:
                    name = _safe_name(f.name)
                except ValueError as e:
                    st.warning(f"{f.name}: {e}")
                    continue
                dest = up / name
                dest.write_bytes(f.getvalue())
                st.success(f"Saved: {dest.name}")

        st.subheader("Uploaded files")
        paths = sorted(up.iterdir(), key=lambda p: p.name.lower())
        if not paths:
            st.info("The uploads folder is empty.")
        for p in paths:
            cols = st.columns([4, 1, 1])
            cols[0].write(p.name)
            if cols[1].button("Delete", key=f"del_{p.name}"):
                p.unlink(missing_ok=True)
                st.rerun()
            if p.suffix.lower() in {".xlsx", ".xlsm", ".xls", ".csv"} and cols[2].button("Preview", key=f"pv_{p.name}"):
                try:
                    head = read_table(p).head(10)
                    st.dataframe(head, use_container_width=True)
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))

    with tab_merge:
        st.markdown(
            "Merge multiple files: rows with the same **key columns** are grouped; **numeric** columns use the "
            "**mean**, other columns use the **first** value."
        )
        all_files = sorted([p for p in up.iterdir() if p.is_file()], key=lambda p: p.name.lower())
        if len(all_files) < 2:
            st.warning("Upload at least two files into `uploads/` to merge.")
        else:
            chosen = st.multiselect("Files to merge", options=[p.name for p in all_files], default=[p.name for p in all_files[:5]])
            sheet = st.text_input("Sheet name or index (0 = first sheet)", value="0")
            sheet_val: str | int
            if re.fullmatch(r"\d+", sheet.strip()):
                sheet_val = int(sheet.strip())
            else:
                sheet_val = sheet.strip()

            ref_name = chosen[0] if chosen else all_files[0].name
            ref_path = up / ref_name
            cols_preview: list[str] = []
            try:
                cols_preview = list(read_table(ref_path, sheet_name=sheet_val).columns.astype(str))
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not read column list: {e}")

            keys = st.multiselect("Key columns", options=cols_preview, default=cols_preview[:1] if cols_preview else [])
            out_name = st.text_input("Output file name", value="merged.xlsx")

            if st.button("Run merge"):
                if len(chosen) < 2:
                    st.error("Select at least two files.")
                elif not keys:
                    st.error("Select at least one key column.")
                else:
                    try:
                        paths_sel = [up / n for n in chosen]
                        merged = merge_mean_by_keys(paths_sel, keys, sheet_name=sheet_val)
                        out_raw = (out_name or "merged").strip()
                        p_out = Path(out_raw)
                        if p_out.suffix.lower() != ".xlsx":
                            p_out = Path(p_out.stem + ".xlsx")
                        dest = out / _safe_name(p_out.name)
                        merged.to_excel(dest, index=False, engine="openpyxl")
                        st.success(f"Saved: {dest}")
                        st.dataframe(merged.head(50), use_container_width=True)
                        st.download_button(
                            "Download result",
                            data=dest.read_bytes(),
                            file_name=dest.name,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{dest.name}",
                        )
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))

        st.divider()
        st.subheader("Clear outputs")
        outs = sorted(out.iterdir(), key=lambda p: p.name.lower())
        if st.button("Empty outputs folder"):
            for p in outs:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            st.success("Outputs folder cleared.")
            st.rerun()
        for p in outs:
            st.write(p.name)

    _fill_welcome_heading_slot(welcome_slot)


if __name__ == "__main__":
    main()
