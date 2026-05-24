# CLAUDE.md

AI 코딩 어시스턴트(Claude Code 등)가 이 프로젝트에서 올바르게 동작하도록 안내하는 문서이다.

---

## Backlog (Claude Code 전용)

세션 시작 시 이 목록을 확인한다.
사용자가 다른 작업을 요청하시면 그것을 우선하고, 완료한 항목은 즉시 삭제한다.

> 상세 로드맵은 `AGENTS.md > 개발 로드맵` 참조. 아래는 Claude Code 실행 큐 전용.

---

### 완료된 항목 (Phase 1~6 코드 작업)

- [x] S1-1: TaxConstantsRegistry (`src/domain/tax_constants.py`)
- [x] S1-2: DateResolver + FactInput 날짜 필드 (`src/domain/date_resolver.py`, `src/api/fact_input.py`)
- [x] S1-3: AcquisitionTimeline (`src/domain/acquisition_timeline.py`)
- [x] S1-4: Confirmation Gate L1.5 (`src/domain/confirmation.py`, `src/domain/pipeline.py`)
- [x] S1-5: article_tag_map.json 외부화 (`src/infra/article_tag_map.json`)
- [x] S1-6: Multi-anchor Pinecone 필터 + Hybrid BM25 (`retriever_impl.py`, `embedder.py`)
- [x] S2-1: AreaDesignation 3종 통합 (`admin_notices.py`, `data/area_designations/manual_table.json`)
- [x] S2-2: Pinecone Hybrid Search BM25 (S1-6에 통합)
- [x] S2-3: 법령 커버리지 14개 법령 + MST 검증 + 부칙/별표 분리 (`collect.py`)
- [x] S2-4: chunk_id 포맷 마이그레이션 (`{version_mst}_{law_slug}_{article_slug}_{eff_slug}`)
- [x] S3-1: SpecialCaseFinder 15종 (`src/domain/special_case_finder.py`)
- [x] S3-2: 장기보유특별공제율 표1/표2 (`data/tax_tables/`)
- [x] S4-1: TaxCalculator (`src/calculator/tax_calculator.py`)
- [x] S4-2: query_mode report/consulting 분기 (`pipeline.py`)
- [x] S4-3: E2E 골든 케이스 30개 + test_e2e_golden.py (`tests/`)
- [x] RLVR 검색 품질 분석기 (`src/eval/retrieval_analyzer.py`)
- [x] verdict_matcher.py (`src/eval/verdict_matcher.py`)
- [x] Red-Blue 멀티라운드 강화 + 할루시네이션 방지 + expert escalation (`src/eval/debate.py`)
- [x] BGE reranker 훈련데이터 추출 (`scripts/extract_reranker_pairs.py`)
- [x] 합성 케이스 생성기 (`src/eval/case_generator.py`)
- [x] 3-티어 상담 라우터 (`src/services/tier_router.py`)
- [x] MCP 도구: calculate_tax, lookup_ruling, check_area_designation (`mcp_server.py`)
- [x] 법령 개정 자동 감지 + Pinecone 자동 reindex (`scripts/detect_law_changes.py`, `setup_scheduler.ps1`)
- [x] linked_buchik_ids 본칙↔부칙 연결 + retrieve_with_buchik 실동작
- [x] 부칙 applicability_anchor 구조화 파싱 (`_extract_buchik_anchor()`, 8개 패턴)
- [x] 주민등록 ≠ 실질 거주 특례 발굴 인터뷰 (`src/services/residence_interview.py`)
- [x] Red-Win 누적 배치 러너 (`scripts/accumulate_red_wins.py`) — 골든케이스 30개 + 합성 경계케이스로 BGE reranker 파인튜닝용 50건 수집
- [x] 세법해석정비 수집기 (`src/ingestion/collect_rulings_revision.py`) — deprecated 예규 ID 자동 관리, `data/rulings/deprecated_ids.json`
- [x] 유권해석 DB 수집기 3종:
  - `src/ingestion/collect_rulings_nts.py` — 질의회신(qt)/판단사례(pd)/세법해석례(ic)/자주찾는쟁점별사례(hotissue), POST 필터 + 쟁점 자동 순회
  - `src/ingestion/collect_rulings_decisions.py` — 판례·결정례 JSON API (`POST action.do`, `dcmClCdCtl=["001_08"]`심판청구, `icldVcbCtl=["양도"]`)
  - `src/ingestion/collect_rulings_pdf.py` — 세법집행기준 PDF 파서 (pdfplumber, `data/rulings/pdf_source/` 드롭)
- [x] Citation.source_label + SOURCE_LABELS — 법령/예규/심판청구 등 한국어 출처 라벨 전 파이프라인 관통 (`tax_answer.py`, `embed_rulings.py`, `llm_fn.py`, `embed.py`)

---

### 남은 작업 — 사용자 실행 필요

> 아래는 코드가 아닌 데이터·인프라·운영 작업이다. Claude Code가 대신할 수 없다.

- [ ] **법령 재수집** — `python -m src.ingestion.collect`
  - 새 MST 14개 법령 + chunk_id 신포맷 + applicability_anchor 포함
- [ ] **Pinecone reindex** — `python -m src.ingestion.embed`
  - linked_buchik_ids, applicability_anchor, article_type 신규 필드 반영
- [ ] **스케줄러 등록** — 관리자 PowerShell에서 `.\scripts\setup_scheduler.ps1`
  - 매일 23:00 자동 감지 + Pinecone 업로드
- [x] **유권해석 DB 수집 완료** — 3,785건 수집 + Pinecone 업로드 완료
  - `data/rulings/nts/` 342건 → `tax-ruling-nts`
  - `data/rulings/decisions/` 3,007건 → `tax-ruling-decisions` (12개 키워드 × 800건 한도)
  - `data/rulings/pdf/` 436건 → `tax-ruling-pdf` (세법집행기준-2024)
  - `data/rulings/deprecated_ids.json` 969개 deprecated 예규 ID
  - 추가 수집 필요 시: `python -m src.ingestion.collect_rulings_decisions --keyword <키워드> --resume`

---

### 장기 로드맵 (코드 작업, 우선순위 낮음)

- [x] 부칙 applicability_anchor 하드필터 — retriever_impl.py `_is_buchik_applicable()` + `retrieve_with_buchik()` 오버라이드
- [x] 유형2 시뮬레이션 엔진 — `src/services/simulation_engine.py` (양도/증여/부담부증여 비교, TaxCalculator·증여세 연동)
- [x] 행정 레이어 지도 시각화 — `src/pages/area_map.py` (pydeck 지도 + 기준일 필터 + 구역별 현황)
- [x] 유권해석 DB 2단계 파이프라인 — `src/ingestion/embed_rulings.py` (ntis/tt/court 청킹·임베딩)
- [x] 컨설팅 모드 UI — `src/ui.py` 사이드바 모드 토글, 시뮬레이션 파라미터, 시나리오 비교표 렌더링
- [ ] **BGE reranker 파인튜닝** — red_won 케이스 50건+ 축적 후 (`scripts/extract_reranker_pairs.py` 활용)
  - `python -m scripts.accumulate_red_wins --phase 1` 으로 골든케이스 replay
  - `python -m scripts.accumulate_red_wins --phase 2` 로 합성 경계케이스 추가
  - 현재 `data/red_wins/` 건수 확인 후 50건 초과 시 파인튜닝 진행

---

## 프로젝트 개요

한국 **양도소득세 비과세 / 감면 / 중과 여부 판단**을 위한 법령 RAG 엔진이다.

JSON 사실관계 입력 → L2(팩트체크) → L3(쿼리 보강) → L4(법령 검색 + LLM 추론) → L5(출력 검증) → TaxAnswer 반환.

**핵심 원칙:**
- 모든 답변은 반드시 검색된 조문에 근거해야 한다. LLM 기억에서 직접 답변하는 것은 허용하지 않는다.
- 조문 인용은 실제 검색된 chunk_id가 있는 것만 허용한다. (phantom citation 금지)
- 불확실한 사실관계가 있으면 결론을 내리지 말고 missing_facts에 명시한다.
- 모든 판단은 추적 가능(traceable)하고 감사 가능(auditable)해야 한다.

**시스템 철학:**
- **엔드투엔드 에이전트 자동화** — 법령 수집 → 임베딩 → 검색 → 판단 → 출력까지 전 과정이 에이전트 파이프라인으로 자동화된다. 인간이 개입하는 지점은 예외 처리와 최종 승인에 한정된다.
- **인간 전문가 즉시 개입 가능** — 파이프라인 전 단계의 입출력(fact_json, citations, debate_record, expert_review_signals)이 항상 노출된다. 세무사·전문가가 어느 단계에서든 판단 근거를 확인하고 개입할 수 있어야 한다.
- **전 과정 모니터링** — 추적 불가능한 블랙박스 판단을 허용하지 않는다. 모든 verdict는 검색된 chunk_id, 인용 조문, debate 기록과 함께 저장된다.

---

## 핵심 스택

| 역할 | 구성요소 |
|------|---------|
| 법령 수집 | law.go.kr DRF API (OC=jctax) |
| 버전 관리 | effective_date / expiration_date 정수(YYYYMMDD) |
| 임베딩 | Upstage Solar (solar-embedding-1-large-passage), fallback: OpenAI text-embedding-3-large |
| 벡터 DB | Pinecone Serverless (cosine, dim=4096) |
| Reranker | BAAI/bge-reranker-v2-m3 (CrossEncoder) |
| LLM | Claude Sonnet 4.6 (기본), Claude Opus 4.7 (고정밀) |
| 파이프라인 | src/domain/pipeline.py — L2~L5 오케스트레이터 |
| 채팅 API | src/api/chat_api.py — POST /api/v1/chat + chat_turn() |
| UI | Streamlit (src/ui.py) — 입력/표시/피드백 수집만 담당 |
| 평가·루프 | src/eval/debate.py → golden_injector.py → llm_fn.py (우로보로스 루프) |

---

## 아키텍처

```text
[입력 경로]
  JSON fact_json ─► src/api/fact_input.py  (FactInput → RAGQueryInput 변환)
                    src/api/chat_api.py    (chat_turn / POST /api/v1/chat)
                    src/api/sample_cases.py (35개 실무 케이스)
  자연어 question ─► src/rag.py answer_with_citations (레거시 경로)

    ▼
src/domain/pipeline.py  — L1~L5 오케스트레이터
    ├── L2: fact_checker.py       사실관계 완전성 검사, can_proceed=False → LLM 차단
    ├── L3: query_enrichment.py   danger_flags → 조문 키워드 주입
    ├── L4a: retriever_impl.py    Pinecone 날짜/entity_scope 필터 → BGE Reranker
    ├── L4b: llm_fn.py            Claude API 추론 (golden_injector few-shot 포함)
    └── L5: output_validator.py   phantom citation 검사, 신뢰도 상한 조정, expert_review_signals 생성
    ▼
TaxAnswer (verdict / confidence / citations / missing_facts / warnings / expert_review_signals)
    ▼  [confidence<0.8 또는 danger_flags>=2일 때]
src/eval/debate.py  — Red-Blue 논쟁 엔진
    ├── Red Team: 6가지 오류 유형 검증 (별도 Claude 호출)
    ├── Blue Team: missing_articles 재검색 후 반박
    └── 결과 → data/debates/ + data/red_wins/ or data/blue_wins/
         └── blue_won/no_contest → data/golden/qa_pairs.json (골든셋 누적)
              └── src/eval/golden_injector.py → 다음 L4 few-shot 주입 (우로보로스 루프)
```

---

## 파이프라인 진입점

### JSON 입력 (UI / REST API)

```python
from src.api.chat_api import chat_turn

result = await chat_turn(
    fact_json={"transfer_date": "20240601", "property_type": "아파트", ...},
    enable_debate=True,
)
# result["verdict"]  → "비과세" | "감면" | "중과" | "일반과세" | "단기세율" | "고가주택" | "사실관계부족"
# result["blocked"]  → True이면 missing_facts 채워 재요청
```

### RAGQueryInput 직접 입력 (내부 파이프라인)

```python
from src.domain.pipeline import run_rag_pipeline
from src.retrieval.retriever_impl import PineconeTaxLawRetriever
from src.retrieval.llm_fn import llm_fn

result = await run_rag_pipeline(
    query=RAGQueryInput.from_fact_ledger(fact_ledger, owner_profile, user_property),
    retriever=PineconeTaxLawRetriever(),
    llm_fn=llm_fn,
    fact_json=fact_json,    # optional — debate/few-shot 활성화용
    enable_debate=True,
)
# result.answer.verdict     → TaxVerdict 한글 값
# result.blocked_at_l2      → True이면 크리티컬 사실 누락
# result.debate_record      → 논쟁 결과 (실행된 경우)
```

---

## 도메인 계약

### TaxVerdict (7종)

```python
class TaxVerdict(str, Enum):
    EXEMPT           = "비과세"      # 소득세법 §89
    REDUCED          = "감면"        # 조특법 감면
    HEAVY_TAX        = "중과"        # 다주택자 +20%/+30%
    GENERAL          = "일반과세"    # 기본세율 6~45%
    SHORT_TERM       = "단기세율"    # 보유 1년 미만 70%, 1~2년 60%
    PARTIALLY_EXEMPT = "고가주택"    # 12억 초과분 과세
    NEEDS_VERIFICATION = "사실관계부족"
```

### TaxAnswer (출력)

```python
@dataclass
class TaxAnswer:
    answer: str               # 한국어 판단 상세
    verdict: str              # TaxVerdict 한글 값
    confidence: float         # 0.0~1.0 (L5에서 조정 가능)
    citations: List[Citation] # chunk_id 포함 — 없으면 phantom 처리
    chunk_ids: List[str]
    missing_facts: List[str]
    warnings: List[str]
    expert_review_signals: List[ExpertReviewSignal]  # 예규/판례 의존 영역 탐지 → 세무사 아이템 신호

@dataclass
class ExpertReviewSignal:
    category: str          # "예규공백" | "판례의존" | "조세불복가능" | "해석다툼"
    description: str       # 상황 설명 (상담 화면 노출)
    opportunity: str       # 세무사 활용 포인트
    related_article: str   # 관련 조문
```

### RAGQueryInput (입력)

```python
@dataclass
class RAGQueryInput:
    date_bundle: DateBundle   # transfer_date, acquisition_date
    tax_type: TaxType         # TaxType.TRANSFER
    entity_scope: EntityScope # "주택" | "분양권" | "입주권" | ...
    fact_vector: FactVector   # to_text()로 벡터 검색 텍스트 생성
    top_k: int = 10
    include_buchik: bool = True
```

`SpecialCaseFlags`에 이월과세/상생임대/일시적2주택/상속/재건축 등 14개 특례 유형이 정의되어 있다.

---

## 디렉터리 구조

```text
tax-rag/
├── src/
│   ├── domain/        # 인터페이스·타입·L2~L5 로직
│   │   ├── query_input.py       # RAGQueryInput + FactVector + SpecialCaseFlags
│   │   ├── tax_answer.py        # TaxAnswer + Citation + TaxVerdict
│   │   ├── fact_checker.py      # L2: 사실관계 완전성 검사
│   │   ├── query_enrichment.py  # L3: 조문 키워드 주입
│   │   ├── output_validator.py  # L5: phantom citation / 신뢰도 상한
│   │   ├── pipeline.py          # L1~L5 오케스트레이터 + debate 훅
│   │   ├── chunk_metadata.py    # LawChunkMetadata + ApplicabilitySpec
│   │   └── retriever.py         # TaxLawRetriever ABC
│   ├── retrieval/
│   │   ├── retriever_impl.py    # PineconeTaxLawRetriever
│   │   └── llm_fn.py            # async llm_fn → Claude API (few-shot 포함)
│   ├── infra/
│   │   ├── embedder.py          # Upstage Solar / OpenAI fallback
│   │   ├── pinecone_client.py
│   │   └── reranker.py          # BGE-Reranker-v2-m3
│   ├── ingestion/
│   │   ├── collect.py           # law.go.kr XML 수집
│   │   ├── embed.py             # 임베딩 + Pinecone 업로드
│   │   └── admin_notices.py     # 행정/금융 고시 수집 (조정대상지역 API, DSR/LTV) — API키 발급 후 구현
│   ├── api/
│   │   ├── chat_api.py          # POST /api/v1/chat + chat_turn()
│   │   ├── fact_input.py        # FactInput → RAGQueryInput 변환 팩토리
│   │   ├── sample_cases.py      # 35개 실무 케이스
│   │   ├── mcp_server.py        # FastMCP (search_tax_law 등)
│   │   └── schema.py            # Pydantic 스키마 (레거시 shim)
│   ├── eval/
│   │   ├── debate.py            # Red-Blue 논쟁 엔진
│   │   ├── golden_injector.py   # 유사 케이스 few-shot 블록 생성
│   │   ├── feedback.py          # trace 로깅
│   │   ├── eval.py              # 골든셋 배치 평가
│   │   └── retrieval_analyzer.py # RLVR 검색 품질 분석 + DANGER_KEYWORD_MAP 자동 보강
│   ├── agents/
│   │   ├── prompts.py           # RAG_SYSTEM, RED_TEAM, BLUE_DEFENSE 프롬프트
│   │   ├── crew.py / roles.py / tools.py  # CrewAI 대안 경로 (선택적)
│   ├── rag.py                   # 레거시 shim (신규 로직 추가 금지)
│   └── ui.py                    # Streamlit 채팅 UI (판단 로직 추가 금지)
├── data/
│   ├── golden/        # qa_pairs.json (debate 누적), example_cases.json
│   ├── debates/       # 개별 논쟁 기록 ({debate_id}.json)
│   ├── red_wins/      # Red 승리 케이스
│   ├── blue_wins/     # Blue 방어 성공 케이스
│   ├── rulings/       # 유권해석 DB (ntis/, tt/, court/ 하위 디렉터리)
│   ├── feedback/      # 피드백 JSONL (.gitignore)
│   ├── raw/           # law.go.kr XML (.gitignore)
│   └── processed/     # 파싱 JSON 청크 (.gitignore)
├── tests/
└── scripts/
```

---

## 환경 변수

```env
LAW_API_OC=jctax
LAW_API_BASE_URL=https://www.law.go.kr/DRF

ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-sonnet-4-6

UPSTAGE_API_KEY=
UPSTAGE_EMBEDDING_MODEL=solar-embedding-1-large-passage
OPENAI_API_KEY=          # Upstage fallback

PINECONE_API_KEY=
PINECONE_INDEX_NAME=tax-rag
PINECONE_NAMESPACE=tax-law
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1

BGE_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RETRIEVER_TOP_K=20
RETRIEVER_RERANK_TOP_N=5

MCP_PORT=8001
STREAMLIT_PORT=8501
```

---

## 개발 워크플로

```bash
pip install -r requirements.txt
cp .env.example .env

python -m src.ingestion.collect       # 법령 수집
python -m src.ingestion.embed         # Pinecone 업로드
streamlit run src/ui.py               # UI 실행
python -m src.api.mcp_server --sse    # MCP 서버 (HTTP SSE)
python -m src.eval.eval               # 골든셋 평가
pytest                                # 테스트
```

---

## 한국 법령 도메인 규칙

### 법령 계층 구조

```text
법률 / 시행령 / 시행규칙
  └── 조 → 항 → 호 → 목
부칙 (Supplementary Provisions) — 본칙과 별도 청크로 분리한다.
별표 (Attached Tables) — 장기보유특별공제율 표1/표2 등
```

### 유권해석 계층 (구속력 순서)

| 기관 | 종류 | 특징 |
|------|------|------|
| 기획재정부 | 세법해석 사전답변, 예규 | 최상위 — 국세청도 따라야 함 |
| 국세청 (ntis.go.kr) | 예규, 질의회신, 심사결정 | 실무 기준, 건수 가장 많음 |
| 조세심판원 (tt.go.kr) | 결정례 | 납세자 불복 케이스, binary 정답 |
| 대법원 | 판결 | 최종 권위, 건수 적음 |

### 핵심 판단 요소

| 필드 | 연결 조문 |
|------|---------|
| transfer_date / acquisition_date | §89, §154 보유기간 기산 |
| household_house_count | §89 1세대1주택 판단 |
| adjustment_area_at_acquisition | §154 거주요건 2년 |
| adjustment_area_at_transfer | §104 다주택 중과 |
| transfer_price | §156의2 고가주택(12억) |
| rollover_taxation | §97의2 이월과세 (오류 위험 최고) |
| sangsaeng_rental | §155의3 상생임대 |
| is_temporary_two_house | §155① 일시적2주택 |
| inheritance | §155② 상속주택 |
| reconstruction | §156의2 조합원입주권 |
| **is_related_party_transaction** | **§101 부당행위계산부인 — 특수관계자 저가양도 시 양도가액을 시가로 재계산. 비과세 판단이 완전히 바뀔 수 있어 JSON 입력에서 항상 수신 필요** |

### Pinecone 버전 관리

- 메타데이터: `effective_date`(YYYYMMDD 정수), `expiration_date`(현행=99991231)
- Stage 1 필터: `effective_date <= transfer_date AND expiration_date >= transfer_date`
- 결과가 없으면 필터 없이 재검색한다. (법령 이력 미수집 대응)

---

## L2 팩트체크 — 크리티컬 규칙

크리티컬 항목이 1개라도 누락되면 `can_proceed=False` → LLM 미호출 → 재질문을 반환한다.

| 우선순위 | 누락 필드 | 이유 |
|---------|---------|------|
| 1 | transfer_price | 고가주택(12억) 판단 불가 |
| 2 | is_gift_from_spouse_or_lineal | 이월과세 (조용히 틀릴 위험 최고) |
| 3 | death_date (상속) | §155 5년 기산 불가 |
| 4 | temp_two_house.new_acquisition_date | 종전주택 3년 기한 계산 불가 |
| 5 | management_disposal_date (입주권) | 보유기간 기산 불가 |

**비크리티컬 경고 (차단하지 않음, danger_flag + expert_review_signal 생성):**

| 필드 | 이유 |
|------|------|
| is_related_party_transaction=True | §101 부당행위계산부인 — 양도가액 시가 재계산 가능, 조세불복 아이템 |

---

## 코딩 규칙

- 모든 public 함수에 Python type hints를 작성한다.
- 도메인 모델은 `src/domain/` dataclass를 사용한다. Pydantic은 API 스키마 전용이다.
- 사용자 노출 텍스트는 한국어, 함수명·변수명·코드 주석은 영어로 작성한다.
- 모든 프롬프트는 `src/agents/prompts.py`에서 버전 관리한다. 인라인 작성은 금지이다.
- 커밋 메시지: 한국어, `타입: 요약` 형식 (feat/fix/docs/refactor/test/chore)

---

## 절대 금지 사항 (Critical DO NOTs)

- API 키, OC 코드, 인덱스명 **하드코딩 금지** — .env에서만 로드한다.
- **.env 커밋 금지**
- **RAG 우회 금지** — 법령 질문에 LLM 직접 답변은 허용되지 않는다.
- **BGE Reranker 생략 금지** — 최종 조문 선택은 반드시 reranking 이후에 진행한다.
- **청킹 전략 무단 변경 금지** — 조문 단위 기준은 법적 정확성의 핵심이다.
- **법령 계층 구조 평탄화 금지** — 조/항/호/목 메타데이터를 반드시 보존한다.
- **인용 조문 날조 금지** — 검색된 chunk_id에 있는 조문만 인용한다.
- **ui.py에 판단 로직 추가 금지** — 입력/표시/피드백 수집만 담당한다.
- **Pinecone namespace/dimension/임베딩 모델 무단 변경 금지**
- **src/rag.py에 신규 로직 추가 금지** — 레거시 shim 유지 전용이다.

---

## 테스트 우선순위

- XML 파서가 조/항/호/목 구조를 보존하는지 확인한다.
- 모든 청크에 `law_name`, `article_number`, `effective_date`, `expiration_date`가 존재해야 한다.
- Pinecone 날짜 필터가 정수(YYYYMMDD) 타입으로 동작하는지 확인한다.
- BGE Reranker가 최종 선택 전 반드시 호출되어야 한다.
- 인용 조문은 검색된 청크에만 해당해야 한다. (phantom citation 없음)
- L2 크리티컬 누락 시 LLM이 미호출되는지 확인한다.
- L5 phantom citation 검출 시 confidence가 0.3 이하인지 확인한다.
