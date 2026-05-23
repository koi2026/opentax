# RAW agent — 양도소득세 AI

양도소득세 관련 세금 판단을 **소득세법·조세특례제한법 조문에 근거**해 수행하는 RAG 기반 AI 에이전트입니다.
공식 법령 데이터(law.go.kr)를 벡터 DB에 인덱싱하고, 사용자 질문에 대해 근거 조문을 검색·제시·판단합니다.

> KAIST SW교육센터 4주 해커톤 트랙C 출품작

---

## 아키텍처

```
사용자 입력 (양도 정보)
    │
    ▼
┌─────────────────┐
│  Streamlit UI   │  ← 디버그 UI: top-5 조문, 유사도 점수, 에이전트 추론 과정
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│   MCP Server    │  ← FastAPI 기반 Model Context Protocol
│   (FastAPI)     │    tools: search_tax_law, retrieve_article,
└────────┬────────┘           analyze_exemption, verify_citations
         │
    ▼
┌─────────────────────────────────────────┐
│           CrewAI Orchestration          │
│                                         │
│  Tax Researcher ──► Tax Advisor         │
│  (사실관계 정리 +   (조문 적용 →        │
│   RAG 검색)         비과세 판단)        │
└────────┬────────────────────────────────┘
         │
    ▼
┌─────────────────┐     ┌──────────────────┐
│  LlamaIndex RAG │────►│ Pinecone 벡터 DB │
│  + BGE Reranker │     │ (2,238 법령 청크) │
└─────────────────┘     └──────────────────┘
         │
    ▼
┌─────────────────┐
│  Claude Opus    │  ← 최종 판단 및 한국어 응답 생성
│  4.7 (Anthropic)│
└─────────────────┘
         │
    ▼
법령 데이터 원천: law.go.kr DRF API
(소득세법, 시행령, 시행규칙 + 조세특례제한법, 시행령, 시행규칙)
```

---

## 빠른 시작

### 사전 요건

- Docker Desktop 또는 Docker Engine + Docker Compose
- Python 3.12+ (Docker를 쓰지 않는 경우)
- Pinecone 계정 (Serverless 인덱스)
- Anthropic API 키
- OpenAI 또는 Upstage API 키 (임베딩용)

### 설치 및 환경변수

```bash
git clone https://github.com/Raw-Agent/korean-tax-rag.git
cd korean-tax-rag
cp .env.example .env
```

`.env` 파일을 열어 아래 키를 입력합니다:

| 변수명 | 설명 |
|--------|------|
| `ANTHROPIC_API_KEY` | Anthropic Claude API 키 |
| `PINECONE_API_KEY` | Pinecone 벡터 DB 키 |
| `PINECONE_INDEX_NAME` | Pinecone 인덱스 이름 (예: `tax-rag`) |
| `OPENAI_API_KEY` | OpenAI 임베딩 키 (text-embedding-3-large) |
| `UPSTAGE_API_KEY` | Upstage Solar 임베딩 키 (선택, 우선 적용) |
| `LAW_API_OC` | law.go.kr DRF OC 파라미터 (`jctax`) |

### Docker 개발 환경 실행

```bash
# UI + FastAPI chat API + MCP SSE 서버 실행
docker compose up --build
```

접속 URL:

- Streamlit UI: `http://localhost:8501`
- FastAPI docs: `http://localhost:8000/docs`
- MCP SSE: `http://localhost:8001`

개발 명령은 `api` 서비스를 일회성 컨테이너로 사용합니다:

```bash
# 테스트
docker compose run --rm api python -m pytest -q

# 법령 데이터 수집
docker compose run --rm api python -m src.ingestion.collect

# 법령 임베딩 생성 및 Pinecone 업로드
docker compose run --rm api python -m src.ingestion.embed

# 유권해석/PDF 등 추가 수집 예시
docker compose run --rm api python -m src.ingestion.collect_rulings_pdf
docker compose run --rm api python -m src.ingestion.embed_rulings nts
```

### 로컬 Python 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 법령 데이터 수집 (최초 1회, 이후 캐시 사용)
python -m src.ingestion.collect

# 3. 임베딩 생성 및 Pinecone 업로드
python -m src.ingestion.embed

# 4. FastAPI chat API 실행
uvicorn src.api.chat_api:app --host 0.0.0.0 --port 8000 --reload

# 5. MCP SSE 서버 실행 (별도 터미널)
python -m src.api.mcp_server --sse

# 6. Streamlit UI 실행
streamlit run src/ui.py --server.port 8501
```

브라우저에서 `http://localhost:8501` 접속

---

## 프로젝트 구조

```
tax-rag/
├── src/
│   ├── api/
│   │   ├── chat_api.py   # FastAPI chat API + chat_turn()
│   │   └── mcp_server.py # FastMCP 도구 서버
│   ├── domain/           # L2~L5 도메인 로직, 타입, 검증
│   ├── ingestion/        # law.go.kr/유권해석 수집 + Pinecone 업로드
│   ├── retrieval/        # Pinecone 검색 + LLM 호출
│   ├── rag.py            # 레거시 자연어 RAG shim
│   ├── ui.py             # Streamlit UI
│   └── agents/
│       ├── crew.py       # CrewAI Crew 정의
│       ├── tools.py      # RAG/MCP 도구 래퍼
│       ├── roles.py      # Agent 역할 정의
│       └── prompts.py    # 프롬프트 버전 관리
├── data/
│   ├── raw/              # XML 원본 (.gitignore)
│   └── processed/        # JSON 청크 (.gitignore)
├── tests/                # 단위 테스트
├── .env.example          # 환경변수 템플릿
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── CLAUDE.md             # AI 코딩 어시스턴트 가이드
└── README.md
```

---

## 수집 법령 목록

| 법령명 | MST | 분류 |
|--------|-----|------|
| 소득세법 | 285523 | 법률 |
| 소득세법 시행령 | 285631 | 대통령령 |
| 소득세법 시행규칙 | 284987 | 부령 |
| 조세특례제한법 | 285525 | 법률 |
| 조세특례제한법 시행령 | 283625 | 대통령령 |
| 조세특례제한법 시행규칙 | 284611 | 부령 |

총 **2,238개 청크** (조문단위 기준, 조/항/호/목 구조 보존)

---

## 개발 로드맵 (4주 해커톤)

| 주차 | 목표 | 완료 기준 |
|------|------|----------|
| **Week 1** | 데이터 파이프라인 | `collect.py` + `embed.py` 완성, Pinecone 인덱스 구축 |
| **Week 2** | RAG + 에이전트 | `rag.py` BGE reranker 적용, CrewAI 2-agent 워크플로우 |
| **Week 3** | MCP 서버 + UI | FastAPI MCP 도구, Streamlit 디버그 UI (top-5 조문 표시) |
| **Week 4** | 통합 + 데모 | End-to-end 테스트, 해커톤 발표 시나리오 준비 |

---

## 팀원 기여 가이드

### 브랜치 전략

```bash
main          # 발표용 안정 버전
dev           # 통합 개발 브랜치
feature/*     # 기능 개발 (예: feature/rag-reranker)
fix/*         # 버그 수정
```

### 새 법령 추가 방법

[src/collect.py](src/collect.py)의 `TARGET_LAWS` 리스트에 항목 추가:

```python
{"name": "법령명", "mst": "MST번호", "category": "법률|대통령령|부령"}
```

MST 번호는 [law.go.kr](https://www.law.go.kr) 에서 해당 법령 검색 후 URL에서 확인.

### 에이전트 확장 방법

1. `src/agents/roles.py`에 새 역할 정의
2. `src/agents/tools.py`에 필요한 도구 추가
3. `src/agents/prompts.py`에 프롬프트 버전 관리
4. `src/agents/crew.py`에 Crew에 에이전트/태스크 등록

### 커밋 전 체크리스트

- [ ] `.env`가 커밋에 포함되지 않았는지 확인
- [ ] `data/raw/`, `data/processed/` 제외 확인
- [ ] 새 API 키가 코드에 하드코딩되지 않았는지 확인
- [ ] 관련 테스트 추가 또는 업데이트

---

## 법률 고지

본 시스템은 **정보 제공** 목적으로 개발되었으며, 법률 자문이 아닙니다.
양도소득세 신고·납부에 관한 최종 판단은 반드시 공인 세무사와 상담하시기 바랍니다.

---

## 기술 스택

![Python](https://img.shields.io/badge/Python-3.12-blue)
![CrewAI](https://img.shields.io/badge/CrewAI-0.95+-green)
![LlamaIndex](https://img.shields.io/badge/LlamaIndex-0.12+-orange)
![Pinecone](https://img.shields.io/badge/Pinecone-Serverless-purple)
![Claude](https://img.shields.io/badge/Claude-Opus%204.7-red)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal)
![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-pink)
