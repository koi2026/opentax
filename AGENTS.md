# AGENTS.md

AI 코딩 어시스턴트(Codex, Gemini 등)가 이 프로젝트에서 올바르게 동작하도록 안내하는 문서이다.

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
    ├── [L1.5 NEW] confirmation.py    사용자 확약 4항목 Gate — No 시 완전 차단
    ├── L2: fact_checker.py           사실관계 완전성 검사, can_proceed=False → LLM 차단
    ├── L3: query_enrichment.py       danger_flags → 조문 키워드 주입
    │       + special_case_finder.py  [NEW] 특례 발굴 스캐너
    ├── L4a: retriever_impl.py        Pinecone 날짜/entity_scope 필터 → BGE Reranker
    │         (hybrid: dense+sparse)  [NEW] BM25 조문번호 exact match
    ├── L4b: llm_fn.py                Claude API 추론 (golden_injector few-shot 포함)
    ├── L5: output_validator.py       phantom citation 검사, 신뢰도 상한 조정
    └── [L6 NEW] tax_calculator.py   납부세액까지 결정론 계산 (LLM 없음)
    ▼
TaxAnswer (verdict / confidence / citations / missing_facts / warnings / expert_review_signals)
    + ApplicableSpecialCase 목록 (확정 / 가능 / 검토_필요)
    + TaxCalculation (납부세액, 가산세, 지방소득세)
    ▼  [confidence<0.8 또는 danger_flags>=2일 때]
src/eval/debate.py  — Red-Blue 논쟁 엔진 (무한루프)
    ├── Red Team: 6가지 오류 유형 검증 + 다모델 교차검색 (할루시네이션 방지)
    ├── Blue Team: missing_articles 재검색 후 반박
    ├── 루프 종료: 양팀 모두 인정 + 예규 공백 → tier_router.py로 분기
    └── 결과 → data/debates/ + data/red_wins/ or data/blue_wins/
         └── blue_won/no_contest → data/golden/qa_pairs.json (골든셋 누적)
              └── src/eval/golden_injector.py → 다음 L4 few-shot 주입 (우로보로스 루프)
    ▼  [논쟁 소진 후]
src/services/tier_router.py  — 상담 3티어 라우터 [NEW]
    ├── Bot: 자료 재요청 (필수 서식 미제출)
    ├── Quick Check: 세무사 채팅 (사실관계 불명, 5~10만원)
    └── Premium: 대면/전화 풀패키지 (예규 공백·3주택+, 30~50만원)
```

---

## 세법 개정 완전 자동화 대원칙 (Critical)

**모든 세법 개정은 시행일 기준으로 자동 감지·반영·검증되어야 한다. 수동 단계는 예외를 제외하고 허용하지 않는다.**

### 자동화 파이프라인 (목표 상태)

```text
[법령 개정 공포]
    ↓ (매일 23:00 자동)
scripts/detect_law_changes.py
    ├── 조문 변경 감지 → Pinecone 재인덱스 자동 실행           ✅ 구현됨
    ├── TaxConstantsRegistry 변경 LLM 자동 파싱 → PR 생성     🔲 목표
    ├── 영향 케이스 eval 자동 실행 → Slack/이메일 알림         🔲 목표
    └── eval 정확도 하락 시 RERANK_TOP_N 자동 조정 시도        🔲 목표
    ↓
[정확도 회복 확인]
    ├── red_wins 50건 초과 → BGE 파인튜닝 자동 트리거         🔲 목표
    └── 파인튜닝 완료 → golden_injector few-shot 자동 갱신    🔲 목표
```

### 레이어별 개정 반영 방법

| 레이어 | 구현 위치 | 반영 방식 | 자동화 여부 |
|--------|---------|----------|-----------|
| 법령 조문 | Pinecone `tax-law` | detect_law_changes.py | ✅ 자동 |
| 유권해석 DB | Pinecone `tax-ruling-*` | collect_rulings_*.py → embed_rulings.py | 🔲 스케줄링 목표 |
| 세율·기간·한도 | `TaxConstantsRegistry` | LLM 파싱 → 코드 PR | 🔲 목표 (현재: 수동 즉시) |
| 장기보유공제율 | `data/tax_tables/*.json` | JSON 교체 | 수동 |
| 골든셋·eval | `data/golden/qa_pairs.json` | eval 자동 재실행 | 🔲 목표 (현재: 반수동) |
| BGE reranker | `BAAI/bge-reranker-v2-m3` | red_wins 50건 → 재파인튜닝 | 🔲 목표 (현재: 수동) |

### 모니터링 대원칙

- **정확도 대시보드**: eval 결과를 시계열로 저장 → 개정 전후 정확도 비교 자동 표시
- **회귀 알림**: eval 정확도가 직전 대비 -3%p 이상 하락 시 즉시 알림
- **개정 영향 케이스 목록**: 변경된 법령에 연관된 케이스 자동 재평가 후 NG 목록 리포트
- **하드코딩 상수 감지**: 코드 변경 PR에서 숫자 하드코딩 자동 탐지 (CI 훅)

### 사전 학습(개정안 미리 준비)

**불가능하다.** 개정안 단계에서는 법령이 확정되지 않으므로 현행법 기준으로만 판단한다.  
개정 공포 + 시행일 기준으로 Pinecone 날짜 필터가 자동으로 새 버전을 적용한다.

---

## L1.5 확인서 — 책임소재 관리 원칙

**새로운 책임 이슈가 생기면 → `confirmation.py`의 `CONFIRMATION_ITEMS`에 추가한다. 항목 중 하나라도 미확인이면 파이프라인 완전 차단 — 답변 출력 불가.**

| key | 책임 내용 |
|-----|---------|
| `household_house_count_verified` | 세대 전체 주택 수 (분양권·입주권·오피스텔·지분·상속 포함) |
| `balance_or_registration_date_used` | 잔금 지급일 / 등기 접수일 중 빠른 날 사용 |
| `no_related_party` | 매수·매도인이 특수관계인이 아님 |
| `actual_residence_verified` | 주민등록 이전 후 실제 거주한 기간만 포함 |
| `acquisition_document_confirmed` | 취득서류 보유 확인 + 환산취득 적용 시 사후 세액변동 책임은 납세자에 있음을 인지 |

각 항목의 책임 내용·서류 요건·계산 방식은 코드(`confirmation.py`, `fact_checker.py`)에 구현돼 있다.

---

## 개발 로드맵

> CCG(Claude+Codex+Gemini) 3모델 합의 로드맵. 2026-05-21 확정.

### 설계 원칙 (3모델 합의)

1. **결정론 코드 우선** — 날짜 계산·세액 계산에 LLM 개입 금지. LLM은 법령 해석 윤활유만.
2. **수동 기준표 우선, API 검증** — 조정대상지역 등 법적 데이터는 수동 기준표가 1급. API 불안정 대비.
3. **하드코딩 상수 전면 금지** — TaxConstantsRegistry에서 날짜 기준으로 조회.
4. **확인서 양방향 연동** — 확인서 No → 파이프라인 차단, 답변 절대 출력 안 됨.
5. **특례 발굴 = 핵심 경쟁력** — SpecialCaseFinder가 세무사도 놓치는 특례를 먼저 발굴.
6. **유권해석 없음 = 수익 기회** — "논쟁의 여지 있음"을 3티어 상담 전환 트리거로 활용.

### Phase 1 — Foundation (즉시 시작)

| 태스크 | 파일 | 핵심 |
|--------|------|------|
| S1-1 TaxConstantsRegistry | `src/domain/tax_constants.py` | 모든 상수 날짜 기준 버전 dict |
| S1-2 DateResolver | `src/domain/date_resolver.py` | min(잔금일,등기일) 결정론 |
| S1-3 AcquisitionTimeline | `src/domain/acquisition_timeline.py` | 상속/증여 취득일 승계 코드 |
| S1-4 Confirmation Gate | `src/domain/confirmation.py` | 4항목 L1.5 차단 |
| S1-5 article_tag_map | `src/infra/article_tag_map.json` | 태그 외부화 |
| S1-6 Multi-anchor filter | `src/retrieval/retriever_impl.py` | 날짜 앵커 분기 |

**S1-4 확인서 5항목 (전부 차단, No 시 재요청):**
1. 세대원 전원 주택수 (오피스텔·분양권·입주권·지분·상속주택 포함)
2. 잔금지급일/등기접수일 중 빠른 날 정확히 입력 확인
3. 특수관계인 간 거래 없음 (§101 부당행위계산부인)
4. 실질 거주 요건 — 주민등록 외 거주 사실 확인
5. 취득 관련 서류 보유 확인 — 없을 경우 기준시가 환산 적용, 사후 실거래가 확인 시 세액 변동 책임 납세자 귀속 인지

### Phase 2 — Search Enhancement

| 태스크 | 파일 | 핵심 |
|--------|------|------|
| S2-1 AreaDesignation 3종 | `src/ingestion/admin_notices.py` | 조정+투기과열+토지거래허가 통합 |
| S2-2 Hybrid Search | `src/retrieval/retriever_impl.py` | Pinecone dense+sparse BM25 |
| S2-3 법령 커버리지 | `src/ingestion/collect.py` | 지방세법·국세기본법, YEARS_BACK=30 |
| S2-4 chunk_id 마이그레이션 | Pinecone reindex | 부칙 수집 완료 후 |

**S2-1 설계:** `AreaDesignationRecord(region_code, area_type, designated_at, released_at, source)` + `resolve_area_status(region, date, area_type)` 통합 함수. 수동 기준표 `data/area_designations/manual_table.json`이 1급 데이터.

### Phase 3 — Special Case Engine

| 태스크 | 파일 | 핵심 |
|--------|------|------|
| S3-1 SpecialCaseFinder | `src/domain/special_case_finder.py` | 전 조특법 특례 망라, certainty 3단계 |
| S3-2 별표 수동 등록 | `data/tax_tables/ltshd_rate_table_{1,2}.json` | 표1/표2 수동 → TaxConstantsRegistry |

**특례 발굴 UX:** 결과 말미에 "AI가 N개의 절세 기회를 발견했습니다" → 추가 자료 요청 or 세무사 연결 CTA.

### Phase 4 — Calculator & Type Routing

| 태스크 | 파일 | 핵심 |
|--------|------|------|
| S4-1 TaxCalculator | `src/calculator/tax_calculator.py` | 납부세액+가산세 결정론 |
| S4-2 query_mode | `src/domain/pipeline.py` | report|consulting 얇은 분기 |
| S4-3 E2E 테스트 러너 | `tests/` | 100케이스, golden 자동 기록 |

**calculator 원칙:** 비거주자 세율·부담부증여 포함. 법인은 법인세 대상이므로 L2에서 차단.

### Phase 5 — Ruling DB & RLVR ✅ 코드 완성

| 태스크 | 파일 | 상태 |
|--------|------|------|
| 세법해석정비 수집기 | `src/ingestion/collect_rulings_revision.py` | ✅ 완성 |
| 유권해석 수집기 (질의회신·판단사례) | `src/ingestion/collect_rulings_nts.py` | ✅ 완성 |
| 판례·결정례 JSON API 수집기 | `src/ingestion/collect_rulings_decisions.py` | ✅ 완성 |
| 세법집행기준 PDF 파서 | `src/ingestion/collect_rulings_pdf.py` | ✅ 완성 |
| embed_rulings (4개 namespace) | `src/ingestion/embed_rulings.py` | ✅ 완성 |
| verdict_matcher | `src/eval/verdict_matcher.py` | ✅ 완성 |
| Red-Blue 무한루프 | `src/eval/debate.py` | ✅ 완성 |
| Red-Win 누적 배치 러너 | `scripts/accumulate_red_wins.py` | ✅ 완성 |
| BGE 파인튜닝 | `scripts/extract_reranker_pairs.py` | ⏳ red_wins 50건 대기 중 |

**수집 실행 순서 (사용자 실행):**
```bash
# 1. 폐지 예규 목록 먼저
python -m src.ingestion.collect_rulings_revision --tax transfer

# 2. 예규·질의회신
python -m src.ingestion.collect_rulings_nts --tax 양도소득세

# 3. 심판청구 판례
python -m src.ingestion.collect_rulings_decisions --type tax_tribunal --keyword 양도

# 4. PDF (세법집행기준)
python -m src.ingestion.collect_rulings_pdf

# 5. Pinecone 업로드
python -m src.ingestion.embed_rulings nts
python -m src.ingestion.embed_rulings decisions
python -m src.ingestion.embed_rulings pdf
```

**Pinecone 네임스페이스:**
- `tax-ruling-nts` — 질의회신·판단사례·세법해석례
- `tax-ruling-decisions` — 심판청구·이의신청·판례
- `tax-ruling-pdf` — 세법집행기준

**source_label 체계:** 모든 Citation에 한국어 출처 표시. LLM 컨텍스트에도 `▶ 출처:` 포함.

### Phase 6 — Service Layer (장기)

| 태스크 | 핵심 |
|--------|------|
| 3-티어 상담 라우터 | Bot(무료) → Quick Check(5~10만원) → Premium(30~50만원) |
| 실질 거주 특례 인터뷰 | 주민등록 ≠ 실질 거주 발굴 → 1세대1주택 비과세 유지 가능성 탐색 |
| 행정 레이어 지도 시각화 | 조정+투기과열+토지거래허가 시점별 지도 오버레이 |
| 유형2 시뮬레이션 | 양도/증여/부담부증여 세액 비교 |

### 평가 지표 (KPI)

| 지표 | 정의 | 목표 |
|------|------|------|
| 세액 정확도 | 납부세액 오차 0원 | 100% |
| 특례 발굴율 | AI 제안 특례 중 세무사 확정 비율 | >70% |
| 초안 완성도 | 세무사 수정 없이 승인한 비율 | >80% |
| recall@k | 필수 조문 검색 성공률 | >95% |
| Tax-Gap 감소액 | AI 미사용 대비 납세자 절세 평균액 | 측정 후 목표 설정 |

### Phase 7 — 개정세법 사전 대응 (유형2 고객 커버리지, 장기)

**배경:** 한국 세법 개정 타임라인

| 시점 | 이벤트 | 우리 시스템 |
|------|--------|------------|
| 7~8월 | 기재부 세법개정안 발표 (PDF 공개) | ← **유일한 조기 입수 경로** |
| 9~12월 | 국회 심의 (변경 가능성 있음) | 미확정 — 반영 보류 |
| 12월 말 | 국회 통과 + 공포 → law.go.kr 등록 | API 수집 자동화 |
| 다음해 1월 1일 | 시행 (부칙 명시) | 벡터 DB 전환 |

**문제:** law.go.kr API는 공포(12월)된 법령만 제공. 개정안 발표(8월) ~ 공포(12월) 4개월간 API로 커버 불가.

**유형2 고객 니즈 (개정안 발표 이후):**
- "내년 세법 기준으로 올해 팔까요 vs 내년에 팔까요?" (가장 많은 질문)
- 개정안 적용 시 세액 차이 시뮬레이션
- 특례 일몰/신설 확인

**솔루션 설계:**

```text
기재부 세법개정안 PDF
    ↓
[PDF 파서] → 개정 조문 추출 + 시행예정일 파싱
    ↓
Pinecone namespace: "tax-law-pending" (별도 격리)
    ↓
쿼리 시: 현행법 + 개정예정법 두 가지 응답
    예: "현행 기준: 비과세 (12억 이하)"
        "개정안 기준(2027.1.1 시행예정): [변경 내용]"
    ↓
시행일 도래 시: "tax-law-pending" → "tax-law" 자동 이전
```

**구현 목록:**

| 태스크 | 파일 | 핵심 |
|--------|------|------|
| 개정안 PDF 파서 | `src/ingestion/collect_amendment_pdf.py` | 기재부 PDF → 개정 조문 추출 |
| pending namespace 업로드 | `src/ingestion/embed_amendment.py` | 시행예정일 메타데이터 포함 |
| 이중 검색 쿼리 | `src/retrieval/retriever_impl.py` | 현행 + pending 병렬 검색 |
| 개정 예고 UI 컴포넌트 | `src/ui.py` | "개정안 기준 시뮬레이션" 탭 |
| 자동 전환 스케줄러 | `scripts/promote_pending_law.py` | 시행일 0시 pending→main |

**개정안 입수 방법:** API 불가. 기재부 홈페이지(moef.go.kr) PDF 수동 다운로드 → `data/amendments/` 드롭 → 자동 파싱.

**주의:** 국회 심의 중 내용이 바뀔 수 있음. 개정안(안)과 확정 법률 명확히 구분해서 사용자에게 고지.

---

### 추가 논의 필요 (다모델 공동 검토 예정)

- BM25 sparse 인코딩 최적화 방식 (article_number 필드 설계)
- 유권해석 크롤링 허용 여부 + 데이터 라이선스 검토
- 평가 지표 가중치 확정
- 별표 이미지 OCR 파이프라인 도입 시점

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

---

## 도메인 계약

### TaxVerdict (7종)

```python
class TaxVerdict(str, Enum):
    EXEMPT             = "비과세"       # 소득세법 §89
    REDUCED            = "감면"         # 조특법 감면
    HEAVY_TAX          = "중과"         # 다주택자 +20%/+30%
    GENERAL            = "일반과세"     # 기본세율 6~45%
    SHORT_TERM         = "단기세율"     # 보유 1년 미만 70%, 1~2년 60%
    PARTIALLY_EXEMPT   = "고가주택"     # 12억 초과분 과세
    NEEDS_VERIFICATION = "사실관계부족"
```

### TaxAnswer (출력)

```python
@dataclass
class Citation:
    chunk_id: str
    article: str        # 예: "소득세법 시행령 제154조 제1항"
    excerpt: str        # 관련 조문 발췌
    law_version: str    # 적용 법령 버전 (시행일 기준)
    source_label: str   # 출처 한국어 표시 — "법령 (소득세법)", "국세청 질의회신", "조세심판원 심판청구" 등

@dataclass
class TaxAnswer:
    answer: str
    verdict: str
    confidence: float
    citations: List[Citation]   # chunk_id + source_label 포함 — 없으면 phantom 처리
    chunk_ids: List[str]
    missing_facts: List[str]
    warnings: List[str]
    expert_review_signals: List[ExpertReviewSignal]
```

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
│   │   ├── collect.py                    # law.go.kr XML 수집
│   │   ├── embed.py                      # 임베딩 + Pinecone 업로드 (source_label 포함)
│   │   ├── embed_rulings.py              # 유권해석 임베딩 (nts/decisions/pdf 등)
│   │   ├── collect_rulings_revision.py   # 세법해석정비 — deprecated_ids.json 관리
│   │   ├── collect_rulings_nts.py        # 질의회신·판단사례·세법해석례·쟁점별사례
│   │   ├── collect_rulings_decisions.py  # 판례·결정례 JSON API (action.do)
│   │   ├── collect_rulings_pdf.py        # 세법집행기준 PDF 파서
│   │   ├── area_designation_pipeline.py  # 규제지역 변경 감지 3-tier
│   │   └── admin_notices.py              # 행정/금융 고시 수집
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
│   │   └── retrieval_analyzer.py # RLVR 검색 품질 분석
│   ├── agents/
│   │   └── prompts.py           # RAG_SYSTEM, RED_TEAM, BLUE_DEFENSE 프롬프트
│   ├── pages/
│   │   └── admin.py             # Streamlit 어드민 페이지
│   ├── rag.py                   # 레거시 shim (신규 로직 추가 금지)
│   └── ui.py                    # Streamlit 채팅 UI (판단 로직 추가 금지)
├── data/
│   ├── golden/              # qa_pairs.json (debate 누적)
│   ├── debates/             # 개별 논쟁 기록 (.gitignore)
│   ├── red_wins/            # Red 승리 케이스 (.gitignore)
│   ├── blue_wins/           # Blue 방어 성공 케이스 (.gitignore)
│   ├── rulings/
│   │   ├── nts/             # 질의회신·판단사례·세법해석례 (taxlaw.nts.go.kr)
│   │   ├── decisions/       # 판례·결정례 (action.do JSON API)
│   │   ├── pdf/             # 세법집행기준 파싱 결과
│   │   ├── pdf_source/      # 원본 PDF 드롭 폴더 (양도소득세 집행기준-2024.pdf)
│   │   ├── deprecated_ids.json   # 폐지 예규 ID 목록
│   │   └── revision_cases.json   # 세법해석정비 전체 목록
│   ├── area_designations/   # 규제지역 수동 기준표 + 소스 상태
│   ├── feedback/            # 피드백 JSONL (.gitignore)
│   ├── raw/                 # law.go.kr XML (.gitignore)
│   └── processed/           # 파싱 JSON 청크 (.gitignore)
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
OPENAI_API_KEY=

PINECONE_API_KEY=
PINECONE_INDEX_NAME=tax-rag
PINECONE_NAMESPACE=tax-law
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1

BGE_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RETRIEVER_TOP_K=20
RETRIEVER_RERANK_TOP_N=7

MCP_PORT=8001
STREAMLIT_PORT=8501
```

---

## 개발 워크플로

```bash
pip install -r requirements.txt
cp .env.example .env

python -m src.ingestion.collect       # 법령 수집
python -m src.ingestion.embed         # 법령 Pinecone 업로드

# 유권해석 DB 수집 (순서 중요)
python -m src.ingestion.collect_rulings_revision --tax transfer   # 폐지 예규 목록
python -m src.ingestion.collect_rulings_nts --tax 양도소득세        # 질의회신·판단사례
python -m src.ingestion.collect_rulings_decisions --type tax_tribunal --keyword 양도
python -m src.ingestion.collect_rulings_pdf                        # 세법집행기준 PDF
python -m src.ingestion.embed_rulings nts                          # Pinecone 업로드
python -m src.ingestion.embed_rulings decisions
python -m src.ingestion.embed_rulings pdf

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

| 기관 | 종류 | 수집 방법 | source_label |
|------|------|-----------|--------------|
| 기획재정부 | 세법해석 사전답변·예규 | taxlaw.nts.go.kr 통합 (ic/qt 타입) | 국세청 세법해석례 |
| 국세청 | 예규·질의회신·심사결정 | taxlaw.nts.go.kr (qt/pd/hotissue) | 국세청 질의회신 |
| 조세심판원 | 심판청구 결정례 | taxlaw.nts.go.kr action.do API | 조세심판원 심판청구 |
| 대법원 | 판결 | taxlaw.nts.go.kr action.do API | 대법원 판례 |
| 국세청 (집행기준) | 양도소득세 집행기준 | PDF 파서 (`collect_rulings_pdf.py`) | 세법집행기준 |

> **통합 수집 원칙**: tt.go.kr / ntis.go.kr 별도 스크래핑 불필요. taxlaw.nts.go.kr 하나에서 전부 수집 가능.
> **세법해석정비** 먼저 실행 → `deprecated_ids.json` 생성 → 폐지 예규가 RAG에 들어가지 않음.

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
| is_related_party_transaction | §101 부당행위계산부인 — 특수관계자 저가양도 시 양도가액 시가 재계산 |

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
