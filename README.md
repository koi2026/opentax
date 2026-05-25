# RAW Agent — 양도소득세 법령 RAG 시스템

> **한국 양도소득세 비과세·감면·중과 판단을 위한 법령 기반 AI 추론 엔진**  
> 단순한 계산기가 아닙니다. 법령을 읽고, 유권해석을 참조하고, 근거를 제시하면서 판단합니다.

---

## 핵심 철학

세금 판단의 오류는 납세자에게 실제 피해가 됩니다.  
그렇기 때문에 이 시스템은 두 가지 원칙을 동시에 지킵니다.

### 완전 자동화
법령 수집 → 임베딩 → 검색 → 추론 → 출력까지 전 과정이 에이전트 파이프라인으로 자동화됩니다.  
법령이 개정되면 자동 감지 → 재인덱스 → 시스템 전체 반영.  
사람이 개입하는 지점은 예외 처리와 최종 승인에 한정됩니다.

### 인간 즉각 개입 가능
모든 판단의 근거(fact_json, 검색 조문, 인용 chunk_id, debate 기록)가 항상 노출됩니다.  
세무사·전문가가 어느 단계에서든 판단 과정을 확인하고 즉시 개입할 수 있습니다.  
블랙박스 판단은 허용하지 않습니다.

---

## 지금 이 시스템이 하는 것

```
[사건 사실관계 입력]
     ↓
[L1.5] 확인서 체크 — 세대구성·취득일·특수관계 등 미확인 시 차단
     ↓
[L2]  팩트체크 — 판단에 필요한 결정적 정보 누락 검출
     ↓
[L3]  쿼리 보강 — 세법 특화 검색 키워드 생성
     ↓
[L4]  법령·유권해석 멀티소스 검색 + LLM 추론
     │  ┌─────────────────────────────────────┐
     │  │ Pinecone 5개 네임스페이스            │
     │  │  · tax-law          (법령 조문)      │
     │  │  · tax-ruling-nts   (국세청 질의회신) │
     │  │  · tax-ruling-decisions (심판원)     │
     │  │  · tax-ruling-moef  (기재부 해석)    │
     │  │  · tax-ruling-nts-interp (법령해석)  │
     │  └─────────────────────────────────────┘
     │  BGE Reranker (세법 도메인 파인튜닝) 적용
     ↓
[L5]  출력 검증 — phantom citation 검출, confidence 계산
     ↓
[판단 결과]  verdict + 근거 조문 + debate 기록 + 감사 추적
```

**판단 유형:** 비과세 / 고가주택 / 일반과세 / 단기세율 / 중과 / 감면 / 사실관계부족

---

## 달성 현황

| 단계 | 내용 | 상태 |
|------|------|------|
| Phase 1 | 법령 수집 파이프라인 (law.go.kr DRF) | ✅ |
| Phase 2 | Pinecone 임베딩 + Solar 4096차원 | ✅ |
| Phase 3 | L2~L5 판단 파이프라인 | ✅ |
| Phase 4 | 유권해석 5개 네임스페이스 통합 | ✅ |
| Phase 5 | BGE Reranker 세법 파인튜닝 (acc 0.9545) | ✅ |
| Phase 6 | 확인서(L1.5) + 책임소재 관리 | ✅ |
| 진행 중 | 유권해석 본문 수집 (37,400건 + 2,305건) | 🔄 |
| 예정 | BGE 재파인튜닝 (본문 데이터 기반) | ⏳ |
| 예정 | 조정대상지역 자동조회 API | ⏳ |

> 85개 커밋, 5일 연속 활성 개발 (2026-05-21 ~ 현재)

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| LLM | Claude Sonnet 4.6 / Opus 4.7 |
| 임베딩 | Upstage Solar `solar-embedding-1-large-passage` (dim=4096) |
| 벡터 DB | Pinecone Serverless (5 namespace) |
| Reranker | BGE `bge-reranker-v2-m3` (세법 파인튜닝, CrossEncoder) |
| 파이프라인 | Python / FastAPI / Streamlit |
| MCP | FastMCP (Claude Desktop 연동, 7개 도구) |
| 법령 소스 | law.go.kr DRF API / taxlaw.nts.go.kr |

---

## 핵심 설계 계약 (변경 불가)

| 원칙 | 구현 |
|------|------|
| 근거 없는 답변 금지 | 검색된 chunk_id가 있는 조문만 인용 |
| 수치 리터럴 코드 삽입 금지 | 세율·기간·금액 → `TaxConstantsRegistry` 전용 |
| BGE Reranker 생략 금지 | 최종 조문 선택 전 반드시 reranking |
| 판단 전 확인서 차단 | L1.5 미확인 항목 있으면 답변 출력 불가 |
| 전 과정 감사 추적 | verdict + chunk_id + debate 기록 항상 보존 |

---

## 빠른 시작

```bash
git clone https://github.com/Raw-Agent/korean-tax-rag.git
cd korean-tax-rag
pip install -r requirements.txt
cp .env.example .env   # API 키 입력

streamlit run src/ui.py          # UI  → http://localhost:8501
uvicorn src.api.chat_api:app     # API → http://localhost:8000
python src/api/mcp_server.py     # MCP (Claude Desktop용)
```

---

## 디렉터리 구조

```
src/
├── api/
│   ├── chat_api.py        # FastAPI — 외부 연동 REST
│   └── mcp_server.py      # FastMCP — Claude Desktop 7개 도구
├── domain/
│   ├── pipeline.py        # L1.5 ~ L5 메인 파이프라인
│   ├── confirmation.py    # 확인서 체크 (L1.5)
│   ├── tax_calculator.py  # 세액 계산
│   └── constants.py       # TaxConstantsRegistry
├── retrieval/
│   └── retriever_impl.py  # 멀티 네임스페이스 + BGE reranking
├── ingestion/             # 법령·유권해석 수집기
├── eval/                  # RVRL debate, golden set 관리
├── agents/prompts.py      # 프롬프트 버전 관리
├── pages/
│   ├── admin.py           # 어드민 — 수집 현황·파이프라인 상태
│   └── labeling.py        # 전문가 레이블링 UI
└── ui.py                  # Streamlit 메인

data/
├── golden/                # 골든셋 (142건 종합 케이스)
├── tax_tables/            # 세율표 JSON (TaxConstantsRegistry 소스)
└── models/                # BGE 파인튜닝 모델 (별도 관리)

scripts/
├── collect_and_embed_rulings.py  # 증분 수집 + 임베딩 스케줄러
├── finetune_reranker.py          # BGE 파인튜닝
├── run_baseline_eval.py          # 골든셋 eval 실행
└── detect_law_changes.py         # 법령 개정 자동 감지
```

---

## 개발 기여

- 코드 기여 전 [CLAUDE.md](CLAUDE.md) 필독 (설계 계약 명시)
- 업무 요청서 및 태스크 번들: [DEVELOPERS.md](DEVELOPERS.md)
- 세부 아키텍처·법령 도메인 규칙: [AGENTS.md](AGENTS.md)

커밋 메시지: 한국어, `feat/fix/docs/refactor/test/chore: 요약`

---

## 법률 고지

본 시스템은 정보 제공 목적으로 개발되었으며 법률 자문이 아닙니다.  
양도소득세 신고·납부에 관한 최종 판단은 반드시 공인 세무사와 상담하시기 바랍니다.
