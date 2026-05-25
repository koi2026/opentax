# CLAUDE.md

AI 코딩 어시스턴트(Claude Code 등)가 이 프로젝트에서 올바르게 동작하도록 안내하는 문서이다.

---

## Backlog (Claude Code 전용)

세션 시작 시 `AGENTS.md > 개발 로드맵` 을 확인한다.
사용자가 다른 작업을 요청하면 그것을 우선한다.

> Phase 1~6 전체 완료. 상세 이력은 git log 참조.
> 남은 운영 작업·장기 로드맵(BGE 파인튜닝·개정세법 대응 등)은 **AGENTS.md** 참조.

---

## 프로젝트 개요

한국 **양도소득세 비과세 / 감면 / 중과 여부 판단**을 위한 법령 RAG 엔진이다.

JSON 사실관계 입력 → L2(팩트체크) → L3(쿼리 보강) → L4(법령 검색 + LLM 추론) → L5(출력 검증) → TaxAnswer 반환.

**핵심 원칙:**
- 모든 답변은 반드시 검색된 조문에 근거해야 한다. LLM 기억에서 직접 답변하는 것은 허용하지 않는다.
- 조문 인용은 실제 검색된 chunk_id가 있는 것만 허용한다. (phantom citation 금지)
- 불확실한 사실관계가 있으면 결론을 내리지 말고 missing_facts에 명시한다.
- 모든 판단은 추적 가능(traceable)하고 감사 가능(auditable)해야 한다.
- **모든 세율·기간·금액 기준은 `TaxConstantsRegistry`와 `data/tax_tables/` JSON에서만 읽는다.** 계산기·파이프라인·서비스 레이어 어디에도 수치 리터럴을 박지 않는다. 이 원칙을 어기면 법령 개정 즉시 대응이 불가능해진다.

**시스템 철학:**
- **엔드투엔드 에이전트 자동화** — 법령 수집 → 임베딩 → 검색 → 판단 → 출력까지 전 과정이 에이전트 파이프라인으로 자동화된다. 인간이 개입하는 지점은 예외 처리와 최종 승인에 한정된다.
- **인간 전문가 즉시 개입 가능** — 파이프라인 전 단계의 입출력(fact_json, citations, debate_record, expert_review_signals)이 항상 노출된다. 세무사·전문가가 어느 단계에서든 판단 근거를 확인하고 개입할 수 있어야 한다.
- **전 과정 모니터링** — 추적 불가능한 블랙박스 판단을 허용하지 않는다. 모든 verdict는 검색된 chunk_id, 인용 조문, debate 기록과 함께 저장된다.
- **상수 외부화(No Magic Numbers)** — 세율·기간·금액 한도 등 세법이 정한 수치는 `TaxConstantsRegistry` 또는 `data/tax_tables/` JSON이 유일한 진실의 원천이다. 개정 발생 시 단일 지점만 수정하면 전 시스템에 반영된다. 이 원칙은 RAG 검색·계산기·시뮬레이션·검증 레이어 모두에 동등하게 적용된다.

---

## 핵심 스택 · 아키텍처 · 디렉터리 · 환경 변수

> 상세는 [AGENTS.md](AGENTS.md) 참조.

**핵심 요약:**
- 임베딩: Upstage Solar `solar-embedding-1-large-passage` (dim=4096)
- 벡터 DB: Pinecone Serverless (`tax-rag` 인덱스, `tax-law` 네임스페이스)
- Reranker: `BAAI/bge-reranker-v2-m3` (CrossEncoder, RERANK_TOP_N=7)
- LLM: Claude Sonnet 4.6 기본, Opus 4.7 고정밀
- 파이프라인: `src/domain/pipeline.py` (L1.5→L2→L3→L4→L5)

---

## 개발 워크플로

> 상세는 [AGENTS.md](AGENTS.md) 참조.

```bash
pip install -r requirements.txt && cp .env.example .env
streamlit run src/ui.py
python -m scripts.run_baseline_eval --workers 3
```

---

## 한국 법령 도메인 규칙

> 법령 계층 구조·유권해석 체계·핵심 판단 요소·Pinecone 버전 관리 — [AGENTS.md](AGENTS.md) 참조.

---

## L2 팩트체크 — 크리티컬 규칙

> [AGENTS.md](AGENTS.md) 참조.

---

## 책임소재 관리 원칙 (Critical)

**새로운 책임 이슈가 생기면 → `src/domain/confirmation.py`의 `CONFIRMATION_ITEMS`에 추가한다.**
L1.5 확인서는 파이프라인 입구 차단 장치다. 항목 중 하나라도 미확인이면 답변을 출력하지 않는다.

| key | 책임 내용 |
|-----|---------|
| `household_house_count_verified` | 세대 전체 주택 수 (분양권·입주권·오피스텔·지분·상속 포함) |
| `balance_or_registration_date_used` | 잔금 지급일 / 등기 접수일 중 빠른 날 사용 |
| `no_related_party` | 매수·매도인이 특수관계인이 아님 |
| `actual_residence_verified` | 주민등록 이전 후 실제 거주한 기간만 포함 |
| `acquisition_document_confirmed` | 취득서류 보유 확인 + 환산취득 적용 시 사후 세액변동 책임은 납세자에 있음을 인지 |

**새 항목 추가 패턴:** `CONFIRMATION_ITEMS` dict에 `(key, 질문 텍스트)` 추가 → `check_confirmation()` 자동 반영. UI·API는 별도 수정 없음.

---

## 상수 외부화 원칙 & 세법 개정 자동 반영 (Critical)

> 이 원칙은 세법 개정 대응에 그치지 않는다. 계산기(tax_calculator)·시뮬레이션(simulation_engine)·파이프라인(pipeline)·검증(output_validator) 등 **모든 레이어를 관통하는 설계 계약**이다.

**모든 수치와 기준은 반드시 외부화한다. 코드에 하드코딩 절대 금지.**

| 항목 | 구현 위치 | 비고 |
|------|---------|------|
| 세율 테이블 (6%~45%, 단기 70%/60%) | `TaxConstantsRegistry` | 개정 시 registry 값만 수정 |
| 중과세율 (+20%/+30%) | `TaxConstantsRegistry` | |
| 중과 한시적 면세 기간 | `TaxConstantsRegistry.HEAVY_TAX_SUSPENSION_END` | |
| 장기보유특별공제율 표1/표2 | `data/tax_tables/` JSON | 개정 시 JSON만 교체 |
| 1세대1주택 비과세 한도 (12억) | `TaxConstantsRegistry.EXEMPT_THRESHOLD` | |
| 일시적2주택 처분기한 (3년) | `TaxConstantsRegistry` | |
| 상생임대 특례 유효기간 | `TaxConstantsRegistry.SANGSAENG_WINDOW_*` | |
| 이월과세 기산 기간 (10년) | `TaxConstantsRegistry.IOTA_PERIOD_YEARS` | |
| 기준시가 (공시가격) | 상위 수집기에서 제공 — 엔진 역할 아님 | fact_json으로 수신 |

**법령 개정 감지 자동화:** `scripts/detect_law_changes.py` → 매일 23:00 실행 → 변경 감지 시 알림 + Pinecone 재인덱스.

**개정 시 처리 목표 (전 과정 자동화 + 모니터링):**
| 레이어 | 현재 | 목표 |
|--------|------|------|
| 법령 조문 | ✅ Pinecone 자동 재인덱스 | ✅ 완료 |
| TaxConstantsRegistry | 🔧 코드 수동 수정 | 🔲 LLM 자동 파싱 → PR |
| 골든셋·eval | 🔧 수동 케이스 검토 | 🔲 eval 자동 재실행 → 영향 케이스 Slack 알림 |
| BGE reranker | 🔧 수동 (50건 초과 시) | 🔲 자동 파인튜닝 트리거 |

> 환산취득가액·사전 대응 상세 → [AGENTS.md](AGENTS.md) 참조.

---

## 코딩 규칙

- 모든 public 함수에 Python type hints를 작성한다.
- 도메인 모델은 `src/domain/` dataclass를 사용한다. Pydantic은 API 스키마 전용이다.
- 사용자 노출 텍스트는 한국어, 함수명·변수명·코드 주석은 영어로 작성한다.
- 모든 프롬프트는 `src/agents/prompts.py`에서 버전 관리한다. 인라인 작성은 금지이다.
- 커밋 메시지: 한국어, `타입: 요약` 형식 (feat/fix/docs/refactor/test/chore)

---

## 자율 실행 vs. 먼저 물어볼 것 (바이브코딩 기준)

**아래 항목은 먼저 물어보지 않고 바로 실행한다:**
- 버그 수정, 기존 기능 개선, 성능 최적화
- 테스트 케이스 추가·수정, 골든셋 관리
- 문서·주석 업데이트
- CLAUDE.md / AGENTS.md 업데이트
- `CONFIRMATION_ITEMS` 신규 항목 추가 (책임소재)
- `TaxConstantsRegistry` 상수 값 수정 (세법 개정 반영)
- `DANGER_KEYWORD_MAP` 키워드 추가 (검색 개선)

**아래 항목은 방향을 먼저 확인하고 진행한다:**
- 파이프라인 레이어(L1~L5) 구조 변경
- 임베딩 모델·Pinecone 스키마·namespace 변경
- 새로운 외부 의존성(라이브러리·서비스) 도입
- 판단 카테고리(TaxVerdict) 추가·삭제
- `src/domain/` 핵심 dataclass 스키마 변경
- 비즈니스 로직(세법 적용 방식) 변경 — 코드 수정 전 설명 먼저

---

## 절대 금지 사항 (Critical DO NOTs)

- API 키, OC 코드, 인덱스명 **하드코딩 금지** — .env에서만 로드한다.
- **세율·기간·금액 기준값 코드 리터럴 금지** — `TaxConstantsRegistry.get()` 또는 `data/tax_tables/` JSON 사용 의무. `tax_calculator.py`, `simulation_engine.py`, `output_validator.py` 등 모든 파일에 동등 적용.
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
