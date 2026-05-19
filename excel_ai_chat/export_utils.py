"""Spreadsheet export helpers for download buttons."""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def safe_export_filename(label: str, index: int) -> str:
    stem = re.sub(r"[^\w.\-]+", "_", label).strip("_") or f"result_{index + 1}"
    if stem.lower().endswith(".xlsx"):
        return stem[:120]
    return f"{stem[:110]}.xlsx"


def dataframe_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def collect_tabular_exports(result_obj: Any) -> list[tuple[str, pd.DataFrame]]:
    """Turn a code `result` value into zero or more named DataFrames for download."""
    if isinstance(result_obj, pd.DataFrame):
        return [("result", result_obj)]
    if isinstance(result_obj, pd.Series):
        name = str(result_obj.name) if result_obj.name else "value"
        return [(name, result_obj.to_frame())]
    if isinstance(result_obj, dict):
        out: list[tuple[str, pd.DataFrame]] = []
        for key, val in result_obj.items():
            label = str(key)
            if isinstance(val, pd.DataFrame):
                out.append((label, val))
            elif isinstance(val, pd.Series):
                out.append((label, val.to_frame()))
        return out
    return []


def build_download_items(exports: list[tuple[str, pd.DataFrame]]) -> list[dict[str, Any]]:
    """Streamlit download_button payloads: label, file_name, data, mime."""
    items: list[dict[str, Any]] = []
    for i, (label, df) in enumerate(exports):
        if df.empty and len(df.columns) == 0:
            continue
        fname = safe_export_filename(label, i)
        items.append(
            {
                "label": f"Download {fname}",
                "file_name": fname,
                "data": dataframe_to_xlsx_bytes(df),
                "mime": _XLSX_MIME,
            }
        )
    return items
