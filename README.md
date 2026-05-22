# basic-sw-tech

Welcome to my basic software technology!

excel-ai-chat은 Ollama와 대화하며 CSV·Excel 등을 분석, 수정, 생성, 저장 등을 할 수 있는 Streamlit 웹 UI입니다. 대화는 Markdown으로 보내거나 `outputs/` 아래에 저장합니다.

## 사용 화면 캡쳐

### 메인 허브

우측 상단의 사용자 프로필은 전역 사용자 정보로 관리되며, 페르소나 설정과 독립적으로 모든 모델 요청에 포함됩니다.
전역 사용자 정보는 `호칭`, `사용 언어`, `시간대 / 지역`, `간단한 자기소개`로 구성되며, 모든 항목은 선택 입력입니다.

<img width="800" alt="메인 허브 화면" src="https://github.com/user-attachments/assets/2a80c598-40e3-4a81-8d1a-eb194ca2f9bf" />

### 엑셀 에이전트 모드

엑셀 전문가 페르소나를 기본 적용하고, 사용자 선호 옵션이 있는 경우 함께 반영합니다.

<img width="800" alt="엑셀 에이전트 모드 화면" src="https://github.com/user-attachments/assets/620a4bee-3871-4512-974c-ae38d99a98df" />

### 사용자 전용 페르소나 생성

`balanced`, `professional`, `friendly` 프리셋 외에도 사용자 취향에 맞는 커스텀 페르소나를 생성, 수정 및 삭제 등 관리 할 수 있습니다.

<img width="800" alt="사용자 전용 페르소나 생성 화면" src="https://github.com/user-attachments/assets/938cd542-b78a-40f8-b1c3-baf35c5fcce5" />

### 작업 파일 다운로드

사용자가 요청한 작업을 처리하기 위해 코드 실행이 필요한 경우, 실행 전에 사용자에게 진행 여부를 확인합니다.

<img width="800" alt="작업 파일 다운로드 화면" src="https://github.com/user-attachments/assets/b77dc5f2-e014-46aa-8123-8eeb28c24984" />

### 다운로드 완료 화면

<img width="800" alt="다운로드 완료 화면" src="https://github.com/user-attachments/assets/e53f5f7f-ce3d-4382-ad81-f2a3dc2159b2" />

### 챗 히스토리 관리 및 저장

메인 허브, 엑셀 에이전트 등 모드별로 챗 히스토리를 분리합니다. 사용자는 저장된 히스토리를 다운로드, 이름 수정, 개별 삭제할 수 있으며, 필요에 따라 전체 히스토리도 삭제할 수 있습니다.

<img width="800" alt="챗 히스토리 관리 및 저장" src="https://github.com/user-attachments/assets/6e7ab1de-72ab-49d9-a8ba-01545c27b796" />

## 아키텍처 개요

단일 Streamlit 앱(`excel_ai_chat/app.py`)이 UI·상태·라우팅을 담당하고, 도메인 로직은 패키지 모듈로 분리합니다. 외부 의존은 **Ollama HTTP API**와 **로컬 디스크**(`uploads/`, `outputs/`)입니다.

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

## 시스템 프롬프트

시스템 지시문은 `excel_ai_chat/prompts.py`(`PROMPT_VERSION`)에 정의되며, 각 채팅 요청 시 Ollama `role: system`으로 전달됩니다(저장된 대화 JSON에는 포함하지 않음).

| 모드 | 기본 동작 |
|------|-----------|
| **허브 채팅** | 일반 어시스턴트, 간결한 Markdown, 사용자와 같은 언어, 사실 날조 금지 |
| **Excel** | 스프레드시트 분석가, `<spreadsheet_data>` 샘플 참고, 전체 데이터 연산은 샌드박스 ` ```python ` (`dfs`, `pd`, `np`) |

선택적 오버라이드: 실행 전 `OLLAMA_SYSTEM_CHAT` 또는 `OLLAMA_SYSTEM_EXCEL` 환경 변수.

Excel 코드 루프: `EXCEL_CODE_MAX_ROUNDS`(기본 3), `EXCEL_CODE_TIMEOUT` 초(기본 15).

Python 실행 전 **코드 미리보기**, 요약, **Run analysis** / **Cancel** 버튼을 표시하여 선택 가능합니다.

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
