# codex advisor artifact

- Provider: codex
- Exit code: 0
- Created at: 2026-05-20T05:33:46.298Z

## Original task

Korean tax RAG system architecture review. The system has these hardcoded law-change-vulnerable points:

1. query_input.py - constants: HIGH_VALUE_THRESHOLD=1.2B KRW, SANGSAENG_WINDOW_END=2024-12-31, iota_period_years logic (5yr pre-2023, 10yr post-2023)
2. fact_checker.py - L2 decision rules referencing these constants
3. DANGER_KEYWORD_MAP - article numbers hardcoded in keyword strings (e.g. '제97조의2')
4. embed.py _tag_chunk() - article-number-to-topic mapping rules
5. prompts.py - hardcoded thresholds in Red Team prompt ('5년/10년', '12억')

Proposed RLVR loop: eval results → per-flag recall@k → missing chunk keyword extraction from Pinecone → DANGER_KEYWORD_MAP update suggestions. Reward signals: citation_precision (automatic L5), recall@k (gold_chunk_ids), verdict_match. No auto-apply - human review required.

Review: (1) What technical gaps or risks are missed in this analysis? (2) Are there architectural issues with the proposed RLVR approach? (3) What monitoring/alerting patterns are missing? (4) Is the 'detect only, human fixes' approach appropriate or too conservative? Provide concrete technical critique.

## Final prompt

Korean tax RAG system architecture review. The system has these hardcoded law-change-vulnerable points:

1. query_input.py - constants: HIGH_VALUE_THRESHOLD=1.2B KRW, SANGSAENG_WINDOW_END=2024-12-31, iota_period_years logic (5yr pre-2023, 10yr post-2023)
2. fact_checker.py - L2 decision rules referencing these constants
3. DANGER_KEYWORD_MAP - article numbers hardcoded in keyword strings (e.g. '제97조의2')
4. embed.py _tag_chunk() - article-number-to-topic mapping rules
5. prompts.py - hardcoded thresholds in Red Team prompt ('5년/10년', '12억')

Proposed RLVR loop: eval results → per-flag recall@k → missing chunk keyword extraction from Pinecone → DANGER_KEYWORD_MAP update suggestions. Reward signals: citation_precision (automatic L5), recall@k (gold_chunk_ids), verdict_match. No auto-apply - human review required.

Review: (1) What technical gaps or risks are missed in this analysis? (2) Are there architectural issues with the proposed RLVR approach? (3) What monitoring/alerting patterns are missing? (4) Is the 'detect only, human fixes' approach appropriate or too conservative? Provide concrete technical critique.

## Raw output

```text
**Findings**

1. The analysis is too retrieval-centric. Your biggest law-change risk is not just “missing the right chunk,” it is deterministic rule drift in multiple layers that all reuse the same stale assumptions. `HIGH_VALUE_THRESHOLD`, `iota_period_years`, and date windows drive verdict logic in [query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:21), [fact_checker.py](/c:/Users/user/cording2025/tax-rag/src/domain/fact_checker.py:72), and even post-LLM safety behavior in [output_validator.py](/c:/Users/user/cording2025/tax-rag/src/domain/output_validator.py:65). RLVR updates to `DANGER_KEYWORD_MAP` do nothing for those failures.

2. The system has a correlated-failure problem. Tests and prompts encode the same stale law assumptions, so eval may “pass” while the law is wrong. The 5-year rollover assumption is asserted in [test_pipeline_cases.py](/c:/Users/user/cording2025/tax-rag/tests/test_pipeline_cases.py:146), and expected articles/verdicts are hardcoded in [rag_golden_cases.py](/c:/Users/user/cording2025/tax-rag/tests/rag_golden_cases.py:52). That means `verdict_match` can reward conformity to outdated policy.

3. Your retrieval versioning model is underspecified for tax law. The retriever filters chunks only by `transfer_date` in [retriever_impl.py](/c:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py:111), but many transitional tax rules depend on acquisition date, contract date, gift date, death date, or application date. This is a more serious architecture gap than the keyword map. RLVR cannot repair a wrong legal-version slice.

4. `DANGER_KEYWORD_MAP` and `_tag_chunk()` are coupled but analyzed separately. Retrieval enrichment may be improved while Stage 1 tagging/filtering still excludes the relevant material. See [query_enrichment.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_enrichment.py:20) and [_tag_chunk in ingestion/embed.py](/c:/Users/user/cording2025/tax-rag/src/ingestion/embed.py:34). If the ontology drifts, recall will remain unstable no matter how good the keywords become.

5. `citation_precision` is too weak if it is basically “not a phantom citation.” That checks existence, not support. A retrieved article can be real and still be the wrong clause, wrong version, or legally insufficient for the proposition. Your reward signal will overestimate quality.

**(1) Missed technical gaps / risks**

- No single source of truth for law-dependent rules. You need a versioned legal-rules registry, not scattered constants plus prose prompts.
- Transitional-law applicability is the missing first-class concept. Current chunk metadata has effective dates, but not enough machine-readable applicability logic.
- Prompt drift is treated as cosmetic, but here prompts are part of the reasoning control plane. Hardcoded “12억”, “5년/10년” in [prompts.py](/c:/Users/user/cording2025/tax-rag/src/agents/prompts.py:101) can anchor the model to obsolete law even when retrieval is correct.
- Stage 1 taxonomy drift is missing from the analysis. `_tag_chunk()` article-number rules are effectively a second retrieval policy layer.
- Eval set drift is missing. If golden cases are not regularly re-based against current law and corpus versions, RLVR will optimize against stale labels.
- Corpus freshness risk is missing. A law change may be correctly reflected in logic review but absent from Pinecone because ingestion lagged.

**(2) Architectural issues in the proposed RLVR approach**

- It optimizes the wrong lever first. Most proposed actions update `DANGER_KEYWORD_MAP`, but several failure modes are caused by rule logic, version selection, or tagging.
- It risks reward hacking. The system may learn to stuff more article-number tokens into queries to improve recall@k without improving legal correctness.
- Keyword extraction from missing Pinecone chunks is lexically brittle. If law numbering changes, extracted candidates may reinforce obsolete article references.
- `verdict_match` is unsafe as a primary signal unless labels are versioned by law date and reviewed after amendments.
- The approach is incomplete because it does not propose synchronized changes to:
  - legal constants/rules
  - query enrichment
  - chunk tagging ontology
  - prompts
  - tests/golden labels
- It lacks provenance. Suggested updates should cite which failed cases, which missing chunks, which law versions, and which statute diffs triggered the suggestion.

A better architecture is:
1. Centralize law-dependent rules in a versioned config/registry with anchors and citations.
2. Make retriever applicability multi-anchor, not `transfer_date`-only.
3. Treat RLVR as diagnosis/ranking, not as the primary adaptation mechanism.
4. Generate suggestions per layer: retrieval keywords, tagging rules, deterministic legal rules, prompts, and tests.

**(3) Missing monitoring / alerting**

- Law source diff monitor: detect statute/article text changes from `law.go.kr`, not just downstream retrieval regressions.
- Corpus freshness SLA: alert if source changed but processed JSON / Pinecone index has not been rebuilt.
- Version mismatch alerts: retrieved chunk effective dates inconsistent with case anchors.
- Per-flag dashboards: recall@k, rerank hit rate, citation support rate, verdict drift.
- Stage-by-stage counters:
  - zero-hit retrieval rate
  - reranker drop-off rate
  - Stage 1 filter false-exclusion rate
  - L2 block rate by reason
  - L5 warning rate by type
- Citation quality metrics beyond phantom detection:
  - cited chunk retrieved
  - cited chunk reranked top-n
  - cited article actually contains supporting clause
- Distribution-shift monitoring on `danger_flags` and user fact patterns.
- Review queue alerting: backlog, time-to-review, repeated suggestions for same flag.
- Canary set alerts: known amendment-sensitive cases run daily against latest corpus.

**(4) Is “detect only, human fixes” appropriate?**

For legal tax logic, `no auto-apply` is correct for anything that changes verdict behavior, citations, thresholds, or rule windows. Fully automatic mutation is too risky.

But “detect only” is too conservative if it means humans must do all mechanical work. A better split is:

- Auto-generate evidence-rich change proposals.
- Auto-open patch suggestions for config/tests/prompts in a review branch.
- Auto-run regression suites and show impact deltas.
- Require human approval for merge and deployment.

So the right posture is not “auto-apply” vs “detect only.” It is “auto-diagnose and auto-prepare, human-authorize.”

**Bottom line**

Your current analysis correctly spots hardcoded law-sensitive values, but it underestimates:
- deterministic rule drift,
- legal-version applicability drift,
- ontology/tagging drift,
- eval-label drift.

The proposed RLVR loop is useful as a retrieval diagnostics tool, but architecturally it is too narrow to be the main adaptation mechanism for a legal RAG system.


OpenAI Codex v0.123.0 (research preview)
--------
workdir: c:\Users\user\cording2025\tax-rag
model: gpt-5.4
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 019e43de-77f7-75e3-908a-815d07c9c2d1
--------
user
Korean tax RAG system architecture review. The system has these hardcoded law-change-vulnerable points:

1. query_input.py - constants: HIGH_VALUE_THRESHOLD=1.2B KRW, SANGSAENG_WINDOW_END=2024-12-31, iota_period_years logic (5yr pre-2023, 10yr post-2023)
2. fact_checker.py - L2 decision rules referencing these constants
3. DANGER_KEYWORD_MAP - article numbers hardcoded in keyword strings (e.g. '제97조의2')
4. embed.py _tag_chunk() - article-number-to-topic mapping rules
5. prompts.py - hardcoded thresholds in Red Team prompt ('5년/10년', '12억')

Proposed RLVR loop: eval results → per-flag recall@k → missing chunk keyword extraction from Pinecone → DANGER_KEYWORD_MAP update suggestions. Reward signals: citation_precision (automatic L5), recall@k (gold_chunk_ids), verdict_match. No auto-apply - human review required.

Review: (1) What technical gaps or risks are missed in this analysis? (2) Are there architectural issues with the proposed RLVR approach? (3) What monitoring/alerting patterns are missing? (4) Is the 'detect only, human fixes' approach appropriate or too conservative? Provide concrete technical critique.
codex
하드코딩된 법령 취약 지점과 RLVR 제안을 코드 기준으로 검토하겠습니다. 먼저 해당 파일들의 실제 구현과 규칙 분산 정도를 확인한 뒤, 빠진 리스크와 아키텍처 문제를 짚겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'rg -n "HIGH_VALUE_THRESHOLD|SANGSAENG_WINDOW_END|iota_period_years|DANGER_KEYWORD_MAP|제97조의2|_tag_chunk|5년|10년|12억|97조의2" src tests' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'Get-ChildItem -Recurse src | Select-Object FullName' in c:\Users\user\cording2025\tax-rag
 succeeded in 3415ms:

FullName                                                                                  
--------                                                                                  
C:\Users\user\cording2025\tax-rag\src\agents                                              
C:\Users\user\cording2025\tax-rag\src\api                                                 
C:\Users\user\cording2025\tax-rag\src\domain                                              
C:\Users\user\cording2025\tax-rag\src\eval                                                
C:\Users\user\cording2025\tax-rag\src\infra                                               
C:\Users\user\cording2025\tax-rag\src\ingestion                                           
C:\Users\user\cording2025\tax-rag\src\retrieval                                           
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
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__                                  
C:\Users\user\cording2025\tax-rag\src\domain\chunk_metadata.py                            
C:\Users\user\cording2025\tax-rag\src\domain\fact_checker.py                              
C:\Users\user\cording2025\tax-rag\src\domain\output_validator.py                          
C:\Users\user\cording2025\tax-rag\src\domain\pipeline.py                                  
C:\Users\user\cording2025\tax-rag\src\domain\query_enrichment.py                          
C:\Users\user\cording2025\tax-rag\src\domain\query_input.py                               
C:\Users\user\cording2025\tax-rag\src\domain\retriever.py                                 
C:\Users\user\cording2025\tax-rag\src\domain\tax_answer.py                                
C:\Users\user\cording2025\tax-rag\src\domain\__init__.py                                  
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\chunk_metadata.cpython-313.pyc   
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\fact_checker.cpython-313.pyc     
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\output_validator.cpython-313.pyc 
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\pipeline.cpython-313.pyc         
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\query_enrichment.cpython-313.pyc 
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\query_input.cpython-313.pyc      
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\retriever.cpython-313.pyc        
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\tax_answer.cpython-313.pyc       
C:\Users\user\cording2025\tax-rag\src\domain\__pycache__\__init__.cpython-313.pyc         
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__                                    
C:\Users\user\cording2025\tax-rag\src\eval\debate.py                                      
C:\Users\user\cording2025\tax-rag\src\eval\eval.py                                        
C:\Users\user\cording2025\tax-rag\src\eval\feedback.py                                    
C:\Users\user\cording2025\tax-rag\src\eval\golden_injector.py                             
C:\Users\user\cording2025\tax-rag\src\eval\retrieval_analyzer.py                          
C:\Users\user\cording2025\tax-rag\src\eval\__init__.py                                    
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\eval.cpython-313.pyc               
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\feedback.cpython-313.pyc           
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\retrieval_analyzer.cpython-313.pyc 
C:\Users\user\cording2025\tax-rag\src\eval\__pycache__\__init__.cpython-313.pyc           
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__                                   
C:\Users\user\cording2025\tax-rag\src\infra\embedder.py                                   
C:\Users\user\cording2025\tax-rag\src\infra\pinecone_client.py                            
C:\Users\user\cording2025\tax-rag\src\infra\reranker.py                                   
C:\Users\user\cording2025\tax-rag\src\infra\__init__.py                                   
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\embedder.cpython-313.pyc          
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\pinecone_client.cpython-313.pyc   
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\reranker.cpython-313.pyc          
C:\Users\user\cording2025\tax-rag\src\infra\__pycache__\__init__.cpython-313.pyc          
C:\Users\user\cording2025\tax-rag\src\ingestion\collect.py                                
C:\Users\user\cording2025\tax-rag\src\ingestion\embed.py                                  
C:\Users\user\cording2025\tax-rag\src\ingestion\__init__.py                               
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__                               
C:\Users\user\cording2025\tax-rag\src\retrieval\llm_fn.py                                 
C:\Users\user\cording2025\tax-rag\src\retrieval\retriever_impl.py                         
C:\Users\user\cording2025\tax-rag\src\retrieval\__init__.py                               
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__\llm_fn.cpython-313.pyc        
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__\retriever_impl.cpython-313.pyc
C:\Users\user\cording2025\tax-rag\src\retrieval\__pycache__\__init__.cpython-313.pyc      
C:\Users\user\cording2025\tax-rag\src\__pycache__\collect.cpython-313.pyc                 
C:\Users\user\cording2025\tax-rag\src\__pycache__\embed.cpython-313.pyc                   
C:\Users\user\cording2025\tax-rag\src\__pycache__\feedback.cpython-313.pyc                
C:\Users\user\cording2025\tax-rag\src\__pycache__\rag.cpython-313.pyc                     
C:\Users\user\cording2025\tax-rag\src\__pycache__\schema.cpython-313.pyc                  
C:\Users\user\cording2025\tax-rag\src\__pycache__\__init__.cpython-313.pyc                



 succeeded in 3431ms:
src\api\mcp_server.py:102:                  (예: "2019년 취득, 2024년 양도, 보유 5년, 거주 3년, 1세대 1주택")
src\domain\fact_checker.py:70:            reason="양도가액 미확인 — 12억 초과 고가주택 여부를 알 수 없으면 비과세 범위 계산 불가",
src\domain\fact_checker.py:76:        danger.append("고가주택")  # 12억 초과 확인 → L3에서 §89/§156의2 키워드 주입
src\domain\fact_checker.py:96:            if years_elapsed < rt.iota_period_years:
src\domain\fact_checker.py:97:                danger.append(f"이월과세_{rt.iota_period_years}년이내")
src\domain\fact_checker.py:102:                            f"배우자/직계존비속 증여 후 {rt.iota_period_years}년 이내 양도 — "
src\domain\fact_checker.py:118:                reason="상속개시일(사망일) 필요 — 5년 이내 상속주택 주택 수 제외 기간 기산점",
tests\rag_golden_cases.py:29:    # 조건: 아파트, 매매취득, 1주택, 조정대상지역, 2년 이상 거주, 12억 이하
tests\rag_golden_cases.py:61:            "notes": "조정대상지역 취득 → 2년 거주요건 충족. 12억 이하 → 전액 비과세.",
tests\rag_golden_cases.py:67:    # 조건: 1주택, 2년 거주 충족, 양도가액 15억 → 12억 초과분은 과세
tests\rag_golden_cases.py:73:        "description": "비과세 요건은 충족하지만 12억 초과분(3억)에 대해 과세되는 케이스.",
tests\rag_golden_cases.py:100:                "양도가액 15억 → 12억 초과 3억에 대해 과세. "
tests\rag_golden_cases.py:101:                "장기보유특별공제 표2(10년 이상 보유+거주) 적용 가능. "
tests\rag_golden_cases.py:128:            "transfer_date": "2025-09-10",         # 증여 후 약 3.2년 → 5년 이내
tests\rag_golden_cases.py:208:    #        상속개시일로부터 5년 이내 → 상속주택은 주택 수에서 제외
tests\rag_golden_cases.py:217:            "상속개시 5년 이내(2027-11-30 전)에 일반주택 양도(2025-11-10) → 상속주택 제외 1주택 비과세."
tests\rag_golden_cases.py:252:                "상속개시 후 5년 이내 일반주택 양도 → 상속주택 주택 수 제외. "
tests\rag_golden_cases.py:255:                "양도가액 7.5억 → 12억 이하 → 전액 비과세."
src\domain\output_validator.py:64:    # 12억 초과이면 초과분은 과세 → 완전 비과세가 아님
src\domain\output_validator.py:72:            "⚠ 양도가액 미확인 — 고가주택(12억 초과) 해당 시 초과분 과세됨. "
src\agents\prompts.py:41:    "10년 경력의 세무사 출신 AI 어드바이저. 조문에 없는 내용은 절대 인용하지 않으며, "
src\agents\prompts.py:112:6. 고가주택 기준 오류 — 12억 초과 판단 착오
src\agents\prompts.py:113:7. 이월과세 누락 — 배우자·직계존비속 증여 후 5년/10년 내 양도
src\api\sample_cases.py:62:        "label": "고가주택 — 12억 초과, 초과분만 과세",
src\api\sample_cases.py:281:        "label": "배우자 증여 이월과세 — 5년 이내 양도",
src\api\sample_cases.py:304:        "label": "직계존비속 증여 이월과세 — 10년 이내 양도",
src\api\sample_cases.py:349:        "label": "혼인합가 일시적 2주택 — 5년 내 양도 비과세",
src\domain\query_enrichment.py:22:DANGER_KEYWORD_MAP: Dict[str, str] = {
src\domain\query_enrichment.py:23:    "이월과세": "배우자 직계존비속 증여 이월과세 소득세법 제97조의2 원취득가액",
src\domain\query_enrichment.py:24:    "이월과세_5년이내": "증여 후 5년 이내 양도 이월과세 소득세법 제97조의2",
src\domain\query_enrichment.py:25:    "이월과세_10년이내": "증여 후 10년 이내 양도 이월과세 소득세법 제97조의2 2023년 개정",
src\domain\query_enrichment.py:26:    "고가주택_미확인": "고가주택 12억 초과 장기보유특별공제 표2 소득세법 제95조",
src\domain\query_enrichment.py:27:    "고가주택": "고가주택 12억 장기보유특별공제 표2 소득세법 제95조 시행령 제156조의2",
src\domain\query_enrichment.py:42:    "동거봉양합가": "동거봉양 합가 10년 이내 비과세 소득세법 시행령 제155조 제4항",
src\domain\query_enrichment.py:55:    (re.compile(r"고가주택|12억"), "고가주택"),
src\domain\query_enrichment.py:102:        kw = DANGER_KEYWORD_MAP.get(flag)
src\domain\query_input.py:5:- transfer_price 추가 → 고가주택(12억 초과) 판단 가능
src\domain\query_input.py:25:HIGH_VALUE_THRESHOLD = 1_200_000_000  # 12억 원
src\domain\query_input.py:29:SANGSAENG_WINDOW_END = date(2024, 12, 31)
src\domain\query_input.py:220:    mandatory_period_years: int           # 의무임대기간 (4/8/10년)
src\domain\query_input.py:246:    ① 계약 체결일: SANGSAENG_WINDOW_START ~ SANGSAENG_WINDOW_END
src\domain\query_input.py:268:        return SANGSAENG_WINDOW_START <= self.contract_date <= SANGSAENG_WINDOW_END
src\domain\query_input.py:290:    혼인 전 각자 1주택 → 혼인 후 1세대 2주택 → 5년 이내 양도 시 비과세.
src\domain\query_input.py:361:      - 2023년 이전 증여: 증여일로부터 5년 이내
src\domain\query_input.py:362:      - 2023년 이후 증여: 증여일로부터 10년 이내 (2023.01.01 개정)
src\domain\query_input.py:373:    def iota_period_years(self) -> int:
src\domain\query_input.py:374:        """이월과세 적용 기간: 2023년 이후 증여는 10년, 이전은 5년"""
src\domain\query_input.py:387:    60세 이상 or 중증질환 직계존속과 합가 후 10년 이내 먼저 양도하는 주택 비과세.
src\domain\query_input.py:540:            period = self.rollover_taxation.iota_period_years
src\domain\query_input.py:589:    #   상속주택 5년 이내 = 제외, 지방저가주택(3억↓) = 제외 가능
src\domain\query_input.py:621:        """고가주택 여부 (양도가액 12억 초과) — 비과세 전액 불가, 초과분 과세"""
src\domain\query_input.py:624:        return self.transfer_price > HIGH_VALUE_THRESHOLD
src\domain\query_input.py:678:                f"이월과세적용: 소득세법제97조의2 배우자직계증여후{rt.iota_period_years}년이내양도 "
src\domain\tax_answer.py:18:    PARTIALLY_EXEMPT = "고가주택"  # 12억 초과분만 과세
src\api\schema.py:60:    # 혼인 전 각자 보유 주택 취득일 (소령 §155⑤ — 5년 이내 먼저 양도 비과세)
src\api\schema.py:68:    cohabitation_start_date: str            # 합가일 (소령 §155④ — 10년 이내 비과세)
src\api\schema.py:295:        "고가주택",         # 12억 초과분만 과세
src\eval\retrieval_analyzer.py:2:검색 품질 분석기 + DANGER_KEYWORD_MAP 자동 개선 제안
src\eval\retrieval_analyzer.py:7:  → DANGER_KEYWORD_MAP 업데이트 제안 생성
src\eval\retrieval_analyzer.py:23:from src.domain.query_enrichment import DANGER_KEYWORD_MAP, detect_flags_from_text
src\eval\retrieval_analyzer.py:189:        current_kw = DANGER_KEYWORD_MAP.get(flag, "")
src\eval\retrieval_analyzer.py:203:    DANGER_KEYWORD_MAP 업데이트 제안을 생성한다.
src\eval\retrieval_analyzer.py:216:                "current_keyword": DANGER_KEYWORD_MAP.get(flag, "(없음)"),
src\eval\retrieval_analyzer.py:283:    print("  DANGER_KEYWORD_MAP 업데이트 제안")
src\ingestion\embed.py:34:def _tag_chunk(law_name: str, article_number: str, full_text: str) -> dict:
src\ingestion\embed.py:184:            tags = _tag_chunk(law_name, article_number, full_text)
tests\test_pipeline_cases.py:126:        # 9억 < 12억 → 고가주택 아님
tests\test_pipeline_cases.py:130:# ── 케이스 2: 이월과세 (배우자 증여 후 5년 이내 양도) ─────────────────────────
tests\test_pipeline_cases.py:144:        # 2022년 증여 → 2023년 이전 → 5년 적용
tests\test_pipeline_cases.py:146:        assert rt.iota_period_years == 5
tests\test_pipeline_cases.py:156:        # 3.35년 < 5년 이내 → danger flag 생성
tests\test_pipeline_cases.py:157:        assert "이월과세_5년이내" in result.danger_flags
tests\test_pipeline_cases.py:162:        assert "소득세법 제97조의2" in enriched
tests\test_pipeline_cases.py:167:        assert "소득세법제97조의2" in text
tests\test_pipeline_cases.py:174:        fact_checker 규칙 #2: rt.is_gift_from_spouse_or_lineal=True + 5년 이내
tests\test_pipeline_cases.py:201:        # 15억 > 12억 → 고가주택
src\retrieval\retriever_impl.py:139:        # EntityScope.value = "주택"/"분양권" 등 — embed.py의 _tag_chunk()와 동일한 값 사용

codex
규칙이 예상보다 더 넓게 퍼져 있습니다. 하드코딩 이슈는 5개 지점만이 아니라 테스트, 후처리 검증, 샘플케이스, retrieval tag 스키마까지 연쇄되어 있어 변경 감지 범위를 더 넓혀야 합니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\query_input.py | Select-Object -First 220" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\fact_checker.py | Select-Object -First 220" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\query_enrichment.py | Select-Object -First 220" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\ingestion\\embed.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\eval\\retrieval_analyzer.py | Select-Object -First 360" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\agents\\prompts.py | Select-Object -First 220" in c:\Users\user\cording2025\tax-rag
 succeeded in 3933ms:
"""
RAG 荑쇰━ ?낅젰 ?ㅽ궎留????ъ떎愿怨???踰뺣졊 寃???낅젰媛?
而ㅻ쾭由ъ? 媛?諛섏쁺 (v3):
- transfer_price 異붽? ??怨좉?二쇳깮(12??珥덇낵) ?먮떒 媛??- PropertyType enum ??遺꾩뼇沅??낆＜沅??ㅺ?援?寃몄슜二쇳깮 援щ텇
- 議곗젙??곸???痍⑤뱷???묐룄??紐낆떆??遺꾨━ ?좎?
- residence_periods 蹂듭닔 湲곌컙 ???⑹궛 2??怨꾩궛 媛??- ?밸?蹂??곸꽭 dataclass ???쇱떆??二쇳깮/?곸냽/?κ린?꾨?/?쇱씤?⑹궛
- DateBundle??愿由ъ쿂遺꾧퀎?띿씤媛??異붽? ??議고빀?먯엯二쇨텒
- SangsaengRentalDetail ???곸깮?꾨? 5媛??붽굔 寃利?(?뚮졊 짠155??)
- ResidenceExemptionType ??嫄곗＜?붽굔 硫댁젣/?⑥텞 ?밸? ?듯빀 愿由?  (?곸깮?꾨? / ?꾨??ъ뾽?먭굅二쇱＜??/ ?댁쇅?댁＜ / 痍⑦븰洹쇰Т / ?섏슜)
- to_text() ?꾨찓???ㅼ썙??紐낆떆 ??踰≫꽣 寃???뺥솗???μ긽
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

# 怨좉?二쇳깮 湲곗? (?뚮뱷?몃쾿 짠89???? ?쒗뻾??짠156??)
HIGH_VALUE_THRESHOLD = 1_200_000_000  # 12????
# ?곸깮?꾨? ?쒖떆 ?곸슜 湲곌컙 (?뚮뱷?몃쾿 ?쒗뻾??짠155??)
SANGSAENG_WINDOW_START = date(2021, 12, 20)
SANGSAENG_WINDOW_END = date(2024, 12, 31)
SANGSAENG_MAX_INCREASE_RATE = 0.05  # ?꾨?猷?5% ?대궡 ?몄긽

# ?ㅼ＜?앹옄 以묎낵???쒖떆 諛곗젣 湲곌컙 (?뚮뱷?몃쾿 짠104?? ?뚮졊 짠167??0)
# Codex 寃利? ?쇰컲 ?좎삁??2026-05-09 醫낅즺. 2026-05-10 ?댄썑??寃쎄낵洹쒖젙留?
# ??踰뺣졊 泥?겕媛 transfer_date 湲곗??쇰줈 踰꾩쟾 ?꾪꽣?섎㈃ ?먮룞 泥섎━.
#   蹂꾨룄 ?꾨뱶 遺덊븘?? ?? 寃쎄낵洹쒖젙 而ㅻ쾭 ??land_trade_permit_application_date ?꾩슂?????덉쓬.
HEAVY_TAX_SUSPENSION_END = date(2026, 5, 9)


# ?? Enums ??????????????????????????????????????????????????????????????????


class TaxType(str, Enum):
    TRANSFER = "transfer"
    GIFT = "gift"
    INHERITANCE = "inheritance"


class PropertyType(str, Enum):
    """
    ?몃쾿???먮떒 寃쎈줈媛 ?щ씪吏??二쇳깮 ?좏삎.
    asset_kind(?먯쑀???띿뒪??? 蹂꾧컻濡??쇱슦?낆슜?쇰줈 ?ъ슜.
    """
    APARTMENT = "?꾪뙆??
    HOUSE = "?⑤룆二쇳깮"
    VILLA = "?곕┰?ㅼ꽭?"
    DAGAGU = "?ㅺ?援?            # ?꾩껜 1??= 1二쇳깮 (?뚮뱷?몃쾿 ?쒗뻾??짠155??
    GYEOMYONG = "寃몄슜二쇳깮"       # 二쇨굅+?곴? ?쇳빀 ??二쇨굅 鍮꾩쑉濡??먮떒
    SUBSCRIPTION_RIGHT = "遺꾩뼇沅?   # 2021.01.01 ?댄썑 痍⑤뱷遺?二쇳깮 ???곗엯
    ASSOCIATION_RIGHT = "?낆＜沅?    # 議고빀?먯엯二쇨텒 ??愿由ъ쿂遺꾧퀎?띿씤媛??湲곗?
    OFFICETEL_RESIDENTIAL = "二쇨굅?⑹삤?쇱뒪??
    OFFICETEL_COMMERCIAL = "?낅Т?⑹삤?쇱뒪??
    RURAL_HOUSE = "?띿뼱珥뚯＜??   # 議고듅踰?짠99?? ??蹂꾨룄 ?붽굔
    LAND = "?좎?"
    COMMERCIAL = "?곴?"


class AcquisitionReason(str, Enum):
    PURCHASE = "留ㅻℓ"
    SUBSCRIPTION = "遺꾩뼇"
    INHERITANCE = "?곸냽"
    GIFT = "利앹뿬"
    BURDEN_GIFT = "遺?대?利앹뿬"
    DIVORCE = "?댄샎?ъ궛遺꾪븷"
    AUCTION = "寃쎈ℓ"
    RECONSTRUCTION = "?ш굔異?
    REDEVELOPMENT = "?ш컻諛?
    EXPROPRIATION = "?섏슜"
    MARRIAGE_MERGE = "?쇱씤?⑷?"


class EntityScope(str, Enum):
    """Stage 1 Symbolic Filter 理쒖긽??遺꾨쪟 ??PropertyType蹂대떎 ?볦? ?⑥쐞"""
    HOUSE = "二쇳깮"
    LAND = "?좎?"
    BUNYANG_RIGHT = "遺꾩뼇沅?
    IPJU_RIGHT = "?낆＜沅?
    COMMERCIAL = "?곴?"
    OFFICETEL_RESIDENTIAL = "二쇨굅?⑹삤?쇱뒪??
    OFFICETEL_COMMERCIAL = "?낅Т?⑹삤?쇱뒪??
    STOCK = "二쇱떇"


class SpecialEventType(str, Enum):
    INHERITANCE_OPENED = "?곸냽媛쒖떆??
    GIFT_EXECUTED = "利앹뿬??
    RECONSTRUCTION_COMPLETED = "?ш굔異뺤?怨듭씪"
    MANAGEMENT_DISPOSAL_APPROVED = "愿由ъ쿂遺꾧퀎?띿씤媛??  # 議고빀?먯엯二쇨텒 湲곗궛??    EXPROPRIATION_DECIDED = "?섏슜寃곗젙??
    LOT_CONVERSION = "?섏?泥섎텇??
    DEEMED_ACQUISITION = "?섏젣痍⑤뱷??   # 1985-01-01 湲곗??쒓? ?곸슜


# ?? Date 愿????????????????????????????????????????????????????????????????


@dataclass
class SpecialEventDate:
    event_type: SpecialEventType
    date: date


@dataclass
class DateBundle:
    """
    踰뺣졊 踰꾩쟾 ?듭빱 臾띠쓬.

    遺移?寃쎄낵議곗튂 ?⑦꽩 ?덉떆:
      "??踰??쒗뻾 ???묐룄遺??곸슜. ??2018-09-13 ?댁쟾 痍⑤뱷遺꾩? 醫낆쟾 洹쒖젙."
      ??transfer_date AND acquisition_date ?????꾩슂.

    議고빀?먯엯二쇨텒:
      愿由ъ쿂遺꾧퀎?띿씤媛?쇱씠 痍⑤뱷?쒓린 湲곗궛????special_event_dates???ы븿.
    """
    transfer_date: date
    acquisition_date: date
    contract_date: Optional[date] = None
    balance_payment_date: Optional[date] = None   # ?붽툑泥?궛??    registration_date: Optional[date] = None      # ?깃린?묒닔??    special_event_dates: List[SpecialEventDate] = field(default_factory=list)

    def get_anchor(self, anchor_key: str) -> Optional[date]:
        mapping = {
            "transfer_date": self.transfer_date,
            "acquisition_date": self.acquisition_date,
            "contract_date": self.contract_date,
            "balance_payment_date": self.balance_payment_date,
            "registration_date": self.registration_date,
        }
        if anchor_key in mapping:
            return mapping[anchor_key]
        for evt in self.special_event_dates:
            if evt.event_type.value == anchor_key:
                return evt.date
        return None


# ?? 嫄곗＜ 湲곌컙 ???????????????????????????????????????????????????????????????


@dataclass
class ResidencePeriod:
    """
    ?⑥씪 嫄곗＜ 援ш컙.
    ?ㅺ굅二??붽굔(2???댁긽)? 蹂듭닔 ?끒룻눜嫄?援ш컙???⑹궛?쇰줈 怨꾩궛.
    end_date=None?대㈃ ?꾩옱 嫄곗＜ 以?
    """
    start_date: date
    end_date: Optional[date] = None

    def days(self, as_of: Optional[date] = None) -> int:
        end = self.end_date or (as_of or date.today())
        return max(0, (end - self.start_date).days)


def total_residence_years(periods: List[ResidencePeriod], as_of: Optional[date] = None) -> float:
    return sum(p.days(as_of) for p in periods) / 365.25


# ?? ?밸? ?곸꽭 ??????????????????????????????????????????????????????????????


@dataclass
class TempTwoHouseDetail:
    """
    ?쇱떆??2二쇳깮 鍮꾧낵???밸? (?뚮뱷?몃쾿 ?쒗뻾??짠155??.
    ?좉퇋二쇳깮 痍⑤뱷 ??醫낆쟾二쇳깮??湲고븳 ???묐룄?댁빞 鍮꾧낵??
    議곗젙??곸????щ????곕씪 湲고븳???щ씪吏?1??vs 3??.
    """
    new_acquisition_date: date
    old_house_must_sell_by: date     # 醫낆쟾二쇳깮 ?묐룄 湲고븳
    new_is_adjustment_area: bool     # ?좉퇋二쇳깮??議곗젙??곸???씤吏
    # 湲고븳 ?대궡 ?묐룄 ?щ???transfer_date? 鍮꾧탳?댁꽌 ?먮떒


@dataclass
class InheritanceDetail:
    """
    ?곸냽二쇳깮 ?밸? ??3媛吏 蹂꾨룄 寃쎈줈.

    寃쎈줈 A (?뚮졊 짠155??: ?곸냽二쇳깮 + ?쇰컲二쇳깮 ?숈떆 蹂댁쑀 ???쇰컲二쇳깮 ?묐룄 ??鍮꾧낵??    寃쎈줈 B (?뚮졊 짠155??: ?곸냽二쇳깮 ?먯껜 ?묐룄 ???쇱긽?띿씤 蹂댁쑀湲곌컙 ?⑹궛
    寃쎈줈 C (?뚮졊 짠155??以??: ?숆굅遊됱뼇 ?⑷? ?곸냽 ??CohabitationCareDetail 蹂꾨룄

    怨듬룞?곸냽 ??
      理쒕?吏遺꾩옄媛 ?곸냽二쇳깮 蹂댁쑀?먮줈 媛꾩＜.
      吏遺??숈씪 ??嫄곗＜?? 理쒖뿰?μ옄 ?쒖쑝濡?1??吏??
    """
    death_date: date
    same_household_at_death: bool        # ?щ쭩 ???숈씪?몃? ?щ?
    inherited_as_only_house: bool        # ?곸냽 ?뱀떆 ?곸냽?몄씠 臾댁＜?앹씠?덈뒗吏
    selling_inherited_house: bool        # True: ?곸냽二쇳깮 ?묐룄(寃쎈줈B) / False: ?쇰컲二쇳깮 ?묐룄(寃쎈줈A)
    donor_acquisition_date: Optional[date] = None  # ?쇱긽?띿씤 ?먯랬?앹씪 (寃쎈줈 B ?꾩닔, 寃쎈줈 A 遺덊븘??

    # 怨듬룞?곸냽 ?곸꽭
    is_joint_inheritance: bool = False
    inheritance_share_pct: float = 100.0   # 蹂몄씤 吏遺꾩쑉 (%)
    is_largest_share_holder: bool = True   # 理쒕?吏遺?蹂댁쑀 ?щ?
    is_designated_holder: bool = False     # 吏遺??숈씪 ??吏??蹂댁쑀???щ?

    inherited_holding_years: Optional[float] = None  # ?쇱긽?띿씤 蹂댁쑀湲곌컙 (寃쎈줈 B ?먮룞怨꾩궛??


@dataclass
class LongTermRentalDetail:
    """
    ?κ린?꾨?二쇳깮 媛먮㈃ ?밸? (議고듅踰?짠97??~짠97??).
    ?섎Т?꾨?湲곌컙, ?꾨?猷?利앹븸 ?쒗븳 以?섍? ?듭떖 ?붽굔.
    """
    registration_date: date               # ?꾨??ъ뾽???깅줉??    mandatory_period_years: int           # ?섎Т?꾨?湲곌컙 (4/8/10??
    mandatory_period_fulfilled: bool      # ?섎Т?꾨?湲곌컙 異⑹” ?щ?
    rent_increase_limit_complied: bool    # ?꾨?猷?5% 利앹븸 ?쒗븳 以???щ?


class ResidenceExemptionType(str, Enum):
    """
    嫄곗＜?붽굔(2?? 硫댁젣 ?먮뒗 ?⑥텞 ?밸? ?좏삎.
    ?대떦 ??RAG 荑쇰━??議곕Ц ?ㅼ썙?쒕? 紐낆떆?곸쑝濡??ы븿?댁빞 ??
    """
    SANGSAENG_RENTAL = "?곸깮?꾨?"              # ?뚮졊 짠155?? ??嫄곗＜?붽굔 ?꾨㈃ 硫댁젣

 succeeded in 3948ms:
"""
L3 ??Query Enrichment

danger_flags ???꾨찓???ㅼ썙??二쇱엯.
踰≫꽣 寃?됱? "?낅젰 ?띿뒪?몄? ?좎궗??議곕Ц"??李얠쑝誘濡?
?ㅼ썙?쒓? ?놁쑝硫??대떦 議곕Ц??寃??寃곌낵?먯꽌 ?꾨씫??

?? "?댁썡怨쇱꽭" ?ㅼ썙???놁씠 "諛곗슦??利앹뿬 二쇳깮 ?묐룄" 寃??    ??짠97?? ????쇰컲 ?묐룄??議곕Ц留?寃?됰맖 ???由?痍⑤뱷媛???곸슜
"""

from __future__ import annotations

import re
from typing import Dict, List

from .query_input import RAGQueryInput


# danger_flag ???쎌엯???꾨찓???ㅼ썙??+ 議곕Ц 踰덊샇
# ?ㅼ썙?쒓? 荑쇰━???덉뼱??踰≫꽣 寃?됱씠 ?대떦 議곕Ц 泥?겕瑜?李얠븘??DANGER_KEYWORD_MAP: Dict[str, str] = {
    "?댁썡怨쇱꽭": "諛곗슦??吏곴퀎議대퉬??利앹뿬 ?댁썡怨쇱꽭 ?뚮뱷?몃쾿 ??7議곗쓽2 ?먯랬?앷???,
    "?댁썡怨쇱꽭_5?꾩씠??: "利앹뿬 ??5???대궡 ?묐룄 ?댁썡怨쇱꽭 ?뚮뱷?몃쾿 ??7議곗쓽2",
    "?댁썡怨쇱꽭_10?꾩씠??: "利앹뿬 ??10???대궡 ?묐룄 ?댁썡怨쇱꽭 ?뚮뱷?몃쾿 ??7議곗쓽2 2023??媛쒖젙",
    "怨좉?二쇳깮_誘명솗??: "怨좉?二쇳깮 12??珥덇낵 ?κ린蹂댁쑀?밸퀎怨듭젣 ?? ?뚮뱷?몃쾿 ??5議?,
    "怨좉?二쇳깮": "怨좉?二쇳깮 12???κ린蹂댁쑀?밸퀎怨듭젣 ?? ?뚮뱷?몃쾿 ??5議??쒗뻾????56議곗쓽2",
    "?곸냽二쇳깮": "?곸냽二쇳깮 ?뚮뱷?몃쾿 ?쒗뻾????55議??쇱긽?띿씤 蹂댁쑀湲곌컙 ?⑹궛",
    "?곸냽二쇳깮_?먯껜?묐룄": "?곸냽二쇳깮 ?먯껜?묐룄 ?쇱긽?띿씤 蹂댁쑀湲곌컙 ?⑹궛 ?뚮졊 ??55議?????,
    "?쇱떆??二쇳깮": "?쇱떆??2二쇳깮 醫낆쟾二쇳깮 3???대궡 ?묐룄 ?뚮뱷?몃쾿 ?쒗뻾????55議?????,
    "議고빀?먯엯二쇨텒": "議고빀?먯엯二쇨텒 愿由ъ쿂遺꾧퀎?띿씤媛 蹂댁쑀湲곌컙 ?뚮뱷?몃쾿 ?쒗뻾????56議곗쓽2",
    "遺꾩뼇沅?: "遺꾩뼇沅??뚮뱷?몃쾿 ??8議?二쇳깮 ???곗엯",
    "遺꾩뼇沅?2021??二쇳깮?섎??곗엯": "2020???댁쟾 痍⑤뱷 遺꾩뼇沅?二쇳깮 ??誘몄궛???뚮뱷?몃쾿 遺移?,
    "遺꾩뼇沅?2021??二쇳깮?섏궛??: "2021???댄썑 痍⑤뱷 遺꾩뼇沅?二쇳깮 ???곗엯 ?뚮뱷?몃쾿 ??8議?????,
    "遺꾩뼇沅?湲곗?遺덈챸": "遺꾩뼇沅?痍⑤뱷??2021??湲곗? 二쇳깮 ???곗엯 ?щ? ?뚮뱷?몃쾿 ??8議?,
    "?곸깮?꾨?": "?곸깮?꾨?二쇳깮 嫄곗＜?붽굔 硫댁젣 ?뚮뱷?몃쾿 ?쒗뻾????55議곗쓽3",
    "怨듬룞紐낆쓽": "怨듬룞紐낆쓽 吏遺??묐룄 鍮꾩쑉 ?뚮뱷?몃쾿 ??8議?????,
    "鍮꾧굅二쇱옄": "鍮꾧굅二쇱옄 1?몃? 1二쇳깮 鍮꾧낵??諛곗젣 ?뚮뱷?몃쾿 ??21議?,
    "鍮꾧굅二쇱옄_?댁쇅?댁＜2?꾩씠?댁뼇?꾧???: "?댁쇅?댁＜ 2???대궡 ?묐룄 鍮꾧낵???뚮뱷?몃쾿 ?쒗뻾????54議?????????,
    "?ш굔異뺤옱媛쒕컻?먯“?⑹썝": "?먯“?⑹썝 ?ш굔異?蹂댁쑀湲곌컙 愿由ъ쿂遺??뚮뱷?몃쾿 ?쒗뻾????56議곗쓽2",
    "?ш굔異뺤옱媛쒕컻?밴퀎議고빀??: "?밴퀎議고빀???낆＜沅?痍⑤뱷??蹂댁쑀湲곌컙 ?뚮뱷?몃쾿 ?쒗뻾????56議곗쓽2",
    "?숆굅遊됱뼇?⑷?": "?숆굅遊됱뼇 ?⑷? 10???대궡 鍮꾧낵???뚮뱷?몃쾿 ?쒗뻾????55議?????,
    "?섏슜_compulsory_嫄곗＜?붽굔硫댁젣": "媛뺤젣?섏슜 嫄곗＜?붽굔 硫댁젣 ?뚮뱷?몃쾿 ?쒗뻾????54議??????⑥꽌",
    "?섏슜_negotiated_嫄곗＜?붽굔硫댁젣": "?묒쓽痍⑤뱷 嫄곗＜?붽굔 硫댁젣 ?뚮뱷?몃쾿 ?쒗뻾????54議??????⑥꽌",
}


# raw ?띿뒪?몄뿉??danger_flag瑜??먮룞 ?먯??섎뒗 ?⑦꽩 紐⑸줉.
# eval.py / mcp_server.py ??L2 ?⑺듃泥댄겕 ?놁씠 ?띿뒪?몃쭔 ?덈뒗 寃쎌슦???ъ슜.
RAW_TRIGGER_PATTERNS: List[tuple] = [
    (re.compile(r"諛곗슦??吏곴퀎議대퉬??利앹뿬"), "?댁썡怨쇱꽭"),
    (re.compile(r"?댁썡怨쇱꽭"), "?댁썡怨쇱꽭"),
    (re.compile(r"?곸냽"), "?곸냽二쇳깮"),
    (re.compile(r"?쇱떆??{0,4}2二쇳깮|醫낆쟾二쇳깮"), "?쇱떆??二쇳깮"),
    (re.compile(r"怨좉?二쇳깮|12??), "怨좉?二쇳깮"),
    (re.compile(r"?곸깮?꾨?"), "?곸깮?꾨?"),
    (re.compile(r"遺꾩뼇沅?), "遺꾩뼇沅?),
    (re.compile(r"議고빀?먯엯二쇨텒|?낆＜沅?), "議고빀?먯엯二쇨텒"),
    (re.compile(r"鍮꾧굅二쇱옄|?댁쇅?댁＜"), "鍮꾧굅二쇱옄"),
    (re.compile(r"?숆굅遊됱뼇|?⑷?"), "?숆굅遊됱뼇?⑷?"),
    (re.compile(r"?섏슜|媛뺤젣痍⑤뱷|?묒쓽痍⑤뱷"), "?섏슜_compulsory_嫄곗＜?붽굔硫댁젣"),
    (re.compile(r"?ш굔異??ш컻諛?), "?ш굔異뺤옱媛쒕컻?먯“?⑹썝"),
    (re.compile(r"怨듬룞紐낆쓽|吏遺?), "怨듬룞紐낆쓽"),
]


def detect_flags_from_text(query: str) -> List[str]:
    """raw ?띿뒪?몄뿉??danger_flags瑜??먮룞 ?먯??쒕떎."""
    seen: set[str] = set()
    flags: List[str] = []
    for pattern, flag in RAW_TRIGGER_PATTERNS:
        if pattern.search(query) and flag not in seen:
            flags.append(flag)
            seen.add(flag)
    return flags


def enrich_raw_query_text(query: str) -> str:
    """
    raw ?띿뒪???⑦꽩 留ㅼ묶?쇰줈 ?꾨찓???ㅼ썙?쒕? 二쇱엯?쒕떎.
    L2 ?⑺듃泥댄겕 ?놁씠 ?띿뒪?몃쭔 ?덉쓣 ??MCP, eval) ?ъ슜.
    """
    flags = detect_flags_from_text(query)
    return enrich_query(query, flags)


def enrich_query(base_query: str, danger_flags: List[str]) -> str:
    """
    RAG 寃??荑쇰━??danger_flags????묓븯???꾨찓???ㅼ썙?쒕? 二쇱엯.

    Args:
        base_query: fact_vector.to_text() ??湲곕낯 荑쇰━ ?띿뒪??        danger_flags: FactCheckResult.danger_flags

    Returns:
        ?ㅼ썙?쒓? 二쇱엯??媛뺥솕 荑쇰━ ?띿뒪??    """
    injected: List[str] = []
    seen: set[str] = set()

    for flag in danger_flags:
        kw = DANGER_KEYWORD_MAP.get(flag)
        if kw and kw not in seen:
            injected.append(kw)
            seen.add(kw)

    if not injected:
        return base_query

    enriched = base_query + "\n[寃??蹂닿컯] " + " | ".join(injected)
    return enriched


def build_rag_query(query_input: RAGQueryInput, danger_flags: List[str]) -> str:
    """
    RAGQueryInput ??理쒖쥌 RAG 寃???띿뒪??
    fact_vector.to_text()瑜?base濡?danger_flags ?ㅼ썙?쒕? 異붽?.
    """
    base = query_input.fact_vector.to_text()
    return enrich_query(base, danger_flags)

 succeeded in 3960ms:
"""
寃???덉쭏 遺꾩꽍湲?+ DANGER_KEYWORD_MAP ?먮룞 媛쒖꽑 ?쒖븞

?ㅽ봽?쇱씤 ?쇰뱶諛?猷⑦봽 (RLVR):
  eval 寃곌낵 + gold_chunk_ids ??danger_flag蹂?recall 吏묎퀎
  ???쏀븳 flag 媛먯? ???꾨씫 議곕Ц?먯꽌 ?ㅼ썙???꾨낫 ?먮룞 異붿텧
  ??DANGER_KEYWORD_MAP ?낅뜲?댄듃 ?쒖븞 ?앹꽦

Reward ?좏샇:
  - citation_precision : L5 phantom 寃????human ?놁씠 ?먮룞 痢≪젙
  - recall@k           : gold_chunk_ids 湲곕컲 ??由щ럭??1??吏?????먮룞 諛섎났
  - verdict_match      : expected_verdict ?쇱튂 ?щ?
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.domain.query_enrichment import DANGER_KEYWORD_MAP, detect_flags_from_text
from src.eval.feedback import compute_retrieval_metrics

REPORT_DIR = Path("data/eval_results")

# ?꾨씫 議곕Ц ?띿뒪?몄뿉??異붿텧??踰뺣졊 ?⑦꽩
_ARTICLE_RE = re.compile(r"??d+議??:??d+)?")
_LAW_RE = re.compile(r"(?:?뚮뱷?몃쾿|議곗꽭?밸??쒗븳踰?(?:\s*?쒗뻾??\s*?쒗뻾洹쒖튃)?")
_DOMAIN_TERMS = [
    "?댁썡怨쇱꽭", "?κ린蹂댁쑀?밸퀎怨듭젣", "1?몃?1二쇳깮", "怨좉?二쇳깮", "?쇱떆??二쇳깮",
    "?곸냽二쇳깮", "?곸깮?꾨?", "遺꾩뼇沅?, "議고빀?먯엯二쇨텒", "鍮꾧굅二쇱옄", "?숆굅遊됱뼇",
    "愿由ъ쿂遺?, "?먯랬?앷???, "嫄곗＜?붽굔", "蹂댁쑀湲곌컙", "以묎낵?몄쑉", "?⑷?",
    "?쇱긽?띿씤", "諛곗슦??, "吏곴퀎議대퉬??, "利앹뿬", "?섏슜", "?묒쓽痍⑤뱷",
]


# ?? ?대? ?좏떥 ??????????????????????????????????????????????????????????????????

def _extract_legal_keywords(text: str) -> list[str]:
    """踰뺣졊 ?띿뒪?몄뿉??議곕Ц踰덊샇쨌踰뺣졊紐끒룸룄硫붿씤 ?⑹뼱瑜?異붿텧?쒕떎."""
    found: list[str] = []
    found += _ARTICLE_RE.findall(text)
    found += _LAW_RE.findall(text)
    found += [t for t in _DOMAIN_TERMS if t in text]
    return list(dict.fromkeys(found))  # ?쒖꽌 ?좎? 以묐났 ?쒓굅


def _fetch_chunk_texts(chunk_ids: list[str]) -> dict[str, str]:
    """Pinecone?먯꽌 chunk_id ??full_text 留?諛섑솚. ?ㅽ뙣 ??鍮?dict."""
    if not chunk_ids:
        return {}
    try:
        from src.infra.pinecone_client import get_pinecone_index, PINECONE_NAMESPACE
        index = get_pinecone_index()
        res = index.fetch(ids=chunk_ids, namespace=PINECONE_NAMESPACE)
        vectors = (
            res.get("vectors", {}) if isinstance(res, dict)
            else getattr(res, "vectors", {})
        )
        result = {}
        for cid, vec in vectors.items():
            meta = (
                vec.get("metadata", {}) if isinstance(vec, dict)
                else getattr(vec, "metadata", {})
            )
            result[cid] = (meta or {}).get("full_text", "")
        return result
    except Exception:
        return {}


def _auto_flags(case: dict) -> list[str]:
    """
    golden case??danger_flags ?꾨뱶媛 ?놁쑝硫?吏덈Ц ?띿뒪?몄뿉???먮룞 ?먯??쒕떎.
    """
    flags = case.get("danger_flags")
    if flags is not None:
        return flags
    question = case.get("question", "") + " " + case.get("description", "")
    return detect_flags_from_text(question)


# ?? 遺꾩꽍 ?⑥닔 ??????????????????????????????????????????????????????????????????

def analyze_flag_recall(
    golden_cases: list[dict],
    eval_results: list[dict],
) -> dict[str, dict]:
    """
    danger_flag蹂?recall@k, verdict_match, citation_precision??吏묎퀎?쒕떎.

    Returns:
        {flag: {avg_recall, avg_verdict_match, avg_citation_precision, count, cases}}
    """
    stats: dict[str, dict] = defaultdict(lambda: {
        "recall_sum": 0.0,
        "verdict_sum": 0.0,
        "cit_sum": 0.0,
        "count": 0,
        "cases": [],
    })

    result_by_id = {r["case_id"]: r for r in eval_results}

    for case in golden_cases:
        case_id = case.get("id", "")
        flags = _auto_flags(case)
        result = result_by_id.get(case_id)
        if not result or not flags:
            continue

        recall = result.get("retrieval_metrics", {}).get("recall_at_k") or 0.0
        verdict = float(result.get("verdict_match") or 0)
        cit = result.get("citation_precision", 1.0)

        for flag in flags:
            s = stats[flag]
            s["recall_sum"] += recall
            s["verdict_sum"] += verdict
            s["cit_sum"] += cit
            s["count"] += 1
            s["cases"].append(case_id)

    out: dict[str, dict] = {}
    for flag, s in stats.items():
        n = s["count"]
        out[flag] = {
            "avg_recall": round(s["recall_sum"] / n, 4) if n else 0.0,
            "avg_verdict_match": round(s["verdict_sum"] / n, 4) if n else 0.0,
            "avg_citation_precision": round(s["cit_sum"] / n, 4) if n else 0.0,
            "count": n,
            "cases": s["cases"],
        }
    return out


def discover_missing_keywords(
    golden_cases: list[dict],
    eval_results: list[dict],
    recall_threshold: float = 0.6,
) -> dict[str, list[str]]:
    """
    recall????? flag???꾨씫 議곕Ц ?띿뒪?몄뿉???ㅼ썙???꾨낫瑜?異붿텧?쒕떎.

    gold_chunk_ids媛 鍮꾩뼱?덈뒗 耳?댁뒪??嫄대꼫?대떎.
    Returns:
        {flag: [keyword_candidate, ...]}
    """
    flag_recall = analyze_flag_recall(golden_cases, eval_results)
    result_by_id = {r["case_id"]: r for r in eval_results}

    # recall ??? flag??????꾨씫 chunk ?섏쭛
    flag_missing: dict[str, set[str]] = defaultdict(set)
    for case in golden_cases:
        case_id = case.get("id", "")
        flags = _auto_flags(case)
        gold_ids = set(case.get("gold_chunk_ids") or [])
        if not gold_ids:
            continue
        result = result_by_id.get(case_id)
        if not result:
            continue

        retrieved = set(result.get("retrieved_chunk_ids") or [])
        missing = gold_ids - retrieved

        for flag in flags:
            if flag_recall.get(flag, {}).get("avg_recall", 1.0) < recall_threshold:
                flag_missing[flag].update(missing)

    if not flag_missing:
        return {}

    # Pinecone?먯꽌 ?꾨씫 chunk ?띿뒪??fetch
    all_missing = set().union(*flag_missing.values())
    chunk_texts = _fetch_chunk_texts(list(all_missing))

    # flag蹂??ㅼ썙???꾨낫 異붿텧 (?꾩옱 map???녿뒗 寃껊쭔)
    suggestions: dict[str, list[str]] = {}
    for flag, missing_ids in flag_missing.items():
        kws: list[str] = []
        for cid in missing_ids:
            text = chunk_texts.get(cid, "")
            if text:
                kws.extend(_extract_legal_keywords(text))

        current_kw = DANGER_KEYWORD_MAP.get(flag, "")
        new_kws = [k for k in dict.fromkeys(kws) if k not in current_kw]
        if new_kws:
            suggestions[flag] = new_kws

    return suggestions


def suggest_map_updates(
    golden_cases: list[dict],
    eval_results: list[dict],
    recall_threshold: float = 0.6,
) -> dict[str, dict]:
    """
    DANGER_KEYWORD_MAP ?낅뜲?댄듃 ?쒖븞???앹꽦?쒕떎.

    Returns:
        {flag: {current, suggested_additions, avg_recall, avg_verdict_match, case_count}}
    """
    flag_stats = analyze_flag_recall(golden_cases, eval_results)
    kw_suggestions = discover_missing_keywords(golden_cases, eval_results, recall_threshold)

    updates: dict[str, dict] = {}
    for flag, stats in flag_stats.items():
        # recall ?먮뒗 verdict_match媛 threshold 誘몃떖??flag留??쒖븞
        if stats["avg_recall"] < recall_threshold or stats["avg_verdict_match"] < recall_threshold:
            updates[flag] = {
                "current_keyword": DANGER_KEYWORD_MAP.get(flag, "(?놁쓬)"),
                "suggested_additions": kw_suggestions.get(flag, []),
                "avg_recall": stats["avg_recall"],
                "avg_verdict_match": stats["avg_verdict_match"],
                "avg_citation_precision": stats["avg_citation_precision"],
                "case_count": stats["count"],
                "note": (
                    "gold_chunk_ids 誘몄엯????由щ럭?닿? ?뺣떟 chunk瑜?吏?뺥븯硫??ㅼ썙???꾨낫 ?먮룞 異붿텧"
                    if not kw_suggestions.get(flag)
                    else ""
                ),
            }
    return updates


# ?? 硫붿씤 吏꾩엯??????????????????????????????????????????????????????????????????

def run_analysis(
    golden_cases: list[dict],
    eval_results: list[dict],
    recall_threshold: float = 0.6,
    save_report: bool = True,
) -> dict:
    """
    ?꾩껜 遺꾩꽍 ?ㅽ뻾:
      1. danger_flag蹂?recall / verdict_match / citation_precision 吏묎퀎
      2. ?쏀븳 flag ?ㅼ썙??蹂닿컯 ?쒖븞
      3. 由ы룷?????
    golden_cases??danger_flags ?꾨뱶媛 ?놁쑝硫?吏덈Ц ?띿뒪?몄뿉???먮룞 ?먯?.
    gold_chunk_ids媛 ?놁쑝硫?recall 遺꾩꽍? 嫄대꼫?곌퀬 verdict/citation留?吏묎퀎.
    """
    flag_stats = analyze_flag_recall(golden_cases, eval_results)
    updates = suggest_map_updates(golden_cases, eval_results, recall_threshold)

    has_gold = any(case.get("gold_chunk_ids") for case in golden_cases)

    # ?? 異쒕젰 ??????????????????????????????????????????????????????????????????

    print("\n" + "=" * 60)
    print("  danger_flag蹂?寃???덉쭏 遺꾩꽍")
    print("=" * 60)

    if not flag_stats:
        print("  (遺꾩꽍 ????놁쓬 ??golden_cases??danger_flags ?먮뒗 吏덈Ц ?띿뒪???꾩슂)")
    else:
        if not has_gold:
            print("  ??gold_chunk_ids 誘몄엯????recall@k??N/A, verdict/citation留?吏묎퀎??)
            print("    由щ럭?닿? gold_chunk_ids瑜?梨꾩슦硫?recall + ?ㅼ썙??諛쒓껄???쒖꽦?붾맗?덈떎.\n")

        header = f"  {'flag':<40} {'recall':>7} {'verdict':>8} {'cit_prec':>9} {'n':>4}"
        print(header)
        print("  " + "-" * 72)
        for flag, s in sorted(flag_stats.items(), key=lambda x: x[1]["avg_recall"]):
            recall_str = f"{s['avg_recall']:.2f}" if has_gold else "  N/A"
            warn = " ?? if (
                (has_gold and s["avg_recall"] < recall_threshold)
                or s["avg_verdict_match"] < recall_threshold
            ) else ""
            print(
                f"  {flag:<40} {recall_str:>7} "
                f"{s['avg_verdict_match']:>8.2f} "
                f"{s['avg_citation_precision']:>9.2f} "
                f"{s['count']:>4}{warn}"
            )

    print("\n" + "=" * 60)
    print("  DANGER_KEYWORD_MAP ?낅뜲?댄듃 ?쒖븞")
    print("=" * 60)

    if not updates:
        print("  (threshold 誘몃떖 flag ?놁쓬 ??紐⑤몢 ?묓샇)")
    else:
        for flag, info in updates.items():
            print(f"\n  [{flag}]  recall={info['avg_recall']}  verdict={info['avg_verdict_match']}")
            print(f"    ?꾩옱 ?ㅼ썙?? {info['current_keyword']}")
            additions = info["suggested_additions"]
            if additions:
                print(f"    異붽? ?꾨낫:   {' | '.join(additions)}")
            elif info.get("note"):
                print(f"    {info['note']}")

    report = {
        "recall_threshold": recall_threshold,
        "has_gold_chunks": has_gold,
        "flag_stats": {
            k: {kk: vv for kk, vv in v.items() if kk != "cases"}
            for k, v in flag_stats.items()
        },
        "keyword_update_suggestions": {
            k: {kk: vv for kk, vv in v.items() if kk != "note"}
            for k, v in updates.items()
        },
    }

    if save_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = REPORT_DIR / f"retrieval_analysis_{ts}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  由ы룷????? {path}")

    return report

 succeeded in 3963ms:
"""
L2 ??Fact Completeness Check

LLM ?몄텧 ?꾩뿉 ?ㅽ뻾. 寃곗젙??洹쒖튃?쇰줈 ?ъ떎愿怨??꾩쟾?깆쓣 寃??
?щ━?곗뺄 ??ぉ??鍮좎?硫?LLM???몄텧?섏? ?딄퀬 議곌린 諛섑솚.

?ㅺ퀎 ?먯튃:
- RAGQueryInput(typed schema)??諛쏆븘 semantic completeness瑜?寃??- 臾몄옄??鍮꾧탳 ?놁쓬 ??date 媛앹껜? enum 吏곸젒 鍮꾧탳
- "紐⑤Ⅴ硫??꾪뿕??履쎌쑝濡? ?먯튃: 遺덊솗????danger_flag 異붽?, can_proceed=False
- missing_facts??LLM ?꾨＼?꾪듃?먮룄 ?꾨떖??"???뺣낫媛 ?놁뼱??遺덊솗?ㅽ빀?덈떎"瑜??덈궡
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from .query_input import (
    AcquisitionReason,
    PropertyType,
    RAGQueryInput,
)


@dataclass
class MissingFact:
    """
    ?꾨씫???ъ떎愿怨?1嫄?
    is_critical=True?대㈃ ????ぉ ?놁씠??LLM ?몄텧??李⑤떒.
    """
    field_name: str        # ?꾨씫 ?꾨뱶紐?(?ъ슜?먯뿉寃??ъ쭏臾몄슜)
    reason: str            # ???꾩슂?쒖? ???곷떞 ?붾㈃???몄텧
    article_hint: str      # 愿??議곕Ц (LLM ?꾨＼?꾪듃???쎌엯)
    is_critical: bool = True


@dataclass
class FactCheckResult:
    can_proceed: bool                         # False硫?LLM ?몄텧 李⑤떒
    missing_facts: List[MissingFact] = field(default_factory=list)
    danger_flags: List[str] = field(default_factory=list)  # L3 ?ㅼ썙??二쇱엯??    forced_verdict: Optional[str] = None     # "needs_verification" ??
    @property
    def critical_missing(self) -> List[MissingFact]:
        return [f for f in self.missing_facts if f.is_critical]

    def missing_fact_texts(self) -> List[str]:
        """LLM ?꾨＼?꾪듃 ?쎌엯???띿뒪??紐⑸줉"""
        return [f"{f.field_name}: {f.reason}" for f in self.missing_facts]


def check_facts(query: RAGQueryInput) -> FactCheckResult:
    """
    RAGQueryInput??諛쏆븘 ?ъ떎愿怨??꾩쟾??寃??
    ?쒖꽌媛 以묒슂: ?щ━?곗뺄 ?쒖꽌?濡?泥댄겕.
    """
    missing: List[MissingFact] = []
    danger: List[str] = []
    fv = query.fact_vector
    sc = fv.special_cases
    db = query.date_bundle

    # ?? 1. 怨좉?二쇳깮 ?먮떒 遺덇? (紐⑤뱺 耳?댁뒪???곹뼢) ??????????????????????
    if fv.transfer_price is None:
        missing.append(MissingFact(
            field_name="transfer_price",
            reason="?묐룄媛??誘명솗????12??珥덇낵 怨좉?二쇳깮 ?щ?瑜??????놁쑝硫?鍮꾧낵??踰붿쐞 怨꾩궛 遺덇?",
            article_hint="?뚮뱷?몃쾿 짠89???? ?쒗뻾??짠156??",
            is_critical=True,
        ))
        danger.append("怨좉?二쇳깮_誘명솗??)
    elif fv.is_high_value_house:
        danger.append("怨좉?二쇳깮")  # 12??珥덇낵 ?뺤씤 ??L3?먯꽌 짠89/짠156?? ?ㅼ썙??二쇱엯

    # ?? 2. ?댁썡怨쇱꽭 (媛???꾪뿕: 議곗슜???由?寃곌낵) ???????????????????????
    is_gift_acquisition = fv.acquisition_reason in (
        AcquisitionReason.GIFT, AcquisitionReason.BURDEN_GIFT
    )
    if is_gift_acquisition:
        danger.append("?댁썡怨쇱꽭")
        rt = sc.rollover_taxation
        if rt is None or not rt.is_gift_from_spouse_or_lineal:
            # 利앹뿬 痍⑤뱷?몃뜲 諛곗슦??吏곴퀎 ?щ? 誘명솗?????댁썡怨쇱꽭 ?곸슜 媛?μ꽦 ?덉쓬
            missing.append(MissingFact(
                field_name="is_gift_from_spouse_or_lineal",
                reason="利앹뿬?먭? 諛곗슦??吏곴퀎議대퉬?띿씤吏 ?뺤씤 ?꾩슂 ???대떦 ???댁썡怨쇱꽭 ?곸슜?쇰줈 痍⑤뱷媛?≤룹랬?앹씪 湲곗궛?먯씠 諛붾?,
                article_hint="?뚮뱷?몃쾿 짠97??",
                is_critical=True,
            ))
        elif rt.is_gift_from_spouse_or_lineal:
            # 諛곗슦??吏곴퀎 利앹뿬 ?뺤씤 ???댁썡怨쇱꽭 湲곌컙 ?댁씤吏 泥댄겕
            years_elapsed = _years_between(rt.gift_date, db.transfer_date)
            if years_elapsed < rt.iota_period_years:
                danger.append(f"?댁썡怨쇱꽭_{rt.iota_period_years}?꾩씠??)
                if not rt.original_donor_acquisition_date or rt.original_donor_acquisition_price == 0:
                    missing.append(MissingFact(
                        field_name="original_donor_acquisition_date / original_donor_acquisition_price",
                        reason=(
                            f"諛곗슦??吏곴퀎議대퉬??利앹뿬 ??{rt.iota_period_years}???대궡 ?묐룄 ??"
                            "?댁썡怨쇱꽭 ?곸슜 ??利앹뿬???먯랬?앹씪怨??먯랬?앷??≪쑝濡?怨꾩궛?? "
                            "???뺣낫 ?놁씠??痍⑤뱷媛??怨꾩궛 遺덇?"
                        ),
                        article_hint="?뚮뱷?몃쾿 짠97??",
                        is_critical=True,
                    ))

    # ?? 3. ?곸냽二쇳깮 ???쇱긽?띿씤 ?먯랬?앹씪 ?놁쓬 ????????????????????????????
    # 寃쎈줈 A(?쇰컲二쇳깮 ?묐룄) ?ы븿 ??acquisition_reason??PURCHASE?щ룄 sc.is_inherited_house濡?媛먯?
    if fv.acquisition_reason == AcquisitionReason.INHERITANCE or sc.is_inherited_house:
        danger.append("?곸냽二쇳깮")
        inh = sc.inheritance
        if inh is None:
            missing.append(MissingFact(
                field_name="death_date",
                reason="?곸냽媛쒖떆???щ쭩?? ?꾩슂 ??5???대궡 ?곸냽二쇳깮 二쇳깮 ???쒖쇅 湲곌컙 湲곗궛??,
                article_hint="?뚮뱷?몃쾿 ?쒗뻾??짠155??,
                is_critical=True,
            ))
        else:
            # InheritanceDetail???덈뜑?쇰룄 寃쎈줈 B(?곸냽二쇳깮 ?먯껜 ?묐룄) ???쇱긽?띿씤 ?먯랬?앹씪 ?꾩닔
            if inh.selling_inherited_house:
                danger.append("?곸냽二쇳깮_?먯껜?묐룄")
                donor_acq = getattr(inh, "donor_acquisition_date", None)
                if donor_acq is None:
                    missing.append(MissingFact(
                        field_name="donor_acquisition_date",
                        reason="?곸냽二쇳깮 ?먯껜 ?묐룄 ???쇱긽?띿씤 ?먯랬?앹씪 ?꾩슂 ??蹂댁쑀湲곌컙 ?⑹궛 ?щ? ?먮떒 遺덇?",
                        article_hint="?뚮뱷?몃쾿 ?쒗뻾??짠155??,
                        is_critical=True,
                    ))

    # ?? 4. ?쇱떆??2二쇳깮 ???좉퇋二쇳깮 痍⑤뱷???놁쓬 ??????????????????????????
    if sc.is_temporary_two_house:
        danger.append("?쇱떆??二쇳깮")
        td = sc.temp_two_house
        if td is None or not getattr(td, "new_acquisition_date", None):
            missing.append(MissingFact(
                field_name="temp_two_house.new_acquisition_date",
                reason="?좉퇋二쇳깮 痍⑤뱷???꾩슂 ??醫낆쟾二쇳깮 3???대궡 ?묐룄 湲고븳 怨꾩궛 遺덇?",
                article_hint="?뚮뱷?몃쾿 ?쒗뻾??짠155??,
                is_critical=True,
            ))

    # ?? 5. ?ш굔異??ш컻諛???愿由ъ쿂遺꾧퀎?띿씤媛???놁쓬 ??????????????????????
    if fv.property_type == PropertyType.ASSOCIATION_RIGHT:
        danger.append("議고빀?먯엯二쇨텒")
        rc = sc.reconstruction
        if rc is None:
            missing.append(MissingFact(
                field_name="management_disposal_date",
                reason="愿由ъ쿂遺꾧퀎?띿씤媛???꾩슂 ??議고빀?먯엯二쇨텒 蹂댁쑀湲곌컙 湲곗궛?? 1?몃?1二쇳깮 ?밸? ?먮떒 遺덇?",
                article_hint="?뚮뱷?몃쾿 ?쒗뻾??짠156??",
                is_critical=True,
            ))
        elif not rc.original_house_acquisition_date:
            missing.append(MissingFact(
                field_name="reconstruction.original_house_acquisition_date",
                reason="醫낆쟾二쇳깮 痍⑤뱷???꾩슂 ???먯“?⑹썝 蹂댁쑀湲곌컙 湲곗궛??,
                article_hint="?뚮뱷?몃쾿 ?쒗뻾??짠156????,
                is_critical=True,
            ))

    # ?? 6. 遺꾩뼇沅???2021??湲곗? 二쇳깮 ???곗엯 ?щ? ???????????????????????
    if fv.property_type == PropertyType.SUBSCRIPTION_RIGHT:
        danger.append("遺꾩뼇沅?)
        before = sc.bunyang_acquired_before_2021
        if before is None:
            # 痍⑤뱷???덉쑝硫??먮룞 ?먮떒?섏뼱???섎뒗??None?대㈃ ?곗씠???꾨씫
            missing.append(MissingFact(
                field_name="acquisition_date (遺꾩뼇沅?",
                reason="遺꾩뼇沅?痍⑤뱷???꾩슂 ??2021.01.01 ?댄썑 痍⑤뱷遺꾨쭔 二쇳깮 ?섏뿉 ?곗엯??,
                article_hint="?뚮뱷?몃쾿 짠88??,
                is_critical=False,  # 二쇱쓽 ?섏? (鍮꾧낵??怨꾩궛???곹뼢)
            ))
            danger.append("遺꾩뼇沅?湲곗?遺덈챸")
        elif before:
            danger.append("遺꾩뼇沅?2021??二쇳깮?섎??곗엯")
        else:
            danger.append("遺꾩뼇沅?2021??二쇳깮?섏궛??)

    # ?? 7. 議곗젙??곸????쒖젏 誘몃텇由?寃쎄퀬 ????????????????????????????????
    # (?대? 遺꾨━?섏뼱 ?덉쑝硫?pass ??湲곗〈 ?ㅺ퀎?먯꽌 泥섎━??
    # ????None??寃쎌슦留?寃쎄퀬
    if not fv.adjustment_area_at_acquisition and not fv.adjustment_area_at_transfer:
        # ????False???섎룄 ?덉쑝誘濡?None???꾨땶 寃쎌슦???뺤긽
        pass  # ?ㅼ젣濡쒕뒗 DB?먯꽌 ??긽 怨꾩궛?섎?濡?異붽? 泥댄겕 遺덊븘??
    # ?? 8. ?곸깮?꾨? ??議곗젙??곸????щ? 誘명솗????????????????????????????
    if sc.sangsaeng_rental and sc.sangsaeng_rental.residence_requirement_waived:
        danger.append("?곸깮?꾨?")
        if not fv.adjustment_area_at_transfer:
            # ?곸깮?꾨???議곗젙??곸???씠?댁빞 嫄곗＜?붽굔 硫댁젣 ?섎?媛 ?덉쓬
            # 鍮꾩“?뺤???씠硫??먮옒 嫄곗＜?붽굔 ?놁쓬 ???곸깮?꾨? ?곸슜 ?섎? ?놁쓬
            missing.append(MissingFact(
                field_name="adjustment_area_at_transfer",
                reason="?곸깮?꾨? 嫄곗＜?붽굔 硫댁젣??議곗젙??곸???二쇳깮?먮쭔 ?곸슜 ??鍮꾩“?뺤???씠硫??먮옒 嫄곗＜?붽굔 ?놁쓬",
                article_hint="?뚮뱷?몃쾿 ?쒗뻾??짠155??",
                is_critical=False,
            ))

    # ?? 9. 怨듬룞紐낆쓽 ??吏遺??뺣낫 ?놁쓬 ????????????????????????????????????
    if fv.joint_ownership_yn:
        danger.append("怨듬룞紐낆쓽")
        # joint_owner_info??FactVector???녾퀬 user_property?먯꽌 ?ㅻ?濡?        # ?ш린?쒕뒗 danger flag留?異붽?

    # ?? 寃곗젙 ?????????????????????????????????????????????????????????????
    critical_count = sum(1 for m in missing if m.is_critical)
    can_proceed = critical_count == 0

    return FactCheckResult(
        can_proceed=can_proceed,
        missing_facts=missing,
        danger_flags=danger,
        forced_verdict="needs_verification" if not can_proceed else None,
    )


def _years_between(earlier: date, later: date) -> float:
    """???좎쭨 ?ъ씠 寃쎄낵 ?곗닔. 遺덊솗????0 諛섑솚(?꾪뿕??履쎌쑝濡??먮떒?섏? ?딆쓬 ???몄텧遺?먯꽌 泥섎━)."""
    try:
        return (later - earlier).days / 365.25

 succeeded in 3975ms:
"""
?꾨쿋??+ Pinecone ?낅줈???ㅽ겕由쏀듃
data/processed/all_chunks.json ??Pinecone Serverless
"""
import os
import json
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "tax-rag")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
UPSTAGE_EMBEDDING_MODEL = os.getenv("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large-passage")

PROCESSED_DIR = Path("data/processed")
BATCH_SIZE = 100  # Pinecone upsert 諛곗튂 ?ш린

# ?? Stage 1 ?꾪꽣 ?쒓퉭 洹쒖튃 ?????????????????????????????????????????????????????
# (law_name, article_number_prefix) ??(entity_scopes, topic_tags)
# ?낆뒪?몃┝ Stage 1 symbolic filter ??entity_scope / tax_type 留ㅼ묶???ъ슜

def _tag_chunk(law_name: str, article_number: str, full_text: str) -> dict:
    """
    議곕Ц ?뺣낫 湲곕컲 洹쒖튃 ?쒓퉭.
    entity_scopes: ["二쇳깮", "遺꾩뼇沅?, "議고빀?먯엯二쇨텒", "?좎?", ...]
    topic_tags: ["1?몃?1二쇳깮鍮꾧낵??, "?κ린蹂댁쑀?밸퀎怨듭젣", ...]
    tax_types: ["transfer"] (?꾩옱 ?섏쭛 ????꾩껜)
    """
    art = article_number.strip().lstrip("??).split("議?)[0].replace("??, ".")
    # "89", "97.2", "154" ?깆쑝濡??뺢퇋??
    entity_scopes: list[str] = []
    topic_tags: list[str] = []

    # ?뚮뱷?몃쾿 / ?뚮뱷?몃쾿 ?쒗뻾????二쇳깮 以묒떖 (遺꾩뼇沅뙿룹엯二쇨텒 ?ы븿)
    if "?뚮뱷?몃쾿" in law_name:
        entity_scopes.append("二쇳깮")

        art_num = article_number.lstrip("??).split("議?)[0]
        if art_num in ("89",):
            topic_tags += ["1?몃?1二쇳깮鍮꾧낵??]
        if art_num in ("95",):
            topic_tags += ["?κ린蹂댁쑀?밸퀎怨듭젣"]
        if art_num in ("97??", "97.2"):
            topic_tags += ["1?몃?1二쇳깮鍮꾧낵??, "?댁썡怨쇱꽭"]
        if art_num in ("104",):
            topic_tags += ["?ㅼ＜?앹쨷怨?, "?몄쑉"]
        if "?쒗뻾?? in law_name:
            if art_num in ("154",):
                topic_tags += ["1?몃?1二쇳깮鍮꾧낵??]
            if art_num in ("155",):
                topic_tags += ["1?몃?1二쇳깮鍮꾧낵??, "?쇱떆??二쇳깮", "?곸냽二쇳깮"]
            if art_num in ("155??",):
                topic_tags += ["1?몃?1二쇳깮鍮꾧낵??, "?곸깮?꾨?"]
                entity_scopes.append("?곸깮?꾨?")
            if art_num in ("156??", "156??"):
                topic_tags += ["遺꾩뼇沅뚯엯二쇨텒"]
                entity_scopes += ["遺꾩뼇沅?, "議고빀?먯엯二쇨텒"]
            if art_num in ("167??0",):
                topic_tags += ["?ㅼ＜?앹쨷怨?]
            if art_num in ("159??",):
                topic_tags += ["?κ린蹂댁쑀?밸퀎怨듭젣"]

    # 議곗꽭?밸??쒗븳踰????꾨?二쇳깮쨌?띿뼱珥뚯＜???밸?
    if "議곗꽭?밸??쒗븳踰? in law_name:
        entity_scopes.append("二쇳깮")
        topic_tags += ["議고듅踰뺢컧硫?]
        art_num = article_number.lstrip("??).split("議?)[0]
        if art_num in ("97??", "97??", "97??"):
            topic_tags += ["?κ린?꾨?二쇳깮"]
        if art_num in ("99??",):
            topic_tags += ["?κ린?꾨?二쇳깮"]

    # 遺移?蹂꾪몴 ?쒓렇
    if "遺移? in full_text[:50] or "遺  移? in full_text[:50]:
        topic_tags.append("遺移숆꼍怨쇱“移?)

    return {
        "entity_scopes": list(dict.fromkeys(entity_scopes)),  # ?쒖꽌 ?좎? 以묐났 ?쒓굅
        "topic_tags": list(dict.fromkeys(topic_tags)),
        "tax_types": ["transfer"],
    }


def _build_embed_client() -> tuple[OpenAI, str, int]:
    """(client, model_name, dimension) 諛섑솚"""
    if UPSTAGE_API_KEY:
        client = OpenAI(
            api_key=UPSTAGE_API_KEY,
            base_url="https://api.upstage.ai/v1",
        )
        return client, UPSTAGE_EMBEDDING_MODEL, 4096
    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        return client, "text-embedding-3-large", 3072
    raise RuntimeError("UPSTAGE_API_KEY ?먮뒗 OPENAI_API_KEY 以??섎굹媛 ?꾩슂?⑸땲??)


def _embed_texts(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    """?띿뒪??諛곗튂瑜??꾨쿋??踰≫꽣濡?蹂??""
    truncated = [t[:3000] for t in texts]
    resp = client.embeddings.create(model=model, input=truncated)
    return [item.embedding for item in resp.data]


def _get_or_create_index(pc: Pinecone, dimension: int):
    """Pinecone ?몃뜳??議고쉶 ?먮뒗 ?앹꽦"""
    existing = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing:
        print(f"?몃뜳???앹꽦 以? {PINECONE_INDEX_NAME} (dim={dimension})")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
        # ?몃뜳??以鍮??湲?        while not pc.describe_index(PINECONE_INDEX_NAME).status["ready"]:
            print("  ?몃뜳??以鍮?以?..")
            time.sleep(3)
        print("  ?몃뜳??以鍮??꾨즺")
    else:
        print(f"湲곗〈 ?몃뜳???ъ슜: {PINECONE_INDEX_NAME}")
    return pc.Index(PINECONE_INDEX_NAME)


def embed_and_upload(chunks_path: Optional[Path] = None) -> int:
    """
    JSON 泥?겕 ?뚯씪???쎌뼱 ?꾨쿋????Pinecone???낅줈??
    諛섑솚媛? upsert??踰≫꽣 ??    """
    if chunks_path is None:
        chunks_path = PROCESSED_DIR / "all_chunks.json"

    if not chunks_path.exists():
        raise FileNotFoundError(
            f"{chunks_path} ?놁쓬 ??癒쇱? `python src/collect.py` ?ㅽ뻾"
        )

    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY媛 ?꾩슂?⑸땲??)

    # 泥?겕 濡쒕뱶
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    print(f"珥?{len(chunks)}媛?泥?겕 濡쒕뱶 ?꾨즺")

    # ?꾨쿋???대씪?댁뼵??    embed_client, embed_model, dimension = _build_embed_client()
    print(f"?꾨쿋??紐⑤뜽: {embed_model} (dim={dimension})")

    # Pinecone ?몃뜳??    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc, dimension)

    # 諛곗튂 ?낅줈??    total_upserted = 0
    batches = [chunks[i : i + BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]

    for batch in tqdm(batches, desc="Pinecone ?낅줈??):
        texts = [c.get("full_text", "") for c in batch]
        try:
            vectors = _embed_texts(embed_client, embed_model, texts)
        except Exception as e:
            print(f"\n?꾨쿋???ㅻ쪟 (諛곗튂 嫄대꼫?): {e}")
            continue

        upsert_payload = []
        for chunk, vec in zip(batch, vectors):
            law_name = chunk.get("law_name", "")
            article_number = chunk.get("article_number", "")
            full_text = chunk.get("full_text", "")
            tags = _tag_chunk(law_name, article_number, full_text)
            metadata = {
                "law_name": law_name,
                "article_number": article_number,
                "article_title": chunk.get("article_title", ""),
                # Pinecone $lte/$gte???レ옄 ????꾩슜 ??YYYYMMDD ?뺤닔濡????                "effective_date": int(chunk["effective_date"]) if chunk.get("effective_date") else 0,
                "expiration_date": int(chunk["expiration_date"]) if chunk.get("expiration_date") else 99991231,
                "version_mst": chunk.get("version_mst", chunk.get("law_mst", "")),
                "law_category": chunk.get("law_category", ""),
                "source": "law.go.kr",
                # Stage 1 symbolic filter???쒓렇 (?낆뒪?몃┝ entity_scope/tax_type 留ㅼ묶)
                "entity_scopes": tags["entity_scopes"],
                "topic_tags": tags["topic_tags"],
                "tax_types": tags["tax_types"],
                # Pinecone 踰≫꽣??硫뷀??곗씠???쒕룄 40KB ??4000?먭퉴吏 ???(reranker + LLM 紐⑤몢 ???꾨뱶 ?ъ슜)
                "full_text": full_text[:4000],
            }
            upsert_payload.append(
                {"id": chunk["id"], "values": vec, "metadata": metadata}
            )

        index.upsert(vectors=upsert_payload, namespace=PINECONE_NAMESPACE)
        total_upserted += len(upsert_payload)
        time.sleep(0.2)  # rate limit 諛⑹?

    print(f"\n[?꾨즺] {total_upserted}媛?踰≫꽣 ?낅줈????{PINECONE_INDEX_NAME}/{PINECONE_NAMESPACE}")
    return total_upserted


if __name__ == "__main__":
    embed_and_upload()

 succeeded in 3980ms:
"""
紐⑤뱺 ?꾨＼?꾪듃瑜??ш린??踰꾩쟾 愿由?
"""

# ?? Tax Researcher (TaxIssueAnalyzer + LawRetriever ?⑹튇 MVP ??븷) ??????????
RESEARCHER_ROLE = "?쒓뎅 ?묐룄?뚮뱷??踰뺣졊 議곗궗愿"
RESEARCHER_GOAL = (
    "?ъ슜?먯쓽 ?ъ떎愿怨꾨? ?뺣━?섍퀬, RAG ?꾧뎄濡?愿??踰뺣졊 議곕Ц???뺥솗??寃?됲빐 "
    "?꾨떖?쒕떎. 踰뺣졊 議곕Ц ?먮Ц ?댁쇅???댁슜? 異붿륫?섏? ?딅뒗??"
)
RESEARCHER_BACKSTORY = (
    "?섎뀈媛??뚮뱷?몃쾿쨌議곗꽭?밸??쒗븳踰?踰뺣졊 ?곗씠?곕쿋?댁뒪瑜?愿由ы빐???꾨Ц媛. "
    "議곕Ц??怨꾩링 援ъ“(議?????紐?瑜??뺥솗???뚯븙?섍퀬 "
    "?꾩슂??議곕Ц??鍮좎쭚?놁씠 寃?됲븯??寃껋쓣 理쒖슦?좎쑝濡??쒕떎."
)

RESEARCHER_TASK = """\
?꾨옒 ?ъ슜??吏덈Ц??遺꾩꽍?섍퀬 RAG 寃???꾧뎄瑜??몄텧?섎씪.

吏덈Ц: {question}

?섑뻾 ?④퀎:
1. 吏덈Ц?먯꽌 ?듭떖 ?ъ떎愿怨???ぉ 異붿텧 (痍⑤뱷?? ?묐룄?? 蹂댁쑀湲곌컙, ?몃??? 二쇳깮 ????
2. 寃???ㅼ썙???ㅺ퀎 (踰뺣졊 ?⑹뼱 ?곗꽑)
3. search_tax_law ?꾧뎄 ?몄텧
4. 寃?됰맂 議곕Ц 紐⑸줉怨?chunk_id瑜?洹몃?濡?異쒕젰

異쒕젰 ?뺤떇:
- ?뺤씤???ъ떎愿怨? ...
- 遺덊솗???꾨씫 ?뺣낫: ...
- 寃?됰맂 議곕Ц: (?꾧뎄 寃곌낵 洹몃?濡?
"""

# ?? Tax Advisor (ExemptionReasoner + CitationVerifier + AnswerComposer ?⑹튇 MVP ??븷) ?
ADVISOR_ROLE = "?쒓뎅 ?묐룄?뚮뱷??踰뺣졊 ?댁꽍 ?꾨Ц媛"
ADVISOR_GOAL = (
    "議곗궗愿??寃?됲븳 議곕Ц?먮쭔 洹쇨굅??鍮꾧낵?맞룰컧硫는룹쨷怨??щ?瑜??먮떒?섍퀬, "
    "?몄슜 議곕Ц???ㅼ젣 寃??寃곌낵??議댁옱?섎뒗吏 寃利앺븳 ??理쒖쥌 ?듬????묒꽦?쒕떎."
)
ADVISOR_BACKSTORY = (
    "10??寃쎈젰???몃Т??異쒖떊 AI ?대뱶諛붿씠?. 議곕Ц???녿뒗 ?댁슜? ?덈? ?몄슜?섏? ?딆쑝硫? "
    "遺덊솗?ㅽ븳 ?ъ떎愿怨꾧? ?덉쑝硫?寃곕줎???좊낫?섍퀬 異붽? ?뺤씤 ?ы빆??紐낆떆?쒕떎."
)

ADVISOR_TASK = """\
議곗궗愿??寃??寃곌낵瑜?諛뷀깢?쇰줈 理쒖쥌 ?멸툑 ?먮떒???섑뻾?섎씪.

吏덈Ц: {question}
議곗궗愿 寃곌낵: {research_result}

?섑뻾 ?④퀎:
1. 議곗궗愿???쒓났??chunk_id 紐⑸줉 ?뺤씤
2. 媛??몄슜 議곕Ц???ㅼ젣 寃??寃곌낵 ?덉뿉 ?덈뒗吏 寃利?(?놁쑝硫??몄슜 湲덉?)
3. 寃利앸맂 議곕Ц留??ъ슜??鍮꾧낵??媛먮㈃/以묎낵 ?щ? ?먮떒
4. ?꾨옒 ?뺤떇?쇰줈 ?쒓뎅??理쒖쥌 ?듬? ?묒꽦

[?붿빟 ?먮떒]
鍮꾧낵???대떦 / 鍮꾪빐??/ 異붽? ?뺤씤 ?꾩슂

[洹쇨굅 踰뺣졊]
- ?뚮뱷?몃쾿 ?쏰O議??쏰???쏰??
- ...

[?먮떒 怨쇱젙]
1. ...
2. ...

[異붽? ?뺤씤 ?꾩슂]
- (?꾨씫???ъ떎愿怨?

[?좎쓽?ы빆]
蹂??듬?? 踰뺣쪧 ?먮Ц???꾨땶 ?뺣낫 ?쒓났 紐⑹쟻?낅땲?? ?뺥솗???먮떒? ?몃Т?ъ? ?곷떞?섏꽭??
"""

# ?? rag.py?먯꽌 ?ъ슜?섎뒗 ?⑥씪 LLM ?꾨＼?꾪듃 ??????????????????????????????????
RAG_SYSTEM_PROMPT = """?뱀떊? ?쒓뎅 ?묐룄?뚮뱷??踰뺣졊 ?꾨Ц AI ?댁떆?ㅽ꽩?몄엯?덈떎.
諛섎뱶???꾨옒 洹쒖튃???곕Ⅴ?몄슂:
1. ?쒓났??踰뺣졊 議곕Ц?먮쭔 洹쇨굅???듬??⑸땲?? 議곕Ц???녿뒗 ?댁슜? 異붿륫?섏? ?딆뒿?덈떎.
2. 遺덊솗?ㅽ븳 ?ъ떎愿怨꾧? ?덉쑝硫?'異붽? ?뺤씤 ?꾩슂' ??ぉ??紐낆떆?⑸땲??
3. ?듬?? 諛섎뱶???ㅼ쓬 JSON ?뺤떇?쇰줈留?異쒕젰?⑸땲??

{
  "answer": "?붿빟 ?먮떒 諛?洹쇨굅",
  "citations": ["?뚮뱷?몃쾿 ??9議?????????, ...],
  "chunk_ids": ["285523_0890000", ...],
  "confidence": 0.0~1.0,
  "missing_facts": ["?뺤씤???꾩슂???ъ떎愿怨?紐⑸줉"],
  "warnings": ["二쇱쓽?ы빆 紐⑸줉"]
}"""

RAG_USER_TEMPLATE = """?ㅼ쓬 踰뺣졊 議곕Ц??李멸퀬??吏덈Ц???듯븯?몄슂.

=== 寃?됰맂 踰뺣졊 議곕Ц ===
{context}

=== 吏덈Ц ===
{question}

諛섎뱶??JSON ?뺤떇?쇰줈留??듯븯?몄슂."""

# ?? Red Team ?꾨＼?꾪듃 ?????????????????????????????????????????????????????????

RED_TEAM_SYSTEM = """?뱀떊? ?묐룄?뚮뱷??踰뺣졊 媛먯궗愿?낅땲??
釉붾（????먮떒?먯꽌 踰뺤쟻 ?ㅻ쪟瑜?李얠븘 諛섎컯?⑸땲??

諛섎컯 媛?ν븳 ?ㅻ쪟 ?좏삎:
1. ?좊졊 ?몄슜 ??寃??寃곌낵???녿뒗 議곕Ц???몄슜
2. ?붽굔 異⑹” ?ㅽ뙋 ??蹂댁쑀湲곌컙쨌嫄곗＜湲곌컙 怨꾩궛 李⑹삤
3. ?쒖젏 ?ㅻ쪟 ??議곗젙??곸????먮떒 ?쒖젏(痍⑤뱷/?묐룄) ?쇰룞
4. ?밸? ?꾨씫 ??遺移?寃쎄낵議곗튂, ?쒖떆 洹쒖젙 誘몄쟻??
5. 以묎낵 ?뚰뵾 ???ㅼ＜??以묎낵?몄쑉 ?곸슜 ?꾨씫
6. 怨좉?二쇳깮 湲곗? ?ㅻ쪟 ??12??珥덇낵 ?먮떒 李⑹삤
7. ?댁썡怨쇱꽭 ?꾨씫 ??諛곗슦?먃룹쭅怨꾩〈鍮꾩냽 利앹뿬 ??5??10?????묐룄

諛섎뱶??吏??洹쒖튃:
- 援ъ껜??踰뺣졊 議곕Ц 踰덊샇濡?洹쇨굅瑜??쒖떆?섎씪 (?? ?뚮뱷?몃쾿 ??04議?????????
- 洹쇨굅 ?놁씠 諛섎컯?섏? 留먮씪
- ?ㅻ쪟媛 ?놁쑝硫?"?댁쓽 ?놁쓬"??諛섑솚?섎씪
- 諛섎뱶??JSON?쇰줈留??묐떟?섎씪"""

RED_TEAM_CHALLENGE_TEMPLATE = """釉붾（? ?먮떒??寃?좏븯怨??ㅻ쪟瑜?李얠븘??

=== ?ъ떎愿怨?===
{fact_summary}

=== 釉붾（? ?먮떒 ===
verdict: {verdict}
answer: {answer}
citations: {citations}
confidence: {confidence}

=== 釉붾（???寃?됲븳 議곕Ц chunk_id 紐⑸줉 ===
{chunk_ids}

?ㅻ쪟媛 ?덉쑝硫?諛섎컯?섍퀬, ?놁쑝硫?"?댁쓽 ?놁쓬"??諛섑솚?섎씪.

諛섎뱶???꾨옒 JSON ?뺤떇?쇰줈留??묐떟?섎씪:
{{
  "has_challenge": true | false,
  "challenge_type": "?좊졊?몄슜" | "?붽굔?ㅽ뙋" | "?쒖젏?ㅻ쪟" | "?밸??꾨씫" | "以묎낵?뚰뵾" | "怨좉?二쇳깮?ㅻ쪟" | "?댁썡怨쇱꽭?꾨씫" | "?댁쓽?놁쓬",
  "challenge_text": "援ъ껜??諛섎컯 ?댁슜 (踰뺣졊 議곕Ц 踰덊샇 ?ы븿)",
  "challenged_citations": ["?ㅻ쪟媛 ?덈뒗 ?몄슜 議곕Ц"],
  "missing_articles": ["?꾨씫??踰뺣졊 議곕Ц ???ш린??寃???꾩슂"],
  "red_confidence": 0.0 ~ 1.0
}}"""

# ?? Blue Team 諛⑹뼱 ?꾨＼?꾪듃 ???????????????????????????????????????????????????

BLUE_DEFENSE_SYSTEM = """?뱀떊? ?쒓뎅 ?묐룄?뚮뱷??踰뺣졊 ?댁꽍 ?꾨Ц媛?낅땲??
?덈뱶???諛섎컯??踰뺣졊 洹쇨굅濡?諛⑹뼱?섍굅?? ?ㅻ쪟瑜??몄젙?섍퀬 ?섏젙???먮떒???쒖떆?⑸땲??

諛섎뱶??吏??洹쒖튃:
- ?쒓났??踰뺣졊 議곕Ц(?먮낯 + 異붽? 寃??寃곌낵)?먮쭔 洹쇨굅?섎씪
- ?덈뱶???吏?곹븳 ?꾨씫 議곕Ц??異붽? 寃??寃곌낵???덉쑝硫?諛섏쁺?섎씪
- ?ㅻ쪟 ?몄젙???꾩슂?섎㈃ ?붿쭅?섍쾶 ?먮떒???섏젙?섎씪
- 諛섎뱶??JSON?쇰줈留??묐떟?섎씪"""

BLUE_DEFENSE_TEMPLATE = """?덈뱶???諛섎컯???묐떟?섎씪. 異붽? 寃??寃곌낵媛 ?쒓났?쒕떎.

=== ?먮낯 ?먮떒 ===
verdict: {verdict}
answer: {answer}

=== ?덈뱶? 諛섎컯 ===
{challenge_text}

=== 異붽? 寃?됰맂 踰뺣졊 議곕Ц ===
{additional_context}

諛섎뱶???꾨옒 JSON ?뺤떇?쇰줈留??묐떟?섎씪:
{{
  "defense_result": "defended" | "conceded" | "partial",
  "revised_verdict": "鍮꾧낵?? | "媛먮㈃" | "以묎낵" | "?쇰컲怨쇱꽭" | "?④린?몄쑉" | "怨좉?二쇳깮" | "?ъ떎愿怨꾨?議?,
  "defense_text": "諛⑹뼱 ?먮뒗 ?섏젙 ?댁슜 (踰뺣졊 議곕Ц 洹쇨굅 ?ы븿)",
  "new_citations": ["異붽? 寃?됱쑝濡?諛쒓껄??議곕Ц"],
  "blue_confidence": 0.0 ~ 1.0
}}"""

codex
출력 검증기와 retriever 태깅도 함께 보겠습니다. 법령 변경이 retrieval 성능 저하로만 끝나는지, 아니면 최종 판정 로직까지 이중으로 깨지는지 확인하는 단계입니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\output_validator.py | Select-Object -First 220" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\retrieval\\retriever_impl.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content tests\\test_pipeline_cases.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content tests\\rag_golden_cases.py | Select-Object -First 340" in c:\Users\user\cording2025\tax-rag
 succeeded in 3477ms:
"""
L5 ??Output Validator

LLM 異쒕젰???섏삩 ???ㅽ뻾. ??醫낅쪟???ㅻ쪟瑜?諛⑹뼱:

- 議곗슜???ㅻ쪟: ?댁썡怨쇱꽭 臾댁떆?섍퀬 "鍮꾧낵?? ??L2媛 ?≪븘???섏?留??듦낵??寃쎌슦 理쒗썑 諛⑹뼱
- ?먯떊媛??덈뒗 ?ㅻ쪟: 怨좉?二쇳깮 ?뺤씤 ?놁씠 "100% 鍮꾧낵?? ???좊ː??媛뺤젣 ?섑뼢

?먯튃: confidence媛 ?믪븘??missing_facts媛 ?덉쑝硫??섑뼢.
     ?몄슜 chunk媛 寃??寃곌낵???놁쑝硫?phantom citation) ?좊ː??0.3 ?댄븯.
"""

from __future__ import annotations

from typing import Set

from .tax_answer import TaxAnswer

# ?좊ː???곹븳 ??missing_facts ?덉쓣 ??CONFIDENCE_CAP_WITH_MISSING = 0.75

# phantom citation 諛쒓껄 ???좊ː??媛뺤젣 ?곹븳
CONFIDENCE_CAP_PHANTOM_CITATION = 0.3

# "鍮꾧낵?? verdict?몃뜲 怨좉?二쇳깮 誘명솗?????좊ː???곹븳
CONFIDENCE_CAP_UNCHECKED_HIGH_VALUE = 0.6


def validate_output(answer: TaxAnswer, retrieved_chunk_ids: Set[str]) -> TaxAnswer:
    """
    TaxAnswer瑜?寃利앺븯怨??꾩슂 ??confidence瑜??섑뼢 議곗젙.

    Args:
        answer: LLM???앹꽦??TaxAnswer
        retrieved_chunk_ids: Stage 1+2 寃?됱뿉???ㅼ젣濡?諛섑솚??chunk ID 吏묓빀

    Returns:
        warnings 異붽? 諛?confidence 議곗젙??TaxAnswer
    """
    warnings = list(answer.warnings)
    confidence = answer.confidence

    # ?? 1. Phantom Citation 寃???????????????????????????????????????????
    # LLM???몄슜??chunk媛 ?ㅼ젣 寃??寃곌낵???놁쑝硫?hallucination ?섏떖
    cited_ids = {c.chunk_id for c in answer.citations}
    phantom = cited_ids - retrieved_chunk_ids
    if phantom:
        warnings.append(
            f"???몄슜 {len(phantom)}媛?泥?겕媛 寃??寃곌낵???놁쓬 ??"
            f"?섍컖 ?몄슜 媛?μ꽦: {', '.join(sorted(phantom))}"
        )
        confidence = min(confidence, CONFIDENCE_CAP_PHANTOM_CITATION)

    # ?? 2. Missing Facts ???좊ː???곹븳 ??????????????????????????????????
    if answer.missing_facts and confidence > CONFIDENCE_CAP_WITH_MISSING:
        warnings.append(
            f"異붽? ?뺤씤 ?꾩슂 ??ぉ {len(answer.missing_facts)}嫄???"
            f"?좊ː??{confidence:.0%} ??{CONFIDENCE_CAP_WITH_MISSING:.0%}濡?議곗젙"
        )
        confidence = CONFIDENCE_CAP_WITH_MISSING

    # ?? 3. 鍮꾧낵??verdict + 怨좉?二쇳깮 誘명솗???????????????????????????????
    # "鍮꾧낵???쇨퀬 ?덈뒗???묐룄媛?≪쓣 ?뺤씤?섏? ?딆? 寃쎌슦
    # 12??珥덇낵?대㈃ 珥덇낵遺꾩? 怨쇱꽭 ???꾩쟾 鍮꾧낵?멸? ?꾨떂
    is_exemption_verdict = answer.verdict in ("鍮꾧낵??, "議곌굔遺鍮꾧낵??)
    high_value_unchecked = any(
        "?묐룄媛?? in f or "怨좉?二쇳깮" in f
        for f in answer.missing_facts
    )
    if is_exemption_verdict and high_value_unchecked:
        warnings.append(
            "???묐룄媛??誘명솗????怨좉?二쇳깮(12??珥덇낵) ?대떦 ??珥덇낵遺?怨쇱꽭?? "
            "鍮꾧낵???먮떒? ?묐룄媛???뺤씤 ???ш????꾩슂"
        )
        confidence = min(confidence, CONFIDENCE_CAP_UNCHECKED_HIGH_VALUE)

    # ?? 4. ?댁썡怨쇱꽭 寃쎄퀬 ?듦낵 ?щ? ??????????????????????????????????????
    # L2?먯꽌 ?댁썡怨쇱꽭 ?щ━?곗뺄 ??ぉ??鍮좎죱?붾뜲 ?ш린源뚯? ?붾떎硫?    # (can_proceed=True?몃뜲 ?댁썡怨쇱꽭 愿??missing_facts媛 ?덈뒗 寃쎌슦)
    iota_missing = any("?댁썡怨쇱꽭" in f or "?먯랬?앹씪" in f or "?먯랬?앷??? in f for f in answer.missing_facts)
    if iota_missing and is_exemption_verdict:
        warnings.append(
            "???댁썡怨쇱꽭 ?곸슜 ?щ? 誘명솗????諛곗슦??吏곴퀎 利앹뿬 ??湲곌컙 ???묐룄 ??"
            "痍⑤뱷媛?≪씠 利앹뿬???먭?濡?諛붾뚯뼱 ?몄븸???ш쾶 ?щ씪吏????덉쓬"
        )
        confidence = min(confidence, 0.5)

    # ?? 5. 理쒖쥌 諛섑솚 ?????????????????????????????????????????????????????
    if confidence != answer.confidence or warnings != answer.warnings:
        return answer.with_update(confidence=confidence, warnings=warnings)
    return answer

 succeeded in 3473ms:
"""
RAG ?뚯씠?꾨씪??怨⑤뱺 ?뚯뒪??耳?댁뒪 ??RAG ?붿쭊 ? end-to-end 寃利앹슜

?ъ슜踰?
    from tests.fixtures.rag_golden_cases import RAG_GOLDEN_CASES
    from app.domain.rag.query_input import RAGQueryInput

    for case in RAG_GOLDEN_CASES:
        query = RAGQueryInput.from_fact_ledger(
            fact_ledger=case["fact_ledger"],
            owner_profile=case["owner_profile"],
            user_property=case["user_property"],
        )
        result = await run_rag_pipeline(query, retriever, llm_fn)
        # result? case["expected"] 鍮꾧탳

耳?댁뒪 紐⑸줉:
    CASE-01  1?몃?1二쇳깮 ?⑥닚 鍮꾧낵??    CASE-02  怨좉?二쇳깮 (15?? 議곌굔遺鍮꾧낵????珥덇낵遺?怨쇱꽭
    CASE-03  ?댁썡怨쇱꽭 L2 李⑤떒 ??blocked_at_l2=True 寃利?    CASE-04  ?쇱떆??2二쇳깮 鍮꾧낵????3???대궡 ?묐룄 異⑹”
    CASE-05  ?곸냽二쇳깮 寃쎈줈 A ???쇰컲二쇳깮 ?묐룄 鍮꾧낵??"""

RAG_GOLDEN_CASES = [

    # ????????????????????????????????????????????????????????????????????
    # CASE-01: 1?몃? 1二쇳깮 ?⑥닚 鍮꾧낵??    # 議곌굔: ?꾪뙆?? 留ㅻℓ痍⑤뱷, 1二쇳깮, 議곗젙??곸??? 2???댁긽 嫄곗＜, 12???댄븯
    # ?덉긽: verdict=鍮꾧낵?? confidence??.85, blocked_at_l2=False
    # ????????????????????????????????????????????????????????????????????
    {
        "case_id": "CASE-01",
        "title": "1?몃? 1二쇳깮 ?⑥닚 鍮꾧낵??,
        "description": "媛??湲곕낯?곸씤 鍮꾧낵??耳?댁뒪. 議곗젙??곸????꾪뙆?? 2???댁긽 嫄곗＜.",
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "?꾪뙆??,
            "acquisition_cause": "留ㅻℓ",
            "acquisition_date": "2019-04-10",
            "transfer_date": "2025-07-15",
            "acquisition_price": 480000000,
            "sale_price_total": 850000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 6.3,
            "residence_period_years": 3.5,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "鍮꾧낵??,
            "confidence_min": 0.85,
            "key_article": "?뚮뱷?몃쾿 ?쒗뻾????54議?,
            "notes": "議곗젙??곸???痍⑤뱷 ??2??嫄곗＜?붽굔 異⑹”. 12???댄븯 ???꾩븸 鍮꾧낵??",
        },
    },

    # ????????????????????????????????????????????????????????????????????
    # CASE-02: 怨좉?二쇳깮 (?묐룄媛??15?? 議곌굔遺鍮꾧낵??    # 議곌굔: 1二쇳깮, 2??嫄곗＜ 異⑹”, ?묐룄媛??15????12??珥덇낵遺꾩? 怨쇱꽭
    # ?덉긽: verdict=議곌굔遺鍮꾧낵?? L5?먯꽌 怨좉?二쇳깮 寃쎄퀬 異붽?
    # ????????????????????????????????????????????????????????????????????
    {
        "case_id": "CASE-02",
        "title": "怨좉?二쇳깮 議곌굔遺鍮꾧낵??(?묐룄媛??15??",
        "description": "鍮꾧낵???붽굔? 異⑹”?섏?留?12??珥덇낵遺?3???????怨쇱꽭?섎뒗 耳?댁뒪.",
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "?꾪뙆??,
            "acquisition_cause": "留ㅻℓ",
            "acquisition_date": "2016-09-01",
            "transfer_date": "2025-08-20",
            "acquisition_price": 700000000,
            "sale_price_total": 1500000000,       # 15????怨좉?二쇳깮
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 8.97,
            "residence_period_years": 4.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "議곌굔遺鍮꾧낵??,
            "confidence_min": 0.75,
            "key_article": "?뚮뱷?몃쾿 ??9議?????????,
            "notes": (
                "?묐룄媛??15????12??珥덇낵 3?듭뿉 ???怨쇱꽭. "
                "?κ린蹂댁쑀?밸퀎怨듭젣 ??(10???댁긽 蹂댁쑀+嫄곗＜) ?곸슜 媛?? "
                "L5?먯꽌 怨좉?二쇳깮 寃쎄퀬 ?ы븿 ?덉긽."
            ),
        },
    },

    # ????????????????????????????????????????????????????????????????????
    # CASE-03: ?댁썡怨쇱꽭 L2 李⑤떒
    # 議곌굔: 諛곗슦?먯뿉寃뚯꽌 利앹뿬諛쏆? ?꾪뙆?? 利앹뿬?쇰줈遺??3???대궡 ?묐룄
    #        ?먯랬?앹씪/?먯랬?앷???誘명솗???곹깭 ??L2 critical 李⑤떒
    # ?덉긽: blocked_at_l2=True (?먯랬?앹씪 誘명솗?몄씠 critical)
    # ????????????????????????????????????????????????????????????????????
    {
        "case_id": "CASE-03",
        "title": "?댁썡怨쇱꽭 L2 李⑤떒 ??諛곗슦??利앹뿬 ??3???대궡 ?묐룄",
        "description": (
            "諛곗슦?먯뿉寃뚯꽌 利앹뿬諛쏆? ?꾪뙆?몃? 利앹뿬?쇰줈遺??3???대궡 ?묐룄. "
            "?댁썡怨쇱꽭(짠97??) ?곸슜 ?щ? ?먮떒???꾩슂??利앹뿬???먯랬?앹씪/?먯랬?앷??≪씠 ?놁쓬 ??L2 李⑤떒."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "?꾪뙆??,
            "acquisition_cause": "利앹뿬",
            "acquisition_date": "2022-06-15",     # 利앹뿬??            "transfer_date": "2025-09-10",         # 利앹뿬 ????3.2????5???대궡
            "acquisition_price": 900000000,        # 利앹뿬 ?뱀떆 ?좉퀬媛??            "sale_price_total": 1100000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 3.2,
            "residence_period_years": 2.5,
            "joint_ownership_yn": False,
            "gift_date": "2022-06-15",
        },
        "fact_ledger": {
            "is_gift_from_spouse_or_lineal": True,
            # ?섎룄?곸쑝濡?original_donor_acquisition_date / original_donor_acquisition_price ?놁쓬
            # ??L2 check_facts()媛 critical missing?쇰줈 李⑤떒?댁빞 ??        },
        "expected": {
            "blocked_at_l2": True,
            "verdict": "needs_verification",
            "missing_fact_contains": "original_donor_acquisition_date",
            "notes": (
                "利앹뿬???먯랬?앹씪/?먯랬?앷????놁씠 ?댁썡怨쇱꽭 ?몄븸 怨꾩궛 遺덇?. "
                "blocked_at_l2=True ?ъ빞 ?섍퀬 missing_facts??"
                "original_donor_acquisition_date/original_donor_acquisition_price ?ы븿 ?꾩닔."
            ),
        },
    },

    # ????????????????????????????????????????????????????????????????????
    # CASE-04: ?쇱떆??2二쇳깮 鍮꾧낵????醫낆쟾二쇳깮 3???대궡 ?묐룄 異⑹”
    # 議곌굔: 醫낆쟾二쇳깮 蹂댁쑀 以??좉퇋二쇳깮 痍⑤뱷, 3???대궡 醫낆쟾二쇳깮 ?묐룄
    #        ?좉퇋二쇳깮 痍⑤뱷?? 2023-05-01 ???묐룄湲고븳: 2026-05-01
    #        ?ㅼ젣 ?묐룄?? 2025-10-15 ??湲고븳 ??異⑹”
    # ?덉긽: verdict=鍮꾧낵??    # ????????????????????????????????????????????????????????????????????
    {
        "case_id": "CASE-04",
        "title": "?쇱떆??2二쇳깮 鍮꾧낵????3???대궡 醫낆쟾二쇳깮 ?묐룄",
        "description": (
            "醫낆쟾二쇳깮 蹂댁쑀 以??좉퇋二쇳깮 痍⑤뱷(2023-05-01). "
            "3???대궡(2026-05-01 ????醫낆쟾二쇳깮 ?묐룄(2025-10-15) ??鍮꾧낵???붽굔 異⑹”."
        ),
        "owner_profile": {
            "household_house_count": 2,            # ?쇱떆??2二쇳깮 ?곹깭
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "?꾪뙆??,
            "acquisition_cause": "留ㅻℓ",
            "acquisition_date": "2017-03-20",      # 醫낆쟾二쇳깮 痍⑤뱷
            "transfer_date": "2025-10-15",         # 醫낆쟾二쇳깮 ?묐룄 (湲고븳 ??
            "acquisition_price": 420000000,
            "sale_price_total": 980000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 8.6,
            "residence_period_years": 5.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": True,
            "temp_new_acquisition_date": "2023-05-01",   # ?좉퇋二쇳깮 痍⑤뱷??            "temp_old_must_sell_by": "2026-05-01",       # 醫낆쟾二쇳깮 ?묐룄 湲고븳
            "temp_new_is_adjustment_area": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "鍮꾧낵??,
            "confidence_min": 0.80,
            "key_article": "?뚮뱷?몃쾿 ?쒗뻾????55議?????,
            "notes": (
                "?좉퇋二쇳깮 鍮꾩“?뺤???痍⑤뱷 ??3???대궡 ?묐룄 湲곗? ?곸슜. "
                "2025-10-15 < 2026-05-01 ??湲고븳 ??異⑹”. "
                "醫낆쟾二쇳깮 2??嫄곗＜ ?붽굔 ?놁쓬(鍮꾩“?뺤???痍⑤뱷 ?뱀떆)."
            ),
        },
    },

    # ????????????????????????????????????????????????????????????????????
    # CASE-05: ?곸냽二쇳깮 寃쎈줈 A ???쇰컲二쇳깮 ?묐룄 鍮꾧낵??    # 議곌굔: 1二쇳깮 蹂댁쑀 以??곸냽?쇰줈 二쇳깮 異붽? 痍⑤뱷 (?곸냽二쇳깮 ?ы븿 2二쇳깮)
    #        ?곸냽媛쒖떆?쇰줈遺??5???대궡 ???곸냽二쇳깮? 二쇳깮 ?섏뿉???쒖쇅
    #        ?쇰컲二쇳깮(?먮옒 蹂댁쑀?섎뜕 二쇳깮) ?묐룄 ??1二쇳깮?쇰줈 媛꾩＜ 鍮꾧낵??    # ?덉긽: verdict=鍮꾧낵??    # ????????????????????????????????????????????????????????????????????
    {
        "case_id": "CASE-05",
        "title": "?곸냽二쇳깮 寃쎈줈 A ???쇰컲二쇳깮 ?묐룄 鍮꾧낵??,
        "description": (
            "蹂몄씤 ?뚯쑀 1二쇳깮 蹂댁쑀 以?遺紐??щ쭩?쇰줈 ?곸냽二쇳깮 痍⑤뱷(2022-11-30). "
            "?곸냽媛쒖떆 5???대궡(2027-11-30 ?????쇰컲二쇳깮 ?묐룄(2025-11-10) ???곸냽二쇳깮 ?쒖쇅 1二쇳깮 鍮꾧낵??"
        ),
        "owner_profile": {
            "household_house_count": 2,            # ?쇰컲二쇳깮 + ?곸냽二쇳깮
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "?꾪뙆??,
            "acquisition_cause": "留ㅻℓ",
            "acquisition_date": "2018-07-01",      # ?쇰컲二쇳깮 痍⑤뱷
            "transfer_date": "2025-11-10",         # ?쇰컲二쇳깮 ?묐룄
            "acquisition_price": 350000000,
            "sale_price_total": 750000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 7.4,
            "residence_period_years": 3.0,
            "joint_ownership_yn": False,
            "death_date": "2022-11-30",            # ?곸냽媛쒖떆??        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            # ?곸냽二쇳깮 ?뺣낫 ??acquisition_cause媛 ?꾨땶 蹂꾨룄 ?뚮옒洹몃줈 愿由?            # user_property??acquisition_cause??"留ㅻℓ"(?쇰컲二쇳깮 湲곗?)
            # ?곸냽二쇳깮? 蹂꾨룄 property濡?議댁옱?섎굹 ?ш린?쒕뒗 ?뚯쑀二?蹂댁쑀二쇳깮??2)濡?諛섏쁺
            "inherited_as_only_house": False,      # ?곸냽 ?뱀떆 1二쇳깮???꾨떂 (?쇰컲二쇳깮 蹂댁쑀 以?
            "deceased_same_household": False,      # ?쇱긽?띿씤怨?蹂꾧굅
            "selling_inherited_house": False,      # ?쇰컲二쇳깮 ?묐룄 (寃쎈줈 A)
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "鍮꾧낵??,
            "confidence_min": 0.80,
            "key_article": "?뚮뱷?몃쾿 ?쒗뻾????55議?????,
            "notes": (
                "?곸냽媛쒖떆 ??5???대궡 ?쇰컲二쇳깮 ?묐룄 ???곸냽二쇳깮 二쇳깮 ???쒖쇅. "
                "1二쇳깮?쇰줈 媛꾩＜ 鍮꾧낵?? "
                "?쇰컲二쇳깮 議곗젙??곸???痍⑤뱷 ??2??嫄곗＜ 異⑹”(3.0??. "
                "?묐룄媛??7.5????12???댄븯 ???꾩븸 鍮꾧낵??"
            ),
        },
    },
]


# ?? ?ъ슜 ?덉떆 ??????????????????????????????????????????????????????????
#
# pytest ?덉떆:
#
#   @pytest.mark.parametrize("case", RAG_GOLDEN_CASES)
#   async def test_rag_pipeline_golden(case, retriever, llm_fn):
#       query = RAGQueryInput.from_fact_ledger(
#           fact_ledger=case["fact_ledger"],
#           owner_profile=case["owner_profile"],
#           user_property=case["user_property"],
#       )
#       result = await run_rag_pipeline(query, retriever, llm_fn)
#
#       exp = case["expected"]
#       assert result.blocked_at_l2 == exp["blocked_at_l2"], f"{case['case_id']} blocked_at_l2 mismatch"
#       if not result.blocked_at_l2:
#           assert result.answer.verdict == exp["verdict"], f"{case['case_id']} verdict mismatch"
#           assert result.answer.confidence >= exp["confidence_min"], f"{case['case_id']} confidence too low"

 succeeded in 3481ms:
"""
?낆뒪?몃┝ ?섑뵆 ?곗씠??3耳?댁뒪 ??L2/L3 ?뚯씠?꾨씪??寃利?(?몃? ?쒕퉬??遺덊븘??

?뚯뒪??紐⑹쟻:
- RAGQueryInput.from_fact_ledger()媛 ?щ컮瑜닿쾶 ?숈옉?섎뒗吏 ?뺤씤
- L2 fact_checker媛 ?щ━?곗뺄 ?꾨씫/?뺤긽 耳?댁뒪瑜??뺥솗??遺꾨쪟?섎뒗吏 ?뺤씤
- L3 query_enrichment媛 danger_flags??留욌뒗 ?ㅼ썙?쒕? 二쇱엯?섎뒗吏 ?뺤씤

E2E ?뚯뒪??Pinecone+Claude)??pytest -m integration?쇰줈 蹂꾨룄 ?ㅽ뻾.
"""
from datetime import date
import pytest

from src.domain.query_input import RAGQueryInput
from src.domain.fact_checker import check_facts
from src.domain.query_enrichment import build_rag_query


# ?? ?섑뵆 ?곗씠??????????????????????????????????????????????????????????????????

CASE1_OWNER = {"household_house_count": 1, "overseas_residence_yn": False}
CASE1_PROP = {
    "asset_kind": "?꾪뙆??,
    "acquisition_cause": "留ㅻℓ",
    "acquisition_date": "2018-03-15",
    "transfer_date": "2025-06-20",
    "acquisition_price": 500_000_000,
    "sale_price_total": 900_000_000,
    "adjustment_area_at_acquisition": True,
    "adjustment_area_at_transfer": False,
    "holding_period_years": 7.3,
    "residence_period_years": 3.5,
    "joint_ownership_yn": False,
}
CASE1_LEDGER = {"is_temporary_two_house": False}


CASE2_OWNER = {"household_house_count": 1, "overseas_residence_yn": False}
CASE2_PROP = {
    "asset_kind": "?꾪뙆??,
    "acquisition_cause": "利앹뿬",
    "acquisition_date": "2022-05-10",
    "transfer_date": "2025-09-15",
    "acquisition_price": 600_000_000,
    "sale_price_total": 800_000_000,
    "adjustment_area_at_acquisition": True,
    "adjustment_area_at_transfer": False,
    "holding_period_years": 3.35,
    "residence_period_years": 2.1,
    "joint_ownership_yn": False,
    "gift_date": "2022-05-10",
}
CASE2_LEDGER = {
    "is_gift_from_spouse_or_lineal": True,
    "original_donor_acquisition_date": "2015-08-20",
    "original_donor_acquisition_price": 350_000_000,
}


CASE3_OWNER = {"household_house_count": 2, "overseas_residence_yn": False}
CASE3_PROP = {
    "asset_kind": "?꾪뙆??,
    "acquisition_cause": "留ㅻℓ",
    "acquisition_date": "2016-11-01",
    "transfer_date": "2025-08-30",
    "acquisition_price": 700_000_000,
    "sale_price_total": 1_500_000_000,
    "adjustment_area_at_acquisition": True,
    "adjustment_area_at_transfer": False,
    "holding_period_years": 8.8,
    "residence_period_years": 4.0,
    "joint_ownership_yn": False,
}
CASE3_LEDGER = {
    "is_temporary_two_house": True,
    "temp_new_acquisition_date": "2024-09-01",
    "temp_old_must_sell_by": "2027-09-01",
    "temp_new_is_adjustment_area": False,
}


# ?? ?ы띁 ???????????????????????????????????????????????????????????????????????

def build_query(ledger, owner, prop) -> RAGQueryInput:
    return RAGQueryInput.from_fact_ledger(ledger, owner, prop)


# ?? 耳?댁뒪 1: 1?몃?1二쇳깮 ?⑥닚 留ㅻℓ ????????????????????????????????????????????

class TestCase1:
    def setup_method(self):
        self.query = build_query(CASE1_LEDGER, CASE1_OWNER, CASE1_PROP)

    def test_from_fact_ledger_succeeds(self):
        assert self.query.date_bundle.transfer_date == date(2025, 6, 20)
        assert self.query.date_bundle.acquisition_date == date(2018, 3, 15)

    def test_entity_scope_is_house(self):
        from src.domain.query_input import EntityScope
        assert self.query.entity_scope == EntityScope.HOUSE

    def test_l2_can_proceed(self):
        result = check_facts(self.query)
        # ?묐룄媛???쒓났??9?? ??怨좉?二쇳깮 ?꾨떂 ???щ━?곗뺄 ?꾨씫 ?놁쓬
        assert result.can_proceed is True
        assert len(result.critical_missing) == 0

    def test_l2_no_danger_flags(self):
        result = check_facts(self.query)
        # ?⑥닚 留ㅻℓ 1二쇳깮 ???댁썡怨쇱꽭/?곸냽/?낆＜沅??놁쓬
        dangerous = {"?댁썡怨쇱꽭", "?곸냽二쇳깮", "議고빀?먯엯二쇨텒"}
        assert not dangerous & set(result.danger_flags)

    def test_l3_enriched_query_contains_base_info(self):
        result = check_facts(self.query)
        enriched = build_rag_query(self.query, result.danger_flags)
        assert "?꾪뙆?? in enriched
        assert "留ㅻℓ" in enriched

    def test_fact_vector_to_text_includes_adjustment_area(self):
        text = self.query.fact_vector.to_text()
        assert "議곗젙??곸???痍⑤뱷?? ?대떦" in text
        assert "議곗젙??곸????묐룄?? 鍮꾪빐?? in text

    def test_fact_vector_high_value_false(self):
        # 9??< 12????怨좉?二쇳깮 ?꾨떂
        assert self.query.fact_vector.is_high_value_house is False


# ?? 耳?댁뒪 2: ?댁썡怨쇱꽭 (諛곗슦??利앹뿬 ??5???대궡 ?묐룄) ?????????????????????????

class TestCase2:
    def setup_method(self):
        self.query = build_query(CASE2_LEDGER, CASE2_OWNER, CASE2_PROP)

    def test_rollover_taxation_populated(self):
        rt = self.query.fact_vector.special_cases.rollover_taxation
        assert rt is not None
        assert rt.is_gift_from_spouse_or_lineal is True
        assert rt.gift_date == date(2022, 5, 10)
        assert rt.original_donor_acquisition_price == 350_000_000

    def test_iota_period_is_5_years(self):
        # 2022??利앹뿬 ??2023???댁쟾 ??5???곸슜
        rt = self.query.fact_vector.special_cases.rollover_taxation
        assert rt.iota_period_years == 5

    def test_l2_can_proceed_when_all_info_present(self):
        # ?먯랬?앹씪/?먯랬?앷???紐⑤몢 ?쒓났 ??L2 李⑤떒 ?놁쓬
        # (李⑤떒? ?먯랬???뺣낫 ?꾨씫 ?쒖뿉留?諛쒖깮)
        result = check_facts(self.query)
        assert result.can_proceed is True

    def test_l2_danger_flag_iota(self):
        result = check_facts(self.query)
        # 3.35??< 5???대궡 ??danger flag ?앹꽦
        assert "?댁썡怨쇱꽭_5?꾩씠?? in result.danger_flags

    def test_l3_injects_iota_keyword(self):
        result = check_facts(self.query)
        enriched = build_rag_query(self.query, result.danger_flags)
        assert "?뚮뱷?몃쾿 ??7議곗쓽2" in enriched
        assert "?댁썡怨쇱꽭" in enriched

    def test_fact_vector_to_text_includes_iota_article(self):
        text = self.query.fact_vector.to_text()
        assert "?뚮뱷?몃쾿??7議곗쓽2" in text
        assert "?댁썡怨쇱꽭" in text

    def test_l2_blocks_when_donor_info_missing(self):
        """?먯랬???뺣낫 ?녿뒗 寃쎌슦 ???닿쾬???ㅼ젣 L2 李⑤떒 耳?댁뒪.

        is_gift_from_spouse_or_lineal=True + gift_date ?덉쓬 ??rollover_taxation ?앹꽦(partial).
        fact_checker 洹쒖튃 #2: rt.is_gift_from_spouse_or_lineal=True + 5???대궡
          ??original_donor_acquisition_date ?꾨씫 媛먯? ??L2 李⑤떒.
        """
        ledger_no_donor = {
            "is_gift_from_spouse_or_lineal": True,
            # original_donor_acquisition_date / _price ?놁쓬
        }
        q = build_query(ledger_no_donor, CASE2_OWNER, CASE2_PROP)
        result = check_facts(q)
        assert result.can_proceed is False
        fields = [m.field_name for m in result.critical_missing]
        assert any("original_donor" in f for f in fields)


# ?? 耳?댁뒪 3: ?쇱떆??2二쇳깮 + 怨좉?二쇳깮 ????????????????????????????????????????

class TestCase3:
    def setup_method(self):
        self.query = build_query(CASE3_LEDGER, CASE3_OWNER, CASE3_PROP)

    def test_temp_two_house_flag_set(self):
        sc = self.query.fact_vector.special_cases
        assert sc.is_temporary_two_house is True
        assert sc.temp_two_house is not None
        assert sc.temp_two_house.new_acquisition_date == date(2024, 9, 1)

    def test_high_value_house(self):
        # 15??> 12????怨좉?二쇳깮
        assert self.query.fact_vector.is_high_value_house is True

    def test_l2_can_proceed(self):
        result = check_facts(self.query)
        assert result.can_proceed is True

    def test_l2_danger_flags_temp_two_house_and_high_value(self):
        result = check_facts(self.query)
        assert "?쇱떆??二쇳깮" in result.danger_flags
        # 怨좉?二쇳깮 誘명솗??flag: transfer_price ?쒓났?먯쑝誘濡??놁뼱????        assert "怨좉?二쇳깮_誘명솗?? not in result.danger_flags

    def test_l3_injects_temp_two_house_keyword(self):
        result = check_facts(self.query)
        enriched = build_rag_query(self.query, result.danger_flags)
        assert "?뚮뱷?몃쾿 ?쒗뻾????55議????? in enriched

    def test_fact_vector_to_text_includes_temp_two_house_flag(self):
        text = self.query.fact_vector.to_text()
        assert "?쇱떆??二쇳깮" in text

    def test_household_count_2(self):
        assert self.query.fact_vector.household_house_count == 2

 succeeded in 3498ms:
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
from src.infra.embedder import embed_query
from src.infra.pinecone_client import get_pinecone_index, query_pinecone
from src.infra.reranker import rerank

load_dotenv()

PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")
TOP_K = int(os.getenv("RETRIEVER_TOP_K", "20"))
RERANK_TOP_N = int(os.getenv("RETRIEVER_RERANK_TOP_N", "5"))

# 踰뺣졊紐???LawId 留ㅽ븨
_LAW_NAME_TO_ID = {
    "?뚮뱷?몃쾿": LawId.INCOME_TAX_ACT,
    "?뚮뱷?몃쾿 ?쒗뻾??: LawId.INCOME_TAX_DECREE,
    "?뚮뱷?몃쾿 ?쒗뻾洹쒖튃": LawId.INCOME_TAX_RULE,
    "議곗꽭?밸??쒗븳踰?: LawId.SPECIAL_TAX_ACT,
    "議곗꽭?밸??쒗븳踰??쒗뻾??: LawId.SPECIAL_TAX_DECREE,
    "議곗꽭?밸??쒗븳踰??쒗뻾洹쒖튃": LawId.SPECIAL_TAX_RULE,
}

_LAW_CATEGORY_TO_LEVEL = {
    "踰뺣쪧": LawLevel.ACT,
    "??듬졊??: LawLevel.ENFORCEMENT_DECREE,
    "遺??: LawLevel.ENFORCEMENT_RULE,
    "?쒗뻾洹쒖튃": LawLevel.ENFORCEMENT_RULE,
}


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
        appendix_type=AppendixType.MAIN_BODY,
        applicability=ApplicabilitySpec(rule_type=ApplicabilityRuleType.NONE),
        tax_types=["transfer"],
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

        # Stage 1 ??Symbolic Filter: ?묐룄??湲곗? ?좎쭨 踰붿쐞 (Pinecone ?レ옄 ?꾪꽣)
        # DateBundle.transfer_date??required ??None 遺덇?
        as_of_int = int(query.date_bundle.transfer_date.strftime("%Y%m%d"))
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
        )

        # ?좎쭨 ?꾪꽣 寃곌낵 ?놁쑝硫??꾪꽣 ?놁씠 ?ш???(踰뺣졊 踰꾩쟾 ?대젰 誘몄닔吏??곹깭 ???
        if not matches:
            matches = query_pinecone(
                vector=vector,
                top_k=top_k,
                namespace=self.namespace,
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

codex
이제 구체적인 리스크를 정리하겠습니다. 핵심은 “법령 변경 취약점”이 retrieval recall 문제로만 정의되어 있는데, 현재 코드는 판정 로직, 출력 검증, 테스트 oracle까지 같은 상수를 중복 사용해 함께 drift할 수 있다는 점입니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\domain\\query_input.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "HIGH_VALUE_THRESHOLD|SANGSAENG_WINDOW_END|iota_period_years|HEAVY_TAX_SUSPENSION_END|is_high_value_house"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\domain\\fact_checker.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "12억|is_high_value_house|iota_period_years|danger.append|death_date|new_acquisition_date"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\domain\\query_enrichment.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "DANGER_KEYWORD_MAP|제97조의2|12억|155조|156조의2|detect_flags_from_text"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\ingestion\\embed.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "def _tag_chunk|art_num in|entity_scopes|topic_tags"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\domain\\output_validator.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "12억|이월과세|CONFIDENCE_CAP|high_value"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\eval\\retrieval_analyzer.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "DANGER_KEYWORD_MAP|recall_threshold|gold_chunk_ids|citation_precision|verdict_match|detect_flags_from_text"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\agents\\prompts.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "12억|5년/10년|5년|10년|Red Team|고가주택"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content tests'"\\test_pipeline_cases.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "12억|iota_period_years|제97조의2|5년|15억"' in c:\Users\user\cording2025\tax-rag
 succeeded in 4505ms:

101	# ?? Red Team ?꾨＼?꾪듃 ??????????????????????????????????????????????
???????????



 succeeded in 4530ms:

2	寃???덉쭏 遺꾩꽍湲?+ DANGER_KEYWORD_MAP ?먮룞 媛쒖꽑 ?쒖븞
5	  eval 寃곌낵 + gold_chunk_ids ??danger_flag蹂?recall 吏묎퀎
7	  ??DANGER_KEYWORD_MAP ?낅뜲?댄듃 ?쒖븞 ?앹꽦
10	  - citation_precision : L5 phantom 寃????human ?놁씠 ?먮룞 痢≪젙
11	  - recall@k           : gold_chunk_ids 湲곕컲 ??由щ럭??1??吏?????먮룞 諛섎났
12	  - verdict_match      : expected_verdict ?쇱튂 ?щ?
23	from src.domain.query_enrichment import DANGER_KEYWORD_MAP, detect_flags_from_text
82	    return detect_flags_from_text(question)
92	    danger_flag蹂?recall@k, verdict_match, citation_precision??吏묎퀎?쒕떎.
95	        {flag: {avg_recall, avg_verdict_match, avg_citation_precision, count, cases}}
115	        verdict = float(result.get("verdict_match") or 0)
116	        cit = result.get("citation_precision", 1.0)
131	            "avg_verdict_match": round(s["verdict_sum"] / n, 4) if n else 0.0,
132	            "avg_citation_precision": round(s["cit_sum"] / n, 4) if n else 0.0,
142	    recall_threshold: float = 0.6,
147	    gold_chunk_ids媛 鍮꾩뼱?덈뒗 耳?댁뒪??嫄대꼫?대떎.
159	        gold_ids = set(case.get("gold_chunk_ids") or [])
170	            if flag_recall.get(flag, {}).get("avg_recall", 1.0) < recall_threshold:
189	        current_kw = DANGER_KEYWORD_MAP.get(flag, "")
200	    recall_threshold: float = 0.6,
203	    DANGER_KEYWORD_MAP ?낅뜲?댄듃 ?쒖븞???앹꽦?쒕떎.
206	        {flag: {current, suggested_additions, avg_recall, avg_verdict_match, case_count}}
209	    kw_suggestions = discover_missing_keywords(golden_cases, eval_results, recall_threshold)
213	        # recall ?먮뒗 verdict_match媛 threshold 誘몃떖??flag留??쒖븞
214	        if stats["avg_recall"] < recall_threshold or stats["avg_verdict_match"] < recall_threshold:
216	                "current_keyword": DANGER_KEYWORD_MAP.get(flag, "(?놁쓬)"),
219	                "avg_verdict_match": stats["avg_verdict_match"],
220	                "avg_citation_precision": stats["avg_citation_precision"],
223	                    "gold_chunk_ids 誘몄엯????由щ럭?닿? ?뺣떟 chunk瑜?吏?뺥븯硫??ㅼ썙???꾨낫 ?먮룞 異붿텧"
236	    recall_threshold: float = 0.6,
241	      1. danger_flag蹂?recall / verdict_match / citation_precision 吏묎퀎
245	    gold_chunk_ids媛 ?놁쑝硫?recall 遺꾩꽍? 嫄대꼫?곌퀬 verdict/citation留?吏묎퀎.
248	    updates = suggest_map_updates(golden_cases, eval_results, recall_threshold)
250	    has_gold = any(case.get("gold_chunk_ids") for case in golden_cases)
262	            print("  ??gold_chunk_ids 誘몄엯????recall@k??N/A, verdict/citation留?吏묎퀎??)
263	            print("    由щ럭?닿? gold_chunk_ids瑜?梨꾩슦硫?recall + ?ㅼ썙??諛쒓껄???쒖꽦?붾맗?덈떎.\n")
271	                (has_gold and s["avg_recall"] < recall_threshold)
272	                or s["avg_verdict_match"] < recall_threshold
276	                f"{s['avg_verdict_match']:>8.2f} "
277	                f"{s['avg_citation_precision']:>9.2f} "
282	    print("  DANGER_KEYWORD_MAP ?낅뜲?댄듃 ?쒖븞")
289	            print(f"\n  [{flag}]  recall={info['avg_recall']}  verdict={info['avg_verdict_match']}")
298	        "recall_threshold": recall_threshold,



 succeeded in 4564ms:

71	        danger.append("怨좉?二쇳깮_誘명솗??)
72	    elif fv.is_high_value_house:
73	        danger.append("怨좉?二쇳깮")  # 12??珥덇낵 ?뺤씤 ??L3?먯꽌 짠89/짠156?? ?ㅼ썙??二쇱엯
80	        danger.append("?댁썡怨쇱꽭")
93	            if years_elapsed < rt.iota_period_years:
94	                danger.append(f"?댁썡怨쇱꽭_{rt.iota_period_years}?꾩씠??)
99	                            f"諛곗슦??吏곴퀎議대퉬??利앹뿬 ??{rt.iota_period_years}???대궡 ?묐룄 ??"
110	        danger.append("?곸냽二쇳깮")
114	                field_name="death_date",
122	                danger.append("?곸냽二쇳깮_?먯껜?묐룄")
134	        danger.append("?쇱떆??二쇳깮")
136	        if td is None or not getattr(td, "new_acquisition_date", None):
138	                field_name="temp_two_house.new_acquisition_date",
146	        danger.append("議고빀?먯엯二쇨텒")
165	        danger.append("遺꾩뼇沅?)
175	            danger.append("遺꾩뼇沅?湲곗?遺덈챸")
177	            danger.append("遺꾩뼇沅?2021??二쇳깮?섎??곗엯")
179	            danger.append("遺꾩뼇沅?2021??二쇳깮?섏궛??)
189	        danger.append("?곸깮?꾨?")
202	        danger.append("怨듬룞紐낆쓽")



 succeeded in 4574ms:

21	HIGH_VALUE_THRESHOLD = 1_200_000_000  # 12????
24	SANGSAENG_WINDOW_END = date(2024, 12, 31)
31	HEAVY_TAX_SUSPENSION_END = date(2026, 5, 9)
236	    ??怨꾩빟 泥닿껐?? SANGSAENG_WINDOW_START ~ SANGSAENG_WINDOW_END
257	        return SANGSAENG_WINDOW_START <= self.contract_date <= SANGSAENG_WINDOW_END
357	    def iota_period_years(self) -> int:
518	            period = self.rollover_taxation.iota_period_years
595	    def is_high_value_house(self) -> bool:
599	        return self.transfer_price > HIGH_VALUE_THRESHOLD
615	            label = "怨좉?二쇳깮" if self.is_high_value_house else "?쇰컲二쇳깮"
651	                f"?댁썡怨쇱꽭?곸슜: ?뚮뱷?몃쾿??7議곗쓽2 諛곗슦?먯쭅怨꾩쬆?ы썑{rt.iota_period_years}?꾩씠?댁뼇??"



 succeeded in 4605ms:

31	# (law_name, article_number_prefix) ??(entity_scopes, topic_tags)
34	def _tag_chunk(law_name: str, article_number: str, full_text: str) -> dict:
37	    entity_scopes: ["二쇳깮", "遺꾩뼇沅?, "議고빀?먯엯二쇨텒", "?좎?", ...]
38	    topic_tags: ["1?몃?1二쇳깮鍮꾧낵??, "?κ린蹂댁쑀?밸퀎怨듭젣", ...]
43	    entity_scopes: list[str] = []
44	    topic_tags: list[str] = []
48	        entity_scopes.append("二쇳깮")
51	        if art_num in ("89",):
52	            topic_tags += ["1?몃?1二쇳깮鍮꾧낵??]
53	        if art_num in ("95",):
54	            topic_tags += ["?κ린蹂댁쑀?밸퀎怨듭젣"]
55	        if art_num in ("97??", "97.2"):
56	            topic_tags += ["1?몃?1二쇳깮鍮꾧낵??, "?댁썡怨쇱꽭"]
57	        if art_num in ("104",):
58	            topic_tags += ["?ㅼ＜?앹쨷怨?, "?몄쑉"]
60	            if art_num in ("154",):
61	                topic_tags += ["1?몃?1二쇳깮鍮꾧낵??]
62	            if art_num in ("155",):
63	                topic_tags += ["1?몃?1二쇳깮鍮꾧낵??, "?쇱떆??二쇳깮", "?곸냽二쇳깮"]
64	            if art_num in ("155??",):
65	                topic_tags += ["1?몃?1二쇳깮鍮꾧낵??, "?곸깮?꾨?"]
66	                entity_scopes.append("?곸깮?꾨?")
67	            if art_num in ("156??", "156??"):
68	                topic_tags += ["遺꾩뼇沅뚯엯二쇨텒"]
69	                entity_scopes += ["遺꾩뼇沅?, "議고빀?먯엯二쇨텒"]
70	            if art_num in ("167??0",):
71	                topic_tags += ["?ㅼ＜?앹쨷怨?]
72	            if art_num in ("159??",):
73	                topic_tags += ["?κ린蹂댁쑀?밸퀎怨듭젣"]
77	        entity_scopes.append("二쇳깮")
78	        topic_tags += ["議고듅踰뺢컧硫?]
80	        if art_num in ("97??", "97??", "97??"):
81	            topic_tags += ["?κ린?꾨?二쇳깮"]
82	        if art_num in ("99??",):
83	            topic_tags += ["?κ린?꾨?二쇳깮"]
87	        topic_tags.append("遺移숆꼍怨쇱“移?)
90	        "entity_scopes": list(dict.fromkeys(entity_scopes)),  # ?쒖꽌 ?좎? 以묐났 ?쒓굅
91	        "topic_tags": list(dict.fromkeys(topic_tags)),
189	                "entity_scopes": tags["entity_scopes"],
190	                "topic_tags": tags["topic_tags"],



 succeeded in 4610ms:

146	        assert rt.iota_period_years == 5



 succeeded in 4627ms:

20	# ?ㅼ썙?쒓? 荑쇰━???덉뼱??踰≫꽣 寃?됱씠 ?대떦 議곕Ц 泥?겕瑜?李얠븘??DANGER_KEYWORD_MAP: Dict[str, str] = {
65	def detect_flags_from_text(query: str) -> List[str]:
81	    flags = detect_flags_from_text(query)
98	        kw = DANGER_KEYWORD_MAP.get(flag)



 succeeded in 4654ms:

19	# ?좊ː???곹븳 ??missing_facts ?덉쓣 ??CONFIDENCE_CAP_WITH_MISSING = 0.75
22	CONFIDENCE_CAP_PHANTOM_CITATION = 0.3
25	CONFIDENCE_CAP_UNCHECKED_HIGH_VALUE = 0.6
51	        confidence = min(confidence, CONFIDENCE_CAP_PHANTOM_CITATION)
54	    if answer.missing_facts and confidence > CONFIDENCE_CAP_WITH_MISSING:
57	            f"?좊ː??{confidence:.0%} ??{CONFIDENCE_CAP_WITH_MISSING:.0%}濡?議곗젙"
59	        confidence = CONFIDENCE_CAP_WITH_MISSING
65	    high_value_unchecked = any(
69	    if is_exemption_verdict and high_value_unchecked:
74	        confidence = min(confidence, CONFIDENCE_CAP_UNCHECKED_HIGH_VALUE)



codex
하나 더 확인할 부분이 있습니다. 법령 drift는 숫자 상수만의 문제가 아니라, 어떤 날짜를 기준으로 어느 버전 조문을 검색하느냐의 문제이기도 해서 retrieval의 버전 선택 로직을 같이 봅니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content src'"\\retrieval\\retriever_impl.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "as_of_int|effective_date|expiration_date|query.fact_vector.to_text|scope_val"' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '$i=1; Get-Content tests'"\\rag_golden_cases.py | ForEach-Object {\""'$i`t$_"; $i++} | Select-String "12억|5년|10년|key_article|gold_chunk_ids|expected"' in c:\Users\user\cording2025\tax-rag
 succeeded in 3165ms:

15	        # result? case["expected"] 鍮꾧탳
52	        "expected": {
56	            "key_article": "?뚮뱷?몃쾿 ?쒗뻾????54議?,
89	        "expected": {
93	            "key_article": "?뚮뱷?몃쾿 ??9議?????????,
135	        "expected": {
182	        "expected": {
186	            "key_article": "?뚮뱷?몃쾿 ?쒗뻾????55議?????,
231	        "expected": {
235	            "key_article": "?뚮뱷?몃쾿 ?쒗뻾????55議?????,
260	#       exp = case["expected"]



 succeeded in 3168ms:

67	    eff_int = int(float(meta.get("effective_date", 0) or 0))
68	    exp_int = int(float(meta.get("expiration_date", 99991231) or 99991231))
104	        query_text = query.fact_vector.to_text()
111	        as_of_int = int(query.date_bundle.transfer_date.strftime("%Y%m%d"))
114	                {"effective_date": {"$lte": as_of_int}},
115	                {"expiration_date": {"$gte": as_of_int}},
139	        scope_val = query.entity_scope.value
140	        if scope_val:
144	                or scope_val in m["metadata"]["entity_scopes"]



codex
**Findings**

1. The analysis is too retrieval-centric. Your biggest law-change risk is not just “missing the right chunk,” it is deterministic rule drift in multiple layers that all reuse the same stale assumptions. `HIGH_VALUE_THRESHOLD`, `iota_period_years`, and date windows drive verdict logic in [query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:21), [fact_checker.py](/c:/Users/user/cording2025/tax-rag/src/domain/fact_checker.py:72), and even post-LLM safety behavior in [output_validator.py](/c:/Users/user/cording2025/tax-rag/src/domain/output_validator.py:65). RLVR updates to `DANGER_KEYWORD_MAP` do nothing for those failures.

2. The system has a correlated-failure problem. Tests and prompts encode the same stale law assumptions, so eval may “pass” while the law is wrong. The 5-year rollover assumption is asserted in [test_pipeline_cases.py](/c:/Users/user/cording2025/tax-rag/tests/test_pipeline_cases.py:146), and expected articles/verdicts are hardcoded in [rag_golden_cases.py](/c:/Users/user/cording2025/tax-rag/tests/rag_golden_cases.py:52). That means `verdict_match` can reward conformity to outdated policy.

3. Your retrieval versioning model is underspecified for tax law. The retriever filters chunks only by `transfer_date` in [retriever_impl.py](/c:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py:111), but many transitional tax rules depend on acquisition date, contract date, gift date, death date, or application date. This is a more serious architecture gap than the keyword map. RLVR cannot repair a wrong legal-version slice.

4. `DANGER_KEYWORD_MAP` and `_tag_chunk()` are coupled but analyzed separately. Retrieval enrichment may be improved while Stage 1 tagging/filtering still excludes the relevant material. See [query_enrichment.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_enrichment.py:20) and [_tag_chunk in ingestion/embed.py](/c:/Users/user/cording2025/tax-rag/src/ingestion/embed.py:34). If the ontology drifts, recall will remain unstable no matter how good the keywords become.

5. `citation_precision` is too weak if it is basically “not a phantom citation.” That checks existence, not support. A retrieved article can be real and still be the wrong clause, wrong version, or legally insufficient for the proposition. Your reward signal will overestimate quality.

**(1) Missed technical gaps / risks**

- No single source of truth for law-dependent rules. You need a versioned legal-rules registry, not scattered constants plus prose prompts.
- Transitional-law applicability is the missing first-class concept. Current chunk metadata has effective dates, but not enough machine-readable applicability logic.
- Prompt drift is treated as cosmetic, but here prompts are part of the reasoning control plane. Hardcoded “12억”, “5년/10년” in [prompts.py](/c:/Users/user/cording2025/tax-rag/src/agents/prompts.py:101) can anchor the model to obsolete law even when retrieval is correct.
- Stage 1 taxonomy drift is missing from the analysis. `_tag_chunk()` article-number rules are effectively a second retrieval policy layer.
- Eval set drift is missing. If golden cases are not regularly re-based against current law and corpus versions, RLVR will optimize against stale labels.
- Corpus freshness risk is missing. A law change may be correctly reflected in logic review but absent from Pinecone because ingestion lagged.

**(2) Architectural issues in the proposed RLVR approach**

- It optimizes the wrong lever first. Most proposed actions update `DANGER_KEYWORD_MAP`, but several failure modes are caused by rule logic, version selection, or tagging.
- It risks reward hacking. The system may learn to stuff more article-number tokens into queries to improve recall@k without improving legal correctness.
- Keyword extraction from missing Pinecone chunks is lexically brittle. If law numbering changes, extracted candidates may reinforce obsolete article references.
- `verdict_match` is unsafe as a primary signal unless labels are versioned by law date and reviewed after amendments.
- The approach is incomplete because it does not propose synchronized changes to:
  - legal constants/rules
  - query enrichment
  - chunk tagging ontology
  - prompts
  - tests/golden labels
- It lacks provenance. Suggested updates should cite which failed cases, which missing chunks, which law versions, and which statute diffs triggered the suggestion.

A better architecture is:
1. Centralize law-dependent rules in a versioned config/registry with anchors and citations.
2. Make retriever applicability multi-anchor, not `transfer_date`-only.
3. Treat RLVR as diagnosis/ranking, not as the primary adaptation mechanism.
4. Generate suggestions per layer: retrieval keywords, tagging rules, deterministic legal rules, prompts, and tests.

**(3) Missing monitoring / alerting**

- Law source diff monitor: detect statute/article text changes from `law.go.kr`, not just downstream retrieval regressions.
- Corpus freshness SLA: alert if source changed but processed JSON / Pinecone index has not been rebuilt.
- Version mismatch alerts: retrieved chunk effective dates inconsistent with case anchors.
- Per-flag dashboards: recall@k, rerank hit rate, citation support rate, verdict drift.
- Stage-by-stage counters:
  - zero-hit retrieval rate
  - reranker drop-off rate
  - Stage 1 filter false-exclusion rate
  - L2 block rate by reason
  - L5 warning rate by type
- Citation quality metrics beyond phantom detection:
  - cited chunk retrieved
  - cited chunk reranked top-n
  - cited article actually contains supporting clause
- Distribution-shift monitoring on `danger_flags` and user fact patterns.
- Review queue alerting: backlog, time-to-review, repeated suggestions for same flag.
- Canary set alerts: known amendment-sensitive cases run daily against latest corpus.

**(4) Is “detect only, human fixes” appropriate?**

For legal tax logic, `no auto-apply` is correct for anything that changes verdict behavior, citations, thresholds, or rule windows. Fully automatic mutation is too risky.

But “detect only” is too conservative if it means humans must do all mechanical work. A better split is:

- Auto-generate evidence-rich change proposals.
- Auto-open patch suggestions for config/tests/prompts in a review branch.
- Auto-run regression suites and show impact deltas.
- Require human approval for merge and deployment.

So the right posture is not “auto-apply” vs “detect only.” It is “auto-diagnose and auto-prepare, human-authorize.”

**Bottom line**

Your current analysis correctly spots hardcoded law-sensitive values, but it underestimates:
- deterministic rule drift,
- legal-version applicability drift,
- ontology/tagging drift,
- eval-label drift.

The proposed RLVR loop is useful as a retrieval diagnostics tool, but architecturally it is too narrow to be the main adaptation mechanism for a legal RAG system.
tokens used
68,993

```

## Concise summary

Provider completed successfully. Review the raw output for details.

## Action items

- Review the response and extract decisions you want to apply.
- Capture follow-up implementation tasks if needed.
