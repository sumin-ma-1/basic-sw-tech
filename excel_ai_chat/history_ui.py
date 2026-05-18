"""Sidebar chat-history row component (compact ghost buttons + ⋯ menu)."""

from __future__ import annotations

import html
from collections.abc import Callable

import streamlit as st
import streamlit.components.v1 as components


def history_widget_key(chat_id: str) -> str:
    return chat_id.replace("-", "_")


def _hist_row_container(key: str):
    try:
        return st.container(key=key)
    except TypeError:
        return st.container()


def _history_menu_container(label: str, *, key: str):
    popover = getattr(st, "popover", None)
    if popover is not None:
        return popover(label, key=key)
    try:
        return st.expander(label, expanded=False, key=key)
    except TypeError:
        return st.expander(label, expanded=False)


def sidebar_history_row_bind() -> None:
    """Row hover + active sync (Streamlit DOM breaks pure CSS sibling :hover)."""
    components.html(
        """
<script>
(function () {
  const doc = window.parent.document;
  const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
  if (!sidebar) return;

  function rowFor(anchor) {
    return (
      anchor.closest('[class*="st-key-bst_hist_row_"]')
      || anchor.closest('[data-testid="stVerticalBlockBorderWrapper"]')
    );
  }

  function syncActive(row, anchor) {
    row.classList.toggle('bst-hist-row-active', anchor.classList.contains('is-active'));
  }

  function bindRows() {
    sidebar.querySelectorAll('.bst-hist-item-anchor').forEach((anchor) => {
      const row = rowFor(anchor);
      if (!row || row.dataset.bstHistBound === '1') return;
      row.dataset.bstHistBound = '1';
      syncActive(row, anchor);

      row.addEventListener('mouseenter', () => row.classList.add('bst-hist-row-hover'));
      row.addEventListener('mouseleave', () => row.classList.remove('bst-hist-row-hover'));
    });
  }

  bindRows();
  if (sidebar.dataset.bstHistObserved === '1') return;
  sidebar.dataset.bstHistObserved = '1';
  new MutationObserver(bindRows).observe(sidebar, { childList: true, subtree: true });
})();
</script>
        """,
        height=0,
    )


def render_history_row(
    *,
    mode: str,
    chat_id: str,
    title: str,
    is_active: bool,
    on_open: Callable[[str, str], None],
    on_share: Callable[[str, str], None],
    on_rename: Callable[[str, str], None],
    on_delete: Callable[[str, str], None],
) -> None:
    """One history row: title button + ⋯ menu (⋯ on hover only)."""
    wkey = history_widget_key(chat_id)
    label = (title or "New chat").strip()
    active_cls = " is-active" if is_active else ""
    active_attr = ' data-active="true"' if is_active else ""
    row_key = f"bst_hist_row_{mode}_{wkey}"

    with _hist_row_container(row_key):
        st.markdown(
            f'<span class="bst-hist-item-anchor{active_cls}" '
            f'data-mode="{html.escape(mode)}" data-wkey="{html.escape(wkey)}"{active_attr} '
            'aria-hidden="true"></span>',
            unsafe_allow_html=True,
        )

        title_col, menu_col = st.columns([1, 0.001], gap="small")
        with title_col:
            st.button(
                label,
                key=f"bst_hist_item_{mode}_{wkey}",
                use_container_width=True,
                type="secondary",
                on_click=on_open,
                args=(mode, chat_id),
            )
        with menu_col:
            with _history_menu_container("⋯", key=f"bst_hist_menu_{mode}_{wkey}"):
                st.button(
                    "Share",
                    key=f"bst_hist_share_{mode}_{wkey}",
                    use_container_width=True,
                    type="secondary",
                    on_click=on_share,
                    args=(mode, chat_id),
                )
                st.button(
                    "Rename",
                    key=f"bst_hist_rename_{mode}_{wkey}",
                    use_container_width=True,
                    type="secondary",
                    on_click=on_rename,
                    args=(mode, chat_id),
                )
                st.button(
                    "Delete",
                    key=f"bst_hist_delete_{mode}_{wkey}",
                    use_container_width=True,
                    type="secondary",
                    on_click=on_delete,
                    args=(mode, chat_id),
                )
