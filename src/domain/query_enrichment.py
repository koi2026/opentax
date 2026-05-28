"""
L3 — Query Enrichment

danger_flags → 도메인 키워드 주입.
벡터 검색은 "입력 텍스트와 유사한 조문"을 찾으므로,
키워드가 없으면 해당 조문이 검색 결과에서 누락됨.

예: "이월과세" 키워드 없이 "배우자 증여 주택 양도" 검색
    → §97의2 대신 일반 양도세 조문만 검색됨 → 틀린 취득가액 적용
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from .query_input import RAGQueryInput


# danger_flag → 삽입할 도메인 키워드 + 조문 번호
# 키워드가 쿼리에 있어야 벡터 검색이 해당 조문 청크를 찾아옴
DANGER_KEYWORD_MAP: Dict[str, str] = {
    "이월과세": "배우자 직계존비속 증여 이월과세 소득세법 제97조의2 원취득가액",
    "이월과세_5년이내": "증여 후 5년 이내 양도 이월과세 소득세법 제97조의2",
    "이월과세_10년이내": "증여 후 10년 이내 양도 이월과세 소득세법 제97조의2 2023년 개정",
    "고가주택_미확인": "고가주택 12억 초과 장기보유특별공제 표2 소득세법 제95조",
    "고가주택": "고가주택 12억 장기보유특별공제 표2 소득세법 제95조 시행령 제156조의2",
    "상속주택": "상속주택 소득세법 시행령 제155조 피상속인 보유기간 합산",
    "상속주택_자체양도": "상속주택 자체양도 피상속인 보유기간 합산 소령 제155조 제3항",
    "일시적2주택": "일시적 2주택 종전주택 3년 이내 양도 소득세법 시행령 제155조 제1항",
    "조합원입주권": "조합원입주권 관리처분계획인가 보유기간 소득세법 시행령 제156조의2",
    "분양권": "분양권 소득세법 제88조 주택 수 산입",
    "분양권_2021전_주택수미산입": "2020년 이전 취득 분양권 주택 수 미산입 소득세법 부칙",
    "분양권_2021후_주택수산입": "2021년 이후 취득 분양권 주택 수 산입 소득세법 제88조 제7항",
    "분양권_기준불명": "분양권 취득일 2021년 기준 주택 수 산입 여부 소득세법 제88조",
    "상생임대": "상생임대주택 거주요건 면제 소득세법 시행령 제155조의3",
    "공동명의": "공동명의 지분 양도 비율 소득세법 제88조 제1항",
    "비거주자": "비거주자 1세대 1주택 비과세 배제 소득세법 제121조",
    "비거주자_해외이주2년이내양도가능": "해외이주 2년 이내 양도 비과세 소득세법 시행령 제154조 제1항 제2호",
    "재건축재개발원조합원": "원조합원 재건축 보유기간 관리처분 소득세법 시행령 제156조의2",
    "재건축재개발승계조합원": "승계조합원 입주권 취득일 보유기간 소득세법 시행령 제156조의2",
    "동거봉양합가": "동거봉양 합가 10년 이내 비과세 소득세법 시행령 제155조 제4항",
    "수용_compulsory_거주요건면제": "강제수용 거주요건 면제 소득세법 시행령 제154조 제1항 단서",
    "수용_negotiated_거주요건면제": "협의취득 거주요건 면제 소득세법 시행령 제154조 제1항 단서",
    "특수관계자거래": "특수관계자 저가양도 고가매입 부당행위계산부인 소득세법 제101조 시가",
    "조정지역_거주요건": "조정대상지역 취득 거주기간 2년 소득세법 시행령 제154조 비과세 요건",
    "농어촌주택": "농어촌주택 보유 주택 수 제외 1세대1주택 비과세 적용 소득세법시행령 제155조의2 조세특례제한법 제99조의4",
    "공익수용감면": "조세특례제한법 제77조 공익사업 수용 양도소득세 감면 채권보상 대토보상",
    "수용_조특77감면": "조세특례제한법 제77조 공익사업 수용 양도소득세 감면 채권보상 대토보상 15% 30%",
    "다주택중과": "다주택자 조정대상지역 중과세율 소득세법 제104조 제1항 제7호 제8호 20퍼센트 30퍼센트",
    "다주택비조정": "다주택자 비조정대상지역 일반세율 소득세법 제104조 중과 비해당 기본세율",
    "중과한시면세": "한시적 중과세율 배제 2022년5월10일~2026년5월9일 다주택자 조정대상지역 중과 적용 제외 일반세율 소득세법 제104조 조세특례제한법 부칙 시행령",
    "장기임대감면": "조세특례제한법 제97조의3 장기임대주택 양도소득세 감면 의무임대기간 임대사업자등록",
    "장기임대감면취소": "조세특례제한법 제97조의3 장기임대주택 감면 취소 의무임대기간 미충족 5% 증액제한 위반 일반과세",
}


def _load_keyword_patch() -> None:
    """auto_apply_map_updates()가 저장한 패치를 DANGER_KEYWORD_MAP에 적용한다."""
    patch_path = Path("data/eval_results/keyword_map_patch.json")
    if patch_path.exists():
        try:
            patch = json.loads(patch_path.read_text(encoding="utf-8"))
            DANGER_KEYWORD_MAP.update(patch)
        except Exception:
            pass


_load_keyword_patch()


def _build_dynamic_entries() -> None:
    """TaxConstantsRegistry 연동 — 현재 유효한 이월과세 기간으로 키워드 동적 생성.

    IOTA_PERIOD_YEARS가 개정되면 새 키(예: "이월과세_7년이내")가 자동으로 추가된다.
    기존 키(5년/10년)는 유지되므로 하위 호환성 깨지지 않는다.
    """
    try:
        from datetime import date as _date
        from .tax_constants import TaxConstantsRegistry as _TCR
        iota_years: int = _TCR.get("IOTA_PERIOD_YEARS", _date.today())
        key = f"이월과세_{iota_years}년이내"
        if key not in DANGER_KEYWORD_MAP:
            DANGER_KEYWORD_MAP[key] = (
                f"증여 후 {iota_years}년 이내 양도 이월과세 소득세법 제97조의2 "
                f"배우자 직계존비속 원취득가액 원취득일"
            )
    except Exception:
        pass  # 순환임포트 등 예외 시 기존 정적 맵으로 동작


_build_dynamic_entries()


# raw 텍스트에서 danger_flag를 자동 탐지하는 패턴 목록.
# eval.py / mcp_server.py 등 L2 팩트체크 없이 텍스트만 있는 경우에 사용.
RAW_TRIGGER_PATTERNS: List[tuple] = [
    (re.compile(r"배우자|직계존비속|증여"), "이월과세"),
    (re.compile(r"이월과세"), "이월과세"),
    (re.compile(r"상속"), "상속주택"),
    (re.compile(r"일시적.{0,4}2주택|종전주택"), "일시적2주택"),
    (re.compile(r"고가주택|12억"), "고가주택"),
    (re.compile(r"상생임대"), "상생임대"),
    (re.compile(r"분양권"), "분양권"),
    (re.compile(r"조합원입주권|입주권"), "조합원입주권"),
    (re.compile(r"비거주자|해외이주"), "비거주자"),
    (re.compile(r"동거봉양|합가"), "동거봉양합가"),
    (re.compile(r"수용|강제취득|협의취득"), "수용_compulsory_거주요건면제"),
    (re.compile(r"재건축|재개발"), "재건축재개발원조합원"),
    (re.compile(r"공동명의|지분"), "공동명의"),
    (re.compile(r"특수관계자|부당행위계산"), "특수관계자거래"),
]


def detect_flags_from_text(query: str) -> List[str]:
    """raw 텍스트에서 danger_flags를 자동 탐지한다."""
    seen: set[str] = set()
    flags: List[str] = []
    for pattern, flag in RAW_TRIGGER_PATTERNS:
        if pattern.search(query) and flag not in seen:
            flags.append(flag)
            seen.add(flag)
    return flags


def enrich_raw_query_text(query: str) -> str:
    """
    raw 텍스트 패턴 매칭으로 도메인 키워드를 주입한다.
    L2 팩트체크 없이 텍스트만 있을 때(MCP, eval) 사용.
    """
    flags = detect_flags_from_text(query)
    return enrich_query(query, flags)


def enrich_query(base_query: str, danger_flags: List[str]) -> str:
    """
    RAG 검색 쿼리에 danger_flags에 대응하는 도메인 키워드를 주입.

    Args:
        base_query: fact_vector.to_text() 등 기본 쿼리 텍스트
        danger_flags: FactCheckResult.danger_flags

    Returns:
        키워드가 주입된 강화 쿼리 텍스트
    """
    injected: List[str] = []
    seen: set[str] = set()

    for flag in danger_flags:
        kw = DANGER_KEYWORD_MAP.get(flag)
        if kw and kw not in seen:
            injected.append(kw)
            seen.add(kw)

    if not injected:
        return base_query

    enriched = base_query + "\n[검색 보강] " + " | ".join(injected)
    return enriched


def build_rag_query(query_input: RAGQueryInput, danger_flags: List[str]) -> str:
    """
    RAGQueryInput → 최종 RAG 검색 텍스트.
    fact_vector.to_text()를 base로 danger_flags 키워드를 추가.
    """
    base = query_input.fact_vector.to_text()
    return enrich_query(base, danger_flags)
