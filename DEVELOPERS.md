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

그래서 국세청 37,400건, 기재부 2,305건을 수집했더니 — 이번엔 제목만 있고 본문이 비어 있었습니다.  
`taxlaw.nts.go.kr/action.do` API의 actionId를 역공학으로 분석했고, **USEQTA002P 페이지 인라인 JS에서 정확한 파라미터를 찾아냈습니다.**  
기재부 2,304건 본문 수집 완료, 국세청 37,400건 수집 진행 중입니다.

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

## 완료된 것 (2026-05-26 기준)

### ✅ BLOCKER-1 해결: 유권해석 본문 수집

**원인:** `taxlaw.nts.go.kr/action.do`의 올바른 actionId는 `ASIQTB002PR01`, paramData 구조는 `{"dcmDVO": {"ntstDcmId": "..."}}`  
기존 코드는 `ASIQTA002MR01` 등을 추정으로 썼는데 모두 실패. USEQTA002P 페이지 인라인 JS 역공학으로 확인.

**수정된 파일:**
- `src/ingestion/collect_rulings_moef.py` — actionId 수정 + dcmDVO 파라미터 구조 + `--resume` 로직(answer 빈 파일 재수집)
- `src/ingestion/collect_rulings_nts_interp.py` — 동일 수정

**결과:**
- 기재부(moef): 2,304/2,305건 본문 수집 완료 (99.9%)
- 국세청(nts_interp): 37,400건 수집 중 (진행중)
- 이후: Pinecone 재임베딩 → eval 재실행 → BGE 훈련 데이터 자동 추출

### ✅ Reranker 서빙 버그 3종 수정

| 파일 | 수정 | 이유 |
|------|------|------|
| `src/infra/reranker.py` | `_MAX_TEXT_CHARS` 400→**900자** | 한국 법령 단서조항·부칙이 400자 이후에 위치하는 경우 있음 |
| `src/infra/reranker.py` | `_MAX_LENGTH` 256→**512** | 파인튜닝(512)과 서빙(256) 불일치 → 점수 분포 왜곡 수정 |
| `scripts/run_baseline_eval.py` | 모델 프로모션 게이트 추가 | 정확도 85% 미달 시 `.env` 업데이트 차단 (기존에는 미달해도 프로모션됨) |

---

## 지금 진행 중인 것

### 🔄 nts_interp 37,400건 본문 수집 중

완료 후 자동으로 이어지는 작업:
```bash
python -m src.ingestion.embed_rulings moef       # Pinecone 재임베딩
python -m src.ingestion.embed_rulings nts_interp
```

---

### 🟡 알려진 기술 부채

| 항목 | 위치 | 영향 |
|------|------|------|
| UI가 API 서버 우회 | `src/ui.py` → `chat_turn()` 직접 import | BGE가 UI 프로세스 실행, 리소스 분리 불가 |
| MCP 검색 범위 구식 | `src/api/mcp_server.py` | 유권해석 네임스페이스 미포함 |
| eval set 33건뿐 | BGE 평가 | 1건 차이 = 3% 변동, 통계 신뢰 낮음 |
| MCP `check_area_designation` stub | `mcp_server.py` | 실제 API 없이 빈 응답 |

---

## 데이터 현황

| 소스 | 구속력 순위 | 파일 수 | answer 상태 | Pinecone 상태 |
|------|-----------|---------|-------------|--------------|
| 법령 조문 (소득세법 등) | 최상위 | — | ✅ | ✅ `tax-law` |
| 기재부 법령해석 | 유권해석 1위 | 2,305건 | ✅ 2,304건 수집 완료 | ⏳ 재임베딩 대기 |
| 국세청 질의회신 | 유권해석 2위 | ~3,000건 | ✅ | ✅ `tax-ruling-nts` |
| 국세청 법령해석 | 유권해석 2위 | 37,400건 | 🔄 수집 진행 중 | ⏳ 재임베딩 대기 |
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

#### A-1. ✅ 유권해석 본문 수집 해결 (BLOCKER-1 완료)

`ASIQTB002PR01` actionId + `{"dcmDVO": {"ntstDcmId": "..."}}` 구조로 수정 완료.  
기재부 2,304건 수집 완료. 국세청 37,400건 수집 진행 중.

#### A-2. ✅ 수집 파이프라인 신뢰성

- `--resume` 로직 수정 완료: `파일 존재 AND answer != ""` 둘 다 충족해야 스킵
- 실패 건 자동 재시도 큐는 미구현 (현재 조용히 실패)

#### A-3. Pinecone 재임베딩 (국세청 수집 완료 후)

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

`src/pages/admin.py` 어드민 "✏️ 전문가 검토" 서브탭으로 통합됨 (기존 `labeling.py` 삭제).

- 사실관계 표시 + 전문가 verdict·확신도·메모 입력 → `expert_labels.json` 저장
- 신규 케이스 직접 입력 폼 (골든셋 추가)
- CSV 내보내기

추가로 연결이 필요한 것:
- "현재 파이프라인으로 재판정" 버튼 → 실시간 결과 비교
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
✅ BLOCKER-1 해결 (A-1) — 완료
    ↓
✅ moef 2,304건 본문 수집 완료
🔄 nts_interp 37,400건 수집 진행 중
    ↓
⏳ Pinecone 재임베딩 (A-3) — nts_interp 완료 후
    ↓
⏳ eval 재실행 + 훈련 데이터 자동 추출 (B-1, B-2)
    ↓
⏳ BGE 재파인튜닝 (B-3)
    ↓
⏳ MCP 업그레이드 / 어드민 개선 (병렬 가능)
```

nts_interp 수집 완료되면 `embed_rulings`부터 순서대로 진행합니다.

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
