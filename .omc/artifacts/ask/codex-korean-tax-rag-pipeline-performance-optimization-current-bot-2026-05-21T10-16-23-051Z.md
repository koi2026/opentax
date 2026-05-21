# codex advisor artifact

- Provider: codex
- Exit code: 0
- Created at: 2026-05-21T10:16:23.053Z

## Original task

Korean tax RAG pipeline performance optimization - current bottlenecks: BGE Reranker (BAAI/bge-reranker-v2-m3) takes 22.8s on CPU for 20 candidates, Claude Sonnet 4.6 API takes ~80s for a single call with 5 law article chunks (800 chars each) + 1500 max_tokens. Total pipeline: 90-110s. Stack: Python, Streamlit, Pinecone, Upstage Solar embedding, sentence_transformers CrossEncoder. What further optimizations are possible? Focus on: 1) Reranker CPU inference speedup without GPU, 2) Claude API latency reduction (prompt caching, streaming, model routing), 3) Pipeline parallelism (can embedding+rerank overlap?), 4) Caching strategies (query cache, reranker result cache). Provide concrete code-level recommendations.

## Final prompt

Korean tax RAG pipeline performance optimization - current bottlenecks: BGE Reranker (BAAI/bge-reranker-v2-m3) takes 22.8s on CPU for 20 candidates, Claude Sonnet 4.6 API takes ~80s for a single call with 5 law article chunks (800 chars each) + 1500 max_tokens. Total pipeline: 90-110s. Stack: Python, Streamlit, Pinecone, Upstage Solar embedding, sentence_transformers CrossEncoder. What further optimizations are possible? Focus on: 1) Reranker CPU inference speedup without GPU, 2) Claude API latency reduction (prompt caching, streaming, model routing), 3) Pipeline parallelism (can embedding+rerank overlap?), 4) Caching strategies (query cache, reranker result cache). Provide concrete code-level recommendations.

## Raw output

```text
핵심은 두 가지입니다. 지금 병목은 “모델 자체가 느리다”보다 “불필요하게 큰 입력을 느린 경로에 태운다”에 더 가깝습니다. 특히 현재 파이프라인에서는 `L3`에서 만든 `enriched_query`를 retrieval에 쓰지 않고 있어서, 검색 품질이 낮아지고 reranker/LLM 둘 다 더 무거워집니다. 이건 [src/domain/pipeline.py](</c:/Users/user/cording2025/tax-rag/src/domain/pipeline.py>) 와 [src/retrieval/retriever_impl.py](</c:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py>) 조합에서 바로 보입니다.

우선순위는 아래 순서가 맞습니다.

**1. Reranker CPU 속도**
가장 효과 큰 건 `20개 전부를 bge-reranker-v2-m3`에 태우지 않는 겁니다.

- `dense/hybrid top_k=20` 유지, `rerank_pool_k=6~10`으로 축소
- 축소 기준은 Pinecone score + article-number exact hit + entity_scope hit + 부칙 연결 여부 같은 결정론 신호
- 최종 선택은 여전히 BGE 이후로 유지하므로 AGENTS 규칙도 안 깨집니다

예시:
```python
# src/retrieval/retriever_impl.py
def _cheap_prefilter(matches: list[dict], query_text: str, limit: int = 8) -> list[dict]:
    article_boost = 0.15 if "제" in query_text or "§" in query_text else 0.0

    def score(m: dict) -> float:
        base = float(m.get("score", 0.0))
        meta = m.get("metadata", {})
        text = meta.get("full_text", "")
        bonus = 0.0
        if meta.get("article_number") and meta["article_number"] in query_text:
            bonus += article_boost
        if meta.get("entity_scopes"):
            bonus += 0.05
        if meta.get("linked_buchik_ids"):
            bonus += 0.03
        return base + bonus

    return sorted(matches, key=score, reverse=True)[:limit]
```

그 다음 [src/infra/reranker.py](</c:/Users/user/cording2025/tax-rag/src/infra/reranker.py>)에서 바로 할 일:

- `max_length`를 512 기본값에서 `192` 또는 `256`으로 낮추기
- `batch_size` 명시
- ONNX Runtime CPU backend 사용
- 가능하면 INT8 dynamic quantization

예시:
```python
from sentence_transformers import CrossEncoder

_reranker = CrossEncoder(
    BGE_RERANKER_MODEL,
    max_length=256,
    backend="onnx",   # onnxruntime 설치 필요
)
```

```python
scores = reranker.predict(
    pairs,
    batch_size=8,
    show_progress_bar=False,
    convert_to_numpy=True,
)
```

추가로:
- `_MAX_TEXT_CHARS=600`도 여전히 길 수 있습니다. 법령은 앞부분 집중도가 높아서 `350~450 chars`로 먼저 실험할 가치가 큽니다.
- article 본문 전체 대신 “제목 + 조문번호 + 첫 문단 + 키워드 매칭 문장 1~2개”만 reranker에 넣는 압축 뷰를 따로 만들면 CPU 시간이 더 줄어듭니다.
- 프로세스 시작 시 1회 워밍업 호출을 넣으세요.
- `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `torch.set_num_threads()`도 고정해서 흔들림을 줄이세요.

정리하면 CPU에서 기대되는 순서는:
1. rerank 후보 축소
2. `max_length` 축소
3. ONNX/INT8
4. 입력 텍스트 압축

**2. Claude API 지연**
80초는 거의 항상 “입력 + 출력이 너무 김”입니다. [src/retrieval/llm_fn.py](</c:/Users/user/cording2025/tax-rag/src/retrieval/llm_fn.py>) 기준으로 줄일 지점이 명확합니다.

바로 바꿀 것:
- `1500 max_tokens`를 `500~700`으로 낮추기
- `5 chunks x 800 chars`를 그대로 보내지 말고 `3~4 chunks` + chunk당 `250~450 chars`로 줄이기
- few-shot은 fast path에서는 끄고, low-confidence일 때만 2차 호출로 승격
- `Anthropic()` 매 호출 생성 대신 singleton 또는 `AsyncAnthropic` 사용
- streaming으로 TTFT 개선
- prompt caching 적용

캐싱 구조는 system/instructions와 고정 출력 스키마를 캐시 prefix로 두는 게 맞습니다. 공식 문서:
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Streaming: https://platform.claude.com/docs/en/build-with-claude/streaming
- Latency guidance: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency
- Models overview: https://platform.claude.com/docs/en/about-claude/models/overview

예시:
```python
from anthropic import AsyncAnthropic

_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": RAG_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": JSON_SCHEMA_INSTRUCTION,
        "cache_control": {"type": "ephemeral"},
    },
]
```

```python
message = await _client.messages.create(
    model=CLAUDE_MODEL,
    max_tokens=600,
    system=SYSTEM_BLOCKS,
    messages=[{"role": "user", "content": user_prompt}],
)
```

중요한 점:
- 캐시는 “완전히 동일한 prefix”여야 먹습니다
- `few_shot_block`이 요청마다 바뀌면 캐시 효율이 깨집니다
- 따라서 `few-shot`은 캐시 prefix에 두지 말고, 필요 시 별도 2차 호출로 분리하는 게 낫습니다

모델 라우팅도 바로 가능:
- 기본: `claude-haiku-4-5`
- `danger_flags >= 2`, `missing_facts`, `고가주택`, `이월과세`, `상속`, `특례 충돌`일 때만 `claude-sonnet-4-6`
- debate 단계만 Opus 또는 Sonnet 유지

예시:
```python
def choose_model(query, fact_check, chunks) -> str:
    if fact_check.danger_flags >= 2:
        return "claude-sonnet-4-6"
    if len(chunks) <= 3 and not fact_check.missing_fact_texts():
        return "claude-haiku-4-5"
    return "claude-sonnet-4-6"
```

**3. 병렬화**
`embedding -> Pinecone -> rerank`는 strict dependency라 직접 겹칠 수 없습니다. embedding과 rerank를 겹치는 건 불가합니다.

겹칠 수 있는 건 이쪽입니다:
- query enrichment와 sparse BM25 생성
- Pinecone 조회 후 부칙 `fetch`는 batch fetch로 병렬/일괄화
- LLM 호출 전 `few_shot_block` 생성, citation map 준비, output-validator용 retrieved-id set 구성
- Streamlit 응답은 streaming으로 먼저 보여주고, L5 검증/후처리는 뒤에서 수행

지금 `retrieve_with_buchik()`는 linked 부칙을 개별 `fetch`하고 있어서 왕복이 많습니다. 이건 일괄 fetch로 줄이세요.

```python
# src/retrieval/retriever_impl.py
all_buchik_ids = list({
    bid
    for chunk in results
    for bid in chunk.metadata.linked_buchik_ids
    if bid not in seen_ids
})
res = index.fetch(ids=all_buchik_ids, namespace=self.namespace)
```

그리고 큰 구조상 더 중요한 병렬화는 “1차 fast answer / 2차 refine”입니다.
- 1차: top 3 chunks, no few-shot, Haiku or Sonnet short output
- 2차: low-confidence일 때만 Sonnet full + debate
이렇게 해야 체감 시간이 확 줄어듭니다.

**4. 캐시**
캐시는 네 군데가 유효합니다.

- query embedding cache
- Pinecone result cache
- reranker result cache
- final answer cache

추천 키:
```python
cache_key = sha256(json.dumps({
    "query_text": normalized_query_text,
    "anchor_date": as_of_int,
    "entity_scope": query.entity_scope.value,
    "namespace": self.namespace,
    "top_k": top_k,
    "hybrid_alpha": hybrid_alpha,
}, sort_keys=True).encode()).hexdigest()
```

reranker 캐시는 더 좁게:
```python
rerank_key = sha256(json.dumps({
    "query": normalized_query_text,
    "candidate_ids": [m["id"] for m in prefiltered_matches],
    "candidate_versions": [
        m["metadata"].get("effective_date") for m in prefiltered_matches
    ],
    "model": BGE_RERANKER_MODEL,
    "max_length": 256,
}, sort_keys=True).encode()).hexdigest()
```

실무 팁:
- 메모리 `lru_cache` + 디스크 `diskcache` 또는 Redis 2단계
- TTL은 법령 검색은 길게, 세션 answer cache는 짧게
- query normalization은 필수
- 날짜/주택수/특례 flag가 다르면 캐시 분리

예시:
```python
from diskcache import Cache
cache = Cache(".cache/rag")

def cached_rerank(key: str, fn):
    val = cache.get(key)
    if val is not None:
        return val
    val = fn()
    cache.set(key, val, expire=3600)
    return val
```

**지금 코드에서 먼저 손댈 5개**
1. `enriched_query`를 retrieval에도 반영
2. rerank 대상 20 -> 8
3. CrossEncoder `max_length=256`, `backend="onnx"`
4. Claude `max_tokens=1500 -> 600`, chunks `5x800 -> 3~4x350`
5. prompt cache + fast/slow model routing

이 5개만 해도 90~110초를 대체로 절반 이하로 내릴 가능성이 큽니다. 원하면 다음 턴에 바로 `retriever_impl.py`, `reranker.py`, `llm_fn.py` 기준으로 실제 패치까지 해드리겠습니다.


OpenAI Codex v0.123.0 (research preview)
--------
workdir: c:\Users\user\cording2025\tax-rag
model: gpt-5.4
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 019e4a07-66f0-7153-a8d6-cfcf9790e985
--------
user
Korean tax RAG pipeline performance optimization - current bottlenecks: BGE Reranker (BAAI/bge-reranker-v2-m3) takes 22.8s on CPU for 20 candidates, Claude Sonnet 4.6 API takes ~80s for a single call with 5 law article chunks (800 chars each) + 1500 max_tokens. Total pipeline: 90-110s. Stack: Python, Streamlit, Pinecone, Upstage Solar embedding, sentence_transformers CrossEncoder. What further optimizations are possible? Focus on: 1) Reranker CPU inference speedup without GPU, 2) Claude API latency reduction (prompt caching, streaming, model routing), 3) Pipeline parallelism (can embedding+rerank overlap?), 4) Caching strategies (query cache, reranker result cache). Provide concrete code-level recommendations.
codex
요청한 범위에 맞춰 현재 파이프라인의 병목 지점을 코드 기준으로 확인한 뒤, 바로 적용 가능한 최적화안을 정리하겠습니다. 우선 `pipeline`, `retriever_impl`, `llm_fn`, 캐시 유무를 확인해서 일반론이 아니라 이 저장소 구조에 맞는 권고로 좁히겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'rg -n "reranker|CrossEncoder|Claude|anthropic|cache|stream|prompt cache|embedding|Pinecone|top_k|rerank" src tests' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'Get-ChildItem -Recurse src | Select-Object FullName' in c:\Users\user\cording2025\tax-rag
 succeeded in 4001ms:
tests\test_e2e_golden.py:9:외부 서비스(Pinecone, Claude API) 의존 테스트는 pytest -m integration으로만 실행.
tests\test_e2e_golden.py:311:    전체 파이프라인 E2E 검증 — Pinecone + Claude API 필요.
tests\test_e2e_golden.py:320:    from src.retrieval.retriever_impl import PineconeTaxLawRetriever
tests\test_e2e_golden.py:332:        retriever=PineconeTaxLawRetriever(),
src\agents\crew.py:18:    """CrewAI용 LLM 객체 반환 (Claude)"""
src\agents\crew.py:21:        model=f"anthropic/{CLAUDE_MODEL}",
tests\test_pipeline_cases.py:9:E2E 테스트(Pinecone+Claude)는 pytest -m integration으로 별도 실행.
src\embed.py:2:임베딩 생성 및 Pinecone 업로드
src\embed.py:3:data/processed/all_chunks.json → Pinecone Serverless
src\embed.py:12:from pinecone import Pinecone, ServerlessSpec
src\embed.py:19:UPSTAGE_EMBEDDING_MODEL = os.getenv("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large-passage")
src\embed.py:28:MAX_EMBED_CHARS = 2000  # solar-embedding-1-large 최대 4000토큰 → 한국어 약 2000자 이내
src\embed.py:37:def get_embedding_client() -> tuple[OpenAI, str]:
src\embed.py:46:        print("임베딩: OpenAI text-embedding-3-large (fallback)")
src\embed.py:47:        return OpenAI(api_key=OPENAI_API_KEY), "text-embedding-3-large"
src\embed.py:53:    resp = client.embeddings.create(model=model, input=truncated)
src\embed.py:54:    return [d.embedding for d in resp.data]
src\embed.py:57:def get_or_create_index(pc: Pinecone, dimension: int) -> None:
src\embed.py:60:        print(f"Pinecone 인덱스 생성 중: {PINECONE_INDEX_NAME} (dim={dimension})")
src\embed.py:84:    client, model = get_embedding_client()
src\embed.py:91:    pc = Pinecone(api_key=pinecone_api_key)
src\embed.py:96:    for i in tqdm(range(0, len(chunks), BATCH_SIZE), desc="Pinecone 업로드"):
src\embed.py:99:        embeddings = embed_texts(client, model, texts)
src\embed.py:116:            for c, emb in zip(batch, embeddings)
src\agents\tools.py:13:        "한국 양도소득세 관련 법령 조문을 벡터 검색 + BGE reranking으로 검색합니다. "
src\agents\tools.py:14:        "query: 검색할 법령 키워드나 질문, top_k: 검색 후보 수(기본 20), "
src\agents\tools.py:15:        "rerank_top_n: reranking 후 반환 수(기본 5)"
src\agents\tools.py:17:    top_k: int = Field(default=20)
src\agents\tools.py:18:    rerank_top_n: int = Field(default=5)
src\agents\tools.py:21:        chunks = retrieve_tax_law(query, top_k=self.top_k, rerank_top_n=self.rerank_top_n)
src\agents\tools.py:29:                f"    chunk_id: {chunk.id} | rerank_score: {chunk.score:.4f}\n"
src\domain\chunk_metadata.py:80:    수집 시 정규식으로 추출 → Pinecone 메타데이터에 저장 → retriever에서 하드필터 활용.
tests\test_rag.py:8:# Pinecone/임베딩 없이 단위 테스트 가능하도록 모킹
tests\test_rag.py:99:@patch("src.rag._get_reranker")
tests\test_rag.py:100:def test_retrieve_returns_law_chunks(mock_reranker, mock_embed, mock_index):
tests\test_rag.py:107:    # Pinecone 결과 모킹
tests\test_rag.py:121:    mock_reranker_instance = MagicMock()
tests\test_rag.py:122:    mock_reranker_instance.predict.return_value = [0.95]
tests\test_rag.py:123:    mock_reranker.return_value = mock_reranker_instance
tests\test_rag.py:125:    chunks = retrieve_tax_law("1세대 1주택 비과세 요건", top_k=5, rerank_top_n=1)
tests\test_rag.py:135:@patch("src.rag._get_reranker")
tests\test_rag.py:136:def test_retrieve_returns_chunk_ids_not_just_text(mock_reranker, mock_embed, mock_index):
tests\test_rag.py:150:    mock_reranker_instance = MagicMock()
tests\test_rag.py:151:    mock_reranker_instance.predict.return_value = [0.8]
tests\test_rag.py:152:    mock_reranker.return_value = mock_reranker_instance
tests\test_rag.py:154:    chunks = retrieve_tax_law("비과세", top_k=5, rerank_top_n=1)
tests\test_rag.py:203:@patch("src.rag._get_reranker")
tests\test_rag.py:204:def test_reranker_is_called_before_final_selection(mock_reranker, mock_embed, mock_index):
tests\test_rag.py:205:    """BGE reranker가 반드시 호출됨 (최종 선택 전)"""
tests\test_rag.py:218:    mock_reranker_instance = MagicMock()
tests\test_rag.py:219:    mock_reranker_instance.predict.return_value = [0.9, 0.8, 0.7, 0.6, 0.5]
tests\test_rag.py:220:    mock_reranker.return_value = mock_reranker_instance
tests\test_rag.py:222:    retrieve_tax_law("테스트", top_k=5, rerank_top_n=3)
tests\test_rag.py:224:    mock_reranker_instance.predict.assert_called_once()
src\ui.py:11:# streamlit run src/ui.py 실행 시 프로젝트 루트를 sys.path에 추가
src\ui.py:14:import streamlit as st
src\rag.py:6:- Pinecone: src.infra.pinecone_client.{get_pinecone_index, query_pinecone}
src\rag.py:7:- Reranker: src.infra.reranker.{get_reranker, rerank}
src\rag.py:21:import anthropic
src\rag.py:28:from src.infra import reranker as _reranker_mod
src\rag.py:62:# `src.rag._get_reranker` 를 patch 한다. shim 도 같은 이름을 노출해야 한다.
src\rag.py:72:def _get_reranker():
src\rag.py:73:    return _reranker_mod.get_reranker()
src\rag.py:80:    top_k: int = 20,
src\rag.py:81:    rerank_top_n: int = 5,
src\rag.py:85:    법령 벡터 검색 + BGE reranking → 상위 rerank_top_n 개 반환.
src\rag.py:91:    # 2. Pinecone 날짜 필터
src\rag.py:102:    # 3. Pinecone 벡터 검색 (테스트 호환: index.query 를 직접 호출)
src\rag.py:106:        top_k=top_k,
src\rag.py:125:    reranker = _get_reranker()
src\rag.py:127:    rerank_scores = reranker.predict(pairs)
src\rag.py:130:        zip(rerank_scores, matches),
src\rag.py:133:    )[:rerank_top_n]
src\rag.py:166:    """검색 → reranking → LLM 추론 → TaxAnswer. enable_trace=True 면 trace 기록."""
src\rag.py:201:            f"(chunk_id: {chunk.id}, rerank_score: {chunk.score:.4f})\n"
src\rag.py:206:    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
src\rag.py:254:                rerank_scores=[c.score for c in chunks],
src\rag.py:283:    from src.retrieval.retriever_impl import PineconeTaxLawRetriever
src\rag.py:287:    retriever = PineconeTaxLawRetriever()
src\rag.py:314:    chunks = retrieve_tax_law(query, top_k=20, rerank_top_n=5)
src\rag.py:315:    print(f"검색 결과 (reranking 후 상위 {len(chunks)}개):")
src\rag.py:318:        print(f"     chunk_id: {c.id} | rerank_score: {c.score:.4f}")
src\pages\area_map.py:19:import streamlit as st
src\pages\area_map.py:57:@st.cache_data
src\eval\debate.py:30:import anthropic
src\eval\debate.py:105:    """동기 Claude 호출 → JSON 파싱. 파싱 실패 시 raw 반환."""
src\eval\debate.py:106:    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
src\eval\debate.py:135:            chunks = retrieve_tax_law(article_hint, top_k=10, rerank_top_n=3)
src\eval\debate.py:232:                chunks = retrieve_tax_law(article_hint, top_k=10, rerank_top_n=3)
src\eval\eval.py:27:    top_k: int = 20,
src\eval\eval.py:28:    rerank_top_n: int = 5,
src\eval\eval.py:54:        chunks = retrieve_tax_law(enriched_question, top_k=top_k, rerank_top_n=rerank_top_n, as_of_date=as_of_date)
src\eval\eval.py:59:        ret_metrics = compute_retrieval_metrics(retrieved_ids, gold_chunks, k=rerank_top_n)
src\eval\eval.py:97:            f"recall@{rerank_top_n}={ret_metrics.get('recall_at_k', 'N/A')!s:.4} "
src\infra\embedder.py:33:            _embed_model = "solar-embedding-1-large-query"
src\infra\embedder.py:36:            _embed_model = "text-embedding-3-large"
src\infra\embedder.py:45:    resp = client.embeddings.create(model=model, input=[query[:2000]])
src\infra\embedder.py:46:    return resp.data[0].embedding
src\infra\embedder.py:56:    """BM25 sparse vector for Pinecone hybrid search.
src\infra\embedder.py:59:    and returns Pinecone-compatible sparse_values.
src\eval\feedback.py:26:    rerank_scores: list[float],
src\eval\feedback.py:50:        "rerank_scores": rerank_scores,
src\eval\feedback.py:108:    top_k = retrieved_ids[:k]
src\eval\feedback.py:111:    hits = [1 if rid in gold_set else 0 for rid in top_k]
src\infra\pinecone_client.py:2:Pinecone Serverless 클라이언트 — 인덱스 싱글톤 + 검색 헬퍼.
src\infra\pinecone_client.py:10:from pinecone import Pinecone
src\infra\pinecone_client.py:22:    """Pinecone 인덱스 싱글톤."""
src\infra\pinecone_client.py:27:        pc = Pinecone(api_key=PINECONE_API_KEY)
src\infra\pinecone_client.py:34:    top_k: int = 20,
src\infra\pinecone_client.py:48:        top_k=top_k,
src\infra\reranker.py:10:from sentence_transformers import CrossEncoder
src\infra\reranker.py:14:BGE_RERANKER_MODEL = os.getenv("BGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
src\infra\reranker.py:16:_reranker: Optional[CrossEncoder] = None
src\infra\reranker.py:19:def get_reranker() -> CrossEncoder:
src\infra\reranker.py:20:    """BGE reranker 싱글톤."""
src\infra\reranker.py:21:    global _reranker
src\infra\reranker.py:22:    if _reranker is None:
src\infra\reranker.py:24:        _reranker = CrossEncoder(BGE_RERANKER_MODEL)
src\infra\reranker.py:26:    return _reranker
src\infra\reranker.py:29:_MAX_TEXT_CHARS = 600  # CrossEncoder 내부에서 512토큰으로 잘리므로 미리 제한해 tokenizer 부하 감소
src\infra\reranker.py:32:def rerank(
src\infra\reranker.py:39:    candidates: Pinecone matches (id, metadata) — metadata.full_text 사용.
src\infra\reranker.py:43:    reranker = get_reranker()
src\infra\reranker.py:45:    scores = reranker.predict(pairs, show_progress_bar=False)
src\ingestion\admin_notices.py:104:    JSON 파일로 직렬화해 Pinecone과 별도로 관리.
src\ingestion\collect.py:180:# Pinecone vector ID ASCII 전용 — 법령명 → 짧은 코드 매핑
src\ingestion\collect.py:201:    Pinecone ASCII 전용 chunk ID: {mst}_{law_code}_{art_code}_{eff}
src\ingestion\collect.py:372:            # effective_date=0, expiration_date=99991231 → Pinecone 날짜 필터에서 항상 통과
src\infra\__init__.py:1:"""외부 서비스 클라이언트 — 임베딩, Pinecone, Reranker."""
src\ingestion\embed.py:2:임베딩 + Pinecone 업로드 스크립트
src\ingestion\embed.py:3:data/processed/all_chunks.json → Pinecone Serverless
src\ingestion\embed.py:13:from pinecone import Pinecone, ServerlessSpec
src\ingestion\embed.py:25:UPSTAGE_EMBEDDING_MODEL = os.getenv("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large-passage")
src\ingestion\embed.py:28:BATCH_SIZE = 100  # Pinecone upsert 배치 크기
src\ingestion\embed.py:92:        return client, "text-embedding-3-large", 3072
src\ingestion\embed.py:99:    resp = client.embeddings.create(model=model, input=truncated)
src\ingestion\embed.py:100:    return [item.embedding for item in resp.data]
src\ingestion\embed.py:103:def _get_or_create_index(pc: Pinecone, dimension: int):
src\ingestion\embed.py:104:    """Pinecone 인덱스 조회 또는 생성"""
src\ingestion\embed.py:126:    JSON 청크 파일을 읽어 임베딩 후 Pinecone에 업로드.
src\ingestion\embed.py:148:    # Pinecone 인덱스
src\ingestion\embed.py:149:    pc = Pinecone(api_key=PINECONE_API_KEY)
src\ingestion\embed.py:156:    for batch in tqdm(batches, desc="Pinecone 업로드"):
src\ingestion\embed.py:175:                # Pinecone $lte/$gte는 숫자 타입 전용 — YYYYMMDD 정수로 저장
src\ingestion\embed.py:189:                # Pinecone 벡터당 메타데이터 한도 40KB — 4000자까지 저장 (reranker + LLM 모두 이 필드 사용)
src\ingestion\embed.py:206:    청크 리스트를 직접 받아 임베딩 후 Pinecone에 업로드.
src\ingestion\embed.py:216:    pc = Pinecone(api_key=PINECONE_API_KEY)
src\eval\verdict_matcher.py:5:RLVR 루프에서 BGE reranker 파인튜닝 신호로 사용.
src\ingestion\embed_rulings.py:2:유권해석 DB 임베딩 + Pinecone 업로드 파이프라인.
src\ingestion\embed_rulings.py:3:data/rulings/{ntis,tt,court}/*.json → Pinecone tax-ruling-{ntis,tt,court} 네임스페이스.
src\ingestion\embed_rulings.py:19:from pinecone import Pinecone
src\ingestion\embed_rulings.py:59:    """유권해석 레코드를 Pinecone 업로드용 청크로 변환."""
src\ingestion\embed_rulings.py:131:    data/rulings/{source}/*.json 읽기 → 청킹 → 임베딩 → Pinecone 업로드.
src\ingestion\embed_rulings.py:150:    pc = Pinecone(api_key=PINECONE_API_KEY)
src\eval\retrieval_analyzer.py:52:    """Pinecone에서 chunk_id → full_text 맵 반환. 실패 시 빈 dict."""
src\eval\retrieval_analyzer.py:177:    # Pinecone에서 누락 chunk 텍스트 fetch
src\retrieval\llm_fn.py:4:anthropic SDK 는 sync 이므로 asyncio executor 로 래핑한다.
src\retrieval\llm_fn.py:14:import anthropic
src\retrieval\llm_fn.py:36:    """검색 결과 + 누락 힌트 → Claude user prompt."""
src\retrieval\llm_fn.py:104:    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
src\domain\query_input.py:767:    top_k: int = 10
src\domain\retriever.py:5:Stage 2: VectorRanker — 임베딩 유사도 + reranker로 최종 선택.
src\domain\retriever.py:37:    """Stage 2 — 벡터 검색 + reranker."""
src\api\mcp_server.py:3:FastMCP 기반: stdio(Claude Desktop) + SSE(HTTP 클라이언트) 양쪽 지원
src\api\mcp_server.py:29:    top_k: int = 20,
src\api\mcp_server.py:30:    rerank_top_n: int = 5,
src\api\mcp_server.py:34:    한국 양도소득세 관련 법령 조문을 벡터 검색 + BGE reranking으로 검색합니다.
src\api\mcp_server.py:38:        top_k: 벡터 검색 후보 수 (기본 20)
src\api\mcp_server.py:39:        rerank_top_n: BGE reranking 후 반환할 조문 수 (기본 5)
src\api\mcp_server.py:44:        enriched_query, top_k=top_k, rerank_top_n=rerank_top_n,
src\api\mcp_server.py:54:            f"    chunk_id: {chunk.id} | rerank_score: {chunk.score:.4f}\n"
src\api\mcp_server.py:72:    chunks = retrieve_tax_law(query, top_k=20, rerank_top_n=10)
src\api\mcp_server.py:97:    양도소득세 비과세·감면·중과 여부를 RAG 검색 후 Claude로 분석합니다.
src\api\mcp_server.py:130:    chunks = retrieve_tax_law(question, top_k=20, rerank_top_n=10)
src\api\mcp_server.py:256:    top_k: int = 5,
src\api\mcp_server.py:268:        top_k: 반환할 최대 결과 수 (기본 5)
src\api\mcp_server.py:274:    # Pinecone 네임스페이스 매핑
src\api\mcp_server.py:294:    # Pinecone 클라이언트 초기화 및 네임스페이스별 검색
src\api\mcp_server.py:320:                top_k=top_k,
src\api\mcp_server.py:357:    # 점수 내림차순 정렬 후 top_k 제한
src\api\mcp_server.py:359:    results = results[:top_k]
src\api\mcp_server.py:378:    # 인자 없으면 stdio (Claude Desktop), --sse 이면 HTTP SSE
src\api\chat_api.py:92:        from src.retrieval.retriever_impl import PineconeTaxLawRetriever
src\api\chat_api.py:98:        retriever = PineconeTaxLawRetriever()
src\retrieval\retriever_impl.py:2:PineconeTaxLawRetriever — TaxLawRetriever ABC 의 Pinecone 구현.
src\retrieval\retriever_impl.py:4:Pinecone 메타데이터 ↔ LawChunkMetadata 매핑을 담당한다.
src\retrieval\retriever_impl.py:28:from src.infra.reranker import rerank
src\retrieval\retriever_impl.py:66:    """Select the most appropriate date anchor for Pinecone version filtering.
src\retrieval\retriever_impl.py:107:    """Pinecone match.metadata → LawChunkMetadata 로 변환."""
src\retrieval\retriever_impl.py:114:    # linked_buchik_ids: Pinecone는 list 메타데이터를 그대로 반환
src\retrieval\retriever_impl.py:147:class PineconeTaxLawRetriever(TaxLawRetriever):
src\retrieval\retriever_impl.py:148:    """Pinecone + BGE Reranker 기반 TaxLawRetriever 구현."""
src\retrieval\retriever_impl.py:152:        top_k: int = TOP_K,
src\retrieval\retriever_impl.py:153:        rerank_top_n: int = RERANK_TOP_N,
src\retrieval\retriever_impl.py:156:        self.top_k = top_k
src\retrieval\retriever_impl.py:157:        self.rerank_top_n = rerank_top_n
src\retrieval\retriever_impl.py:164:        # query.top_k 우선, 없으면 인스턴스 기본값
src\retrieval\retriever_impl.py:165:        top_k = getattr(query, "top_k", None) or self.top_k
src\retrieval\retriever_impl.py:177:        # Stage 1 — Symbolic Filter: 앵커 날짜 기준 날짜 범위 (Pinecone 숫자 필터)
src\retrieval\retriever_impl.py:190:            top_k=top_k,
src\retrieval\retriever_impl.py:201:                top_k=top_k,
src\retrieval\retriever_impl.py:210:        # Stage 1 보강 — entity_scope 후필터 (Pinecone entity_scopes 메타데이터 기반)
src\retrieval\retriever_impl.py:222:        ranked = rerank(query_text, matches, self.rerank_top_n)
src\retrieval\retriever_impl.py:293:            # 시행일 기준 부칙 — Pinecone 날짜 필터가 이미 처리, 항상 통과
src\pages\admin.py:14:import streamlit as st
src\pages\admin.py:340:        top_k = st.slider("top_k (후보 수)", 5, 50, 20)
src\pages\admin.py:342:        rerank_top_n = st.slider("rerank_top_n (LLM 전달 수)", 1, 10, 5)
src\pages\admin.py:348:                chunks = retrieve_tax_law(debug_query, top_k=top_k, rerank_top_n=rerank_top_n)

 succeeded in 4036ms:

FullName                                                                                     
--------                                                                                     
C:\Users\user\cording2025\tax-rag\src\agents                                                 
C:\Users\user\cording2025\tax-rag\src\api                                                    
C:\Users\user\cording2025\tax-rag\src\calculator                                             
C:\Users\user\cording2025\tax-rag\src\domain                                                 
C:\Users\user\cording2025\tax-rag\src\eval                                                   
C:\Users\user\cording2025\tax-rag\src\infra                                                  
C:\Users\user\cording2025\tax-rag\src\ingestion                                              
C:\Users\user\cording2025\tax-rag\src\pages                                                  
C:\Users\user\cording2025\tax-rag\src\retrieval                                              
C:\Users\user\cording2025\tax-rag\src\services                                               
C:\Users\user\cording2025\tax-rag\src\__pycache__                                            
C:\Users\user\cording2025\tax-rag\src\embed.py                                               
C:\Users\user\cording2025\tax-rag\src\rag.py                                                 
C:\Users\user\cording2025\tax-rag\src\ui.py                                                  
C:\Users\user\cording2025\tax-rag\src\__init__.py                                            
C:\Users\user\cording2025\tax-rag\src\agents\__pycache__                                     
C:\Users\user\cording2025\tax-rag\src\agents\crew.py                                         
C:\Users\user\cording2025\tax-rag\src\agents\prompts.py                                      
C:\Users\user\cording2025\tax-rag\src\agents\roles.py                                        
C:\Users\user\cording2025\tax-rag\src\agents\tools.py                                        
C:\Users\user\cording2025\tax-rag\src\agents\__init__.py                                     
C:\Users\user\cording2025\tax-rag\src\agents\__pycache__\prompts.cpython-313.pyc             
C:\Users\user\cording2025\tax-rag\src\agents\__pycache__\__init__.cpython-313.pyc            
C:\Users\user\cording2025\tax-rag\src\api\__pycache__                                        
C:\Users\user\cording2025\tax-rag\src\api\chat_api.py                                        
C:\Users\user\cording2025\tax-rag\src\api\fact_input.py                                      
C:\Users\user\cording2025\tax-rag\src\api\mcp_server.py                                      
C:\Users\user\cording2025\tax-rag\src\api\sample_cases.py                                    
C:\Users\user\cording2025\tax-rag\src\api\schema.py                                          
C:\Users\user\cording2025\tax-rag\src\api\__init__.py                                        
C:\Users\user\cording2025\tax-rag\src\api\__pycache__\chat_api.cpython-313.pyc               
C:\Users\user\cording2025\tax-rag\src\api\__pycache__\fact_input.cpython-313.pyc             
C:\Users\user\cording2025\tax-rag\src\api\__pycache__\mcp_server.cpython-313.pyc             
C:\Users\user\cording2025\tax-rag\src\api\__pycache__\sample_cases.cpython-313.pyc           
C:\Users\user\cording2025\tax-rag\src\api\__pycache__\schema.cpython-313.pyc                 
C:\Users\user\cording2025\tax-rag\src\api\__pycache__\__init__.cpython-313.pyc               
C:\Users\user\cording2025\tax-rag\src\calculator\__pycache__                                 
C:\Users\user\cording2025\tax-rag\src\calculator\tax_calculator.py                           
C:\Users\user\cording2025\tax-rag\src\calculator\__init__.py                                 
C:\Users\user\cording2025\tax-rag\src\calculator\__pycache__\tax_calculator.cpython-313.pyc  
C:\Users\user\cording2025\tax-rag\src\calculator\__pycache__\__init__.cpython-313.pyc        
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__                                     
C:\Users\user\cording2025\tax-rag\src\domain\acquisition_timeline.py                         
C:\Users\user\cording2025\tax-rag\src\domain\chunk_metadata.py                               
C:\Users\user\cording2025\tax-rag\src\domain\confirmation.py                                 
C:\Users\user\cording2025\tax-rag\src\domain\date_resolver.py                                
C:\Users\user\cording2025\tax-rag\src\domain\fact_checker.py                                 
C:\Users\user\cording2025\tax-rag\src\domain\output_validator.py                             
C:\Users\user\cording2025\tax-rag\src\domain\pipeline.py                                     
C:\Users\user\cording2025\tax-rag\src\domain\query_enrichment.py                             
C:\Users\user\cording2025\tax-rag\src\domain\query_input.py                                  
C:\Users\user\cording2025\tax-rag\src\domain\retriever.py                                    
C:\Users\user\cording2025\tax-rag\src\domain\special_case_finder.py                          
C:\Users\user\cording2025\tax-rag\src\domain\tax_answer.py                                   
C:\Users\user\cording2025\tax-rag\src\domain\tax_constants.py                                
C:\Users\user\cording2025\tax-rag\src\domain\__init__.py                                     
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\acquisition_timeline.cpython-313.pyc
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\chunk_metadata.cpython-313.pyc      
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\confirmation.cpython-313.pyc        
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\date_resolver.cpython-313.pyc       
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\fact_checker.cpython-313.pyc        
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\output_validator.cpython-313.pyc    
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\pipeline.cpython-313.pyc            
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\query_enrichment.cpython-313.pyc    
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\query_input.cpython-313.pyc         
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\retriever.cpython-313.pyc           
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\tax_answer.cpython-313.pyc          
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\tax_constants.cpython-313.pyc       
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\__init__.cpython-313.pyc            
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__                                       
C:\Users\user\cording2025\tax-rag\src\eval\case_generator.py                                 
C:\Users\user\cording2025\tax-rag\src\eval\debate.py                                         
C:\Users\user\cording2025\tax-rag\src\eval\eval.py                                           
C:\Users\user\cording2025\tax-rag\src\eval\feedback.py                                       
C:\Users\user\cording2025\tax-rag\src\eval\golden_injector.py                                
C:\Users\user\cording2025\tax-rag\src\eval\retrieval_analyzer.py                             
C:\Users\user\cording2025\tax-rag\src\eval\verdict_matcher.py                                
C:\Users\user\cording2025\tax-rag\src\eval\__init__.py                                       
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\debate.cpython-313.pyc                
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\eval.cpython-313.pyc                  
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\feedback.cpython-313.pyc              
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\golden_injector.cpython-313.pyc       
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\retrieval_analyzer.cpython-313.pyc    
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\__init__.cpython-313.pyc              
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__                                      
C:\Users\user\cording2025\tax-rag\src\infra\article_tag_map.json                             
C:\Users\user\cording2025\tax-rag\src\infra\embedder.py                                      
C:\Users\user\cording2025\tax-rag\src\infra\pinecone_client.py                               
C:\Users\user\cording2025\tax-rag\src\infra\reranker.py                                      
C:\Users\user\cording2025\tax-rag\src\infra\__init__.py                                      
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\embedder.cpython-313.pyc             
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\pinecone_client.cpython-313.pyc      
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\reranker.cpython-313.pyc             
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\__init__.cpython-313.pyc             
C:\Users\user\cording2025\tax-rag\src\ingestion\__pycache__                                  
C:\Users\user\cording2025\tax-rag\src\ingestion\admin_notices.py                             
C:\Users\user\cording2025\tax-rag\src\ingestion\collect.py                                   
C:\Users\user\cording2025\tax-rag\src\ingestion\embed.py                                     
C:\Users\user\cording2025\tax-rag\src\ingestion\embed_rulings.py                             
C:\Users\user\cording2025\tax-rag\src\ingestion\__init__.py                                  
C:\Users\user\cording2025\tax-rag\src\ingestion\__pycache__\collect.cpython-313.pyc          
C:\Users\user\cording2025\tax-rag\src\ingestion\__pycache__\embed.cpython-313.pyc            
C:\Users\user\cording2025\tax-rag\src\ingestion\__pycache__\embed_rulings.cpython-313.pyc    
C:\Users\user\cording2025\tax-rag\src\ingestion\__pycache__\__init__.cpython-313.pyc         
C:\Users\user\cording2025\tax-rag\src\pages\admin.py                                         
C:\Users\user\cording2025\tax-rag\src\pages\area_map.py                                      
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__                                  
C:\Users\user\cording2025\tax-rag\src\retrieval\llm_fn.py                                    
C:\Users\user\cording2025\tax-rag\src\retrieval\retriever_impl.py                            
C:\Users\user\cording2025\tax-rag\src\retrieval\__init__.py                                  
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__\llm_fn.cpython-313.pyc           
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__\retriever_impl.cpython-313.pyc   
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__\__init__.cpython-313.pyc         
C:\Users\user\cording2025\tax-rag\src\services\__pycache__                                   
C:\Users\user\cording2025\tax-rag\src\services\residence_interview.py                        
C:\Users\user\cording2025\tax-rag\src\services\simulation_engine.py                          
C:\Users\user\cording2025\tax-rag\src\services\tier_router.py                                
C:\Users\user\cording2025\tax-rag\src\services\__init__.py                                   
C:\Users\user\cording2025\tax-rag\src\services\__pycache__\simulation_engine.cpython-313.pyc 
C:\Users\user\cording2025\tax-rag\src\services\__pycache__\__init__.cpython-313.pyc          
C:\Users\user\cording2025\tax-rag\src\__pycache__\collect.cpython-313.pyc                    
C:\Users\user\cording2025\tax-rag\src\__pycache__\embed.cpython-313.pyc                      
C:\Users\user\cording2025\tax-rag\src\__pycache__\feedback.cpython-313.pyc                   
C:\Users\user\cording2025\tax-rag\src\__pycache__\rag.cpython-313.pyc                        
C:\Users\user\cording2025\tax-rag\src\__pycache__\schema.cpython-313.pyc                     
C:\Users\user\cording2025\tax-rag\src\__pycache__\__init__.cpython-313.pyc                   



codex
현재 코드상 reranker는 `CrossEncoder.predict()` 직호출, LLM은 sync Anthropic SDK를 executor로 감싼 형태입니다. 다음으로 실제 호출 경로와 입력 크기, 병렬화 가능 지점을 확인하고, Claude 쪽은 공식 문서 기준으로 캐싱/스트리밍 옵션을 검증하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\infra\\reranker.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\retrieval\\llm_fn.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\retrieval\\retriever_impl.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\pipeline.py" in c:\Users\user\cording2025\tax-rag
 succeeded in 3941ms:
"""
BGE Cross-Encoder Reranker ??理쒖쥌 議곕Ц ?좏깮 吏곸쟾 ?몄텧.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from sentence_transformers import CrossEncoder

load_dotenv()

BGE_RERANKER_MODEL = os.getenv("BGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

_reranker: Optional[CrossEncoder] = None


def get_reranker() -> CrossEncoder:
    """BGE reranker ?깃???"""
    global _reranker
    if _reranker is None:
        print(f"BGE Reranker 濡쒕뱶 以? {BGE_RERANKER_MODEL}")
        _reranker = CrossEncoder(BGE_RERANKER_MODEL)
        print("Reranker 以鍮??꾨즺")
    return _reranker


_MAX_TEXT_CHARS = 600  # CrossEncoder ?대??먯꽌 512?좏겙?쇰줈 ?섎━誘濡?誘몃━ ?쒗븳??tokenizer 遺??媛먯냼


def rerank(
    query: str,
    candidates: list[dict],
    top_n: int = 5,
) -> list[tuple[float, dict]]:
    """
    BGE Cross-Encoder濡?(query, candidate.full_text) ?먯닔 怨꾩궛 ???곸쐞 N媛?諛섑솚.
    candidates: Pinecone matches (id, metadata) ??metadata.full_text ?ъ슜.
    """
    if not candidates:
        return []
    reranker = get_reranker()
    pairs = [(query, c["metadata"].get("full_text", "")[:_MAX_TEXT_CHARS]) for c in candidates]
    scores = reranker.predict(pairs, show_progress_bar=False)
    ranked = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True,
    )[:top_n]
    return list(ranked)

 succeeded in 3976ms:
"""
?낆뒪?몃┝ llm_fn 怨꾩빟 援ы쁽 ??RetrievedChunk + missing_hints ??TaxAnswer.

anthropic SDK ??sync ?대?濡?asyncio executor 濡??섑븨?쒕떎.
?꾨＼?꾪듃??src/agents/prompts.py ??踰꾩쟾 愿由?(RAG_SYSTEM_PROMPT ?ъ궗??.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import List, Optional

import anthropic
from dotenv import load_dotenv

from src.agents.prompts import RAG_SYSTEM_PROMPT
from src.domain.retriever import RetrievedChunk
from src.domain.tax_answer import Citation, TaxAnswer

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


_MAX_CHUNK_CHARS = 800  # 議곕Ц ?먮Ц 理쒕? ?꾨떖 湲몄씠 (?좏겙 ?덉빟 ???듭떖 ?댁슜? ?욌?遺꾩뿉 吏묒쨷)


def _build_user_prompt(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    few_shot_block: str = "",
) -> str:
    """寃??寃곌낵 + ?꾨씫 ?뚰듃 ??Claude user prompt."""
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        m = chunk.metadata
        marker = " [遺移?" if chunk.included_as_linked_buchik else ""
        context_parts.append(
            f"[{i}]{marker} {m.law_name} ??m.article_number}議?n"
            f"(chunk_id: {m.chunk_id}, score: {chunk.score:.4f})\n"
            f"{chunk.content[:_MAX_CHUNK_CHARS]}"
        )
    context = "\n\n".join(context_parts)

    hints_text = ""
    if missing_hints:
        hints_text = "\n\n[異붽? ?뺤씤 ?꾩슂 ??ぉ ?????뺣낫媛 ?놁뼱 ?먮떒??遺덊솗?ㅼ꽦???덉뒿?덈떎]\n"
        hints_text += "\n".join(f"- {h}" for h in missing_hints)

    few_shot_section = f"\n{few_shot_block}\n" if few_shot_block else ""

    return f"""?ㅼ쓬 踰뺣졊 議곕Ц??洹쇨굅濡??먮떒?섏떗?쒖삤.

[寃?됰맂 踰뺣졊 議곕Ц]
{context}
{hints_text}{few_shot_section}
[吏덈Ц]
{enriched_query}

諛섎뱶???꾨옒 JSON ?뺤떇?쇰줈 ?듬??섏떗?쒖삤:
{{
  "answer": "?곸꽭 ?먮떒 (踰뺣졊 洹쇨굅 ?ы븿)",
  "verdict": "鍮꾧낵?? | "怨쇱꽭" | "議곌굔遺鍮꾧낵?? | "needs_verification",
  "confidence": 0.0 ~ 1.0,
  "citations": [
    {{"chunk_id": "...", "article": "?뚮뱷?몃쾿 ?쒗뻾????54議?????, "excerpt": "愿??議곕Ц 諛쒖톸", "law_version": "?쒗뻾??}}
  ],
  "missing_facts": ["異붽? ?뺤씤 ?꾩슂 ??ぉ"],
  "warnings": ["二쇱쓽?ы빆"]
}}"""


async def llm_fn(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict] = None,
) -> TaxAnswer:
    """
    ?낆뒪?몃┝ ?쒓렇?덉쿂 ??寃?됰맂 泥?겕? ?꾨씫 ?뚰듃濡?TaxAnswer ?앹꽦.
    ANTHROPIC_API_KEY 誘몄꽕????needs_verification ?쇰줈 ?덉쟾 諛섑솚.
    """
    if not ANTHROPIC_API_KEY:
        return TaxAnswer(
            answer="[ANTHROPIC_API_KEY 誘몄꽕??",
            verdict="needs_verification",
            confidence=0.0,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            warnings=["LLM 誘몄꽕??],
        )

    # 怨⑤뱺??few-shot 二쇱엯 (5嫄??댁긽 ?볦씤 寃쎌슦?먮쭔)
    few_shot_block = ""
    if fact_json:
        try:
            from src.eval.golden_injector import build_few_shot_block
            few_shot_block = build_few_shot_block(fact_json)
        except Exception:
            pass

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_prompt = _build_user_prompt(enriched_query, chunks, missing_hints, few_shot_block)

    loop = asyncio.get_event_loop()
    message = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=RAG_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        ),
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return TaxAnswer(
            answer=raw,
            verdict="needs_verification",
            confidence=0.3,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            warnings=["JSON ?뚯떛 ?ㅽ뙣 ???먮Ц 諛섑솚"],
        )

    citations = [
        Citation(
            chunk_id=c.get("chunk_id", ""),
            article=c.get("article", ""),
            excerpt=c.get("excerpt", ""),
            law_version=c.get("law_version", ""),
        )
        for c in data.get("citations", [])
    ]

    return TaxAnswer(
        answer=data.get("answer", ""),
        verdict=data.get("verdict", "needs_verification"),
        confidence=float(data.get("confidence", 0.0)),
        citations=citations,
        chunk_ids=[c.metadata.chunk_id for c in chunks],
        missing_facts=data.get("missing_facts", []),
        warnings=data.get("warnings", []),
    )

 succeeded in 3992ms:
"""
PineconeTaxLawRetriever ??TaxLawRetriever ABC ??Pinecone 援ы쁽.

Pinecone 硫뷀??곗씠????LawChunkMetadata 留ㅽ븨???대떦?쒕떎.
?꾩옱 誘몄닔吏??꾨뱶(linked_buchik_ids, entity_scopes ?????⑸━??湲곕낯媛??ъ슜.
"""
from __future__ import annotations

import os
from datetime import date
from typing import List, Optional

from dotenv import load_dotenv

from src.domain.chunk_metadata import (
    AmendmentType,
    AppendixType,
    ApplicabilityRuleType,
    ApplicabilitySpec,
    LawChunkMetadata,
    LawId,
    LawLevel,
)
from src.domain.query_input import RAGQueryInput
from src.domain.retriever import RetrievedChunk, TaxLawRetriever
from src.infra.embedder import bm25_sparse_vector, embed_query
from src.infra.pinecone_client import get_pinecone_index, query_pinecone
from src.infra.reranker import rerank

load_dotenv()

PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")
TOP_K = int(os.getenv("RETRIEVER_TOP_K", "20"))
RERANK_TOP_N = int(os.getenv("RETRIEVER_RERANK_TOP_N", "5"))

# None = dense-only; float string = hybrid (0.0 pure sparse, 1.0 pure dense, 0.75 typical)
_HYBRID_ALPHA_RAW = os.getenv("PINECONE_HYBRID_ALPHA")

# 踰뺣졊紐???LawId 留ㅽ븨
_LAW_NAME_TO_ID = {
    "?뚮뱷?몃쾿": LawId.INCOME_TAX_ACT,
    "?뚮뱷?몃쾿 ?쒗뻾??: LawId.INCOME_TAX_DECREE,
    "?뚮뱷?몃쾿 ?쒗뻾洹쒖튃": LawId.INCOME_TAX_RULE,
    "議곗꽭?밸??쒗븳踰?: LawId.SPECIAL_TAX_ACT,
    "議곗꽭?밸??쒗븳踰??쒗뻾??: LawId.SPECIAL_TAX_DECREE,
    "議곗꽭?밸??쒗븳踰??쒗뻾洹쒖튃": LawId.SPECIAL_TAX_RULE,
    "吏諛⑹꽭踰?: LawId.LOCAL_TAX_ACT,
    "吏諛⑹꽭踰??쒗뻾??: LawId.LOCAL_TAX_DECREE,
    "吏諛⑹꽭踰??쒗뻾洹쒖튃": LawId.LOCAL_TAX_RULE,
    "援?꽭湲곕낯踰?: LawId.FRAMEWORK_TAX_ACT,
    "援?꽭湲곕낯踰??쒗뻾??: LawId.FRAMEWORK_TAX_DECREE,
    "援?꽭湲곕낯踰??쒗뻾洹쒖튃": LawId.FRAMEWORK_TAX_RULE,
    "?곸냽??諛?利앹뿬?몃쾿": LawId.INHERITANCE_TAX_ACT,
    "?곸냽??諛?利앹뿬?몃쾿 ?쒗뻾??: LawId.INHERITANCE_TAX_DECREE,
}

_LAW_CATEGORY_TO_LEVEL = {
    "踰뺣쪧": LawLevel.ACT,
    "??듬졊??: LawLevel.ENFORCEMENT_DECREE,
    "遺??: LawLevel.ENFORCEMENT_RULE,
    "?쒗뻾洹쒖튃": LawLevel.ENFORCEMENT_RULE,
}


def _select_anchor_date(query: RAGQueryInput) -> date:
    """Select the most appropriate date anchor for Pinecone version filtering.

    Special cases use a different date than the default transfer_date:
    - ?댁썡怨쇱꽭: 利앹뿬??(law version when the gift occurred)
    - ?곸냽二쇳깮: ?곸냽媛쒖떆??(law version when death occurred)
    - 議고빀?먯엯二쇨텒: 愿由ъ쿂遺꾧퀎?띿씤媛??(law version when reconstruction was approved)
    - Default: ?묐룄??    """
    sc = query.fact_vector.special_cases

    # ?댁썡怨쇱꽭: 利앹뿬??湲곗? 踰뺣졊 踰꾩쟾
    rt = sc.rollover_taxation if sc else None
    if rt and rt.is_gift_from_spouse_or_lineal and rt.gift_date:
        return rt.gift_date

    # ?곸냽二쇳깮: ?곸냽媛쒖떆??湲곗?
    inh = sc.inheritance if sc else None
    if inh and inh.death_date:
        return inh.death_date

    # 議고빀?먯엯二쇨텒: 愿由ъ쿂遺꾩씤媛??湲곗?
    rc = sc.reconstruction if sc else None
    if rc and rc.management_disposal_date:
        return rc.management_disposal_date

    # 湲곕낯: ?묐룄??    return query.date_bundle.transfer_date


def _int_to_date(val: int) -> date:
    """YYYYMMDD ?뺤닔 ??date. ?뺤떇 ?ㅻ쪟硫?2000-01-01 ?덉쟾 fallback."""
    s = str(int(val))
    if len(s) != 8:
        return date(2000, 1, 1)
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return date(2000, 1, 1)


def _pinecone_meta_to_chunk_metadata(match_id: str, meta: dict) -> LawChunkMetadata:
    """Pinecone match.metadata ??LawChunkMetadata 濡?蹂??"""
    eff_int = int(float(meta.get("effective_date", 0) or 0))
    exp_int = int(float(meta.get("expiration_date", 99991231) or 99991231))
    law_name = meta.get("law_name", "")
    article_type = meta.get("article_type", "")
    appendix = AppendixType.BUCHIK if article_type == "遺移? else AppendixType.MAIN_BODY

    # linked_buchik_ids: Pinecone??list 硫뷀??곗씠?곕? 洹몃?濡?諛섑솚
    raw_buchik = meta.get("linked_buchik_ids", [])
    buchik_ids: list[str] = list(raw_buchik) if isinstance(raw_buchik, list) else []

    # applicability_anchor ??ApplicabilitySpec.anchors 留ㅽ븨
    # ?섏쭛 ??_extract_buchik_anchor()濡?異붿텧????"transfer_date" ??瑜?洹몃?濡?蹂댁〈
    anchor_key = meta.get("applicability_anchor", "effective_date") or "effective_date"
    applicability = ApplicabilitySpec(
        rule_type=ApplicabilityRuleType.NONE,
        anchors=[anchor_key],
    )

    return LawChunkMetadata(
        chunk_id=match_id,
        law_id=_LAW_NAME_TO_ID.get(law_name, LawId.INCOME_TAX_ACT),
        law_name=law_name,
        law_level=_LAW_CATEGORY_TO_LEVEL.get(meta.get("law_category", ""), LawLevel.ACT),
        article_number=meta.get("article_number", ""),
        paragraph=None,
        item=None,
        lsi_seq=str(meta.get("version_mst", "")),
        promulgation_date=_int_to_date(eff_int) if eff_int else date(2000, 1, 1),
        effective_from=_int_to_date(eff_int) if eff_int else date(2000, 1, 1),
        effective_to=None if exp_int == 99991231 else _int_to_date(exp_int),
        amendment_type=AmendmentType.PARTIAL,
        article_lineage_root=meta.get("article_number", ""),
        appendix_type=appendix,
        applicability=applicability,
        tax_types=["transfer"],
        linked_buchik_ids=buchik_ids,
    )


class PineconeTaxLawRetriever(TaxLawRetriever):
    """Pinecone + BGE Reranker 湲곕컲 TaxLawRetriever 援ы쁽."""

    def __init__(
        self,
        top_k: int = TOP_K,
        rerank_top_n: int = RERANK_TOP_N,
        namespace: str = PINECONE_NAMESPACE,
    ):
        self.top_k = top_k
        self.rerank_top_n = rerank_top_n
        self.namespace = namespace

    def retrieve(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        query_text = query.fact_vector.to_text()
        vector = embed_query(query_text)

        # query.top_k ?곗꽑, ?놁쑝硫??몄뒪?댁뒪 湲곕낯媛?        top_k = getattr(query, "top_k", None) or self.top_k

        # Hybrid search: BM25 sparse vector for article-number exact-match precision
        sparse_vec: Optional[dict] = None
        hybrid_alpha: Optional[float] = None
        if _HYBRID_ALPHA_RAW is not None:
            try:
                hybrid_alpha = float(_HYBRID_ALPHA_RAW)
                sparse_vec = bm25_sparse_vector(query_text)
            except ValueError:
                pass  # Malformed env var ??fall back to dense-only

        # Stage 1 ??Symbolic Filter: ?듭빱 ?좎쭨 湲곗? ?좎쭨 踰붿쐞 (Pinecone ?レ옄 ?꾪꽣)
        # ?댁썡怨쇱꽭?믪쬆?ъ씪, ?곸냽?믪긽?띻컻?쒖씪, ?낆＜沅뚢넂愿由ъ쿂遺꾩씤媛?? 湲곕낯?믪뼇?꾩씪
        anchor_date = _select_anchor_date(query)
        as_of_int = int(anchor_date.strftime("%Y%m%d"))
        pinecone_filter = {
            "$and": [
                {"effective_date": {"$lte": as_of_int}},
                {"expiration_date": {"$gte": as_of_int}},
            ]
        }

        matches = query_pinecone(
            vector=vector,
            top_k=top_k,
            namespace=self.namespace,
            filter_dict=pinecone_filter,
            sparse_vector=sparse_vec,
            alpha=hybrid_alpha,
        )

        # ?좎쭨 ?꾪꽣 寃곌낵 ?놁쑝硫??꾪꽣 ?놁씠 ?ш???(踰뺣졊 踰꾩쟾 ?대젰 誘몄닔吏??곹깭 ???
        if not matches:
            matches = query_pinecone(
                vector=vector,
                top_k=top_k,
                namespace=self.namespace,
                sparse_vector=sparse_vec,
                alpha=hybrid_alpha,
            )

        if not matches:
            return []

        # Stage 1 蹂닿컯 ??entity_scope ?꾪븘??(Pinecone entity_scopes 硫뷀??곗씠??湲곕컲)
        # EntityScope.value = "二쇳깮"/"遺꾩뼇沅? ????embed.py??_tag_chunk()? ?숈씪??媛??ъ슜
        scope_val = query.entity_scope.value
        if scope_val:
            filtered = [
                m for m in matches
                if not m.get("metadata", {}).get("entity_scopes")  # ?쒓렇 ?놁쑝硫??듦낵
                or scope_val in m["metadata"]["entity_scopes"]
            ]
            matches = filtered if filtered else matches  # ?꾪꽣 寃곌낵 鍮꾨㈃ ?꾩껜 ?좎?

        # Stage 2 ??Vector Rerank
        ranked = rerank(query_text, matches, self.rerank_top_n)

        results: List[RetrievedChunk] = []
        for score, match in ranked:
            meta = match["metadata"]
            chunk_meta = _pinecone_meta_to_chunk_metadata(match["id"], meta)
            results.append(
                RetrievedChunk(
                    metadata=chunk_meta,
                    content=meta.get("full_text", ""),
                    score=float(score),
                )
            )
        return results

    def _get_chunk_by_id(self, chunk_id: str) -> Optional[LawChunkMetadata]:
        index = get_pinecone_index()
        res = index.fetch(ids=[chunk_id], namespace=self.namespace)
        vectors = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        if chunk_id not in vectors:
            return None
        vec = vectors[chunk_id]
        meta = vec.get("metadata", {}) if isinstance(vec, dict) else getattr(vec, "metadata", {})
        return _pinecone_meta_to_chunk_metadata(chunk_id, meta or {})

    def _get_content(self, chunk_id: str) -> str:
        index = get_pinecone_index()
        res = index.fetch(ids=[chunk_id], namespace=self.namespace)
        vectors = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        if chunk_id not in vectors:
            return ""
        vec = vectors[chunk_id]
        meta = vec.get("metadata", {}) if isinstance(vec, dict) else getattr(vec, "metadata", {})
        return (meta or {}).get("full_text", "")

    def _get_anchor_date(self, query: RAGQueryInput, anchor_key: str) -> Optional[date]:
        """遺移??듭빱 ????荑쇰━???대떦 ?좎쭨.

        DateBundle.get_anchor()濡?而ㅻ쾭?섏? ?딅뒗 gift_date/death_date??        FactVector.special_cases?먯꽌 吏곸젒 議고쉶?쒕떎.
        """
        d = query.date_bundle.get_anchor(anchor_key)
        if d is not None:
            return d

        sc = getattr(query.fact_vector, "special_cases", None)
        if sc is None:
            return None

        if anchor_key == "gift_date":
            rt = getattr(sc, "rollover_taxation", None)
            return getattr(rt, "gift_date", None) if rt else None

        if anchor_key == "death_date":
            inh = getattr(sc, "inheritance", None)
            return getattr(inh, "death_date", None) if inh else None

        return None

    def _is_buchik_applicable(self, chunk: RetrievedChunk, query: RAGQueryInput) -> bool:
        """遺移?泥?겕媛 荑쇰━ ?좎쭨 湲곗??쇰줈 ?곸슜 媛?ν븳吏 ?먮떒.

        ?듭빱 ?좎쭨 < 遺移??쒗뻾??????媛쒖젙??遺移숈? ?꾩쭅 ?곸슜 ????False(?쒖쇅).
        ?듭빱 ?좎쭨瑜??????놁쑝硫??덉쟾?섍쾶 True(?ы븿).
        """
        anchors = chunk.metadata.applicability.anchors
        if not anchors:
            return True

        anchor_key = anchors[0]
        if anchor_key == "effective_date":
            # ?쒗뻾??湲곗? 遺移???Pinecone ?좎쭨 ?꾪꽣媛 ?대? 泥섎━, ??긽 ?듦낵
            return True

        anchor_date = self._get_anchor_date(query, anchor_key)
        if anchor_date is None:
            # ?좎쭨 ?뺣낫 ?놁쓬 ???꾪꽣 遺덇? ???덉쟾?섍쾶 ?ы븿
            return True

        effective_from = chunk.metadata.effective_from
        # ?듭빱 ?좎쭨媛 ??遺移숈쓽 ?쒗뻾???댄썑?ъ빞 ?곸슜 ???        return anchor_date >= effective_from

    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        """蹂몄튃 寃????linked_buchik_ids濡?遺移?蹂닿컯, applicability_anchor ?섎뱶?꾪꽣 ?곸슜.

        遺移??곸슜濡 ??
          "??踰??쒗뻾 ???묐룄遺꾨????곸슜" ??anchor=transfer_date
          "痍⑤뱷遺꾨????곸슜" ??anchor=acquisition_date
        ?듭빱 ?좎쭨 < 遺移??쒗뻾?쇱씠硫??대떦 遺移숈? ???ш굔??誘몄쟻?????쒖쇅.
        """
        results = self.retrieve(query)
        if not query.include_buchik:
            return results

        seen_ids = {r.metadata.chunk_id for r in results}
        extra: List[RetrievedChunk] = []
        for chunk in results:
            for buchik_id in chunk.metadata.linked_buchik_ids:
                if buchik_id in seen_ids:
                    continue
                buchik_meta = self._get_chunk_by_id(buchik_id)
                if buchik_meta is None:
                    continue
                buchik_chunk = RetrievedChunk(
                    metadata=buchik_meta,
                    content=self._get_content(buchik_id),
                    score=chunk.score,
                    included_as_linked_buchik=True,
                )
                # ?듭빱 ?좎쭨 湲곗? 遺移??곸슜 媛???щ? 寃??                if not self._is_buchik_applicable(buchik_chunk, query):
                    continue
                extra.append(buchik_chunk)
                seen_ids.add(buchik_id)

        return results + extra

 succeeded in 4014ms:
"""
RAG ?뚯씠?꾨씪??吏꾩엯????L1~L5 ?듯빀

?ъ슜踰?
    result = await run_rag_pipeline(
        query=RAGQueryInput.from_fact_ledger(...),
        retriever=retriever,
        llm_fn=call_llm,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Set

from .confirmation import ConfirmationResult, check_confirmation
from .fact_checker import FactCheckResult, check_facts
from .output_validator import validate_output
from .query_enrichment import build_rag_query
from .query_input import RAGQueryInput
from .retriever import RetrievedChunk, TaxLawRetriever
from .tax_answer import TaxAnswer, Citation


@dataclass
class PipelineResult:
    answer: TaxAnswer
    fact_check: FactCheckResult
    enriched_query: str
    retrieved_chunks: List[RetrievedChunk] = field(default_factory=list)
    blocked_at_l2: bool = False
    blocked_at_confirmation: bool = False
    debate_record: Optional[dict] = None   # ?쇱웳???ㅽ뻾??寃쎌슦 寃곌낵 ?붿빟
    query_mode: str = "report"
    consulting_scenarios: Optional[List[dict]] = None


def _build_consulting_scenarios(
    query: RAGQueryInput,
    answer: TaxAnswer,
    fact_json: Optional[dict] = None,
) -> List[dict]:
    """
    而⑥꽕??紐⑤뱶: ?묐룄/利앹뿬/遺?대?利앹뿬 ?쒕굹由ъ삤 鍮꾧탳.
    SimulationEngine???듯빐 ?ㅼ젣 ?몄븸??怨꾩궛?섏뿬 諛섑솚?쒕떎.
    """
    from src.services.simulation_engine import run_simulation

    fv = query.fact_vector
    fact = fact_json or {}

    market_value = fv.transfer_price or 0
    acquisition_price = fv.acquisition_price or 0

    if market_value == 0 or acquisition_price == 0:
        return [{"error": "?쒓? ?먮뒗 痍⑤뱷媛??誘몄엯?????쒕??덉씠??遺덇?"}]

    sim = run_simulation(
        market_value=market_value,
        acquisition_price=acquisition_price,
        holding_years=fv.holding_period_years,
        residence_years=fv.residence_period_years,
        household_house_count=fv.household_house_count,
        verdict=answer.verdict,
        encumbrance=int(fact.get("simulation_encumbrance", 0) or 0),
        gift_recipient=str(fact.get("simulation_gift_recipient", "吏곴퀎議대퉬??)),
        recipient_is_adult=bool(fact.get("simulation_recipient_is_adult", True)),
        necessary_expenses=int(fact.get("necessary_expenses", 0) or 0),
        heavy_tax_suspended=bool(fact.get("heavy_tax_suspended", False)),
        is_non_resident=fv.overseas_residence_yn,
    )

    return sim.to_dict()["scenarios"] + [
        {
            "optimal_type": sim.optimal_type,
            "optimal_saving": sim.optimal_saving,
            "recommendation_reason": sim.recommendation_reason,
            "expert_review_needed": sim.expert_review_needed,
            "warnings": sim.warnings,
        }
    ]


async def run_rag_pipeline(
    query: RAGQueryInput,
    retriever: TaxLawRetriever,
    llm_fn: Callable[[str, List[RetrievedChunk], List[str]], Awaitable[TaxAnswer]],
    fact_json: Optional[dict] = None,
    enable_debate: bool = False,
    debate_auto_promote: bool = True,
    confirmed: Optional[Dict[str, bool]] = None,
    query_mode: Literal["report", "consulting"] = "report",
) -> PipelineResult:
    """
    L1: schema validation ??RAGQueryInput ?앹꽦 ???대? 泥섎━??
    L2: fact completeness check
    L3: query enrichment
    L4: RAG + LLM
    L5: output validation
    """

    # ?? L1.5: Confirmation Gate ??????????????????????????????????????????
    confirmation = check_confirmation(confirmed)
    if not confirmation.can_proceed:
        from .tax_answer import TaxVerdict
        blocked_answer = TaxAnswer(
            answer="?ㅼ쓬 ??ぉ??癒쇱? ?뺤씤??二쇱꽭??\n" + "\n".join(
                f"- {q}" for q in confirmation.unconfirmed_questions
            ),
            verdict=TaxVerdict.NEEDS_VERIFICATION,
            confidence=0.0,
            citations=[],
            chunk_ids=[],
            missing_facts=confirmation.unconfirmed_questions,
            warnings=["?뺤씤??誘몄셿猷????먮떒??吏꾪뻾?????놁뒿?덈떎."],
            expert_review_signals=[],
        )
        return PipelineResult(
            answer=blocked_answer,
            fact_check=FactCheckResult(can_proceed=True),
            enriched_query="",
            blocked_at_l2=False,
            blocked_at_confirmation=True,
        )

    # ?? L2: Fact Completeness ????????????????????????????????????????????
    fact_check = check_facts(query)

    if not fact_check.can_proceed:
        blocked_answer = TaxAnswer(
            answer="?먮떒???꾩슂???ъ떎愿怨꾧? 遺덉땐遺꾪빀?덈떎. ?꾨옒 ??ぉ??異붽?濡??뺤씤??二쇱꽭??",
            verdict="needs_verification",
            confidence=0.0,
            missing_facts=fact_check.missing_fact_texts(),
            warnings=[
                f"?щ━?곗뺄 ?뺣낫 {len(fact_check.critical_missing)}嫄??꾨씫?쇰줈 異붾줎 以묐떒"
            ],
        )
        return PipelineResult(
            answer=blocked_answer,
            fact_check=fact_check,
            enriched_query="",
            blocked_at_l2=True,
        )

    # ?? L3: Query Enrichment ?????????????????????????????????????????????
    enriched_query = build_rag_query(query, fact_check.danger_flags)

    # ?? L4: RAG + LLM ????????????????????????????????????????????????????
    chunks = retriever.retrieve_with_buchik(query)
    retrieved_ids: Set[str] = {c.metadata.chunk_id for c in chunks}

    # missing_facts瑜?LLM ?꾨＼?꾪듃???꾨떖 ??"???뺣낫媛 ?놁뼱??遺덊솗?ㅽ빀?덈떎" ?덈궡
    llm_missing_hints = fact_check.missing_fact_texts()

    raw_answer = await llm_fn(enriched_query, chunks, llm_missing_hints)

    # chunk_ids ?숆린????LLM???꾨씫?쒖섟?????덉쑝誘濡?寃??寃곌낵濡?蹂댁셿
    if not raw_answer.chunk_ids:
        raw_answer = raw_answer.with_update(chunk_ids=list(retrieved_ids))

    # missing_facts 蹂묓빀
    combined_missing = list(set(raw_answer.missing_facts + llm_missing_hints))
    raw_answer = raw_answer.with_update(missing_facts=combined_missing)

    # ?? L5: Output Validation ????????????????????????????????????????????
    validated = validate_output(raw_answer, retrieved_ids, danger_flags=fact_check.danger_flags)

    result = PipelineResult(
        answer=validated,
        fact_check=fact_check,
        enriched_query=enriched_query,
        retrieved_chunks=chunks,
        query_mode=query_mode,
    )

    # ?? Consulting Mode: ?쒕굹由ъ삤 鍮꾧탳 ?몃뱶 ??????????????????????????????
    if query_mode == "consulting":
        result.consulting_scenarios = _build_consulting_scenarios(query, validated, fact_json)

    # ?? ?좏깮??Red-Blue ?쇱웳 ?????????????????????????????????????????????
    if enable_debate and fact_json:
        try:
            from src.eval.debate import run_red_blue_debate, should_debate
            if should_debate(result):
                debate = await run_red_blue_debate(
                    fact_json=fact_json,
                    pipeline_result=result,
                    auto_promote=debate_auto_promote,
                )
                result.debate_record = {
                    "debate_id": debate.debate_id,
                    "outcome": debate.outcome,
                    "challenge_type": debate.red_challenge.get("challenge_type"),
                    "revised_verdict": debate.blue_defense.get("revised_verdict"),
                    "promoted_to_golden": debate.promoted_to_golden,
                }
                # Red媛 ?닿꼈?쇰㈃ ?뚯씠?꾨씪??理쒖쥌 verdict ?낅뜲?댄듃
                if debate.outcome == "red_won":
                    revised = debate.blue_defense.get("revised_verdict", validated.verdict)
                    result.answer = validated.with_update(
                        verdict=revised,
                        warnings=validated.warnings + [
                            f"[Red Team ?섏젙] {debate.red_challenge.get('challenge_type')}: "
                            f"{debate.blue_defense.get('defense_text', '')[:100]}"
                        ],
                    )
        except Exception as e:
            # ?쇱웳 ?ㅽ뙣媛 二??뚯씠?꾨씪?몄쓣 留됱쑝硫?????
            result.debate_record = {"error": str(e)}

    return result

web search: 
web search: Anthropic prompt caching documentation messages.create cache_control official
web search: 
web search: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
codex
공식 문서 기준으로는 Claude 쪽에서 `cache_control`을 붙인 prefix 캐시와 streaming-under-the-hood를 바로 활용할 수 있습니다. 이제 현재 Pinecone/embedding 경로를 봐서 어디까지 병렬화가 실제로 가능한지, 그리고 캐시 키를 어떻게 잡아야 안정적인지 정리하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\infra\\pinecone_client.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\infra\\embedder.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\api\\chat_api.py" in c:\Users\user\cording2025\tax-rag
 succeeded in 3502ms:
"""
Pinecone Serverless ?대씪?댁뼵?????몃뜳???깃???+ 寃???ы띁.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "tax-rag")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")

_pinecone_index = None


def get_pinecone_index():
    """Pinecone ?몃뜳???깃???"""
    global _pinecone_index
    if _pinecone_index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY媛 ?꾩슂?⑸땲??)
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def query_pinecone(
    vector: list[float],
    top_k: int = 20,
    namespace: str = PINECONE_NAMESPACE,
    filter_dict: Optional[dict] = None,
    sparse_vector: Optional[dict] = None,
    alpha: Optional[float] = None,
) -> list[dict]:
    """踰≫꽣 寃????matches 由ъ뒪??諛섑솚 (?놁쑝硫?鍮?由ъ뒪??.

    sparse_vector: {"indices": [...], "values": [...]} for BM25 hybrid search.
    alpha: 0.0 = pure sparse, 1.0 = pure dense, 0.75 = typical hybrid. None = dense only.
    """
    index = get_pinecone_index()
    kwargs: dict = dict(
        vector=vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )
    if filter_dict:
        kwargs["filter"] = filter_dict

    if sparse_vector is not None and alpha is not None:
        kwargs["vector"] = [v * alpha for v in vector]
        kwargs["sparse_vector"] = {
            "indices": sparse_vector["indices"],
            "values": [v * (1 - alpha) for v in sparse_vector["values"]],
        }

    result = index.query(**kwargs)
    return result.get("matches", []) or []

 succeeded in 3516ms:
"""
?꾨쿋???대씪?댁뼵????Upstage Solar (湲곕낯) / OpenAI (fallback).
?깃????대씪?댁뼵?몃줈 紐⑤뱢 ?섎챸 ?숈븞 ?ъ궗??
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_embed_client: Optional[OpenAI] = None
_embed_model: Optional[str] = None


def _get_embed_client() -> Tuple[OpenAI, str]:
    """?꾨쿋???대씪?댁뼵?몄? 紐⑤뜽紐?諛섑솚 ??Upstage ?곗꽑, ?놁쑝硫?OpenAI."""
    global _embed_client, _embed_model
    if _embed_client is None:
        if UPSTAGE_API_KEY:
            _embed_client = OpenAI(
                api_key=UPSTAGE_API_KEY,
                base_url="https://api.upstage.ai/v1",
            )
            _embed_model = "solar-embedding-1-large-query"
        elif OPENAI_API_KEY:
            _embed_client = OpenAI(api_key=OPENAI_API_KEY)
            _embed_model = "text-embedding-3-large"
        else:
            raise RuntimeError("UPSTAGE_API_KEY ?먮뒗 OPENAI_API_KEY媛 ?꾩슂?⑸땲??)
    return _embed_client, _embed_model


def embed_query(query: str) -> list[float]:
    """荑쇰━ ?띿뒪?몃? ?꾨쿋??踰≫꽣濡?蹂??(2000???쒗븳)."""
    client, model = _get_embed_client()
    resp = client.embeddings.create(model=model, input=[query[:2000]])
    return resp.data[0].embedding


def bm25_sparse_vector(
    text: str,
    vocab: Optional[dict[str, int]] = None,
    k1: float = 1.5,
    b: float = 0.75,
    avg_doc_len: float = 200.0,
) -> dict:
    """BM25 sparse vector for Pinecone hybrid search.

    Tokenizes Korean text plus article-number patterns (e.g. ??9議? 짠97)
    and returns Pinecone-compatible sparse_values.

    vocab: {token: index} mapping. If None, uses abs(hash(token)) % 65536.
    Returns {"indices": [...], "values": [...]}.
    """
    tokens = re.findall(r"??d+議곗쓽?\d*|짠\d+|[媛-??+|[a-zA-Z0-9]+", text)
    if not tokens:
        return {"indices": [], "values": []}

    tf = Counter(tokens)
    doc_len = len(tokens)

    indices: list[int] = []
    values: list[float] = []
    for token, freq in tf.items():
        idx = vocab.get(token, abs(hash(token)) % 65536) if vocab else abs(hash(token)) % 65536
        tf_score = (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * doc_len / avg_doc_len))
        indices.append(idx)
        values.append(float(tf_score))

    return {"indices": indices, "values": values}

 succeeded in 3547ms:
"""
梨꾪똿 紐⑤뱶 API ??FastAPI ?붾뱶?ъ씤??+ 吏곸젒 ?⑥닔 ?몄텧 ?묒そ 吏??

Streamlit UI????紐⑤뱢??chat_turn()??吏곸젒 ?꾪룷?명빐???ъ슜?쒕떎.
?몃? ?대씪?댁뼵?몃뒗 uvicorn?쇰줈 ?ㅽ뻾 ??POST /api/v1/chat ?쇰줈 ?몄텧?쒕떎.

?ㅽ뻾:
    uvicorn src.api.chat_api:app --host 0.0.0.0 --port 8001 --reload
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="?묐룄?뚮뱷??RAG 梨꾪똿 API",
    description="JSON ?ъ떎愿怨???L1-L5 ?뚯씠?꾨씪?????몄쑉 ?먮떒",
    version="1.0.0",
)


# ?? ?붿껌/?묐떟 ?ㅽ궎留??????????????????????????????????????????????????????????

class ChatRequest(BaseModel):
    """
    梨꾪똿 1???붿껌.

    fact_json???덉쑝硫??뚯씠?꾨씪?몄쑝濡??쇱슦??
    fact_json???놁쑝硫??먯뿰??question留뚯쑝濡??덇굅??RAG ?몄텧.
    """
    session_id: Optional[str] = None    # ?놁쑝硫??먮룞 ?앹꽦
    question: Optional[str] = None      # ?먯뿰??吏덈Ц (fact_json ?놁쓣 ???ъ슜)
    fact_json: Optional[dict] = None    # 援ъ“???ъ떎愿怨?
    enable_debate: bool = False         # Red-Blue ?쇱웳 ?ㅽ뻾 ?щ?

    class Config:
        json_schema_extra = {
            "example": {
                "fact_json": {
                    "transfer_date": "20240601",
                    "acquisition_date": "20200301",
                    "property_type": "?꾪뙆??,
                    "acquisition_reason": "留ㅻℓ",
                    "household_house_count": 1,
                    "transfer_price": 1100000000,
                    "residence_years": 2.5,
                    "is_adjustment_area_at_transfer": True,
                }
            }
        }


class ChatResponse(BaseModel):
    session_id: str
    verdict: str                    # 鍮꾧낵??| 媛먮㈃ | 以묎낵 | ?쇰컲怨쇱꽭 | ?④린?몄쑉 | 怨좉?二쇳깮 | ?ъ떎愿怨꾨?議?
    answer: str
    confidence: float
    citations: list[str]
    chunk_ids: list[str]
    missing_facts: list[str]
    warnings: list[str]
    blocked: bool                   # L2?먯꽌 李⑤떒?먯쑝硫?True (missing_facts濡??ъ슂泥?
    mode: str                       # "pipeline" | "legacy"


# ?? ?듭떖 濡쒖쭅 ?????????????????????????????????????????????????????????????????

async def chat_turn(
    fact_json: Optional[dict] = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    enable_debate: bool = False,
    query_mode: str = "report",
) -> dict[str, Any]:
    """
    梨꾪똿 1??泥섎━ ?⑥닔. Streamlit UI?먯꽌 吏곸젒 ?몄텧 媛??

    fact_json ?덉쓬 ??L1-L5 ?뚯씠?꾨씪??(verdict ?ы븿)
    fact_json ?놁쓬 ???덇굅??answer_with_citations (?먯뿰??吏덈Ц)
    query_mode: "report" | "consulting" ??consulting?대㈃ consulting_scenarios ?ы븿 諛섑솚
    """
    sid = session_id or str(uuid.uuid4())[:8]

    if fact_json:
        # ?? L1-L5 ?뚯씠?꾨씪??寃쎈줈 ??????????????????????????????????????????
        from src.api.fact_input import FactInput, fact_input_to_rag_query
        from src.domain.pipeline import run_rag_pipeline
        from src.retrieval.retriever_impl import PineconeTaxLawRetriever
        from src.retrieval.llm_fn import llm_fn

        # simulation_* ?ㅻ뒗 FactInput ?ㅽ궎留??몃? ???뚯떛 ??遺꾨━
        fact_for_schema = {k: v for k, v in fact_json.items() if not k.startswith("simulation_") and k != "necessary_expenses"}
        query = fact_input_to_rag_query(FactInput(**fact_for_schema))
        retriever = PineconeTaxLawRetriever()
        result = await run_rag_pipeline(
            query, retriever, llm_fn,
            fact_json=fact_json,
            enable_debate=enable_debate,
            query_mode=query_mode,
        )

        ans = result.answer
        citations_str = [
            c.article if hasattr(c, "article") else str(c)
            for c in ans.citations
        ]
        return {
            "session_id": sid,
            "verdict": ans.verdict,
            "answer": ans.answer,
            "confidence": ans.confidence,
            "citations": citations_str,
            "chunk_ids": ans.chunk_ids,
            "missing_facts": ans.missing_facts,
            "warnings": ans.warnings,
            "blocked": result.blocked_at_l2,
            "mode": "pipeline",
            "consulting_scenarios": result.consulting_scenarios,
        }

    elif question:
        # ?? ?덇굅??寃쎈줈 (?먯뿰??吏덈Ц) ??????????????????????????????????????
        from src.rag import answer_with_citations

        loop = asyncio.get_event_loop()
        ans = await loop.run_in_executor(
            None, lambda: answer_with_citations(question)
        )
        return {
            "session_id": sid,
            "verdict": "?ъ떎愿怨꾨?議?,
            "answer": ans.answer,
            "confidence": ans.confidence,
            "citations": ans.citations,
            "chunk_ids": ans.chunk_ids,
            "missing_facts": ans.missing_facts,
            "warnings": ans.warnings,
            "blocked": False,
            "mode": "legacy",
        }

    else:
        return {
            "session_id": sid,
            "verdict": "?ъ떎愿怨꾨?議?,
            "answer": "fact_json ?먮뒗 question 以??섎굹瑜??낅젰??二쇱꽭??",
            "confidence": 0.0,
            "citations": [],
            "chunk_ids": [],
            "missing_facts": [],
            "warnings": ["?낅젰 ?놁쓬"],
            "blocked": True,
            "mode": "none",
        }


# ?? FastAPI ?붾뱶?ъ씤??????????????????????????????????????????????????????????

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """
    梨꾪똿 1??泥섎━.

    - fact_json ?덉쓬: L1-L5 ?뚯씠?꾨씪?몄쑝濡?鍮꾧낵??媛먮㈃/以묎낵/?쇰컲怨쇱꽭/?④린?몄쑉 ?먮떒
    - fact_json ?놁쓬: ?먯뿰??吏덈Ц?쇰줈 ?덇굅??RAG 寃??

    blocked=true ?대㈃ missing_facts ??ぉ??梨꾩썙 ?ъ슂泥?븯?몄슂.
    """
    result = await chat_turn(
        fact_json=req.fact_json,
        question=req.question,
        session_id=req.session_id,
    )
    return ChatResponse(**result)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

codex
핵심은 두 가지입니다. 지금 병목은 “모델 자체가 느리다”보다 “불필요하게 큰 입력을 느린 경로에 태운다”에 더 가깝습니다. 특히 현재 파이프라인에서는 `L3`에서 만든 `enriched_query`를 retrieval에 쓰지 않고 있어서, 검색 품질이 낮아지고 reranker/LLM 둘 다 더 무거워집니다. 이건 [src/domain/pipeline.py](</c:/Users/user/cording2025/tax-rag/src/domain/pipeline.py>) 와 [src/retrieval/retriever_impl.py](</c:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py>) 조합에서 바로 보입니다.

우선순위는 아래 순서가 맞습니다.

**1. Reranker CPU 속도**
가장 효과 큰 건 `20개 전부를 bge-reranker-v2-m3`에 태우지 않는 겁니다.

- `dense/hybrid top_k=20` 유지, `rerank_pool_k=6~10`으로 축소
- 축소 기준은 Pinecone score + article-number exact hit + entity_scope hit + 부칙 연결 여부 같은 결정론 신호
- 최종 선택은 여전히 BGE 이후로 유지하므로 AGENTS 규칙도 안 깨집니다

예시:
```python
# src/retrieval/retriever_impl.py
def _cheap_prefilter(matches: list[dict], query_text: str, limit: int = 8) -> list[dict]:
    article_boost = 0.15 if "제" in query_text or "§" in query_text else 0.0

    def score(m: dict) -> float:
        base = float(m.get("score", 0.0))
        meta = m.get("metadata", {})
        text = meta.get("full_text", "")
        bonus = 0.0
        if meta.get("article_number") and meta["article_number"] in query_text:
            bonus += article_boost
        if meta.get("entity_scopes"):
            bonus += 0.05
        if meta.get("linked_buchik_ids"):
            bonus += 0.03
        return base + bonus

    return sorted(matches, key=score, reverse=True)[:limit]
```

그 다음 [src/infra/reranker.py](</c:/Users/user/cording2025/tax-rag/src/infra/reranker.py>)에서 바로 할 일:

- `max_length`를 512 기본값에서 `192` 또는 `256`으로 낮추기
- `batch_size` 명시
- ONNX Runtime CPU backend 사용
- 가능하면 INT8 dynamic quantization

예시:
```python
from sentence_transformers import CrossEncoder

_reranker = CrossEncoder(
    BGE_RERANKER_MODEL,
    max_length=256,
    backend="onnx",   # onnxruntime 설치 필요
)
```

```python
scores = reranker.predict(
    pairs,
    batch_size=8,
    show_progress_bar=False,
    convert_to_numpy=True,
)
```

추가로:
- `_MAX_TEXT_CHARS=600`도 여전히 길 수 있습니다. 법령은 앞부분 집중도가 높아서 `350~450 chars`로 먼저 실험할 가치가 큽니다.
- article 본문 전체 대신 “제목 + 조문번호 + 첫 문단 + 키워드 매칭 문장 1~2개”만 reranker에 넣는 압축 뷰를 따로 만들면 CPU 시간이 더 줄어듭니다.
- 프로세스 시작 시 1회 워밍업 호출을 넣으세요.
- `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `torch.set_num_threads()`도 고정해서 흔들림을 줄이세요.

정리하면 CPU에서 기대되는 순서는:
1. rerank 후보 축소
2. `max_length` 축소
3. ONNX/INT8
4. 입력 텍스트 압축

**2. Claude API 지연**
80초는 거의 항상 “입력 + 출력이 너무 김”입니다. [src/retrieval/llm_fn.py](</c:/Users/user/cording2025/tax-rag/src/retrieval/llm_fn.py>) 기준으로 줄일 지점이 명확합니다.

바로 바꿀 것:
- `1500 max_tokens`를 `500~700`으로 낮추기
- `5 chunks x 800 chars`를 그대로 보내지 말고 `3~4 chunks` + chunk당 `250~450 chars`로 줄이기
- few-shot은 fast path에서는 끄고, low-confidence일 때만 2차 호출로 승격
- `Anthropic()` 매 호출 생성 대신 singleton 또는 `AsyncAnthropic` 사용
- streaming으로 TTFT 개선
- prompt caching 적용

캐싱 구조는 system/instructions와 고정 출력 스키마를 캐시 prefix로 두는 게 맞습니다. 공식 문서:
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Streaming: https://platform.claude.com/docs/en/build-with-claude/streaming
- Latency guidance: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency
- Models overview: https://platform.claude.com/docs/en/about-claude/models/overview

예시:
```python
from anthropic import AsyncAnthropic

_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": RAG_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": JSON_SCHEMA_INSTRUCTION,
        "cache_control": {"type": "ephemeral"},
    },
]
```

```python
message = await _client.messages.create(
    model=CLAUDE_MODEL,
    max_tokens=600,
    system=SYSTEM_BLOCKS,
    messages=[{"role": "user", "content": user_prompt}],
)
```

중요한 점:
- 캐시는 “완전히 동일한 prefix”여야 먹습니다
- `few_shot_block`이 요청마다 바뀌면 캐시 효율이 깨집니다
- 따라서 `few-shot`은 캐시 prefix에 두지 말고, 필요 시 별도 2차 호출로 분리하는 게 낫습니다

모델 라우팅도 바로 가능:
- 기본: `claude-haiku-4-5`
- `danger_flags >= 2`, `missing_facts`, `고가주택`, `이월과세`, `상속`, `특례 충돌`일 때만 `claude-sonnet-4-6`
- debate 단계만 Opus 또는 Sonnet 유지

예시:
```python
def choose_model(query, fact_check, chunks) -> str:
    if fact_check.danger_flags >= 2:
        return "claude-sonnet-4-6"
    if len(chunks) <= 3 and not fact_check.missing_fact_texts():
        return "claude-haiku-4-5"
    return "claude-sonnet-4-6"
```

**3. 병렬화**
`embedding -> Pinecone -> rerank`는 strict dependency라 직접 겹칠 수 없습니다. embedding과 rerank를 겹치는 건 불가합니다.

겹칠 수 있는 건 이쪽입니다:
- query enrichment와 sparse BM25 생성
- Pinecone 조회 후 부칙 `fetch`는 batch fetch로 병렬/일괄화
- LLM 호출 전 `few_shot_block` 생성, citation map 준비, output-validator용 retrieved-id set 구성
- Streamlit 응답은 streaming으로 먼저 보여주고, L5 검증/후처리는 뒤에서 수행

지금 `retrieve_with_buchik()`는 linked 부칙을 개별 `fetch`하고 있어서 왕복이 많습니다. 이건 일괄 fetch로 줄이세요.

```python
# src/retrieval/retriever_impl.py
all_buchik_ids = list({
    bid
    for chunk in results
    for bid in chunk.metadata.linked_buchik_ids
    if bid not in seen_ids
})
res = index.fetch(ids=all_buchik_ids, namespace=self.namespace)
```

그리고 큰 구조상 더 중요한 병렬화는 “1차 fast answer / 2차 refine”입니다.
- 1차: top 3 chunks, no few-shot, Haiku or Sonnet short output
- 2차: low-confidence일 때만 Sonnet full + debate
이렇게 해야 체감 시간이 확 줄어듭니다.

**4. 캐시**
캐시는 네 군데가 유효합니다.

- query embedding cache
- Pinecone result cache
- reranker result cache
- final answer cache

추천 키:
```python
cache_key = sha256(json.dumps({
    "query_text": normalized_query_text,
    "anchor_date": as_of_int,
    "entity_scope": query.entity_scope.value,
    "namespace": self.namespace,
    "top_k": top_k,
    "hybrid_alpha": hybrid_alpha,
}, sort_keys=True).encode()).hexdigest()
```

reranker 캐시는 더 좁게:
```python
rerank_key = sha256(json.dumps({
    "query": normalized_query_text,
    "candidate_ids": [m["id"] for m in prefiltered_matches],
    "candidate_versions": [
        m["metadata"].get("effective_date") for m in prefiltered_matches
    ],
    "model": BGE_RERANKER_MODEL,
    "max_length": 256,
}, sort_keys=True).encode()).hexdigest()
```

실무 팁:
- 메모리 `lru_cache` + 디스크 `diskcache` 또는 Redis 2단계
- TTL은 법령 검색은 길게, 세션 answer cache는 짧게
- query normalization은 필수
- 날짜/주택수/특례 flag가 다르면 캐시 분리

예시:
```python
from diskcache import Cache
cache = Cache(".cache/rag")

def cached_rerank(key: str, fn):
    val = cache.get(key)
    if val is not None:
        return val
    val = fn()
    cache.set(key, val, expire=3600)
    return val
```

**지금 코드에서 먼저 손댈 5개**
1. `enriched_query`를 retrieval에도 반영
2. rerank 대상 20 -> 8
3. CrossEncoder `max_length=256`, `backend="onnx"`
4. Claude `max_tokens=1500 -> 600`, chunks `5x800 -> 3~4x350`
5. prompt cache + fast/slow model routing

이 5개만 해도 90~110초를 대체로 절반 이하로 내릴 가능성이 큽니다. 원하면 다음 턴에 바로 `retriever_impl.py`, `reranker.py`, `llm_fn.py` 기준으로 실제 패치까지 해드리겠습니다.
tokens used
97,335

```

## Concise summary

Provider completed successfully. Review the raw output for details.

## Action items

- Review the response and extract decisions you want to apply.
- Capture follow-up implementation tasks if needed.
