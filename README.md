# basic-sw-tech

Welcome to our basic software technology!

Streamlit web UI to chat with **Ollama**, **upload/list/delete** CSV and Excel files, and **merge** multiple tables by key columns (**numeric columns averaged**, others use **first** value). Export conversations as Markdown or save them under `outputs/`.

## Demo

Usage screen recording (GIF).

<img width="1392" height="1080" alt="Usage demo — hub chat, Analyze Excel, and file merge" src="https://github.com/user-attachments/assets/3488e184-d82c-4c9e-867e-41f2905ff95f" />

## Requirements

- Python **3.10+**
- For the Chat tab: [Ollama](https://ollama.com) running and the model you use pulled (e.g. `ollama pull …`)

## Install

Use a virtual environment at the repository root (recommended).

**Windows (PowerShell)**

```powershell
cd path\to\basic-sw-tech
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## Run

### Console entry point (recommended)

`excel-ai-chat` starts Streamlit on port **8502** by default.

```powershell
excel-ai-chat
```

Override the port with an environment variable:

```powershell
$env:STREAMLIT_SERVER_PORT = 8600
excel-ai-chat
```

### `streamlit run` directly

From the project root, `.streamlit/config.toml` applies `[server] port` (default **8502**).

```powershell
python -m streamlit run excel_ai_chat/app.py
```

Open `http://localhost:8502` (or the port you set) in your browser.

## Ollama

- Default API base: `http://127.0.0.1:11434`
- Change **Base URL** in the app sidebar, or set `OLLAMA_BASE_URL` before launch (see [.env.example](.env.example)).
- Use sidebar **Test connection** to verify `/api/tags` when something fails.

## Features

The app opens on a **hub**: choose **Excel World** for chat, file uploads, and merge. Use **Home** to return; new capabilities can add more tiles on the hub.

| Area | Description |
|------|-------------|
| **Chat** | Multi-turn chat via Ollama `api/chat`, temperature, download chat as `.md` or save under `outputs/` |
| **Files** | Save CSV/Excel to `uploads/`, list, delete, preview |
| **Merge** | Pick files, group by key columns, **mean** for numeric columns and **first** for others; save to `outputs/` and download |

## Directories

| Path | Description |
|------|-------------|
| `excel_ai_chat/` | Package source (`app.py`, Ollama client, Excel helpers, `theme.py`) |
| `excel_ai_chat/static/css/` | Hub UI styles (`hub_theme.css`, `waiting.css`), loaded by `theme.py` |
| `uploads/` | Uploaded files (gitignored) |
| `outputs/` | Merged files and saved chats (gitignored) |
| `.streamlit/config.toml` | Streamlit server port, etc. |
| `.venv/` | Virtual environment (gitignored) |

## Development

```powershell
pip install -e ".[dev]"
```

## License

MIT (see `pyproject.toml`).
