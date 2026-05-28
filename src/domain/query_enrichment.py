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


def _load_keyword_map() -> Dict[str, str]:
    """data/config/danger_keyword_map.json에서 키워드 맵을 로드한다. 파일 없으면 빈 dict 반환."""
    path = Path("data/config/danger_keyword_map.json")
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# danger_flag → 삽입할 도메인 키워드 + 조문 번호
# 키워드가 쿼리에 있어야 벡터 검색이 해당 조문 청크를 찾아옴
# 실제 키워드는 data/config/danger_keyword_map.json에서 로드 (template: danger_keyword_map.template.json)
DANGER_KEYWORD_MAP: Dict[str, str] = _load_keyword_map()


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
