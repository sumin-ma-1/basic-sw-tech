"""Excel chat agent: Ollama + pandas code execution (with user confirmation before run)."""

from __future__ import annotations

import os
from typing import TypedDict

import pandas as pd

from excel_ai_chat.code_runner import (
    execute_pandas_code,
    extract_analysis_summary,
    extract_python_blocks,
    strip_analysis_markup,
    summarize_code_heuristic,
)
from excel_ai_chat.ollama_client import chat

DEFAULT_MAX_ROUNDS = 3


class ExcelCodeProposal(TypedDict):
    """Waiting for user to approve running generated code."""

    ollama_base: str
    model: str
    temperature: float
    api_messages: list[dict[str, str]]
    blocks: list[str]
    summary: str
    assistant_preamble: str


def _max_rounds() -> int:
    try:
        return max(1, min(5, int(os.environ.get("EXCEL_CODE_MAX_ROUNDS", DEFAULT_MAX_ROUNDS))))
    except ValueError:
        return DEFAULT_MAX_ROUNDS


def _timeout_s() -> float:
    try:
        return max(3.0, min(60.0, float(os.environ.get("EXCEL_CODE_TIMEOUT", "15"))))
    except ValueError:
        return 15.0


def _strip_fenced_code(text: str) -> str:
    """Remove ```python``` blocks and analysis_summary tag for preamble display."""
    return strip_analysis_markup(text)


def _summarize_blocks(blocks: list[str], assistant_text: str) -> str:
    tagged = extract_analysis_summary(assistant_text)
    if tagged:
        return tagged
    if len(blocks) == 1:
        return summarize_code_heuristic(blocks[0])
    parts = [summarize_code_heuristic(b) for b in blocks]
    return " ".join(f"({i + 1}) {s}" for i, s in enumerate(parts))


def _execution_feedback(
    blocks: list[str],
    files: dict[str, pd.DataFrame],
) -> tuple[str, list[tuple[str, pd.DataFrame]]]:
    sections: list[str] = []
    exports: list[tuple[str, pd.DataFrame]] = []
    for i, code in enumerate(blocks, start=1):
        sections.append(f"### Code block {i}\n```python\n{code}\n```")
        outcome = execute_pandas_code(files, code, timeout_s=_timeout_s())
        sections.append(outcome.feedback)
        for label, df in outcome.exports:
            exports.append((f"step{i}_{label}", df))
    body = "\n\n".join(sections)
    feedback = (
        "<execution_result>\n"
        "The following Python was run against the full uploaded DataFrames in `dfs` "
        "(not just the CSV sample).\n\n"
        f"{body}\n"
        "</execution_result>\n\n"
        "Explain the findings to the user in Markdown. Use only numbers from the "
        "execution output above. If execution failed, emit a corrected ```python block "
        "(no imports; use preloaded `pd`, `np`, `dfs`) or explain the error briefly — "
        "do not ask the user to install pandas or run code on their own machine."
    )
    return feedback, exports


def excel_first_model_response(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
) -> str:
    """Single Ollama call (before any code execution)."""
    return chat(base_url, model, messages, temperature=temperature)


def excel_proposal_from_response(
    response: str,
    api_messages: list[dict[str, str]],
    *,
    ollama_base: str,
    model: str,
    temperature: float,
) -> ExcelCodeProposal | None:
    """If *response* contains Python blocks, build a confirmation payload."""
    blocks = extract_python_blocks(response)
    if not blocks:
        return None
    full_thread = [*api_messages, {"role": "assistant", "content": response}]
    return ExcelCodeProposal(
        ollama_base=ollama_base,
        model=model,
        temperature=temperature,
        api_messages=full_thread,
        blocks=blocks,
        summary=_summarize_blocks(blocks, response),
        assistant_preamble=_strip_fenced_code(response),
    )


def excel_continue_after_execution(
    base_url: str,
    model: str,
    api_messages: list[dict[str, str]],
    files: dict[str, pd.DataFrame],
    *,
    temperature: float = 0.7,
) -> str | ExcelCodeProposal:
    """
    Continue after user approved code run (*api_messages* already includes execution_result).
  May return another ExcelCodeProposal if the model emits new code.
    """
    thread = list(api_messages)
    last_response = ""

    for _ in range(_max_rounds()):
        last_response = chat(base_url, model, thread, temperature=temperature)
        blocks = extract_python_blocks(last_response)
        if not blocks:
            return last_response

        return ExcelCodeProposal(
            ollama_base=base_url,
            model=model,
            temperature=temperature,
            api_messages=[*thread, {"role": "assistant", "content": last_response}],
            blocks=blocks,
            summary=_summarize_blocks(blocks, last_response),
            assistant_preamble=_strip_fenced_code(last_response),
        )

    return (
        f"{last_response}\n\n"
        "*(Reached the maximum number of analysis steps. "
        "Refine your question or try again.)*"
    )


def excel_run_approved_blocks(
    proposal: ExcelCodeProposal,
    files: dict[str, pd.DataFrame],
) -> tuple[str | ExcelCodeProposal, list[tuple[str, pd.DataFrame]]]:
    """Execute approved code and continue the agent loop."""
    thread = list(proposal["api_messages"])
    feedback, exports = _execution_feedback(proposal["blocks"], files)
    thread.append({"role": "user", "content": feedback})
    outcome = excel_continue_after_execution(
        proposal["ollama_base"],
        proposal["model"],
        thread,
        files,
        temperature=proposal["temperature"],
    )
    return outcome, exports
