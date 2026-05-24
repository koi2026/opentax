"""
골든케이스 법적 의존성 메타데이터.

rag_golden_cases.py는 수정하지 않는다.
법령 개정 시 detect_law_changes.py가 이 파일을 참조해
영향받는 케이스를 자동으로 추출한다.

sensitivity:
  high   — 법 개정 시 expected_verdict 자체가 바뀔 수 있음 (일몰 조항, 기준금액, 세율)
  medium — 요건 판단에 영향, verdict는 유지될 수도 있음
  low    — 파이프라인 동작 검증용, 법 개정 영향 거의 없음

category:
  law_sensitive       — 법령 개정에 따라 expected_verdict가 바뀔 수 있음
  pipeline_invariant  — L2 차단/confirmation gate/phantom citation 등 코드 동작 검증용
"""
from __future__ import annotations

from typing import TypedDict


class LegalDep(TypedDict):
    case_id: str
    category: str            # "law_sensitive" | "pipeline_invariant"
    sensitivity: str         # "high" | "medium" | "low"
    legal_deps: list[str]    # TARGET_LAWS의 law["name"] 값과 일치해야 함
    notes: str               # 개정 시 어떤 판단이 바뀌는지 한 줄 설명


GOLDEN_CASE_LEGAL_DEPS: list[LegalDep] = [
    {
        "case_id": "CASE-01",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§89 1세대1주택, §154 거주요건 2년. 거주요건 폐지/변경 시 verdict 변동 가능.",
    },
    {
        "case_id": "CASE-02",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§89 고가주택 12억 기준. 기준금액 변경 시 verdict 즉시 flip.",
    },
    {
        "case_id": "CASE-03",
        "category": "pipeline_invariant",
        "sensitivity": "low",
        "legal_deps": [],
        "notes": "L2 blocked_at_l2 검증. 이월과세 필수 필드 누락 → 차단 동작 테스트.",
    },
    {
        "case_id": "CASE-04",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§155① 일시적2주택 3년 기한. 기한 변경(예: 2년→1년) 시 verdict 변동.",
    },
    {
        "case_id": "CASE-05",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§155② 상속주택 5년 기간. 기간 변경 시 verdict 변동.",
    },
    {
        "case_id": "CASE-06",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["소득세법"],
        "notes": "§104 다주택 중과 +20%. 중과세율 한시배제 종료(2026-05-09) 후 verdict 유지되지만 세율 변동.",
    },
    {
        "case_id": "CASE-07",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["소득세법"],
        "notes": "§104 3주택 중과 +30%. 한시배제 종료 후 영향.",
    },
    {
        "case_id": "CASE-08",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "§104 비조정지역 2주택. 지역 구분 기준 변경 시 verdict 변동.",
    },
    {
        "case_id": "CASE-09",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "§104 단기세율 1년 미만 70%. 세율 변경 시 영향.",
    },
    {
        "case_id": "CASE-10",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "§104 단기세율 1~2년 60%. 세율 변경 시 영향.",
    },
    {
        "case_id": "CASE-11",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§155의3 상생임대 일몰(2024-12-31 → 연장 가능). 일몰 종료 시 verdict 즉시 flip.",
    },
    {
        "case_id": "CASE-12",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§155의3 상생임대 임대료 5% 기준. 기준 변경 시 verdict 변동.",
    },
    {
        "case_id": "CASE-13",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "§97의2 이월과세 5년. 기간 변경 시 verdict 변동.",
    },
    {
        "case_id": "CASE-14",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "§97의2 이월과세 기간 경과(11년). 기간 변경 시 verdict 변동.",
    },
    {
        "case_id": "CASE-15",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "비거주자 과세. 조약 등 외부 변수 연동.",
    },
    {
        "case_id": "CASE-16",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["소득세법"],
        "notes": "§89 12억 경계값. 기준금액 변경 시 verdict 즉시 flip — 최우선 모니터링 대상.",
    },
    {
        "case_id": "CASE-17",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["소득세법"],
        "notes": "§89 12억 초과 고가주택. 기준금액 변경 시 verdict 변동 — 최우선 모니터링 대상.",
    },
    {
        "case_id": "CASE-18",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§155 동거봉양 합가 특례. 요건 변경 시 verdict 변동.",
    },
    {
        "case_id": "CASE-19",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "§104 분양권 단기세율 70%. 분양권 세율 별도 규정 개정 시 영향.",
    },
    {
        "case_id": "CASE-20",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "입주권 양도 과세. 입주권 정의 또는 과세방법 변경 시 영향.",
    },
    {
        "case_id": "CASE-21",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법", "소득세법 시행령"],
        "notes": "§155② 상속주택 5년 경과 후 일반과세. 상속주택 규정 변경 시 영향.",
    },
    {
        "case_id": "CASE-22",
        "category": "pipeline_invariant",
        "sensitivity": "low",
        "legal_deps": [],
        "notes": "L2 차단 — 양도가액 누락. 코드 동작 검증.",
    },
    {
        "case_id": "CASE-23",
        "category": "pipeline_invariant",
        "sensitivity": "low",
        "legal_deps": [],
        "notes": "L2 차단 — 일시적2주택 취득일 누락. 코드 동작 검증.",
    },
    {
        "case_id": "CASE-24",
        "category": "pipeline_invariant",
        "sensitivity": "low",
        "legal_deps": [],
        "notes": "L2 차단 — 입주권 관리처분인가일 누락. 코드 동작 검증.",
    },
    {
        "case_id": "CASE-25",
        "category": "pipeline_invariant",
        "sensitivity": "low",
        "legal_deps": [],
        "notes": "L2 차단 — 상속주택 사망일 누락. 코드 동작 검증.",
    },
    {
        "case_id": "CASE-26",
        "category": "pipeline_invariant",
        "sensitivity": "low",
        "legal_deps": [],
        "notes": "Confirmation gate 차단. 코드 동작 검증.",
    },
    {
        "case_id": "CASE-27",
        "category": "pipeline_invariant",
        "sensitivity": "low",
        "legal_deps": [],
        "notes": "Confirmation gate 통과. 코드 동작 검증.",
    },
    {
        "case_id": "CASE-28",
        "category": "law_sensitive",
        "sensitivity": "medium",
        "legal_deps": ["소득세법"],
        "notes": "§101 특수관계자 부당행위계산부인. expert_review_signals 생성 검증.",
    },
    {
        "case_id": "CASE-29",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["조세특례제한법", "조세특례제한법 시행령"],
        "notes": "조특법 §99의4 농어촌주택 일몰 조항. 일몰 종료 시 verdict 즉시 flip.",
    },
    {
        "case_id": "CASE-30",
        "category": "law_sensitive",
        "sensitivity": "high",
        "legal_deps": ["조세특례제한법"],
        "notes": "조특법 §99의4 요건 미충족. 일몰 종료 시 영향.",
    },
]


def get_deps_by_law(law_name: str) -> list[LegalDep]:
    """특정 법령에 의존하는 law_sensitive 케이스 목록 반환."""
    return [
        d for d in GOLDEN_CASE_LEGAL_DEPS
        if d["category"] == "law_sensitive"
        and any(law_name in dep for dep in d["legal_deps"])
    ]


def get_high_sensitivity_cases() -> list[LegalDep]:
    """sensitivity=high 케이스 목록 반환."""
    return [d for d in GOLDEN_CASE_LEGAL_DEPS if d["sensitivity"] == "high"]


def summary() -> dict:
    total = len(GOLDEN_CASE_LEGAL_DEPS)
    law_sensitive = sum(1 for d in GOLDEN_CASE_LEGAL_DEPS if d["category"] == "law_sensitive")
    pipeline_invariant = total - law_sensitive
    high = sum(1 for d in GOLDEN_CASE_LEGAL_DEPS if d["sensitivity"] == "high")
    return {
        "total": total,
        "law_sensitive": law_sensitive,
        "pipeline_invariant": pipeline_invariant,
        "high_sensitivity": high,
    }
