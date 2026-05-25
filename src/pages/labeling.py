"""
전문가 레이블링 페이지 — 비개발자 세법 전문가용.
골든셋 케이스를 검토하고 verdict·근거를 확인·수정한다.
판단 로직 없음. 저장·표시·내보내기 전용.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st

st.set_page_config(page_title="전문가 검토", page_icon="⚖️", layout="wide")

_ROOT = Path(__file__).parent.parent.parent
_GOLDEN_PATH = _ROOT / "data" / "golden" / "synthetic_comprehensive.json"
_LABELS_PATH = _ROOT / "data" / "golden" / "expert_labels.json"

_VERDICT_OPTIONS = ["비과세", "고가주택", "일반과세", "중과", "단기세율", "감면", "사실관계부족"]
_CONFIDENCE_OPTIONS = ["높음", "보통", "낮음 (재검토 필요)"]

_VERDICT_COLOR = {
    "비과세": "🟢", "감면": "🔵", "중과": "🔴",
    "일반과세": "🟠", "단기세율": "🔴", "고가주택": "🟠",
    "사실관계부족": "⚫",
}

_FACT_LABELS = {
    "property_type": "부동산 유형",
    "acquisition_date": "취득일",
    "transfer_date": "양도일",
    "acquisition_price": "취득가액",
    "transfer_price": "양도가액",
    "household_house_count": "세대 주택 수",
    "residence_years": "실거주 기간(년)",
    "is_adjustment_area_at_transfer": "양도 시 조정대상지역",
    "is_adjustment_area_at_acquisition": "취득 시 조정대상지역",
    "acquisition_reason": "취득 원인",
    "holding_years": "보유 기간(년)",
}


# ── 데이터 로드/저장 ────────────────────────────────────────────────────────────

@st.cache_data(ttl=0)
def _load_cases() -> list[dict]:
    if not _GOLDEN_PATH.exists():
        return []
    with open(_GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_labels() -> dict[str, dict]:
    if not _LABELS_PATH.exists():
        return {}
    with open(_LABELS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_labels(labels: dict[str, dict]) -> None:
    _LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)


def _fmt_money(v) -> str:
    if not v:
        return "—"
    try:
        v = int(v)
        if v >= 100_000_000:
            return f"{v / 100_000_000:,.1f}억원"
        if v >= 10_000:
            return f"{v / 10_000:,.0f}만원"
        return f"{v:,}원"
    except Exception:
        return str(v)


def _fmt_date(v) -> str:
    s = str(int(v)) if v else ""
    if len(s) == 8:
        return f"{s[:4]}년 {s[4:6]}월 {s[6:]}일"
    return s or "—"


def _fmt_fact(key: str, val) -> str:
    if val is None:
        return "—"
    if key in ("acquisition_price", "transfer_price"):
        return _fmt_money(val)
    if key in ("acquisition_date", "transfer_date"):
        return _fmt_date(val)
    if key in ("residence_years", "holding_years"):
        return f"{float(val):.1f}년"
    if isinstance(val, bool):
        return "예" if val else "아니오"
    return str(val)


# ── 사이드바 필터 ──────────────────────────────────────────────────────────────

def _sidebar(cases: list[dict], labels: dict[str, dict]) -> list[dict]:
    st.sidebar.title("⚖️ 전문가 검토")
    st.sidebar.markdown("---")

    total = len(cases)
    reviewed = sum(1 for c in cases if c["case_id"] in labels and labels[c["case_id"]].get("reviewed"))
    st.sidebar.metric("전체 케이스", total)
    st.sidebar.metric("검토 완료", reviewed, delta=f"{reviewed/total*100:.0f}%" if total else "0%")
    st.sidebar.progress(reviewed / total if total else 0)

    st.sidebar.markdown("---")
    st.sidebar.subheader("필터")

    status_filter = st.sidebar.radio(
        "검토 상태",
        ["전체", "미검토", "검토완료", "재검토 필요"],
        index=0,
    )

    verdict_filter = st.sidebar.multiselect(
        "AI 예상 verdict",
        options=_VERDICT_OPTIONS + ["없음"],
        default=[],
    )

    search = st.sidebar.text_input("케이스 설명 검색", placeholder="예: 상속주택, 일시적2주택...")

    st.sidebar.markdown("---")
    if st.sidebar.button("📥 CSV 내보내기", use_container_width=True):
        _export_csv(cases, labels)

    filtered = cases
    if status_filter == "미검토":
        filtered = [c for c in filtered if c["case_id"] not in labels or not labels[c["case_id"]].get("reviewed")]
    elif status_filter == "검토완료":
        filtered = [c for c in filtered if c["case_id"] in labels and labels[c["case_id"]].get("reviewed")]
    elif status_filter == "재검토 필요":
        filtered = [c for c in filtered if c["case_id"] in labels and labels[c["case_id"]].get("confidence") == "낮음 (재검토 필요)"]

    if verdict_filter:
        def _match_verdict(c):
            v = c.get("expected_verdict") or "없음"
            return v in verdict_filter
        filtered = [c for c in filtered if _match_verdict(c)]

    if search:
        filtered = [c for c in filtered if search.lower() in (c.get("description") or "").lower()
                    or search in str(c.get("tags", []))]

    return filtered


def _export_csv(cases: list[dict], labels: dict[str, dict]) -> None:
    lines = ["case_id,설명,AI_verdict,전문가_verdict,신뢰도,메모,검토일시"]
    for c in cases:
        cid = c["case_id"]
        lbl = labels.get(cid, {})
        row = [
            cid,
            (c.get("description") or "").replace(",", " "),
            c.get("expected_verdict") or "",
            lbl.get("expert_verdict") or "",
            lbl.get("confidence") or "",
            (lbl.get("notes") or "").replace(",", " ").replace("\n", " "),
            lbl.get("reviewed_at") or "",
        ]
        lines.append(",".join(row))
    csv_data = "\n".join(lines)
    st.sidebar.download_button(
        "💾 다운로드",
        data=csv_data.encode("utf-8-sig"),
        file_name=f"expert_labels_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ── 케이스 카드 ────────────────────────────────────────────────────────────────

def _case_card(c: dict, lbl: dict | None, idx: int) -> None:
    cid = c["case_id"]
    desc = c.get("description") or cid
    ai_verdict = c.get("expected_verdict") or "없음"
    tags = c.get("tags") or []

    reviewed = lbl.get("reviewed") if lbl else False
    expert_verdict = lbl.get("expert_verdict") if lbl else None
    status_icon = "✅" if reviewed else ("⚠️" if lbl else "📋")

    verdict_icon = _VERDICT_COLOR.get(ai_verdict, "⚪")
    label = f"{status_icon} [{idx+1}] {verdict_icon} {ai_verdict}  |  {desc[:60]}"
    with st.expander(label, expanded=False):
        _case_detail(c, lbl)


def _case_detail(c: dict, lbl: dict | None) -> None:
    cid = c["case_id"]
    fact = c.get("fact_json") or {}
    ai_verdict = c.get("expected_verdict") or "없음"
    tags = c.get("tags") or []
    boundary = c.get("boundary_type") or ""

    col_fact, col_review = st.columns([1, 1], gap="large")

    with col_fact:
        st.markdown("#### 📋 사실관계")
        for key, label in _FACT_LABELS.items():
            val = fact.get(key)
            if val is not None:
                st.markdown(f"- **{label}**: {_fmt_fact(key, val)}")
        if tags:
            st.markdown(f"- **태그**: `{'` `'.join(tags)}`")
        if boundary:
            st.markdown(f"- **경계 유형**: `{boundary}`")

        st.markdown("#### 🤖 AI 예상 결과")
        verdict_color = {"비과세": "green", "감면": "blue", "중과": "red",
                         "일반과세": "orange", "단기세율": "red", "고가주택": "orange",
                         "사실관계부족": "gray"}.get(ai_verdict, "gray")
        st.markdown(f":{verdict_color}[**{ai_verdict}**]")

        gold_ids = c.get("gold_chunk_ids") or []
        if gold_ids:
            with st.expander(f"참조 조문 ID ({len(gold_ids)}건)"):
                for gid in gold_ids:
                    st.code(gid, language=None)

    with col_review:
        st.markdown("#### ✏️ 전문가 검토")

        lbl = lbl or {}
        default_verdict = lbl.get("expert_verdict") or ai_verdict
        verdict_idx = _VERDICT_OPTIONS.index(default_verdict) if default_verdict in _VERDICT_OPTIONS else 0

        expert_verdict = st.selectbox(
            "판단 결과",
            options=_VERDICT_OPTIONS,
            index=verdict_idx,
            key=f"verdict_{cid}",
        )

        conf_idx = _CONFIDENCE_OPTIONS.index(lbl["confidence"]) if lbl.get("confidence") in _CONFIDENCE_OPTIONS else 0
        confidence = st.radio(
            "확신도",
            options=_CONFIDENCE_OPTIONS,
            index=conf_idx,
            horizontal=True,
            key=f"conf_{cid}",
        )

        notes = st.text_area(
            "근거 및 메모 (조문 번호, 판단 이유 등)",
            value=lbl.get("notes") or "",
            height=120,
            placeholder="예: 소득세법 제89조 1항 3호, 2년 보유 요건 미충족으로 비과세 불가...",
            key=f"notes_{cid}",
        )

        reviewed = st.checkbox(
            "검토 완료 (저장 시 완료 처리됨)",
            value=lbl.get("reviewed") or False,
            key=f"reviewed_{cid}",
        )

        disagreement = expert_verdict != ai_verdict and ai_verdict != "없음"
        if disagreement:
            st.warning(f"AI 예상({ai_verdict})과 다릅니다. 근거를 메모에 기록해 주세요.")

        if st.button("💾 저장", key=f"save_{cid}", type="primary", use_container_width=True):
            labels = _load_labels()
            labels[cid] = {
                "expert_verdict": expert_verdict,
                "confidence": confidence,
                "notes": notes,
                "reviewed": reviewed,
                "ai_verdict": ai_verdict,
                "disagreement": disagreement,
                "reviewed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            _save_labels(labels)
            st.success("저장되었습니다.")
            st.rerun()


# ── 신규 케이스 입력 ───────────────────────────────────────────────────────────

def _new_case_form() -> None:
    st.markdown("---")
    with st.expander("➕ 신규 케이스 직접 입력", expanded=False):
        st.info("세법 전문가가 직접 케이스를 추가합니다. 추가된 케이스는 골든셋에 반영됩니다.")

        col1, col2 = st.columns(2)
        with col1:
            desc = st.text_input("케이스 설명 *", placeholder="예: 상속주택 + 일시적2주택 중첩")
            property_type = st.selectbox("부동산 유형 *", ["아파트", "단독주택", "다세대", "오피스텔", "토지", "상가"])
            acq_date = st.text_input("취득일 (YYYYMMDD) *", placeholder="20200101")
            trans_date = st.text_input("양도일 (YYYYMMDD) *", placeholder="20240101")
            acq_price = st.number_input("취득가액 (원)", min_value=0, step=10_000_000)
            trans_price = st.number_input("양도가액 (원)", min_value=0, step=10_000_000)

        with col2:
            house_count = st.number_input("세대 주택 수", min_value=1, max_value=10, value=1)
            residence_years = st.number_input("실거주 기간(년)", min_value=0.0, max_value=50.0, step=0.5)
            is_adj_acq = st.checkbox("취득 시 조정대상지역")
            is_adj_trans = st.checkbox("양도 시 조정대상지역")
            acq_reason = st.selectbox("취득 원인", ["매매", "상속", "증여", "신축", "기타"])
            expected_verdict = st.selectbox("전문가 판단 결과 *", _VERDICT_OPTIONS)
            notes = st.text_area("근거 (조문, 이유)", height=80)

        if st.button("케이스 추가", type="primary"):
            if not desc or not acq_date or not trans_date:
                st.error("필수 항목을 입력해 주세요.")
                return

            import hashlib, uuid
            new_id = "exp_" + hashlib.md5(f"{desc}{acq_date}{trans_date}".encode()).hexdigest()[:8]
            new_case = {
                "case_id": new_id,
                "description": desc,
                "fact_json": {
                    "property_type": property_type,
                    "acquisition_date": acq_date,
                    "transfer_date": trans_date,
                    "acquisition_price": int(acq_price),
                    "transfer_price": int(trans_price),
                    "household_house_count": int(house_count),
                    "residence_years": float(residence_years),
                    "is_adjustment_area_at_acquisition": is_adj_acq,
                    "is_adjustment_area_at_transfer": is_adj_trans,
                    "acquisition_reason": acq_reason,
                },
                "expected_verdict": expected_verdict,
                "boundary_type": "expert_added",
                "tags": ["전문가입력"],
                "registry_deps": [],
                "registry_snapshot": {},
                "gold_chunk_ids": [],
            }

            cases = _load_cases()
            if any(c["case_id"] == new_id for c in cases):
                st.warning("이미 유사한 케이스가 존재합니다.")
                return

            cases.append(new_case)
            with open(_GOLDEN_PATH, "w", encoding="utf-8") as f:
                json.dump(cases, f, ensure_ascii=False, indent=2)

            labels = _load_labels()
            labels[new_id] = {
                "expert_verdict": expected_verdict,
                "confidence": "높음",
                "notes": notes,
                "reviewed": True,
                "ai_verdict": expected_verdict,
                "disagreement": False,
                "reviewed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "expert_added",
            }
            _save_labels(labels)

            st.success(f"케이스 추가 완료: {new_id}")
            st.cache_data.clear()
            st.rerun()


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.title("⚖️ 전문가 검토 패널")
    st.caption("세법 전문가 전용 · 골든셋 케이스 검토 및 레이블링")

    cases = _load_cases()
    if not cases:
        st.error("골든셋 파일을 찾을 수 없습니다.")
        return

    labels = _load_labels()
    filtered = _sidebar(cases, labels)

    if not filtered:
        st.info("조건에 맞는 케이스가 없습니다.")
        _new_case_form()
        return

    st.markdown(f"**{len(filtered)}건** 표시 중 (전체 {len(cases)}건)")
    st.markdown("---")

    for idx, c in enumerate(filtered):
        lbl = labels.get(c["case_id"])
        _case_card(c, lbl, idx)

    _new_case_form()


main()
