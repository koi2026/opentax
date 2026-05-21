# gemini advisor artifact

- Provider: gemini
- Exit code: 0
- Created at: 2026-05-21T06:14:21.375Z

## Original task

한국 양도소득세 RAG 시스템 설계 질문: 법령 부칙(附則)의 적용례 조건 구조화 필요성 분석. 현황: 법령 개정 시 부칙에 '이 법 시행 이후 양도하는 분부터 적용' 또는 '취득하는 분부터 적용'처럼 적용 기준이 자연어로 기재됨. 현재 접근: linked_buchik_ids로 부칙 항상 함께 retrieval, LLM이 텍스트 읽고 판단. 대안 검토 요청: (1) 부칙 수집 시점에 LLM/regex로 '양도분/취득분/계약분/증여분' 키워드 추출 → ApplicabilitySpec 구조화 → retriever 하드필터, (2) Red-Blue RLVR 보상루프로 오류 누적 catch, (3) 현행(LLM 읽기) 유지. 각 접근의 실용성, 엣지케이스, 실제 세무 판단에서 '양도분 vs 취득분' 오적용 시 얼마나 치명적인지, 한국 조세법 개정 패턴상 이 구분이 얼마나 자주 등장하는지 분석해 주세요. 가장 현실적인 구현 방향 추천.

## Final prompt

한국 양도소득세 RAG 시스템 설계 질문: 법령 부칙(附則)의 적용례 조건 구조화 필요성 분석. 현황: 법령 개정 시 부칙에 '이 법 시행 이후 양도하는 분부터 적용' 또는 '취득하는 분부터 적용'처럼 적용 기준이 자연어로 기재됨. 현재 접근: linked_buchik_ids로 부칙 항상 함께 retrieval, LLM이 텍스트 읽고 판단. 대안 검토 요청: (1) 부칙 수집 시점에 LLM/regex로 '양도분/취득분/계약분/증여분' 키워드 추출 → ApplicabilitySpec 구조화 → retriever 하드필터, (2) Red-Blue RLVR 보상루프로 오류 누적 catch, (3) 현행(LLM 읽기) 유지. 각 접근의 실용성, 엣지케이스, 실제 세무 판단에서 '양도분 vs 취득분' 오적용 시 얼마나 치명적인지, 한국 조세법 개정 패턴상 이 구분이 얼마나 자주 등장하는지 분석해 주세요. 가장 현실적인 구현 방향 추천.

## Raw output

```text
한국 양도소득세 RAG 시스템에서 **부칙(附則)의 적용례(적용기준) 구조화**는 단순한 성능 개선이 아니라, **시스템의 신뢰도를 결정짓는 핵심 설계 요소**입니다. 요청하신 세 가지 접근법을 한국 세법의 특수성과 실무적 치명도 관점에서 분석해 드립니다.

---

### 1. 각 접근법 분석

#### (1) ApplicabilitySpec 구조화 및 하드필터 (추천: ★★★★★)
부칙 수집 시점에 LLM/Regex를 사용하여 `양도분 / 취득분 / 계약분 / 증여분 / 상속개시분` 등의 키워드를 추출하고, 이를 `LawChunkMetadata`의 `applicability_anchor` 필드로 구조화하는 방식입니다.

*   **실용성:** 매우 높음. 한국 부칙의 문언은 "이 법 시행 후 최초로 [양도/취득/계약]하는 분부터 적용한다"는 식으로 매우 정형화되어 있어 정규식만으로도 90% 이상 추출 가능합니다.
*   **치명도:** **최상.** '양도분' 기준 규정을 '취득분'으로 오인하면, 비과세 요건(거주 2년 등) 유무 자체가 달라져 수억 원의 세액 차이가 발생합니다.
*   **엣지케이스:** 
    *   **혼합형:** "제1항은 양도분부터, 제2항은 취득분부터 적용"과 같이 한 부칙 내에서도 조문별로 앵커가 갈리는 경우. (조문 단위 청킹 필수)
    *   **소급/경과조치:** "종전 규정에 따라 계약을 체결하고 계약금을 지급한 경우"처럼 날짜 외에 '행위' 조건이 붙는 경우.

#### (2) Red-Blue RLVR 보상루프 (추천: ★★★★☆)
현재 프로젝트에 이미 구현된 `src/eval/debate.py`를 활용하여, Red Team(검증자)이 "부칙 적용례가 올바른 앵커(양도 vs 취득)를 사용했는가?"를 집중 공격하게 하는 방식입니다.

*   **실용성:** 중간. 모든 쿼리에 대해 실행하기엔 비용이 높지만, **골든셋(Golden Set) 구축 및 회귀 테스트**에는 필수적입니다.
*   **장점:** (1)번 방식에서 놓친 복잡한 예외(경과조치 등)를 LLM의 추론 능력으로 잡아내어 '오류 패턴'으로 저장할 수 있습니다.
*   **한계:** Retrieval 단계에서 애초에 '과거 버전'의 조문이 누락되었다면, 아무리 추론해도 정답을 낼 수 없습니다.

#### (3) 현행 유지 (LLM 판단) (추천: ★★☆☆☆)
모든 부칙을 컨텍스트에 넣고 LLM이 읽고 판단하게 하는 방식입니다.

*   **위험성:** 컨텍스트 윈도우 낭비가 심하며, 부칙 텍스트가 길어질 경우 LLM이 적용례 키워드를 놓칠 확률(Needle In A Haystack 문제)이 높습니다. 
*   **비효율:** 특히 한국 세법 부칙은 수십 페이지에 달하는 경우가 많아, 관련 없는 부칙까지 모두 Feed하면 할루시네이션 유발 가능성이 커집니다.

---

### 2. 한국 조세법 패턴 분석

*   **등장 빈도:** **거의 매년.** 한국 양도세는 부동산 정책에 따라 부칙 적용례가 수시로 바뀝니다. (예: 2021.1.1. 최종1주택 판정, 2017.8.3. 거주요건 신설 등)
*   **치명적 사례:**
    *   **취득분 기준:** 1세대 1주택 비과세 거주요건 (2017.8.3. 이후 조정지역 내 '취득'분부터 적용). 이를 '양도분'으로 판단하면, 이전에 취득한 사람에게 억울하게 과세하는 결론을 낼 수 있습니다.
    *   **계약분 기준:** 상생임대주택 특례 (특정 기간 내 '계약' 체결분). 계약일 정보를 무시하고 양도일/취득일만 보면 특례 적용 여부를 틀리게 됩니다.

---

### 3. 가장 현실적인 구현 방향 추천 (Hybrid 로드맵)

가장 권장하는 방향은 **"구조화된 필터링 + 다중 버전 검색(Multi-version Retrieval)"**입니다.

1.  **Ingestion 단계 (추출):** 
    *   부칙에서 `rule_type` (양도/취득/계약)을 추출하여 메타데이터에 기록합니다.
2.  **Retrieval 단계 (확장 검색):**
    *   사용자 입력(`DateBundle`)에 `transfer_date`, `acquisition_date`, `contract_date`를 모두 포함시킵니다.
    *   Retriever는 한 종류의 날짜 필터만 쓰지 않고, **"사용자의 모든 주요 날짜가 포함된 기간의 조문 버전들"**을 후보군으로 가져옵니다.
3.  **Reranking/Filtering 단계 (구조화 필터):**
    *   가져온 조문 중 메타데이터의 `applicability_anchor`와 사용자의 해당 날짜를 대조하여, 유효하지 않은 버전은 하드필터링하거나 페널티를 줍니다.
    *   예: 조문 A의 앵커가 '취득분'인데, 사용자의 `acquisition_date`가 조문의 `effective_from` 이전이라면 해당 버전은 제외하고 이전 버전을 채택합니다.
4.  **Validation 단계 (Red-Blue):**
    *   `src/eval/debate.py`에 부칙 적용례 전용 체크리스트를 추가하여, 최종 답변이 사용자의 각 시점별 사실관계와 부칙 문언을 대조했는지 검증합니다.

**결론:** 한국 세무 판단에서 **양도분 vs 취득분 구분은 시스템의 '법적 정확성'을 결정하는 최소 요건**입니다. (1)번의 구조화를 통해 검색 품질을 근본적으로 높이고, (2)번의 루프로 엣지케이스를 보완하는 것이 가장 현실적이고 강력한 대안입니다.

```python
# 추천하는 Metadata 확장 구조 (src/domain/chunk_metadata.py)
@dataclass
class ApplicabilitySpec:
    rule_type: ApplicabilityRuleType  # 적용례, 경과조치 등
    anchors: List[str]                # ["transfer_date"], ["acquisition_date"] 등
    condition_text: Optional[str]     # "2018-09-13 이전 계약분은 종전 규정 적용" (자연어 보조)
```


Warning: True color (24-bit) support not detected. Using a terminal with true color enabled will result in a better visual experience.
YOLO mode is enabled. All tool calls will be automatically approved.
YOLO mode is enabled. All tool calls will be automatically approved.
Ripgrep is not available. Falling back to GrepTool.
Attempt 1 failed. Retrying with backoff... Error: exception TypeError: fetch failed sending request
    at file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-JEW7ZIWE.js:36023:13
    at async Models.generateContent (file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-JEW7ZIWE.js:36995:16)
    at async file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:273552:26
    at async file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:250407:23
    at async retryWithBackoff (file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:270684:23)
    at async BaseLlmClient._generateWithRetry (file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:270941:14)
    at async BaseLlmClient.generateJson (file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:270848:21)
    at async NumericalClassifierStrategy.route (file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:318678:28)
    at async CompositeStrategy.route (file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:318743:26)
    at async ModelRouterService.route (file:///C:/Users/user/AppData/Roaming/npm/node_modules/@google/gemini-cli/bundle/chunk-7VVHSNDQ.js:318904:18)
(node:7524) [DEP0190] DeprecationWarning: Passing args to a child process with shell option true can lead to security vulnerabilities, as the arguments are not escaped, only concatenated.
(Use `node --trace-deprecation ...` to show where the warning was created)

```

## Concise summary

Provider completed successfully. Review the raw output for details.

## Action items

- Review the response and extract decisions you want to apply.
- Capture follow-up implementation tasks if needed.
