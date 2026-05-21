# codex advisor artifact

- Provider: codex
- Exit code: 0
- Created at: 2026-05-21T10:38:30.077Z

## Original task

Korean tax RAG system: design a robust area-designation change-detection pipeline. Context: no public API exists for 조정대상지역/투기과열지구/투기지역. These are announced by MOLIT (국토교통부) or MoEF (기획재정부) without notice and directly affect capital gains tax verdicts (비과세↔중과). Current state: manual_table.json hardcoded, Windows Task Scheduler runs detect_law_changes.py daily at 23:00. Stack: Python, Pinecone, scripts/detect_law_changes.py. Question: what is the most reliable technical architecture for (1) detecting new designations/releases, (2) updating manual_table.json automatically or semi-automatically, (3) alerting the operator, (4) fallback if scraping breaks? Be specific about data sources (molit.go.kr, lawmaking.go.kr, 입법예고, RSS, news API), scraping stability risks, hash-based change detection, and integration pattern with detect_law_changes.py.

## Final prompt

Korean tax RAG system: design a robust area-designation change-detection pipeline. Context: no public API exists for 조정대상지역/투기과열지구/투기지역. These are announced by MOLIT (국토교통부) or MoEF (기획재정부) without notice and directly affect capital gains tax verdicts (비과세↔중과). Current state: manual_table.json hardcoded, Windows Task Scheduler runs detect_law_changes.py daily at 23:00. Stack: Python, Pinecone, scripts/detect_law_changes.py. Question: what is the most reliable technical architecture for (1) detecting new designations/releases, (2) updating manual_table.json automatically or semi-automatically, (3) alerting the operator, (4) fallback if scraping breaks? Be specific about data sources (molit.go.kr, lawmaking.go.kr, 입법예고, RSS, news API), scraping stability risks, hash-based change detection, and integration pattern with detect_law_changes.py.

## Raw output

```text
가장 신뢰도 높은 구조는 `manual_table.json`을 계속 1급 기준표로 두고, 그 앞단에 “다중 소스 감시 + 후보 추출 + 승인 반영” 파이프라인을 붙이는 방식입니다. 이 프로젝트 성격상 `full auto overwrite`보다 `high-confidence auto patch + operator approve`가 맞습니다. 조정대상지역/투기과열지구/투기지역은 법적 효력이 큰데, 공고 형식과 게시 위치가 자주 흔들리고, 실제로 MOLIT/MoEF는 단순 `requests` 호출을 끊는 경우도 있어 WAF/anti-bot 리스크가 있습니다.

**권장 아키텍처**
1. `P0 authoritative`
- 전자관보 `gwanbo.go.kr`: 최종 공고 효력 확인용.
- MOLIT 공고/행정규칙 상세 + 첨부 PDF/HWP/HWPX: 조정대상지역, 투기과열지구.
- MoEF 고시·공고·지침 상세 + 첨부 PDF/HWP: 투기지역.

2. `P1 early signal`
- MOLIT RSS: 보도자료/공지 신규 게시 감지.
- MOLIT 보도자료: 주거정책심의위원회 결과가 공고보다 먼저 뜨는 경우가 많음.
- Lawmaking API: `주택법`, `소득세법 시행령`, 관련 입법예고/행정예고를 감시해서 “곧 바뀔 수 있음” 신호로만 사용.

3. `P2 weak fallback`
- News API: 네이버 뉴스 API, GDELT, NewsAPI 중 하나.
- 키워드: `조정대상지역`, `투기과열지구`, `투기지역`, `지정 해제`, `주거정책심의위원회`, `부동산 지정지역 해제 공고문`.
- 뉴스는 절대 truth source로 쓰지 말고 “공식 사이트 재확인 필요” 경보만 올립니다.

**구현 패턴**
- 기존 `scripts/detect_law_changes.py`는 유지하고, 여기에 `detect_area_designations()`를 오케스트레이션으로 붙입니다.
- 실제 소스별 구현은 분리합니다.
- 예시:
  - `src/ingestion/area_sources/molit_rss.py`
  - `src/ingestion/area_sources/molit_board.py`
  - `src/ingestion/area_sources/moef_board.py`
  - `src/ingestion/area_sources/lawmaking_api.py`
  - `src/ingestion/area_sources/news_signal.py`
  - `src/ingestion/area_designation_pipeline.py`

`detect_law_changes.py` 흐름:
1. 기존 법령 버전 감지 실행
2. `detect_area_designations()` 실행
3. 결과를 `data/admin_notices/`와 `data/area_designations/`에 저장
4. alert 발송
5. `manual_table.json` 자동 반영 또는 승인 대기

**변경 감지 방식**
- 소스별로 `source_state.json` 유지:
  - `last_success_at`
  - `last_http_status`
  - `last_etag`
  - `last_modified`
  - `last_page_hash`
  - `last_seen_item_ids`
- 2단 해시를 씁니다.
- `page_hash`: 목록 페이지의 `(제목, 날짜, 상세URL, 첨부URL)` 정규화 후 SHA256.
- `item_hash`: 상세 본문 + 첨부 텍스트까지 정규화 후 SHA256.
- 추출 결과도 별도 해시:
  - `designation_hash = sha256(area_type|region_code|designated_at|released_at|announcement_no)`

이렇게 해야:
- 페이지 광고/레이아웃 변경과 실제 공고 변경을 분리할 수 있고
- 같은 제목 재게시도 본문/첨부 기준으로 잡을 수 있고
- 추출 로직 수정 후 동일 이벤트 중복 반영을 막을 수 있습니다.

**자동/반자동 업데이트**
- `manual_table.json`을 바로 덮어쓰지 말고 먼저 `proposed_changes_YYYYMMDD_HHMMSS.json` 생성.
- 내용:
  - source URLs
  - announcement_no
  - detected_at
  - extracted rows
  - confidence
  - raw attachment paths
  - parser warnings
- 그 다음 두 모드 중 선택:
- `semi-auto 권장`
  - `manual_table.patch.json` 생성
  - operator가 admin page 또는 CLI에서 승인
  - 승인 후에만 `manual_table.json` 갱신
- `auto-apply 제한`
  - 전자관보 또는 부처 공식 공고 상세 + 첨부 파싱까지 성공
  - `announcement_no`, `effective date`, `지역 목록` 3개가 모두 추출됨
  - 기존 active row와 충돌 규칙 검사 통과
  - 이 경우에만 자동 반영

**추출 규칙**
- 첨부 PDF/HWP/HWPX가 핵심입니다. HTML 제목만으로는 부족합니다.
- 파서 우선순위:
  - PDF: `pymupdf` 또는 `pdfplumber`
  - HWPX: zip/XML 파싱
  - HWP: 전용 라이브러리 또는 변환 툴, 실패 시 operator review
- region normalization 필요:
  - `서울특별시 강남구` / `서울 강남구` / `강남구`
  - 내부적으로 `region_code`를 같이 저장하는 게 안전합니다.
- release 처리:
  - 기존 active row의 `released_at`만 채우는 케이스와
  - 일부 읍·면 제외/추가 지정 같은 partial update를 분리해야 합니다.

**알림**
- 최소 2채널 권장:
  - Slack/Discord webhook
  - 이메일
- 알림 등급:
  - `critical`: 현재 active 지역 해제/신규 지정 감지
  - `warning`: 뉴스나 RSS만 잡히고 공식 공고 미확인
  - `error`: 2일 이상 MOLIT/MoEF 스크레이퍼 실패
- 메시지에는 반드시:
  - area_type
  - 지역 수
  - 공고번호
  - 유효일
  - source URLs
  - 자동반영 여부
  - 승인 필요 여부

**스크레이핑 리스크와 대응**
- MOLIT/MoEF는 구형 JSP, 파라미터 기반 목록, 첨부파일 중심이라 DOM 의존 파싱이 깨지기 쉽습니다.
- 직접 HTTP 호출이 끊길 수 있어 `requests` 단독보다 `Playwright headless` fallback이 필요합니다.
- 대응 순서:
  1. 일반 HTTP fetch
  2. 실패 시 headless browser fetch
  3. 그래도 실패 시 RSS/뉴스/관보만 감시하고 operator 경보
- 목록 파싱은 CSS selector보다 `제목/날짜/상세링크/첨부링크` 텍스트 앵커 기반이 더 안정적입니다.
- 상세 URL의 `idx`, `bbsId`, `searchKeyword` 같은 파라미터는 raw로 저장해야 재현 가능합니다.

**fallback 전략**
- 1차 fallback: 전자관보 검색으로 동일 키워드 재확인
- 2차 fallback: MOLIT RSS + 보도자료 + 뉴스 API로 signal 유지
- 3차 fallback: operator manual review queue 생성
- 4차 fallback: “감지 실패 상태”를 RAG verdict 보수화에 연결
  - 최근 72시간 이내 primary source degraded면
  - `warnings`에 “규제지역 최신 공고 수동 확인 권장” 추가
  - 필요한 경우 confidence cap

**운영 권장**
- 23:00 하루 1회는 부족합니다.
- 추천:
  - `07:30`, `12:30`, `18:30`, `23:00` 하루 4회
  - 또는 평일 매 2시간
- 이유는 공고가 장중에 뜨고, 양도세 판단은 당일 문의에 바로 영향이 있기 때문입니다.

**이 프로젝트에 맞는 결론**
- source of truth: `manual_table.json`
- detection truth: `전자관보 + 부처 공식 공고 첨부`
- early warning: `MOLIT RSS + 보도자료 + Lawmaking API`
- weak fallback: `뉴스 API`
- update mode: 기본은 `semi-auto approve`, 고신뢰 조건에서만 auto-apply
- integration: `detect_law_changes.py`는 오케스트레이터로 유지하고, 행정지정지역 감지는 별도 모듈/상태파일로 분리

참고 소스:
- MOLIT RSS 안내: https://www.molit.go.kr/USR/p_etc_rsssvc/m_123/ers.jsp
- MOLIT 투기과열지구 해제 공고 상세 예시: https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?idx=17625
- MoEF 고시·공고·지침 검색 예시: https://www.moef.go.kr/lw/pblanc/TbPblancList.do?bbsId=MOSFBBS_000000000060&menuNo=7090200&searchCondition3=1&searchKeyword3=%EC%A7%80%EC%A0%95%EC%A7%80%EC%97%AD
- 국민참여입법센터 API 활용가이드: https://opinion.lawmaking.go.kr/api/operationGuide
- 전자관보: https://www.gwanbo.go.kr/
- 전자관보 효력/발행근거: https://www.gwanbo.go.kr/user/ofcttIntrcn/basis.do

원하시면 다음 단계로 바로 이어서 `detect_area_designations()` 모듈 인터페이스와 `manual_table.patch.json` 스키마까지 설계해드리겠습니다.


OpenAI Codex v0.123.0 (research preview)
--------
workdir: c:\Users\user\cording2025\tax-rag
model: gpt-5.4
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 019e4a1b-3620-7592-bffe-eb208e1b4a79
--------
user
Korean tax RAG system: design a robust area-designation change-detection pipeline. Context: no public API exists for 조정대상지역/투기과열지구/투기지역. These are announced by MOLIT (국토교통부) or MoEF (기획재정부) without notice and directly affect capital gains tax verdicts (비과세↔중과). Current state: manual_table.json hardcoded, Windows Task Scheduler runs detect_law_changes.py daily at 23:00. Stack: Python, Pinecone, scripts/detect_law_changes.py. Question: what is the most reliable technical architecture for (1) detecting new designations/releases, (2) updating manual_table.json automatically or semi-automatically, (3) alerting the operator, (4) fallback if scraping breaks? Be specific about data sources (molit.go.kr, lawmaking.go.kr, 입법예고, RSS, news API), scraping stability risks, hash-based change detection, and integration pattern with detect_law_changes.py.
codex
요청하신 건 코드 변경보다 운영 아키텍처 설계에 가깝습니다. 먼저 현재 리포지토리의 `scripts/detect_law_changes.py`와 관련 파일 구조를 확인한 뒤, 실제 공공 소스들의 현재 접근 경로까지 검증해서 안정적인 감지 파이프라인 형태로 정리하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'rg --files .' in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'Get-Date -Format o' in c:\Users\user\cording2025\tax-rag
 succeeded in 3534ms:
2026-05-21T19:36:10.6950624+09:00

 succeeded in 3560ms:
.\tests\__init__.py
.\tests\test_rag.py
.\tests\test_pipeline_cases.py
.\tests\test_phase1_modules.py
.\tests\test_e2e_golden.py
.\tests\test_chunking.py
.\tests\rag_golden_cases.py
.\CLAUDE.md
.\README.md
.\requirements.txt
.\AGENTS.md
.\src\__init__.py
.\src\ui.py
.\scripts\setup_scheduler.ps1
.\scripts\extract_reranker_pairs.py
.\scripts\detect_law_changes.py
.\scripts\claude_desktop_config.json
.\src\services\__init__.py
.\src\services\tier_router.py
.\src\services\simulation_engine.py
.\src\services\residence_interview.py
.\src\ingestion\__init__.py
.\src\ingestion\embed_rulings.py
.\src\ingestion\embed.py
.\src\ingestion\collect.py
.\src\ingestion\admin_notices.py
.\data\tax_tables\ltshd_rate_table_2.json
.\data\tax_tables\ltshd_rate_table_1.json
.\src\retrieval\__init__.py
.\src\retrieval\retriever_impl.py
.\src\retrieval\llm_fn.py
.\src\rag.py
.\src\infra\__init__.py
.\src\infra\reranker.py
.\src\infra\pinecone_client.py
.\src\infra\embedder.py
.\src\infra\article_tag_map.json
.\src\pages\area_map.py
.\src\pages\admin.py
.\src\eval\__init__.py
.\src\eval\verdict_matcher.py
.\src\eval\retrieval_analyzer.py
.\src\eval\golden_injector.py
.\src\eval\feedback.py
.\src\eval\eval.py
.\src\eval\debate.py
.\src\eval\case_generator.py
.\src\embed.py
.\data\red_wins\ca4dd0de.json
.\data\red_wins\78b96eb1.json
.\src\domain\__init__.py
.\src\domain\tax_constants.py
.\src\domain\tax_answer.py
.\src\domain\special_case_finder.py
.\src\domain\retriever.py
.\src\domain\query_input.py
.\src\domain\query_enrichment.py
.\src\domain\pipeline.py
.\src\domain\output_validator.py
.\src\domain\fact_checker.py
.\src\domain\date_resolver.py
.\src\domain\confirmation.py
.\src\domain\chunk_metadata.py
.\src\domain\acquisition_timeline.py
.\data\debates\78b96eb1.json
.\data\debates\ca4dd0de.json
.\data\golden\example_cases.json
.\data\golden\qa_pairs.json
.\data\area_designations\manual_table.json
.\src\api\mcp_server.py
.\src\api\fact_input.py
.\src\api\chat_api.py
.\src\api\schema.py
.\src\api\sample_cases.py
.\src\api\__init__.py
.\src\calculator\__init__.py
.\src\calculator\tax_calculator.py
.\src\agents\__init__.py
.\src\agents\tools.py
.\src\agents\roles.py
.\src\agents\prompts.py
.\src\agents\crew.py

codex
리포지토리에는 이미 `data/area_designations/manual_table.json`와 `scripts/detect_law_changes.py`가 있습니다. 지금은 이 스크립트 구현과 `admin_notices.py`를 읽고, 동시에 실제 MOLIT/입법예고 채널이 현재 어떤 형태인지 확인하겠습니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content -Path scripts\\detect_law_changes.py -TotalCount 250" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content -Path src\\ingestion\\admin_notices.py -TotalCount 250" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content -Path data\\area_designations\\manual_table.json -TotalCount 200" in c:\Users\user\cording2025\tax-rag
 succeeded in 3530ms:
"""
踰뺣졊 媛쒖젙 ?먮룞 媛먯? ?ㅽ겕由쏀듃

留ㅼ씪 ????ㅽ뻾 ??fetch_law_version_list濡??꾪뻾 MST 紐⑸줉 議고쉶
???ㅻ깄?룰낵 鍮꾧탳 ????踰꾩쟾 諛쒓껄 ??XML ?섏쭛 + Pinecone reindex

?ъ슜踰?
    python -m scripts.detect_law_changes              # 媛먯?留?    python -m scripts.detect_law_changes --embed      # 媛먯? + Pinecone ?낅줈??    python -m scripts.detect_law_changes --dry-run    # API ?몄텧 ?놁씠 ?ㅻ깄?룸쭔 異쒕젰

Windows Task Scheduler ?깅줉:
    schtasks /create /tn "TaxLawChanges" /tr "python -m scripts.detect_law_changes --embed" /sc DAILY /st 23:00
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ?꾨줈?앺듃 猷⑦듃瑜?PYTHONPATH??異붽?
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.collect import (
    TARGET_LAWS,
    fetch_law_version_list,
    fetch_law_xml,
    parse_xml_to_chunks,
    PROCESSED_DIR,
    RAW_DIR,
)

SNAPSHOT_PATH = PROCESSED_DIR / "law_version_snapshots.json"
CHANGE_LOG_PATH = Path("data") / "law_change_log.jsonl"


# ?? ?ㅻ깄??濡쒕뱶/????????????????????????????????????????????????????????????

def load_snapshot() -> dict[str, list[str]]:
    """law_name ??[mst, ...] ?ㅻ깄??濡쒕뱶. ?놁쑝硫?鍮?dict."""
    if not SNAPSHOT_PATH.exists():
        return {}
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_snapshot(snapshot: dict[str, list[str]]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ?? 蹂寃?媛먯? ?????????????????????????????????????????????????????????????????

def detect_changes(
    snapshot: dict[str, list[str]],
) -> dict[str, list[str]]:
    """
    媛?踰뺣졊???꾪뻾 MST 紐⑸줉??API濡?議고쉶?섍퀬 ?ㅻ깄?룰낵 鍮꾧탳?쒕떎.
    諛섑솚: {law_name: [new_mst, ...]} ???ㅻ깄?룹뿉 ?녿뒗 ?좉퇋 MST留??ы븿.
    """
    new_versions: dict[str, list[str]] = {}

    for law in TARGET_LAWS:
        name = law["name"]
        print(f"\n[{name}] 踰꾩쟾 紐⑸줉 議고쉶 以?..")
        try:
            versions = fetch_law_version_list(name)
        except Exception as e:
            print(f"  ??API ?ㅻ쪟: {e}")
            continue

        if not versions:
            print("  ??踰꾩쟾 紐⑸줉 ?놁쓬 (?대젰 API 誘몄????먮뒗 踰뺣졊紐?遺덉씪移?")
            continue

        current_msts = {v["mst"] for v in versions}
        known_msts = set(snapshot.get(name, []))
        added = current_msts - known_msts

        print(f"  ?꾪뻾 踰꾩쟾: {len(current_msts)}媛?| ?좉퇋: {len(added)}媛?)

        if added:
            new_versions[name] = sorted(added)
            for mst in sorted(added):
                v = next((v for v in versions if v["mst"] == mst), {})
                print(f"  ???좉퇋 MST={mst} (?쒗뻾?? {v.get('effective_date', '遺덈챸')})")

    return new_versions


# ?? ?좉퇋 踰꾩쟾 ?섏쭛 + ?좏깮???꾨쿋?????????????????????????????????????????????

def collect_new_versions(
    new_versions: dict[str, list[str]],
    snapshot: dict[str, list[str]],
    do_embed: bool,
) -> None:
    """?좉퇋 MST??XML???섏쭛?섍퀬, do_embed=True ?대㈃ Pinecone???낅줈?쒗븳??"""

    if do_embed:
        # ?꾨쿋??紐⑤뱢? 臾닿굅?곕?濡??꾩슂???뚮쭔 import
        from src.ingestion.embed import embed_and_upload_chunks

    all_new_chunks: list[dict] = []
    law_info_map = {law["name"]: law for law in TARGET_LAWS}

    for law_name, mst_list in new_versions.items():
        law = law_info_map[law_name]
        # ?꾩껜 踰꾩쟾 紐⑸줉 ?ъ“??(effective_date ??硫뷀? ?꾩슂)
        try:
            all_versions = fetch_law_version_list(law_name)
        except Exception:
            all_versions = []
        version_map = {v["mst"]: v for v in all_versions}

        for mst in mst_list:
            raw_path = RAW_DIR / f"{law_name.replace(' ', '_')}_{mst}.xml"
            version = version_map.get(mst, {
                "mst": mst,
                "effective_date": "",
                "promulgation_date": "",
                "expiration_date": "",
            })

            try:
                xml_text = fetch_law_xml(mst)
                RAW_DIR.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(xml_text, encoding="utf-8")
                print(f"  ??XML ??? {law_name} MST={mst}")
            except Exception as e:
                print(f"  ??XML ?섏쭛 ?ㅽ뙣 {mst}: {e}")
                continue

            chunks = parse_xml_to_chunks(xml_text, law, version)
            all_new_chunks.extend(chunks)
            print(f"     泥?겕: {len(chunks)}媛?)

    if not all_new_chunks:
        print("\n?좉퇋 泥?겕 ?놁쓬.")
        return

    # ?좉퇋 泥?겕 JSON ???(媛먯궗 濡쒓렇)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_chunks_path = PROCESSED_DIR / f"new_chunks_{ts}.json"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    new_chunks_path.write_text(
        json.dumps(all_new_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n?좉퇋 泥?겕 {len(all_new_chunks)}媛???{new_chunks_path}")

    if do_embed:
        print("Pinecone ?낅줈??以?..")
        embed_and_upload_chunks(all_new_chunks)
        print("Pinecone ?낅줈???꾨즺")
    else:
        print("--embed ?놁씠 ?ㅽ뻾: Pinecone ?낅줈??嫄대꼫?.")
        print(f"?낅줈?쒗븯?ㅻ㈃:  python -m scripts.detect_law_changes --embed")


# ?? 蹂寃??대젰 湲곕줉 ????????????????????????????????????????????????????????????

def append_change_log(new_versions: dict[str, list[str]]) -> None:
    """data/law_change_log.jsonl ??媛먯? 寃곌낵瑜???以꾩뵫 湲곕줉."""
    CHANGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHANGE_LOG_PATH.open("a", encoding="utf-8") as f:
        for law_name, mst_list in new_versions.items():
            record = {
                "detected_at": datetime.now().isoformat(),
                "law_name": law_name,
                "new_msts": mst_list,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ?? 硫붿씤 ?????????????????????????????????????????????????????????????????????

def main() -> None:
    parser = argparse.ArgumentParser(description="踰뺣졊 媛쒖젙 ?먮룞 媛먯?")
    parser.add_argument("--embed", action="store_true", help="?좉퇋 踰꾩쟾 Pinecone ?낅줈??)
    parser.add_argument("--dry-run", action="store_true", help="?ㅻ깄?룸쭔 異쒕젰, API ?몄텧 ?놁쓬")
    parser.add_argument("--reset-snapshot", action="store_true", help="?ㅻ깄??珥덇린?????꾩껜 ?ъ닔吏?)
    args = parser.parse_args()

    print(f"=== 踰뺣졊 媛쒖젙 媛먯? ?쒖옉 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    print(f"???踰뺣졊: {len(TARGET_LAWS)}媛?n")

    if args.dry_run:
        snapshot = load_snapshot()
        print("--- ?꾩옱 ?ㅻ깄??---")
        if snapshot:
            for name, msts in snapshot.items():
                print(f"  {name}: {len(msts)}媛?踰꾩쟾")
        else:
            print("  (?ㅻ깄???놁쓬 - 泥??ㅽ뻾 ???꾩껜 ?섏쭛)")
        return

    snapshot = {} if args.reset_snapshot else load_snapshot()
    if args.reset_snapshot:
        print("?ㅻ깄??珥덇린?? ?꾩껜 踰꾩쟾 ?ъ닔吏묓빀?덈떎.\n")

    # 1. 蹂寃?媛먯?
    new_versions = detect_changes(snapshot)

    # 2. 寃곌낵 ?붿빟
    total_new = sum(len(v) for v in new_versions.values())
    print(f"\n=== 媛먯? ?꾨즺: {total_new}媛??좉퇋 踰꾩쟾 ===")

    if not new_versions:
        print("蹂寃??놁쓬.")
    else:
        for name, msts in new_versions.items():
            print(f"  {name}: {msts}")

        # 3. ?섏쭛 + ?좏깮???꾨쿋??        collect_new_versions(new_versions, snapshot, do_embed=args.embed)

        # 4. 蹂寃??대젰 湲곕줉
        append_change_log(new_versions)

    # 5. ?ㅻ깄??媛깆떊 (?좉퇋 踰꾩쟾???놁뼱???꾪뻾 紐⑸줉?쇰줈 ?낅뜲?댄듃)
    try:
        updated_snapshot = dict(snapshot)
        for law in TARGET_LAWS:
            name = law["name"]
            try:
                versions = fetch_law_version_list(name)
                if versions:
                    updated_snapshot[name] = sorted({v["mst"] for v in versions})
            except Exception:
                pass  # 媛깆떊 ?ㅽ뙣?대룄 湲곗〈 媛??좎?
        save_snapshot(updated_snapshot)
        print(f"\n?ㅻ깄??????꾨즺: {SNAPSHOT_PATH}")
    except Exception as e:
        print(f"\n???ㅻ깄??????ㅽ뙣: {e}")

    print("\n=== ?꾨즺 ===")


if __name__ == "__main__":
    main()

 succeeded in 3522ms:
[
  {
    "region": "?쒖슱?밸퀎??,
    "area_type": "議곗젙??곸???,
    "designated_at": "2016-11-03",
    "released_at": null,
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??016-786??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎??媛뺣궓援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???쒖큹援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???≫뙆援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎??媛뺣궓援?,
    "area_type": "議곗젙??곸???,
    "designated_at": "2016-11-03",
    "released_at": null,
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??016-786??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???쒖큹援?,
    "area_type": "議곗젙??곸???,
    "designated_at": "2016-11-03",
    "released_at": null,
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??016-786??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???≫뙆援?,
    "area_type": "議곗젙??곸???,
    "designated_at": "2016-11-03",
    "released_at": null,
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??016-786??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???⑹궛援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎??留덊룷援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???깅룞援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???몄썝援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎??媛뺣룞援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2024-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎??媛뺣궓援?,
    "area_type": "?ш린吏??,
    "designated_at": "2017-08-03",
    "released_at": "2023-01-05",
    "announcement_no": "湲고쉷?ъ젙遺怨좎떆 ??017-17??,
    "source_url": "https://www.moef.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???쒖큹援?,
    "area_type": "?ш린吏??,
    "designated_at": "2017-08-03",
    "released_at": "2023-01-05",
    "announcement_no": "湲고쉷?ъ젙遺怨좎떆 ??017-17??,
    "source_url": "https://www.moef.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???≫뙆援?,
    "area_type": "?ш린吏??,
    "designated_at": "2017-08-03",
    "released_at": "2023-01-05",
    "announcement_no": "湲고쉷?ъ젙遺怨좎떆 ??017-17??,
    "source_url": "https://www.moef.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎??媛뺣궓援?,
    "area_type": "?좎?嫄곕옒?덇?援ъ뿭",
    "designated_at": "2020-06-17",
    "released_at": null,
    "announcement_no": "?쒖슱?밸퀎?쒓퀬????020-272??,
    "source_url": "https://www.seoul.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???쒖큹援?,
    "area_type": "?좎?嫄곕옒?덇?援ъ뿭",
    "designated_at": "2020-06-17",
    "released_at": null,
    "announcement_no": "?쒖슱?밸퀎?쒓퀬????020-272??,
    "source_url": "https://www.seoul.go.kr"
  },
  {
    "region": "?쒖슱?밸퀎???≫뙆援?,
    "area_type": "?좎?嫄곕옒?덇?援ъ뿭",
    "designated_at": "2020-06-17",
    "released_at": null,
    "announcement_no": "?쒖슱?밸퀎?쒓퀬????020-272??,
    "source_url": "https://www.seoul.go.kr"
  },
  {
    "region": "寃쎄린???깅궓??遺꾨떦援?,
    "area_type": "議곗젙??곸???,
    "designated_at": "2016-11-03",
    "released_at": "2022-11-14",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??016-786??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "寃쎄린???깅궓??遺꾨떦援?,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2022-11-14",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "寃쎄린??怨쇱쿇??,
    "area_type": "議곗젙??곸???,
    "designated_at": "2016-11-03",
    "released_at": "2022-11-14",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??016-786??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "寃쎄린??怨쇱쿇??,
    "area_type": "?ш린怨쇱뿴吏援?,
    "designated_at": "2018-08-28",
    "released_at": "2022-11-14",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-599??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "寃쎄린???섎궓??,
    "area_type": "議곗젙??곸???,
    "designated_at": "2018-12-31",
    "released_at": "2022-11-14",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??018-916??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?몄쿇愿묒뿭???곗닔援?,
    "area_type": "議곗젙??곸???,
    "designated_at": "2020-06-19",
    "released_at": "2022-11-14",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??020-489??,
    "source_url": "https://www.molit.go.kr"
  },
  {
    "region": "?몄쥌?밸퀎?먯튂??,
    "area_type": "議곗젙??곸???,
    "designated_at": "2016-11-03",
    "released_at": "2023-01-05",
    "announcement_no": "援?넗援먰넻遺怨좎떆 ??016-786??,
    "source_url": "https://www.molit.go.kr"

 succeeded in 3552ms:
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
from typing import List, Literal, Optional

from dotenv import load_dotenv

load_dotenv()

MOEF_API_KEY = os.getenv("MOEF_API_KEY", "")
FSC_API_KEY = os.getenv("FSC_API_KEY", "")
NOTICES_DIR = Path(os.getenv("ADMIN_NOTICES_DIR", "data/admin_notices"))


# ?? ?곗씠??紐⑤뜽 ????????????????????????????????????????????????????????????????


@dataclass
class AreaDesignationRecord:
    """
    吏??吏???④굔 ?덉퐫??(3醫??듯빀).

    ?몃쾿 ?곸슜 湲곗?:
      - 議곗젙??곸???痍⑤뱷????2??嫄곗＜?붽굔 (?뚮졊 짠154??
      - 議곗젙??곸????묐룄?????ㅼ＜??以묎낵 (?뚮쾿 짠104??
      - ?ш린怨쇱뿴吏援?痍⑤뱷????二쇳깮?대낫?異?LTV ?쒗븳
      - ?좎?嫄곕옒?덇?援ъ뿭 ???ㅺ굅二??섎Т
    """
    region: str                         # 吏??챸 ("?쒖슱?밸퀎??媛뺣궓援? ??
    area_type: Literal["議곗젙??곸???, "?ш린怨쇱뿴吏援?, "?좎?嫄곕옒?덇?援ъ뿭", "?ш린吏??]
    designated_at: date                 # 吏?뺤씪
    released_at: Optional[date]         # ?댁젣??(None = ?꾩옱 ?좏슚)
    announcement_no: str                # 怨좎떆 踰덊샇 ("援?넗援먰넻遺怨좎떆 ??021-1588?? ??
    source: str = "manual"              # "manual" | "api"
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


# backward compat
AdjustmentAreaRecord = AreaDesignationRecord


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
    area_designations: List[AreaDesignationRecord] = field(default_factory=list)
    financial_regulations: List[FinancialRegulationRecord] = field(default_factory=list)
    last_updated: Optional[str] = None

    @property
    def adjustment_areas(self) -> List[AreaDesignationRecord]:
        """backward compat ??area_designations??蹂꾩묶."""
        return self.area_designations

    @adjustment_areas.setter
    def adjustment_areas(self, value: List[AreaDesignationRecord]) -> None:
        self.area_designations = value


# ?? 吏??吏??議고쉶 ?ы띁 ????????????????????????????????????????????????????????

MANUAL_TABLE_PATH = Path("data/area_designations/manual_table.json")


def load_manual_table() -> List[AreaDesignationRecord]:
    """
    ?섎룞 湲곗???濡쒕뱶.
    踰뺤쟻 遺꾩웳 ?곗씠?????섎룞 湲곗??쒓? API蹂대떎 ?곗꽑.
    """
    if not MANUAL_TABLE_PATH.exists():
        return []
    raw = json.loads(MANUAL_TABLE_PATH.read_text(encoding="utf-8"))
    result: List[AreaDesignationRecord] = []
    for r in raw:
        result.append(AreaDesignationRecord(
            region=r["region"],
            area_type=r["area_type"],
            designated_at=date.fromisoformat(r["designated_at"]),
            released_at=date.fromisoformat(r["released_at"]) if r.get("released_at") else None,
            announcement_no=r.get("announcement_no", ""),
            source="manual",
            source_url=r.get("source_url"),
        ))
    return result


def resolve_area_status(
    region: str,
    target_date: date,
    area_type: str,
    records: List[AreaDesignationRecord],
) -> bool:
    """
    region??target_date ?쒖젏??area_type?쇰줈 吏?뺣릺???덉뿀?붿? 議고쉶.
    ?섎룞 湲곗????곗꽑 (legal disputes ??API蹂대떎 ?좊ː???믪쓬).

    ?ъ슜泥?
      - L1 RAGQueryInput ?앹꽦 ??adjustment_area_at_acquisition / _at_transfer 怨꾩궛
      - fact_input.py FlatFactInput ??RAGQueryInput 蹂????    """
    for rec in records:
        if rec.area_type == area_type and rec.region in region:
            if rec.is_designated_as_of(target_date):
                return True
    return False


def resolve_adjustment_area(region: str, target_date: date, db: "AdminNoticesDB") -> bool:
    """
    backward compat ??resolve_area_status(area_type="議곗젙??곸???) ?몄텧.

    DB媛 鍮꾩뼱?덉쑝硫?False 諛섑솚 (?섏쭛 誘몄셿猷??곹깭).
    """
    return resolve_area_status(region, target_date, "議곗젙??곸???, db.area_designations)


def load_db() -> AdminNoticesDB:
    """??λ맂 DB 濡쒕뱶. ?뚯씪 ?놁쑝硫?鍮?DB 諛섑솚."""
    path = NOTICES_DIR / "admin_notices_db.json"
    if not path.exists():
        return AdminNoticesDB()
    raw = json.loads(path.read_text(encoding="utf-8"))

    # support both old key ("adjustment_areas") and new key ("area_designations")
    area_raw = raw.get("area_designations", raw.get("adjustment_areas", []))
    areas = [
        AreaDesignationRecord(
            region=r["region"],
            area_type=r["area_type"],
            designated_at=date.fromisoformat(r["designated_at"]),
            released_at=date.fromisoformat(r["released_at"]) if r.get("released_at") else None,
            announcement_no=r.get("announcement_no", ""),
            source=r.get("source", "manual"),
            source_url=r.get("source_url"),
        )
        for r in area_raw
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
        area_designations=areas,
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
        "area_designations": [
            {k: _serial(v) for k, v in asdict(r).items()}
            for r in db.area_designations
        ],
        "financial_regulations": [
            {k: _serial(v) for k, v in asdict(r).items()}
            for r in db.financial_regulations
        ],
        "last_updated": db.last_updated,
    }
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


# ?? ?섏쭛 ?ㅽ뀅 ??????????????????????????????????????????????????????????????????


async def collect_adjustment_areas() -> List[AreaDesignationRecord]:
    """
    援?넗援먰넻遺 怨듦났?곗씠?고룷??API?먯꽌 議곗젙??곸????꾪솴 ?섏쭛.

    API: data.go.kr > 援?넗援먰넻遺_?ш린怨쇱뿴吏援?룹“?뺣??곸???怨좎떆 ?꾪솴
    ?섍꼍蹂?? MOEF_API_KEY

    TODO:
      1. data.go.kr?먯꽌 API ??諛쒓툒 (MOEF_API_KEY)
      2. ?붾뱶?ъ씤???뺤씤 ???꾨옒 援ы쁽 梨꾩슦湲?      3. ?묐떟 ?뚯떛: region, designated_at, released_at, announcement_no 異붿텧
    """

web search: 
web search: site:molit.go.kr 조정대상지역 공고 보도자료 주거정책심의위원회
web search: 
web search: site:molit.go.kr RSS 보도자료 molit
web search: 
web search: site:lawmaking.go.kr RSS 법제처 입법예고 RSS
web search: 
web search: https://www.moef.go.kr/lw/pblanc/TbPblancList.do?bbsId=MOSFBBS_000000000060&menuNo=7090200
web search: 
web search: site:molit.go.kr 조정대상지역 조정 주거정책심의위원회 보도자료 2024 molit
web search: 
web search: 
codex
현재 구조상 `detect_law_changes.py`는 법령 개정 감지용이고, 행정지정지역은 `manual_table.json`만 수동 기준표로 쓰고 있습니다. 여기서 핵심은 “법령 수집 파이프라인과 별개로, 공고/보도자료/입법예고를 다층 감시하는 별도 watcher”를 두는 쪽이 맞는지 검증하는 단계입니다.
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "@'
import requests
urls = [
  'https://www.molit.go.kr/USR/p_etc_rsssvc/m_123/ers.jsp',
  'https://www.moef.go.kr/lw/pblanc/TbPblancList.do?bbsId=MOSFBBS_000000000060&menuNo=7090200&searchCondition3=1&searchKeyword3=%EC%A7%80%EC%A0%95%EC%A7%80%EC%97%AD',
  'https://opinion.lawmaking.go.kr/api/operationGuide'
]
for u in urls:
    try:
        r = requests.get(u, timeout=20)
        print('URL:', u)
        print('STATUS:', r.status_code)
        print('FINAL:', r.url)
        print(r.text[:800].replace('\\n',' ')[:800])
        print('\\n' + '='*80 + '\\n')
    except Exception as e:
        print('URL:', u)
        print('ERROR:', e)
        print('\\n' + '='*80 + '\\n')
'@ | python -" in c:\Users\user\cording2025\tax-rag
exec
"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content -Path scripts\\setup_scheduler.ps1 -TotalCount 200" in c:\Users\user\cording2025\tax-rag
 succeeded in 3377ms:
# Law change detection - Windows Task Scheduler registration
# Run as Administrator: .\scripts\setup_scheduler.ps1

$TaskName    = "TaxRAG-LawChangeDetect"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe   = (Get-Command python).Source
$LogDir      = Join-Path $ProjectRoot "data\logs"
$LogFile     = Join-Path $LogDir "law_change_detect.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$ArgString = "-m scripts.detect_law_changes --embed"

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ArgString `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At "23:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10)

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task"
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Tax-RAG law change detection + Pinecone reindex" `
    -RunLevel Highest

Write-Host ""
Write-Host "=== Registered ==="
Write-Host "Task     : $TaskName"
Write-Host "Schedule : Daily 23:00"
Write-Host "Log      : $LogFile"
Write-Host ""
Write-Host "Manual test:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"

 succeeded in 5697ms:
URL: https://www.molit.go.kr/USR/p_etc_rsssvc/m_123/ers.jsp
ERROR: ('Connection aborted.', ConnectionResetError(10054, '현재 연결은 원격 호스트에 의해 강제로 끊겼습니다', None, 10054, None))

================================================================================

URL: https://www.moef.go.kr/lw/pblanc/TbPblancList.do?bbsId=MOSFBBS_000000000060&menuNo=7090200&searchCondition3=1&searchKeyword3=%EC%A7%80%EC%A0%95%EC%A7%80%EC%97%AD
ERROR: ('Connection aborted.', ConnectionResetError(10054, '현재 연결은 원격 호스트에 의해 강제로 끊겼습니다', None, 10054, None))

================================================================================

URL: https://opinion.lawmaking.go.kr/api/operationGuide
STATUS: 200
FINAL: https://opinion.lawmaking.go.kr/api/operationGuide
                                                                                                                                                           <!DOCTYPE html> <html lang="ko">  <head> 	<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />  	<meta http-equiv="X-UA-Compatible" content="IE=edge" />  	<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no" />  	<title>국민참여입법센터</title> 	 	<link rel="preload" href="/static/css/font/woff2/PretendardGOV-Bold.subset.woff2" as="font" type="font/woff2" crossorigin> 	<link rel="preload" href="

================================================================================


web search: 
web search: site:data.go.kr 조정대상지역 API
web search: 
web search: site:gwanbo.go.kr 투기과열지구 공고
codex
가장 신뢰도 높은 구조는 `manual_table.json`을 계속 1급 기준표로 두고, 그 앞단에 “다중 소스 감시 + 후보 추출 + 승인 반영” 파이프라인을 붙이는 방식입니다. 이 프로젝트 성격상 `full auto overwrite`보다 `high-confidence auto patch + operator approve`가 맞습니다. 조정대상지역/투기과열지구/투기지역은 법적 효력이 큰데, 공고 형식과 게시 위치가 자주 흔들리고, 실제로 MOLIT/MoEF는 단순 `requests` 호출을 끊는 경우도 있어 WAF/anti-bot 리스크가 있습니다.

**권장 아키텍처**
1. `P0 authoritative`
- 전자관보 `gwanbo.go.kr`: 최종 공고 효력 확인용.
- MOLIT 공고/행정규칙 상세 + 첨부 PDF/HWP/HWPX: 조정대상지역, 투기과열지구.
- MoEF 고시·공고·지침 상세 + 첨부 PDF/HWP: 투기지역.

2. `P1 early signal`
- MOLIT RSS: 보도자료/공지 신규 게시 감지.
- MOLIT 보도자료: 주거정책심의위원회 결과가 공고보다 먼저 뜨는 경우가 많음.
- Lawmaking API: `주택법`, `소득세법 시행령`, 관련 입법예고/행정예고를 감시해서 “곧 바뀔 수 있음” 신호로만 사용.

3. `P2 weak fallback`
- News API: 네이버 뉴스 API, GDELT, NewsAPI 중 하나.
- 키워드: `조정대상지역`, `투기과열지구`, `투기지역`, `지정 해제`, `주거정책심의위원회`, `부동산 지정지역 해제 공고문`.
- 뉴스는 절대 truth source로 쓰지 말고 “공식 사이트 재확인 필요” 경보만 올립니다.

**구현 패턴**
- 기존 `scripts/detect_law_changes.py`는 유지하고, 여기에 `detect_area_designations()`를 오케스트레이션으로 붙입니다.
- 실제 소스별 구현은 분리합니다.
- 예시:
  - `src/ingestion/area_sources/molit_rss.py`
  - `src/ingestion/area_sources/molit_board.py`
  - `src/ingestion/area_sources/moef_board.py`
  - `src/ingestion/area_sources/lawmaking_api.py`
  - `src/ingestion/area_sources/news_signal.py`
  - `src/ingestion/area_designation_pipeline.py`

`detect_law_changes.py` 흐름:
1. 기존 법령 버전 감지 실행
2. `detect_area_designations()` 실행
3. 결과를 `data/admin_notices/`와 `data/area_designations/`에 저장
4. alert 발송
5. `manual_table.json` 자동 반영 또는 승인 대기

**변경 감지 방식**
- 소스별로 `source_state.json` 유지:
  - `last_success_at`
  - `last_http_status`
  - `last_etag`
  - `last_modified`
  - `last_page_hash`
  - `last_seen_item_ids`
- 2단 해시를 씁니다.
- `page_hash`: 목록 페이지의 `(제목, 날짜, 상세URL, 첨부URL)` 정규화 후 SHA256.
- `item_hash`: 상세 본문 + 첨부 텍스트까지 정규화 후 SHA256.
- 추출 결과도 별도 해시:
  - `designation_hash = sha256(area_type|region_code|designated_at|released_at|announcement_no)`

이렇게 해야:
- 페이지 광고/레이아웃 변경과 실제 공고 변경을 분리할 수 있고
- 같은 제목 재게시도 본문/첨부 기준으로 잡을 수 있고
- 추출 로직 수정 후 동일 이벤트 중복 반영을 막을 수 있습니다.

**자동/반자동 업데이트**
- `manual_table.json`을 바로 덮어쓰지 말고 먼저 `proposed_changes_YYYYMMDD_HHMMSS.json` 생성.
- 내용:
  - source URLs
  - announcement_no
  - detected_at
  - extracted rows
  - confidence
  - raw attachment paths
  - parser warnings
- 그 다음 두 모드 중 선택:
- `semi-auto 권장`
  - `manual_table.patch.json` 생성
  - operator가 admin page 또는 CLI에서 승인
  - 승인 후에만 `manual_table.json` 갱신
- `auto-apply 제한`
  - 전자관보 또는 부처 공식 공고 상세 + 첨부 파싱까지 성공
  - `announcement_no`, `effective date`, `지역 목록` 3개가 모두 추출됨
  - 기존 active row와 충돌 규칙 검사 통과
  - 이 경우에만 자동 반영

**추출 규칙**
- 첨부 PDF/HWP/HWPX가 핵심입니다. HTML 제목만으로는 부족합니다.
- 파서 우선순위:
  - PDF: `pymupdf` 또는 `pdfplumber`
  - HWPX: zip/XML 파싱
  - HWP: 전용 라이브러리 또는 변환 툴, 실패 시 operator review
- region normalization 필요:
  - `서울특별시 강남구` / `서울 강남구` / `강남구`
  - 내부적으로 `region_code`를 같이 저장하는 게 안전합니다.
- release 처리:
  - 기존 active row의 `released_at`만 채우는 케이스와
  - 일부 읍·면 제외/추가 지정 같은 partial update를 분리해야 합니다.

**알림**
- 최소 2채널 권장:
  - Slack/Discord webhook
  - 이메일
- 알림 등급:
  - `critical`: 현재 active 지역 해제/신규 지정 감지
  - `warning`: 뉴스나 RSS만 잡히고 공식 공고 미확인
  - `error`: 2일 이상 MOLIT/MoEF 스크레이퍼 실패
- 메시지에는 반드시:
  - area_type
  - 지역 수
  - 공고번호
  - 유효일
  - source URLs
  - 자동반영 여부
  - 승인 필요 여부

**스크레이핑 리스크와 대응**
- MOLIT/MoEF는 구형 JSP, 파라미터 기반 목록, 첨부파일 중심이라 DOM 의존 파싱이 깨지기 쉽습니다.
- 직접 HTTP 호출이 끊길 수 있어 `requests` 단독보다 `Playwright headless` fallback이 필요합니다.
- 대응 순서:
  1. 일반 HTTP fetch
  2. 실패 시 headless browser fetch
  3. 그래도 실패 시 RSS/뉴스/관보만 감시하고 operator 경보
- 목록 파싱은 CSS selector보다 `제목/날짜/상세링크/첨부링크` 텍스트 앵커 기반이 더 안정적입니다.
- 상세 URL의 `idx`, `bbsId`, `searchKeyword` 같은 파라미터는 raw로 저장해야 재현 가능합니다.

**fallback 전략**
- 1차 fallback: 전자관보 검색으로 동일 키워드 재확인
- 2차 fallback: MOLIT RSS + 보도자료 + 뉴스 API로 signal 유지
- 3차 fallback: operator manual review queue 생성
- 4차 fallback: “감지 실패 상태”를 RAG verdict 보수화에 연결
  - 최근 72시간 이내 primary source degraded면
  - `warnings`에 “규제지역 최신 공고 수동 확인 권장” 추가
  - 필요한 경우 confidence cap

**운영 권장**
- 23:00 하루 1회는 부족합니다.
- 추천:
  - `07:30`, `12:30`, `18:30`, `23:00` 하루 4회
  - 또는 평일 매 2시간
- 이유는 공고가 장중에 뜨고, 양도세 판단은 당일 문의에 바로 영향이 있기 때문입니다.

**이 프로젝트에 맞는 결론**
- source of truth: `manual_table.json`
- detection truth: `전자관보 + 부처 공식 공고 첨부`
- early warning: `MOLIT RSS + 보도자료 + Lawmaking API`
- weak fallback: `뉴스 API`
- update mode: 기본은 `semi-auto approve`, 고신뢰 조건에서만 auto-apply
- integration: `detect_law_changes.py`는 오케스트레이터로 유지하고, 행정지정지역 감지는 별도 모듈/상태파일로 분리

참고 소스:
- MOLIT RSS 안내: https://www.molit.go.kr/USR/p_etc_rsssvc/m_123/ers.jsp
- MOLIT 투기과열지구 해제 공고 상세 예시: https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?idx=17625
- MoEF 고시·공고·지침 검색 예시: https://www.moef.go.kr/lw/pblanc/TbPblancList.do?bbsId=MOSFBBS_000000000060&menuNo=7090200&searchCondition3=1&searchKeyword3=%EC%A7%80%EC%A0%95%EC%A7%80%EC%97%AD
- 국민참여입법센터 API 활용가이드: https://opinion.lawmaking.go.kr/api/operationGuide
- 전자관보: https://www.gwanbo.go.kr/
- 전자관보 효력/발행근거: https://www.gwanbo.go.kr/user/ofcttIntrcn/basis.do

원하시면 다음 단계로 바로 이어서 `detect_area_designations()` 모듈 인터페이스와 `manual_table.patch.json` 스키마까지 설계해드리겠습니다.
tokens used
122,534

```

## Concise summary

Provider completed successfully. Review the raw output for details.

## Action items

- Review the response and extract decisions you want to apply.
- Capture follow-up implementation tasks if needed.
