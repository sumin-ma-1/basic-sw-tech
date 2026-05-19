"""Restricted pandas execution for Excel mode (LLM-generated code, app-side sandbox)."""

from __future__ import annotations

import io
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from excel_ai_chat.export_utils import collect_tabular_exports

MAX_CODE_CHARS = 12_000
DEFAULT_TIMEOUT_S = 15.0

_FORBIDDEN_SNIPPETS = (
    "import ",
    "__",
    "open(",
    "exec(",
    "eval(",
    "compile(",
    "breakpoint(",
    "os.",
    "sys.",
    "subprocess",
    "shutil",
    "pathlib",
    "socket",
    "requests",
    "httpx",
    "pickle",
    "builtins",
    "globals(",
    "locals(",
    "getattr(",
    "setattr(",
    "delattr(",
)

_SAFE_BUILTINS: dict[str, Any] = {
    "len": len,
    "range": range,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "round": round,
    "abs": abs,
    "print": print,
    "isinstance": isinstance,
    "any": any,
    "all": all,
    "True": True,
    "False": False,
    "None": None,
}

_PYTHON_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_ANALYSIS_SUMMARY_RE = re.compile(
    r"<analysis_summary>\s*(.*?)\s*</analysis_summary>",
    re.IGNORECASE | re.DOTALL,
)
# Models often emit these even though pd/np/dfs are preloaded — strip before validation.
_REDUNDANT_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:"
    r"import\s+(?:pandas(?:\s+as\s+pd)?|numpy(?:\s+as\s+np)?|pd|np)\s*"
    r"|from\s+(?:pandas|numpy)\s+import\s+.+"
    r")\s*(?:#.*)?$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_python_blocks(text: str) -> list[str]:
    """Return fenced ```python``` (or ```) code blocks in order."""
    return [m.strip() for m in _PYTHON_BLOCK_RE.findall(text) if m.strip()]


def strip_analysis_markup(text: str) -> str:
    """Remove <analysis_summary> and fenced code blocks for UI preamble text."""
    text = _ANALYSIS_SUMMARY_RE.sub("", text)
    return re.sub(r"```(?:python)?\s*\n.*?```", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def extract_analysis_summary(text: str) -> str | None:
    """Optional one-line summary from the model (see EXCEL_ANALYSIS_SYSTEM)."""
    m = _ANALYSIS_SUMMARY_RE.search(text)
    if not m:
        return None
    line = m.group(1).strip()
    return line if line else None


def summarize_code_heuristic(code: str) -> str:
    """Short fallback summary when the model omits <analysis_summary>."""
    lowered = code.lower()
    hints: list[str] = []
    if "groupby" in lowered:
        hints.append("groups rows and aggregates")
    if ".mean(" in lowered:
        hints.append("computes means")
    if ".sum(" in lowered:
        hints.append("computes sums")
    if ".count(" in lowered:
        hints.append("counts values")
    if "duplicated" in lowered or "duplicate" in lowered:
        hints.append("finds duplicate rows")
    if ".sort_values" in lowered or "sort(" in lowered:
        hints.append("sorts data")
    if "filter" in lowered or "[" in code and "]" in code:
        hints.append("filters rows")
    if "merge(" in lowered or "join" in lowered:
        hints.append("combines tables")
    if "dfs[" in lowered:
        hints.append("uses your uploaded file(s) in dfs")
    if not hints:
        return "Runs a pandas calculation on the full uploaded spreadsheet data."
    return "This code " + ", ".join(hints) + "."


def sanitize_code_for_sandbox(code: str) -> str:
    """Remove redundant pandas/numpy import lines (pd, np, dfs are already in scope)."""
    cleaned = _REDUNDANT_IMPORT_LINE_RE.sub("", code)
    return "\n".join(line for line in cleaned.splitlines() if line.strip() or not cleaned).strip()


def validate_code(code: str) -> str | None:
    """Return an error message if code is not allowed, else None."""
    if not code.strip():
        return "Code block is empty."
    if len(code) > MAX_CODE_CHARS:
        return f"Code exceeds {MAX_CODE_CHARS} characters."
    lowered = code.lower()
    for snippet in _FORBIDDEN_SNIPPETS:
        if snippet in lowered:
            if snippet == "import ":
                return (
                    "Import statements are not allowed. `pd`, `np`, and `dfs` are already "
                    "loaded on the full uploaded tables. Rewrite the code with no import lines."
                )
            return f"Disallowed construct: `{snippet.strip()}`"
    return None


@dataclass
class CodeExecutionOutcome:
    """Sandbox run result for the model and optional spreadsheet downloads."""

    feedback: str
    exports: list[tuple[str, pd.DataFrame]] = field(default_factory=list)


def _execute_in_thread(
    code: str,
    globals_dict: dict[str, Any],
) -> tuple[str, str | None, list[tuple[str, pd.DataFrame]]]:
    """Run code; return (stdout_capture, result_repr or None, tabular exports)."""
    locals_dict: dict[str, Any] = {}
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(code, globals_dict, locals_dict)  # noqa: S102 — sandboxed globals
    stdout = buffer.getvalue().strip()
    result_obj = locals_dict.get("result")
    if result_obj is None:
        result_obj = globals_dict.get("result")
    exports = collect_tabular_exports(result_obj)
    result_text: str | None = None
    if result_obj is not None:
        if isinstance(result_obj, pd.DataFrame):
            if len(result_obj) > 30:
                preview = result_obj.head(30)
                result_text = (
                    f"{preview.to_string()}\n\n"
                    f"(… {len(result_obj) - 30} more rows; total {len(result_obj)} rows)"
                )
            else:
                result_text = result_obj.to_string()
        elif isinstance(result_obj, pd.Series):
            result_text = result_obj.to_string()
        else:
            result_text = str(result_obj)
    return stdout, result_text, exports


def execute_pandas_code(
    files: dict[str, pd.DataFrame],
    code: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> CodeExecutionOutcome:
    """
    Execute *code* with `dfs` (filename → DataFrame, full data) and `pd` / `np`.
    Returns feedback text for the model and any tabular `result` for download.
    """
    code = sanitize_code_for_sandbox(code)
    err = validate_code(code)
    if err:
        return CodeExecutionOutcome(feedback=f"Execution failed (validation): {err}")

    dfs: dict[str, pd.DataFrame] = {name: df.copy() for name, df in files.items()}
    globals_dict: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "pd": pd,
        "np": np,
        "dfs": dfs,
    }

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_execute_in_thread, code, globals_dict)
            stdout, result_text, exports = future.result(timeout=timeout_s)
    except FuturesTimeoutError:
        return CodeExecutionOutcome(
            feedback=f"Execution failed: timed out after {timeout_s:.0f}s.",
        )
    except Exception as e:  # noqa: BLE001
        return CodeExecutionOutcome(
            feedback=f"Execution failed: {type(e).__name__}: {e}",
        )

    parts: list[str] = ["Execution succeeded."]
    if stdout:
        parts.append("stdout:\n" + stdout)
    if result_text:
        parts.append("result:\n" + result_text)
    if not stdout and not result_text:
        parts.append("(No stdout or `result` variable — assign to `result` or use print().)")
    if exports:
        parts.append(
            f"(Tabular result available for download: {len(exports)} spreadsheet export(s).)"
        )
    return CodeExecutionOutcome(feedback="\n\n".join(parts), exports=exports)
