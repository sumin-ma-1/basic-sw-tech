"""Load packaged CSS and inject once per session (keeps app.py lean)."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_CSS_DIR = Path(__file__).resolve().parent / "static" / "css"


def _read_css(filename: str) -> str:
    path = _CSS_DIR / filename
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def inject_hub_theme(session_key: str = "_bst_hub_theme_css") -> None:
    """Inject hub layout + animation styles into <head> (survives Streamlit rerenders).

    st.markdown(<style>) injects into <body> and can be lost on partial rerenders.
    components.html JS injection into window.parent.document.head is persistent.
    """
    combined = "\n".join(
        filter(
            None,
            [
                _read_css("variables.css"),
                _read_css("global.css"),
                _read_css("sidebar.css"),
                _read_css("personalization.css"),
                _read_css("hub.css"),
                _read_css("file_manager.css"),
                _read_css("hub_animations.css"),
                _read_css("waiting.css"),
            ],
        )
    )
    if not combined.strip():
        return
    # json.dumps produces a valid JS string literal (handles all special characters)
    css_json = json.dumps(combined)
    components.html(
        f"<script>(function(){{"
        f"var d=window.parent.document;"
        f"var id='{session_key}';"
        f"var el=d.getElementById(id);"
        f"if(!el){{el=d.createElement('style');el.id=id;d.head.appendChild(el);}}"
        f"el.textContent={css_json};"
        f"}})();</script>",
        height=0,
        scrolling=False,
    )
    st.session_state[session_key] = True
    _inject_profile_fab_dock()


def _inject_profile_fab_dock() -> None:
    """Re-parent profile button to document.body so position:fixed is always visible."""
    components.html(
        "<script>(function(){"
        "var doc=window.parent.document;"
        "var timer=null;"
        "function findBtnWrap(){"
        "var anchor=doc.getElementById('bst-profile-fab-anchor');"
        "if(!anchor)return null;"
        "var wrap=anchor.closest('.stElementContainer');"
        "if(!wrap)return null;"
        "var next=wrap.nextElementSibling;"
        "while(next){"
        "if(next.querySelector&&next.querySelector('[class*=\"st-key-bst_profile_open\"]'))"
        "return next;"
        "next=next.nextElementSibling;"
        "}"
        "return null;"
        "}"
        "function dock(){"
        "var btnWrap=findBtnWrap();"
        "if(!btnWrap)return;"
        "btnWrap.classList.add('bst-profile-fab-docked');"
        "if(btnWrap.parentElement!==doc.body)doc.body.appendChild(btnWrap);"
        "}"
        "function schedule(){"
        "if(timer)clearTimeout(timer);"
        "timer=setTimeout(dock,40);"
        "}"
        "schedule();"
        "if(!doc.__bstProfileFabObs){"
        "doc.__bstProfileFabObs=new MutationObserver(schedule);"
        "doc.__bstProfileFabObs.observe(doc.body,{childList:true,subtree:true});"
        "}"
        "})();</script>",
        height=0,
        scrolling=False,
    )
