"""Resolved directories for uploads and generated files."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parent


def repo_root() -> Path:
    """Project root (parent of package)."""
    return _REPO_ROOT


def uploads_dir() -> Path:
    p = _REPO_ROOT / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def outputs_dir() -> Path:
    p = _REPO_ROOT / "outputs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def chats_dir() -> Path:
    """Saved hub conversations (JSON)."""
    p = outputs_dir() / "chats"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_ollama_base() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
