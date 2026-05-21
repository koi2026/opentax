# codex advisor artifact

- Provider: codex
- Exit code: 0
- Created at: 2026-05-21T02:32:40.305Z

## Original task

한국 양도소득세 RAG 시스템(tax-rag) 개발 로드맵 아키텍처 검토를 부탁합니다.

## 프로젝트 개요
- 한국 양도소득세 비과세/감면/중과 판단 RAG 엔진
- 스택: Pinecone(벡터DB) + Claude API + BGE Reranker + Upstage Solar 임베딩
- 파이프라인: L2(팩트체크) → L3(쿼리보강) → L4(법령검색+LLM추론) → L5(출력검증)
- Red-Blue 논쟁 엔진(debate.py)으로 검증

## 당장 처리해야 할 코드 작업 (우선순위 순)

1. **조정대상지역·투기과열지구·토지거래허가구역 자동 조회** (admin_notices.py)
   - API 우선 탐색, 없으면 수동 이력 테이블 내장
   - 계약일 기준 + 취득일 기준 모두 지원
   - 3종 세트(조정대상+투기과열+토지거래허가) 동시 설계

2. **TaxConstantsRegistry** (src/domain/tax_constants.py 신규)
   - 모든 법령 기준값(고가주택 12억, 상생임대 종료일, 중과배제 유예 종료일 등)을 transfer_date 기준 버전 dict로 관리
   - 하드코딩 상수 전면 교체
   - 별표 이미지 감지 시 경고 로그 + 수동 등록 흐름

3. **SpecialCaseFlags 확장 + 특례 발굴 엔진** (src/domain/special_case_finder.py 신규)
   - 모든 조특법 특례 망라 (농어촌주택, 직장이전, 소규모재건축, 공익수용 등)
   - 케이스에서 적용 가능 특례 자동 탐색
   - 말미에 '이런 특례가 있을 수 있습니다' 제안 출력

4. **확인서(Confirmation) 모듈** (src/domain/confirmation.py 신규)
   - 3개 핵심 항목: ①다른주택없음 ②잔금지급일선후 ③특수관계자거래아님
   - 확인서 No → 파이프라인 차단 + 자료재요청 반환 (양방향 연동 필수)
   - 청약홈 세대원 각각 인증 + 주택목록 연동

5. **날짜 필드 확장** (src/api/fact_input.py)
   - contract_date, balance_payment_date, registration_date 별도 필드 추가
   - 취득시기 = min(잔금지급일, 등기접수일) 결정론 코드로 처리

6. **상속·증여 취득일 승계 규칙** (src/calculator/ 또는 src/domain/)
   - 결정론 코드로 구현 여부 확인 필요
   - LLM에 날짜 연산 절대 위임 금지

## 추가 논의 필요 항목 (Codex 의견 부탁)

A. **BM25 sparse 검색 도입 여부**
   - 현재 dense 벡터만 사용 — '제89조' 같은 조문번호 exact match 정확도 문제
   - Pinecone hybrid search(dense+sparse) vs 별도 Elasticsearch 인스턴스 vs 현행 유지

B. **유권해석 크롤링 아키텍처**
   - ntis.go.kr(국세청), tt.go.kr(조세심판원), law.go.kr(대법원판례)
   - 크롤링 가능성, 별도 네임스페이스  설계

C. **유형1(신고)/유형2(컨설팅) 파이프라인 분리**
   - 유형2: 양도/증여/부담부증여 시뮬레이션 → 장기 프로젝트
   - MVP에서의 최소 분기 설계

D. **별표 이미지(장기보유특별공제율 표1/2) 처리**
   - law.go.kr XML에서 이미지로 오는 경우 텍스트 추출 불가
   - 수동 관리 vs OCR 파이프라인 vs 상수 하드코딩 중 최적 방안

각 항목에 대해 구현 순서, 리스크, 권장 접근법을 구체적으로 알려주세요.

## Final prompt

한국 양도소득세 RAG 시스템(tax-rag) 개발 로드맵 아키텍처 검토를 부탁합니다.

## 프로젝트 개요
- 한국 양도소득세 비과세/감면/중과 판단 RAG 엔진
- 스택: Pinecone(벡터DB) + Claude API + BGE Reranker + Upstage Solar 임베딩
- 파이프라인: L2(팩트체크) → L3(쿼리보강) → L4(법령검색+LLM추론) → L5(출력검증)
- Red-Blue 논쟁 엔진(debate.py)으로 검증

## 당장 처리해야 할 코드 작업 (우선순위 순)

1. **조정대상지역·투기과열지구·토지거래허가구역 자동 조회** (admin_notices.py)
   - API 우선 탐색, 없으면 수동 이력 테이블 내장
   - 계약일 기준 + 취득일 기준 모두 지원
   - 3종 세트(조정대상+투기과열+토지거래허가) 동시 설계

2. **TaxConstantsRegistry** (src/domain/tax_constants.py 신규)
   - 모든 법령 기준값(고가주택 12억, 상생임대 종료일, 중과배제 유예 종료일 등)을 transfer_date 기준 버전 dict로 관리
   - 하드코딩 상수 전면 교체
   - 별표 이미지 감지 시 경고 로그 + 수동 등록 흐름

3. **SpecialCaseFlags 확장 + 특례 발굴 엔진** (src/domain/special_case_finder.py 신규)
   - 모든 조특법 특례 망라 (농어촌주택, 직장이전, 소규모재건축, 공익수용 등)
   - 케이스에서 적용 가능 특례 자동 탐색
   - 말미에 '이런 특례가 있을 수 있습니다' 제안 출력

4. **확인서(Confirmation) 모듈** (src/domain/confirmation.py 신규)
   - 3개 핵심 항목: ①다른주택없음 ②잔금지급일선후 ③특수관계자거래아님
   - 확인서 No → 파이프라인 차단 + 자료재요청 반환 (양방향 연동 필수)
   - 청약홈 세대원 각각 인증 + 주택목록 연동

5. **날짜 필드 확장** (src/api/fact_input.py)
   - contract_date, balance_payment_date, registration_date 별도 필드 추가
   - 취득시기 = min(잔금지급일, 등기접수일) 결정론 코드로 처리

6. **상속·증여 취득일 승계 규칙** (src/calculator/ 또는 src/domain/)
   - 결정론 코드로 구현 여부 확인 필요
   - LLM에 날짜 연산 절대 위임 금지

## 추가 논의 필요 항목 (Codex 의견 부탁)

A. **BM25 sparse 검색 도입 여부**
   - 현재 dense 벡터만 사용 — '제89조' 같은 조문번호 exact match 정확도 문제
   - Pinecone hybrid search(dense+sparse) vs 별도 Elasticsearch 인스턴스 vs 현행 유지

B. **유권해석 크롤링 아키텍처**
   - ntis.go.kr(국세청), tt.go.kr(조세심판원), law.go.kr(대법원판례)
   - 크롤링 가능성, 별도 네임스페이스  설계

C. **유형1(신고)/유형2(컨설팅) 파이프라인 분리**
   - 유형2: 양도/증여/부담부증여 시뮬레이션 → 장기 프로젝트
   - MVP에서의 최소 분기 설계

D. **별표 이미지(장기보유특별공제율 표1/2) 처리**
   - law.go.kr XML에서 이미지로 오는 경우 텍스트 추출 불가
   - 수동 관리 vs OCR 파이프라인 vs 상수 하드코딩 중 최적 방안

각 항목에 대해 구현 순서, 리스크, 권장 접근법을 구체적으로 알려주세요.

## Raw output

```text
**총평**

로드맵 방향은 맞습니다. 다만 현재 코드 기준으로는 `법령 검색 정확도`보다 먼저 `결정론 레이어 정리`를 해야 합니다. 지금 병목은 검색이 아니라 입력 사실관계와 법령 기준값이 코드 여러 곳에 흩어져 있다는 점입니다. 특히 [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:25)에 기준값이 하드코딩돼 있고, [src/api/fact_input.py](/c:/Users/user/cording2025/tax-rag/src/api/fact_input.py:76)는 날짜 필드를 아직 충분히 받지 않으며, [src/domain/pipeline.py](/c:/Users/user/cording2025/tax-rag/src/domain/pipeline.py:35)는 차단 지점이 `L2 fact check` 하나뿐입니다.

**권장 구현 순서**

1. `TaxConstantsRegistry`부터 하십시오.
이게 선행돼야 `12억`, 상생임대 기간, 중과배제 유예, 경과규정 기준일 같은 값이 한 군데로 모입니다. 지금은 [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:25), [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:28), [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:36)처럼 분산돼 있어 변경 리스크가 큽니다. 구조는 `constant_key -> [{effective_from, effective_to, value, source_law, source_article, notes}]`를 권장합니다. `transfer_date` 기준 조회만 두지 말고 `anchor_key`를 받아 `transfer_date`, `contract_date`, `acquisition_date`를 모두 지원해야 합니다. 별표 이미지 조문은 “자동 파싱 실패”를 값으로 숨기지 말고 `manual_only=True`와 경고 로그를 남기십시오.

2. 날짜 필드 확장을 바로 뒤에 두십시오.
도메인 쪽 `DateBundle`에는 이미 `contract_date`, `balance_payment_date`, `registration_date`가 있습니다([src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:113)). 그런데 `FactInput`은 아직 `transfer_date`, `acquisition_date` 중심입니다([src/api/fact_input.py](/c:/Users/user/cording2025/tax-rag/src/api/fact_input.py:96)). 이 불일치를 먼저 없애야 이후 특례 판단이 안정됩니다. `취득시기 = min(잔금지급일, 등기접수일)`은 `fact_input.py`나 별도 `date_resolver.py`에서 결정론적으로 계산하고, 원시 입력값과 계산 결과를 둘 다 보존하십시오.

3. 상속·증여 취득일 승계 규칙을 결정론 코드로 분리하십시오.
이건 LLM 금지 항목이 맞습니다. 현재 일부 구조는 있으나([src/domain/fact_checker.py](/c:/Users/user/cording2025/tax-rag/src/domain/fact_checker.py:85), [src/domain/fact_checker.py](/c:/Users/user/cording2025/tax-rag/src/domain/fact_checker.py:117)) 규칙 엔진으로 분리되지 않았습니다. `src/domain/acquisition_timeline.py` 같은 모듈에서 `resolve_effective_acquisition_date(facts)`, `resolve_holding_period_base(facts)`를 두는 편이 낫습니다. 리스크는 “원취득일/증여일/사망일” 앵커를 혼동하는 것입니다. 이건 테스트를 많이 깔아야 합니다.

4. 확인서 모듈은 `L1.5 Gate`로 넣으십시오.
이건 `fact_checker`에 섞지 말고 [src/domain/pipeline.py](/c:/Users/user/cording2025/tax-rag/src/domain/pipeline.py:52) 앞에 별도 차단 단계로 두는 게 맞습니다. 이유는 `사실 누락`과 `사용자 확인 부재`는 성격이 다르기 때문입니다. `ConfirmationResult(can_proceed, missing_confirmations, warnings)` 형태를 권장합니다. 세 항목은 전부 양방향 차단 대상으로 두되, “특수관계자 거래 아님”은 향후 증빙 첨부까지 확장 가능하게 설계하십시오. 청약홈 연동은 MVP 범위를 넘으니 지금은 인터페이스만 두고 공급자 어댑터를 분리하는 정도면 충분합니다.

5. `admin_notices.py`의 3종 구역 자동 조회를 그 다음에 구현하십시오.
이건 중요하지만, 앞선 결정론 레이어 없이 먼저 붙이면 결국 boolean 필드만 더 늘어납니다. 현재 [src/ingestion/admin_notices.py](/c:/Users/user/cording2025/tax-rag/src/ingestion/admin_notices.py:46) 구조는 조정대상지역 위주라 `designation_type` 일반화가 필요합니다. `AdjustmentAreaRecord` 대신 `AreaDesignationRecord(region_code, area_type, designated_at, released_at, source)`로 바꾸고, `resolve_area_status(region, target_date, area_type)` 하나로 합치십시오. API가 불안정하면 수동 이력 테이블을 정식 1급 데이터 소스로 두고, API는 “보강/검증용”으로 두는 편이 안전합니다. 법적 분쟁 리스크가 있는 데이터라 “API 우선, 없으면 fallback”보다 “수동 기준표 우선, API 검증”이 운영상 더 낫습니다.

6. `SpecialCaseFlags` 확장과 특례 발굴 엔진은 마지막에 두십시오.
이건 범위가 가장 큽니다. 현재 `SpecialCaseFlags`는 이미 비대해지는 중입니다([src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:437)). 여기에 모든 조특법 특례를 계속 넣으면 유지보수성이 무너집니다. `SpecialCaseFlags`는 핵심 boolean/summary만 남기고, 별도 `special_case_finder.py`에서 `ApplicableSpecialCase` 목록을 반환하는 형태가 맞습니다. 출력은 “적용 확정”과 “추가 검토 제안”을 분리하십시오. 제안형 특례는 verdict를 바꾸지 말고 warnings에만 넣는 편이 안전합니다.

**각 항목별 핵심 리스크**

1. 구역 자동 조회: 행정구역명 표기 편차, 날짜 기준 혼동, 부분 해제 이력 누락.
2. 상수 레지스트리: 경과규정 anchor가 `transfer_date` 하나로 안 끝나는 경우.
3. 특례 발굴: recall을 높이려다 false positive가 급증할 가능성.
4. 확인서: UI/REST/MCP 경로에서 동일 차단 규칙이 안 맞을 가능성.
5. 날짜 확장: 기존 `acquisition_date`와 계산된 취득시기 충돌.
6. 상속·증여 승계: “보유기간 승계”와 “취득가액 승계”를 같은 함수에서 다뤄 버리는 설계 실수.

**A-D 의사결정**

A. BM25 sparse 검색은 도입하는 쪽이 맞습니다.
우선순위는 `Pinecone hybrid > 별도 Elasticsearch > 현행 유지`입니다. 이유는 현재 retriever가 Pinecone 날짜 필터와 reranker 흐름에 이미 맞춰져 있기 때문입니다([src/retrieval/retriever_impl.py](/c:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py:110)). 정확한 조문번호, `제89조`, `§154`, 부칙 번호는 dense만으로는 불안합니다. 다만 처음부터 ES를 별도 운영하면 운영 복잡도만 늘어납니다. 1차는 article-number sparse field만 넣은 hybrid로 충분합니다.

B. 유권해석 크롤링은 법령과 별도 네임스페이스가 맞습니다.
`tax-law`, `tax-ruling-ntis`, `tax-ruling-tt`, `tax-ruling-court`로 나누고, 검색 시에는 법령 우선, 유권해석은 보강 evidence로 붙이십시오. verdict 근거는 여전히 법령 chunk가 1순위여야 합니다. 유권해석만으로 결론을 내리는 경로는 만들지 않는 것이 좋습니다.

C. 유형1/유형2는 지금 당장 파이프라인을 물리적으로 분리하지 마십시오.
`query_mode: report | consulting` 정도의 얇은 분기만 넣고, L2/L3/L4의 코어는 공유하는 편이 낫습니다. 유형2에서만 시뮬레이션 노드와 비교표 출력을 추가하십시오. MVP에서 코드베이스를 둘로 쪼개면 테스트 비용만 커집니다.

D. 별표 이미지는 단기적으로 수동 관리가 최적입니다.
OCR 파이프라인은 후순위입니다. 별표는 숫자 테이블이라 OCR 오차가 치명적입니다. `TaxConstantsRegistry`에 수동 등록하고, 수집기에서 이미지 감지 시 `manual_review_required`를 남기십시오. OCR은 “초안 추출 + 사람 검수” 용도로만 쓰는 게 맞습니다.

**권장 2주 스프린트 순서**

1. `tax_constants.py` 신설, 기존 하드코딩 상수 제거.
2. `fact_input.py` 날짜 필드 확장, 취득시기 결정론 함수 추가.
3. 상속·증여 취득일/보유기간 계산 모듈 분리.
4. `confirmation.py` 추가, `pipeline.py`에 L1.5 gate 삽입.
5. `admin_notices.py`를 3종 구역 일반화 + 수동 이력 DB 우선화.
6. Pinecone hybrid search PoC.
7. `special_case_finder.py`는 제안형 엔진부터 시작.

**테스트 게이트**

반드시 추가할 테스트는 4개입니다.

- 날짜 앵커별 상수 조회 테스트
- `min(balance_payment_date, registration_date)` 취득시기 결정 테스트
- 확인서 `No` 시 LLM 미호출 차단 테스트
- 구역 지정 이력의 취득일 기준/양도일 기준 분리 테스트

원하시면 다음 단계로 바로 `실행 가능한 구현 계획` 형태로 끊어서, 파일별 변경안까지 내려드리겠습니다.


OpenAI Codex v0.123.0 (research preview)
--------
workdir: c:\Users\user\cording2025\tax-rag
model: gpt-5.4
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 019e485f-0b55-7763-ae9d-40378d594c3b
--------
user
한국 양도소득세 RAG 시스템(tax-rag) 개발 로드맵 아키텍처 검토를 부탁합니다.

## 프로젝트 개요
- 한국 양도소득세 비과세/감면/중과 판단 RAG 엔진
- 스택: Pinecone(벡터DB) + Claude API + BGE Reranker + Upstage Solar 임베딩
- 파이프라인: L2(팩트체크) → L3(쿼리보강) → L4(법령검색+LLM추론) → L5(출력검증)
- Red-Blue 논쟁 엔진(debate.py)으로 검증

## 당장 처리해야 할 코드 작업 (우선순위 순)

1. **조정대상지역·투기과열지구·토지거래허가구역 자동 조회** (admin_notices.py)
   - API 우선 탐색, 없으면 수동 이력 테이블 내장
   - 계약일 기준 + 취득일 기준 모두 지원
   - 3종 세트(조정대상+투기과열+토지거래허가) 동시 설계

2. **TaxConstantsRegistry** (src/domain/tax_constants.py 신규)
   - 모든 법령 기준값(고가주택 12억, 상생임대 종료일, 중과배제 유예 종료일 등)을 transfer_date 기준 버전 dict로 관리
   - 하드코딩 상수 전면 교체
   - 별표 이미지 감지 시 경고 로그 + 수동 등록 흐름

3. **SpecialCaseFlags 확장 + 특례 발굴 엔진** (src/domain/special_case_finder.py 신규)
   - 모든 조특법 특례 망라 (농어촌주택, 직장이전, 소규모재건축, 공익수용 등)
   - 케이스에서 적용 가능 특례 자동 탐색
   - 말미에 '이런 특례가 있을 수 있습니다' 제안 출력

4. **확인서(Confirmation) 모듈** (src/domain/confirmation.py 신규)
   - 3개 핵심 항목: ①다른주택없음 ②잔금지급일선후 ③특수관계자거래아님
   - 확인서 No → 파이프라인 차단 + 자료재요청 반환 (양방향 연동 필수)
   - 청약홈 세대원 각각 인증 + 주택목록 연동

5. **날짜 필드 확장** (src/api/fact_input.py)
   - contract_date, balance_payment_date, registration_date 별도 필드 추가
   - 취득시기 = min(잔금지급일, 등기접수일) 결정론 코드로 처리

6. **상속·증여 취득일 승계 규칙** (src/calculator/ 또는 src/domain/)
   - 결정론 코드로 구현 여부 확인 필요
   - LLM에 날짜 연산 절대 위임 금지

## 추가 논의 필요 항목 (Codex 의견 부탁)

A. **BM25 sparse 검색 도입 여부**
   - 현재 dense 벡터만 사용 — '제89조' 같은 조문번호 exact match 정확도 문제
   - Pinecone hybrid search(dense+sparse) vs 별도 Elasticsearch 인스턴스 vs 현행 유지

B. **유권해석 크롤링 아키텍처**
   - ntis.go.kr(국세청), tt.go.kr(조세심판원), law.go.kr(대법원판례)
   - 크롤링 가능성, 별도 네임스페이스  설계

C. **유형1(신고)/유형2(컨설팅) 파이프라인 분리**
   - 유형2: 양도/증여/부담부증여 시뮬레이션 → 장기 프로젝트
   - MVP에서의 최소 분기 설계

D. **별표 이미지(장기보유특별공제율 표1/2) 처리**
   - law.go.kr XML에서 이미지로 오는 경우 텍스트 추출 불가
   - 수동 관리 vs OCR 파이프라인 vs 상수 하드코딩 중 최적 방안

각 항목에 대해 구현 순서, 리스크, 권장 접근법을 구체적으로 알려주세요.
codex
요청하신 로드맵을 현재 코드 구조 기준으로 검토하겠습니다. 먼저 실제 리포지토리에서 언급된 모듈과 파이프라인 연결 지점을 확인한 뒤, 우선순위·구현 순서·리스크를 코드 기준으로 정리하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'rg -n "SpecialCaseFlags|TaxConstants|confirmation|fact_checker|query_enrichment|output_validator|chat_turn|RAGQueryInput|transfer_price|contract_date|balance_payment_date|registration_date|inheritance|gift|rollover_taxation|temporary_two_house|adjustment_area|토지거래허가|조정대상|투기과열|BM25|sparse|reranker|Pinecone" src tests' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'rg --files src tests' in c:\Users\user\cording2025\tax-rag
 succeeded in 3608ms:
tests\rag_golden_cases.py
tests\test_chunking.py
tests\__init__.py
tests\test_pipeline_cases.py
tests\test_rag.py
src\ui.py
src\__init__.py
src\embed.py
src\rag.py
src\pages\admin.py
src\agents\prompts.py
src\agents\crew.py
src\agents\roles.py
src\eval\eval.py
src\eval\debate.py
src\eval\feedback.py
src\eval\__init__.py
src\eval\retrieval_analyzer.py
src\eval\golden_injector.py
src\retrieval\retriever_impl.py
src\retrieval\llm_fn.py
src\retrieval\__init__.py
src\agents\tools.py
src\agents\__init__.py
src\api\mcp_server.py
src\api\fact_input.py
src\api\chat_api.py
src\api\schema.py
src\api\sample_cases.py
src\api\__init__.py
src\domain\query_enrichment.py
src\domain\pipeline.py
src\domain\output_validator.py
src\domain\fact_checker.py
src\domain\chunk_metadata.py
src\domain\tax_answer.py
src\domain\__init__.py
src\domain\retriever.py
src\domain\query_input.py
src\ingestion\__init__.py
src\ingestion\embed.py
src\ingestion\collect.py
src\ingestion\admin_notices.py
src\infra\__init__.py
src\infra\reranker.py
src\infra\pinecone_client.py
src\infra\embedder.py

 succeeded in 3660ms:
tests\rag_golden_cases.py:6:    from app.domain.rag.query_input import RAGQueryInput
tests\rag_golden_cases.py:9:        query = RAGQueryInput.from_fact_ledger(
tests\rag_golden_cases.py:29:    # 조건: 아파트, 매매취득, 1주택, 조정대상지역, 2년 이상 거주, 12억 이하
tests\rag_golden_cases.py:35:        "description": "가장 기본적인 비과세 케이스. 조정대상지역 아파트, 2년 이상 거주.",
tests\rag_golden_cases.py:47:            "adjustment_area_at_acquisition": True,
tests\rag_golden_cases.py:48:            "adjustment_area_at_transfer": False,
tests\rag_golden_cases.py:54:            "is_temporary_two_house": False,
tests\rag_golden_cases.py:61:            "notes": "조정대상지역 취득 → 2년 거주요건 충족. 12억 이하 → 전액 비과세.",
tests\rag_golden_cases.py:85:            "adjustment_area_at_acquisition": True,
tests\rag_golden_cases.py:86:            "adjustment_area_at_transfer": False,
tests\rag_golden_cases.py:92:            "is_temporary_two_house": False,
tests\rag_golden_cases.py:131:            "adjustment_area_at_acquisition": True,
tests\rag_golden_cases.py:132:            "adjustment_area_at_transfer": False,
tests\rag_golden_cases.py:136:            "gift_date": "2022-06-15",
tests\rag_golden_cases.py:139:            "is_gift_from_spouse_or_lineal": True,
tests\rag_golden_cases.py:180:            "adjustment_area_at_acquisition": False,
tests\rag_golden_cases.py:181:            "adjustment_area_at_transfer": False,
tests\rag_golden_cases.py:187:            "is_temporary_two_house": True,
tests\rag_golden_cases.py:190:            "temp_new_is_adjustment_area": False,
tests\rag_golden_cases.py:230:            "adjustment_area_at_acquisition": True,
tests\rag_golden_cases.py:231:            "adjustment_area_at_transfer": False,
tests\rag_golden_cases.py:238:            "is_temporary_two_house": False,
tests\rag_golden_cases.py:254:                "일반주택 조정대상지역 취득 → 2년 거주 충족(3.0년). "
tests\rag_golden_cases.py:268:#       query = RAGQueryInput.from_fact_ledger(
src\api\chat_api.py:4:Streamlit UI는 이 모듈의 chat_turn()을 직접 임포트해서 사용한다.
src\api\chat_api.py:49:                    "transfer_price": 1100000000,
src\api\chat_api.py:51:                    "is_adjustment_area_at_transfer": True,
src\api\chat_api.py:72:async def chat_turn(
src\api\chat_api.py:91:        from src.retrieval.retriever_impl import PineconeTaxLawRetriever
src\api\chat_api.py:96:        retriever = PineconeTaxLawRetriever()
src\api\chat_api.py:169:    result = await chat_turn(
src\domain\chunk_metadata.py:81:    ADJUSTMENT_AREA = "조정대상지역"
src\embed.py:2:임베딩 생성 및 Pinecone 업로드
src\embed.py:3:data/processed/all_chunks.json → Pinecone Serverless
src\embed.py:12:from pinecone import Pinecone, ServerlessSpec
src\embed.py:57:def get_or_create_index(pc: Pinecone, dimension: int) -> None:
src\embed.py:60:        print(f"Pinecone 인덱스 생성 중: {PINECONE_INDEX_NAME} (dim={dimension})")
src\embed.py:91:    pc = Pinecone(api_key=pinecone_api_key)
src\embed.py:96:    for i in tqdm(range(0, len(chunks), BATCH_SIZE), desc="Pinecone 업로드"):
src\api\fact_input.py:2:채팅 모드용 JSON 사실관계 입력 스키마 및 RAGQueryInput 변환 팩토리.
src\api\fact_input.py:11:from src.domain.query_input import RAGQueryInput
src\api\fact_input.py:20:    new_is_adjustment_area: bool = False
src\api\fact_input.py:34:    is_gift_from_spouse_or_lineal: bool     # 배우자·직계존비속 여부
src\api\fact_input.py:48:    contract_date: str              # 상생임대차계약 체결일 YYYYMMDD
src\api\fact_input.py:57:    registration_date: str          # 임대사업자 등록일 YYYYMMDD
src\api\fact_input.py:66:    inheritance: Optional[InheritanceInput] = None
src\api\fact_input.py:67:    gift: Optional[GiftInput] = None
src\api\fact_input.py:90:        "transfer_price": 1100000000,
src\api\fact_input.py:92:        "is_adjustment_area_at_transfer": true
src\api\fact_input.py:110:    transfer_price: Optional[int] = None        # 양도가액 (원) — 고가주택 판단 필수
src\api\fact_input.py:114:    is_adjustment_area_at_acquisition: bool = False  # 취득 시 조정대상지역
src\api\fact_input.py:115:    is_adjustment_area_at_transfer: bool = False     # 양도 시 조정대상지역
src\api\fact_input.py:134:def fact_input_to_rag_query(fact: FactInput) -> RAGQueryInput:
src\api\fact_input.py:136:    FactInput → RAGQueryInput 변환.
src\api\fact_input.py:147:        "sale_price_total": fact.transfer_price,
src\api\fact_input.py:149:        "adjustment_area_at_acquisition": fact.is_adjustment_area_at_acquisition,
src\api\fact_input.py:150:        "adjustment_area_at_transfer": fact.is_adjustment_area_at_transfer,
src\api\fact_input.py:158:            "rental_registration_date": _yyyymmdd_to_iso(lr.registration_date),
src\api\fact_input.py:163:    if sc.inheritance:
src\api\fact_input.py:164:        inh = sc.inheritance
src\api\fact_input.py:178:            "is_temporary_two_house": True,
src\api\fact_input.py:181:            "temp_new_is_adjustment_area": tt.new_is_adjustment_area,
src\api\fact_input.py:183:    if sc.inheritance:
src\api\fact_input.py:184:        inh = sc.inheritance
src\api\fact_input.py:190:    if sc.gift:
src\api\fact_input.py:191:        g = sc.gift
src\api\fact_input.py:192:        fact_ledger["is_gift_from_spouse_or_lineal"] = g.is_gift_from_spouse_or_lineal
src\api\fact_input.py:208:            "sangsaeng_contract_date": _yyyymmdd_to_iso(sr.contract_date),
src\api\fact_input.py:224:    return RAGQueryInput.from_fact_ledger(fact_ledger, owner_profile, user_property)
src\domain\fact_checker.py:8:- RAGQueryInput(typed schema)을 받아 semantic completeness를 검사
src\domain\fact_checker.py:23:    RAGQueryInput,
src\domain\fact_checker.py:55:def check_facts(query: RAGQueryInput) -> FactCheckResult:
src\domain\fact_checker.py:57:    RAGQueryInput을 받아 사실관계 완전성 검사.
src\domain\fact_checker.py:67:    if fv.transfer_price is None:
src\domain\fact_checker.py:69:            field_name="transfer_price",
src\domain\fact_checker.py:79:    is_gift_acquisition = fv.acquisition_reason in (
src\domain\fact_checker.py:82:    if is_gift_acquisition:
src\domain\fact_checker.py:84:        rt = sc.rollover_taxation
src\domain\fact_checker.py:85:        if rt is None or not rt.is_gift_from_spouse_or_lineal:
src\domain\fact_checker.py:88:                field_name="is_gift_from_spouse_or_lineal",
src\domain\fact_checker.py:93:        elif rt.is_gift_from_spouse_or_lineal:
src\domain\fact_checker.py:95:            years_elapsed = _years_between(rt.gift_date, db.transfer_date)
src\domain\fact_checker.py:114:        inh = sc.inheritance
src\domain\fact_checker.py:136:    if sc.is_temporary_two_house:
src\domain\fact_checker.py:184:    # ── 7. 조정대상지역 시점 미분리 경고 ────────────────────────────────
src\domain\fact_checker.py:187:    if not fv.adjustment_area_at_acquisition and not fv.adjustment_area_at_transfer:
src\domain\fact_checker.py:191:    # ── 8. 상생임대 — 조정대상지역 여부 미확인 ──────────────────────────
src\domain\fact_checker.py:194:        if not fv.adjustment_area_at_transfer:
src\domain\fact_checker.py:195:            # 상생임대는 조정대상지역이어야 거주요건 면제 의미가 있음
src\domain\fact_checker.py:198:                field_name="adjustment_area_at_transfer",
src\domain\fact_checker.py:199:                reason="상생임대 거주요건 면제는 조정대상지역 주택에만 적용 — 비조정지역이면 원래 거주요건 없음",
src\agents\prompts.py:109:3. 시점 오류 — 조정대상지역 판단 시점(취득/양도) 혼동
src\ingestion\admin_notices.py:6:  ② 행정   : 국토부/MOEF 고시    → 이 모듈 (조정대상지역, 투기과열지구, 공시지가 기준)
src\ingestion\admin_notices.py:12:    "비과세 요건 + 현재 조정대상지역 여부 + DSR 규제" 통합 상담이 가능함
src\ingestion\admin_notices.py:15:  ② 조정대상지역: 국토교통부 공공데이터포털 API (TODO: MOEF_API_KEY 발급)
src\ingestion\admin_notices.py:16:  ② 투기과열지구: 동일 API
src\ingestion\admin_notices.py:48:    조정대상지역 / 투기과열지구 단건 레코드.
src\ingestion\admin_notices.py:51:      - 취득일 기준 조정대상지역 여부 → 2년 거주요건 발생 (소령 §154①)
src\ingestion\admin_notices.py:52:      - 양도일 기준 조정대상지역 여부 → 다주택 중과세율 적용 (소법 §104①)
src\ingestion\admin_notices.py:56:    area_type: str                      # "조정대상지역" | "투기과열지구" | "투기지역"
src\ingestion\admin_notices.py:98:    JSON 파일로 직렬화해 Pinecone과 별도로 관리.
src\ingestion\admin_notices.py:100:    adjustment_areas: list[AdjustmentAreaRecord] = field(default_factory=list)
src\ingestion\admin_notices.py:105:# ── 조정대상지역 조회 헬퍼 ─────────────────────────────────────────────────────
src\ingestion\admin_notices.py:108:def resolve_adjustment_area(region: str, target_date: date, db: AdminNoticesDB) -> bool:
src\ingestion\admin_notices.py:110:    region이 target_date 시점에 조정대상지역이었는지 조회.
src\ingestion\admin_notices.py:114:      - L1 RAGQueryInput 생성 시 adjustment_area_at_acquisition / _at_transfer 계산
src\ingestion\admin_notices.py:115:      - fact_input.py FlatFactInput → RAGQueryInput 변환 시
src\ingestion\admin_notices.py:117:    for rec in db.adjustment_areas:
src\ingestion\admin_notices.py:118:        if rec.area_type == "조정대상지역" and rec.region in region:
src\ingestion\admin_notices.py:140:        for r in raw.get("adjustment_areas", [])
src\ingestion\admin_notices.py:155:        adjustment_areas=areas,
src\ingestion\admin_notices.py:171:        "adjustment_areas": [
src\ingestion\admin_notices.py:173:            for r in db.adjustment_areas
src\ingestion\admin_notices.py:187:async def collect_adjustment_areas() -> list[AdjustmentAreaRecord]:
src\ingestion\admin_notices.py:189:    국토교통부 공공데이터포털 API에서 조정대상지역 현황 수집.
src\ingestion\admin_notices.py:191:    API: data.go.kr > 국토교통부_투기과열지구·조정대상지역 고시 현황
src\ingestion\admin_notices.py:244:        areas = await collect_adjustment_areas()
src\ingestion\admin_notices.py:245:        db.adjustment_areas = areas
src\ingestion\admin_notices.py:246:        print(f"조정대상지역 {len(areas)}건 수집 완료")
src\ingestion\admin_notices.py:248:        print(f"[SKIP] 조정대상지역: {e}")
src\pages\admin.py:39:    "transfer_price": "양도가액",
src\pages\admin.py:43:    "is_adjustment_area_at_transfer": "양도시 조정대상지역",
src\pages\admin.py:44:    "is_adjustment_area_at_acquisition": "취득시 조정대상지역",
src\pages\admin.py:76:    if "transfer_price" in fact:
src\pages\admin.py:77:        price = fact["transfer_price"]
src\pages\admin.py:83:    from src.api.chat_api import chat_turn
src\pages\admin.py:84:    return asyncio.run(chat_turn(fact_json=fact_json, enable_debate=enable_debate))
src\pages\admin.py:261:                            from src.api.chat_api import chat_turn
src\pages\admin.py:262:                            result = asyncio.run(chat_turn(question=question, enable_debate=enable_debate))
src\api\mcp_server.py:11:from src.domain.query_enrichment import enrich_raw_query_text
src\rag.py:6:- Pinecone: src.infra.pinecone_client.{get_pinecone_index, query_pinecone}
src\rag.py:7:- Reranker: src.infra.reranker.{get_reranker, rerank}
src\rag.py:28:from src.infra import reranker as _reranker_mod
src\rag.py:62:# `src.rag._get_reranker` 를 patch 한다. shim 도 같은 이름을 노출해야 한다.
src\rag.py:72:def _get_reranker():
src\rag.py:73:    return _reranker_mod.get_reranker()
src\rag.py:91:    # 2. Pinecone 날짜 필터
src\rag.py:102:    # 3. Pinecone 벡터 검색 (테스트 호환: index.query 를 직접 호출)
src\rag.py:125:    reranker = _get_reranker()
src\rag.py:127:    rerank_scores = reranker.predict(pairs)
src\rag.py:277:    기존 answer_with_citations()와 달리 fact_checker / query_enrichment /
src\rag.py:278:    output_validator 를 모두 경유해 정확한 세율 판단을 수행한다.
src\rag.py:283:    from src.retrieval.retriever_impl import PineconeTaxLawRetriever
src\rag.py:287:    retriever = PineconeTaxLawRetriever()
src\domain\output_validator.py:88:        danger_flags: L2 fact_checker에서 탐지된 위험 플래그 목록 (예규 신호 탐지용)
tests\test_pipeline_cases.py:5:- RAGQueryInput.from_fact_ledger()가 올바르게 동작하는지 확인
tests\test_pipeline_cases.py:6:- L2 fact_checker가 크리티컬 누락/정상 케이스를 정확히 분류하는지 확인
tests\test_pipeline_cases.py:7:- L3 query_enrichment가 danger_flags에 맞는 키워드를 주입하는지 확인
tests\test_pipeline_cases.py:9:E2E 테스트(Pinecone+Claude)는 pytest -m integration으로 별도 실행.
tests\test_pipeline_cases.py:14:from src.domain.query_input import RAGQueryInput
tests\test_pipeline_cases.py:15:from src.domain.fact_checker import check_facts
tests\test_pipeline_cases.py:16:from src.domain.query_enrichment import build_rag_query
tests\test_pipeline_cases.py:29:    "adjustment_area_at_acquisition": True,
tests\test_pipeline_cases.py:30:    "adjustment_area_at_transfer": False,
tests\test_pipeline_cases.py:35:CASE1_LEDGER = {"is_temporary_two_house": False}
tests\test_pipeline_cases.py:46:    "adjustment_area_at_acquisition": True,
tests\test_pipeline_cases.py:47:    "adjustment_area_at_transfer": False,
tests\test_pipeline_cases.py:51:    "gift_date": "2022-05-10",
tests\test_pipeline_cases.py:54:    "is_gift_from_spouse_or_lineal": True,
tests\test_pipeline_cases.py:68:    "adjustment_area_at_acquisition": True,
tests\test_pipeline_cases.py:69:    "adjustment_area_at_transfer": False,
tests\test_pipeline_cases.py:75:    "is_temporary_two_house": True,
tests\test_pipeline_cases.py:78:    "temp_new_is_adjustment_area": False,
tests\test_pipeline_cases.py:84:def build_query(ledger, owner, prop) -> RAGQueryInput:
tests\test_pipeline_cases.py:85:    return RAGQueryInput.from_fact_ledger(ledger, owner, prop)
tests\test_pipeline_cases.py:120:    def test_fact_vector_to_text_includes_adjustment_area(self):
tests\test_pipeline_cases.py:122:        assert "조정대상지역_취득시: 해당" in text
tests\test_pipeline_cases.py:123:        assert "조정대상지역_양도시: 비해당" in text
tests\test_pipeline_cases.py:136:    def test_rollover_taxation_populated(self):
tests\test_pipeline_cases.py:137:        rt = self.query.fact_vector.special_cases.rollover_taxation
tests\test_pipeline_cases.py:139:        assert rt.is_gift_from_spouse_or_lineal is True
tests\test_pipeline_cases.py:140:        assert rt.gift_date == date(2022, 5, 10)
tests\test_pipeline_cases.py:145:        rt = self.query.fact_vector.special_cases.rollover_taxation
tests\test_pipeline_cases.py:173:        is_gift_from_spouse_or_lineal=True + gift_date 있음 → rollover_taxation 생성(partial).
tests\test_pipeline_cases.py:174:        fact_checker 규칙 #2: rt.is_gift_from_spouse_or_lineal=True + 5년 이내
tests\test_pipeline_cases.py:178:            "is_gift_from_spouse_or_lineal": True,
tests\test_pipeline_cases.py:196:        assert sc.is_temporary_two_house is True
tests\test_pipeline_cases.py:211:        # 고가주택 미확인 flag: transfer_price 제공됐으므로 없어야 함
src\api\sample_cases.py:19:            "transfer_price": 900000000,
src\api\sample_cases.py:23:            "is_adjustment_area_at_acquisition": True,
src\api\sample_cases.py:24:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:36:            "transfer_price": 700000000,
src\api\sample_cases.py:39:            "is_adjustment_area_at_acquisition": False,
src\api\sample_cases.py:40:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:52:            "transfer_price": 850000000,
src\api\sample_cases.py:55:            "is_adjustment_area_at_acquisition": True,
src\api\sample_cases.py:56:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:70:            "transfer_price": 1800000000,
src\api\sample_cases.py:74:            "is_adjustment_area_at_acquisition": True,
src\api\sample_cases.py:75:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:87:            "transfer_price": 1300000000,
src\api\sample_cases.py:91:            "is_adjustment_area_at_acquisition": False,
src\api\sample_cases.py:92:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:106:            "transfer_price": 700000000,
src\api\sample_cases.py:110:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:122:            "transfer_price": 400000000,
src\api\sample_cases.py:126:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:140:            "transfer_price": 800000000,
src\api\sample_cases.py:144:            "is_adjustment_area_at_acquisition": True,
src\api\sample_cases.py:145:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:157:            "transfer_price": 1100000000,
src\api\sample_cases.py:161:            "is_adjustment_area_at_acquisition": True,
src\api\sample_cases.py:162:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:174:            "transfer_price": 500000000,
src\api\sample_cases.py:178:            "is_adjustment_area_at_acquisition": False,
src\api\sample_cases.py:179:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:193:            "transfer_price": 950000000,
src\api\sample_cases.py:196:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:201:                    "new_is_adjustment_area": True,
src\api\sample_cases.py:215:            "transfer_price": 900000000,
src\api\sample_cases.py:218:            "is_adjustment_area_at_acquisition": True,
src\api\sample_cases.py:219:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:224:                    "new_is_adjustment_area": True,
src\api\sample_cases.py:240:            "transfer_price": 800000000,
src\api\sample_cases.py:243:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:245:                "inheritance": {
src\api\sample_cases.py:263:            "transfer_price": 600000000,
src\api\sample_cases.py:266:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:268:                "inheritance": {
src\api\sample_cases.py:289:            "transfer_price": 900000000,
src\api\sample_cases.py:293:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:295:                "gift": {
src\api\sample_cases.py:296:                    "is_gift_from_spouse_or_lineal": True,
src\api\sample_cases.py:312:            "transfer_price": 1100000000,
src\api\sample_cases.py:316:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:318:                "gift": {
src\api\sample_cases.py:319:                    "is_gift_from_spouse_or_lineal": True,
src\api\sample_cases.py:335:            "transfer_price": 450000000,
src\api\sample_cases.py:340:                "gift": {
src\api\sample_cases.py:341:                    "is_gift_from_spouse_or_lineal": False,
src\api\sample_cases.py:357:            "transfer_price": 750000000,
src\api\sample_cases.py:360:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:381:            "transfer_price": 600000000,
src\api\sample_cases.py:384:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:396:            "transfer_price": 550000000,
src\api\sample_cases.py:399:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:413:            "transfer_price": 1000000000,
src\api\sample_cases.py:416:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:430:            "transfer_price": 950000000,
src\api\sample_cases.py:433:            "is_adjustment_area_at_acquisition": True,
src\api\sample_cases.py:434:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:437:                    "contract_date": "20220301",
src\api\sample_cases.py:457:            "transfer_price": 700000000,
src\api\sample_cases.py:461:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:464:                    "registration_date": "20140801",
src\api\sample_cases.py:483:            "transfer_price": 800000000,
src\api\sample_cases.py:487:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:499:            "transfer_price": 1200000000,
src\api\sample_cases.py:517:            "transfer_price": 900000000,
src\api\sample_cases.py:520:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:534:            "transfer_price": 800000000,
src\api\sample_cases.py:539:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:553:            "transfer_price": 850000000,
src\api\sample_cases.py:556:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:571:            "transfer_price": 650000000,
src\api\sample_cases.py:574:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:591:            "transfer_price": 800000000,
src\api\sample_cases.py:594:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:608:            "transfer_price": 950000000,
src\api\sample_cases.py:612:            "is_adjustment_area_at_transfer": False,
src\api\sample_cases.py:626:            "transfer_price": 700000000,
src\api\sample_cases.py:629:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:645:            "is_adjustment_area_at_transfer": True,
src\api\sample_cases.py:657:            "transfer_price": 650000000,
src\api\sample_cases.py:659:            "is_adjustment_area_at_transfer": False,
src\infra\pinecone_client.py:2:Pinecone Serverless 클라이언트 — 인덱스 싱글톤 + 검색 헬퍼.
src\infra\pinecone_client.py:10:from pinecone import Pinecone
src\infra\pinecone_client.py:22:    """Pinecone 인덱스 싱글톤."""
src\infra\pinecone_client.py:27:        pc = Pinecone(api_key=PINECONE_API_KEY)
src\ui.py:26:    "transfer_price": "양도가액",
src\ui.py:30:    "is_adjustment_area_at_transfer": "양도시 조정대상지역",
src\ui.py:31:    "is_adjustment_area_at_acquisition": "취득시 조정대상지역",
src\ui.py:32:    "is_gift_from_spouse_or_lineal": "배우자/직계존비속 증여",
src\ui.py:234:            from src.api.chat_api import chat_turn
src\ui.py:235:            result = asyncio.run(chat_turn(
src\eval\eval.py:13:from src.domain.query_enrichment import enrich_raw_query_text, detect_flags_from_text
src\domain\pipeline.py:6:        query=RAGQueryInput.from_fact_ledger(...),
src\domain\pipeline.py:17:from .fact_checker import FactCheckResult, check_facts
src\domain\pipeline.py:18:from .output_validator import validate_output
src\domain\pipeline.py:19:from .query_enrichment import build_rag_query
src\domain\pipeline.py:20:from .query_input import RAGQueryInput
src\domain\pipeline.py:36:    query: RAGQueryInput,
src\domain\pipeline.py:44:    L1: schema validation — RAGQueryInput 생성 시 이미 처리됨
tests\test_rag.py:8:# Pinecone/임베딩 없이 단위 테스트 가능하도록 모킹
tests\test_rag.py:88:        warnings=["조정대상지역 여부 미확인"],
tests\test_rag.py:99:@patch("src.rag._get_reranker")
tests\test_rag.py:100:def test_retrieve_returns_law_chunks(mock_reranker, mock_embed, mock_index):
tests\test_rag.py:107:    # Pinecone 결과 모킹
tests\test_rag.py:121:    mock_reranker_instance = MagicMock()
tests\test_rag.py:122:    mock_reranker_instance.predict.return_value = [0.95]
tests\test_rag.py:123:    mock_reranker.return_value = mock_reranker_instance
tests\test_rag.py:135:@patch("src.rag._get_reranker")
tests\test_rag.py:136:def test_retrieve_returns_chunk_ids_not_just_text(mock_reranker, mock_embed, mock_index):
tests\test_rag.py:150:    mock_reranker_instance = MagicMock()
tests\test_rag.py:151:    mock_reranker_instance.predict.return_value = [0.8]
tests\test_rag.py:152:    mock_reranker.return_value = mock_reranker_instance
tests\test_rag.py:203:@patch("src.rag._get_reranker")
tests\test_rag.py:204:def test_reranker_is_called_before_final_selection(mock_reranker, mock_embed, mock_index):
tests\test_rag.py:205:    """BGE reranker가 반드시 호출됨 (최종 선택 전)"""
tests\test_rag.py:218:    mock_reranker_instance = MagicMock()
tests\test_rag.py:219:    mock_reranker_instance.predict.return_value = [0.9, 0.8, 0.7, 0.6, 0.5]
tests\test_rag.py:220:    mock_reranker.return_value = mock_reranker_instance
tests\test_rag.py:224:    mock_reranker_instance.predict.assert_called_once()
src\ingestion\collect.py:241:            # effective_date=0, expiration_date=99991231 → Pinecone 날짜 필터에서 항상 통과
src\domain\query_enrichment.py:19:from .query_input import RAGQueryInput
src\domain\query_enrichment.py:132:def build_rag_query(query_input: RAGQueryInput, danger_flags: List[str]) -> str:
src\domain\query_enrichment.py:134:    RAGQueryInput → 최종 RAG 검색 텍스트.
src\infra\reranker.py:14:BGE_RERANKER_MODEL = os.getenv("BGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
src\infra\reranker.py:16:_reranker: Optional[CrossEncoder] = None
src\infra\reranker.py:19:def get_reranker() -> CrossEncoder:
src\infra\reranker.py:20:    """BGE reranker 싱글톤."""
src\infra\reranker.py:21:    global _reranker
src\infra\reranker.py:22:    if _reranker is None:
src\infra\reranker.py:24:        _reranker = CrossEncoder(BGE_RERANKER_MODEL)
src\infra\reranker.py:26:    return _reranker
src\infra\reranker.py:36:    candidates: Pinecone matches (id, metadata) — metadata.full_text 사용.
src\infra\reranker.py:40:    reranker = get_reranker()
src\infra\reranker.py:42:    scores = reranker.predict(pairs)
src\api\schema.py:16:    contract_date: Optional[str] = None     # 계약일 — 부칙 경과조치 기준
src\api\schema.py:17:    balance_payment_date: Optional[str] = None  # 잔금일 — 실질 양도일 판단
src\api\schema.py:41:    is_joint_inheritance: bool = False      # 공동상속 여부
src\api\schema.py:42:    inheritance_share_pct: Optional[float] = None  # 지분율 (공동상속 시)
src\api\schema.py:50:    gift_date: str                          # 증여일 YYYYMMDD
src\api\schema.py:51:    is_gift_from_spouse_or_lineal: bool     # 배우자·직계존비속 여부 → 이월과세 트리거
src\api\schema.py:90:    new_house_is_adjustment_area: bool      # 신규주택 조정대상지역 여부
src\api\schema.py:97:    local_gov_registration_date: str        # 지자체 임대사업자 등록일
src\api\schema.py:114:    contract_date: str                      # 상생임대차계약 체결일
src\api\schema.py:132:            and "20211220" <= self.contract_date.replace("-", "") <= "20241231"
src\api\schema.py:188:    transfer_price: Optional[int] = None      # 양도가액 (원)
src\api\schema.py:193:    # 업스트림이 산정 전 원시값을 보내면 fact_checker가 산입/제외 판단
src\api\schema.py:197:    # ── 조정대상지역 (시점 분리) ──────────────────────────────────────────────
src\api\schema.py:198:    is_adjustment_area_at_acquisition: Optional[bool] = None  # 취득일 기준
src\api\schema.py:199:    is_adjustment_area_at_transfer: Optional[bool] = None     # 양도일 기준
src\api\schema.py:213:        "inheritance",          # 상속
src\api\schema.py:214:        "gift",                 # 증여
src\api\schema.py:221:    # fact_checker가 이 플래그로 required 상세 모델 존재 여부 검증
src\api\schema.py:232:    inheritance_detail: Optional[InheritanceDetail] = None
src\api\schema.py:233:    gift_detail: Optional[GiftDetail] = None
src\api\schema.py:256:        if self.acquisition_reason == "inheritance" and not self.inheritance_detail:
src\api\schema.py:257:            errors.append("acquisition_reason=inheritance → inheritance_detail 필수")
src\api\schema.py:259:        if self.acquisition_reason == "gift" and not self.gift_detail:
src\api\schema.py:260:            errors.append("acquisition_reason=gift → gift_detail 필수")
src\retrieval\retriever_impl.py:2:PineconeTaxLawRetriever — TaxLawRetriever ABC 의 Pinecone 구현.
src\retrieval\retriever_impl.py:4:Pinecone 메타데이터 ↔ LawChunkMetadata 매핑을 담당한다.
src\retrieval\retriever_impl.py:24:from src.domain.query_input import RAGQueryInput
src\retrieval\retriever_impl.py:28:from src.infra.reranker import rerank
src\retrieval\retriever_impl.py:66:    """Pinecone match.metadata → LawChunkMetadata 로 변환."""
src\retrieval\retriever_impl.py:90:class PineconeTaxLawRetriever(TaxLawRetriever):
src\retrieval\retriever_impl.py:91:    """Pinecone + BGE Reranker 기반 TaxLawRetriever 구현."""
src\retrieval\retriever_impl.py:103:    def retrieve(self, query: RAGQueryInput) -> List[RetrievedChunk]:
src\retrieval\retriever_impl.py:110:        # Stage 1 — Symbolic Filter: 양도일 기준 날짜 범위 (Pinecone 숫자 필터)
src\retrieval\retriever_impl.py:138:        # Stage 1 보강 — entity_scope 후필터 (Pinecone entity_scopes 메타데이터 기반)
src\ingestion\embed.py:2:임베딩 + Pinecone 업로드 스크립트
src\ingestion\embed.py:3:data/processed/all_chunks.json → Pinecone Serverless
src\ingestion\embed.py:13:from pinecone import Pinecone, ServerlessSpec
src\ingestion\embed.py:28:BATCH_SIZE = 100  # Pinecone upsert 배치 크기
src\ingestion\embed.py:118:def _get_or_create_index(pc: Pinecone, dimension: int):
src\ingestion\embed.py:119:    """Pinecone 인덱스 조회 또는 생성"""
src\ingestion\embed.py:141:    JSON 청크 파일을 읽어 임베딩 후 Pinecone에 업로드.
src\ingestion\embed.py:163:    # Pinecone 인덱스
src\ingestion\embed.py:164:    pc = Pinecone(api_key=PINECONE_API_KEY)
src\ingestion\embed.py:171:    for batch in tqdm(batches, desc="Pinecone 업로드"):
src\ingestion\embed.py:189:                # Pinecone $lte/$gte는 숫자 타입 전용 — YYYYMMDD 정수로 저장
src\ingestion\embed.py:199:                # Pinecone 벡터당 메타데이터 한도 40KB — 4000자까지 저장 (reranker + LLM 모두 이 필드 사용)
src\infra\__init__.py:1:"""외부 서비스 클라이언트 — 임베딩, Pinecone, Reranker."""
src\domain\query_input.py:5:- transfer_price 추가 → 고가주택(12억 초과) 판단 가능
src\domain\query_input.py:7:- 조정대상지역 취득시/양도시 명시적 분리 유지
src\domain\query_input.py:44:    GIFT = "gift"
src\domain\query_input.py:45:    INHERITANCE = "inheritance"
src\domain\query_input.py:126:    contract_date: Optional[date] = None
src\domain\query_input.py:127:    balance_payment_date: Optional[date] = None   # 잔금청산일
src\domain\query_input.py:128:    registration_date: Optional[date] = None      # 등기접수일
src\domain\query_input.py:135:            "contract_date": self.contract_date,
src\domain\query_input.py:136:            "balance_payment_date": self.balance_payment_date,
src\domain\query_input.py:137:            "registration_date": self.registration_date,
src\domain\query_input.py:177:    조정대상지역 여부에 따라 기한이 달라짐(1년 vs 3년).
src\domain\query_input.py:181:    new_is_adjustment_area: bool     # 신규주택이 조정대상지역인지
src\domain\query_input.py:205:    is_joint_inheritance: bool = False
src\domain\query_input.py:206:    inheritance_share_pct: float = 100.0   # 본인 지분율 (%)
src\domain\query_input.py:219:    registration_date: date               # 임대사업자 등록일
src\domain\query_input.py:242:    조정대상지역 내 주택이라도 상생임대 5개 요건을 모두 충족하면
src\domain\query_input.py:250:    ⑤ 양도 시점 조정대상지역 — (RAGQueryInput.fact_vector에서 확인)
src\domain\query_input.py:252:    ①~④는 이 객체에서 검증. ⑤는 adjustment_area_at_transfer로 확인.
src\domain\query_input.py:254:    contract_date: date              # 상생임대차계약 체결일
src\domain\query_input.py:268:        return SANGSAENG_WINDOW_START <= self.contract_date <= SANGSAENG_WINDOW_END
src\domain\query_input.py:365:    L2 fact_checker가 원취득 정보 누락을 critical missing으로 차단한다.
src\domain\query_input.py:367:    is_gift_from_spouse_or_lineal: bool      # 배우자/직계존비속 증여 여부
src\domain\query_input.py:368:    gift_date: date                          # 증여일
src\domain\query_input.py:375:        return 10 if self.gift_date >= date(2023, 1, 1) else 5
src\domain\query_input.py:380:        return self.is_gift_from_spouse_or_lineal
src\domain\query_input.py:433:# ── SpecialCaseFlags ───────────────────────────────────────────────────────
src\domain\query_input.py:437:class SpecialCaseFlags:
src\domain\query_input.py:443:    is_temporary_two_house: bool = False
src\domain\query_input.py:447:    inheritance: Optional[InheritanceDetail] = None
src\domain\query_input.py:467:    donor_same_household_at_gift: Optional[bool] = None
src\domain\query_input.py:477:    rollover_taxation: Optional[RolloverTaxationDetail] = None
src\domain\query_input.py:511:        if self.is_temporary_two_house:
src\domain\query_input.py:539:        if self.rollover_taxation and self.rollover_taxation.iota_applies:
src\domain\query_input.py:540:            period = self.rollover_taxation.iota_period_years
src\domain\query_input.py:596:    transfer_price: Optional[int] = None      # 양도가액 (원)
src\domain\query_input.py:599:    # --- 조정대상지역 (시점별 분리 — 판단 기준이 다름) ---
src\domain\query_input.py:602:    adjustment_area_at_acquisition: bool = False
src\domain\query_input.py:603:    adjustment_area_at_transfer: bool = False
src\domain\query_input.py:612:    special_cases: SpecialCaseFlags = field(default_factory=SpecialCaseFlags)
src\domain\query_input.py:629:        if self.transfer_price is None:
src\domain\query_input.py:631:        return self.transfer_price > HIGH_VALUE_THRESHOLD
src\domain\query_input.py:646:        if self.transfer_price is not None:
src\domain\query_input.py:648:            lines.append(f"양도가액: {self.transfer_price:,}원 ({label})")
src\domain\query_input.py:652:        # 조정대상지역 — 취득시/양도시 명시
src\domain\query_input.py:654:            f"조정대상지역_취득시: {'해당' if self.adjustment_area_at_acquisition else '비해당'}"
src\domain\query_input.py:657:            f"조정대상지역_양도시: {'해당' if self.adjustment_area_at_transfer else '비해당'}"
src\domain\query_input.py:680:        rt = self.special_cases.rollover_taxation
src\domain\query_input.py:749:# ── RAGQueryInput ──────────────────────────────────────────────────────────
src\domain\query_input.py:753:class RAGQueryInput:
src\domain\query_input.py:778:    ) -> "RAGQueryInput":
src\domain\query_input.py:780:        기존 DB 레코드에서 RAGQueryInput 생성.
src\domain\query_input.py:802:        contract_date=_pd(up.get("contract_date")),
src\domain\query_input.py:803:        balance_payment_date=_pd(up.get("balance_payment_date")),
src\domain\query_input.py:804:        registration_date=_pd(up.get("registration_date")),
src\domain\query_input.py:819:def _build_special_cases(fl: dict, up: dict) -> SpecialCaseFlags:
src\domain\query_input.py:820:    sc = SpecialCaseFlags()
src\domain\query_input.py:823:    if fl.get("is_temporary_two_house"):
src\domain\query_input.py:824:        sc.is_temporary_two_house = True
src\domain\query_input.py:829:                new_is_adjustment_area=bool(fl.get("temp_new_is_adjustment_area")),
src\domain\query_input.py:836:    is_inheritance_acquisition = up.get("acquisition_cause") == "상속"
src\domain\query_input.py:837:    has_inheritance_flags = "selling_inherited_house" in fl
src\domain\query_input.py:838:    if is_inheritance_acquisition or has_inheritance_flags:
src\domain\query_input.py:842:            sc.inheritance = InheritanceDetail(
src\domain\query_input.py:851:                    fl.get("selling_inherited_house", is_inheritance_acquisition)
src\domain\query_input.py:874:        if rd := _pd(up.get("rental_registration_date")):
src\domain\query_input.py:876:                registration_date=rd,
src\domain\query_input.py:884:        if cd := _pd(fl.get("sangsaeng_contract_date") or up.get("sangsaeng_contract_date")):
src\domain\query_input.py:886:                contract_date=cd,
src\domain\query_input.py:921:    # 이월과세 — is_gift_from_spouse_or_lineal=True가 명시된 경우에만 생성
src\domain\query_input.py:923:    # → fact_checker Rule #2가 "is_gift_from_spouse_or_lineal" 재확인 요청
src\domain\query_input.py:924:    if fl.get("is_gift_from_spouse_or_lineal"):
src\domain\query_input.py:925:        gd = _pd(up.get("gift_date") or fl.get("gift_date"))
src\domain\query_input.py:927:            sc.rollover_taxation = RolloverTaxationDetail(
src\domain\query_input.py:928:                is_gift_from_spouse_or_lineal=True,
src\domain\query_input.py:929:                gift_date=gd,
src\domain\query_input.py:992:def _build_fact_vector(op: dict, up: dict, sc: SpecialCaseFlags, fl: dict | None = None) -> FactVector:
src\domain\query_input.py:1016:        transfer_price=_parse_int(up.get("sale_price_total")),
src\domain\query_input.py:1018:        adjustment_area_at_acquisition=bool(up.get("adjustment_area_at_acquisition")),
src\domain\query_input.py:1019:        adjustment_area_at_transfer=bool(up.get("adjustment_area_at_transfer")),
src\eval\retrieval_analyzer.py:23:from src.domain.query_enrichment import DANGER_KEYWORD_MAP, detect_flags_from_text
src\eval\retrieval_analyzer.py:52:    """Pinecone에서 chunk_id → full_text 맵 반환. 실패 시 빈 dict."""
src\eval\retrieval_analyzer.py:177:    # Pinecone에서 누락 chunk 텍스트 fetch
src\eval\retrieval_analyzer.py:253:    from src.domain.query_enrichment import DANGER_KEYWORD_MAP
src\eval\retrieval_analyzer.py:271:        # 패치 파일에 누적 저장 — 재시작 후 query_enrichment._load_keyword_patch()에서 재적용
src\domain\retriever.py:5:Stage 2: VectorRanker — 임베딩 유사도 + reranker로 최종 선택.
src\domain\retriever.py:15:from .query_input import DateBundle, RAGQueryInput
src\domain\retriever.py:31:        query: RAGQueryInput,
src\domain\retriever.py:37:    """Stage 2 — 벡터 검색 + reranker."""
src\domain\retriever.py:40:        query: RAGQueryInput,
src\domain\retriever.py:49:    def retrieve(self, query: RAGQueryInput) -> List[RetrievedChunk]:
src\domain\retriever.py:52:    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:

codex
현재 구조를 보니 이미 `contract_date`/`balance_payment_date`/`registration_date` 일부가 도메인 모델에 들어가 있고, `admin_notices.py`도 조정대상지역 스켈레톤이 있습니다. 다음으로 파이프라인 차단 지점과 하드코딩 상수 위치를 확인해서, 어떤 항목이 신규 구현이고 어떤 항목은 확장인지 분리하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\pipeline.py | Select-Object -First 220" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\query_input.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\ingestion\\admin_notices.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\fact_checker.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
 succeeded in 3571ms:
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
from typing import Any, Awaitable, Callable, List, Optional, Set

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
    debate_record: Optional[dict] = None   # ?쇱웳???ㅽ뻾??寃쎌슦 寃곌낵 ?붿빟


async def run_rag_pipeline(
    query: RAGQueryInput,
    retriever: TaxLawRetriever,
    llm_fn: Callable[[str, List[RetrievedChunk], List[str]], Awaitable[TaxAnswer]],
    fact_json: Optional[dict] = None,
    enable_debate: bool = False,
    debate_auto_promote: bool = True,
) -> PipelineResult:
    """
    L1: schema validation ??RAGQueryInput ?앹꽦 ???대? 泥섎━??
    L2: fact completeness check
    L3: query enrichment
    L4: RAG + LLM
    L5: output validation
    """

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
    )

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

 succeeded in 3593ms:
"""
RAG 荑쇰━ ?낅젰 ?ㅽ궎留????ъ떎愿怨???踰뺣졊 寃???낅젰媛?

而ㅻ쾭由ъ? 媛?諛섏쁺 (v3):
- transfer_price 異붽? ??怨좉?二쇳깮(12??珥덇낵) ?먮떒 媛??
- PropertyType enum ??遺꾩뼇沅??낆＜沅??ㅺ?援?寃몄슜二쇳깮 援щ텇
- 議곗젙??곸???痍⑤뱷???묐룄??紐낆떆??遺꾨━ ?좎?
- residence_periods 蹂듭닔 湲곌컙 ???⑹궛 2??怨꾩궛 媛??
- ?밸?蹂??곸꽭 dataclass ???쇱떆??二쇳깮/?곸냽/?κ린?꾨?/?쇱씤?⑹궛
- DateBundle??愿由ъ쿂遺꾧퀎?띿씤媛??異붽? ??議고빀?먯엯二쇨텒
- SangsaengRentalDetail ???곸깮?꾨? 5媛??붽굔 寃利?(?뚮졊 짠155??)
- ResidenceExemptionType ??嫄곗＜?붽굔 硫댁젣/?⑥텞 ?밸? ?듯빀 愿由?
  (?곸깮?꾨? / ?꾨??ъ뾽?먭굅二쇱＜??/ ?댁쇅?댁＜ / 痍⑦븰洹쇰Т / ?섏슜)
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
    MANAGEMENT_DISPOSAL_APPROVED = "愿由ъ쿂遺꾧퀎?띿씤媛??  # 議고빀?먯엯二쇨텒 湲곗궛??
    EXPROPRIATION_DECIDED = "?섏슜寃곗젙??
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
    balance_payment_date: Optional[date] = None   # ?붽툑泥?궛??
    registration_date: Optional[date] = None      # ?깃린?묒닔??
    special_event_dates: List[SpecialEventDate] = field(default_factory=list)

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

    寃쎈줈 A (?뚮졊 짠155??: ?곸냽二쇳깮 + ?쇰컲二쇳깮 ?숈떆 蹂댁쑀 ???쇰컲二쇳깮 ?묐룄 ??鍮꾧낵??
    寃쎈줈 B (?뚮졊 짠155??: ?곸냽二쇳깮 ?먯껜 ?묐룄 ???쇱긽?띿씤 蹂댁쑀湲곌컙 ?⑹궛
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
    registration_date: date               # ?꾨??ъ뾽???깅줉??
    mandatory_period_years: int           # ?섎Т?꾨?湲곌컙 (4/8/10??
    mandatory_period_fulfilled: bool      # ?섎Т?꾨?湲곌컙 異⑹” ?щ?
    rent_increase_limit_complied: bool    # ?꾨?猷?5% 利앹븸 ?쒗븳 以???щ?


class ResidenceExemptionType(str, Enum):
    """
    嫄곗＜?붽굔(2?? 硫댁젣 ?먮뒗 ?⑥텞 ?밸? ?좏삎.
    ?대떦 ??RAG 荑쇰━??議곕Ц ?ㅼ썙?쒕? 紐낆떆?곸쑝濡??ы븿?댁빞 ??
    """
    SANGSAENG_RENTAL = "?곸깮?꾨?"              # ?뚮졊 짠155?? ??嫄곗＜?붽굔 ?꾨㈃ 硫댁젣
    RENTAL_BUSINESS_OWN_HOUSE = "?꾨??ъ뾽?먭굅二쇱＜??  # ?뚮졊 짠155????2??嫄곗＜ ?좎?
    OVERSEAS_EMIGRATION = "?댁쇅?댁＜"           # ?뚮졊 짠154??????嫄곗＜?붽굔 硫댁젣
    UNAVOIDABLE_RELOCATION = "痍⑦븰洹쇰Т遺?앹씠"  # ?뚮졊 짠154?? ??1???댁긽 嫄곗＜ ??硫댁젣
    EXPROPRIATION = "?섏슜"                    # ?뚮졊 짠154?? ??嫄곗＜?붽굔 硫댁젣


@dataclass
class SangsaengRentalDetail:
    """
    ?곸깮?꾨?二쇳깮 ?밸? (?뚮뱷?몃쾿 ?쒗뻾??짠155??, 2022.02.15 ?좎꽕).

    議곗젙??곸?????二쇳깮?대씪???곸깮?꾨? 5媛??붽굔??紐⑤몢 異⑹”?섎㈃
    1?몃? 1二쇳깮 鍮꾧낵?몄쓽 '嫄곗＜湲곌컙 2?? ?붽굔??硫댁젣??

    ?붽굔:
    ??怨꾩빟 泥닿껐?? SANGSAENG_WINDOW_START ~ SANGSAENG_WINDOW_END
    ??吏곸쟾 ?꾨?李④퀎??議댁옱 (?좉퇋 ?꾩감??遺덇?)
    ???꾨?猷??몄긽瑜?5% ?대궡
    ???ㅼ젣 ?꾨?湲곌컙 2???댁긽
    ???묐룄 ?쒖젏 議곗젙??곸?????(RAGQueryInput.fact_vector?먯꽌 ?뺤씤)

    ???ｋ뒗 ??媛앹껜?먯꽌 寃利? ?ㅻ뒗 adjustment_area_at_transfer濡??뺤씤.
    """
    contract_date: date              # ?곸깮?꾨?李④퀎??泥닿껐??
    contract_period_months: int      # ?ㅼ젣 ?꾨?湲곌컙 (????
    previous_monthly_rent: int       # 吏곸쟾 怨꾩빟 ?붿꽭 (?꾩꽭???섏궛?붿꽭)
    new_monthly_rent: int            # ?곸깮?꾨? 怨꾩빟 ?붿꽭
    has_prior_contract: bool         # 吏곸쟾 ?꾨?李④퀎??議댁옱 ?щ? (?붽굔 ??

    @property

 succeeded in 3598ms:
"""
?됱젙 怨좎떆 ?섏쭛 紐⑤뱢

?섏쭛 踰붿쐞 ?뺤옣 濡쒕뱶留?
  ???몃쾿   : law.go.kr           ??src/ingestion/collect.py  (湲곌뎄??
  ???됱젙   : 援?넗遺/MOEF 怨좎떆    ????紐⑤뱢 (議곗젙??곸??? ?ш린怨쇱뿴吏援? 怨듭떆吏媛 湲곗?)
  ??湲덉쑖   : 湲덉쑖??湲덇컧??怨좎떆  ????紐⑤뱢 (DSR, LTV, ?밸?蹂닿툑?먮━濡??쒕룄)

愿怨꾨?泥??⑸룞 諛쒗몴 ?⑦꽩:
  遺?숈궛 ?梨?= 湲고쉷?ъ젙遺 + 援?넗援먰넻遺 + 湲덉쑖?꾩썝???숈떆 諛쒗몴
  ?????몄젣(collect.py) + ???됱젙(??紐⑤뱢) + ??湲덉쑖(??紐⑤뱢)???④퍡 ?섏쭛?댁빞
    "鍮꾧낵???붽굔 + ?꾩옱 議곗젙??곸????щ? + DSR 洹쒖젣" ?듯빀 ?곷떞??媛?ν븿

API ?곕룞 ?꾪솴:
  ??議곗젙??곸??? 援?넗援먰넻遺 怨듦났?곗씠?고룷??API (TODO: MOEF_API_KEY 諛쒓툒)
  ???ш린怨쇱뿴吏援? ?숈씪 API
  ??湲덉쑖洹쒖젣:     湲덉쑖?꾩썝??OpenAPI (TODO: FSC_API_KEY 諛쒓툒)

?섍꼍蹂??
  MOEF_API_KEY=   # 援?넗援먰넻遺 怨듦났?곗씠?고룷??API ??  FSC_API_KEY=    # 湲덉쑖?꾩썝??OpenAPI ??  ADMIN_NOTICES_DIR=data/admin_notices  # ?섏쭛 寃곌낵 ???寃쎈줈
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

MOEF_API_KEY = os.getenv("MOEF_API_KEY", "")
FSC_API_KEY = os.getenv("FSC_API_KEY", "")
NOTICES_DIR = Path(os.getenv("ADMIN_NOTICES_DIR", "data/admin_notices"))


# ?? ?곗씠??紐⑤뜽 ????????????????????????????????????????????????????????????????


@dataclass
class AdjustmentAreaRecord:
    """
    議곗젙??곸???/ ?ш린怨쇱뿴吏援??④굔 ?덉퐫??

    ?몃쾿 ?곸슜 湲곗?:
      - 痍⑤뱷??湲곗? 議곗젙??곸????щ? ??2??嫄곗＜?붽굔 諛쒖깮 (?뚮졊 짠154??
      - ?묐룄??湲곗? 議곗젙??곸????щ? ???ㅼ＜??以묎낵?몄쑉 ?곸슜 (?뚮쾿 짠104??
      ???좎쭨瑜?蹂꾨룄濡?議고쉶?댁빞 ??
    """
    region: str                         # 吏??챸 ("?쒖슱?밸퀎??媛뺣궓援? ??
    area_type: str                      # "議곗젙??곸??? | "?ш린怨쇱뿴吏援? | "?ш린吏??
    designated_at: date                 # 吏?뺤씪
    released_at: Optional[date]         # ?댁젣??(None = ?꾩옱 ?좏슚)
    announcement_no: str                # 怨좎떆 踰덊샇 ("援?넗援먰넻遺怨좎떆 ??021-1588?? ??
    source_url: Optional[str] = None    # ?먮Ц URL

    @property
    def is_active(self) -> bool:
        return self.released_at is None

    def is_designated_as_of(self, target_date: date) -> bool:
        """target_date ?쒖젏????吏??씠 吏???곹깭??붿? ?뺤씤."""
        return (
            self.designated_at <= target_date
            and (self.released_at is None or self.released_at > target_date)
        )


@dataclass
class FinancialRegulationRecord:
    """
    湲덉쑖 洹쒖젣 ?④굔 ?덉퐫??(DSR/LTV/蹂닿툑?먮━濡???.

    ?뺤옣 紐⑺몴:
      - DSR 40% ??湲덉쑖沅??곸슜 (2022.07~)
      - LTV 吏??퀎/二쇳깮?섎퀎 李⑤벑
      - ?밸?蹂닿툑?먮━濡??쒕룄 諛??곸슜 湲곌컙
      - ?뺤콉紐④린吏 湲덈━
    """
    regulation_type: str        # "DSR" | "LTV" | "蹂닿툑?먮━濡? | "?뺤콉湲덈━"
    target: str                 # ?곸슜 ???("??湲덉쑖沅?, "媛뺣궓3援?, ...)
    value: str                  # 洹쒖젣媛?("40%", "50%", ...)
    effective_from: date
    effective_to: Optional[date]
    announcement_no: str
    source_url: Optional[str] = None


@dataclass
class AdminNoticesDB:
    """
    ?섏쭛???됱젙 怨좎떆 ?꾩껜 蹂닿???
    JSON ?뚯씪濡?吏곷젹?뷀빐 Pinecone怨?蹂꾨룄濡?愿由?
    """
    adjustment_areas: list[AdjustmentAreaRecord] = field(default_factory=list)
    financial_regulations: list[FinancialRegulationRecord] = field(default_factory=list)
    last_updated: Optional[str] = None


# ?? 議곗젙??곸???議고쉶 ?ы띁 ?????????????????????????????????????????????????????


def resolve_adjustment_area(region: str, target_date: date, db: AdminNoticesDB) -> bool:
    """
    region??target_date ?쒖젏??議곗젙??곸???씠?덈뒗吏 議고쉶.
    DB媛 鍮꾩뼱?덉쑝硫?False 諛섑솚 (?섏쭛 誘몄셿猷??곹깭).

    ?ъ슜泥?
      - L1 RAGQueryInput ?앹꽦 ??adjustment_area_at_acquisition / _at_transfer 怨꾩궛
      - fact_input.py FlatFactInput ??RAGQueryInput 蹂????    """
    for rec in db.adjustment_areas:
        if rec.area_type == "議곗젙??곸??? and rec.region in region:
            if rec.is_designated_as_of(target_date):
                return True
    return False


def load_db() -> AdminNoticesDB:
    """??λ맂 DB 濡쒕뱶. ?뚯씪 ?놁쑝硫?鍮?DB 諛섑솚."""
    path = NOTICES_DIR / "admin_notices_db.json"
    if not path.exists():
        return AdminNoticesDB()
    raw = json.loads(path.read_text(encoding="utf-8"))

    areas = [
        AdjustmentAreaRecord(
            region=r["region"],
            area_type=r["area_type"],
            designated_at=date.fromisoformat(r["designated_at"]),
            released_at=date.fromisoformat(r["released_at"]) if r.get("released_at") else None,
            announcement_no=r["announcement_no"],
            source_url=r.get("source_url"),
        )
        for r in raw.get("adjustment_areas", [])
    ]
    fins = [
        FinancialRegulationRecord(
            regulation_type=r["regulation_type"],
            target=r["target"],
            value=r["value"],
            effective_from=date.fromisoformat(r["effective_from"]),
            effective_to=date.fromisoformat(r["effective_to"]) if r.get("effective_to") else None,
            announcement_no=r["announcement_no"],
            source_url=r.get("source_url"),
        )
        for r in raw.get("financial_regulations", [])
    ]
    return AdminNoticesDB(
        adjustment_areas=areas,
        financial_regulations=fins,
        last_updated=raw.get("last_updated"),
    )


def save_db(db: AdminNoticesDB) -> None:
    NOTICES_DIR.mkdir(parents=True, exist_ok=True)
    path = NOTICES_DIR / "admin_notices_db.json"

    def _serial(obj):
        if isinstance(obj, date):
            return obj.isoformat()
        return obj

    raw = {
        "adjustment_areas": [
            {k: _serial(v) for k, v in asdict(r).items()}
            for r in db.adjustment_areas
        ],
        "financial_regulations": [
            {k: _serial(v) for k, v in asdict(r).items()}
            for r in db.financial_regulations
        ],
        "last_updated": db.last_updated,
    }
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


# ?? ?섏쭛 ?ㅽ뀅 ??????????????????????????????????????????????????????????????????


async def collect_adjustment_areas() -> list[AdjustmentAreaRecord]:
    """
    援?넗援먰넻遺 怨듦났?곗씠?고룷??API?먯꽌 議곗젙??곸????꾪솴 ?섏쭛.

    API: data.go.kr > 援?넗援먰넻遺_?ш린怨쇱뿴吏援?룹“?뺣??곸???怨좎떆 ?꾪솴
    ?섍꼍蹂?? MOEF_API_KEY

    TODO:
      1. data.go.kr?먯꽌 API ??諛쒓툒 (MOEF_API_KEY)
      2. ?붾뱶?ъ씤???뺤씤 ???꾨옒 援ы쁽 梨꾩슦湲?      3. ?묐떟 ?뚯떛: region, designated_at, released_at, announcement_no 異붿텧
    """
    if not MOEF_API_KEY:
        raise EnvironmentError(
            "MOEF_API_KEY 誘몄꽕????data.go.kr?먯꽌 援?넗援먰넻遺 API ??諛쒓툒 ??.env??異붽?"
        )
    # TODO: implement
    # async with httpx.AsyncClient() as client:
    #     resp = await client.get(
    #         "https://api.data.go.kr/openapi/tn_pubr_public_aptrnk_ctprvn_api",
    #         params={"serviceKey": MOEF_API_KEY, "type": "json"},
    #     )
    raise NotImplementedError("援?넗援먰넻遺 API 援ы쁽 ?덉젙")


async def collect_financial_regulations() -> list[FinancialRegulationRecord]:
    """
    湲덉쑖?꾩썝??DSR/LTV 洹쒖젣 ?꾪솴 ?섏쭛.

    ???洹쒖젣:
      - DSR 40% (2022.07~ ??湲덉쑖沅? 珥앸?異?1??珥덇낵)
      - LTV: 臾댁＜??1二쇳깮/?ㅼ＜??횞 議곗젙/鍮꾩“??議고빀?쇰줈 6?④퀎
      - ?밸?蹂닿툑?먮━濡? ?쒕룄, 湲덈━, ?곸슜 湲곌컙

    TODO:
      1. 湲덉쑖??OpenAPI (fsc.go.kr) ?먮뒗 蹂대룄?먮즺 ?щ·留?      2. FSC_API_KEY 諛쒓툒 ??.env??異붽?
    """
    if not FSC_API_KEY:
        raise EnvironmentError(
            "FSC_API_KEY 誘몄꽕????fsc.go.kr?먯꽌 湲덉쑖?꾩썝??API ??諛쒓툒 ??.env??異붽?"
        )
    raise NotImplementedError("湲덉쑖?꾩썝??API 援ы쁽 ?덉젙")


async def run_collect_all() -> AdminNoticesDB:
    """
    ?꾩껜 ?됱젙/湲덉쑖 怨좎떆 ?섏쭛 ?ㅽ뻾.

    ?몃쾿 ?섏쭛(collect.py)怨??④퍡 二쇨린?곸쑝濡??ㅽ뻾:
      python -m src.ingestion.collect        # ?몃쾿
      python -m src.ingestion.admin_notices  # ?됱젙쨌湲덉쑖
    """
    import time
    db = load_db()

    try:
        areas = await collect_adjustment_areas()
        db.adjustment_areas = areas
        print(f"議곗젙??곸???{len(areas)}嫄??섏쭛 ?꾨즺")
    except NotImplementedError as e:
        print(f"[SKIP] 議곗젙??곸??? {e}")

    try:
        fins = await collect_financial_regulations()
        db.financial_regulations = fins
        print(f"湲덉쑖洹쒖젣 {len(fins)}嫄??섏쭛 ?꾨즺")
    except NotImplementedError as e:
        print(f"[SKIP] 湲덉쑖洹쒖젣: {e}")

    db.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    save_db(db)
    return db


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_collect_all())

 succeeded in 3597ms:
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

    # ?? 10. ?뱀닔愿怨꾩옄媛?嫄곕옒 ??遺?뱁뻾?꾧퀎?곕????꾪뿕 ?????????????????????
    # 李⑤떒?섏? ?딆쓬(鍮꾪겕由ы떚而? ??寃쎄퀬 ??吏꾪뻾. L5?먯꽌 expert_review_signal ?앹꽦.
    if fv.is_related_party_transaction:
        danger.append("?뱀닔愿怨꾩옄嫄곕옒")
        missing.append(MissingFact(
            field_name="related_party_transaction_details",
            reason=(
                "?뱀닔愿怨꾩옄 嫄곕옒 ?뺤씤 ???뚮뱷?몃쾿 짠101 遺?뱁뻾?꾧퀎?곕????곸슜 ??"
                "?묐룄媛?≪씠 ?쒓?濡??ш퀎?곕릺???묐룄李⑥씡쨌鍮꾧낵??踰붿쐞媛 ?щ씪吏????덉쓬"
            ),
            article_hint="?뚮뱷?몃쾿 짠101",
            is_critical=False,
        ))

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
    except (TypeError, AttributeError):
        return 0.0

codex
도메인 모델 쪽에서는 이미 날짜 번들과 일부 특례 데이터 구조가 준비돼 있지만, 기준값은 `query_input.py`에 하드코딩되어 있고 `admin_notices.py`는 아직 수집/정규화 계층이 비어 있습니다. `fact_input.py`도 실제 입력 필드와 도메인 모델 사이에 불일치가 있을 가능성이 보여서 그 지점을 추가로 확인합니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\api\\fact_input.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\api\\chat_api.py | Select-Object -First 220" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\retrieval\\retriever_impl.py | Select-Object -First 240" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content tests\\test_pipeline_cases.py | Select-Object -First 260" in c:\Users\user\cording2025\tax-rag
 succeeded in 3463ms:
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
) -> dict[str, Any]:
    """
    梨꾪똿 1??泥섎━ ?⑥닔. Streamlit UI?먯꽌 吏곸젒 ?몄텧 媛??

    fact_json ?덉쓬 ??L1-L5 ?뚯씠?꾨씪??(verdict ?ы븿)
    fact_json ?놁쓬 ???덇굅??answer_with_citations (?먯뿰??吏덈Ц)
    """
    sid = session_id or str(uuid.uuid4())[:8]

    if fact_json:
        # ?? L1-L5 ?뚯씠?꾨씪??寃쎈줈 ??????????????????????????????????????????
        from src.rag import answer_with_pipeline
        from src.api.fact_input import FactInput, fact_input_to_rag_query
        from src.domain.pipeline import run_rag_pipeline
        from src.retrieval.retriever_impl import PineconeTaxLawRetriever
        from src.retrieval.llm_fn import llm_fn
        from src.api.fact_input import FactInput

        query = fact_input_to_rag_query(FactInput(**fact_json))
        retriever = PineconeTaxLawRetriever()
        result = await run_rag_pipeline(
            query, retriever, llm_fn,
            fact_json=fact_json,
            enable_debate=enable_debate,
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

 succeeded in 3462ms:
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

 succeeded in 3470ms:
"""
梨꾪똿 紐⑤뱶??JSON ?ъ떎愿怨??낅젰 ?ㅽ궎留?諛?RAGQueryInput 蹂???⑺넗由?

?몃??먯꽌 ???뺤떇?쇰줈 ?ъ떎愿怨꾨? ?꾨떖?섎㈃ ?대? ?뚯씠?꾨씪??L1-L5)???숈옉?쒕떎.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, model_validator

from src.domain.query_input import RAGQueryInput


# ?? ?밸? ?곸꽭 (以묒꺽 JSON) ????????????????????????????????????????????????????

class TempTwoHouseInput(BaseModel):
    """?쇱떆??2二쇳깮 ?밸? ?곸꽭"""
    new_acquisition_date: str       # ?좉퇋二쇳깮 痍⑤뱷??YYYYMMDD
    old_house_must_sell_by: str     # 醫낆쟾二쇳깮 ?묐룄 湲고븳 YYYYMMDD
    new_is_adjustment_area: bool = False


class InheritanceInput(BaseModel):
    """?곸냽 ?곸꽭"""
    death_date: str                         # ?곸냽媛쒖떆??YYYYMMDD
    same_household_at_death: bool = False
    inherited_as_only_house: bool = False
    selling_inherited_house: bool = True    # True: ?곸냽二쇳깮 ?묐룄, False: ?쇰컲二쇳깮 ?묐룄
    donor_acquisition_date: Optional[str] = None


class GiftInput(BaseModel):
    """利앹뿬 ?곸꽭 (?댁썡怨쇱꽭 ?몃━嫄??щ? ?ы븿)"""
    is_gift_from_spouse_or_lineal: bool     # 諛곗슦?먃룹쭅怨꾩〈鍮꾩냽 ?щ?
    donor_acquisition_date: Optional[str] = None
    donor_acquisition_price: Optional[int] = None


class MarriageMergeInput(BaseModel):
    """?쇱씤?⑷? ?곸꽭"""
    marriage_date: str
    spouse_house_count_before_marriage: int = 1
    own_house_count_before_marriage: int = 1


class SangsaengRentalInput(BaseModel):
    """?곸깮?꾨? ?곸꽭 (?뚮졊 짠155??)"""
    contract_date: str              # ?곸깮?꾨?李④퀎??泥닿껐??YYYYMMDD
    contract_period_months: int     # ?ㅼ젣 ?꾨?湲곌컙 (???? 24 ?댁긽)
    previous_monthly_rent: int      # 吏곸쟾 怨꾩빟 ?붿꽭
    new_monthly_rent: int           # ?곸깮?꾨? 怨꾩빟 ?붿꽭
    has_prior_contract: bool = True


class LongTermRentalInput(BaseModel):
    """?κ린?꾨? 媛먮㈃ ?곸꽭"""
    registration_date: str          # ?꾨??ъ뾽???깅줉??YYYYMMDD
    mandatory_period_years: int = 8
    mandatory_period_fulfilled: bool = False
    rent_increase_limit_complied: bool = False


class SpecialCasesInput(BaseModel):
    """?쒕굹由ъ삤蹂??밸? ?곸꽭 ???대떦?섎뒗 ??ぉ留?梨꾩슫??""
    temp_two_house: Optional[TempTwoHouseInput] = None
    inheritance: Optional[InheritanceInput] = None
    gift: Optional[GiftInput] = None
    marriage_merge: Optional[MarriageMergeInput] = None
    sangsaeng_rental: Optional[SangsaengRentalInput] = None
    long_term_rental: Optional[LongTermRentalInput] = None
    residence_exemption_reason: Optional[str] = None  # "?댁쇅?댁＜" | "痍⑦븰" | "?섏슜" ??


# ?? 硫붿씤 ?낅젰 ?ㅽ궎留??????????????????????????????????????????????????????????

class FactInput(BaseModel):
    """
    梨꾪똿 API媛 ?섏떊?섎뒗 JSON ?ъ떎愿怨?

    ?꾩닔 ?꾨뱶留뚯쑝濡쒕룄 湲곕낯 ?먮떒??媛?ν븯硫?
    special_cases瑜?梨꾩슱?섎줉 ?뺣????먮떒??媛?ν븯??

    ?덉떆:
    {
        "transfer_date": "20240601",
        "acquisition_date": "20200301",
        "property_type": "?꾪뙆??,
        "acquisition_reason": "留ㅻℓ",
        "household_house_count": 1,
        "transfer_price": 1100000000,
        "residence_years": 2.5,
        "is_adjustment_area_at_transfer": true
    }
    """
    # ?? ?꾩닔 ??????????????????????????????????????????????????????????????????
    transfer_date: str          # ?묐룄??YYYYMMDD
    acquisition_date: str       # 痍⑤뱷??YYYYMMDD
    property_type: Literal[
        "?꾪뙆??, "?⑤룆二쇳깮", "?곕┰?ㅼ꽭?", "?ㅺ?援?, "寃몄슜二쇳깮",
        "遺꾩뼇沅?, "?낆＜沅?, "二쇨굅?⑹삤?쇱뒪??, "?낅Т?⑹삤?쇱뒪??,
        "?띿뼱珥뚯＜??, "?좎?", "?곴?",
    ]
    acquisition_reason: Literal[
        "留ㅻℓ", "遺꾩뼇", "?곸냽", "利앹뿬", "遺?대?利앹뿬", "?댄샎?ъ궛遺꾪븷",
        "寃쎈ℓ", "?ш굔異?, "?ш컻諛?, "?섏슜", "?쇱씤?⑷?",
    ]
    household_house_count: int  # ?묐룄 ?쒖젏 ?몃? 蹂댁쑀 二쇳깮 ??

    # ?? ?좏깮: 怨쇱꽭 怨꾩궛???꾩슂 ????????????????????????????????????????????????
    transfer_price: Optional[int] = None        # ?묐룄媛??(?? ??怨좉?二쇳깮 ?먮떒 ?꾩닔
    acquisition_price: Optional[int] = None     # 痍⑤뱷媛??(??
    holding_years: Optional[float] = None       # 蹂댁쑀湲곌컙 (?? ???놁쑝硫??좎쭨濡?怨꾩궛
    residence_years: Optional[float] = None     # 嫄곗＜湲곌컙 (??
    is_adjustment_area_at_acquisition: bool = False  # 痍⑤뱷 ??議곗젙??곸???
    is_adjustment_area_at_transfer: bool = False     # ?묐룄 ??議곗젙??곸???
    joint_ownership: bool = False               # 怨듬룞紐낆쓽 ?щ?
    is_non_resident: bool = False               # 鍮꾧굅二쇱옄 ?щ?
    residential_area_ratio: Optional[float] = None   # 寃몄슜二쇳깮 二쇨굅硫댁쟻 鍮꾩쑉 (0~1)

    # ?? ?밸? ?곸꽭 ?????????????????????????????????????????????????????????????
    special_cases: Optional[SpecialCasesInput] = None

    @model_validator(mode="after")
    def _validate_dates(self) -> "FactInput":
        for field_name in ("transfer_date", "acquisition_date"):
            val = getattr(self, field_name)
            if len(val) != 8 or not val.isdigit():
                raise ValueError(f"{field_name}? YYYYMMDD ?뺤떇?댁뼱???⑸땲?? {val!r}")
        if self.transfer_date < self.acquisition_date:
            raise ValueError("?묐룄?쇱씠 痍⑤뱷?쇰낫???댁쟾?????놁뒿?덈떎.")
        return self


def fact_input_to_rag_query(fact: FactInput) -> RAGQueryInput:
    """
    FactInput ??RAGQueryInput 蹂??
    湲곗〈 from_fact_ledger(fact_ledger, owner_profile, user_property) ?쒓렇?덉쿂瑜??ъ궗?⑺븳??
    """
    sc = fact.special_cases or SpecialCasesInput()

    # user_property dict ??from_fact_ledger媛 湲곕??섎뒗 而щ읆紐??ъ슜
    user_property: dict = {
        "transfer_date": _yyyymmdd_to_iso(fact.transfer_date),
        "acquisition_date": _yyyymmdd_to_iso(fact.acquisition_date),
        "asset_kind": fact.property_type,
        "acquisition_cause": fact.acquisition_reason,
        "sale_price_total": fact.transfer_price,
        "acquisition_price": fact.acquisition_price,
        "adjustment_area_at_acquisition": fact.is_adjustment_area_at_acquisition,
        "adjustment_area_at_transfer": fact.is_adjustment_area_at_transfer,
        "joint_ownership_yn": fact.joint_ownership,
        "overseas_residence_yn": fact.is_non_resident,
    }
    if sc.long_term_rental:
        lr = sc.long_term_rental
        user_property.update({
            "long_term_rental_yn": True,
            "rental_registration_date": _yyyymmdd_to_iso(lr.registration_date),
            "mandatory_rental_years": lr.mandatory_period_years,
            "mandatory_period_fulfilled": lr.mandatory_period_fulfilled,
            "rent_increase_limit_complied": lr.rent_increase_limit_complied,
        })
    if sc.inheritance:
        inh = sc.inheritance
        user_property["death_date"] = _yyyymmdd_to_iso(inh.death_date)
        if inh.donor_acquisition_date:
            user_property["donor_acquisition_date"] = _yyyymmdd_to_iso(inh.donor_acquisition_date)

    # fact_ledger dict ???밸? ?뚮옒洹?
    fact_ledger: dict = {
        "household_house_count": fact.household_house_count,
        "holding_years": fact.holding_years,
        "residence_years": fact.residence_years,
    }
    if sc.temp_two_house:
        tt = sc.temp_two_house
        fact_ledger.update({
            "is_temporary_two_house": True,
            "temp_new_acquisition_date": _yyyymmdd_to_iso(tt.new_acquisition_date),
            "temp_old_must_sell_by": _yyyymmdd_to_iso(tt.old_house_must_sell_by),
            "temp_new_is_adjustment_area": tt.new_is_adjustment_area,
        })
    if sc.inheritance:
        inh = sc.inheritance
        fact_ledger.update({
            "deceased_same_household": inh.same_household_at_death,
            "inherited_as_only_house": inh.inherited_as_only_house,
            "selling_inherited_house": inh.selling_inherited_house,
        })
    if sc.gift:
        g = sc.gift
        fact_ledger["is_gift_from_spouse_or_lineal"] = g.is_gift_from_spouse_or_lineal
        if g.donor_acquisition_date:
            fact_ledger["donor_acquisition_date"] = _yyyymmdd_to_iso(g.donor_acquisition_date)
        if g.donor_acquisition_price is not None:
            fact_ledger["donor_acquisition_price"] = g.donor_acquisition_price
    if sc.marriage_merge:
        mm = sc.marriage_merge
        fact_ledger.update({
            "marriage_date": _yyyymmdd_to_iso(mm.marriage_date),
            "spouse_house_count_before_marriage": mm.spouse_house_count_before_marriage,
            "own_house_count_before_marriage": mm.own_house_count_before_marriage,
        })
    if sc.sangsaeng_rental:
        sr = sc.sangsaeng_rental
        fact_ledger.update({
            "sangsaeng_rental_yn": True,
            "sangsaeng_contract_date": _yyyymmdd_to_iso(sr.contract_date),
            "sangsaeng_period_months": sr.contract_period_months,
            "sangsaeng_prev_rent": sr.previous_monthly_rent,
            "sangsaeng_new_rent": sr.new_monthly_rent,
            "sangsaeng_has_prior_contract": sr.has_prior_contract,
        })
    if sc.residence_exemption_reason:
        fact_ledger["residence_exemption_reason"] = sc.residence_exemption_reason
    if fact.residential_area_ratio is not None:
        fact_ledger["residential_area_ratio"] = fact.residential_area_ratio

    # owner_profile ???몃???援ъ꽦 (?꾩옱??二쇳깮 ?섎쭔 ?꾨떖)
    owner_profile: dict = {
        "household_house_count": fact.household_house_count,
    }

    return RAGQueryInput.from_fact_ledger(fact_ledger, owner_profile, user_property)


def _yyyymmdd_to_iso(d: str) -> str:
    """YYYYMMDD ??YYYY-MM-DD"""
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

 succeeded in 3391ms:
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

codex
이제 충분히 맥락은 잡혔습니다. 답변에서는 “로드맵 자체의 우선순위”와 “현재 코드 기준으로 어디에 꽂아야 하는지”를 분리해서 정리하겠습니다. 특히 바로 손대면 충돌 나는 부분은 `query_input.py`의 상수 하드코딩, `fact_input.py`의 입력-도메인 매핑, `pipeline.py`의 차단 지점입니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"HIGH_VALUE_THRESHOLD|SANGSAENG_WINDOW_START|HEAVY_TAX_SUSPENSION_END|class SpecialCaseFlags|class DateBundle|contract_date|balance_payment_date|registration_date|is_high_value_house|from_fact_ledger|_build_special_cases|transfer_price\" src\\domain\\query_input.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"run_rag_pipeline|check_facts|blocked_at_l2|enable_debate|TaxAnswer\\(|validate_output\" src\\domain\\pipeline.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"class FactInput|fact_input_to_rag_query|transfer_date|acquisition_date|contract_date|balance_payment_date|registration_date|special_cases\" src\\api\\fact_input.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"class AdjustmentAreaRecord|class AdminNoticesDB|resolve_adjustment_area|collect_adjustment_areas|collect_financial_regulations|run_collect_all\" src\\ingestion\\admin_notices.py" in c:\Users\user\cording2025\tax-rag
 succeeded in 3501ms:
46:class AdjustmentAreaRecord:
95:class AdminNoticesDB:
108:def resolve_adjustment_area(region: str, target_date: date, db: AdminNoticesDB) -> bool:
187:async def collect_adjustment_areas() -> list[AdjustmentAreaRecord]:
212:async def collect_financial_regulations() -> list[FinancialRegulationRecord]:
232:async def run_collect_all() -> AdminNoticesDB:
244:        areas = await collect_adjustment_areas()
251:        fins = await collect_financial_regulations()
264:    asyncio.run(run_collect_all())

 succeeded in 3512ms:
5:    result = await run_rag_pipeline(
17:from .fact_checker import FactCheckResult, check_facts
18:from .output_validator import validate_output
31:    blocked_at_l2: bool = False
35:async def run_rag_pipeline(
40:    enable_debate: bool = False,
52:    fact_check = check_facts(query)
55:        blocked_answer = TaxAnswer(
68:            blocked_at_l2=True,
92:    validated = validate_output(raw_answer, retrieved_ids, danger_flags=fact_check.danger_flags)
102:    if enable_debate and fact_json:

 succeeded in 3512ms:
18:    new_acquisition_date: str       # 신규주택 취득일 YYYYMMDD
29:    donor_acquisition_date: Optional[str] = None
35:    donor_acquisition_date: Optional[str] = None
48:    contract_date: str              # 상생임대차계약 체결일 YYYYMMDD
57:    registration_date: str          # 임대사업자 등록일 YYYYMMDD
76:class FactInput(BaseModel):
81:    special_cases를 채울수록 정밀한 판단이 가능하다.
85:        "transfer_date": "20240601",
86:        "acquisition_date": "20200301",
96:    transfer_date: str          # 양도일 YYYYMMDD
97:    acquisition_date: str       # 취득일 YYYYMMDD
121:    special_cases: Optional[SpecialCasesInput] = None
125:        for field_name in ("transfer_date", "acquisition_date"):
129:        if self.transfer_date < self.acquisition_date:
134:def fact_input_to_rag_query(fact: FactInput) -> RAGQueryInput:
139:    sc = fact.special_cases or SpecialCasesInput()
143:        "transfer_date": _yyyymmdd_to_iso(fact.transfer_date),
144:        "acquisition_date": _yyyymmdd_to_iso(fact.acquisition_date),
158:            "rental_registration_date": _yyyymmdd_to_iso(lr.registration_date),
166:        if inh.donor_acquisition_date:
167:            user_property["donor_acquisition_date"] = _yyyymmdd_to_iso(inh.donor_acquisition_date)
179:            "temp_new_acquisition_date": _yyyymmdd_to_iso(tt.new_acquisition_date),
193:        if g.donor_acquisition_date:
194:            fact_ledger["donor_acquisition_date"] = _yyyymmdd_to_iso(g.donor_acquisition_date)
208:            "sangsaeng_contract_date": _yyyymmdd_to_iso(sr.contract_date),

 succeeded in 3521ms:
5:- transfer_price 추가 → 고가주택(12억 초과) 판단 가능
25:HIGH_VALUE_THRESHOLD = 1_200_000_000  # 12억 원
28:SANGSAENG_WINDOW_START = date(2021, 12, 20)
36:HEAVY_TAX_SUSPENSION_END = date(2026, 5, 9)
113:class DateBundle:
126:    contract_date: Optional[date] = None
127:    balance_payment_date: Optional[date] = None   # 잔금청산일
128:    registration_date: Optional[date] = None      # 등기접수일
135:            "contract_date": self.contract_date,
136:            "balance_payment_date": self.balance_payment_date,
137:            "registration_date": self.registration_date,
219:    registration_date: date               # 임대사업자 등록일
246:    ① 계약 체결일: SANGSAENG_WINDOW_START ~ SANGSAENG_WINDOW_END
254:    contract_date: date              # 상생임대차계약 체결일
268:        return SANGSAENG_WINDOW_START <= self.contract_date <= SANGSAENG_WINDOW_END
437:class SpecialCaseFlags:
596:    transfer_price: Optional[int] = None      # 양도가액 (원)
627:    def is_high_value_house(self) -> bool:
629:        if self.transfer_price is None:
631:        return self.transfer_price > HIGH_VALUE_THRESHOLD
646:        if self.transfer_price is not None:
647:            label = "고가주택" if self.is_high_value_house else "일반주택"
648:            lines.append(f"양도가액: {self.transfer_price:,}원 ({label})")
773:    def from_fact_ledger(
784:        special_cases = _build_special_cases(fact_ledger, user_property)
802:        contract_date=_pd(up.get("contract_date")),
803:        balance_payment_date=_pd(up.get("balance_payment_date")),
804:        registration_date=_pd(up.get("registration_date")),
819:def _build_special_cases(fl: dict, up: dict) -> SpecialCaseFlags:
874:        if rd := _pd(up.get("rental_registration_date")):
876:                registration_date=rd,
884:        if cd := _pd(fl.get("sangsaeng_contract_date") or up.get("sangsaeng_contract_date")):
886:                contract_date=cd,
1016:        transfer_price=_parse_int(up.get("sale_price_total")),

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"transfer_price|is_gift_from_spouse_or_lineal|death_date|temp_two_house.new_acquisition_date|management_disposal_date|is_related_party_transaction|sangsaeng_rental|adjustment_area_at_transfer\" src\\domain\\fact_checker.py" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"hybrid|sparse|bm25|article_number|entity_scopes|effective_date|expiration_date|rerank|top_k\" src\\retrieval\\retriever_impl.py src\\infra\\pinecone_client.py src\\rag.py" in c:\Users\user\cording2025\tax-rag
 succeeded in 3080ms:
67:    if fv.transfer_price is None:
69:            field_name="transfer_price",
85:        if rt is None or not rt.is_gift_from_spouse_or_lineal:
88:                field_name="is_gift_from_spouse_or_lineal",
93:        elif rt.is_gift_from_spouse_or_lineal:
117:                field_name="death_date",
141:                field_name="temp_two_house.new_acquisition_date",
153:                field_name="management_disposal_date",
187:    if not fv.adjustment_area_at_acquisition and not fv.adjustment_area_at_transfer:
192:    if sc.sangsaeng_rental and sc.sangsaeng_rental.residence_requirement_waived:
194:        if not fv.adjustment_area_at_transfer:
198:                field_name="adjustment_area_at_transfer",
212:    if fv.is_related_party_transaction:

 succeeded in 3099ms:
src\infra\pinecone_client.py:34:    top_k: int = 20,
src\infra\pinecone_client.py:42:        top_k=top_k,
src\rag.py:7:- Reranker: src.infra.reranker.{get_reranker, rerank}
src\rag.py:28:from src.infra import reranker as _reranker_mod
src\rag.py:43:    article_number: str
src\rag.py:45:    effective_date: str
src\rag.py:46:    expiration_date: str = ""
src\rag.py:62:# `src.rag._get_reranker` 를 patch 한다. shim 도 같은 이름을 노출해야 한다.
src\rag.py:72:def _get_reranker():
src\rag.py:73:    return _reranker_mod.get_reranker()
src\rag.py:80:    top_k: int = 20,
src\rag.py:81:    rerank_top_n: int = 5,
src\rag.py:85:    법령 벡터 검색 + BGE reranking → 상위 rerank_top_n 개 반환.
src\rag.py:97:                {"effective_date": {"$lte": as_of_int}},
src\rag.py:98:                {"expiration_date": {"$gte": as_of_int}},
src\rag.py:106:        top_k=top_k,
src\rag.py:125:    reranker = _get_reranker()
src\rag.py:127:    rerank_scores = reranker.predict(pairs)
src\rag.py:130:        zip(rerank_scores, matches),
src\rag.py:133:    )[:rerank_top_n]
src\rag.py:149:                article_number=meta.get("article_number", ""),
src\rag.py:151:                effective_date=_date_str(meta.get("effective_date")),
src\rag.py:152:                expiration_date=_date_str(meta.get("expiration_date")),
src\rag.py:166:    """검색 → reranking → LLM 추론 → TaxAnswer. enable_trace=True 면 trace 기록."""
src\rag.py:185:                f"[{c.law_name} 제{c.article_number}조] {c.full_text[:300]}" for c in chunks
src\rag.py:188:                f"{c.law_name} 제{c.article_number}조 {c.article_title}".strip()
src\rag.py:200:            f"[{i}] {chunk.law_name} 제{chunk.article_number}조 {chunk.article_title}\n"
src\rag.py:201:            f"(chunk_id: {chunk.id}, rerank_score: {chunk.score:.4f})\n"
src\rag.py:229:            "citations": [f"{c.law_name} 제{c.article_number}조" for c in chunks],
src\rag.py:254:                rerank_scores=[c.score for c in chunks],
src\rag.py:314:    chunks = retrieve_tax_law(query, top_k=20, rerank_top_n=5)
src\rag.py:315:    print(f"검색 결과 (reranking 후 상위 {len(chunks)}개):")
src\rag.py:317:        print(f"[{i}] {c.law_name} 제{c.article_number}조 {c.article_title}")
src\rag.py:318:        print(f"     chunk_id: {c.id} | rerank_score: {c.score:.4f}")
src\retrieval\retriever_impl.py:5:현재 미수집 필드(linked_buchik_ids, entity_scopes 등)는 합리적 기본값 사용.
src\retrieval\retriever_impl.py:28:from src.infra.reranker import rerank
src\retrieval\retriever_impl.py:67:    eff_int = int(float(meta.get("effective_date", 0) or 0))
src\retrieval\retriever_impl.py:68:    exp_int = int(float(meta.get("expiration_date", 99991231) or 99991231))
src\retrieval\retriever_impl.py:75:        article_number=meta.get("article_number", ""),
src\retrieval\retriever_impl.py:83:        article_lineage_root=meta.get("article_number", ""),
src\retrieval\retriever_impl.py:95:        top_k: int = TOP_K,
src\retrieval\retriever_impl.py:96:        rerank_top_n: int = RERANK_TOP_N,
src\retrieval\retriever_impl.py:99:        self.top_k = top_k
src\retrieval\retriever_impl.py:100:        self.rerank_top_n = rerank_top_n
src\retrieval\retriever_impl.py:107:        # query.top_k 우선, 없으면 인스턴스 기본값
src\retrieval\retriever_impl.py:108:        top_k = getattr(query, "top_k", None) or self.top_k
src\retrieval\retriever_impl.py:115:                {"effective_date": {"$lte": as_of_int}},
src\retrieval\retriever_impl.py:116:                {"expiration_date": {"$gte": as_of_int}},
src\retrieval\retriever_impl.py:122:            top_k=top_k,
src\retrieval\retriever_impl.py:131:                top_k=top_k,
src\retrieval\retriever_impl.py:138:        # Stage 1 보강 — entity_scope 후필터 (Pinecone entity_scopes 메타데이터 기반)
src\retrieval\retriever_impl.py:144:                if not m.get("metadata", {}).get("entity_scopes")  # 태그 없으면 통과
src\retrieval\retriever_impl.py:145:                or scope_val in m["metadata"]["entity_scopes"]
src\retrieval\retriever_impl.py:150:        ranked = rerank(query_text, matches, self.rerank_top_n)

codex
**총평**

로드맵 방향은 맞습니다. 다만 현재 코드 기준으로는 `법령 검색 정확도`보다 먼저 `결정론 레이어 정리`를 해야 합니다. 지금 병목은 검색이 아니라 입력 사실관계와 법령 기준값이 코드 여러 곳에 흩어져 있다는 점입니다. 특히 [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:25)에 기준값이 하드코딩돼 있고, [src/api/fact_input.py](/c:/Users/user/cording2025/tax-rag/src/api/fact_input.py:76)는 날짜 필드를 아직 충분히 받지 않으며, [src/domain/pipeline.py](/c:/Users/user/cording2025/tax-rag/src/domain/pipeline.py:35)는 차단 지점이 `L2 fact check` 하나뿐입니다.

**권장 구현 순서**

1. `TaxConstantsRegistry`부터 하십시오.
이게 선행돼야 `12억`, 상생임대 기간, 중과배제 유예, 경과규정 기준일 같은 값이 한 군데로 모입니다. 지금은 [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:25), [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:28), [src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:36)처럼 분산돼 있어 변경 리스크가 큽니다. 구조는 `constant_key -> [{effective_from, effective_to, value, source_law, source_article, notes}]`를 권장합니다. `transfer_date` 기준 조회만 두지 말고 `anchor_key`를 받아 `transfer_date`, `contract_date`, `acquisition_date`를 모두 지원해야 합니다. 별표 이미지 조문은 “자동 파싱 실패”를 값으로 숨기지 말고 `manual_only=True`와 경고 로그를 남기십시오.

2. 날짜 필드 확장을 바로 뒤에 두십시오.
도메인 쪽 `DateBundle`에는 이미 `contract_date`, `balance_payment_date`, `registration_date`가 있습니다([src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:113)). 그런데 `FactInput`은 아직 `transfer_date`, `acquisition_date` 중심입니다([src/api/fact_input.py](/c:/Users/user/cording2025/tax-rag/src/api/fact_input.py:96)). 이 불일치를 먼저 없애야 이후 특례 판단이 안정됩니다. `취득시기 = min(잔금지급일, 등기접수일)`은 `fact_input.py`나 별도 `date_resolver.py`에서 결정론적으로 계산하고, 원시 입력값과 계산 결과를 둘 다 보존하십시오.

3. 상속·증여 취득일 승계 규칙을 결정론 코드로 분리하십시오.
이건 LLM 금지 항목이 맞습니다. 현재 일부 구조는 있으나([src/domain/fact_checker.py](/c:/Users/user/cording2025/tax-rag/src/domain/fact_checker.py:85), [src/domain/fact_checker.py](/c:/Users/user/cording2025/tax-rag/src/domain/fact_checker.py:117)) 규칙 엔진으로 분리되지 않았습니다. `src/domain/acquisition_timeline.py` 같은 모듈에서 `resolve_effective_acquisition_date(facts)`, `resolve_holding_period_base(facts)`를 두는 편이 낫습니다. 리스크는 “원취득일/증여일/사망일” 앵커를 혼동하는 것입니다. 이건 테스트를 많이 깔아야 합니다.

4. 확인서 모듈은 `L1.5 Gate`로 넣으십시오.
이건 `fact_checker`에 섞지 말고 [src/domain/pipeline.py](/c:/Users/user/cording2025/tax-rag/src/domain/pipeline.py:52) 앞에 별도 차단 단계로 두는 게 맞습니다. 이유는 `사실 누락`과 `사용자 확인 부재`는 성격이 다르기 때문입니다. `ConfirmationResult(can_proceed, missing_confirmations, warnings)` 형태를 권장합니다. 세 항목은 전부 양방향 차단 대상으로 두되, “특수관계자 거래 아님”은 향후 증빙 첨부까지 확장 가능하게 설계하십시오. 청약홈 연동은 MVP 범위를 넘으니 지금은 인터페이스만 두고 공급자 어댑터를 분리하는 정도면 충분합니다.

5. `admin_notices.py`의 3종 구역 자동 조회를 그 다음에 구현하십시오.
이건 중요하지만, 앞선 결정론 레이어 없이 먼저 붙이면 결국 boolean 필드만 더 늘어납니다. 현재 [src/ingestion/admin_notices.py](/c:/Users/user/cording2025/tax-rag/src/ingestion/admin_notices.py:46) 구조는 조정대상지역 위주라 `designation_type` 일반화가 필요합니다. `AdjustmentAreaRecord` 대신 `AreaDesignationRecord(region_code, area_type, designated_at, released_at, source)`로 바꾸고, `resolve_area_status(region, target_date, area_type)` 하나로 합치십시오. API가 불안정하면 수동 이력 테이블을 정식 1급 데이터 소스로 두고, API는 “보강/검증용”으로 두는 편이 안전합니다. 법적 분쟁 리스크가 있는 데이터라 “API 우선, 없으면 fallback”보다 “수동 기준표 우선, API 검증”이 운영상 더 낫습니다.

6. `SpecialCaseFlags` 확장과 특례 발굴 엔진은 마지막에 두십시오.
이건 범위가 가장 큽니다. 현재 `SpecialCaseFlags`는 이미 비대해지는 중입니다([src/domain/query_input.py](/c:/Users/user/cording2025/tax-rag/src/domain/query_input.py:437)). 여기에 모든 조특법 특례를 계속 넣으면 유지보수성이 무너집니다. `SpecialCaseFlags`는 핵심 boolean/summary만 남기고, 별도 `special_case_finder.py`에서 `ApplicableSpecialCase` 목록을 반환하는 형태가 맞습니다. 출력은 “적용 확정”과 “추가 검토 제안”을 분리하십시오. 제안형 특례는 verdict를 바꾸지 말고 warnings에만 넣는 편이 안전합니다.

**각 항목별 핵심 리스크**

1. 구역 자동 조회: 행정구역명 표기 편차, 날짜 기준 혼동, 부분 해제 이력 누락.
2. 상수 레지스트리: 경과규정 anchor가 `transfer_date` 하나로 안 끝나는 경우.
3. 특례 발굴: recall을 높이려다 false positive가 급증할 가능성.
4. 확인서: UI/REST/MCP 경로에서 동일 차단 규칙이 안 맞을 가능성.
5. 날짜 확장: 기존 `acquisition_date`와 계산된 취득시기 충돌.
6. 상속·증여 승계: “보유기간 승계”와 “취득가액 승계”를 같은 함수에서 다뤄 버리는 설계 실수.

**A-D 의사결정**

A. BM25 sparse 검색은 도입하는 쪽이 맞습니다.
우선순위는 `Pinecone hybrid > 별도 Elasticsearch > 현행 유지`입니다. 이유는 현재 retriever가 Pinecone 날짜 필터와 reranker 흐름에 이미 맞춰져 있기 때문입니다([src/retrieval/retriever_impl.py](/c:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py:110)). 정확한 조문번호, `제89조`, `§154`, 부칙 번호는 dense만으로는 불안합니다. 다만 처음부터 ES를 별도 운영하면 운영 복잡도만 늘어납니다. 1차는 article-number sparse field만 넣은 hybrid로 충분합니다.

B. 유권해석 크롤링은 법령과 별도 네임스페이스가 맞습니다.
`tax-law`, `tax-ruling-ntis`, `tax-ruling-tt`, `tax-ruling-court`로 나누고, 검색 시에는 법령 우선, 유권해석은 보강 evidence로 붙이십시오. verdict 근거는 여전히 법령 chunk가 1순위여야 합니다. 유권해석만으로 결론을 내리는 경로는 만들지 않는 것이 좋습니다.

C. 유형1/유형2는 지금 당장 파이프라인을 물리적으로 분리하지 마십시오.
`query_mode: report | consulting` 정도의 얇은 분기만 넣고, L2/L3/L4의 코어는 공유하는 편이 낫습니다. 유형2에서만 시뮬레이션 노드와 비교표 출력을 추가하십시오. MVP에서 코드베이스를 둘로 쪼개면 테스트 비용만 커집니다.

D. 별표 이미지는 단기적으로 수동 관리가 최적입니다.
OCR 파이프라인은 후순위입니다. 별표는 숫자 테이블이라 OCR 오차가 치명적입니다. `TaxConstantsRegistry`에 수동 등록하고, 수집기에서 이미지 감지 시 `manual_review_required`를 남기십시오. OCR은 “초안 추출 + 사람 검수” 용도로만 쓰는 게 맞습니다.

**권장 2주 스프린트 순서**

1. `tax_constants.py` 신설, 기존 하드코딩 상수 제거.
2. `fact_input.py` 날짜 필드 확장, 취득시기 결정론 함수 추가.
3. 상속·증여 취득일/보유기간 계산 모듈 분리.
4. `confirmation.py` 추가, `pipeline.py`에 L1.5 gate 삽입.
5. `admin_notices.py`를 3종 구역 일반화 + 수동 이력 DB 우선화.
6. Pinecone hybrid search PoC.
7. `special_case_finder.py`는 제안형 엔진부터 시작.

**테스트 게이트**

반드시 추가할 테스트는 4개입니다.

- 날짜 앵커별 상수 조회 테스트
- `min(balance_payment_date, registration_date)` 취득시기 결정 테스트
- 확인서 `No` 시 LLM 미호출 차단 테스트
- 구역 지정 이력의 취득일 기준/양도일 기준 분리 테스트

원하시면 다음 단계로 바로 `실행 가능한 구현 계획` 형태로 끊어서, 파일별 변경안까지 내려드리겠습니다.
tokens used
64,595

```

## Concise summary

Provider completed successfully. Review the raw output for details.

## Action items

- Review the response and extract decisions you want to apply.
- Capture follow-up implementation tasks if needed.
