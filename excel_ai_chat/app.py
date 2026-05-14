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

# Flaticon 고래 아이콘 사용 시 출처 표기
FLATICON_WHALE_ATTR_HTML = (
    '<a href="https://www.flaticon.com/kr/free-icons/" title="고래 아이콘">고래 아이콘 제작자: iconfield - Flaticon</a>'
)


def _welcome_stream() -> Iterator[str]:
    """Markdown H1 + 한 글자씩 (st.write_stream용)."""
    yield "# "
    for ch in WELCOME_HEADING:
        yield ch
        time.sleep(0.028)


def _fill_welcome_heading_slot(welcome_slot: Any) -> None:
    """맨 위 슬롯에만 타이핑(나머지 UI는 이미 실행된 뒤 호출)."""
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
    page_icon: str = str(_FAVICON) if _FAVICON.is_file() else "🦫"
    st.set_page_config(
        page_title="Basic Software Technology",
        page_icon=page_icon,
        layout="wide",
    )
    _init_state()

    welcome_slot = st.empty()

    st.caption(
        "가상환경에서 `pip install -e .` 후 `excel-ai-chat`(기본 포트 8502) 또는 "
        "프로젝트 루트에서 `python -m streamlit run excel_ai_chat/app.py`(.streamlit/config.toml)"
    )

    up = uploads_dir()
    out = outputs_dir()

    with st.sidebar:
        st.header("Ollama")
        st.session_state.ollama_base = st.text_input("Base URL", value=st.session_state.ollama_base)
        model_default = st.session_state.get("model_name", "llama3.2")
        model = st.text_input("모델 이름", value=model_default)
        st.session_state.model_name = model
        temperature = st.slider("temperature", 0.0, 1.5, 0.7, 0.05)
        st.caption(
            "기본 API 주소는 `http://127.0.0.1:11434` 입니다. "
            "WinError 10061이면 Ollama가 꺼져 있거나 URL/방화벽 문제일 수 있습니다."
        )
        if st.button("연결 테스트", help="GET /api/tags 로 Ollama 응답 확인"):
            try:
                list_models(st.session_state.ollama_base)
                st.success("Ollama에 연결되었습니다.")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
        if st.button("모델 목록 새로고침"):
            try:
                models = list_models(st.session_state.ollama_base)
                st.session_state["ollama_models"] = models
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
        if "ollama_models" in st.session_state and st.session_state.ollama_models:
            st.selectbox("설치된 모델 (참고)", options=st.session_state.ollama_models, key="_model_pick")

        st.divider()
        st.caption("탭 아이콘 출처")
        st.markdown(
            f'<p style="font-size:0.8rem;margin:0;">{FLATICON_WHALE_ATTR_HTML}</p>',
            unsafe_allow_html=True,
        )

    tab_chat, tab_files, tab_merge = st.tabs(["대화", "파일", "엑셀 통합"])

    with tab_chat:
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        prompt = st.chat_input("메시지를 입력하세요…")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                try:
                    reply = chat(
                        st.session_state.ollama_base,
                        model,
                        st.session_state.messages,
                        temperature=temperature,
                    )
                except Exception as e:  # noqa: BLE001
                    reply = f"**오류**\n\n{e}"
                st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

        st.divider()
        md = _messages_to_markdown(st.session_state.messages)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "대화 내용 .md 다운로드",
                data=md.encode("utf-8"),
                file_name="chat.md",
                mime="text/markdown",
                disabled=not st.session_state.messages,
            )
        with c2:
            if st.button("outputs에 대화 저장", disabled=not st.session_state.messages):
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                p = out / f"chat_{ts}.md"
                p.write_text(md, encoding="utf-8")
                st.success(f"저장됨: {p}")
        with c3:
            if st.button("대화 초기화"):
                st.session_state.messages = []
                st.rerun()

    with tab_files:
        st.subheader("업로드")
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
                st.success(f"저장: {dest.name}")

        st.subheader("업로드된 파일")
        paths = sorted(up.iterdir(), key=lambda p: p.name.lower())
        if not paths:
            st.info("uploads 폴더가 비어 있습니다.")
        for p in paths:
            cols = st.columns([4, 1, 1])
            cols[0].write(p.name)
            if cols[1].button("삭제", key=f"del_{p.name}"):
                p.unlink(missing_ok=True)
                st.rerun()
            if p.suffix.lower() in {".xlsx", ".xlsm", ".xls", ".csv"} and cols[2].button("미리보기", key=f"pv_{p.name}"):
                try:
                    head = read_table(p).head(10)
                    st.dataframe(head, use_container_width=True)
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))

    with tab_merge:
        st.markdown(
            "여러 파일을 합친 뒤, **키 열**이 같은 행끼리 묶어 숫자 열은 **평균**, 그 외는 **첫 값**으로 합니다."
        )
        all_files = sorted([p for p in up.iterdir() if p.is_file()], key=lambda p: p.name.lower())
        if len(all_files) < 2:
            st.warning("통합하려면 uploads에 파일을 2개 이상 올리세요.")
        else:
            chosen = st.multiselect("통합할 파일", options=[p.name for p in all_files], default=[p.name for p in all_files[:5]])
            sheet = st.text_input("시트 이름 또는 인덱스 (0=첫 시트)", value="0")
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
                st.error(f"열 목록을 읽지 못했습니다: {e}")

            keys = st.multiselect("키 열", options=cols_preview, default=cols_preview[:1] if cols_preview else [])
            out_name = st.text_input("결과 파일 이름", value="merged.xlsx")

            if st.button("통합 실행"):
                if len(chosen) < 2:
                    st.error("파일을 2개 이상 선택하세요.")
                elif not keys:
                    st.error("키 열을 하나 이상 선택하세요.")
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
                        st.success(f"저장: {dest}")
                        st.dataframe(merged.head(50), use_container_width=True)
                        st.download_button(
                            "결과 다운로드",
                            data=dest.read_bytes(),
                            file_name=dest.name,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{dest.name}",
                        )
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))

        st.divider()
        st.subheader("outputs 정리")
        outs = sorted(out.iterdir(), key=lambda p: p.name.lower())
        if st.button("outputs 폴더 비우기"):
            for p in outs:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            st.success("outputs 비움")
            st.rerun()
        for p in outs:
            st.write(p.name)

    _fill_welcome_heading_slot(welcome_slot)


if __name__ == "__main__":
    main()
