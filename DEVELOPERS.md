# Tax-RAG 개발 가이드

> 대상: 팀 개발자  
> 참조: [CLAUDE.md](CLAUDE.md) · [AGENTS.md](AGENTS.md)

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
기재부 2,304건·국세청 37,400건 본문 수집 완료. Pinecone 재임베딩까지 완료됐습니다.

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
- `src/ui/app.py` — Streamlit (세무사용 웹, 포트 8501)
- `src/api/main.py` — FastAPI (외부 연동 REST, 포트 8000)
- `src/mcp/server.py` — FastMCP (RAG 검색 실행 계층, 포트 8001)

**현재 구조:** UI는 API만 호출하고, API는 MCP 검색 tool을 통해 Pinecone/BGE 검색을 수행합니다.

---

## 완료된 것 (2026-05-26 기준)

### ✅ BLOCKER-1 해결: 유권해석 본문 수집

**원인:** `taxlaw.nts.go.kr/action.do`의 올바른 actionId는 `ASIQTB002PR01`, paramData 구조는 `{"dcmDVO": {"ntstDcmId": "..."}}`  
기존 코드는 `ASIQTA002MR01` 등을 추정으로 썼는데 모두 실패. USEQTA002P 페이지 인라인 JS 역공학으로 확인.

**수정된 파일:**
- `src/ingestion/collect_rulings_moef.py` — actionId 수정 + dcmDVO 파라미터 구조 + `--resume` 로직(answer 빈 파일 재수집)
- `src/ingestion/collect_rulings_nts_interp.py` — 동일 수정

**결과:**
- 기재부(moef): 2,304/2,305건 본문 수집 완료 (99.9%) → Pinecone `tax-ruling-moef` 2,305건 업로드 완료
- 국세청(nts_interp): 37,400건 수집 완료 → Pinecone `tax-ruling-nts-interp` 37,400건 업로드 완료
- `embed_rulings.py`에 `--resume` 플래그 추가 (중단 후 재개 시 중복 업로드 방지)

### ✅ Reranker 서빙 버그 3종 수정

| 파일 | 수정 | 이유 |
|------|------|------|
| `src/infra/reranker.py` | `_MAX_TEXT_CHARS` 400→**900자** | 한국 법령 단서조항·부칙이 400자 이후에 위치하는 경우 있음 |
| `src/infra/reranker.py` | `_MAX_LENGTH` 256→**512** | 파인튜닝(512)과 서빙(256) 불일치 → 점수 분포 왜곡 수정 |
| `scripts/run_baseline_eval.py` | 모델 프로모션 게이트 추가 | 정확도 85% 미달 시 `.env` 업데이트 차단 (기존에는 미달해도 프로모션됨) |

---

## 완료된 것 (2026-05-28 추가)

### ✅ BGE 재파인튜닝 완료 (2026-05-28, 31시간 15분 CPU)

```
훈련 데이터: data/reranker_pairs.jsonl
  - debate 기반 pairs: ~326쌍
  - nts_interp answer 추출: 1,823쌍  ← scripts/extract_ruling_pairs.py 신규 작성
  - moef answer 추출: 374쌍
  - 합계: ~2,523쌍 (complete=2,190+, pos_only 소수)

결과:
  BGE 내부 eval 정확도: 0.9472 (94.72%)
  F1: 0.9492 | Precision: 0.9136 | Recall: 0.9877
  Average Precision: 0.9768
  모델 저장: data/models/bge-reranker-tax-rag/ (2,182MB)
```

### ✅ Eval 재실행 결과 (2026-05-28)

```
총 케이스: 142건 | 비교 가능: 112건
정확도: 90/112 = 80.4%  ← 파인튜닝 전과 동일
평균 신뢰도: 0.779 | 평균 응답시간: 66.2초
소요: ~3,390초 | 비용: ~$2.56
```

**오답 22건 유형 분석:**

| 유형 | 건수 | 패턴 | 원인 추정 |
|------|------|------|----------|
| 공익수용 감면 | 6건 | `감면 → 일반과세` | 조특§77 조문 Pinecone 미흡 |
| 장기임대 감면 | 4건 | `감면/일반과세 ↔ 비과세` | 조특§97의3 커버리지 부족 |
| 중과 → 일반과세 | 3건 | 2026 중과부활 미적용 | 최신 개정 법령 미수집 |
| 농어촌주택 특례 | 2건 | 조특§99의4 지역 제외 | 별표 지역 목록 조문 누락 |
| 상속주택 | 3건 | 5년 기준 혼동 | L4 추론 오류 |
| 기타 | 4건 | 다양 | — |

**분석:** BGE reranker 내부 정확도는 94.72%로 향상됐으나 파이프라인 정확도는 변화 없음.  
→ 병목이 reranker가 아닌 **Pinecone 법령 조문 커버리지**에 있음을 시사.  
특히 조특§77(공익수용), §97의3(장기임대), §99의4(농어촌주택) 조문이 약함.

**다음 우선순위:**
1. 오답 케이스 조문 커버리지 점검 (`tax-law` 네임스페이스)
2. 2026년 중과부활 최신 법령 수집·재인덱스
3. 추가 골든셋 케이스 생성 (현재 142건 → 목표 300건)

---

## ⚠️ 확정된 인프라 결정: BGE 파인튜닝은 Colab에서 실행

**배경:** 로컬 CPU로 2,500쌍 × 4 epochs = **~27시간 소요** (스텝당 23초).  
동일 작업을 Google Colab T4 GPU에서 실행하면 **30분 이내**, 비용 $0.5 미만.

**파인튜닝은 누적 전체 데이터로 재학습** (새 50건만 학습하면 catastrophic forgetting 발생).  
→ 데이터가 쌓일수록 매번 전체 재학습 필요 → CPU는 구조적으로 부적합.

**앞으로 파인튜닝 실행 방법 (Colab):**

```
1. data/reranker_pairs.jsonl 다운로드
2. scripts/finetune_reranker.py 다운로드
3. Colab에서:
   !pip install sentence-transformers
   !python finetune_reranker.py --epochs 4
4. 생성된 data/models/bge-reranker-tax-rag/ 폴더 로컬로 다운로드
5. 기존 data/models/bge-reranker-tax-rag/ 교체
6. eval 재실행 → 정확도 확인
```

**파인튜닝 트리거 기준:** `data/red_wins/` 50건 초과 시 재실행 권장.

---

### 🟡 알려진 기술 부채

| 항목 | 위치 | 영향 |
|------|------|------|
| MCP 검색 서버 의존 | `src/api/main.py` → `src/mcp/server.py` | API 판단 전 MCP 서버가 먼저 떠 있어야 함 |
| MCP 검색 범위 구식 | `src/mcp/server.py` | 유권해석 네임스페이스 미포함 시 검색 누락 |
| eval set 33건뿐 | BGE 평가 | 1건 차이 = 3% 변동, 통계 신뢰 낮음 |

---

## 데이터 현황

| 소스 | 구속력 순위 | 파일 수 | answer 상태 | Pinecone 상태 |
|------|-----------|---------|-------------|--------------|
| 법령 조문 (소득세법 등) | 최상위 | — | ✅ | ✅ `tax-law` |
| 기재부 법령해석 | 유권해석 1위 | 2,305건 | ✅ 2,304건 수집 완료 | ✅ `tax-ruling-moef` 2,305건 |
| 국세청 질의회신 | 유권해석 2위 | ~3,000건 | ✅ | ✅ `tax-ruling-nts` |
| 국세청 법령해석 | 유권해석 2위 | 37,400건 | ✅ 수집 완료 | ✅ `tax-ruling-nts-interp` 37,400건 |
| 심판원 결정례 | 준사법적 결정 | ~수천건 | ✅ | ✅ `tax-ruling-decisions` |

BGE Reranker:
- 위치: `data/models/bge-reranker-tax-rag/` (2026-05-28 파인튜닝 완료, 2,182MB)
- 내부 eval: acc=0.9472, avg_precision=0.9768 (2,523쌍 학습)
- 파이프라인 정확도: 80.4% (142건 중 112건 비교, 90건 정답)

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

#### A-3. ✅ Pinecone 재임베딩 완료

```bash
python -m src.ingestion.embed_rulings moef        # 2,305건 완료
python -m src.ingestion.embed_rulings nts_interp  # 37,400건 완료
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
국토교통부 API 또는 법령 DB 연동. 현재 MCP `check_area_designation`은 수동 기준표 기반이며, 외부 API 연동은 후속 과제.

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
✅ BLOCKER-1 해결 (A-1)
    ↓
✅ moef 2,304건 본문 수집 완료
✅ nts_interp 37,400건 수집 완료
    ↓
✅ Pinecone 재임베딩 (A-3) — moef 2,305건 + nts_interp 37,400건
    ↓
✅ eval 재실행 + 훈련 데이터 자동 추출 (B-1, B-2)
    ↓
✅ BGE 재파인튜닝 (B-3) — 파인튜닝 후 파이프라인 정확도 80.4% (변화 없음)
    ↓
⏳ 법령 커버리지 보완 (조특§77, §97의3, §99의4 + 2026 중과부활)
    ↓
⏳ MCP 업그레이드 / 어드민 개선 (병렬 가능)
```

---

## 환경 설정

```bash
git clone [repo]
pip install -r requirements.txt
cp .env.example .env  # API 키는 별도 전달

python -m src.mcp.server --sse   # MCP 검색 서버 (포트 8001)
uvicorn src.api.main:app         # API (포트 8000)
streamlit run src/ui/app.py      # UI (포트 8501)
```

검증은 Docker 기준으로 수행한다: `docker compose exec ...`, `docker compose logs`, `docker compose ps` 우선.

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
