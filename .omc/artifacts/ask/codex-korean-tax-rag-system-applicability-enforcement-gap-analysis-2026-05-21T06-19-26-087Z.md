# codex advisor artifact

- Provider: codex
- Exit code: 0
- Created at: 2026-05-21T06:19:26.090Z

## Original task

Korean tax RAG system - 부칙 applicability enforcement gap analysis. System: (1) linked_buchik_ids ensures buchik chunks auto-retrieved with main body articles, (2) LLM reads buchik free text to determine applicability, (3) ApplicabilitySpec dataclass exists but always NONE. Gap: buchik natural language like '이 법 시행 이후 양도하는 분부터 적용' (transfer-date based) vs '취득하는 분부터 적용' (acquisition-date based) is not structurally parsed. These are SILENT errors - wrong answer looks plausible, no exception thrown. Question: (A) Can RLVR binary reward + Red-Blue debate accumulation of golden cases catch these silent applicability errors reliably? (B) What are the failure modes of pure LLM-reads-text approach? (C) Is hybrid approach (pre-compute structured conditions at ingestion via regex or LLM extraction → populate ApplicabilitySpec → hard filter in retriever) worth the complexity? (D) Risk assessment: how often do Korean tax law amendments use '취득분' vs '양도분' distinction, and how critical are the verdict differences? Provide architecture recommendation.

## Final prompt

Korean tax RAG system - 부칙 applicability enforcement gap analysis. System: (1) linked_buchik_ids ensures buchik chunks auto-retrieved with main body articles, (2) LLM reads buchik free text to determine applicability, (3) ApplicabilitySpec dataclass exists but always NONE. Gap: buchik natural language like '이 법 시행 이후 양도하는 분부터 적용' (transfer-date based) vs '취득하는 분부터 적용' (acquisition-date based) is not structurally parsed. These are SILENT errors - wrong answer looks plausible, no exception thrown. Question: (A) Can RLVR binary reward + Red-Blue debate accumulation of golden cases catch these silent applicability errors reliably? (B) What are the failure modes of pure LLM-reads-text approach? (C) Is hybrid approach (pre-compute structured conditions at ingestion via regex or LLM extraction → populate ApplicabilitySpec → hard filter in retriever) worth the complexity? (D) Risk assessment: how often do Korean tax law amendments use '취득분' vs '양도분' distinction, and how critical are the verdict differences? Provide architecture recommendation.

## Raw output

```text
핵심 결론부터 말하면, 이 문제는 RLVR로 “나중에 잡는” 종류가 아니라 retrieval 전에 구조적으로 막아야 하는 종류입니다. 지금 구현은 [retriever_impl.py](/C:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py:133)에서 `ApplicabilitySpec`를 항상 `NONE`으로 두고 있고, debate도 [debate.py](/C:/Users/user/cording2025/tax-rag/src/eval/debate.py:526) 기준으로 `confidence < 0.80` 또는 `danger_flags >= 2`일 때만 돌아서, “그럴듯하지만 틀린” 부칙 적용 오류는 그대로 통과할 수 있습니다. 더 큰 문제는 현재 산출물엔 부칙 청크가 사실상 없습니다. 원천 XML엔 `<부칙>`가 있는데 [소득세법_285523.xml](/C:/Users/user/cording2025/tax-rag/data/raw/소득세법_285523.xml:15235), processed 쪽은 `article_type=부칙`가 0건이고 `linked_buchik_ids`도 전부 비어 있어 [collect.py](/C:/Users/user/cording2025/tax-rag/src/ingestion/collect.py:303) 의도 자체가 실데이터에선 작동하지 않습니다.

**A. RLVR + Red/Blue가 이 오류를 reliably 잡나**
아니오, 보조수단으로는 쓸 수 있어도 1차 방어선으로는 부족합니다.
- binary reward는 “정답/오답”은 줄 수 있어도 왜 틀렸는지, 특히 `양도분` vs `취득분` 같은 적용 anchor를 일반화해서 학습시키기 어렵습니다.
- debate는 샘플링된 케이스만 봅니다. 높은 confidence로 나온 silent error는 토론 자체가 안 열릴 수 있습니다.
- golden retrieval도 [golden_injector.py](/C:/Users/user/cording2025/tax-rag/src/eval/golden_injector.py:34)에서 `property_type`, `acquisition_reason`, 주택 수, special case key 정도만 봐서 “같은 쟁점인데 anchor가 다른 케이스”를 잘 못 끌어옵니다.
- 그래서 RLVR는 “missed pattern 수집기”로는 좋지만, applicability enforcement 대체재는 아닙니다.

**B. pure LLM-reads-text 방식의 실패 모드**
- anchor 혼동: `취득분`인데 `양도일` 기준으로 읽음.
- 혼합 규정 누락: “시행 후 양도분, 다만 시행 전 취득분은 종전 규정” 같은 이중 조건을 한쪽만 반영.
- 예외/단서 역전: `다만`, `종전 규정 적용`, `최초로`를 놓침.
- version leakage: 본칙은 신법, 부칙은 구법 전환조치를 섞어 읽음.
- plausible hallucination: 답이 매우 자연스러워서 validator가 못 잡음. 현재 L5는 phantom citation 위주라 applicability 오판은 직접 검증하지 않습니다.
- non-determinism: 같은 케이스를 다시 물으면 적용 기준이 흔들릴 수 있습니다.

**C. hybrid가 복잡도 대비 가치 있나**
있습니다. 이 도메인에서는 거의 필수입니다. 다만 “전부 LLM 추출”이 아니라 “regex-first + offline LLM backfill”이 맞습니다.
- 1단계: ingestion에서 실제 `<부칙단위>`를 청크로 생성.
- 2단계: 고정 패턴을 정규식으로 구조화.
  - `이 법 시행 후 최초로 양도하는 분부터 적용` → anchor=`transfer_date`
  - `... 취득하는 분부터 적용` → anchor=`acquisition_date`
  - `... 계약을 체결하는 분부터 적용` → anchor=`contract_date`
- 3단계: 정규식이 못 푸는 부칙만 offline LLM extraction으로 `ApplicabilitySpec` 채움.
- 4단계: retriever Stage 1에서 high-confidence spec는 hard filter, low-confidence spec는 soft include + warning.
- 5단계: L5에서 “인용한 청크가 사실관계의 anchor date에 실제 적용되는지”를 다시 검증.

**D. 빈도와 리스크**
제가 현재 로컬 raw corpus(`data/raw/*.xml`)를 직접 스캔한 결과, 중복 포함 hit 기준으로:
- `양도...분부터 적용` 계열: 314회
- `취득...분부터 적용` 계열: 62회
- `계약...분부터 적용` 계열: 16회

이 수치는 unique rule count는 아니고 버전/반복문구 포함 hit count입니다. 그래도 의미는 분명합니다.
- `양도분`이 훨씬 많지만 `취득분`도 무시할 수준이 아닙니다.
- `취득분`은 특히 조특법/시행령에 몰려 있고, 감면/비과세/지방세 특례처럼 verdict를 뒤집는 조항에서 나옵니다.
- 그래서 발생 빈도는 `양도분`보다 낮아도, 한 번 틀리면 “종전 규정 vs 개정 규정”이 갈리면서 감면 존부 자체가 뒤집혀 치명적입니다.

샘플 근거:
- 로컬 raw XML: [소득세법_285523.xml](/C:/Users/user/cording2025/tax-rag/data/raw/소득세법_285523.xml:15488), [조세특례제한법_285525.xml](/C:/Users/user/cording2025/tax-rag/data/raw/조세특례제한법_285525.xml:26839)
- 공식 소스 예시: 국가법령정보센터 판례가 부칙의 “이후 최초로 양도하는 분부터 적용” 해석을 직접 다룹니다. https://www.law.go.kr/LSW/precInfoP.do?precSeq=65115
- 국가법령정보센터 연혁 페이지도 본문과 별도로 부칙을 분리 제공하고 있습니다. https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=188355

아키텍처 권고는 단순합니다.  
1. 먼저 ingestion을 고쳐 부칙을 실제 chunk로 만들고,  
2. `ApplicabilitySpec`를 채우는 extractor를 넣고,  
3. retriever에서 hard/soft applicability filtering을 적용하고,  
4. RLVR/debate는 그 위에서 extractor 누락 패턴을 수집하는 품질 루프로 쓰는 것이 맞습니다.

원하면 다음 턴에서 바로 `Phase 0: 부칙 파싱 복구 + ApplicabilitySpec 최소 스키마 + 테스트 설계`까지 코드 변경안으로 내리겠습니다.


OpenAI Codex v0.123.0 (research preview)
--------
workdir: C:\Users\user\cording2025\tax-rag
model: gpt-5.4
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 019e4929-b7fa-7720-aa93-d3ab24e17b14
--------
user
Korean tax RAG system - 부칙 applicability enforcement gap analysis. System: (1) linked_buchik_ids ensures buchik chunks auto-retrieved with main body articles, (2) LLM reads buchik free text to determine applicability, (3) ApplicabilitySpec dataclass exists but always NONE. Gap: buchik natural language like '이 법 시행 이후 양도하는 분부터 적용' (transfer-date based) vs '취득하는 분부터 적용' (acquisition-date based) is not structurally parsed. These are SILENT errors - wrong answer looks plausible, no exception thrown. Question: (A) Can RLVR binary reward + Red-Blue debate accumulation of golden cases catch these silent applicability errors reliably? (B) What are the failure modes of pure LLM-reads-text approach? (C) Is hybrid approach (pre-compute structured conditions at ingestion via regex or LLM extraction → populate ApplicabilitySpec → hard filter in retriever) worth the complexity? (D) Risk assessment: how often do Korean tax law amendments use '취득분' vs '양도분' distinction, and how critical are the verdict differences? Provide architecture recommendation.
codex
부칙 적용성 처리의 구조적 공백이 실제 코드에서 어디까지 반영돼 있는지 먼저 확인하겠습니다. `ApplicabilitySpec`, `linked_buchik_ids`, retriever/pipeline 흐름을 읽고, 그 위에서 RLVR/LLM-only/hybrid의 실패 모드를 평가하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'Get-ChildItem -Force' in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'rg -n "ApplicabilitySpec|linked_buchik_ids|buchik|부칙|applicability" src tests' in C:\Users\user\cording2025\tax-rag
 succeeded in 3285ms:
src\agents\prompts.py:110:4. 특례 누락 — 부칙 경과조치, 한시 규정 미적용
src\domain\chunk_metadata.py:5:1. 부칙(附則)은 본칙과 분리 청킹 — 본칙만 검색되면 경과조치/적용례 누락
src\domain\chunk_metadata.py:6:2. applicability_anchors: 이 청크가 "어떤 날짜 기준"으로 적용되는지 명시
src\domain\chunk_metadata.py:53:    부칙은 반드시 별도 청크 — 경과조치/적용례가 적용 법령 결정에 핵심.
src\domain\chunk_metadata.py:56:    BUCHIK = "부칙"          # 경과조치, 적용례 포함
src\domain\chunk_metadata.py:95:class ApplicabilitySpec:
src\domain\chunk_metadata.py:148:    applicability: ApplicabilitySpec
src\domain\chunk_metadata.py:154:    # 본칙↔부칙 양방향 링크
src\domain\chunk_metadata.py:155:    # 본칙 청크: 자신에게 적용되는 부칙 청크 ID 목록
src\domain\chunk_metadata.py:156:    # 부칙 청크: 자신이 수정/규정하는 본칙 청크 ID 목록
src\domain\chunk_metadata.py:157:    linked_buchik_ids: List[str] = field(default_factory=list)
src\domain\chunk_metadata.py:185:        이 청크의 applicability anchor에 해당하는 날짜 목록 반환.
src\domain\chunk_metadata.py:190:        for anchor_key in self.applicability.anchors:
src\api\schema.py:16:    contract_date: Optional[str] = None     # 계약일 — 부칙 경과조치 기준
src\retrieval\llm_fn.py:37:        marker = " [부칙]" if chunk.included_as_linked_buchik else ""
src\ingestion\collect.py:218:            "article_type": 조문여부,  # "본문" | "부칙" — 부칙은 경과조치, 별도 청크로 분리됨
src\ingestion\collect.py:243:    # 부칙 ID 목록 수집 후 본칙 청크에 linked_buchik_ids 주입
src\ingestion\collect.py:244:    # 같은 버전(MST) 의 부칙은 본칙 전체에 적용될 수 있으므로 전부 연결
src\ingestion\collect.py:245:    buchik_ids = [c["id"] for c in chunks if c.get("article_type") == "부칙"]
src\ingestion\collect.py:246:    if buchik_ids:
src\ingestion\collect.py:248:            if c.get("article_type") != "부칙":
src\ingestion\collect.py:249:                c["linked_buchik_ids"] = buchik_ids
src\ingestion\collect.py:250:    # 부칙 청크에는 빈 리스트 (부칙끼리 순환참조 방지)
src\ingestion\collect.py:252:        if "linked_buchik_ids" not in c:
src\ingestion\collect.py:253:            c["linked_buchik_ids"] = []
src\retrieval\retriever_impl.py:5:현재 미수집 필드(linked_buchik_ids, entity_scopes 등)는 합리적 기본값 사용.
src\retrieval\retriever_impl.py:19:    ApplicabilitySpec,
src\retrieval\retriever_impl.py:112:    appendix = AppendixType.BUCHIK if article_type == "부칙" else AppendixType.MAIN_BODY
src\retrieval\retriever_impl.py:114:    # linked_buchik_ids: Pinecone는 list 메타데이터를 그대로 반환
src\retrieval\retriever_impl.py:115:    raw_buchik = meta.get("linked_buchik_ids", [])
src\retrieval\retriever_impl.py:116:    buchik_ids: list[str] = list(raw_buchik) if isinstance(raw_buchik, list) else []
src\retrieval\retriever_impl.py:133:        applicability=ApplicabilitySpec(rule_type=ApplicabilityRuleType.NONE),
src\retrieval\retriever_impl.py:135:        linked_buchik_ids=buchik_ids,
src\ingestion\embed.py:71:    # 부칙 태그
src\ingestion\embed.py:72:    if "부칙" in full_text[:50] or "부  칙" in full_text[:50]:
src\ingestion\embed.py:73:        topic_tags.append("부칙경과조치")
src\ingestion\embed.py:174:                "article_type": chunk.get("article_type", ""),  # "본문" | "부칙"
src\ingestion\embed.py:181:                # 본칙↔부칙 연결 — retrieve_with_buchik()가 이 목록으로 부칙 청크를 자동 보강
src\ingestion\embed.py:182:                "linked_buchik_ids": chunk.get("linked_buchik_ids", []),
src\ingestion\embed.py:244:                "linked_buchik_ids": chunk.get("linked_buchik_ids", []),
src\domain\pipeline.py:143:    chunks = retriever.retrieve_with_buchik(query)
src\domain\query_enrichment.py:35:    "분양권_2021전_주택수미산입": "2020년 이전 취득 분양권 주택 수 미산입 소득세법 부칙",
src\domain\query_input.py:112:    부칙 경과조치 패턴 예시:
src\domain\query_input.py:768:    include_buchik: bool = True   # 부칙 자동 포함 (경과조치/적용례 누락 방지)
src\domain\retriever.py:4:Stage 1: SymbolicFilter — chunk applicability/날짜/scope 기반 후보 좁힘.
src\domain\retriever.py:24:    included_as_linked_buchik: bool = False
src\domain\retriever.py:52:    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:
src\domain\retriever.py:54:        본칙 검색 후 query.include_buchik=True 면 연결된 부칙 청크를 보강해서 반환.
src\domain\retriever.py:55:        부칙(경과조치/적용례)은 적용 법령 결정에 필수.
src\domain\retriever.py:58:        if not query.include_buchik:
src\domain\retriever.py:64:            for buchik_id in chunk.metadata.linked_buchik_ids:
src\domain\retriever.py:65:                if buchik_id in seen_ids:
src\domain\retriever.py:67:                buchik_chunk = self._get_chunk_by_id(buchik_id)
src\domain\retriever.py:68:                if buchik_chunk is None:
src\domain\retriever.py:72:                        metadata=buchik_chunk,
src\domain\retriever.py:73:                        content=self._get_content(buchik_id),
src\domain\retriever.py:75:                        included_as_linked_buchik=True,
src\domain\retriever.py:78:                seen_ids.add(buchik_id)
src\domain\retriever.py:83:        """단건 메타데이터 조회 (부칙 보강용)."""
src\domain\retriever.py:87:        """단건 본문 조회 (부칙 보강용)."""

 succeeded in 3313ms:


    디렉터리: C:\Users\user\cording2025\tax-rag


Mode                 LastWriteTime         Length Name                                                                 
----                 -------------         ------ ----                                                                 
d--h--        2026-05-21  오전 10:27                .git                                                                 
d-----        2026-05-21  오전 10:27                .omc                                                                 
d-----        2026-05-17   오후 7:55                .pytest_cache                                                        
d-----        2026-05-21   오후 3:11                data                                                                 
d-----        2026-05-21   오후 3:08                scripts                                                              
d-----        2026-05-21  오후 12:08                src                                                                  
d-----        2026-05-21  오후 12:01                tests                                                                
-a----        2026-05-20   오후 2:34            979 .env                                                                 
-a----        2026-05-21  오후 12:08            851 .env.example                                                         
-a----        2026-05-17   오후 8:18            407 .gitignore                                                           
-a----        2026-05-21  오전 11:40          19710 AGENTS.md                                                            
-a----        2026-05-21  오전 11:39          24842 CLAUDE.md                                                            
-a----        2026-05-17   오후 4:56           7742 README.md                                                            
-a----        2026-05-17   오후 7:50            384 requirements.txt                                                     



codex
`ApplicabilitySpec`가 설계에는 들어가 있지만 retrieval 경로에서 실제로는 `NONE`으로 박혀 있는지, 그리고 debate/eval이 이 유형의 오류를 어떤 방식으로 감지하는지 확인하고 있습니다. 다음으로 메타데이터 모델, retriever 구현, 평가 루프 코드를 직접 읽겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\chunk_metadata.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\retrieval\\retriever_impl.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\retriever.py | Select-Object -First 220" in C:\Users\user\cording2025\tax-rag
 succeeded in 3302ms:
"""
踰뺣졊 泥?겕 硫뷀??곗씠???ㅽ궎留?
?듭떖 ?ㅺ퀎 寃곗젙:
1. 遺移??꾢뎴)? 蹂몄튃怨?遺꾨━ 泥?궧 ??蹂몄튃留?寃?됰릺硫?寃쎄낵議곗튂/?곸슜濡 ?꾨씫
2. applicability_anchors: ??泥?겕媛 "?대뼡 ?좎쭨 湲곗?"?쇰줈 ?곸슜?섎뒗吏 紐낆떆
3. amendment_type 援щ텇 ???꾨?媛쒖젙? lineage ?딄?, ?쇰?媛쒖젙? ?댁뼱吏?4. ?踰뺢컻??蹂꾨룄 泥섎━ ???ㅻⅨ 踰뺤씠 媛쒖젙?섎㈃????踰뺤씠 諛붾뚮뒗 silent amendment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional


class LawLevel(str, Enum):
    ACT = "踰?                   # ?뚮뱷?몃쾿, 議곗꽭?밸??쒗븳踰?    ENFORCEMENT_DECREE = "?쒗뻾??
    ENFORCEMENT_RULE = "?쒗뻾洹쒖튃"


class LawId(str, Enum):
    """愿由????踰뺣졊 紐⑸줉"""
    INCOME_TAX_ACT = "income_tax_act"                          # ?뚮뱷?몃쾿
    INCOME_TAX_DECREE = "income_tax_enforcement_decree"        # ?뚮뱷?몃쾿 ?쒗뻾??    INCOME_TAX_RULE = "income_tax_enforcement_rule"            # ?뚮뱷?몃쾿 ?쒗뻾洹쒖튃
    SPECIAL_TAX_ACT = "special_tax_treatment_act"              # 議곗꽭?밸??쒗븳踰?    SPECIAL_TAX_DECREE = "special_tax_treatment_decree"        # 議곗꽭?밸??쒗븳踰??쒗뻾??    SPECIAL_TAX_RULE = "special_tax_treatment_rule"            # 議곗꽭?밸??쒗븳踰??쒗뻾洹쒖튃
    LOCAL_TAX_ACT = "local_tax_act"                            # 吏諛⑹꽭踰?    LOCAL_TAX_DECREE = "local_tax_enforcement_decree"          # 吏諛⑹꽭踰??쒗뻾??    LOCAL_TAX_RULE = "local_tax_enforcement_rule"              # 吏諛⑹꽭踰??쒗뻾洹쒖튃
    FRAMEWORK_TAX_ACT = "framework_tax_act"                    # 援?꽭湲곕낯踰?    FRAMEWORK_TAX_DECREE = "framework_tax_enforcement_decree"  # 援?꽭湲곕낯踰??쒗뻾??    FRAMEWORK_TAX_RULE = "framework_tax_enforcement_rule"      # 援?꽭湲곕낯踰??쒗뻾洹쒖튃
    INHERITANCE_TAX_ACT = "inheritance_tax_act"                # ?곸냽??諛?利앹뿬?몃쾿
    INHERITANCE_TAX_DECREE = "inheritance_tax_enforcement_decree"  # ?곸냽??諛?利앹뿬?몃쾿 ?쒗뻾??

class AmendmentType(str, Enum):
    PARTIAL = "?쇰?媛쒖젙"     # 議곕Ц lineage ?좎?
    FULL = "?꾨?媛쒖젙"        # lineage ?딄? ????root濡?痍④툒
    OTHER_LAW = "?踰뺢컻??   # ?ㅻⅨ 踰뺤씠 ??踰뺤쓣 媛쒖젙 (silent amendment)
    REPEAL = "?먯?"


class AppendixType(str, Enum):
    """
    泥?궧 ?⑥쐞 援щ텇.
    遺移숈? 諛섎뱶??蹂꾨룄 泥?겕 ??寃쎄낵議곗튂/?곸슜濡媛 ?곸슜 踰뺣졊 寃곗젙???듭떖.
    """
    MAIN_BODY = "蹂몄튃"
    BUCHIK = "遺移?          # 寃쎄낵議곗튂, ?곸슜濡 ?ы븿
    BYULTABLE = "蹂꾪몴"       # ?몄쑉?? 怨듭젣?⑦몴
    FORM = "?쒖떇"
    REASON = "?쒓컻?뺤씠??


class ApplicabilityRuleType(str, Enum):
    """
    ??泥?겕媛 ?곸슜?섎뒗 諛⑹떇.
    none: ?쒗뻾???먯?????transfer_date硫??곸슜 (?⑥닚)
    ?곸슜濡: ?뱀젙 ?됱쐞 ?쒖젏 湲곗??쇰줈 ?곸슜 踰붿쐞 紐낆떆
    寃쎄낵議곗튂: ?쒗뻾 ???ъ떎愿怨꾩뿉 ????꾪솚 洹쒖젙
    ?섏젣痍⑤뱷?? 痍⑤뱷?쇱쓣 踰뺤젙 媛꾩＜ 泥섎━
    """
    NONE = "none"
    JEOKYONGYE = "?곸슜濡"
    GYEONGGWAJOCHIUI = "寃쎄낵議곗튂"
    DEEMED_DATE = "?섏젣痍⑤뱷??
    SPECIAL_CASE = "?밸?"


class TopicTag(str, Enum):
    """寃???꾨낫 ?꾪꽣留곸슜 二쇱젣 ?쒓렇"""
    ONE_HOUSE_EXEMPTION = "1?몃?1二쇳깮鍮꾧낵??
    LONG_TERM_DEDUCTION = "?κ린蹂댁쑀?밸퀎怨듭젣"
    HEAVY_TAX = "?ㅼ＜?앹쨷怨?
    TEMPORARY_TWO_HOUSE = "?쇱떆??二쇳깮"
    INHERITED_HOUSE = "?곸냽二쇳깮"
    LONG_TERM_RENTAL = "?κ린?꾨?二쇳깮"
    BUNYANG_RIGHT = "遺꾩뼇沅뚯엯二쇨텒"
    NECESSARY_EXPENSES = "?꾩슂寃쎈퉬"
    TAX_RATE = "?몄쑉"
    NON_RESIDENT = "鍮꾧굅二쇱옄"
    ADJUSTMENT_AREA = "議곗젙??곸???
    BUSINESS_LAND = "鍮꾩궗?낆슜?좎?"
    SPECIAL_TAX_REDUCTION = "議고듅踰뺢컧硫?


@dataclass
class ApplicabilitySpec:
    """
    ??泥?겕媛 ?ㅼ젣濡??곸슜?섎뒗 議곌굔??援ъ“??

    anchors: ?대뼡 ?좎쭨瑜?湲곗??쇰줈 ?쒗뻾???먯??쇱쓣 泥댄겕?섎뒗吏.
             蹂듭닔 媛??(?? ["transfer_date", "acquisition_date"])

    condition_text: ?먯뿰??議곌굔 ???듭빱 ?좎쭨 踰붿쐞 ??異붽? 議곌굔.
                    LLM??理쒖쥌 ?곸슜 ?щ? ?먮떒 ??李몄“.
    ?? "??踰??쒗뻾 ???묐룄遺꾨????곸슜. ??2018-09-13 ?댁쟾 痍⑤뱷遺꾩? 醫낆쟾 洹쒖젙 ?곸슜."
    """
    rule_type: ApplicabilityRuleType
    anchors: List[str] = field(default_factory=lambda: ["transfer_date"])
    condition_text: Optional[str] = None


@dataclass
class LawChunkMetadata:
    """
    踰뺣졊 泥?겕 1媛쒖쓽 ?꾩쟾??硫뷀??곗씠??

    泥?궧 ?⑥쐞: 議?歟? > ???? ?섏?. ?덈Т ?몃텇?뷀븯硫?留λ씫 ?먯떎,
    ?덈Т ?щ㈃ ?щ윭 ?곸슜 regime???욎엫.
    ?⑥꽌/?덉쇅 議고빆? ?먯튃 議고빆怨?媛숈? 泥?겕 ?좎? (遺꾨━ 湲덉?).
    """

    # === Identity ===
    chunk_id: str
    # ?? "income_tax_decree_짠154_p1_v20220101_main"
    #     踰뺣졊ID_議곕쾲????쾲??踰꾩쟾_???
    law_id: LawId
    law_name: str              # ?뚮뱷?몃쾿 ?쒗뻾??    law_level: LawLevel

    article_number: str        # ??54議?    paragraph: Optional[str]  # ????(None?대㈃ 議??꾩껜)
    item: Optional[str]        # ????
    # === Version ===
    lsi_seq: str               # 援??踰뺣졊?뺣낫?쇳꽣 踰꾩쟾 ?앸퀎??    promulgation_date: date    # 怨듯룷??    effective_from: date       # ?쒗뻾??    effective_to: Optional[date]  # ?먯???(None = ?꾪뻾)

    amendment_type: AmendmentType
    article_lineage_root: str
    # ?꾨?媛쒖젙???덉쑝硫???root ?앹꽦. 媛숈? 議곕쾲?몄뿬???꾨?媛쒖젙 ?꾪썑???ㅻⅨ lineage.

    # === 泥?겕 ???===
    appendix_type: AppendixType

    # === Applicability (?듭떖) ===
    applicability: ApplicabilitySpec

    # === Links ===
    supersedes_chunk_id: Optional[str] = None
    superseded_by_chunk_id: Optional[str] = None

    # 蹂몄튃?붾?移??묐갑??留곹겕
    # 蹂몄튃 泥?겕: ?먯떊?먭쾶 ?곸슜?섎뒗 遺移?泥?겕 ID 紐⑸줉
    # 遺移?泥?겕: ?먯떊???섏젙/洹쒖젙?섎뒗 蹂몄튃 泥?겕 ID 紐⑸줉
    linked_buchik_ids: List[str] = field(default_factory=list)
    parent_main_chunk_id: Optional[str] = None

    cross_refs: List[str] = field(default_factory=list)
    # ?? ["income_tax_act_짠89", "special_tax_decree_짠97??"]

    # === Scope Tags (Stage 1 ?꾪꽣?? ===
    entity_scopes: List[str] = field(default_factory=list)
    # ?? ["二쇳깮", "遺꾩뼇沅?] ??EntityScope.value? 留ㅼ묶
    tax_types: List[str] = field(default_factory=list)
    # ?? ["transfer"]
    topic_tags: List[TopicTag] = field(default_factory=list)

    # === ?먮낯 李몄“ ===
    source_url: Optional[str] = None
    # ?? https://law.go.kr/LSW/lsLawLinkInfo.do?lsiSeq=XXXXX
    source_hash: Optional[str] = None  # ?댁슜 蹂寃?媛먯???
    def is_effective_at(self, check_date: date) -> bool:
        """?⑥닚 ?좎쭨 踰붿쐞 泥댄겕 (Stage 1 1李??꾪꽣)"""
        if check_date < self.effective_from:
            return False
        if self.effective_to and check_date > self.effective_to:
            return False
        return True

    def get_applicable_dates(self, date_bundle: "DateBundle") -> List[date]:
        """
        ??泥?겕??applicability anchor???대떦?섎뒗 ?좎쭨 紐⑸줉 諛섑솚.
        Stage 1 ?ы솕 ?꾪꽣?먯꽌 ?ъ슜.
        """
        from .query_input import DateBundle
        result = []
        for anchor_key in self.applicability.anchors:
            d = date_bundle.get_anchor(anchor_key)
            if d is not None:
                result.append(d)
        return result

    def matches_entity_scope(self, scope: "EntityScope") -> bool:
        from .query_input import EntityScope
        return not self.entity_scopes or scope.value in self.entity_scopes

    def matches_tax_type(self, tax_type: "TaxType") -> bool:
        from .query_input import TaxType
        return not self.tax_types or tax_type.value in self.tax_types

 succeeded in 3290ms:
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
        applicability=ApplicabilitySpec(rule_type=ApplicabilityRuleType.NONE),
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

 succeeded in 3226ms:
"""
2?④퀎 踰뺣졊 寃???꾨왂 ?명꽣?섏씠??

Stage 1: SymbolicFilter ??chunk applicability/?좎쭨/scope 湲곕컲 ?꾨낫 醫곹옒.
Stage 2: VectorRanker ???꾨쿋???좎궗??+ reranker濡?理쒖쥌 ?좏깮.
??紐⑤뱢? TaxLawRetriever ABC 留??뺤쓽?섍퀬, 援ы쁽泥대뒗 src/core/retriever_impl.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Protocol

from .chunk_metadata import LawChunkMetadata
from .query_input import DateBundle, RAGQueryInput


@dataclass
class RetrievedChunk:
    """寃??寃곌낵 1嫄???硫뷀??곗씠??+ 蹂몃Ц + ?먯닔."""
    metadata: LawChunkMetadata
    content: str
    score: float
    included_as_linked_buchik: bool = False


class SymbolicFilter(Protocol):
    """Stage 1 ???꾨낫 醫곹엳湲?"""
    def filter(
        self,
        query: RAGQueryInput,
        all_chunks: List[LawChunkMetadata],
    ) -> List[LawChunkMetadata]: ...


class VectorRanker(Protocol):
    """Stage 2 ??踰≫꽣 寃??+ reranker."""
    def rank(
        self,
        query: RAGQueryInput,
        candidates: List[LawChunkMetadata],
    ) -> List[RetrievedChunk]: ...


class TaxLawRetriever(ABC):
    """?낆뒪?몃┝ 怨꾩빟 ???묐룄?뚮뱷??踰뺣졊 寃?됯린."""

    @abstractmethod
    def retrieve(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        """湲곕낯 寃????蹂몄튃 泥?겕 ?곗꽑 諛섑솚."""

    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        """
        蹂몄튃 寃????query.include_buchik=True 硫??곌껐??遺移?泥?겕瑜?蹂닿컯?댁꽌 諛섑솚.
        遺移?寃쎄낵議곗튂/?곸슜濡)? ?곸슜 踰뺣졊 寃곗젙???꾩닔.
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
                buchik_chunk = self._get_chunk_by_id(buchik_id)
                if buchik_chunk is None:
                    continue
                extra.append(
                    RetrievedChunk(
                        metadata=buchik_chunk,
                        content=self._get_content(buchik_id),
                        score=chunk.score,
                        included_as_linked_buchik=True,
                    )
                )
                seen_ids.add(buchik_id)
        return results + extra

    @abstractmethod
    def _get_chunk_by_id(self, chunk_id: str) -> Optional[LawChunkMetadata]:
        """?④굔 硫뷀??곗씠??議고쉶 (遺移?蹂닿컯??."""

    @abstractmethod
    def _get_content(self, chunk_id: str) -> str:
        """?④굔 蹂몃Ц 議고쉶 (遺移?蹂닿컯??."""

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\query_input.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\eval\\debate.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\eval\\golden_injector.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\retrieval\\llm_fn.py | Select-Object -First 240" in C:\Users\user\cording2025\tax-rag
 succeeded in 3444ms:
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

from .tax_constants import TaxConstantsRegistry as _TCR

# backward-compat aliases ??use TaxConstantsRegistry.get() for version-aware lookups
HIGH_VALUE_THRESHOLD: int = _TCR.get("HIGH_VALUE_THRESHOLD", date.today())
SANGSAENG_WINDOW_START: date = _TCR.get("SANGSAENG_WINDOW_START", date.today())
SANGSAENG_WINDOW_END: date = _TCR.get("SANGSAENG_WINDOW_END", date.today())
SANGSAENG_MAX_INCREASE_RATE: float = _TCR.get("SANGSAENG_MAX_INCREASE_RATE", date.today())
HEAVY_TAX_SUSPENSION_END: date = _TCR.get("HEAVY_TAX_SUSPENSION_END", date.today())


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
    def increase_rate(self) -> float:
        if self.previous_monthly_rent <= 0:
            return float("inf")
        return (self.new_monthly_rent - self.previous_monthly_rent) / self.previous_monthly_rent


 succeeded in 3454ms:
"""
Red Team / Blue Team ?쇱웳 ?붿쭊.

?먮쫫:
  Blue ?먮떒 ??Red 諛섎컯 ??Blue 諛⑹뼱(異붽? 寃?? ??寃곌낵 ???
  寃곌낵??data/debates/ JSONL???꾩쟻?섍퀬
  blue_wins ??golden set, red_wins ???ㅻ쪟 ?⑦꽩?쇰줈 遺꾨쪟?쒕떎.

?몃━嫄?議곌굔 (pipeline.py?먯꽌 ?몄텧):
  - confidence < 0.80
  - danger_flags >= 2媛?
  - verdict == "?ъ떎愿怨꾨?議?
  ?먮뒗 batch 紐⑤뱶 (紐⑤뱺 耳?댁뒪 ?ш???
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import anthropic
from dotenv import load_dotenv

from src.agents.prompts import (
    BLUE_DEFENSE_SYSTEM,
    BLUE_DEFENSE_TEMPLATE,
    RED_TEAM_CHALLENGE_TEMPLATE,
    RED_TEAM_SYSTEM,
)
from src.domain.pipeline import PipelineResult
from src.domain.tax_answer import TaxAnswer

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

DEBATE_DIR = Path("data/debates")
RED_WINS_DIR = Path("data/red_wins")
BLUE_WINS_DIR = Path("data/blue_wins")
GOLDEN_FILE = Path("data/golden/qa_pairs.json")


# ?? ?곗씠??援ъ“ ???????????????????????????????????????????????????????????????

@dataclass
class RedChallenge:
    has_challenge: bool
    challenge_type: str          # "?좊졊?몄슜" | "?붽굔?ㅽ뙋" | ... | "?댁쓽?놁쓬"
    challenge_text: str
    challenged_citations: List[str] = field(default_factory=list)
    missing_articles: List[str] = field(default_factory=list)
    red_confidence: float = 0.0


@dataclass
class BlueDefense:
    defense_result: str          # "defended" | "conceded" | "partial"
    revised_verdict: str
    defense_text: str
    new_citations: List[str] = field(default_factory=list)
    blue_confidence: float = 0.0


@dataclass
class DebateRecord:
    debate_id: str
    trace_id: str
    timestamp: str
    fact_json: dict
    blue_answer: dict            # ?먮낯 Blue ?먮떒
    red_challenge: dict          # Red 諛섎컯
    blue_defense: dict           # Blue 諛⑹뼱
    outcome: str                 # "blue_won" | "red_won" | "no_contest" | "draw"
    new_chunks_found: List[str] = field(default_factory=list)
    promoted_to_golden: bool = False


# ?? LLM ?몄텧 ?ы띁 ?????????????????????????????????????????????????????????????

def _call_claude_sync(system: str, user: str, max_tokens: int = 1024) -> dict:
    """?숆린 Claude ?몄텧 ??JSON ?뚯떛. ?뚯떛 ?ㅽ뙣 ??raw 諛섑솚."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_parse_error": raw}


# ?? Red Team: 諛섎컯 ????????????????????????????????????????????????????????????

async def _red_challenge(
    fact_json: dict,
    blue_answer: TaxAnswer,
    retrieved_chunk_ids: List[str],
) -> RedChallenge:
    """Red Team??Blue ?먮떒??寃?좏븯怨??ㅻ쪟瑜?諛섎컯?쒕떎."""

    citations_str = "\n".join(
        f"- {c.article}" if hasattr(c, "article") else f"- {c}"
        for c in blue_answer.citations
    ) or "(?놁쓬)"

    fact_summary = json.dumps(fact_json, ensure_ascii=False, indent=2)

    prompt = RED_TEAM_CHALLENGE_TEMPLATE.format(
        fact_summary=fact_summary,
        verdict=blue_answer.verdict,
        answer=blue_answer.answer[:800],
        citations=citations_str,
        confidence=blue_answer.confidence,
        chunk_ids=", ".join(retrieved_chunk_ids[:10]),
    )

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: _call_claude_sync(RED_TEAM_SYSTEM, prompt)
    )

    if "_parse_error" in data:
        return RedChallenge(
            has_challenge=False,
            challenge_type="?댁쓽?놁쓬",
            challenge_text=data["_parse_error"],
        )

    return RedChallenge(
        has_challenge=data.get("has_challenge", False),
        challenge_type=data.get("challenge_type", "?댁쓽?놁쓬"),
        challenge_text=data.get("challenge_text", ""),
        challenged_citations=data.get("challenged_citations", []),
        missing_articles=data.get("missing_articles", []),
        red_confidence=float(data.get("red_confidence", 0.0)),
    )


# ?? Blue Team: 諛⑹뼱 (異붽? 寃???ы븿) ?????????????????????????????????????????

async def _blue_defend(
    blue_answer: TaxAnswer,
    red_challenge: RedChallenge,
    fact_json: dict,
) -> tuple[BlueDefense, List[str]]:
    """
    Blue Team??Red 諛섎컯???묐떟?쒕떎.
    missing_articles瑜??ш??됲빐 異붽? 而⑦뀓?ㅽ듃瑜??뺣낫????諛⑹뼱?쒕떎.
    諛섑솚: (BlueDefense, ?덈줈 李얠? chunk_id 紐⑸줉)
    """
    additional_context = ""
    new_chunk_ids: List[str] = []

    # ?꾨씫 議곕Ц 異붽? 寃??
    if red_challenge.missing_articles:
        try:
            from src.rag import retrieve_tax_law
            for article_hint in red_challenge.missing_articles[:3]:
                chunks = retrieve_tax_law(article_hint, top_k=10, rerank_top_n=3)
                for c in chunks:
                    additional_context += (
                        f"\n[異붽?] {c.law_name} ??c.article_number}議?{c.article_title}\n"
                        f"{c.full_text[:400]}\n"
                    )
                    new_chunk_ids.append(c.id)
        except Exception:
            additional_context = "(異붽? 寃???ㅽ뙣)"

    if not additional_context:
        additional_context = "(異붽? 寃??寃곌낵 ?놁쓬)"

    prompt = BLUE_DEFENSE_TEMPLATE.format(
        verdict=blue_answer.verdict,
        answer=blue_answer.answer[:600],
        challenge_text=red_challenge.challenge_text,
        additional_context=additional_context[:1500],
    )

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: _call_claude_sync(BLUE_DEFENSE_SYSTEM, prompt, max_tokens=1500)
    )

    if "_parse_error" in data:
        defense = BlueDefense(
            defense_result="defended",
            revised_verdict=blue_answer.verdict,
            defense_text=data["_parse_error"],
        )
    else:
        defense = BlueDefense(
            defense_result=data.get("defense_result", "defended"),
            revised_verdict=data.get("revised_verdict", blue_answer.verdict),
            defense_text=data.get("defense_text", ""),
            new_citations=data.get("new_citations", []),
            blue_confidence=float(data.get("blue_confidence", 0.0)),
        )

    return defense, new_chunk_ids


# ?? 寃곌낵 ?먯젙 ?????????????????????????????????????????????????????????????????

def _judge_outcome(red: RedChallenge, blue: BlueDefense) -> str:
    """?쇱웳 寃곌낵 ?먯젙."""
    if not red.has_challenge:
        return "no_contest"          # Red媛 ?댁쓽 ?놁쓬
    if blue.defense_result == "conceded":
        return "red_won"             # Blue媛 ?ㅻ쪟 ?몄젙
    if blue.defense_result == "defended" and blue.blue_confidence >= 0.75:
        return "blue_won"            # Blue媛 諛⑹뼱 ?깃났
    return "draw"                    # ?먯젙 遺덇?


# ?? ?????????????????????????????????????????????????????????????????????????

def _ensure_dirs():
    for d in (DEBATE_DIR, RED_WINS_DIR, BLUE_WINS_DIR, GOLDEN_FILE.parent):
        d.mkdir(parents=True, exist_ok=True)


def _save_debate(record: DebateRecord) -> None:
    _ensure_dirs()
    path = DEBATE_DIR / f"{record.debate_id}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump({
            "debate_id": record.debate_id,
            "trace_id": record.trace_id,
            "timestamp": record.timestamp,
            "outcome": record.outcome,
            "fact_json": record.fact_json,
            "blue_answer": record.blue_answer,
            "red_challenge": record.red_challenge,
            "blue_defense": record.blue_defense,
            "new_chunks_found": record.new_chunks_found,
            "promoted_to_golden": record.promoted_to_golden,
        }, f, ensure_ascii=False, indent=2)


def _save_to_outcome_dir(record: DebateRecord) -> None:
    """寃곌낵???곕씪 red_wins / blue_wins ???щ쭅?????蹂듭궗 ???"""
    _ensure_dirs()
    if record.outcome == "red_won":
        target_dir = RED_WINS_DIR
    elif record.outcome in ("blue_won", "no_contest"):
        target_dir = BLUE_WINS_DIR

 succeeded in 3442ms:
"""
怨⑤뱺????L4 few-shot 二쇱엯湲?

debate.py媛 blue_won/no_contest 耳?댁뒪瑜?data/golden/qa_pairs.json???볦쑝硫?
??紐⑤뱢???꾩옱 吏덈Ц怨??좎궗??耳?댁뒪瑜?怨⑤씪 L4 ?꾨＼?꾪듃???덉떆濡?二쇱엯?쒕떎.

?좎궗??湲곗?:
  1. property_type ?쇱튂
  2. acquisition_reason ?쇱튂
  3. household_house_count ?쇱튂
  4. ?밸? ?뚮옒洹?寃뱀묠 ??
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

GOLDEN_FILE = Path("data/golden/qa_pairs.json")
MAX_SHOTS = 2        # ?꾨＼?꾪듃??二쇱엯??理쒕? ?덉떆 ??
MIN_GOLDEN = 5       # 怨⑤뱺??理쒖냼 ?ш린 (?댄븯硫?二쇱엯 ????


def _load_golden() -> list[dict]:
    if not GOLDEN_FILE.exists():
        return []
    with GOLDEN_FILE.open(encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _score_similarity(fact_json: dict, golden_fact: dict) -> int:
    """??fact_json???좎궗???먯닔 (?믪쓣?섎줉 ?좎궗)."""
    score = 0
    for key in ("property_type", "acquisition_reason"):
        if fact_json.get(key) == golden_fact.get(key):
            score += 3
    if fact_json.get("household_house_count") == golden_fact.get("household_house_count"):
        score += 2

    # ?밸? ?뚮옒洹?寃뱀묠
    sc1 = set((fact_json.get("special_cases") or {}).keys())
    sc2 = set((golden_fact.get("special_cases") or {}).keys())
    score += len(sc1 & sc2)

    return score


def find_similar_cases(fact_json: dict, top_n: int = MAX_SHOTS) -> list[dict]:
    """fact_json怨?媛???좎궗??怨⑤뱺 耳?댁뒪 top_n媛?諛섑솚."""
    golden = _load_golden()
    if len(golden) < MIN_GOLDEN:
        return []

    scored = [
        (g, _score_similarity(fact_json, g.get("fact_json", {})))
        for g in golden
        if g.get("source") == "debate" and g.get("verdict")
    ]
    scored.sort(key=lambda x: -x[1])
    return [g for g, s in scored[:top_n] if s > 0]


def build_few_shot_block(fact_json: dict) -> str:
    """
    L4 ?꾨＼?꾪듃???쎌엯??few-shot 釉붾줉 ?앹꽦.
    ?좎궗 耳?댁뒪媛 ?놁쑝硫?鍮?臾몄옄??諛섑솚.
    """
    cases = find_similar_cases(fact_json)
    if not cases:
        return ""

    lines = ["[李멸퀬 ???좎궗 耳?댁뒪 寃利??щ?]"]
    for i, case in enumerate(cases, 1):
        lines.append(
            f"\n?덉떆 {i}. {case.get('fact_json', {}).get('property_type', '')} "
            f"/ {case.get('fact_json', {}).get('acquisition_reason', '')} "
            f"/ {case.get('fact_json', {}).get('household_house_count', '')}二쇳깮"
        )
        lines.append(f"  ?먮떒: {case.get('verdict', '')}")
        answer_preview = (case.get("answer") or "")[:200]
        lines.append(f"  洹쇨굅: {answer_preview}")
        if case.get("citations"):
            lines.append(f"  ?몄슜: {', '.join(case['citations'][:3])}")

    return "\n".join(lines)


def golden_summary() -> dict:
    """怨⑤뱺???꾪솴."""
    golden = _load_golden()
    debate_cases = [g for g in golden if g.get("source") == "debate"]
    verdicts: dict[str, int] = {}
    for g in debate_cases:
        v = g.get("verdict", "unknown")
        verdicts[v] = verdicts.get(v, 0) + 1
    return {
        "total_golden": len(golden),
        "debate_sourced": len(debate_cases),
        "verdict_distribution": verdicts,
    }

 succeeded in 3443ms:
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
            f"{chunk.content}"
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
            max_tokens=2048,
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

web search: 
web search: site:law.go.kr 소득세법 부칙 양도하는 분부터 적용 취득하는 분부터 적용
codex
검색 경로는 예상대로 `linked_buchik_ids`로 부칙을 붙여 주지만, 적용 기준 자체는 구조화되지 않아 retriever 단계에서 전혀 걸러지지 않습니다. 남은 확인 포인트는 output validation과 prompt가 이 오류를 얼마나 막는지입니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\output_validator.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\agents\\prompts.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\domain\\pipeline.py | Select-Object -First 260" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content src\\ingestion\\collect.py | Select-Object -First 320" in C:\Users\user\cording2025\tax-rag
 succeeded in 3474ms:
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

 succeeded in 3493ms:
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


def _build_consulting_scenarios(query: RAGQueryInput, answer: TaxAnswer) -> List[dict]:
    """
    而⑥꽕??紐⑤뱶: ?묐룄/利앹뿬/遺?대?利앹뿬 ?쒕굹由ъ삤 鍮꾧탳.
    ?몄븸 怨꾩궛? TaxCalculator ?꾩꽦 ???곕룞 ?덉젙 ???꾩옱???쒕굹由ъ삤 援ъ“留?諛섑솚.
    """
    fv = query.fact_vector
    scenarios: List[dict] = [
        {
            "type": "?묐룄",
            "description": "?꾩옱 怨꾪쉷?濡??묐룄",
            "verdict": answer.verdict,
            "estimated_tax": None,   # TaxCalculator ?곕룞 ??梨꾩?
            "notes": answer.warnings[:2] if answer.warnings else [],
        }
    ]

    # 利앹뿬 ?쒕굹由ъ삤 ??諛곗슦?먃룹쭅怨?利앹뿬 媛?ν븳 寃쎌슦留?
    if fv.household_house_count >= 1:
        scenarios.append({
            "type": "利앹뿬",
            "description": "諛곗슦???먮뒗 吏곴퀎議대퉬?띿뿉寃?利앹뿬",
            "verdict": "媛먮㈃媛??,
            "estimated_tax": None,
            "notes": ["利앹뿬??蹂꾨룄 諛쒖깮", "?댁썡怨쇱꽭 10??洹쒖젙 ?곸슜"],
        })

    # 遺?대?利앹뿬 ?쒕굹由ъ삤 ???꾨?蹂댁쬆湲??덈뒗 寃쎌슦
    scenarios.append({
        "type": "遺?대?利앹뿬",
        "description": "?꾨?蹂댁쬆湲??ы븿 遺?대?利앹뿬",
        "verdict": "寃?좏븘??,
        "estimated_tax": None,
        "notes": ["梨꾨Т 遺遺꾩? ?묐룄?뚮뱷?? ?섎㉧吏??利앹뿬??, "?꾨Ц媛 ?쒕??덉씠???꾩슂"],
    })

    return scenarios


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
        result.consulting_scenarios = _build_consulting_scenarios(query, validated)

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

 succeeded in 3505ms:
"""
L5 ??Output Validator

LLM 異쒕젰???섏삩 ???ㅽ뻾. ??醫낅쪟???ㅻ쪟瑜?諛⑹뼱:

- 議곗슜???ㅻ쪟: ?댁썡怨쇱꽭 臾댁떆?섍퀬 "鍮꾧낵?? ??L2媛 ?≪븘???섏?留??듦낵??寃쎌슦 理쒗썑 諛⑹뼱
- ?먯떊媛??덈뒗 ?ㅻ쪟: 怨좉?二쇳깮 ?뺤씤 ?놁씠 "100% 鍮꾧낵?? ???좊ː??媛뺤젣 ?섑뼢

?먯튃: confidence媛 ?믪븘??missing_facts媛 ?덉쑝硫??섑뼢.
     ?몄슜 chunk媛 寃??寃곌낵???놁쑝硫?phantom citation) ?좊ː??0.3 ?댄븯.
"""

from __future__ import annotations

from typing import List, Optional, Set

from .tax_answer import ExpertReviewSignal, TaxAnswer

# ?좊ː???곹븳 ??missing_facts ?덉쓣 ??CONFIDENCE_CAP_WITH_MISSING = 0.75

# phantom citation 諛쒓껄 ???좊ː??媛뺤젣 ?곹븳
CONFIDENCE_CAP_PHANTOM_CITATION = 0.3

# "鍮꾧낵?? verdict?몃뜲 怨좉?二쇳깮 誘명솗?????좊ː???곹븳
CONFIDENCE_CAP_UNCHECKED_HIGH_VALUE = 0.6


# ?덇퇋/?먮? ?섏〈?꾧? ?믪? danger_flag ???몃Т???꾨Ц 寃??湲고쉶 ?좏샇
# ?먮윭媛 ?꾨땲???꾩씠??諛쒓뎬 ?좏샇 ???먯??좎닔濡??꾨Ц媛 ?곷떞 媛移?利앷?
EXPERT_REVIEW_TRIGGERS: dict[str, dict] = {
    "?댁썡怨쇱꽭": {
        "category": "?댁꽍?ㅽ댘",
        "description": "?댁썡怨쇱꽭(짠97??) vs 遺?뱁뻾?꾧퀎?곕???짠101) ?좏깮 ?곸슜? ?덇퇋쨌?먮????곕씪 ?щ씪吏묐땲??",
        "opportunity": "諛곗슦??利앹뿬 ???묐룄 ????洹쒖젙??援먯감 ?곸슜 ???몄븸 李⑥씠媛 ?щ?濡??몃Т??寃???꾩씠??,
        "related_article": "?뚮뱷?몃쾿 ??7議곗쓽2, ??01議?,
    },
    "?곸냽二쇳깮": {
        "category": "?댁꽍?ㅽ댘",
        "description": "怨듬룞?곸냽 吏?뺣낫?좎옄 ?붽굔, ?숆굅遊됱뼇 ?⑹궛 ?먮떒 ?깆? ?덇퇋쨌?먮? ?섏〈 ?곸뿭?낅땲??",
        "opportunity": "理쒕?吏遺꽷룰굅二쇱옄쨌理쒖뿰?μ옄 湲곗? 吏??遺꾩웳, ?쇱긽?띿씤 蹂댁쑀湲곌컙 ?⑹궛 踰붿쐞 ???몃Т??寃???꾩씠??,
        "related_article": "?뚮뱷?몃쾿 ?쒗뻾????55議?????,
    },
    "?곸깮?꾨?": {
        "category": "?덇퇋怨듬갚",
        "description": "?곸깮?꾨? 吏곸쟾 ?꾨?李④퀎??踰붿쐞, 蹂댁쬆湲??붿꽭 ?꾪솚 ??5% 怨꾩궛 諛⑹떇???덇퇋濡?援ъ껜?붾맗?덈떎.",
        "opportunity": "?좉퇋 ?꾩감??vs 媛깆떊 怨꾩빟 寃쎄퀎 遺꾩웳 ??5% 利앹븸 ?붽굔 異⑹” ?щ? ?ㅺ퀎 ?꾩씠??,
        "related_article": "?뚮뱷?몃쾿 ?쒗뻾????55議곗쓽3",
    },
    "怨듬룞紐낆쓽": {
        "category": "?댁꽍?ㅽ댘",
        "description": "怨듬룞紐낆쓽 吏遺꾨퀎 二쇳깮 ???곗젙 諛⑹떇, 1二쇳깮 痍④툒 湲곗?? ?덇퇋 ?섏〈 ?곸뿭?낅땲??",
        "opportunity": "吏遺꾩쑉 湲곗? vs 1二쇳깮 痍④툒 ??怨듬룞紐낆쓽 ?덉꽭 援ъ“ ?ㅺ퀎 ?꾩씠??,
        "related_article": "?뚮뱷?몃쾿 ?쒗뻾????54議?,
    },
    "?ш굔異뺤옱媛쒕컻?먯“?⑹썝": {
        "category": "?덇퇋怨듬갚",
        "description": "泥?궛湲??⑸?쨌?섎졊 ??鍮꾨? 怨쇱꽭 怨꾩궛, ?먯“?⑹썝 蹂댁쑀湲곌컙 ?듭궛 諛⑹떇? ?덇퇋濡?援ъ껜?붾맗?덈떎.",
        "opportunity": "泥?궛湲??섎졊遺?鍮꾨? 怨쇱꽭 遺꾧린, 硫몄떎 ???좎텞 ?낆＜沅?蹂댁쑀湲곌컙 湲곗궛 ???몃Т??寃???꾩씠??,
        "related_article": "?뚮뱷?몃쾿 ?쒗뻾????56議곗쓽2",
    },
    "?뱀닔愿怨꾩옄嫄곕옒": {
        "category": "議곗꽭遺덈났媛??,
        "description": "?뱀닔愿怨꾩옄 ?媛?묐룄 ??遺?뱁뻾?꾧퀎?곕????곸슜 ?щ????쒓? ?낆쬆 諛⑸쾿???곕씪 ?ㅽ닾?댁쭏 ???덉뒿?덈떎.",
        "opportunity": "?쒓? vs ?묐룄媛???낆쬆 ?꾨왂, 議곗꽭?ы뙋 ?좊? ?쒖슜 ???몃Т???덉꽭쨌遺덈났 ?꾩씠??,
        "related_article": "?뚮뱷?몃쾿 ??01議?,
    },
    "?숆굅遊됱뼇?⑷?": {
        "category": "?댁꽍?ㅽ댘",
        "description": "?숆굅遊됱뼇 ?⑷? ?붽굔(60?맞룹쨷利앹쭏?? 異⑹” ?щ? 諛?10??湲곗궛?먯씠 ?덇퇋 ?곸젏?낅땲??",
        "opportunity": "?⑷???湲곗? ?낆쬆, 蹂꾧굅 ???ы빀媛 泥섎━ ???몃Т???붽굔 異⑹” 寃???꾩씠??,
        "related_article": "?뚮뱷?몃쾿 ?쒗뻾????55議?????,
    },
}


def validate_output(
    answer: TaxAnswer,
    retrieved_chunk_ids: Set[str],
    danger_flags: Optional[List[str]] = None,
) -> TaxAnswer:
    """
    TaxAnswer瑜?寃利앺븯怨??꾩슂 ??confidence瑜??섑뼢 議곗젙.

    Args:
        answer: LLM???앹꽦??TaxAnswer
        retrieved_chunk_ids: Stage 1+2 寃?됱뿉???ㅼ젣濡?諛섑솚??chunk ID 吏묓빀
        danger_flags: L2 fact_checker?먯꽌 ?먯????꾪뿕 ?뚮옒洹?紐⑸줉 (?덇퇋 ?좏샇 ?먯???

    Returns:
        warnings, expert_review_signals 異붽? 諛?confidence 議곗젙??TaxAnswer
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

    # ?? 5. ?덇퇋/?먮? ?섏〈 ?곸뿭 ???몃Т???꾨Ц 寃??湲고쉶 ?좏샇 ?????????????
    # ?먮윭 ?좏샇媛 ?꾨땲???꾩씠??諛쒓뎬 ?좏샇 ??confidence 議곗젙 ?놁쓬
    expert_signals: List[ExpertReviewSignal] = list(answer.expert_review_signals)
    active_flags = set(danger_flags or [])
    already_categories = {s.category + s.related_article for s in expert_signals}

    for flag in active_flags:
        trigger = EXPERT_REVIEW_TRIGGERS.get(flag)
        if not trigger:
            continue
        key = trigger["category"] + (trigger.get("related_article") or "")
        if key in already_categories:
            continue
        expert_signals.append(ExpertReviewSignal(
            category=trigger["category"],
            description=trigger["description"],
            opportunity=trigger["opportunity"],
            related_article=trigger.get("related_article"),
        ))
        already_categories.add(key)

    # ?? 6. 理쒖쥌 諛섑솚 ?????????????????????????????????????????????????????
    changed = (
        confidence != answer.confidence
        or warnings != answer.warnings
        or expert_signals != answer.expert_review_signals
    )
    if changed:
        return answer.with_update(
            confidence=confidence,
            warnings=warnings,
            expert_review_signals=expert_signals,
        )
    return answer

 succeeded in 3523ms:
"""
踰뺣졊 ?곗씠???섏쭛 ?ㅽ겕由쏀듃
www.law.go.kr DRF API ??data/raw/ (XML) + data/processed/ (JSON chunks)

踰꾩쟾 愿由??꾨왂:
- 媛?踰뺣졊??媛쒖젙 ?대젰??紐⑤몢 ?섏쭛 (理쒓렐 YEARS_BACK??
- 媛?踰꾩쟾(MST)??effective_date + expiration_date 遺??- chunk ID = {version_mst}_{議곕Ц?? ??踰꾩쟾蹂?怨좎쑀??蹂댁옣
"""
import json
import ssl
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import requests
import urllib3
from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OC = "jctax"
BASE_URL = "https://www.law.go.kr/DRF"
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
YEARS_BACK = 30  # 理쒓렐 N?꾩튂 媛쒖젙 踰꾩쟾 ?섏쭛 (痍⑤뱷???뚭툒 ???


def _make_session() -> requests.Session:
    """law.go.kr SSL ?명솚???곗꽑 ?몄뀡 ???ъ떆??3???ы븿"""
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=urllib3.Retry(total=3, backoff_factor=2))
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = False  # law.go.kr TLS ?몃뱶?곗씠???명솚??    session.headers.update({"User-Agent": "Mozilla/5.0 (tax-rag collector)"})
    return session


_SESSION = _make_session()

TARGET_LAWS = [
    # ?뚮뱷?몃쾿 怨꾩뿴 ??짠89 鍮꾧낵?? 짠104 以묎낵, 짠154 嫄곗＜?붽굔
    {"name": "?뚮뱷?몃쾿",                    "mst": "285523", "category": "踰뺣쪧"},
    {"name": "?뚮뱷?몃쾿 ?쒗뻾??,              "mst": "285631", "category": "??듬졊??},
    {"name": "?뚮뱷?몃쾿 ?쒗뻾洹쒖튃",            "mst": "284987", "category": "遺??},
    # 議곗꽭?밸??쒗븳踰?怨꾩뿴 ???쇱떆??二쇳깮, ?곸깮?꾨?, ?띿뼱珥뚯＜?? 怨듭씡?섏슜 ??    {"name": "議곗꽭?밸??쒗븳踰?,              "mst": "285907", "category": "踰뺣쪧"},
    {"name": "議곗꽭?밸??쒗븳踰??쒗뻾??,        "mst": "286053", "category": "??듬졊??},
    {"name": "議곗꽭?밸??쒗븳踰??쒗뻾洹쒖튃",      "mst": "284611", "category": "遺??},
    # 吏諛⑹꽭踰?怨꾩뿴 ???묐룄?뚮뱷??吏諛⑹냼?앹꽭 10% ?곕룞
    {"name": "吏諛⑹꽭踰?,                    "mst": "282559", "category": "踰뺣쪧"},
    {"name": "吏諛⑹꽭踰??쒗뻾??,             "mst": "285497", "category": "??듬졊??},
    {"name": "吏諛⑹꽭踰??쒗뻾洹쒖튃",           "mst": "282705", "category": "遺??},
    # 援?꽭湲곕낯踰?怨꾩뿴 ??媛?곗꽭, 寃쎌젙泥?뎄, 遺?뱁뻾?꾧퀎?곕???짠39
    {"name": "援?꽭湲곕낯踰?,                  "mst": "280373", "category": "踰뺣쪧"},
    {"name": "援?꽭湲곕낯踰??쒗뻾??,           "mst": "283623", "category": "??듬졊??},
    {"name": "援?꽭湲곕낯踰??쒗뻾洹쒖튃",         "mst": "284607", "category": "遺??},
    # ?곸냽??諛?利앹뿬?몃쾿 怨꾩뿴 ???댁썡怨쇱꽭(짠97??) 利앹뿬 湲곗? 議고쉶??    {"name": "?곸냽??諛?利앹뿬?몃쾿",          "mst": "276123", "category": "踰뺣쪧"},
    {"name": "?곸냽??諛?利앹뿬?몃쾿 ?쒗뻾??,   "mst": "283637", "category": "??듬졊??},
]


# ?? 踰꾩쟾 ?대젰 議고쉶 ????????????????????????????????????????????????????????????

def fetch_law_version_list(law_name: str) -> list[dict]:
    """
    踰뺣졊紐낆쑝濡?媛쒖젙 ?대젰 ?곸쓽 紐⑤뱺 踰꾩쟾 議고쉶.
    諛섑솚: [{"mst", "effective_date", "promulgation_date", "expiration_date"}, ...]
    ?쒗뻾???ㅻ쫫李⑥닚 ?뺣젹, 留뚮즺???먮룞 怨꾩궛.
    """
    url = f"{BASE_URL}/lawSearch.do"
    params = {
        "OC": OC,
        "target": "law",
        "query": law_name,
        "display": 100,
        "type": "XML",
    }
    resp = _SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    try:
        root = ET.fromstring(resp.text.encode("utf-8"))
    except ET.ParseError:
        print(f"  ??{law_name} ?대젰 XML ?뚯떛 ?ㅽ뙣, ?꾪뻾 踰꾩쟾留??ъ슜")
        return []

    cutoff = (datetime.now() - timedelta(days=YEARS_BACK * 365)).strftime("%Y%m%d")

    versions = []
    for law_elem in root.findall(".//踰뺣졊"):
        name_elem = law_elem.find("踰뺣졊紐낇븳湲")
        if name_elem is None or name_elem.text is None:
            continue
        if name_elem.text.strip() != law_name:
            continue

        mst_elem = law_elem.find("踰뺣졊?쇰젴踰덊샇")
        eff_elem = law_elem.find("?쒗뻾?쇱옄")
        prom_elem = law_elem.find("怨듯룷?쇱옄")

        if mst_elem is None or mst_elem.text is None:
            continue

        eff_date = eff_elem.text.strip() if eff_elem is not None and eff_elem.text else ""
        if eff_date and eff_date < cutoff:
            continue

        versions.append({
            "mst": mst_elem.text.strip(),
            "effective_date": eff_date,
            "promulgation_date": prom_elem.text.strip() if prom_elem is not None and prom_elem.text else "",
            "expiration_date": "",
        })

    if not versions:
        return []

    # ?쒗뻾???ㅻ쫫李⑥닚 ?뺣젹
    versions.sort(key=lambda x: x["effective_date"])

    # 留뚮즺??= ?ㅼ쓬 踰꾩쟾 ?쒗뻾???꾨궇
    for i, v in enumerate(versions[:-1]):
        next_eff = versions[i + 1]["effective_date"]
        if next_eff:
            exp_dt = datetime.strptime(next_eff, "%Y%m%d") - timedelta(days=1)
            v["expiration_date"] = exp_dt.strftime("%Y%m%d")

    # 留덉?留??꾪뻾) 踰꾩쟾? 留뚮즺???놁쓬
    return versions


# ?? XML ?섏쭛 ??????????????????????????????????????????????????????????????????

def fetch_law_xml(mst: str) -> str:
    url = f"{BASE_URL}/lawService.do"
    params = {"OC": OC, "target": "law", "MST": mst, "type": "XML"}
    resp = _SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


# ?? XML ?뚯떛 ??泥?겕 ???????????????????????????????????????????????????????????

def parse_xml_to_chunks(xml_text: str, law_info: dict, version: dict) -> list[dict]:
    """
    version: {"mst", "effective_date", "promulgation_date", "expiration_date"}
    chunk ID = {version_mst}_{議곕Ц??
    """
    root = ET.fromstring(xml_text.encode("utf-8"))
    chunks = []

    law_name_elem = root.find(".//踰뺣졊紐낇븳湲")
    law_name = law_name_elem.text.strip() if law_name_elem is not None else law_info["name"]

    for 議곕Ц?⑥쐞 in root.findall(".//議곕Ц?⑥쐞"):
        議곕Ц??= 議곕Ц?⑥쐞.get("議곕Ц??, "")
        議곕Ц踰덊샇_elem = 議곕Ц?⑥쐞.find("議곕Ц踰덊샇")
        議곕Ц?щ?_elem = 議곕Ц?⑥쐞.find("議곕Ц?щ?")
        議곕Ц?쒕ぉ_elem = 議곕Ц?⑥쐞.find("議곕Ц?쒕ぉ")
        ?쒗뻾?쇱옄_elem = 議곕Ц?⑥쐞.find("議곕Ц?쒗뻾?쇱옄")
        ?댁슜_elem = 議곕Ц?⑥쐞.find("議곕Ц?댁슜")

        議곕Ц踰덊샇 = 議곕Ц踰덊샇_elem.text.strip() if 議곕Ц踰덊샇_elem is not None and 議곕Ц踰덊샇_elem.text else ""
        議곕Ц?щ? = 議곕Ц?щ?_elem.text.strip() if 議곕Ц?щ?_elem is not None and 議곕Ц?щ?_elem.text else ""
        議곕Ц?쒕ぉ = 議곕Ц?쒕ぉ_elem.text.strip() if 議곕Ц?쒕ぉ_elem is not None and 議곕Ц?쒕ぉ_elem.text else ""
        ?쒗뻾?쇱옄 = ?쒗뻾?쇱옄_elem.text.strip() if ?쒗뻾?쇱옄_elem is not None and ?쒗뻾?쇱옄_elem.text else version["effective_date"]
        ?댁슜 = ?댁슜_elem.text.strip() if ?댁슜_elem is not None and ?댁슜_elem.text else ""

        ??list = []
        for ??in 議곕Ц?⑥쐞.findall(".//??):
            ??쾲??elem = ??find("??쾲??)
            ??궡??elem = ??find("??궡??)
            ??list = []
            for ??in ??findall(".//??):
                ?몃쾲??elem = ??find("?몃쾲??)
                ?몃궡??elem = ??find("?몃궡??)
                ??list.append({
                    "?몃쾲??: ?몃쾲??elem.text.strip() if ?몃쾲??elem is not None and ?몃쾲??elem.text else "",
                    "?몃궡??: ?몃궡??elem.text.strip() if ?몃궡??elem is not None and ?몃궡??elem.text else "",
                })
            ??list.append({
                "??쾲??: ??쾲??elem.text.strip() if ??쾲??elem is not None and ??쾲??elem.text else "",
                "??궡??: ??궡??elem.text.strip() if ??궡??elem is not None and ??궡??elem.text else "",
                "??: ??list,
            })

        if not ?댁슜 and not ??list:
            continue

        full_text_parts = []
        if ?댁슜:
            full_text_parts.append(?댁슜)
        for ??in ??list:
            if ??"??궡??]:
                full_text_parts.append(f"  {??'??궡??]}")
            for ??in ??"??]:
                if ??"?몃궡??]:
                    full_text_parts.append(f"    {??'?몃궡??]}")

        # 蹂꾪몴 ?대?吏 ?쒓렇 媛먯? (manual_review_required ?뚮옒洹?
        is_table_article = "蹂꾪몴" in 議곕Ц?쒕ぉ or "蹂꾪몴" in 議곕Ц踰덊샇
        has_image_placeholder = "<洹몃┝>" in ?댁슜 or "[洹몃┝]" in ?댁슜
        manual_review_required = is_table_article or has_image_placeholder

        chunk = {
            "id": f"{version['mst']}_{議곕Ц??",
            "law_name": law_name,
            "law_mst": law_info["mst"],          # 踰뺣졊 怨좎쑀 ID (踰꾩쟾 臾닿?)
            "version_mst": version["mst"],        # ??踰꾩쟾??MST
            "law_category": law_info["category"],
            "article_number": 議곕Ц踰덊샇,
            "article_type": 議곕Ц?щ?,  # "蹂몃Ц" | "遺移? ??遺移숈? 寃쎄낵議곗튂, 蹂꾨룄 泥?겕濡?遺꾨━??            "article_title": 議곕Ц?쒕ぉ,
            "effective_date": ?쒗뻾?쇱옄,
            "expiration_date": version["expiration_date"],  # 鍮?臾몄옄??= ?꾪뻾
            "promulgation_date": version["promulgation_date"],
            "content": ?댁슜,
            "clauses": ??list,
            "full_text": "\n".join(full_text_parts),
            "manual_review_required": manual_review_required,
            "metadata": {
                "law_name": law_name,
                "article": 議곕Ц踰덊샇,
                "article_number": 議곕Ц踰덊샇,
                "article_title": 議곕Ц?쒕ぉ,
                "effective_date": ?쒗뻾?쇱옄,
                "expiration_date": version["expiration_date"],
                "category": law_info["category"],
                "version_mst": version["mst"],
                "source": "law.go.kr",
            },
        }
        if manual_review_required:
            print(f"  ??[manual_review_required] {law_name} {議곕Ц踰덊샇} ??蹂꾪몴/?대?吏 ?섎룞 寃???꾩슂")
        chunks.append(chunk)

    # 遺移?ID 紐⑸줉 ?섏쭛 ??蹂몄튃 泥?겕??linked_buchik_ids 二쇱엯
    # 媛숈? 踰꾩쟾(MST) ??遺移숈? 蹂몄튃 ?꾩껜???곸슜?????덉쑝誘濡??꾨? ?곌껐
    buchik_ids = [c["id"] for c in chunks if c.get("article_type") == "遺移?]
    if buchik_ids:
        for c in chunks:
            if c.get("article_type") != "遺移?:
                c["linked_buchik_ids"] = buchik_ids
    # 遺移?泥?겕?먮뒗 鍮?由ъ뒪??(遺移숇겮由??쒗솚李몄“ 諛⑹?)
    for c in chunks:
        if "linked_buchik_ids" not in c:
            c["linked_buchik_ids"] = []

    return chunks


# ?? 硫붿씤 ?섏쭛 ?????????????????????????????????????????????????????????????????

def collect_all():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks = []

    for law in TARGET_LAWS:
        print(f"\n[{law['name']}] 媛쒖젙 ?대젰 議고쉶 以?..")

        # 踰꾩쟾 紐⑸줉 議고쉶
        versions = fetch_law_version_list(law["name"])

        if not versions:
            # ?대젰 議고쉶 ?ㅽ뙣 ???꾪뻾 踰꾩쟾 ?⑤룆 ?섏쭛
            # effective_date=0, expiration_date=99991231 ??Pinecone ?좎쭨 ?꾪꽣?먯꽌 ??긽 ?듦낵
            print(f"  ???대젰 ?놁쓬, ?꾪뻾 踰꾩쟾留??섏쭛 (MST={law['mst']})")
            versions = [{
                "mst": law["mst"],
                "effective_date": "0",
                "promulgation_date": "",
                "expiration_date": "99991231",
            }]
        else:
            # ?꾪뻾 MST媛 紐⑸줉???놁쑝硫?異붽?
            existing_msts = {v["mst"] for v in versions}
            if law["mst"] not in existing_msts:
                versions.append({
                    "mst": law["mst"],
                    "effective_date": "",
                    "promulgation_date": "",
                    "expiration_date": "",
                })
            print(f"  ??{len(versions)}媛?踰꾩쟾 諛쒓껄")

        law_chunks = []
        for v in versions:
            raw_path = RAW_DIR / f"{law['name'].replace(' ', '_')}_{v['mst']}.xml"

            if raw_path.exists():
                xml_text = raw_path.read_text(encoding="utf-8")
                print(f"  ??罹먯떆 ?ъ슜: {v['mst']} (?쒗뻾?? {v['effective_date'] or '遺덈챸'})")
            else:
                try:
                    xml_text = fetch_law_xml(v["mst"])
                    raw_path.write_text(xml_text, encoding="utf-8")
                    print(f"  ??XML ??? {v['mst']} (?쒗뻾?? {v['effective_date'] or '遺덈챸'}, {len(xml_text):,} bytes)")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"  ??{v['mst']} ?섏쭛 ?ㅽ뙣: {e}")
                    continue

            chunks = parse_xml_to_chunks(xml_text, law, v)
            print(f"     泥?겕: {len(chunks)}媛?| 留뚮즺?? {v['expiration_date'] or '?꾪뻾'}")
            law_chunks.extend(chunks)

        # 踰뺣졊蹂??듯빀 JSON
        processed_path = PROCESSED_DIR / f"{law['name'].replace(' ', '_')}_{law['mst']}.json"
        processed_path.write_text(
            json.dumps(law_chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        all_chunks.extend(law_chunks)

    # ?꾩껜 ?듯빀 JSON
    all_path = PROCESSED_DIR / "all_chunks.json"
    all_path.write_text(

codex
리스크 평가는 외부 감으로 말하면 안 됩니다. 현재 수집된 법령 코퍼스에서 실제로 부칙 문구 패턴이 얼마나 나오는지, `양도/취득` 기준 문구가 얼마나 자주 갈리는지 정량을 뽑겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n -c \"양도하는 분부터 적용|양도분부터 적용|양도하는 것부터 적용|양도하는 경우부터 적용\" data\\processed" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n -c \"취득하는 분부터 적용|취득분부터 적용|취득하는 것부터 적용|취득하는 경우부터 적용\" data\\processed" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n -c \"이 법 시행 이후 .*적용|이 영 시행 이후 .*적용|시행 이후 .*부터 적용\" data\\processed" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"양도하는 분부터 적용|취득하는 분부터 적용|양도분부터 적용|취득분부터 적용\" data\\processed" in C:\Users\user\cording2025\tax-rag
2026-05-21T06:14:18.952674Z ERROR codex_core::tools::router: error=Exit code: 1
Wall time: 3.5 seconds
Output:

2026-05-21T06:14:18.952674Z ERROR codex_core::tools::router: error=Exit code: 1
Wall time: 3.5 seconds
Output:

 exited 1 in 3514ms:
 exited 1 in 3497ms:
2026-05-21T06:14:19.044422Z ERROR codex_core::tools::router: error=Exit code: 1
Wall time: 3.5 seconds
Output:

 exited 1 in 3450ms:
2026-05-21T06:14:19.050685Z ERROR codex_core::tools::router: error=Exit code: 1
Wall time: 3.5 seconds
Output:

 exited 1 in 3456ms:
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-ChildItem data\\processed" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content data\\processed\\all_chunks.json | Select-Object -First 40" in C:\Users\user\cording2025\tax-rag
 succeeded in 3108ms:
[
  {
    "id": "285523_0001000",
    "law_name": "?뚮뱷?몃쾿",
    "law_mst": "285523",
    "version_mst": "285523",
    "law_category": "踰뺣쪧",
    "article_number": "1",
    "article_type": "?꾨Ц",
    "article_title": "",
    "effective_date": "20260421",
    "expiration_date": "99991231",
    "promulgation_date": "",
    "content": "????珥앹튃 <媛쒖젙 2009.12.31>",
    "clauses": [],
    "full_text": "????珥앹튃 <媛쒖젙 2009.12.31>",
    "metadata": {
      "law_name": "?뚮뱷?몃쾿",
      "article": "1",
      "article_number": "1",
      "article_title": "",
      "effective_date": "20260421",
      "expiration_date": "99991231",
      "category": "踰뺣쪧",
      "version_mst": "285523",
      "source": "law.go.kr"
    }
  },
  {
    "id": "285523_0001001",
    "law_name": "?뚮뱷?몃쾿",
    "law_mst": "285523",
    "version_mst": "285523",
    "law_category": "踰뺣쪧",
    "article_number": "1",
    "article_type": "議곕Ц",
    "article_title": "紐⑹쟻",
    "effective_date": "20260421",
    "expiration_date": "99991231",
    "promulgation_date": "",

 succeeded in 3130ms:


    디렉터리: C:\Users\user\cording2025\tax-rag\data\processed


Mode                 LastWriteTime         Length Name                                                                 
----                 -------------         ------ ----                                                                 
-a----        2026-05-17   오후 8:39       11882304 all_chunks.json                                                      
-a----        2026-05-17   오후 8:39        1384576 소득세법_285523.json                                                     
-a----        2026-05-17   오후 8:39         739250 소득세법_시행규칙_284987.json                                                
-a----        2026-05-17   오후 8:39        2416791 소득세법_시행령_285631.json                                                 
-a----        2026-05-17   오후 8:39        2860882 조세특례제한법_285525.json                                                  
-a----        2026-05-17   오후 8:39         736922 조세특례제한법_시행규칙_284611.json                                             
-a----        2026-05-17   오후 8:39        3743898 조세특례제한법_시행령_283625.json                                              



codex
로컬 코퍼스는 한글 출력 인코딩이 깨져서 그대로는 패턴 집계가 어렵습니다. 출력 인코딩을 UTF-8로 맞춘 뒤, 실제 부칙 문구 빈도를 다시 집계하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Content data\\processed\\all_chunks.json -Encoding UTF8 | Select-Object -First 20" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Select-String -Path data\\processed\\*.json -Pattern '양도하는 분부터 적용|양도분부터 적용|취득하는 분부터 적용|취득분부터 적용' -Encoding UTF8 | Select-Object -First 80" in C:\Users\user\cording2025\tax-rag
 succeeded in 3182ms:
[
  {
    "id": "285523_0001000",
    "law_name": "소득세법",
    "law_mst": "285523",
    "version_mst": "285523",
    "law_category": "법률",
    "article_number": "1",
    "article_type": "전문",
    "article_title": "",
    "effective_date": "20260421",
    "expiration_date": "99991231",
    "promulgation_date": "",
    "content": "제1장 총칙 <개정 2009.12.31>",
    "clauses": [],
    "full_text": "제1장 총칙 <개정 2009.12.31>",
    "metadata": {
      "law_name": "소득세법",
      "article": "1",
      "article_number": "1",

 succeeded in 3924ms:
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $data = Get-Content data'"\\processed\\all_chunks.json -Encoding UTF8 -Raw | ConvertFrom-Json; "'$buchik = $data | Where-Object { $_.article_type -eq '"'부칙' }; 'buchik_count=' + "'$buchik.Count; $patterns = @(
  @{name='"'transfer'; regex='양도["'^'"\\n]{0,40}적용|양도["'^'"\\n]{0,40}부터'},
  @{name='acquisition'; regex='취득["'^'"\\n]{0,40}적용|취득["'^'"\\n]{0,40}부터'},
  @{name='contract'; regex='계약["'^'"\\n]{0,40}적용|계약["'^'"\\n]{0,40}부터'},
  @{name='enforcement'; regex='시행 이후["'^'"\\n]{0,40}적용|시행 이후["'^'"\\n]{0,40}부터'}
); foreach ("'$p in $patterns) { $matches = $buchik | Where-Object { $_.full_text -match $p.regex }; "$($p.name)=$($matches.Count)" }' in C:\Users\user\cording2025\tax-rag
 succeeded in 3589ms:
buchik_count=0
transfer=0
acquisition=0
contract=0
enforcement=0

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $data = Get-Content data'"\\processed\\all_chunks.json -Encoding UTF8 -Raw | ConvertFrom-Json; "'$data | Group-Object article_type | Sort-Object Count -Descending | ForEach-Object { "type=$($_.Name) count=$($_.Count)" }' in C:\Users\user\cording2025\tax-rag
 succeeded in 3957ms:
type=조문 count=2063
type=전문 count=175

codex
중요한 추가 사실이 나왔습니다. 현재 수집 산출물에는 `article_type='부칙'` 청크가 아예 없어서, 설계상 있는 `linked_buchik_ids` 자동보강도 실데이터에서는 거의 작동하지 않을 가능성이 큽니다. 이건 applicability 공백 이전에 ingestion 커버리지 공백입니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $data = Get-Content data'"\\processed\\all_chunks.json -Encoding UTF8 -Raw | ConvertFrom-Json; "'$nonEmpty = $data | Where-Object { $_.linked_buchik_ids -and $_.linked_buchik_ids.Count -gt 0 }; '"'non_empty_linked_buchik=' + "'$nonEmpty.Count; $data | Select-Object -First 3 | ConvertTo-Json -Depth 4' in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Select-String -Path data\\raw\\*.xml -Pattern '부칙|附則' -Encoding UTF8 | Select-Object -First 40" in C:\Users\user\cording2025\tax-rag
 succeeded in 3623ms:

data\raw\소득세법_285523.xml:8317:						<목내용><![CDATA[나.  제1항제1호나목 및 제114조제7항에 따라 환산취득가액에 의하여 취득 당시의 실지거래가액을 계산하는 경우로서 법률 제
4803호 소득세법개정법률 부칙 제8조에 따라 취득한 것으로 보는 날(이하 이 목에서 "의제취득일"이라 한다) 전에 취득한 자산(상속 또는 증여받은 자산을 포함한다)의 취득가액을 취득 당시의 실지거래가액과 그 가액
에 취득일부터 의제취득일의 전날까지의 보유기간의 생산자물가상승률을 곱하여 계산한 금액을 합산한 가액에 의하는 경우에는 그 합산한 가액]]>						</목내용>
data\raw\소득세법_285523.xml:15235:<부칙>
data\raw\소득세법_285523.xml:15236:<부칙단위 부칙키="1994122204803">
data\raw\소득세법_285523.xml:15237:<부칙공포일자>19941222</부칙공포일자>
data\raw\소득세법_285523.xml:15238:<부칙공포번호>04803</부칙공포번호>
data\raw\소득세법_285523.xml:15239:<부칙내용><![CDATA[부칙 <제4803호,1994.12.22>]]>
data\raw\소득세법_285523.xml:15311:<![CDATA[제10조 (원천징수 세율에 관한 특례) 1991년 1월 1일전에 발생한 이자소득 및 배당소득으로서 1991년 1월 1일 현재의 소득세와 199
0년 12월 31일이전의 방위세법 및 교육세법에 의한 방위세 및 교육세를 납부하지 아니한 것에 대한 원천징수세율은 법률 제4281호(所得稅法 中 改正法律) 부칙 제16조의 규정에서 정하는 바에 의한다.]]>
data\raw\소득세법_285523.xml:15426:</부칙내용>
data\raw\소득세법_285523.xml:15427:</부칙단위>
data\raw\소득세법_285523.xml:15428:<부칙단위 부칙키="1994123104856">
data\raw\소득세법_285523.xml:15429:<부칙공포일자>19941231</부칙공포일자>
data\raw\소득세법_285523.xml:15430:<부칙공포번호>04856</부칙공포번호>
data\raw\소득세법_285523.xml:15431:<부칙내용><![CDATA[부칙(독립유공자예우에관한법률) <제4856호,1994.12.31>]]>
data\raw\소득세법_285523.xml:15456:</부칙내용>
data\raw\소득세법_285523.xml:15457:</부칙단위>
data\raw\소득세법_285523.xml:15458:<부칙단위 부칙키="1995122905031">
data\raw\소득세법_285523.xml:15459:<부칙공포일자>19951229</부칙공포일자>
data\raw\소득세법_285523.xml:15460:<부칙공포번호>05031</부칙공포번호>
data\raw\소득세법_285523.xml:15461:<부칙내용><![CDATA[부칙 <제5031호,1995.12.29>]]>
data\raw\소득세법_285523.xml:15464:<![CDATA[제1조 (시행일) 이 법은 1996년 1월 1일부터 시행한다. 다만, 제17조ㆍ제56조제1항ㆍ제165조 및 법률 제4803호 부칙 제8조의 개
정규정은 1997년 1월 1일부터 시행하고, 제12조제4호의2ㆍ제20조의2제1항제1호의 개정규정은 2004년 1월 1일부터 시행한다. <개정 1997.12.13, 2000.12.29>]]>
data\raw\소득세법_285523.xml:15494:<![CDATA[  ③법률 제4803호 부칙 제8조의 개정규정은 1997년 1월 1일이후 최초로 양도하는 분부터 적용한다.]]>
data\raw\소득세법_285523.xml:15516:</부칙내용>
data\raw\소득세법_285523.xml:15517:</부칙단위>
data\raw\소득세법_285523.xml:15518:<부칙단위 부칙키="1995122905108">
data\raw\소득세법_285523.xml:15519:<부칙공포일자>19951229</부칙공포일자>
data\raw\소득세법_285523.xml:15520:<부칙공포번호>05108</부칙공포번호>
data\raw\소득세법_285523.xml:15521:<부칙내용><![CDATA[부칙(지가공시및토지등의평가에관한법률) <제5108호,1995.12.29>]]>
data\raw\소득세법_285523.xml:15543:</부칙내용>
data\raw\소득세법_285523.xml:15544:</부칙단위>
data\raw\소득세법_285523.xml:15545:<부칙단위 부칙키="1996081405155">
data\raw\소득세법_285523.xml:15546:<부칙공포일자>19960814</부칙공포일자>
data\raw\소득세법_285523.xml:15547:<부칙공포번호>05155</부칙공포번호>
data\raw\소득세법_285523.xml:15548:<부칙내용><![CDATA[부칙 <제5155호,1996.8.14>]]>
data\raw\소득세법_285523.xml:15564:</부칙내용>
data\raw\소득세법_285523.xml:15565:</부칙단위>
data\raw\소득세법_285523.xml:15566:<부칙단위 부칙키="1996123005191">
data\raw\소득세법_285523.xml:15567:<부칙공포일자>19961230</부칙공포일자>
data\raw\소득세법_285523.xml:15568:<부칙공포번호>05191</부칙공포번호>
data\raw\소득세법_285523.xml:15569:<부칙내용><![CDATA[부칙 <제5191호,1996.12.30>]]>
data\raw\소득세법_285523.xml:15597:</부칙내용>



 succeeded in 4077ms:
non_empty_linked_buchik=0
[
    {
        "id":  "285523_0001000",
        "law_name":  "소득세법",
        "law_mst":  "285523",
        "version_mst":  "285523",
        "law_category":  "법률",
        "article_number":  "1",
        "article_type":  "전문",
        "article_title":  "",
        "effective_date":  "20260421",
        "expiration_date":  "99991231",
        "promulgation_date":  "",
        "content":  "제1장 총칙 \u003c개정 2009.12.31\u003e",
        "clauses":  [

                    ],
        "full_text":  "제1장 총칙 \u003c개정 2009.12.31\u003e",
        "metadata":  {
                         "law_name":  "소득세법",
                         "article":  "1",
                         "article_number":  "1",
                         "article_title":  "",
                         "effective_date":  "20260421",
                         "expiration_date":  "99991231",
                         "category":  "법률",
                         "version_mst":  "285523",
                         "source":  "law.go.kr"
                     }
    },
    {
        "id":  "285523_0001001",
        "law_name":  "소득세법",
        "law_mst":  "285523",
        "version_mst":  "285523",
        "law_category":  "법률",
        "article_number":  "1",
        "article_type":  "조문",
        "article_title":  "목적",
        "effective_date":  "20260421",
        "expiration_date":  "99991231",
        "promulgation_date":  "",
        "content":  "제1조(목적) 이 법은 개인의 소득에 대하여 소득의 성격과 납세자의 부담능력 등에 따라 적정하게 과세함으로써 조세부담의 형평을 도모하고 재정수입의 원활한 조달에 이바지함을 목적으로 한다.",
        "clauses":  [

                    ],
        "full_text":  "제1조(목적) 이 법은 개인의 소득에 대하여 소득의 성격과 납세자의 부담능력 등에 따라 적정하게 과세함으로써 조세부담의 형평을 도모하고 재정수입의 원활한 조달에 이바지함을 목적으로 한다.",
        "metadata":  {
                         "law_name":  "소득세법",
                         "article":  "1",
                         "article_number":  "1",
                         "article_title":  "목적",
                         "effective_date":  "20260421",
                         "expiration_date":  "99991231",
                         "category":  "법률",
                         "version_mst":  "285523",
                         "source":  "law.go.kr"
                     }
    },
    {
        "id":  "285523_0001021",
        "law_name":  "소득세법",
        "law_mst":  "285523",
        "version_mst":  "285523",
        "law_category":  "법률",
        "article_number":  "1",
        "article_type":  "조문",
        "article_title":  "정의",
        "effective_date":  "20260421",
        "expiration_date":  "99991231",
        "promulgation_date":  "",
        "content":  "제1조의2(정의)",
        "clauses":  [
                        {
                            "항번호":  "①",
                            "항내용":  "① 이 법에서 사용하는 용어의 뜻은 다음과 같다. \u003c개정 2010.12.27, 2014.12.23, 2018.12.31\u003e",
                            "호":  [
                                      "@{호번호=1.; 호내용=1.  \"거주자\"란 국내에 주소를 두거나 183일 이상의 거소(居所)를 둔 개인을 말한다.}",
                                      "@{호번호=2.; 호내용=2.  \"비거주자\"란 거주자가 아닌 개인을 말한다.}",
                                      "@{호번호=3.; 호내용=3.  \"내국법인\"이란 「법인세법」 제2조제1호에 따른 내국법인을 말한다.}",
                                      "@{호번호=4.; 호내용=4.  \"외국법인\"이란 「법인세법」 제2조제3호에 따른 외국법인을 말한다.}",
                                      "@{호번호=5.; 호내용=5.  \"사업자\"란 사업소득이 있는 거주자를 말한다.}"
                                  ]
                        },
                        {
                            "항번호":  "②",
                            "항내용":  "② 제1항에 따른 주소ㆍ거소와 거주자ㆍ비거주자의 구분은 대통령령으로 정한다.",
                            "호":  [

                                  ]
                        }
                    ],
        "full_text":  "제1조의2(정의)\n  ① 이 법에서 사용하는 용어의 뜻은 다음과 같다. \u003c개정 2010.12.27, 2014.12.23, 2018.12.31\u003e\n    1.  \"거주자\"란 국내에 주소를 두거나 183일 이상의 거소(居所)를 둔 개인을 말한다.\n    2.  \"비거주자\"란 거주자가 아닌 개인을 말한다.\n    3.  \"내국법인\"이란 「법인세법」 제2조제1호에 따른 내국법인을 말한다.\n    4.  \"외국법인\"이란 「법인세법」 제2조제3호에 따른 외국법인을 말한다.\n    5.  \"사업자\"란 사업소득이 있는 거주자를 말한다.\n  ② 제1항에 따른 주소ㆍ거소와 거주자ㆍ비거주자의 구분은 대통령령으로 정한다.",
        "metadata":  {
                         "law_name":  "소득세법",
                         "article":  "1",
                         "article_number":  "1",
                         "article_title":  "정의",
                         "effective_date":  "20260421",
                         "expiration_date":  "99991231",
                         "category":  "법률",
                         "version_mst":  "285523",
                         "source":  "law.go.kr"
                     }
    }
]

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $patterns = @(
  @{name='"'양도_분부터적용'; regex='양도하는 분부터 적용|양도하는 것부터 적용|최초로 양도하는 분부터 적용|이후 최초로 양도하는 분부터 적용'},
  @{name='취득_분부터적용'; regex='취득하는 분부터 적용|취득하는 것부터 적용|최초로 취득하는 분부터 적용|이후 최초로 취득하는 분부터 적용'},
  @{name='양도분'; regex='양도분부터 적용|양도분에부터 적용'},
  @{name='취득분'; regex='취득분부터 적용|취득분에부터 적용'},
  @{name='계약분'; regex='계약하는 분부터 적용|계약분부터 적용|계약을 체결하는 분부터 적용'},
  @{name='시행후_양도'; regex='시행 이후["'^'"\\r\\n]{0,50}양도["'^'"\\r\\n]{0,30}적용'},
  @{name='시행후_취득'; regex='시행 이후["'^'"\\r\\n]{0,50}취득["'^'"\\r\\n]{0,30}적용'}
); foreach ("'$p in $patterns) { $m = Select-String -Path data'"\\raw\\*.xml -Pattern "'$p.regex -Encoding UTF8; "$($p.name)=$($m.Count)" }' in C:\Users\user\cording2025\tax-rag
 succeeded in 9655ms:
양도_분부터적용=314
취득_분부터적용=62
양도분=3
취득분=0
계약분=16
시행후_양도=99
시행후_취득=32

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $files = Get-ChildItem data'"\\raw\\*.xml; foreach ("'$f in $files) { $t = (Select-String -Path $f.FullName -Pattern '"'양도하는 분부터 적용|양도하는 것부터 적용|최초로 양도하는 분부터 적용|이후 최초로 양도하는 분부터 적용' -Encoding UTF8).Count; "'$a = (Select-String -Path $f.FullName -Pattern '"'취득하는 분부터 적용|취득하는 것부터 적용|최초로 취득하는 분부터 적용|이후 최초로 취득하는 분부터 적용' -Encoding UTF8).Count; "'$c = (Select-String -Path $f.FullName -Pattern '"'계약을 체결하는 분부터 적용|계약하는 분부터 적용|계약분부터 적용' -Encoding UTF8).Count; if ("'$t -or $a -or $c) { "$($f.Name)`t양도=$t`t취득=$a`t계약=$c" } }' in C:\Users\user\cording2025\tax-rag
 succeeded in 6669ms:
소득세법_285523.xml	양도=53	취득=0	계약=3
소득세법_시행규칙_284987.xml	양도=33	취득=0	계약=1
소득세법_시행령_285631.xml	양도=81	취득=9	계약=9
조세특례제한법_285525.xml	양도=86	취득=41	계약=2
조세특례제한법_시행규칙_284611.xml	양도=12	취득=1	계약=1
조세특례제한법_시행령_283625.xml	양도=49	취득=11	계약=0

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Select-String -Path data\\raw\\조세특례제한법_285525.xml -Pattern '취득하는 분부터 적용|이후 최초로 취득하는 분부터 적용' -Encoding UTF8 | Select-Object -First 8 | ForEach-Object { "'$_.Line.Trim() }' in C:\Users\user\cording2025\tax-rag
 succeeded in 4548ms:
<![CDATA[제8조 (중소기업창업투자회사등의 주식양도차익 비과세등에 관한 적용례) ①제13조ㆍ제14조제1항제2호 내지 제4호 및 제14조제2항의 개정규정은 이 법 시행후 최초로 주식 또는 출자지분을 취득하는 분부터 적용한다.]]>
<![CDATA[제5조 (투자세액공제에 관한 적용례) 제27조 및 제62조의 개정규정은 이 법 시행후 최초로 투자하거나 취득하는 분부터 적용한다.]]>
<![CDATA[제10조 (지방세에 관한 적용례) 제119조 내지 제121조의 개정규정은 이 법 시행후 최초로 취득하는 분부터 적용한다.]]>
<![CDATA[제3조 (기업구조조정조합에 대한 양도소득세 비과세등에 관한 적용례) 제14조 및 제16조의 개정규정은 이 법 시행일이 속하는 과세기간에 기업구조조정조합에 출자하거나 기업구조조정조합이 주식 또는 출자지분을 취득하는 분부터 적용한다.]]>
<![CDATA[  ⑤제120조제5항제8호의 개정규정은 이 법 시행후 최초로 주식을 취득하는 분부터 적용한다.]]>
<![CDATA[제11조 (지방세에 관한 적용례) 제119조 및 제120조의 개정규정은 이 법 시행후 최초로 등기하거나 취득하는 분부터 적용한다.]]>
<![CDATA[제11조 (취득세의 면제에 관한 적용례) 제120조제5항제8호 및 제11호의 개정규정은 이 법 시행후 최초로 주식 또는 지분을 취득하는 분부터 적용한다.]]>
<![CDATA[제5조 (기술이전소득에 대한 세액감면 등에 관한 적용례) 제12조의 개정규정은 이 법 시행후 최초로 양도ㆍ대여ㆍ제공 또는 취득하는 분부터 적용한다.]]>

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Select-String -Path data\\raw\\소득세법_시행령_285631.xml -Pattern '양도하는 분부터 적용|이후 최초로 양도하는 분부터 적용' -Encoding UTF8 | Select-Object -First 8 | ForEach-Object { "'$_.Line.Trim() }' in C:\Users\user\cording2025\tax-rag
 succeeded in 4310ms:
<![CDATA[  ②이 영중 양도소득에 관한 규정은 제1항의 규정에 불구하고 이 영 시행후 최초로 양도하는 분부터 적용한다.]]>
<![CDATA[제8조 (양도소득에 관한 적용례) ①이 영중 양도소득에 관한 개정규정은 이 영 시행후 최초로 양도하는 분부터 적용한다.]]>
<![CDATA[  ③제162조제6항제1호 및 동조제7항제1호의 개정규정은 1997년 1월 1일이후 최초로 양도하는 분부터 적용한다.]]>
<![CDATA[  ④제163조제6항의 개정규정은 이 영 시행후 최초로 양도하는 분부터 적용한다. 다만, 1995년 12월 31일이전에 취득한 자산에 대하여는 종전의 규정을 적용할 수 있다. <개정 1996.12.31>]]>
<![CDATA[③(장외등록법인의 주식양도분에 대한 적용례) 제157조제5항은 이 영 시행후 최초로 양도하는 분부터 적용한다. 다만, 동조동항제2호 및 제3호의 개정규정은 1996년 7월 1일이후 최초로 양도하는 분부터 적용한다.]]>
<![CDATA[제2조 (일반적 적용례) 이 영은 이 영 시행후 최초로 개시하는 과세기간에 발생하는 소득분부터 적용한다. 다만, 제12조제12호ㆍ제77조ㆍ제90조제3호의2 및 제97조제1항의 개정규정은 이 영 시행일이 속하는 과세기간분부터 적용하고, 제152조ㆍ제153조제6항ㆍ제155조ㆍ제156조ㆍ제158조ㆍ제163조ㆍ제164조ㆍ제165조ㆍ제166조ㆍ제175조의2ㆍ제224조 및 대통령령 제14860호 부칙 제8조제4항의 개정규정은 이 영 시행후 최초로 양도하는 분부터 적용한다.]]>
<![CDATA[②(적용례) 제179조제8항의 개정규정은 이 영 시행후 최초로 양도하는 분부터 적용한다.]]>
<![CDATA[제3조 (양도소득세에 관한 적용례) 이 영중 양도소득세에 관한 개정규정은 이 영 시행후 최초로 양도하는 분부터 적용한다.]]>

codex
결론은 거의 정리됐습니다. 마지막으로 파일/라인 근거만 정밀하게 잡아 두겠습니다. debate 트리거, `ApplicabilitySpec=NONE`, 부칙 미파싱 지점을 라인 기준으로 확인한 뒤 답을 정리하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "rg -n \"ApplicabilitySpec\\(rule_type=ApplicabilityRuleType.NONE\\)|retrieve_with_buchik|enable_debate|should_debate|build_few_shot_block|_score_similarity|linked_buchik_ids|article_type == \\\"부칙\\\"|article_type\\) == \\\"부칙\\\"|부칙단위\" src data\\processed data\\raw" in C:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "@'
from pathlib import Path
files = [
    'src/retrieval/retriever_impl.py',
    'src/domain/pipeline.py',
    'src/eval/golden_injector.py',
    'src/ingestion/collect.py'
]
for f in files:
    print(f'## {f}')
    for i, line in enumerate(Path(f).read_text(encoding='utf-8').splitlines(), 1):
        if 'ApplicabilitySpec(rule_type=ApplicabilityRuleType.NONE)' in line or 'retrieve_with_buchik' in line or 'enable_debate' in line or 'should_debate' in line or 'build_few_shot_block' in line or '_score_similarity' in line or 'linked_buchik_ids' in line or 'article_type' in line and '부칙' in line:
            print(f'{i}: {line}')
'@ | python -" in C:\Users\user\cording2025\tax-rag
2026-05-21T06:17:37.880806Z ERROR codex_core::tools::router: error=Exit code: 1
Wall time: 3.7 seconds
Output:
rg: ==: 지정된 파일을 찾을 수 없습니다. (os error 2)
rg: \부칙\|부칙단위 src data\processed data\raw: 지정된 경로를 찾을 수 없습니다. (os error 3)

 exited 1 in 3737ms:
rg: ==: 지정된 파일을 찾을 수 없습니다. (os error 2)
rg: \부칙\|부칙단위 src data\processed data\raw: 지정된 경로를 찾을 수 없습니다. (os error 3)

 succeeded in 3841ms:
## src/retrieval/retriever_impl.py
5: 현재 미수집 필드(linked_buchik_ids, entity_scopes 등)는 합리적 기본값 사용.
114:     # linked_buchik_ids: Pinecone는 list 메타데이터를 그대로 반환
115:     raw_buchik = meta.get("linked_buchik_ids", [])
133:         applicability=ApplicabilitySpec(rule_type=ApplicabilityRuleType.NONE),
135:         linked_buchik_ids=buchik_ids,
## src/domain/pipeline.py
82:     enable_debate: bool = False,
143:     chunks = retriever.retrieve_with_buchik(query)
175:     if enable_debate and fact_json:
177:             from src.eval.debate import run_red_blue_debate, should_debate
178:             if should_debate(result):
## src/eval/golden_injector.py
34: def _score_similarity(fact_json: dict, golden_fact: dict) -> int:
58:         (g, _score_similarity(fact_json, g.get("fact_json", {})))
66: def build_few_shot_block(fact_json: dict) -> str:
## src/ingestion/collect.py
303:     # 부칙 ID 목록 수집 후 본칙 청크에 linked_buchik_ids 주입
309:                 c["linked_buchik_ids"] = buchik_ids
312:         if "linked_buchik_ids" not in c:
313:             c["linked_buchik_ids"] = []

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "@'
from pathlib import Path
f='src/eval/debate.py'
print(f'## {f}')
for i, line in enumerate(Path(f).read_text(encoding='utf-8').splitlines(), 1):
    if 'def should_debate' in line or 'confidence <' in line or 'danger_flags' in line or 'NEEDS_VERIFICATION' in line:
        print(f'{i}: {line}')
'@ | python -" in C:\Users\user\cording2025\tax-rag
 succeeded in 4186ms:
## src/eval/debate.py
10:   - confidence < 0.80
11:   - danger_flags >= 2°ł
526: def should_debate(pipeline_result: PipelineResult) -> bool:
538:         ans.confidence < 0.80
539:         or len(fc.danger_flags) >= 2

exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Select-String -Path data\\raw\\소득세법_285523.xml -Pattern '최초로 양도하는 분부터 적용' -Encoding UTF8 | Select-Object -First 3 | ForEach-Object { \""'$($_.LineNumber): $($_.Line.Trim())" }; Select-String -Path data'"\\raw\\조세특례제한법_285525.xml -Pattern '최초로 취득하는 분부터 적용' -Encoding UTF8 | Select-Object -First 3 | ForEach-Object { \""'$($_.LineNumber): $($_.Line.Trim())" }' in C:\Users\user\cording2025\tax-rag
 succeeded in 4211ms:
15488: <![CDATA[제8조 (양도소득에 관한 적용례) ①이 법중 양도소득에 관한 규정은 각 해당 조항 시행후 최초로 양도하는 분부터 적용한다. 다만, 제165조의 개정규정은 1997년 1월 1일이후 최초로 부동산매매계약을 체결하는 분(등기부에 기재된 등기원인일을 말한다)부터 적용한다.<개정 1996.12.30>]]>
15494: <![CDATA[  ③법률 제4803호 부칙 제8조의 개정규정은 1997년 1월 1일이후 최초로 양도하는 분부터 적용한다.]]>
15506: <![CDATA[제12조 (부동산양도신고등에 관한 적용례) 제165조의 개정규정은 1997년 1월 1일이후 최초로 양도하는 분부터 적용한다.]]>
26839: <![CDATA[제10조 (지방세에 관한 적용례) 제119조 내지 제121조의 개정규정은 이 법 시행후 최초로 취득하는 분부터 적용한다.]]>
27538: <![CDATA[  ②제119조제6항 및 제120조제4항의 개정규정은 이 법 시행후 최초로 취득하는 분부터 적용한다.]]>
27787: <![CDATA[  ②제121조의9제3항의 개정규정중 취득세 및 등록세에 관한 개정규정은 이 법 시행후 최초로 취득하는 분부터 적용하고, 재산세에 관한 개정규정은 이 법 시행후 최초로 납세의무가 성립하는 분부터 적용한다. <개정 2005.1.5>]]>

web search: 
web search: 
web search: 
web search: https://www.law.go.kr/LSW/precInfoP.do?precSeq=65115
codex
핵심 결론부터 말하면, 이 문제는 RLVR로 “나중에 잡는” 종류가 아니라 retrieval 전에 구조적으로 막아야 하는 종류입니다. 지금 구현은 [retriever_impl.py](/C:/Users/user/cording2025/tax-rag/src/retrieval/retriever_impl.py:133)에서 `ApplicabilitySpec`를 항상 `NONE`으로 두고 있고, debate도 [debate.py](/C:/Users/user/cording2025/tax-rag/src/eval/debate.py:526) 기준으로 `confidence < 0.80` 또는 `danger_flags >= 2`일 때만 돌아서, “그럴듯하지만 틀린” 부칙 적용 오류는 그대로 통과할 수 있습니다. 더 큰 문제는 현재 산출물엔 부칙 청크가 사실상 없습니다. 원천 XML엔 `<부칙>`가 있는데 [소득세법_285523.xml](/C:/Users/user/cording2025/tax-rag/data/raw/소득세법_285523.xml:15235), processed 쪽은 `article_type=부칙`가 0건이고 `linked_buchik_ids`도 전부 비어 있어 [collect.py](/C:/Users/user/cording2025/tax-rag/src/ingestion/collect.py:303) 의도 자체가 실데이터에선 작동하지 않습니다.

**A. RLVR + Red/Blue가 이 오류를 reliably 잡나**
아니오, 보조수단으로는 쓸 수 있어도 1차 방어선으로는 부족합니다.
- binary reward는 “정답/오답”은 줄 수 있어도 왜 틀렸는지, 특히 `양도분` vs `취득분` 같은 적용 anchor를 일반화해서 학습시키기 어렵습니다.
- debate는 샘플링된 케이스만 봅니다. 높은 confidence로 나온 silent error는 토론 자체가 안 열릴 수 있습니다.
- golden retrieval도 [golden_injector.py](/C:/Users/user/cording2025/tax-rag/src/eval/golden_injector.py:34)에서 `property_type`, `acquisition_reason`, 주택 수, special case key 정도만 봐서 “같은 쟁점인데 anchor가 다른 케이스”를 잘 못 끌어옵니다.
- 그래서 RLVR는 “missed pattern 수집기”로는 좋지만, applicability enforcement 대체재는 아닙니다.

**B. pure LLM-reads-text 방식의 실패 모드**
- anchor 혼동: `취득분`인데 `양도일` 기준으로 읽음.
- 혼합 규정 누락: “시행 후 양도분, 다만 시행 전 취득분은 종전 규정” 같은 이중 조건을 한쪽만 반영.
- 예외/단서 역전: `다만`, `종전 규정 적용`, `최초로`를 놓침.
- version leakage: 본칙은 신법, 부칙은 구법 전환조치를 섞어 읽음.
- plausible hallucination: 답이 매우 자연스러워서 validator가 못 잡음. 현재 L5는 phantom citation 위주라 applicability 오판은 직접 검증하지 않습니다.
- non-determinism: 같은 케이스를 다시 물으면 적용 기준이 흔들릴 수 있습니다.

**C. hybrid가 복잡도 대비 가치 있나**
있습니다. 이 도메인에서는 거의 필수입니다. 다만 “전부 LLM 추출”이 아니라 “regex-first + offline LLM backfill”이 맞습니다.
- 1단계: ingestion에서 실제 `<부칙단위>`를 청크로 생성.
- 2단계: 고정 패턴을 정규식으로 구조화.
  - `이 법 시행 후 최초로 양도하는 분부터 적용` → anchor=`transfer_date`
  - `... 취득하는 분부터 적용` → anchor=`acquisition_date`
  - `... 계약을 체결하는 분부터 적용` → anchor=`contract_date`
- 3단계: 정규식이 못 푸는 부칙만 offline LLM extraction으로 `ApplicabilitySpec` 채움.
- 4단계: retriever Stage 1에서 high-confidence spec는 hard filter, low-confidence spec는 soft include + warning.
- 5단계: L5에서 “인용한 청크가 사실관계의 anchor date에 실제 적용되는지”를 다시 검증.

**D. 빈도와 리스크**
제가 현재 로컬 raw corpus(`data/raw/*.xml`)를 직접 스캔한 결과, 중복 포함 hit 기준으로:
- `양도...분부터 적용` 계열: 314회
- `취득...분부터 적용` 계열: 62회
- `계약...분부터 적용` 계열: 16회

이 수치는 unique rule count는 아니고 버전/반복문구 포함 hit count입니다. 그래도 의미는 분명합니다.
- `양도분`이 훨씬 많지만 `취득분`도 무시할 수준이 아닙니다.
- `취득분`은 특히 조특법/시행령에 몰려 있고, 감면/비과세/지방세 특례처럼 verdict를 뒤집는 조항에서 나옵니다.
- 그래서 발생 빈도는 `양도분`보다 낮아도, 한 번 틀리면 “종전 규정 vs 개정 규정”이 갈리면서 감면 존부 자체가 뒤집혀 치명적입니다.

샘플 근거:
- 로컬 raw XML: [소득세법_285523.xml](/C:/Users/user/cording2025/tax-rag/data/raw/소득세법_285523.xml:15488), [조세특례제한법_285525.xml](/C:/Users/user/cording2025/tax-rag/data/raw/조세특례제한법_285525.xml:26839)
- 공식 소스 예시: 국가법령정보센터 판례가 부칙의 “이후 최초로 양도하는 분부터 적용” 해석을 직접 다룹니다. https://www.law.go.kr/LSW/precInfoP.do?precSeq=65115
- 국가법령정보센터 연혁 페이지도 본문과 별도로 부칙을 분리 제공하고 있습니다. https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=188355

아키텍처 권고는 단순합니다.  
1. 먼저 ingestion을 고쳐 부칙을 실제 chunk로 만들고,  
2. `ApplicabilitySpec`를 채우는 extractor를 넣고,  
3. retriever에서 hard/soft applicability filtering을 적용하고,  
4. RLVR/debate는 그 위에서 extractor 누락 패턴을 수집하는 품질 루프로 쓰는 것이 맞습니다.

원하면 다음 턴에서 바로 `Phase 0: 부칙 파싱 복구 + ApplicabilitySpec 최소 스키마 + 테스트 설계`까지 코드 변경안으로 내리겠습니다.
tokens used
107,827

```

## Concise summary

Provider completed successfully. Review the raw output for details.

## Action items

- Review the response and extract decisions you want to apply.
- Capture follow-up implementation tasks if needed.
