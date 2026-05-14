"""Read / merge Excel-like files with pandas."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def read_table(path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    if suffix == ".xls":
        return pd.read_excel(path, sheet_name=sheet_name)
    raise ValueError(f"Unsupported extension: {suffix}")


def merge_mean_by_keys(paths: Iterable[Path], key_cols: list[str], sheet_name: str | int = 0) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in paths:
        df = read_table(p, sheet_name=sheet_name)
        missing = [c for c in key_cols if c not in df.columns]
        if missing:
            raise ValueError(f"{p.name}: missing key columns {missing}")
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    g = all_df.groupby(key_cols, dropna=False)
    agg: dict[str, str] = {}
    for col in all_df.columns:
        if col in key_cols:
            continue
        s = all_df[col]
        if pd.api.types.is_numeric_dtype(s):
            agg[col] = "mean"
        else:
            agg[col] = "first"
    if not agg:
        return g.size().reset_index(name="count")
    return g.agg(agg).reset_index()
