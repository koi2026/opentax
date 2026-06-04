<p align="center">
  <img src=".github/images/logo.svg" width="400" alt="OpenTax Logo">
</p>

<div align="center">
  <h3>한국 양도소득세 비과세·감면·중과 판단을 위한 법령 RAG 기반 멀티 에이전트 AI.</h3>
</div>

<div align="center">
  <a href="https://github.com/Raw-Agent/opentax/actions/workflows/ci.yml" target="_blank"><img src="https://github.com/Raw-Agent/opentax/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Raw-Agent/opentax/releases/latest" target="_blank"><img src="https://img.shields.io/github/v/release/Raw-Agent/opentax?label=Release" alt="Release"></a>
  <a href="https://polyformproject.org/licenses/noncommercial/1.0.0" target="_blank"><img src="https://img.shields.io/badge/License-PolyForm%20Noncommercial-red" alt="PyPI - License"></a>
</div>

## 빠른 시작

Docker Compose가 권장 실행 방식입니다.

```bash
git clone https://github.com/Raw-Agent/opentax.git
cd opentax
cp .env.example .env

# .env에 API 키와 Pinecone 설정을 입력합니다.
# BGE reranker 파인튜닝 모델은 Git에 포함되지 않습니다.
# 별도 저장소에서 받아 data/models/bge-reranker-tax-rag/에 배치하세요.

docker compose up --build
```

서비스는 기본적으로 아래 포트에서 실행됩니다.

| 서비스 | 주소 |
|------|------|
| FastAPI | `http://localhost:8000` |
| MCP 검색 서버 | `http://localhost:8001` |
| Streamlit UI | `http://localhost:8501` |

상태 확인과 테스트도 Docker 기준으로 실행합니다.

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose exec api pytest
```

로컬 Python 환경에서 직접 실행하려면 별도 터미널에서 각 서비스를 띄웁니다.

```bash
pip install -r requirements.txt
python -m src.mcp.server --sse
uvicorn src.api.main:app
streamlit run src/ui/app.py
```

필수 환경 변수 예시는 아래와 같습니다.

```env
ANTHROPIC_API_KEY=
UPSTAGE_API_KEY=
OPENAI_API_KEY=
PINECONE_API_KEY=
PINECONE_INDEX_NAME=tax-rag
PINECONE_NAMESPACE=tax-law
BGE_RERANKER_MODEL=data/models/bge-reranker-tax-rag
```

## 어떻게 동작하는가?

OpenTax는 사용자가 입력한 사실관계를 바로 LLM에 넘기지 않습니다. 먼저 확인서와 팩트체크를 통과한 뒤, 검색된 법령 조문과 유권해석 chunk만 근거로 판단합니다.

```text
JSON fact_json 또는 자연어 질문
    ↓
L1.5 확인서 Gate
    - 세대 전체 주택 수
    - 잔금일/등기접수일 중 빠른 날
    - 특수관계인 거래 여부
    - 실제 거주 기간
    - 취득서류 보유 여부
    ↓
L2 팩트체크
    - 필수 사실관계 누락 시 LLM 호출 차단
    ↓
L3 쿼리 보강
    - 세법 위험 플래그와 조문 키워드 주입
    ↓
L4 검색 + 추론
    - Pinecone 날짜 필터
    - 법령/유권해석 멀티소스 검색
    - BGE reranker 재정렬
    - Claude 기반 조문 근거 추론
    ↓
L5 출력 검증
    - phantom citation 차단
    - confidence 상한 조정
    ↓
TaxAnswer
    - verdict
    - citations
    - chunk_ids
    - missing_facts
    - warnings
    - expert_review_signals
```

판단 유형은 `비과세`, `감면`, `중과`, `일반과세`, `단기세율`, `고가주택`, `사실관계부족` 중 하나입니다.

핵심 원칙은 세 가지입니다.

| 원칙 | 의미 |
|------|------|
| RAG 우회 금지 | 검색된 조문 없이 LLM 기억으로 답하지 않습니다. |
| Phantom citation 금지 | 실제 검색 결과에 있는 `chunk_id`만 인용합니다. |
| 결론 유보 우선 | 불확실한 사실관계가 있으면 `missing_facts`로 재요청합니다. |

## 시스템 아키텍처

```text
+--------------------+
| Streamlit UI       |
| fact/question input|
+---------+----------+
          |
          v
+--------------------+       +--------------------+
| FastAPI Chat API   | ----> | MCP Search Server  |
| request/streaming  |       | retrieve context   |
+---------+----------+       +---------+----------+
          |                            |
          v                            v
+--------------------+       +--------------------+
| Domain Pipeline    | <---- | Retrieval Layer    |
| L1.5 ~ L5          |       | Pinecone + BGE     |
+---------+----------+       +--------------------+
          |
          v
+--------------------+       +--------------------+
| Claude Reasoning   | ----> | TaxAnswer          |
| cited chunks only  |       | verdict/citations  |
+--------------------+       +--------------------+
```

## 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python |
| API | FastAPI, Uvicorn |
| UI | Streamlit |
| MCP | FastMCP |
| LLM | Claude Sonnet 4.6, Claude Opus 4.7 |
| 임베딩 | Upstage Solar `solar-embedding-1-large-passage`, OpenAI fallback |
| 벡터 DB | Pinecone Serverless |
| Reranker | BGE CrossEncoder, 세법 도메인 파인튜닝 모델 |
| 수집 | law.go.kr DRF API, taxlaw.nts.go.kr, PDF parser |
| 평가 | pytest, Red-Blue debate, golden set |

---

## 디렉터리 구조

```text
src/
├── api/                    # FastAPI app, chat routes, request/response schema
├── application/            # API service orchestration and serializers
├── domain/                 # L1.5~L5 pipeline, dataclasses, tax rules
├── retrieval/              # Pinecone retriever, MCP retriever, LLM call wrapper
├── infra/                  # Embedding, Pinecone client, reranker adapter
├── ingestion/              # 법령·유권해석·PDF 수집과 임베딩
├── calculator/             # 결정론 세액 계산
├── mcp/                    # FastMCP search tools
├── eval/                   # Debate, golden set, retrieval evaluation
├── services/               # 상담 라우팅 등 서비스 계층
├── agents/                 # Prompt registry
└── ui/                     # Streamlit UI and admin pages

data/
├── golden/                 # 평가용 QA/golden cases
├── rulings/                # 수집된 유권해석 원천 데이터
├── area_designations/      # 규제지역 수동 기준표와 소스 상태
├── tax_tables/             # 세율표·공제표 등 결정론 기준표
└── models/                 # BGE 모델 배치 경로, Git 제외

scripts/
├── eval/                   # Baseline eval and golden refresh
├── ingestion/              # 수집/임베딩 운영 스크립트
├── ops/                    # 법령 변경 감지와 registry 자동화
└── training/               # Reranker pair 추출과 파인튜닝

tests/                      # Unit and regression tests
```

## 개발 기여

기여 방법, 개발 환경, 테스트, PR 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고해 주세요.

도메인 계약과 AI-assisted PR 규칙은 [AGENTS.md](AGENTS.md), [DEVELOPERS.md](DEVELOPERS.md), [CLAUDE.md](CLAUDE.md)에 함께 정리되어 있습니다.

## 라이센스

이 프로젝트는 [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)에 따라 배포됩니다.

상업적 사용, 서비스 제공, 재판매, SaaS 제공 등은 별도 허가 없이 허용되지 않습니다.

## 법률 고지

OpenTax는 정보 제공과 연구·개발 목적으로 제공되는 소프트웨어입니다. 본 시스템의 출력은 법률 자문, 세무 대리, 세무 신고 검토 의견이 아닙니다.

양도소득세 신고·납부, 불복, 세무조사 대응, 과세관청 제출 자료 작성에 관한 최종 판단은 반드시 공인 세무사, 변호사 또는 관계 기관과 상담해 확인해야 합니다. OpenTax의 개발자와 기여자는 본 시스템의 사용 결과로 발생하는 세액 차이, 가산세, 신고 오류, 행정상 불이익에 대해 책임을 지지 않습니다.
