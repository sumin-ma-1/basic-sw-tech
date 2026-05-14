# basic-sw-tech
Welcome to our basic software technology!

Streamlit 기반 웹 UI로, **Ollama**와 대화하고 **CSV/Excel** 파일을 업로드·목록·삭제한 뒤, 여러 표를 **키 기준으로 통합(숫자 열 평균)**할 수 있습니다. 대화 내용은 Markdown으로 내려받거나 `outputs/`에 저장할 수 있습니다.

## 요구 사항

- Python **3.10 이상**
- (대화 탭 사용 시) [Ollama](https://ollama.com)가 실행 중이고, 사용할 모델이 `ollama pull` 등으로 받아져 있을 것

## 설치

저장소 루트에서 가상환경을 쓰는 것을 권장합니다.

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

### 콘솔 스크립트 (권장)

현재 `excel-ai-chat`은 **8502** 포트로 Streamlit을 띄웁니다.

```powershell
excel-ai-chat
```

포트는 환경 변수로 바꿀 수 있습니다.

```powershell
$env:STREAMLIT_SERVER_PORT = 8600
excel-ai-chat
```

### `streamlit run`으로 직접 실행

프로젝트 루트에서 실행하면 `.streamlit/config.toml`의 `[server] port`(기본 8502)가 적용됩니다.

```powershell
python -m streamlit run excel_ai_chat/app.py
```

브라우저에서 `http://localhost:8502` (또는 위에서 지정한 포트)로 접속합니다.

## Ollama 연결

- 기본 API 주소: `http://127.0.0.1:11434`
- 앱 **사이드바**의 Base URL에서 변경하거나, 실행 전에 환경 변수 `OLLAMA_BASE_URL`을 설정합니다. (예시는 [.env.example](.env.example) 참고)
- 연결이 안 될 때는 사이드바의 **연결 테스트**로 `/api/tags` 응답을 확인하세요.

## 주요 기능

| 영역 | 설명 |
|------|------|
| **대화** | Ollama `api/chat`으로 멀티턴 대화, temperature 조절, 대화 `.md` 다운로드 / `outputs/` 저장 |
| **파일** | `uploads/`에 CSV·Excel 저장, 목록·삭제, 미리보기 |
| **엑셀 통합** | 여러 파일 선택 후 키 열 기준 groupby, 숫자 열은 **평균**, 그 외는 **첫 값**, 결과는 `outputs/` 및 다운로드 |

## 디렉터리

| 경로 | 설명 |
|------|------|
| `excel_ai_chat/` | 패키지 소스 (`app.py`, Ollama 클라이언트, 엑셀 유틸) |
| `uploads/` | 업로드된 파일 (Git 무시) |
| `outputs/` | 통합 결과·저장한 대화 등 (Git 무시) |
| `.streamlit/config.toml` | Streamlit 서버 포트 등 |
| `.venv/` | 가상환경 (Git 무시) |

## 개발

```powershell
pip install -e ".[dev]"
```

## 라이선스

MIT (`pyproject.toml` 기준)
