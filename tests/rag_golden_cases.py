"""
RAG 파이프라인 골든 테스트 케이스 — RAG 엔진 팀 end-to-end 검증용

사용법:
    from tests.fixtures.rag_golden_cases import RAG_GOLDEN_CASES
    from app.domain.rag.query_input import RAGQueryInput

    for case in RAG_GOLDEN_CASES:
        query = RAGQueryInput.from_fact_ledger(
            fact_ledger=case["fact_ledger"],
            owner_profile=case["owner_profile"],
            user_property=case["user_property"],
        )
        result = await run_rag_pipeline(query, retriever, llm_fn)
        # result와 case["expected"] 비교

케이스 목록:
    CASE-01  1세대1주택 단순 비과세
    CASE-02  고가주택 (15억) 조건부비과세 — 초과분 과세
    CASE-03  이월과세 L2 차단 — blocked_at_l2=True 검증
    CASE-04  일시적 2주택 비과세 — 3년 이내 양도 충족
    CASE-05  상속주택 경로 A — 일반주택 양도 비과세
    CASE-06  2주택 조정대상지역 양도 → 중과
    CASE-07  3주택 조정대상지역 양도 → 중과 (+30%)
    CASE-08  2주택 비조정지역 양도 → 일반과세
    CASE-09  보유 10개월 → 단기세율 (70%)
    CASE-10  보유 18개월 → 단기세율 (60%)
    CASE-11  상생임대 요건 충족 → 거주요건 면제, 비과세
    CASE-12  상생임대 임대료 인상률 5% 초과 → 요건 미충족, 일반과세
    CASE-13  배우자 증여 5년 이내 양도 → 이월과세 적용, 일반과세
    CASE-14  배우자 증여 11년 후 양도 → 이월과세 기간 경과, 비과세
    CASE-15  해외 거주자 비거주자 양도 → 일반과세
    CASE-16  양도가액 정확히 12억 → 비과세 (경계값)
    CASE-17  양도가액 12억1만원 → 고가주택
    CASE-18  동거봉양 합가 일시적 2주택 → 비과세
    CASE-19  분양권 1년 미만 양도 → 단기세율 (70%)
    CASE-20  분양권→입주권 전환 후 입주권 양도 → 일반과세
    CASE-21  상속주택 자체 양도 (5년 이후) → 일반과세
    CASE-22  양도가액 누락 → blocked_at_l2=True
    CASE-23  일시적2주택 신규주택 취득일 누락 → blocked_at_l2=True
    CASE-24  입주권 관리처분인가일 누락 → blocked_at_l2=True
    CASE-25  상속주택 사망일 누락 → blocked_at_l2=True
    CASE-26  confirmed={} → blocked_at_confirmation=True
    CASE-27  confirmed 4개 모두 True → 정상 진행
    CASE-28  특수관계자 거래 → 경고 포함, expert_review_signals
    CASE-29  농어촌주택 조특법 §99의4 → 주택수 제외, 비과세
    CASE-30  농어촌주택 과밀억제권역 → 요건 미충족, 일반과세
"""

RAG_GOLDEN_CASES = [

    # ────────────────────────────────────────────────────────────────────
    # CASE-01: 1세대 1주택 단순 비과세
    # 조건: 아파트, 매매취득, 1주택, 조정대상지역, 2년 이상 거주, 12억 이하
    # 예상: verdict=비과세, confidence≥0.85, blocked_at_l2=False
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-01",
        "title": "1세대 1주택 단순 비과세",
        "description": "가장 기본적인 비과세 케이스. 조정대상지역 아파트, 2년 이상 거주.",
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
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
            "verdict": "비과세",
            "confidence_min": 0.85,
            "key_article": "소득세법 시행령 제154조",
            "notes": "조정대상지역 취득 → 2년 거주요건 충족. 12억 이하 → 전액 비과세.",
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-02: 고가주택 (양도가액 15억) 조건부비과세
    # 조건: 1주택, 2년 거주 충족, 양도가액 15억 → 12억 초과분은 과세
    # 예상: verdict=조건부비과세, L5에서 고가주택 경고 추가
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-02",
        "title": "고가주택 조건부비과세 (양도가액 15억)",
        "description": "비과세 요건은 충족하지만 12억 초과분(3억)에 대해 과세되는 케이스.",
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2016-09-01",
            "transfer_date": "2025-08-20",
            "acquisition_price": 700000000,
            "sale_price_total": 1500000000,       # 15억 → 고가주택
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
            "verdict": "고가주택",
            "confidence_min": 0.75,
            "key_article": "소득세법 제89조 제1항 제3호",
            "notes": (
                "양도가액 15억 → 12억 초과 3억에 대해 과세. "
                "장기보유특별공제 표2(10년 이상 보유+거주) 적용 가능. "
                "L5에서 고가주택 경고 포함 예상."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-03: 이월과세 L2 차단
    # 조건: 배우자에게서 증여받은 아파트, 증여일로부터 3년 이내 양도
    #        원취득일/원취득가액 미확인 상태 → L2 critical 차단
    # 예상: blocked_at_l2=True (원취득일 미확인이 critical)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-03",
        "title": "이월과세 L2 차단 — 배우자 증여 후 3년 이내 양도",
        "description": (
            "배우자에게서 증여받은 아파트를 증여일로부터 3년 이내 양도. "
            "이월과세(§97의2) 적용 여부 판단에 필요한 증여자 원취득일/원취득가액이 없음 → L2 차단."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "증여",
            "acquisition_date": "2022-06-15",     # 증여일
            "transfer_date": "2025-09-10",         # 증여 후 약 3.2년 → 5년 이내
            "acquisition_price": 900000000,        # 증여 당시 신고가액
            "sale_price_total": 1100000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 3.2,
            "residence_period_years": 2.5,
            "joint_ownership_yn": False,
            "gift_date": "2022-06-15",
        },
        "fact_ledger": {
            "is_gift_from_spouse_or_lineal": True,
            # 의도적으로 original_donor_acquisition_date / original_donor_acquisition_price 없음
            # → L2 check_facts()가 critical missing으로 차단해야 함
        },
        "expected": {
            "blocked_at_l2": True,
            "verdict": "needs_verification",
            "missing_fact_contains": "original_donor_acquisition_date",
            "notes": (
                "증여자 원취득일/원취득가액 없이 이월과세 세액 계산 불가. "
                "blocked_at_l2=True 여야 하고 missing_facts에 "
                "original_donor_acquisition_date/original_donor_acquisition_price 포함 필수."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-04: 일시적 2주택 비과세 — 종전주택 3년 이내 양도 충족
    # 조건: 종전주택 보유 중 신규주택 취득, 3년 이내 종전주택 양도
    #        신규주택 취득일: 2023-05-01 → 양도기한: 2026-05-01
    #        실제 양도일: 2025-10-15 → 기한 내 충족
    # 예상: verdict=비과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-04",
        "title": "일시적 2주택 비과세 — 3년 이내 종전주택 양도",
        "description": (
            "종전주택 보유 중 신규주택 취득(2023-05-01). "
            "3년 이내(2026-05-01 전)에 종전주택 양도(2025-10-15) → 비과세 요건 충족."
        ),
        "owner_profile": {
            "household_house_count": 2,            # 일시적 2주택 상태
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2017-03-20",      # 종전주택 취득
            "transfer_date": "2025-10-15",         # 종전주택 양도 (기한 내)
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
            "temp_new_acquisition_date": "2023-05-01",   # 신규주택 취득일
            "temp_old_must_sell_by": "2026-05-01",       # 종전주택 양도 기한
            "temp_new_is_adjustment_area": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "비과세",
            "confidence_min": 0.80,
            "key_article": "소득세법 시행령 제155조 제1항",
            "notes": (
                "신규주택 비조정지역 취득 → 3년 이내 양도 기준 적용. "
                "2025-10-15 < 2026-05-01 → 기한 내 충족. "
                "종전주택 2년 거주 요건 없음(비조정지역 취득 당시)."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-05: 상속주택 경로 A — 일반주택 양도 비과세
    # 조건: 1주택 보유 중 상속으로 주택 추가 취득 (상속주택 포함 2주택)
    #        상속개시일로부터 5년 이내 → 상속주택은 주택 수에서 제외
    #        일반주택(원래 보유하던 주택) 양도 → 1주택으로 간주 비과세
    # 예상: verdict=비과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-05",
        "title": "상속주택 경로 A — 일반주택 양도 비과세",
        "description": (
            "본인 소유 1주택 보유 중 부모 사망으로 상속주택 취득(2022-11-30). "
            "상속개시 5년 이내(2027-11-30 전)에 일반주택 양도(2025-11-10) → 상속주택 제외 1주택 비과세."
        ),
        "owner_profile": {
            "household_house_count": 2,            # 일반주택 + 상속주택
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2018-07-01",      # 일반주택 취득
            "transfer_date": "2025-11-10",         # 일반주택 양도
            "acquisition_price": 350000000,
            "sale_price_total": 750000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 7.4,
            "residence_period_years": 3.0,
            "joint_ownership_yn": False,
            "death_date": "2022-11-30",            # 상속개시일
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            # 상속주택 정보 — acquisition_cause가 아닌 별도 플래그로 관리
            # user_property의 acquisition_cause는 "매매"(일반주택 기준)
            # 상속주택은 별도 property로 존재하나 여기서는 소유주 보유주택수(2)로 반영
            "inherited_as_only_house": False,      # 상속 당시 1주택자 아님 (일반주택 보유 중)
            "deceased_same_household": False,      # 피상속인과 별거
            "selling_inherited_house": False,      # 일반주택 양도 (경로 A)
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "비과세",
            "confidence_min": 0.80,
            "key_article": "소득세법 시행령 제155조 제2항",
            "notes": (
                "상속개시 후 5년 이내 일반주택 양도 → 상속주택 주택 수 제외. "
                "1주택으로 간주 비과세. "
                "일반주택 조정대상지역 취득 → 2년 거주 충족(3.0년). "
                "양도가액 7.5억 → 12억 이하 → 전액 비과세."
            ),
        },
    },

    # ====================================================================
    # 다주택 중과 (CASE-06 ~ 08)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-06: 2주택 조정대상지역 양도 → 중과
    # 조건: 2주택 보유, 조정대상지역 주택 양도, 중과 유예 기간 종료 후
    # 예상: verdict=중과 (+20%)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-06",
        "title": "2주택 조정대상지역 양도 → 중과",
        "description": (
            "2주택 보유자가 조정대상지역 아파트를 양도. "
            "중과 유예 기간(~2025-05-09) 종료 후 양도 → 기본세율 +20% 중과 적용."
        ),
        "owner_profile": {
            "household_house_count": 2,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2017-06-01",
            "transfer_date": "2025-09-10",
            "acquisition_price": 500000000,
            "sale_price_total": 900000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": True,   # 양도 시점도 조정대상지역
            "holding_period_years": 8.3,
            "residence_period_years": 1.0,         # 거주요건 미충족 → 비과세 배제
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "중과",
            "confidence_min": 0.80,
            "key_article": "소득세법 제104조 제7항",
            "notes": (
                "2주택 + 양도 시점 조정대상지역 → 기본세율 +20% 중과. "
                "거주기간 1년으로 1세대1주택 비과세 요건(2년 거주) 미충족. "
                "중과 유예 종료(2025-05-09) 이후 양도."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-07: 3주택 조정대상지역 양도 → 중과 (+30%)
    # 조건: 3주택 보유, 조정대상지역 주택 양도
    # 예상: verdict=중과 (기본세율 +30%)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-07",
        "title": "3주택 조정대상지역 양도 → 중과 (+30%)",
        "description": (
            "3주택 보유자가 조정대상지역 아파트를 양도. "
            "기본세율 +30% 중과 적용."
        ),
        "owner_profile": {
            "household_house_count": 3,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2016-03-15",
            "transfer_date": "2025-10-20",
            "acquisition_price": 400000000,
            "sale_price_total": 850000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": True,
            "holding_period_years": 9.6,
            "residence_period_years": 0.5,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "중과",
            "confidence_min": 0.80,
            "key_article": "소득세법 제104조 제7항",
            "notes": (
                "3주택 + 양도 시점 조정대상지역 → 기본세율 +30% 중과. "
                "3주택 이상은 2주택(+20%)보다 높은 세율 적용. "
                "장기보유특별공제 배제(중과 대상)."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-08: 2주택이나 한 채는 지방 소도시(비조정) → 일반과세
    # 조건: 2주택 보유, 양도 주택이 비조정대상지역
    # 예상: verdict=일반과세 (중과 요건 불충족)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-08",
        "title": "2주택 비조정지역 양도 → 일반과세",
        "description": (
            "2주택 보유자이지만 양도하는 주택이 비조정대상지역(지방 소도시) → "
            "다주택 중과 요건(조정대상지역) 불충족 → 일반과세."
        ),
        "owner_profile": {
            "household_house_count": 2,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2015-08-10",
            "transfer_date": "2025-08-05",
            "acquisition_price": 150000000,
            "sale_price_total": 300000000,
            "adjustment_area_at_acquisition": False,  # 취득 시 비조정
            "adjustment_area_at_transfer": False,      # 양도 시 비조정
            "holding_period_years": 10.0,
            "residence_period_years": 0.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "일반과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 제104조 제7항",
            "notes": (
                "양도 시점 비조정대상지역 → 다주택 중과 대상 아님. "
                "기본세율(6~45%) 적용. "
                "보유 10년 → 장기보유특별공제 30% 적용 가능."
            ),
        },
    },

    # ====================================================================
    # 단기세율 (CASE-09 ~ 10)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-09: 보유 10개월 → 단기세율 70%
    # 조건: 주택 취득 후 1년 미만 양도
    # 예상: verdict=단기세율 (70%)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-09",
        "title": "보유 10개월 → 단기세율 (70%)",
        "description": (
            "아파트 취득 후 10개월 만에 양도 → 1년 미만 보유 → 70% 단일세율 적용."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2024-07-01",
            "transfer_date": "2025-05-01",         # 10개월 후
            "acquisition_price": 600000000,
            "sale_price_total": 700000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 0.83,          # 약 10개월
            "residence_period_years": 0.5,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "단기세율",
            "confidence_min": 0.85,
            "key_article": "소득세법 제104조 제1항 제1호",
            "notes": (
                "보유기간 1년 미만(10개월) → 70% 단일세율 적용. "
                "비과세 요건(2년 보유) 미충족. "
                "장기보유특별공제 없음."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-10: 보유 18개월 → 단기세율 60%
    # 조건: 주택 취득 후 1년 이상 2년 미만 양도
    # 예상: verdict=단기세율 (60%)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-10",
        "title": "보유 18개월 → 단기세율 (60%)",
        "description": (
            "아파트 취득 후 18개월 만에 양도 → 1년 이상 2년 미만 보유 → 60% 단일세율 적용."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2024-01-15",
            "transfer_date": "2025-07-15",         # 18개월 후
            "acquisition_price": 550000000,
            "sale_price_total": 650000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 1.5,
            "residence_period_years": 1.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "단기세율",
            "confidence_min": 0.85,
            "key_article": "소득세법 제104조 제1항 제2호",
            "notes": (
                "보유기간 1년 이상 2년 미만(18개월) → 60% 단일세율 적용. "
                "비과세 요건(2년 보유) 미충족. "
                "장기보유특별공제 없음."
            ),
        },
    },

    # ====================================================================
    # 상생임대 (CASE-11 ~ 12)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-11: 상생임대 요건 충족 → 거주요건 면제, 비과세
    # 조건: 조정대상지역, 상생임대 계약(임대료 인상률 5% 이하, 2년 이상 임대)
    #        → 2년 거주요건 면제 → 비과세
    # 예상: verdict=비과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-11",
        "title": "상생임대 요건 충족 → 거주요건 면제, 비과세",
        "description": (
            "조정대상지역 아파트. 직전 임대차 계약 대비 임대료 인상률 5% 이하, "
            "2년 이상 임대(상생임대 요건 충족) → 거주요건 면제 → 비과세."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2020-05-01",
            "transfer_date": "2025-06-01",
            "acquisition_price": 700000000,
            "sale_price_total": 950000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": True,
            "holding_period_years": 5.1,
            "residence_period_years": 0.5,         # 실거주 0.5년 — 통상 요건 미충족
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "sangsaeng_rental": {
                "is_sangsaeng_rental": True,
                "rent_increase_rate": 0.04,        # 4% 인상 → 5% 이하 요건 충족
                "lease_start_date": "2022-06-01",
                "lease_end_date": "2024-06-01",    # 2년 임대 충족
                "residence_requirement_waived": True,
            },
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "비과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 시행령 제155조의3",
            "notes": (
                "상생임대 요건 충족(임대료 5% 이하, 2년 이상) → 2년 거주요건 면제. "
                "조정대상지역 취득이어도 거주요건 없이 비과세 가능. "
                "양도가액 9.5억 → 12억 이하 → 전액 비과세."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-12: 상생임대 임대료 인상률 5% 초과 → 요건 미충족, 일반과세
    # 조건: 임대료 인상률 8% → 상생임대 요건 불충족 → 거주요건 면제 없음
    # 예상: verdict=일반과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-12",
        "title": "상생임대 임대료 인상률 5% 초과 → 요건 미충족, 일반과세",
        "description": (
            "조정대상지역 아파트, 임대료 인상률 8%(5% 초과) → 상생임대 요건 불충족. "
            "실거주 1년 → 2년 거주요건 미충족 → 비과세 배제 → 일반과세."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2020-03-01",
            "transfer_date": "2025-04-01",
            "acquisition_price": 680000000,
            "sale_price_total": 900000000,
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": True,
            "holding_period_years": 5.1,
            "residence_period_years": 1.0,         # 거주요건 미충족
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "sangsaeng_rental": {
                "is_sangsaeng_rental": False,      # 요건 불충족
                "rent_increase_rate": 0.08,        # 8% 인상 → 5% 초과
                "residence_requirement_waived": False,
            },
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "일반과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 시행령 제155조의3",
            "notes": (
                "임대료 인상률 8%(5% 초과) → 상생임대 요건 불충족. "
                "거주요건 면제 없음 → 조정대상지역 취득 2년 거주요건 미충족. "
                "비과세 배제 → 1주택이지만 일반과세 적용."
            ),
        },
    },

    # ====================================================================
    # 이월과세 완전 적용 (CASE-13 ~ 14)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-13: 배우자 증여, 증여일로부터 5년 이내 양도 → 이월과세 적용, 일반과세
    # 조건: 배우자 증여, 증여 후 2년 이내 양도 → 이월과세(§97의2) 적용
    #        원취득가액(낮음)으로 재계산 → 양도차익 증가 → 일반과세
    # 예상: verdict=일반과세 (이월과세 적용)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-13",
        "title": "배우자 증여 5년 이내 양도 → 이월과세 적용, 일반과세",
        "description": (
            "배우자로부터 아파트를 증여받아 취득(2022-03-10). "
            "증여일로부터 2년 후(2024-03-10) 양도 → 이월과세(§97의2) 적용. "
            "원취득가액(3억)으로 양도차익 재계산 → 1세대1주택 비과세 배제 → 일반과세."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "증여",
            "acquisition_date": "2022-03-10",      # 증여일 = 취득일
            "transfer_date": "2024-03-10",         # 증여 후 정확히 2년
            "acquisition_price": 850000000,        # 증여 당시 신고가액
            "sale_price_total": 950000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 2.0,
            "residence_period_years": 1.5,
            "joint_ownership_yn": False,
            "gift_date": "2022-03-10",
        },
        "fact_ledger": {
            "is_gift_from_spouse_or_lineal": True,
            "original_donor_acquisition_date": "2012-05-20",   # 증여자 원취득일
            "original_donor_acquisition_price": 300000000,     # 증여자 원취득가액 3억
            "gift_within_iota_period": True,       # 이월과세 기간 이내
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "일반과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 제97조의2",
            "notes": (
                "배우자 증여 후 5년(10년) 이내 양도 → 이월과세 적용. "
                "양도차익 = 양도가액 - 증여자 원취득가액(3억) = 6.5억. "
                "증여세 납부액 차감 가능. "
                "1세대1주택 비과세 판단 시 원취득일(2012년)부터 보유기간 기산."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-14: 배우자 증여, 증여일로부터 11년 후 양도 → 이월과세 기간 경과, 비과세
    # 조건: 배우자 증여 후 11년 경과 → 이월과세 적용 기간(10년) 초과
    #        1주택, 2년 이상 보유 → 비과세
    # 예상: verdict=비과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-14",
        "title": "배우자 증여 11년 후 양도 → 이월과세 기간 경과, 비과세",
        "description": (
            "배우자로부터 아파트를 증여받아 취득(2013-05-01). "
            "증여일로부터 11년 후(2024-05-01) 양도 → 이월과세(§97의2) 적용 기간(10년) 초과. "
            "1주택, 11년 보유, 비조정지역 → 비과세."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "증여",
            "acquisition_date": "2013-05-01",
            "transfer_date": "2024-05-01",
            "acquisition_price": 400000000,
            "sale_price_total": 900000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 11.0,
            "residence_period_years": 5.0,
            "joint_ownership_yn": False,
            "gift_date": "2013-05-01",
        },
        "fact_ledger": {
            "is_gift_from_spouse_or_lineal": True,
            "original_donor_acquisition_date": "2005-08-15",
            "original_donor_acquisition_price": 200000000,
            "gift_within_iota_period": False,      # 이월과세 기간(10년) 초과
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "비과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 제89조 제1항 제3호",
            "notes": (
                "증여 후 11년 경과 → 이월과세(§97의2) 적용 기간(10년) 초과. "
                "증여가액을 취득가액으로 사용. "
                "1주택 11년 보유, 비조정지역(거주요건 없음) → 전액 비과세. "
                "양도가액 9억 → 12억 이하 → 전액 비과세."
            ),
        },
    },

    # ====================================================================
    # 비거주자 (CASE-15)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-15: 해외 거주자(비거주자) 양도 → 일반과세
    # 조건: 해외 거주 2년 이상 → 비거주자 → 1세대1주택 비과세 배제
    #        비거주자 세율(20%) 또는 기본세율 중 큰 것 적용
    # 예상: verdict=일반과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-15",
        "title": "비거주자 양도 → 일반과세",
        "description": (
            "해외에서 3년째 거주 중인 비거주자가 국내 아파트를 양도. "
            "비거주자는 1세대1주택 비과세 규정 적용 대상 아님 → 일반과세."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": True,         # 해외 거주 → 비거주자
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2016-09-01",
            "transfer_date": "2025-08-01",
            "acquisition_price": 450000000,
            "sale_price_total": 800000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 8.9,
            "residence_period_years": 2.0,         # 과거 거주기간 (현재는 해외 체류)
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "overseas_departure_date": "2022-06-01",  # 출국일
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "일반과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 제121조",
            "notes": (
                "비거주자 → 1세대1주택 비과세(§89) 적용 불가. "
                "비거주자 세율 20% 또는 기본세율 중 큰 것 적용. "
                "해외이주 2년 이내 귀국 후 양도 특례(§154①2호) 미해당 — 귀국하지 않음."
            ),
        },
    },

    # ====================================================================
    # 고가주택 경계 (CASE-16 ~ 17)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-16: 양도가액 정확히 12억 → 비과세 (경계값, 초과 아님)
    # 조건: 양도가액 = 12억 정확히 → 고가주택 해당 없음(초과가 아닌 경우)
    # 예상: verdict=비과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-16",
        "title": "양도가액 정확히 12억 → 비과세 (경계값)",
        "description": (
            "1세대1주택, 2년 이상 보유·거주 충족. "
            "양도가액이 정확히 12억원 → 고가주택(12억 초과) 해당 없음 → 전액 비과세."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2018-01-10",
            "transfer_date": "2025-06-10",
            "acquisition_price": 700000000,
            "sale_price_total": 1200000000,        # 정확히 12억
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 7.4,
            "residence_period_years": 2.5,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "비과세",
            "confidence_min": 0.85,
            "key_article": "소득세법 제89조 제1항 제3호",
            "notes": (
                "양도가액 12억 정확히 → '12억 초과' 조건 불충족 → 고가주택 해당 없음. "
                "전액 비과세 적용. "
                "경계값 처리: 초과(>12억)이어야 고가주택 → 12억은 비과세."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-17: 양도가액 12억1만원 → 고가주택
    # 조건: 양도가액 = 12억 + 1만원 → 고가주택 해당 → 초과분 과세
    # 예상: verdict=고가주택
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-17",
        "title": "양도가액 12억1만원 → 고가주택",
        "description": (
            "1세대1주택, 2년 이상 보유·거주 충족. "
            "양도가액 12억1만원 → 12억 초과 → 고가주택 → 1만원 초과분에 대해 과세."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2018-01-10",
            "transfer_date": "2025-06-10",
            "acquisition_price": 700000000,
            "sale_price_total": 1200010000,        # 12억 + 1만원
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 7.4,
            "residence_period_years": 2.5,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "고가주택",
            "confidence_min": 0.85,
            "key_article": "소득세법 제89조 제1항 제3호",
            "notes": (
                "양도가액 12억 초과(1만원 초과) → 고가주택 해당. "
                "비과세 적용 범위: 양도가액 × (12억/양도가액) 비율로 안분. "
                "초과분(1만원)에 대응하는 양도차익 부분만 과세. "
                "경계값 처리: 1원이라도 초과하면 고가주택."
            ),
        },
    },

    # ====================================================================
    # 동거봉양 (CASE-18)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-18: 60세 이상 부모와 합가 → 일시적 2주택 특례, 비과세
    # 조건: 60세 이상 부모와 동거봉양 합가 → 합가일로부터 10년 이내 양도
    # 예상: verdict=비과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-18",
        "title": "동거봉양 합가 → 일시적 2주택 비과세",
        "description": (
            "60세 이상 부모를 모시기 위해 합가(2022-03-01). "
            "각자 1주택 보유 → 합가 후 세대 내 2주택. "
            "합가일로부터 10년 이내(2032-03-01 전)에 종전주택 양도(2025-07-01) → 비과세."
        ),
        "owner_profile": {
            "household_house_count": 2,            # 합가 후 세대 내 2주택
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2016-04-01",      # 자녀(본인) 주택 취득
            "transfer_date": "2025-07-01",
            "acquisition_price": 400000000,
            "sale_price_total": 800000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 9.25,
            "residence_period_years": 6.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "co_habitation_care": {
                "is_co_habitation": True,
                "merge_date": "2022-03-01",        # 합가일
                "parent_age_at_merge": 68,         # 60세 이상 요건 충족
                "sell_by_date": "2032-03-01",      # 합가 후 10년 이내 양도 기한
            },
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "비과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 시행령 제155조 제4항",
            "notes": (
                "60세 이상 부모 동거봉양 합가 → 합가일로부터 10년 이내 양도 시 비과세. "
                "2025-07-01 < 2032-03-01 → 기한 내 양도 충족. "
                "양도가액 8억 → 12억 이하 → 전액 비과세."
            ),
        },
    },

    # ====================================================================
    # 분양권 (CASE-19 ~ 20)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-19: 분양권 취득 후 1년 미만 양도 → 단기세율 (70%)
    # 조건: 분양권 취득 후 9개월 만에 양도 → 1년 미만 → 70%
    # 예상: verdict=단기세율
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-19",
        "title": "분양권 1년 미만 양도 → 단기세율 (70%)",
        "description": (
            "아파트 분양권 취득(2024-08-01) 후 9개월 만에 양도(2025-05-01). "
            "1년 미만 보유 → 70% 단기세율 적용."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "분양권",
            "acquisition_cause": "분양",
            "acquisition_date": "2024-08-01",
            "transfer_date": "2025-05-01",         # 9개월 후
            "acquisition_price": 500000000,        # 분양가
            "sale_price_total": 600000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 0.75,
            "residence_period_years": 0.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "bunyang_acquired_before_2021": False, # 2021 이후 취득 → 주택 수 산입
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "단기세율",
            "confidence_min": 0.80,
            "key_article": "소득세법 제104조 제1항",
            "notes": (
                "분양권 1년 미만 보유(9개월) 양도 → 70% 세율 적용. "
                "2021년 이후 취득 분양권 → 주택 수에 산입. "
                "분양권은 주택이 아니므로 1세대1주택 비과세 불가."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-20: 분양권 → 입주권 전환, 입주권 양도 → 일반과세
    # 조건: 분양권이 조합원입주권으로 전환, 입주권 상태에서 양도
    #        조합원입주권 양도 → 소득세법 §89 비과세 요건 확인 필요
    # 예상: verdict=일반과세 (비과세 요건 미충족)
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-20",
        "title": "분양권→입주권 전환 후 입주권 양도 → 일반과세",
        "description": (
            "아파트 분양권 취득(2020-11-01) → 재건축 조합원입주권으로 전환(관리처분인가일 2023-03-15). "
            "입주권 상태에서 양도(2025-05-01). "
            "비과세 요건(1세대 1주택 + 입주권 특례) 미충족 → 일반과세."
        ),
        "owner_profile": {
            "household_house_count": 2,            # 다른 주택 1채 추가 보유
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "입주권",
            "acquisition_cause": "재건축",
            "acquisition_date": "2020-11-01",      # 분양권 최초 취득일
            "transfer_date": "2025-05-01",
            "acquisition_price": 450000000,
            "sale_price_total": 650000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 4.5,
            "residence_period_years": 0.0,
            "joint_ownership_yn": False,
            "management_disposal_date": "2023-03-15",  # 관리처분계획인가일
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "reconstruction": {
                "management_disposal_date": "2023-03-15",
                "original_house_acquisition_date": "2020-11-01",
                "is_original_member": True,
            },
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "일반과세",
            "confidence_min": 0.70,
            "key_article": "소득세법 시행령 제156조의2",
            "notes": (
                "입주권 양도 → §156의2 조합원입주권 특례 적용 검토. "
                "2주택 보유(입주권 포함) → 1세대1주택 비과세 요건 불충족. "
                "관리처분계획인가일(2023-03-15)부터 보유기간 기산 → 약 2년. "
                "일반과세 적용."
            ),
        },
    },

    # ====================================================================
    # 상속주택 경로 B (CASE-21)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-21: 상속주택 자체 양도 (상속개시 5년 이후) → 일반과세
    # 조건: 상속주택 자체를 양도, 상속개시 5년 경과
    #        상속주택 자체 양도 → §155③ 피상속인 보유기간 합산 검토
    # 예상: verdict=일반과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-21",
        "title": "상속주택 자체 양도 (상속개시 5년 이후) → 일반과세",
        "description": (
            "부모 사망(2018-06-01)으로 상속받은 주택을 양도(2025-08-01). "
            "상속개시 후 7년 경과 → 5년 초과 → 상속주택 주택 수 포함. "
            "상속주택 자체 양도 → 일반과세."
        ),
        "owner_profile": {
            "household_house_count": 2,            # 일반주택 + 상속주택
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "상속",
            "acquisition_date": "2018-06-01",      # 상속개시일 = 취득일
            "transfer_date": "2025-08-01",
            "acquisition_price": 300000000,        # 상속 당시 평가가액
            "sale_price_total": 700000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 7.2,
            "residence_period_years": 0.0,
            "joint_ownership_yn": False,
            "death_date": "2018-06-01",
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "inherited_as_only_house": False,
            "deceased_same_household": False,
            "selling_inherited_house": True,       # 상속주택 자체 양도 (경로 B)
            "donor_acquisition_date": "1998-03-01",  # 피상속인 원취득일
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "일반과세",
            "confidence_min": 0.75,
            "key_article": "소득세법 시행령 제155조 제2항",
            "notes": (
                "상속개시 후 7년 경과(5년 초과) → 상속주택이 주택 수에 포함. "
                "상속주택 자체 양도 → 1세대1주택 비과세 요건 불충족(2주택). "
                "피상속인 보유기간 합산(§155③) 검토 → 합산해도 2주택이라 비과세 불가. "
                "일반과세 적용."
            ),
        },
    },

    # ====================================================================
    # L2 차단 케이스 (CASE-22 ~ 25)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-22: 양도가액 누락 → blocked_at_l2=True
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-22",
        "title": "양도가액 누락 → L2 차단",
        "description": "sale_price_total(양도가액) 없음 → 고가주택 판단 불가 → L2 차단.",
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2019-06-01",
            "transfer_date": "2025-06-01",
            "acquisition_price": 500000000,
            # sale_price_total 의도적 누락
            "adjustment_area_at_acquisition": True,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 6.0,
            "residence_period_years": 3.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
        },
        "expected": {
            "blocked_at_l2": True,
            "missing_fact_contains": "transfer_price",
            "notes": "양도가액 미입력 → L2 크리티컬 차단. missing_facts에 transfer_price 포함 필수.",
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-23: 일시적2주택인데 신규주택 취득일 누락 → blocked_at_l2=True
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-23",
        "title": "일시적2주택 신규주택 취득일 누락 → L2 차단",
        "description": (
            "일시적2주택(is_temporary_two_house=True)인데 "
            "신규주택 취득일(temp_new_acquisition_date) 미입력 → L2 차단."
        ),
        "owner_profile": {
            "household_house_count": 2,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2017-05-01",
            "transfer_date": "2025-08-01",
            "acquisition_price": 400000000,
            "sale_price_total": 750000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 8.25,
            "residence_period_years": 4.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": True,
            # temp_new_acquisition_date 의도적 누락
        },
        "expected": {
            "blocked_at_l2": True,
            "missing_fact_contains": "temp_two_house.new_acquisition_date",
            "notes": (
                "일시적2주택 신규주택 취득일 미입력 → L2 크리티컬 차단. "
                "3년 이내 양도 기한 계산 불가 → can_proceed=False."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-24: 입주권인데 관리처분인가일 누락 → blocked_at_l2=True
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-24",
        "title": "입주권 관리처분인가일 누락 → L2 차단",
        "description": (
            "조합원입주권(asset_kind=입주권) 양도인데 "
            "관리처분계획인가일(management_disposal_date) 미입력 → L2 차단."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "입주권",
            "acquisition_cause": "재건축",
            "acquisition_date": "2015-03-01",
            "transfer_date": "2025-07-01",
            "acquisition_price": 300000000,
            "sale_price_total": 600000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 10.3,
            "residence_period_years": 3.0,
            "joint_ownership_yn": False,
            # management_disposal_date 의도적 누락
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            # reconstruction 정보 없음 → L2 차단
        },
        "expected": {
            "blocked_at_l2": True,
            "missing_fact_contains": "management_disposal_date",
            "notes": (
                "입주권 양도 시 관리처분계획인가일 미입력 → L2 크리티컬 차단. "
                "보유기간 기산점 계산 불가 → can_proceed=False."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-25: 상속주택인데 사망일 누락 → blocked_at_l2=True
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-25",
        "title": "상속주택 사망일 누락 → L2 차단",
        "description": (
            "상속주택 플래그(is_inherited_house) 있는데 "
            "사망일(death_date / InheritanceDetail) 미입력 → L2 차단."
        ),
        "owner_profile": {
            "household_house_count": 2,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "상속",
            "acquisition_date": "2020-01-01",
            "transfer_date": "2025-06-01",
            "acquisition_price": 400000000,
            "sale_price_total": 700000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 5.4,
            "residence_period_years": 1.0,
            "joint_ownership_yn": False,
            # death_date 의도적 누락
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "is_inherited_house": True,
            # InheritanceDetail(death_date) 의도적 누락
        },
        "expected": {
            "blocked_at_l2": True,
            "missing_fact_contains": "death_date",
            "notes": (
                "상속주택 플래그 있으나 사망일 미입력 → L2 크리티컬 차단. "
                "§155② 5년 이내 기산점 계산 불가 → can_proceed=False."
            ),
        },
    },

    # ====================================================================
    # 확인서 차단 (CASE-26 ~ 27)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-26: confirmed={} → blocked_at_confirmation=True
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-26",
        "title": "확인서 미제출(빈 dict) → 확인 게이트 차단",
        "description": (
            "confirmed={}(빈 dict) → 4개 확인 항목 전부 미확인 "
            "→ check_confirmation() can_proceed=False."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2019-01-01",
            "transfer_date": "2025-01-01",
            "acquisition_price": 500000000,
            "sale_price_total": 800000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 6.0,
            "residence_period_years": 3.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "confirmed": {},               # 빈 dict → 전부 미확인
        },
        "expected": {
            "blocked_at_l2": False,        # L2는 통과
            "blocked_at_confirmation": True,
            "notes": (
                "confirmed={} → household_house_count_verified, "
                "balance_or_registration_date_used, no_related_party, "
                "actual_residence_verified 4개 전부 False → 차단."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-27: confirmed 4개 모두 True → blocked_at_confirmation=False, 정상 진행
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-27",
        "title": "확인서 4개 모두 True → 정상 진행",
        "description": (
            "4개 확인 항목 모두 True → check_confirmation() can_proceed=True. "
            "정상적으로 L2~L5 진입."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2019-01-01",
            "transfer_date": "2025-01-01",
            "acquisition_price": 500000000,
            "sale_price_total": 800000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 6.0,
            "residence_period_years": 3.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "confirmed": {
                "household_house_count_verified": True,
                "balance_or_registration_date_used": True,
                "no_related_party": True,
                "actual_residence_verified": True,
            },
        },
        "expected": {
            "blocked_at_l2": False,
            "blocked_at_confirmation": False,
            "verdict": "비과세",
            "confidence_min": 0.80,
            "key_article": "소득세법 제89조 제1항 제3호",
            "notes": (
                "4개 확인 항목 모두 충족 → 게이트 통과. "
                "1주택 6년 보유, 3년 거주, 비조정지역 → 비과세."
            ),
        },
    },

    # ====================================================================
    # 특수관계자 거래 (CASE-28)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-28: 특수관계자 거래 → 경고 포함, expert_review_signals
    # 조건: is_related_party_transaction=True → 부당행위계산부인(§101) 위험
    #        차단하지 않음 — 경고 후 진행
    # 예상: verdict 판단 진행하되 warnings/expert_review_signals 포함
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-28",
        "title": "특수관계자 거래 → 경고 포함, expert_review_signals",
        "description": (
            "부모에게 시가보다 낮은 가액으로 매도(특수관계자 저가 양도). "
            "is_related_party_transaction=True → §101 부당행위계산부인 위험. "
            "L2 차단 없음, verdict 판단 진행, expert_review_signals 생성."
        ),
        "owner_profile": {
            "household_house_count": 1,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2018-03-01",
            "transfer_date": "2025-06-01",
            "acquisition_price": 400000000,
            "sale_price_total": 700000000,  # 시가보다 낮게 매도
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 7.25,
            "residence_period_years": 4.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "is_related_party_transaction": True,  # 특수관계자 거래
            "related_party_relationship": "직계존비속",
            "market_value": 900000000,              # 시가 9억 vs 실거래 7억 → 저가 양도
        },
        "expected": {
            "blocked_at_l2": False,                # 차단하지 않음
            "verdict": "비과세",                   # 판단 자체는 정상 진행
            "confidence_min": 0.60,                # 특수관계자 위험으로 confidence 하향
            "key_article": "소득세법 제101조",
            "warnings_contain": "특수관계자",
            "has_expert_review_signals": True,
            "notes": (
                "is_related_party_transaction=True → 차단 없음, 경고 후 진행. "
                "§101 부당행위계산부인 — 양도가액을 시가(9억)로 재계산 시 "
                "비과세 범위 및 양도차익이 달라짐. "
                "expert_review_signals에 '부당행위계산부인' 포함 필수."
            ),
        },
    },

    # ====================================================================
    # 농어촌주택 (CASE-29 ~ 30)
    # ====================================================================

    # ────────────────────────────────────────────────────────────────────
    # CASE-29: 조특법 §99의4 농어촌주택 취득 → 주택수 제외, 비과세
    # 조건: 농어촌 지역 소재 농어촌주택 취득 → 일반주택 비과세 판단 시 주택 수 제외
    # 예상: verdict=비과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-29",
        "title": "농어촌주택 취득 (조특법 §99의4) → 주택수 제외, 비과세",
        "description": (
            "일반주택 1채 보유 중 농어촌 지역(경북 예천군) 농어촌주택 취득. "
            "조특법 §99의4 요건 충족 → 농어촌주택은 주택 수 제외 → 일반주택 양도 시 비과세."
        ),
        "owner_profile": {
            "household_house_count": 2,            # 일반주택 + 농어촌주택
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2017-09-01",      # 일반주택 취득
            "transfer_date": "2025-09-01",
            "acquisition_price": 450000000,
            "sale_price_total": 850000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 8.0,
            "residence_period_years": 4.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "rural_house": {
                "is_rural_house": True,
                "region": "경상북도 예천군",       # 농어촌 지역 (과밀억제권역 외)
                "acquisition_date": "2022-05-01",
                "acquisition_price": 80000000,     # 기준금액(2억) 이하 요건 충족
                "is_overconcentration_area": False, # 과밀억제권역 아님
                "law_article": "조세특례제한법 제99조의4",
            },
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "비과세",
            "confidence_min": 0.70,
            "key_article": "조세특례제한법 제99조의4",
            "notes": (
                "농어촌주택(경북 예천군, 취득가액 8천만 이하) → 조특법 §99의4 요건 충족. "
                "농어촌주택은 주택 수 제외 → 일반주택만 1주택으로 간주. "
                "일반주택 8년 보유, 4년 거주 → 비과세 요건 충족."
            ),
        },
    },

    # ────────────────────────────────────────────────────────────────────
    # CASE-30: 농어촌주택이나 도시 과밀억제권역 → 요건 미충족, 일반과세
    # 조건: 농어촌주택이라 했으나 과밀억제권역(수도권 등) 소재 → 요건 불충족
    # 예상: verdict=일반과세
    # ────────────────────────────────────────────────────────────────────
    {
        "case_id": "CASE-30",
        "title": "농어촌주택 과밀억제권역 → 요건 미충족, 일반과세",
        "description": (
            "경기도 수원시(과밀억제권역)에 소위 농어촌주택 취득. "
            "과밀억제권역 소재 → 조특법 §99의4 농어촌주택 요건 불충족. "
            "2주택으로 간주 → 일반주택 양도 시 일반과세."
        ),
        "owner_profile": {
            "household_house_count": 2,
            "overseas_residence_yn": False,
        },
        "user_property": {
            "asset_kind": "아파트",
            "acquisition_cause": "매매",
            "acquisition_date": "2018-04-01",
            "transfer_date": "2025-10-01",
            "acquisition_price": 500000000,
            "sale_price_total": 850000000,
            "adjustment_area_at_acquisition": False,
            "adjustment_area_at_transfer": False,
            "holding_period_years": 7.5,
            "residence_period_years": 3.0,
            "joint_ownership_yn": False,
        },
        "fact_ledger": {
            "is_temporary_two_house": False,
            "rural_house": {
                "is_rural_house": False,           # 과밀억제권역 → 농어촌주택 요건 불충족
                "region": "경기도 수원시",
                "is_overconcentration_area": True, # 과밀억제권역 → 요건 미충족
                "law_article": "조세특례제한법 제99조의4",
            },
        },
        "expected": {
            "blocked_at_l2": False,
            "verdict": "일반과세",
            "confidence_min": 0.70,
            "key_article": "조세특례제한법 제99조의4",
            "notes": (
                "경기도 수원시 → 과밀억제권역 → §99의4 농어촌주택 요건 불충족. "
                "농어촌주택 제외 불가 → 2주택으로 간주. "
                "일반주택 양도 → 비과세 불가(2주택) → 일반과세. "
                "비조정지역이므로 중과 미적용."
            ),
        },
    },
]


# ── 사용 예시 ──────────────────────────────────────────────────────────
#
# pytest 예시:
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


# ── 사용 예시 ──────────────────────────────────────────────────────────
#
# pytest 예시:
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
