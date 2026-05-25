# Tax-RAG 개발 요청서

> 작성: 정찬양 (프로젝트 설계·도메인)  
> 대상: 개발자 A, 개발자 B  
> 작성일: 2026-05-25  
> 참조: [CLAUDE.md](CLAUDE.md) · [AGENTS.md](AGENTS.md)

---

## 먼저 읽어주세요

혼자서 너무 많이 진행해버렸습니다.  
설계부터 수집기·파이프라인·임베딩·파인튜닝·UI까지 혼자 하다 보니  
정작 검증하고 개선해야 할 부분이 쌓였습니다.

이 문서는 지시서가 아닙니다.  
**"이런 문제가 있고, 이런 방향으로 풀어가고 싶은데 같이 해줄 수 있어?"** 라는 요청서입니다.

두 분 모두 저보다 특정 영역은 훨씬 잘 알 것입니다.  
방향이나 구현 방식에 의견 있으면 언제든 주세요. 코드보다 판단이 더 중요한 프로젝트입니다.

Claude Code CLI(`claude` 명령어)로 코드베이스 질문을 바로 할 수 있습니다.  
이 레포에 `.claude/` 설정이 있어서 프로젝트 컨텍스트를 알고 있습니다.

---

## 우리가 만드는 것

**한국 양도소득세 비과세·감면·중과 여부를 판단하는 법령 RAG 시스템**입니다.

세무사가 사건 사실관계를 입력하면 → 관련 법령과 유권해석을 검색하고 → LLM이 근거 조문을 인용하면서 판단을 내립니다.

"LLM이 알아서 답하는" 시스템이 아닙니다.  
**검색된 조문에 근거가 있어야만 답변이 나오는** 시스템입니다.  
세금 판단은 틀리면 납세자에게 실제 피해가 생기기 때문입니다.

---

## 우리가 걸어온 길

처음에는 법령 조문만 임베딩해서 검색했습니다.  
정확도가 아쉬워서 세법 전용으로 BGE Reranker를 파인튜닝했습니다.

그런데 알고 보니 **유권해석(국세청·기재부 질의회신)이 수집이 안 돼 있었습니다.**  
세법은 조문보다 유권해석이 더 중요합니다. "법 조문은 이렇지만 해석은 이렇게 해라"는 결정들이 실무를 지배합니다.

그래서 국세청 37,400건, 기재부 2,305건을 수집했더니 — **이번엔 제목만 있고 본문이 비어 있었습니다.**  
`taxlaw.nts.go.kr/action.do` API가 예상대로 안 됩니다.  
**이 API를 뚫는 것이 지금 가장 급한 과제입니다.**

---

## 왜 1000건 인간 레이블이 필요 없는가

> "결국 사람이 1000건 골든셋 승인해줘야 하지 않나? 예규·해석·판례로 극복 못 하나?"

**훈련 데이터로는 극복 가능합니다.** 유권해석 데이터 자체가 레이블입니다.

```
국세청 해석 1건 =
  question: "2주택자가 일시적 취득 후 3년 내 양도하면 비과세?"
  answer:   "소득세법 제89조에 의거 비과세 해당..."
              ↑ answer가 인용한 법령 조문 = (query → relevant_chunk) 레이블
```

answer 본문이 채워지면 37,400건 전부가 훈련 쌍이 됩니다. 사람이 한 건도 안 봐도 됩니다.

| 데이터 전략 | 크기 | 인간 개입 | 조건 |
|------------|------|-----------|------|
| 해석 answer → 인용 법령 자동 추출 | 최대 37,400건 | 0건 | **answer 본문 수집 완료 필수** |
| LLM judge (Claude)가 relevance 판정 | 무제한 | 0건 | API 비용 (백만원 OK) |
| RVRL debate pair 자동 생성 | eval 건수 × N | 0건 | 현재 구현됨 |
| 전문가 직접 레이블 | **50~100건** | 50~100건 | 엣지 케이스·확신 오판만 |

**전문가 검수가 반드시 필요한 범위:**
- Eval set 핵심 50건 (verdict 유형별 10건, 도메인 전문가 확인 필수)
- 모델이 확신 있게 틀린 케이스 (confidence 높은데 오답)
- LLM judge는 "Claude가 Claude를 평가"하는 구조라 catastrophic error를 못 잡음

**결론:** 1000건 인간 레이블은 answer 본문이 없어서 생기는 차선책입니다.  
본문만 채우면 훨씬 좋은 훈련 데이터를 자동으로 뽑을 수 있습니다.

---

## 대원칙

코드를 어떻게 바꾸든 아래 원칙은 지켜야 합니다.

| 원칙 | 이유 |
|------|------|
| **모든 답변은 검색된 조문에 근거** | LLM 기억으로 답하면 법적 책임 소재 없음 |
| **세율·기간·금액은 `TaxConstantsRegistry`에서만** | 세법 개정 시 한 곳만 수정하면 전체 반영 |
| **BGE Reranker 생략 불가** | 검색 정확도의 핵심. 없으면 엉뚱한 조문 인용 |
| **확인서(L1.5) 통과 전 답변 차단** | 사실관계 불확실하면 결론 내지 않음 |
| **phantom citation 금지** | 검색된 chunk_id에 없는 조문 인용 불가 |

---

## 현재 시스템 구조

```
[사용자 입력] 사건 사실관계 JSON
       ↓
[L1.5] 확인서 체크 — 미확인 항목 있으면 질문으로 차단
       ↓
[L2]   팩트체크 — 결정적 누락 사실관계 검출
       ↓
[L3]   쿼리 보강 — 검색용 키워드 생성
       ↓
[L4]   법령 검색 + LLM 추론
       │   Pinecone 5개 네임스페이스 (구속력 높은 순):
       │     tax-law              (법령 조문 — 최상위 근거)
       │     tax-ruling-moef      (기재부 법령해석 — 유권해석 최고 권위) ← 본문 수집 필요
       │     tax-ruling-nts       (국세청 질의회신)
       │     tax-ruling-nts-interp (국세청 법령해석) ← 본문 수집 필요
       │     tax-ruling-decisions  (심판원 결정례 — 준사법적)
       │   BGE Reranker로 최종 조문 선택
       ↓
[L5]   출력 검증 — phantom citation 검출, confidence 계산
       ↓
[출력] verdict + 근거 조문 + debate 기록
```

**3개 서버:**
- `src/ui.py` — Streamlit (세무사용 웹, 포트 8501)
- `src/api/chat_api.py` — FastAPI (외부 연동 REST, 포트 8000)
- `src/api/mcp_server.py` — FastMCP (Claude Desktop 연동, 7개 도구)

**알려진 구조 문제:** UI가 API 서버를 거치지 않고 `chat_turn()`을 직접 import합니다.  
BGE Reranker가 UI 프로세스에서 실행됩니다. 리소스 분리가 안 됩니다.

---

## 지금 막혀 있는 것 (블로커)

### 🔴 BLOCKER-1: 유권해석 본문 수집 실패

**상황:** 국세청 37,400건 + 기재부 2,305건 수집은 됐는데 **본문(answer)이 전부 비어 있습니다.**  
웹 브라우저에서 열면 내용이 잘 나옵니다. API가 actionId를 잘못 쓰거나 세션 인증이 필요한 것으로 추정됩니다.

**수집기 위치:**  
- `src/ingestion/collect_rulings_moef.py` (기재부)  
- `src/ingestion/collect_rulings_nts_interp.py` (국세청)

**해결 방향 후보:**
1. 브라우저 네트워크 탭 → 실제 XHR 파라미터 확인 → actionId 교정
2. Selenium/Playwright로 세션 취득 후 API 호출
3. 직접 HTML 스크래핑

이게 해결돼야 훈련 데이터, Pinecone 재임베딩, BGE 재파인튜닝이 전부 가능합니다.

---

### 🟡 알려진 기술 부채

| 항목 | 위치 | 영향 |
|------|------|------|
| UI가 API 서버 우회 | `src/ui.py` → `chat_turn()` 직접 import | BGE가 UI 프로세스 실행, 리소스 분리 불가 |
| `--resume`이 빈 파일 스킵 | 수집기 공통 | 재수집 시 answer="" 파일 덮어쓰기 안 됨 |
| MCP 검색 범위 구식 | `src/api/mcp_server.py` | 유권해석 네임스페이스 미포함 |
| eval set 33건뿐 | BGE 평가 | 1건 차이 = 3% 변동, 통계 신뢰 낮음 |
| MCP `check_area_designation` stub | `mcp_server.py` | 실제 API 없이 빈 응답 |

---

## 데이터 현황

| 소스 | 구속력 순위 | 파일 수 | answer 상태 | Pinecone 상태 |
|------|-----------|---------|-------------|--------------|
| 법령 조문 (소득세법 등) | 최상위 | — | ✅ | ✅ `tax-law` |
| 기재부 법령해석 | 유권해석 1위 | 2,305건 | ❌ 제목만 | ⏳ `tax-ruling-moef` |
| 국세청 질의회신 | 유권해석 2위 | ~3,000건 | ✅ | ✅ `tax-ruling-nts` |
| 국세청 법령해석 | 유권해석 2위 | 37,400건 | ❌ 제목만 | ⏳ `tax-ruling-nts-interp` |
| 심판원 결정례 | 준사법적 결정 | ~수천건 | ✅ | ✅ `tax-ruling-decisions` |

BGE Reranker:
- 위치: `data/models/bge-reranker-tax-rag/` (epoch 2 best checkpoint)
- 현재 정확도: acc=0.9545, avg_precision=0.9805 (eval 33건 기준, 신뢰도 낮음)

---

## 요청 사항

두 가지 번들이 있습니다. 어느 쪽이 더 맞는지, 혹은 다른 의견 있으면 말해주세요.  
순서나 범위도 조정 가능합니다.

---

### Bundle A — 데이터 파이프라인 & 에이전트

> LangGraph·멀티에이전트 관심 있는 분께 더 맞을 수 있는 방향

**핵심 질문:** "37,400건 해석 데이터를 어떻게 안정적으로 쌓고,  
그 데이터가 에이전트 파이프라인 위에서 자동으로 흐르게 할 수 있을까?"

#### A-1. 유권해석 본문 수집 해결 (최우선, BLOCKER-1)

```
브라우저 네트워크 탭 → 실제 XHR 분석 → actionId/파라미터 교정
또는 Playwright 세션 기반 수집

목표: moef 2,305건 + nts_interp 37,400건 answer 필드 90% 이상 채우기
```

이게 해결되면 나머지 훈련·임베딩·eval이 전부 언블록됩니다.

#### A-2. 수집 파이프라인 신뢰성

- `--resume` 로직 수정: `파일 존재 AND answer != ""` 둘 다 충족해야 스킵
- 실패 건 자동 재시도 큐 (현재 조용히 실패함)
- 수집 완료 → Pinecone 임베딩 자동 트리거 체인

#### A-3. Pinecone 재임베딩

answer 본문 수집 완료 후:
```bash
python -m src.ingestion.embed_rulings moef
python -m src.ingestion.embed_rulings nts_interp
```

#### A-4. MCP 서버 업그레이드

현재 MCP는 단순 함수 래퍼입니다. 세무사가 Claude Desktop에서 바로 세법 질문하는 인터페이스가 될 수 있습니다.

- 7개 도구가 멀티 네임스페이스 검색하도록 수정
- `analyze_exemption`에 L1.5 확인서 체크 통합 (현재 우회됨)
- 응답 구조화: `{ verdict, confidence, citations: [{chunk_id, law, excerpt}], reasoning }`
- 스트리밍 응답 (현재 10~20초 대기)

LangGraph로 멀티스텝 세법 분석 에이전트를 MCP 위에 올리는 구조도 가능합니다.  
관심 있으면 함께 설계해봐요.

#### A-5. 조정대상지역 자동조회

현재 수동 입력입니다. 주소 → 자동 판별로 바꾸면 오류가 크게 줄어듭니다.  
국토교통부 API 또는 법령 DB 연동. MCP `check_area_designation` stub 채우기.

---

### Bundle B — 모델 품질 & 평가 체계

> 멀티모달·ML 배경이 있는 분께 더 맞을 수 있는 방향

**핵심 질문:** "이 시스템이 실제로 잘 작동하는지 어떻게 측정하고,  
사람 검수를 최소화하면서 모델을 개선할 수 있을까?"

#### B-1. Eval 체계 재구축

현재 골든셋 142건, BGE eval 33건 — 둘 다 너무 작습니다.

```
목표:
  골든셋: 142건 → 500건 (AI 생성 + LLM judge 검증)
  BGE eval: 33건 → 150건
  세액 계산 정확도 추가 (현재는 verdict 분류만)
  eval 자동화: push to main → eval 자동 실행 → 결과 리포트
```

#### B-2. 훈련 데이터 자동 생성 파이프라인

answer 본문 수집 완료 후 (Bundle A 의존):

```python
# 각 해석 레코드에서 (query, relevant_law_chunk) 쌍 자동 추출
# answer 텍스트 → 인용 법령 추출 → Pinecone에서 실제 chunk 매칭
# → BGE 훈련 데이터 자동 생성
```

RVRL debate 자동화도 포함:
```
scripts/run_debate.py → (query, positive, negative) 쌍 → data/reranker_training/
```

#### B-3. BGE Reranker 재파인튜닝

```bash
python scripts/finetune_reranker.py --epochs 4
```

- 현재 베이스라인: acc=0.9545 (eval 33건, 신뢰도 낮음)
- 목표: eval 150건 기준 acc 측정 + 이전 대비 향상 확인
- 데이터 충분하면 Solar 임베딩 파인튜닝까지 가능

#### B-4. 레이블링 UI 개선

`src/pages/labeling.py` — 이미 구현됐는데 파이프라인과 연결이 안 됩니다.

- "현재 파이프라인으로 재판정" 버튼 → 실시간 결과 비교
- chunk_id 수동 입력 (gold_chunk_ids 없는 83건 처리)
- 레이블 완료 → BGE 훈련 데이터 자동 변환

#### B-5. 어드민 화면 — 시스템 건강도 대시보드

현재 어드민이 수집 현황은 보여주는데, **대원칙이 시각적으로 드러나지 않습니다.**

```
원하는 것:
  - 각 네임스페이스 answer 완성도 (%, 건수)
  - BGE 최신 eval 정확도
  - 최근 판단: 확인서 차단 건수 / phantom citation 검출 건수
  - 골든셋 크기 / 레이블 완료율
  - 데이터 파이프라인 상태 (수집 → 임베딩 → 모델 흐름)
```

어드민이 "시스템이 대원칙대로 작동하고 있는가"를 한눈에 보여주면 좋겠습니다.

---

## 실행 순서 참고

```
BLOCKER-1 해결 (A-1)
    ↓
Pinecone 재임베딩 (A-3)
    ↓
eval 재실행 + 훈련 데이터 자동 추출 (B-1, B-2)
    ↓
BGE 재파인튜닝 (B-3)
    ↓
MCP 업그레이드 / 레이블링 UI / 어드민 (병렬 가능)
```

A-1이 모든 것의 전제입니다. 여기서 막히면 다른 건 병렬로 진행하면 됩니다.

---

## 환경 설정

```bash
git clone [repo]
pip install -r requirements.txt
cp .env.example .env  # API 키는 별도 전달

streamlit run src/ui.py          # UI (포트 8501)
uvicorn src.api.chat_api:app     # API (포트 8000)
python src/api/mcp_server.py     # MCP (Claude Desktop용)
```

주요 환경변수: `.env.example` 참고

---

## 코딩 규칙 (핵심만)

```python
# ✅ 이렇게
threshold = TaxConstantsRegistry.get("EXEMPT_THRESHOLD")

# ❌ 이렇게 하면 안 됨
if price > 1_200_000_000:   # 세법 개정 시 찾을 수가 없음
```

- 세율·기간·금액 리터럴 코드 안에 박으면 안 됩니다 → `TaxConstantsRegistry` 또는 `data/tax_tables/*.json`
- 프롬프트는 `src/agents/prompts.py`에서만 관리, 인라인 작성 금지
- 사용자 텍스트는 한국어, 코드·변수명은 영어
- 커밋 메시지: 한국어, `feat/fix/docs/refactor/test/chore: 요약`

자세한 규칙: [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md)

---

## 궁금한 것, 하고 싶은 것

방향이나 설계 얘기는 저한테 직접 주세요.  
코드 질문은 `claude` CLI로 레포에서 바로 물어보면 됩니다.

잘 부탁드립니다.
