"""Per-chat Excel attachments and export files on disk."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from excel_ai_chat.export_utils import build_download_items, dataframe_to_xlsx_bytes, safe_export_filename
from excel_ai_chat.paths import chats_dir

_ATTACHMENTS = "attachments"
_EXPORTS = "exports"
_MANIFEST = "exports_manifest.json"


def chat_workspace(chat_id: str) -> Path:
    root = chats_dir() / chat_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def attachments_dir(chat_id: str) -> Path:
    p = chat_workspace(chat_id) / _ATTACHMENTS
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir(chat_id: str) -> Path:
    p = chat_workspace(chat_id) / _EXPORTS
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_table_path(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(path, engine="openpyxl")
    return pd.read_excel(path)


def _write_table_path(path: Path, df: pd.DataFrame) -> None:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df.to_csv(path, index=False)
    else:
        path = path.with_suffix(".xlsx")
        df.to_excel(path, index=False, engine="openpyxl")


def save_attachments(chat_id: str, files: dict[str, pd.DataFrame]) -> None:
    """Persist all attachments for a chat (replaces attachment folder contents)."""
    folder = attachments_dir(chat_id)
    if folder.is_dir():
        for old in folder.iterdir():
            if old.is_file():
                old.unlink()
    for name, df in files.items():
        safe = Path(name).name
        if not safe or safe.startswith("."):
            continue
        _write_table_path(folder / safe, df)


def load_attachments(chat_id: str) -> dict[str, pd.DataFrame]:
    folder = attachments_dir(chat_id)
    if not folder.is_dir():
        return {}
    out: dict[str, pd.DataFrame] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".csv", ".xlsx", ".xlsm", ".xls"}:
            continue
        try:
            out[path.name] = _read_table_path(path)
        except Exception:  # noqa: BLE001
            continue
    return out


def attachment_signature(chat_id: str) -> tuple[tuple[str, int], ...]:
    """Stable signature from on-disk attachments (size + name)."""
    files = load_attachments(chat_id)
    rows: list[tuple[str, int]] = []
    folder = attachments_dir(chat_id)
    for name in sorted(files):
        path = folder / name
        if path.is_file():
            rows.append((name, path.stat().st_size))
    return tuple(rows)


def append_exports(
    chat_id: str,
    exports: list[tuple[str, pd.DataFrame]],
) -> list[dict[str, Any]]:
    """Write new export spreadsheets; return download items for the whole chat export set."""
    if not exports:
        return list_export_download_items(chat_id)

    folder = exports_dir(chat_id)
    manifest_path = folder / _MANIFEST
    manifest: list[dict[str, str]] = []
    if manifest_path.is_file():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                manifest = [e for e in raw if isinstance(e, dict)]
        except (OSError, json.JSONDecodeError):
            manifest = []

    existing_names = {str(e.get("file_name", "")) for e in manifest}
    counter = len(manifest)

    for label, df in exports:
        fname = safe_export_filename(label, counter)
        while fname in existing_names:
            counter += 1
            fname = safe_export_filename(f"{label}_{counter}", counter)
        path = folder / fname
        path.write_bytes(dataframe_to_xlsx_bytes(df))
        manifest.append({"file_name": fname, "label": f"Download {fname}"})
        existing_names.add(fname)
        counter += 1

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return list_export_download_items(chat_id)


def list_export_download_items(chat_id: str) -> list[dict[str, Any]]:
    folder = exports_dir(chat_id)
    manifest_path = folder / _MANIFEST
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(manifest, list):
        return []

    from excel_ai_chat.export_utils import _XLSX_MIME

    items: list[dict[str, Any]] = []
    for entry in manifest:
        if not isinstance(entry, dict):
            continue
        fname = str(entry.get("file_name") or "")
        path = folder / fname
        if not fname or not path.is_file():
            continue
        items.append(
            {
                "label": str(entry.get("label") or f"Download {fname}"),
                "file_name": fname,
                "data": path.read_bytes(),
                "mime": _XLSX_MIME,
            }
        )
    return items


def delete_chat_workspace(chat_id: str) -> None:
    root = chats_dir() / chat_id
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)
