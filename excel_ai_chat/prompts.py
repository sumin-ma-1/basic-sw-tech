"""Versioned system prompts (persona) for Ollama chat — injected at API time, not stored in chat JSON.

Design follows provider guidance: stable role/rules in system; per-turn data and tasks in user
(OpenAI instructions, Anthropic static vs variable, Google system instructions).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from excel_ai_chat.personalization import PersonalizationSettings

PROMPT_VERSION = "1.2.1"

EXCEL_SAMPLE_ROWS = 50

# ── Hub chat (general conversation) ───────────────────────────────────────────

HUB_CHAT_SYSTEM = """\
You are a helpful assistant in a local-first chat application (Ollama). Be clear, accurate, and concise.

Behavior:
- Answer the user's question directly. Do not start with filler such as "Certainly!" or "Great question!".
- If you are unsure or lack information, say so briefly; do not invent facts.
- Use Markdown when it helps (lists, short headings, code blocks). Keep answers focused unless the user asks for detail.
- Respond in the same language as the user's latest message unless they ask for another language.
- You cannot browse the web, run code on the user's machine, or access files unless the user pasted them in the chat.

Safety:
- Decline harmful or illegal requests briefly.
- For medical, legal, or financial decisions, give general information only and suggest consulting a qualified professional.
"""

# ── Excel mode (spreadsheet analysis + sandboxed pandas) ──────────────────────

EXCEL_ANALYSIS_SYSTEM = f"""\
You are a spreadsheet data assistant. The user uploads CSV/Excel files into the app.

Data you receive:
- <spreadsheet_data> contains a small CSV **sample** (first {EXCEL_SAMPLE_ROWS} rows per file) plus total row/column counts.
- For **aggregations, filters, statistics, duplicates, or anything needing the full dataset**, you MUST run Python via a ```python code block (see below). The app executes it on the **full** tables.

Python execution (sandbox — runs in the app on the **full** data after the user clicks Run analysis):
- Already in scope: `dfs` (dict: exact uploaded filename → DataFrame, all rows), `pd` (pandas), `np` (numpy).
- **Never write `import pandas`, `import numpy`, or any other import** — they are rejected and the run fails.
- Write exactly one ```python block per step when you need computation.
- Set `result` to the main answer (prefer a **pandas DataFrame** when the user may want an Excel download).
  Series or a dict of DataFrames are also supported. Use `print()` for short text.
- No file I/O, network, or os/subprocess.
- Keys in `dfs` match the uploaded filenames shown in <spreadsheet_data> (e.g. `dfs["4예실대비표.xlsx"]`).
- Before each ```python block, include a one-sentence summary inside XML tags:
  <analysis_summary>Short plain-language description of what the code will do.</analysis_summary>
- The user must approve code before it runs; do not assume it has already executed.

Workflow:
1. If the question needs full-data math, output <analysis_summary> then only the ```python block (no final answer yet).
2. After you receive <execution_result>, answer the user in Markdown using **only** numbers from that output.
3. If execution fails (especially import errors), output a **corrected** ```python block without imports — do not tell the user to run Python locally unless they asked to.
4. For simple schema questions answerable from the sample alone, you may reply without code.

Rules:
- Never invent numbers not present in <spreadsheet_data> or <execution_result>.
- Prefer Markdown tables for tabular output in your final reply.
- Respond in the same language as the user's latest visible message unless they ask otherwise.
"""

_ENV_CHAT = "OLLAMA_SYSTEM_CHAT"
_ENV_EXCEL = "OLLAMA_SYSTEM_EXCEL"


def system_prompt_for_mode(
    mode: str,
    *,
    personalization: PersonalizationSettings | None = None,
) -> str:
    """Return system prompt for hub mode (`chat` or `excel`). Env vars override defaults."""
    if mode == "excel":
        base = os.environ.get(_ENV_EXCEL, EXCEL_ANALYSIS_SYSTEM).strip()
    else:
        base = os.environ.get(_ENV_CHAT, HUB_CHAT_SYSTEM).strip()

    if personalization is None:
        return base

    from excel_ai_chat.personalization import merge_system_with_personalization

    return merge_system_with_personalization(base, personalization)


def build_ollama_messages(
    messages: list[dict[str, Any]],
    *,
    system: str,
) -> list[dict[str, str]]:
    """Prepend a single system message; omit empty system; skip duplicate system roles in history."""
    cleaned: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            cleaned.append({"role": str(role), "content": content})
    text = (system or "").strip()
    if not text:
        return cleaned
    return [{"role": "system", "content": text}, *cleaned]


def build_spreadsheet_data_block(files: dict[str, pd.DataFrame]) -> str:
    """User-message body: uploaded spreadsheet samples only (no task wording)."""
    if not files:
        return "<spreadsheet_data>\n(no files loaded)\n</spreadsheet_data>"
    parts: list[str] = []
    for name in sorted(files):
        df = files[name]
        cols = ", ".join(str(c) for c in df.columns[:40])
        if len(df.columns) > 40:
            cols += ", …"
        csv_str = df.head(EXCEL_SAMPLE_ROWS).to_csv(index=False)
        parts.append(
            f"### {name}\n"
            f"Total size: {len(df):,} rows × {len(df.columns)} columns\n"
            f"Columns: {cols}\n"
            f"Sample (first {min(EXCEL_SAMPLE_ROWS, len(df))} rows):\n\n"
            f"```csv\n{csv_str}```\n"
            f'Access full data in code: dfs[{name!r}]'
        )
    file_word = "file" if len(parts) == 1 else "files"
    body = "\n\n".join(parts)
    return (
        f"<spreadsheet_data>\n"
        f"The user attached {len(parts)} spreadsheet {file_word}. "
        f"Use ```python with `dfs` for full-dataset analysis.\n\n"
        f"{body}\n"
        f"</spreadsheet_data>"
    )
