"""Console entry: `python -m excel_ai_chat` or `excel-ai-chat` after install."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_DEFAULT_PORT = "8502"


def main() -> None:
    app = Path(__file__).resolve().parent / "app.py"
    port = os.environ.get("STREAMLIT_SERVER_PORT", _DEFAULT_PORT).strip() or _DEFAULT_PORT
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.port",
        port,
    ]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
