# basic-sw-tech

Welcome to my basic software technology!

excel-ai-chat은 Ollama와 대화하며 CSV·Excel 등을 분석, 수정, 생성, 저장 등을 할 수 있는 Streamlit 웹 UI입니다. 대화는 Markdown으로 보내거나 `outputs/` 아래에 저장합니다.

## 사용 화면 캡쳐lit 웹 UI입니다. 대화는 Markdown으로 보내거나 `outputs/` 아래에 저장합니다.

## 사용 화면 캡쳐


### 작업 파일 다운로드

<img width="800" alt="다운로드 완료 화면" src="https://github.com/user-attachments/assets/05b78140-ca95-4885-88f7-5cae53e95cdb" />

### 다운로드 완료 화면

<img width="800" alt="작업 파일 다운로드 화면" src="https://github.com/user-attachments/assets/e53f5f7f-ce3d-4382-ad81-f2a3dc2159b2" />

---

## 아키텍처 개요

단일 Streamlit 앱(`excel_ai_chat/app.py`)이 UI·상태·라우팅을 담당하고, 도메인 로직은 패키지 모듈로 분리합니다. 외부 의존은 **Ollama HTTP API**와 **로컬 디스크**(`uploads/`, `outputs/`)입니다.

### 화면·모드 라우팅

| `session_state` | 값 | 화면 |
|-----------------|-----|------|
| `nav_page` | `hub` | 메인 허브(채팅 / Excel 분석) |
| `nav_page` | `file_manager` | 파일 업로드·미리보기·병합 |
| `hub_mode` | `chat` | 일반 Ollama 채팅 |
| `hub_mode` | `excel` | 스프레드시트 첨부·분석·코드 실행 루프 |

`main()`은 사이드바(Ollama·모델·채팅 기록)를 그린 뒤 `nav_page`에 따라 `_render_hub()` 또는 `_render_file_manager()`를 호출합니다.

### Excel 모드 데이터 흐름

1. **첨부**: 클립 → 숨김 `file_uploader` → `_EXCEL_PENDING_FILES` → 전송 시 `outputs/chats/<chat_id>/attachments/`에 병합 저장.
2. **컨텍스트**: `prompts.build_spreadsheet_data_block()`으로 샘플이 담긴 숨김 user 메시지(`_hidden`)를 스레드에 삽입.
3. **응답**: `excel_agent`가 Ollama 호출 → 응답의 ` ```python ` 블록 추출 → 사용자 **실행 확인** 후 `code_runner` 샌드박스 실행.
4. **결과**: `result`가 DataFrame이면 `exports/`에 xlsx 저장·다운로드 버튼 표시.

일반 채팅 모드는 `messages` + `chat_store`만 사용하며, Excel 첨부·코드 실행 경로는 타지 않습니다.

---

## 디렉터리 구조

```
basic-sw-tech/
├── excel_ai_chat/              # 애플리케이션 패키지
│   ├── app.py                  # Streamlit 진입·UI·세션·라우팅 (단일 화면 오케스트레이션)
│   ├── __main__.py             # `excel-ai-chat` → streamlit run app.py
│   ├── theme.py                # CSS 번들을 <head>에 주입 (components.html)
│   ├── paths.py                # repo_root, uploads_dir, outputs_dir, chats_dir
│   ├── ollama_client.py        # Ollama /api/tags, /api/chat
│   ├── prompts.py              # 시스템 프롬프트·스프레드시트 블록 (PROMPT_VERSION)
│   ├── chat_store.py           # 대화 JSON CRUD (outputs/chats/*.json)
│   ├── excel_chat_files.py     # 대화별 attachments/ · exports/
│   ├── excel_agent.py          # Excel 채팅 + 코드 제안·실행 루프
│   ├── code_runner.py          # pandas 샌드박스 실행·블록 파싱
│   ├── excel_tools.py          # read_table, merge_mean_by_keys (파일 관리자 병합)
│   ├── history_ui.py           # 사이드바 기록 행·메뉴·호버 JS
│   ├── export_utils.py         # xlsx 바이트·다운로드 항목
│   └── static/
│       ├── favicon.png
│       └── css/
│           ├── variables.css   # 디자인 토큰 (:root)
│           ├── global.css      # 공통 버튼·입력 등
│           ├── sidebar.css     # 사이드바·채팅 기록·New chat/Clear all
│           ├── hub.css         # 허브·Excel 컴포저·제안 pills·메시지
│           ├── file_manager.css
│           ├── hub_animations.css
│           ├── waiting.css     # 응답 대기 애니메이션
│           └── hub_theme.css   # (레거시) 단일 파일 시절 잔존 — theme.py는 미사용
├── tests/                      # pytest (chat_store, code_runner, prompts, export)
├── uploads/                    # 파일 관리자 업로드 (gitignore)
├── outputs/                    # 병합 결과·저장 대화 (gitignore)
│   └── chats/
│       ├── <uuid>.json         # 대화 메타·메시지
│       └── <uuid>/
│           ├── attachments/    # Excel 모드 첨부 시트
│           └── exports/        # 분석 결과 xlsx
├── .streamlit/config.toml      # 기본 포트 8502 등
├── .env.example
├── pyproject.toml
└── requirements.txt
```

---

## 모듈 역할

| 모듈 | 책임 |
|------|------|
| **app.py** | 페이지 설정, `session_state` 초기화, 사이드바, 허브/파일관리자 렌더, 채팅 전송·rerun, Excel 컴포저(클립·pending·`st.chat_input`), 환영/제안 칩 |
| **theme.py** | `variables` → `global` → `sidebar` → `hub` → `file_manager` → `hub_animations` → `waiting` 순으로 CSS를 parent `document.head`에 주입 |
| **chat_store.py** | `chat` / `excel` 모드별 대화 목록·저장·삭제·마지막 활성 ID |
| **excel_chat_files.py** | 대화 워크스페이스, 첨부 로드/저장, export manifest |
| **history_ui.py** | `render_history_row()`, 행 호버·활성 상태용 `components.html` JS |
| **excel_agent.py** | Ollama 멀티턴 + 코드 블록 승인 대기(`ExcelCodeProposal`) + 재시도 라운드 |
| **code_runner.py** | `execute_pandas_code`, 마크업/블록 추출 |
| **excel_tools.py** | 파일 I/O·키 기준 병합 (파일 관리자 탭) |
| **prompts.py** | `HUB_CHAT_SYSTEM`, `EXCEL_SYSTEM`, env 오버라이드 (`OLLAMA_SYSTEM_*`) |
| **ollama_client.py** | httpx 기반 API 클라이언트 |
| **export_utils.py** | DataFrame → xlsx, 안전한 파일명 |
| **paths.py** | 저장 경로 단일 정의 |

---

## 요구 사항

- Python **3.10+**
- 채팅 탭: [Ollama](https://ollama.com) 실행 및 사용 모델 pull (예: `ollama pull …`)

## 설치

저장소 루트에서 가상 환경 사용을 권장합니다.

**Windows (PowerShell)**

```powershell
cd path\to\basic-sw-tech
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## 실행

### 콘솔 진입점 (권장)

`excel-ai-chat`는 기본 포트 **8502**에서 Streamlit을 띄웁니다.

```powershell
excel-ai-chat
```

포트 변경:

```powershell
$env:STREAMLIT_SERVER_PORT = 8600
excel-ai-chat
```

### `streamlit run` 직접 실행

프로젝트 루트에서 `.streamlit/config.toml`의 `[server] port`(기본 **8502**)가 적용됩니다.

```powershell
python -m streamlit run excel_ai_chat/app.py
```

브라우저에서 `http://localhost:8502`(또는 설정한 포트)를 엽니다.

---

## 시스템 프롬프트

시스템 지시문은 `excel_ai_chat/prompts.py`(`PROMPT_VERSION`)에 정의되며, 각 채팅 요청 시 Ollama `role: system`으로 전달됩니다(저장된 대화 JSON에는 포함하지 않음).

| 모드 | 기본 동작 |
|------|-----------|
| **허브 채팅** | 일반 어시스턴트, 간결한 Markdown, 사용자와 같은 언어, 사실 날조 금지 |
| **Excel** | 스프레드시트 분석가, `<spreadsheet_data>` 샘플 참고, 전체 데이터 연산은 샌드박스 ` ```python ` (`dfs`, `pd`, `np`) |

선택적 오버라이드: 실행 전 `OLLAMA_SYSTEM_CHAT` 또는 `OLLAMA_SYSTEM_EXCEL` 환경 변수.

Excel 코드 루프: `EXCEL_CODE_MAX_ROUNDS`(기본 3), `EXCEL_CODE_TIMEOUT` 초(기본 15).

Python 실행 전 **코드 미리보기**, 요약, **Run analysis** / **Cancel** 버튼을 표시합니다.

실행 결과 `result`가 DataFrame(또는 Series / 프레임 dict)이면 스레드 아래 **Download results (Excel)** 버튼이 나타나며, `outputs/chats/<chat_id>/exports/`에 저장됩니다.

**대화별 스프레드시트**: Excel 모드 대화마다 첨부가 분리됩니다(`outputs/chats/<chat_id>/attachments/`). 추가 업로드는 현재 대화에 병합되며, 동일 파일명은 해당 시트를 교체합니다. 사이드바에서 다른 대화를 열면 그 대화의 파일·다운로드만 복원됩니다.

## Ollama

- 기본 API: `http://127.0.0.1:11434`
- 앱 사이드바 **Base URL** 또는 실행 전 `OLLAMA_BASE_URL`([.env.example](.env.example) 참고)
- 실패 시 사이드바 **Test connection**으로 `/api/tags` 확인

## 기능 요약

앱은 **허브**에서 시작합니다. **Excel World**로 스프레드시트 채팅·업로드·병합, **Home**으로 복귀합니다.

| 영역 | 설명 |
|------|------|
| **채팅** | Ollama `api/chat`, 모드별 시스템 프롬프트, temperature, `.md` 다운로드 또는 `outputs/` 저장 |
| **파일** | CSV/Excel을 `uploads/`에 저장, 목록·삭제·미리보기 |
| **병합** | 파일 선택, 키 컬럼 그룹, 숫자 열 **평균**·그 외 **첫 값**; `outputs/` 저장 및 다운로드 |

## 개발

```powershell
pip install -e ".[dev]"
pytest tests/ -q
```

## 라이선스

MIT (`pyproject.toml` 참고).
