"""Load packaged CSS and inject once per session (keeps app.py lean)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_CSS_DIR = Path(__file__).resolve().parent / "static" / "css"


def _read_css(filename: str) -> str:
    path = _CSS_DIR / filename
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def inject_hub_theme(session_key: str = "_bst_hub_theme_css") -> None:
    """Inject hub layout + waiting animation styles (single <style> block)."""
    # IMPORTANT:
    # Streamlit reruns the script on every interaction, but it doesn't keep
    # previously-rendered <style> tags unless we render them on the current run.
    # That can cause "first load" vs "refresh" visual mismatches.
    # So we always render the <style> tag, but give it a stable id to avoid
    # accumulating multiple tags in the DOM.
    combined = "\n".join(
        filter(
            None,
            [
                _read_css("hub_theme.css"),
                _read_css("hub_animations.css"),
                _read_css("waiting.css"),
            ],
        )
    )
    if combined.strip():
        st.markdown(
            f"<style id='{session_key}'>\n{combined}\n</style>",
            unsafe_allow_html=True,
        )
    st.session_state[session_key] = True
