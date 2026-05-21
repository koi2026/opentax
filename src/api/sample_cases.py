"""
양도소득세 실무 케이스 샘플 — 랜덤 뽑기용.
자주 만나는 케이스 위주로 구성.
"""
from __future__ import annotations

SAMPLE_CASES: list[dict] = [

    # ── 1주택 비과세 기본 ──────────────────────────────────────────────────────
    {
        "label": "1주택 비과세 — 조정지역 보유·거주 2년 이상",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20240601",
            "acquisition_date": "20200301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 900000000,
            "acquisition_price": 600000000,
            "holding_years": 4.25,
            "residence_years": 2.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "1주택 비과세 — 비조정지역 보유 2년 (거주 불필요)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210801",
            "property_type": "단독주택",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 700000000,
            "holding_years": 3.2,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "1주택 비과세 — 보유 2년, 거주 2년 (경계값)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20240915",
            "acquisition_date": "20220901",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 850000000,
            "holding_years": 2.04,
            "residence_years": 2.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },

    # ── 고가주택 ──────────────────────────────────────────────────────────────
    {
        "label": "고가주택 — 12억 초과, 초과분만 과세",
        "category": "고가주택",
        "fact_json": {
            "transfer_date": "20240801",
            "acquisition_date": "20190501",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 1800000000,
            "acquisition_price": 900000000,
            "holding_years": 5.25,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "고가주택 — 13억, 장기보유특별공제 적용",
        "category": "고가주택",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20140301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 1300000000,
            "acquisition_price": 500000000,
            "holding_years": 10.75,
            "residence_years": 10.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": True,
        },
    },

    # ── 단기 양도 ─────────────────────────────────────────────────────────────
    {
        "label": "단기세율 — 보유 1년 미만 (세율 70%)",
        "category": "단기세율",
        "fact_json": {
            "transfer_date": "20240901",
            "acquisition_date": "20240101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 700000000,
            "acquisition_price": 620000000,
            "holding_years": 0.67,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "단기세율 — 보유 1~2년 (세율 60%)",
        "category": "단기세율",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20230301",
            "property_type": "연립다세대",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 400000000,
            "acquisition_price": 350000000,
            "holding_years": 1.58,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 다주택자 중과 ──────────────────────────────────────────────────────────
    {
        "label": "2주택 중과 — 조정지역 (기본세율 +20%p)",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20240701",
            "acquisition_date": "20180601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 800000000,
            "acquisition_price": 450000000,
            "holding_years": 6.08,
            "residence_years": 0.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "3주택 중과 — 조정지역 (기본세율 +30%p)",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20170401",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 3,
            "transfer_price": 1100000000,
            "acquisition_price": 500000000,
            "holding_years": 7.58,
            "residence_years": 1.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "2주택 — 비조정지역 (중과 아닌 일반세율)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20240901",
            "acquisition_date": "20190301",
            "property_type": "단독주택",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 500000000,
            "acquisition_price": 280000000,
            "holding_years": 5.5,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 일시적 2주택 ──────────────────────────────────────────────────────────
    {
        "label": "일시적 2주택 비과세 — 3년 내 종전주택 양도",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20240801",
            "acquisition_date": "20190601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 950000000,
            "holding_years": 5.17,
            "residence_years": 2.5,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "temp_two_house": {
                    "new_acquisition_date": "20220601",
                    "old_house_must_sell_by": "20250601",
                    "new_is_adjustment_area": True,
                }
            },
        },
    },
    {
        "label": "일시적 2주택 — 기한 초과로 비과세 미적용",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20180301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 900000000,
            "holding_years": 6.75,
            "residence_years": 2.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "temp_two_house": {
                    "new_acquisition_date": "20210601",
                    "old_house_must_sell_by": "20240601",
                    "new_is_adjustment_area": True,
                }
            },
        },
    },

    # ── 상속주택 ──────────────────────────────────────────────────────────────
    {
        "label": "상속주택 경로A — 일반주택 양도 시 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20170501",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 800000000,
            "holding_years": 7.4,
            "residence_years": 2.5,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "inheritance": {
                    "death_date": "20210301",
                    "same_household_at_death": False,
                    "inherited_as_only_house": True,
                    "selling_inherited_house": False,
                }
            },
        },
    },
    {
        "label": "상속주택 경로B — 상속받은 주택 직접 양도",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20210601",
            "property_type": "단독주택",
            "acquisition_reason": "상속",
            "household_house_count": 1,
            "transfer_price": 600000000,
            "holding_years": 3.4,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "inheritance": {
                    "death_date": "20210601",
                    "same_household_at_death": True,
                    "inherited_as_only_house": True,
                    "selling_inherited_house": True,
                    "donor_acquisition_date": "19950301",
                }
            },
        },
    },

    # ── 증여 이월과세 ─────────────────────────────────────────────────────────
    {
        "label": "배우자 증여 이월과세 — 5년 이내 양도",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20220301",
            "property_type": "아파트",
            "acquisition_reason": "증여",
            "household_house_count": 1,
            "transfer_price": 900000000,
            "acquisition_price": 750000000,
            "holding_years": 2.58,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": True,
                    "donor_acquisition_date": "20150601",
                    "donor_acquisition_price": 400000000,
                }
            },
        },
    },
    {
        "label": "직계존비속 증여 이월과세 — 10년 이내 양도",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20240601",
            "acquisition_date": "20180901",
            "property_type": "아파트",
            "acquisition_reason": "증여",
            "household_house_count": 1,
            "transfer_price": 1100000000,
            "acquisition_price": 850000000,
            "holding_years": 5.75,
            "residence_years": 3.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": True,
                    "donor_acquisition_date": "20100301",
                    "donor_acquisition_price": 350000000,
                }
            },
        },
    },
    {
        "label": "타인 증여 — 이월과세 미적용 (일반 양도)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20200601",
            "property_type": "연립다세대",
            "acquisition_reason": "증여",
            "household_house_count": 1,
            "transfer_price": 450000000,
            "acquisition_price": 380000000,
            "holding_years": 4.5,
            "residence_years": 1.0,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": False,
                }
            },
        },
    },

    # ── 혼인합가 / 동거봉양 ───────────────────────────────────────────────────
    {
        "label": "혼인합가 일시적 2주택 — 5년 내 양도 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20160301",
            "property_type": "아파트",
            "acquisition_reason": "혼인합가",
            "household_house_count": 2,
            "transfer_price": 750000000,
            "holding_years": 8.58,
            "residence_years": 3.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "marriage_merge": {
                    "marriage_date": "20200901",
                    "spouse_house_count_before_marriage": 1,
                    "own_house_count_before_marriage": 1,
                }
            },
        },
    },

    # ── 분양권 ────────────────────────────────────────────────────────────────
    {
        "label": "분양권 양도 — 2021년 이후 취득 (주택 수 산입, 단기세율)",
        "category": "단기세율",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20220601",
            "property_type": "분양권",
            "acquisition_reason": "분양",
            "household_house_count": 1,
            "transfer_price": 600000000,
            "acquisition_price": 500000000,
            "holding_years": 2.33,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "분양권 양도 — 2021년 이전 취득 (주택 수 미산입)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20240601",
            "acquisition_date": "20191001",
            "property_type": "분양권",
            "acquisition_reason": "분양",
            "household_house_count": 0,
            "transfer_price": 550000000,
            "acquisition_price": 400000000,
            "holding_years": 4.67,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 입주권 / 재건축 ──────────────────────────────────────────────────────
    {
        "label": "조합원입주권 — 원조합원 1주택 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20050601",
            "property_type": "입주권",
            "acquisition_reason": "재건축",
            "household_house_count": 1,
            "transfer_price": 1000000000,
            "holding_years": 19.5,
            "residence_years": 5.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20150301",
                    "is_original_member": True,
                }
            },
        },
    },

    # ── 상생임대 ──────────────────────────────────────────────────────────────
    {
        "label": "상생임대 — 거주요건 2년 면제 (조정지역 1주택)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 950000000,
            "holding_years": 3.58,
            "residence_years": 0.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "sangsaeng_rental": {
                    "contract_date": "20220301",
                    "contract_period_months": 24,
                    "previous_monthly_rent": 1500000,
                    "new_monthly_rent": 1550000,
                    "has_prior_contract": True,
                }
            },
        },
    },

    # ── 장기임대 감면 ─────────────────────────────────────────────────────────
    {
        "label": "장기임대 — 8년 의무임대 완료, 감면 적용",
        "category": "감면",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20140601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 700000000,
            "acquisition_price": 300000000,
            "holding_years": 10.4,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "long_term_rental": {
                    "registration_date": "20140801",
                    "mandatory_period_years": 8,
                    "mandatory_period_fulfilled": True,
                    "rent_increase_limit_complied": True,
                }
            },
        },
    },

    # ── 겸용주택 ──────────────────────────────────────────────────────────────
    {
        "label": "겸용주택 — 주거비율 60% (주택으로 전체 과세)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20150301",
            "property_type": "겸용주택",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 800000000,
            "holding_years": 9.58,
            "residence_years": 4.0,
            "residential_area_ratio": 0.6,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "겸용주택 — 주거비율 40% (상가 부분 일반과세)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20100601",
            "property_type": "겸용주택",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 1200000000,
            "acquisition_price": 400000000,
            "holding_years": 14.5,
            "residence_years": 8.0,
            "residential_area_ratio": 0.4,
        },
    },

    # ── 다가구주택 ────────────────────────────────────────────────────────────
    {
        "label": "다가구주택 — 1동 전체 단독소유, 1주택 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20170801",
            "property_type": "다가구",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 900000000,
            "holding_years": 7.17,
            "residence_years": 3.0,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 비거주자 ──────────────────────────────────────────────────────────────
    {
        "label": "비거주자 — 단기보유 양도 (거주요건 무관, 일반세율)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20200601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 800000000,
            "acquisition_price": 600000000,
            "holding_years": 4.33,
            "residence_years": 0.0,
            "is_non_resident": True,
            "is_adjustment_area_at_transfer": True,
        },
    },

    # ── 해외이주 / 수용 ───────────────────────────────────────────────────────
    {
        "label": "해외이주 — 거주요건 면제, 1주택 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20190601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 850000000,
            "holding_years": 5.5,
            "residence_years": 1.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "residence_exemption_reason": "해외이주",
            },
        },
    },
    {
        "label": "공익사업 수용 — 거주요건 면제 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20180301",
            "property_type": "단독주택",
            "acquisition_reason": "수용",
            "household_house_count": 1,
            "transfer_price": 650000000,
            "holding_years": 6.58,
            "residence_years": 0.5,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "residence_exemption_reason": "수용",
            },
        },
    },

    # ── 농어촌주택 ────────────────────────────────────────────────────────────
    {
        "label": "농어촌주택 + 일반주택 — 일반주택 양도 시 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20180601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 800000000,
            "holding_years": 6.42,
            "residence_years": 2.5,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "rural_house": {"is_eligible": True}
            },
        },
    },

    # ── 경매 취득 ─────────────────────────────────────────────────────────────
    {
        "label": "경매 취득 — 1주택 장기보유 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20160901",
            "property_type": "아파트",
            "acquisition_reason": "경매",
            "household_house_count": 1,
            "transfer_price": 950000000,
            "acquisition_price": 450000000,
            "holding_years": 8.25,
            "residence_years": 5.0,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 이혼재산분할 ──────────────────────────────────────────────────────────
    {
        "label": "이혼재산분할 — 취득 후 1주택 양도",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210301",
            "property_type": "아파트",
            "acquisition_reason": "이혼재산분할",
            "household_house_count": 1,
            "transfer_price": 700000000,
            "holding_years": 3.58,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": True,
        },
    },

    # ── 사실관계 부족 시나리오 ─────────────────────────────────────────────────
    {
        "label": "사실관계 부족 — 양도가액 미입력 (고가주택 판단 불가)",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20240901",
            "acquisition_date": "20190601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "holding_years": 5.25,
            "residence_years": 3.0,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "사실관계 부족 — 상속 취득일 미입력",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20210801",
            "property_type": "단독주택",
            "acquisition_reason": "상속",
            "household_house_count": 2,
            "transfer_price": 650000000,
            "holding_years": 3.25,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 동거봉양 합가 ──────────────────────────────────────────────────────────
    {
        "label": "동거봉양 합가 — 10년 내 종전주택 양도 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20130601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 850000000,
            "acquisition_price": 350000000,
            "holding_years": 11.33,
            "residence_years": 5.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "cohabitation_care": {
                    "cohabitation_date": "20190301",
                    "parent_age_at_merge": 63,
                }
            },
        },
    },
    {
        "label": "동거봉양 합가 — 10년 초과로 비과세 미적용",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20100301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 920000000,
            "acquisition_price": 250000000,
            "holding_years": 14.75,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "cohabitation_care": {
                    "cohabitation_date": "20130601",
                    "parent_age_at_merge": 61,
                }
            },
        },
    },

    # ── 취학·직장이전·요양 거주요건 면제 ──────────────────────────────────────────
    {
        "label": "취학 사유 — 조정지역 거주요건 2년 면제",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20220301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 800000000,
            "acquisition_price": 680000000,
            "holding_years": 2.58,
            "residence_years": 0.8,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "residence_exemption_reason": "취학",
            },
        },
    },
    {
        "label": "직장이전 사유 — 조정지역 거주요건 면제",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20210601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 750000000,
            "acquisition_price": 630000000,
            "holding_years": 3.42,
            "residence_years": 1.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "residence_exemption_reason": "직장이전",
            },
        },
    },
    {
        "label": "요양 사유 — 1년 이상 치료 필요, 거주요건 면제",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20220901",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 820000000,
            "acquisition_price": 700000000,
            "holding_years": 2.25,
            "residence_years": 0.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "residence_exemption_reason": "요양",
            },
        },
    },

    # ── 소규모재건축 ──────────────────────────────────────────────────────────
    {
        "label": "소규모재건축 — 원조합원 1주택, 준공 후 신축 양도",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20000601",
            "property_type": "아파트",
            "acquisition_reason": "소규모재건축",
            "household_house_count": 1,
            "transfer_price": 950000000,
            "acquisition_price": 150000000,
            "holding_years": 24.33,
            "residence_years": 6.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20180601",
                    "completion_date": "20220301",
                    "is_original_member": True,
                }
            },
        },
    },
    {
        "label": "소규모재건축 — 조합원입주권 양도 (준공 전)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "19980301",
            "property_type": "입주권",
            "acquisition_reason": "소규모재건축",
            "household_house_count": 2,
            "transfer_price": 800000000,
            "acquisition_price": 120000000,
            "holding_years": 26.67,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20170901",
                    "is_original_member": True,
                }
            },
        },
    },

    # ── 공익사업 수용 감면 (조특§77) ─────────────────────────────────────────
    {
        "label": "공익수용 감면 — 보상금 채권 수령 시 추가 감면",
        "category": "감면",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20100601",
            "property_type": "단독주택",
            "acquisition_reason": "수용",
            "household_house_count": 1,
            "transfer_price": 1200000000,
            "acquisition_price": 350000000,
            "holding_years": 14.42,
            "residence_years": 8.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "expropriation": {
                    "compensation_type": "채권",
                    "is_main_residence": True,
                }
            },
        },
    },
    {
        "label": "공익수용 — 2년 미거주, 감면 미적용 (일반과세)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20190301",
            "property_type": "단독주택",
            "acquisition_reason": "수용",
            "household_house_count": 1,
            "transfer_price": 900000000,
            "acquisition_price": 500000000,
            "holding_years": 5.58,
            "residence_years": 0.5,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "public_expropriation": {
                    "compensation_type": "현금",
                    "is_main_residence": False,
                }
            },
        },
    },

    # ── 특수관계인 거래 (§101 부당행위계산부인) ───────────────────────────────
    {
        "label": "특수관계인 저가양도 — 시가 대비 30% 저가 (부당행위계산)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20180601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 600000000,
            "acquisition_price": 400000000,
            "holding_years": 6.33,
            "residence_years": 2.5,
            "is_adjustment_area_at_transfer": False,
            "is_related_party_transaction": True,
            "market_price": 850000000,
        },
    },
    {
        "label": "특수관계인 거래 — 시가 차이 5% 이내 (부당행위계산 미적용)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20190301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 820000000,
            "acquisition_price": 500000000,
            "holding_years": 5.67,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
            "is_related_party_transaction": True,
            "market_price": 850000000,
        },
    },

    # ── 지분 공유 양도 ────────────────────────────────────────────────────────
    {
        "label": "배우자 공동명의 1주택 — 지분 50% 양도",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20200301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 450000000,
            "acquisition_price": 280000000,
            "holding_years": 4.75,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
            "joint_ownership_yn": True,
            "ownership_ratio": 0.5,
        },
    },
    {
        "label": "형제 공유 상속주택 — 소수지분 양도 (일반과세)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210601",
            "property_type": "단독주택",
            "acquisition_reason": "상속",
            "household_house_count": 1,
            "transfer_price": 200000000,
            "acquisition_price": 120000000,
            "holding_years": 3.33,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "joint_ownership_yn": True,
            "ownership_ratio": 0.3,
            "special_cases": {
                "inheritance": {
                    "death_date": "20210601",
                    "same_household_at_death": False,
                    "inherited_as_only_house": False,
                    "selling_inherited_house": True,
                }
            },
        },
    },
    {
        "label": "공동명의 고가주택 — 1인 지분 양도 (12억 기준 지분 적용)",
        "category": "고가주택",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20170601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 700000000,
            "acquisition_price": 350000000,
            "holding_years": 7.5,
            "residence_years": 4.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
            "joint_ownership_yn": True,
            "ownership_ratio": 0.5,
            "full_property_price": 1400000000,
        },
    },

    # ── 오피스텔 ──────────────────────────────────────────────────────────────
    {
        "label": "오피스텔 — 주거용 사실상 사용, 1주택 포함 판정",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20190301",
            "property_type": "오피스텔",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 500000000,
            "acquisition_price": 350000000,
            "holding_years": 5.58,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "officetel_usage": "주거용",
        },
    },
    {
        "label": "오피스텔 — 업무용 임대, 주택 수 미산입 (일반과세)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20200601",
            "property_type": "오피스텔",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 450000000,
            "acquisition_price": 320000000,
            "holding_years": 4.42,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": True,
            "officetel_usage": "업무용",
        },
    },
    {
        "label": "주거용 오피스텔 단독 보유 — 1주택 비과세 요건 검토",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20210301",
            "property_type": "오피스텔",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 550000000,
            "acquisition_price": 420000000,
            "holding_years": 3.75,
            "residence_years": 2.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "officetel_usage": "주거용",
        },
    },

    # ── 보유기간 경계값 추가 ──────────────────────────────────────────────────
    {
        "label": "1주택 — 보유 2년 미만 (비과세 미적용, 단기세율)",
        "category": "단기세율",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20230201",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 700000000,
            "acquisition_price": 620000000,
            "holding_years": 1.67,
            "residence_years": 1.5,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "조정지역 취득 — 거주 1년 11개월 (거주요건 미충족)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20250101",
            "acquisition_date": "20210201",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 900000000,
            "acquisition_price": 700000000,
            "holding_years": 3.92,
            "residence_years": 1.92,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "1주택 — 보유 정확히 2년 (경계값 비과세)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20250301",
            "acquisition_date": "20230301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 780000000,
            "acquisition_price": 700000000,
            "holding_years": 2.0,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 부담부증여 ────────────────────────────────────────────────────────────
    {
        "label": "부담부증여 — 채무 인수분 양도세 과세",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20170601",
            "property_type": "아파트",
            "acquisition_reason": "부담부증여",
            "household_house_count": 1,
            "transfer_price": 1000000000,
            "acquisition_price": 450000000,
            "holding_years": 7.33,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "burdened_gift": {
                    "debt_amount": 300000000,
                    "debt_ratio": 0.3,
                }
            },
        },
    },
    {
        "label": "부담부증여 — 채무 인수분 고가주택 과세",
        "category": "고가주택",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20150301",
            "property_type": "아파트",
            "acquisition_reason": "부담부증여",
            "household_house_count": 1,
            "transfer_price": 1500000000,
            "acquisition_price": 600000000,
            "holding_years": 9.75,
            "residence_years": 5.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "burdened_gift": {
                    "debt_amount": 500000000,
                    "debt_ratio": 0.333,
                }
            },
        },
    },

    # ── 다주택 중과 한시적 유예 (2022.05~2024.05) ─────────────────────────────
    {
        "label": "2주택 중과 유예기간 양도 — 일반세율 적용 (2023.01)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20230115",
            "acquisition_date": "20180601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 800000000,
            "acquisition_price": 450000000,
            "holding_years": 4.54,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "3주택 중과 유예기간 종료 후 양도 — 중과 적용 (2024.06)",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20240615",
            "acquisition_date": "20170301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 3,
            "transfer_price": 1100000000,
            "acquisition_price": 500000000,
            "holding_years": 7.29,
            "residence_years": 1.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },

    # ── 상속주택 추가 ──────────────────────────────────────────────────────────
    {
        "label": "상속주택 경로A — 상속 후 5년 경과, 주택수 산입",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20170901",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 850000000,
            "acquisition_price": 400000000,
            "holding_years": 7.08,
            "residence_years": 2.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "inheritance": {
                    "death_date": "20180601",
                    "same_household_at_death": False,
                    "selling_inherited_house": False,
                }
            },
        },
    },
    {
        "label": "공동상속 — 최다지분 상속인 1인이 상속주택 보유",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20210301",
            "property_type": "단독주택",
            "acquisition_reason": "상속",
            "household_house_count": 1,
            "transfer_price": 700000000,
            "acquisition_price": 350000000,
            "holding_years": 3.67,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "inheritance": {
                    "death_date": "20210301",
                    "same_household_at_death": False,
                    "co_heir_count": 3,
                    "largest_share_holder": True,
                    "ownership_ratio": 0.5,
                    "selling_inherited_house": True,
                }
            },
        },
    },
    {
        "label": "상속주택 — 동거봉양 후 합가 상태에서 상속 (동거봉양 특례 중복)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20150601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 900000000,
            "acquisition_price": 380000000,
            "holding_years": 9.5,
            "residence_years": 6.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "inheritance": {
                    "death_date": "20220901",
                    "same_household_at_death": True,
                    "inherited_as_only_house": True,
                    "selling_inherited_house": False,
                }
            },
        },
    },
    {
        "label": "피상속인 거주주택 — 상속인이 직접 양도 (취득가액 승계)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "19980301",
            "property_type": "단독주택",
            "acquisition_reason": "상속",
            "household_house_count": 1,
            "transfer_price": 1200000000,
            "acquisition_price": 80000000,
            "holding_years": 26.58,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "inheritance": {
                    "death_date": "20210901",
                    "same_household_at_death": False,
                    "donor_acquisition_date": "19980301",
                    "donor_acquisition_price": 80000000,
                    "selling_inherited_house": True,
                }
            },
        },
    },

    # ── 증여 이월과세 추가 ────────────────────────────────────────────────────
    {
        "label": "배우자 증여 이월과세 — 5년 경과 후 양도 (이월과세 미적용)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20180601",
            "property_type": "아파트",
            "acquisition_reason": "증여",
            "household_house_count": 1,
            "transfer_price": 950000000,
            "acquisition_price": 700000000,
            "holding_years": 6.33,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": True,
                    "donor_acquisition_date": "20120301",
                    "donor_acquisition_price": 300000000,
                    "gift_date": "20180601",
                }
            },
        },
    },
    {
        "label": "직계존속 증여 — 이월과세 기간(10년) 내 양도, 원취득가액 적용",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20250101",
            "acquisition_date": "20200301",
            "property_type": "아파트",
            "acquisition_reason": "증여",
            "household_house_count": 1,
            "transfer_price": 1000000000,
            "acquisition_price": 780000000,
            "holding_years": 4.83,
            "residence_years": 2.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": True,
                    "donor_acquisition_date": "20050601",
                    "donor_acquisition_price": 200000000,
                    "gift_date": "20200301",
                }
            },
        },
    },

    # ── 분양권 추가 ───────────────────────────────────────────────────────────
    {
        "label": "분양권 — 보유 1년 미만 양도 (세율 70%)",
        "category": "단기세율",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20240301",
            "property_type": "분양권",
            "acquisition_reason": "분양",
            "household_house_count": 1,
            "transfer_price": 650000000,
            "acquisition_price": 580000000,
            "holding_years": 0.58,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "분양권 전매 — 완공 전 프리미엄 양도 (조정지역)",
        "category": "단기세율",
        "fact_json": {
            "transfer_date": "20240801",
            "acquisition_date": "20220601",
            "property_type": "분양권",
            "acquisition_reason": "분양",
            "household_house_count": 2,
            "transfer_price": 700000000,
            "acquisition_price": 550000000,
            "holding_years": 2.17,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "분양권 — 완공 후 주택 취득, 1주택 비과세 전환",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20250301",
            "acquisition_date": "20210901",
            "property_type": "아파트",
            "acquisition_reason": "분양",
            "household_house_count": 1,
            "transfer_price": 1000000000,
            "acquisition_price": 650000000,
            "holding_years": 3.5,
            "residence_years": 2.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 입주권 추가 ───────────────────────────────────────────────────────────
    {
        "label": "조합원입주권 + 일반주택 1채 — 입주권 양도 (일반과세)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20050301",
            "property_type": "입주권",
            "acquisition_reason": "재건축",
            "household_house_count": 2,
            "transfer_price": 900000000,
            "acquisition_price": 180000000,
            "holding_years": 19.58,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20160601",
                    "has_other_house": True,
                }
            },
        },
    },
    {
        "label": "입주권 — 관리처분인가일 전후 보유기간 합산",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20030601",
            "property_type": "아파트",
            "acquisition_reason": "재건축",
            "household_house_count": 1,
            "transfer_price": 1100000000,
            "acquisition_price": 130000000,
            "holding_years": 21.5,
            "residence_years": 8.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20140301",
                    "completion_date": "20200601",
                    "original_member": True,
                    "has_other_house": False,
                }
            },
        },
    },
    {
        "label": "입주권 취득 후 완공 전 — 일시적2주택 특례 적용",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20180601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 850000000,
            "acquisition_price": 400000000,
            "holding_years": 6.42,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "temp_two_house": {
                    "new_acquisition_date": "20220301",
                    "old_house_must_sell_by": "20250301",
                    "new_is_adjustment_area": False,
                    "new_property_type": "입주권",
                }
            },
        },
    },

    # ── 상생임대 추가 ─────────────────────────────────────────────────────────
    {
        "label": "상생임대 — 임대료 5% 초과, 특례 미적용 (거주요건 미충족)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 900000000,
            "acquisition_price": 700000000,
            "holding_years": 3.33,
            "residence_years": 0.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "sangsaeng_rental": {
                    "contract_date": "20220601",
                    "contract_period_months": 24,
                    "previous_monthly_rent": 1500000,
                    "new_monthly_rent": 1700000,
                    "increase_rate": 0.133,
                    "has_prior_contract": True,
                }
            },
        },
    },
    {
        "label": "상생임대 — 임대기간 2년 미충족 중도해지",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20210301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 850000000,
            "acquisition_price": 650000000,
            "holding_years": 3.75,
            "residence_years": 0.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "sangsaeng_rental": {
                    "contract_date": "20220601",
                    "actual_rental_months": 14,
                    "contract_period_months": 24,
                    "early_termination": True,
                    "has_prior_contract": True,
                }
            },
        },
    },

    # ── 장기임대 추가 ─────────────────────────────────────────────────────────
    {
        "label": "장기임대 — 4년 단기등록 후 자동말소 (의무기간 미충족)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20160301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 650000000,
            "acquisition_price": 280000000,
            "holding_years": 8.67,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "long_term_rental": {
                    "registration_date": "20160601",
                    "mandatory_period_years": 4,
                    "mandatory_period_fulfilled": True,
                    "auto_cancelled": True,
                    "rent_increase_limit_complied": True,
                }
            },
        },
    },
    {
        "label": "장기임대 — 10년 등록 완료, 세액 100% 감면",
        "category": "감면",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20120301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 600000000,
            "acquisition_price": 250000000,
            "holding_years": 12.75,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "long_term_rental": {
                    "registration_date": "20120601",
                    "mandatory_period_years": 10,
                    "mandatory_period_fulfilled": True,
                    "rent_increase_limit_complied": True,
                    "exemption_rate": 1.0,
                }
            },
        },
    },

    # ── 미등기 양도 ───────────────────────────────────────────────────────────
    {
        "label": "미등기 양도 — 세율 70% (등기 이전 전매)",
        "category": "단기세율",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20230601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 650000000,
            "acquisition_price": 550000000,
            "holding_years": 1.33,
            "is_unregistered_transfer": True,
        },
    },

    # ── 양도차손 ──────────────────────────────────────────────────────────────
    {
        "label": "양도차손 — 취득가 > 양도가 (세액 없음)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 550000000,
            "acquisition_price": 700000000,
            "holding_years": 3.33,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "양도차손 — 다주택자, 다른 양도자산 손익통산 필요",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20200301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 480000000,
            "acquisition_price": 620000000,
            "holding_years": 4.75,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": True,
        },
    },

    # ── 고가주택 추가 ──────────────────────────────────────────────────────────
    {
        "label": "고가주택 — 20억, 장기보유특별공제 표1 적용 (거주 2년 미만)",
        "category": "고가주택",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20130601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 2000000000,
            "acquisition_price": 900000000,
            "holding_years": 11.33,
            "residence_years": 1.5,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "고가주택 — 비조정지역 취득, 거주 불필요, 10년 이상 보유",
        "category": "고가주택",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20110301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 1600000000,
            "acquisition_price": 600000000,
            "holding_years": 13.75,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "고가주택 — 12억 경계값 (정확히 12억, 전액 비과세)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20250101",
            "acquisition_date": "20200601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 1200000000,
            "acquisition_price": 800000000,
            "holding_years": 4.58,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 지방미분양 감면 (조특§98의2) ─────────────────────────────────────────
    {
        "label": "지방 미분양 주택 — 조특§98의2 양도세 감면",
        "category": "감면",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20230601",
            "property_type": "아파트",
            "acquisition_reason": "분양",
            "household_house_count": 2,
            "transfer_price": 450000000,
            "acquisition_price": 380000000,
            "holding_years": 1.42,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "local_unsold": {
                    "region": "지방광역시",
                    "is_eligible_area": True,
                }
            },
        },
    },

    # ── 1주택 추가 케이스 ─────────────────────────────────────────────────────
    {
        "label": "1주택 — 재건축 완공 후 신축 아파트 양도 (원주택 취득일 기산)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20020601",
            "property_type": "아파트",
            "acquisition_reason": "재건축",
            "household_house_count": 1,
            "transfer_price": 1100000000,
            "acquisition_price": 120000000,
            "holding_years": 22.5,
            "residence_years": 7.0,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "1주택 — 상가 → 주택 용도변경 후 양도 (보유기간 판정 이슈)",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20130301",
            "property_type": "단독주택",
            "acquisition_reason": "용도변경",
            "household_house_count": 1,
            "transfer_price": 950000000,
            "acquisition_price": 400000000,
            "holding_years": 11.58,
            "residence_years": 5.0,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "1주택 — 증여받은 후 자경, 2년 거주 충족",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20200301",
            "property_type": "단독주택",
            "acquisition_reason": "증여",
            "household_house_count": 1,
            "transfer_price": 680000000,
            "acquisition_price": 500000000,
            "holding_years": 4.67,
            "residence_years": 2.5,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": False,
                }
            },
        },
    },

    # ── 사실관계부족 추가 ─────────────────────────────────────────────────────
    {
        "label": "사실관계 부족 — 이월과세 원취득일 미입력",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210601",
            "property_type": "아파트",
            "acquisition_reason": "증여",
            "household_house_count": 1,
            "transfer_price": 950000000,
            "acquisition_price": 780000000,
            "holding_years": 3.33,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": True,
                }
            },
        },
    },
    {
        "label": "사실관계 부족 — 일시적2주택 신규취득일 미입력",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20190301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 880000000,
            "holding_years": 5.67,
            "residence_years": 2.5,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "temp_two_house": {}
            },
        },
    },
    {
        "label": "사실관계 부족 — 세대원 주택수 미입력 (분양권·오피스텔 포함 여부 불명)",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20200601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "transfer_price": 850000000,
            "holding_years": 4.5,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "사실관계 부족 — 입주권 관리처분인가일 미입력",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20060301",
            "property_type": "입주권",
            "acquisition_reason": "재건축",
            "household_house_count": 1,
            "transfer_price": 1000000000,
            "holding_years": 18.58,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "사실관계 부족 — 잔금지급일·등기접수일 둘 다 미입력 (취득시기 불명)",
        "category": "사실관계부족",
        "fact_json": {
            "transfer_date": "20241101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 750000000,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 혼인합가 추가 ─────────────────────────────────────────────────────────
    {
        "label": "혼인합가 — 5년 초과로 비과세 미적용 (일반세율)",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20120601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 900000000,
            "acquisition_price": 280000000,
            "holding_years": 12.42,
            "residence_years": 4.0,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "marriage_merge": {
                    "marriage_date": "20170301",
                    "must_sell_by": "20220301",
                    "spouse_house_count_before_marriage": 1,
                    "own_house_count_before_marriage": 1,
                }
            },
        },
    },

    # ── 다주택자 추가 ─────────────────────────────────────────────────────────
    {
        "label": "4주택 이상 — 조정지역 중과 (+30%p) 최대 적용",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20150601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 4,
            "transfer_price": 1200000000,
            "acquisition_price": 500000000,
            "holding_years": 9.5,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },
    {
        "label": "2주택 — 조정지역 중과, 장기보유특별공제 배제",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20100301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 1000000000,
            "acquisition_price": 300000000,
            "holding_years": 14.58,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
        },
    },

    # ── 연립·다세대 추가 ─────────────────────────────────────────────────────
    {
        "label": "빌라(연립) 1주택 — 비조정지역 2년 이상 보유 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20210301",
            "property_type": "연립다세대",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 380000000,
            "acquisition_price": 290000000,
            "holding_years": 3.58,
            "residence_years": 2.5,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },
    {
        "label": "다세대 — 2주택, 비조정지역 일반세율",
        "category": "일반과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20180601",
            "property_type": "연립다세대",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 320000000,
            "acquisition_price": 190000000,
            "holding_years": 6.5,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 단독·전원주택 추가 ───────────────────────────────────────────────────
    {
        "label": "전원주택 — 지방 비조정지역, 10년 이상 거주 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20110601",
            "property_type": "단독주택",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 500000000,
            "acquisition_price": 180000000,
            "holding_years": 13.42,
            "residence_years": 12.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 신축/준공 후 첫 양도 ─────────────────────────────────────────────────
    {
        "label": "신축 단독주택 — 건축주 직접 신축, 취득일 기산 이슈",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20140601",
            "property_type": "단독주택",
            "acquisition_reason": "신축",
            "household_house_count": 1,
            "transfer_price": 780000000,
            "acquisition_price": 350000000,
            "holding_years": 10.33,
            "residence_years": 8.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
        },
    },

    # ── 임대사업자 등록 말소 후 ───────────────────────────────────────────────
    {
        "label": "임대등록 말소 후 — 거주주택 비과세 특례 (조특§97의3)",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20190301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 950000000,
            "acquisition_price": 620000000,
            "holding_years": 5.75,
            "residence_years": 2.5,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "residence_exemption_reason": "임대등록말소"
            },
        },
    },

    # ── 해외주택 보유자 ───────────────────────────────────────────────────────
    {
        "label": "해외주택 보유 국내 1주택자 — 국내주택 1주택 비과세",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241101",
            "acquisition_date": "20200601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 900000000,
            "acquisition_price": 680000000,
            "holding_years": 4.42,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
            "has_overseas_house": True,
        },
    },
    {
        "label": "국내 2주택 + 해외주택 — 국내 다주택자 중과 기준 적용",
        "category": "중과",
        "fact_json": {
            "transfer_date": "20241201",
            "acquisition_date": "20180301",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 950000000,
            "acquisition_price": 500000000,
            "holding_years": 6.75,
            "residence_years": 1.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": True,
            "has_overseas_house": True,
        },
    },

    # ── 일시적2주택 + 조정지역 신규 취득 ────────────────────────────────────
    {
        "label": "일시적2주택 — 신규주택 조정지역 취득, 종전주택 1년 내 양도 요건",
        "category": "비과세",
        "fact_json": {
            "transfer_date": "20241001",
            "acquisition_date": "20180601",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 900000000,
            "acquisition_price": 380000000,
            "holding_years": 6.33,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": True,
            "special_cases": {
                "temp_two_house": {
                    "new_acquisition_date": "20231001",
                    "old_house_must_sell_by": "20241001",
                    "new_is_adjustment_area": True,
                }
            },
        },
    },
]

CATEGORY_LABELS = {
    "비과세": "🟢 비과세",
    "감면": "🔵 감면",
    "중과": "🔴 중과",
    "일반과세": "🟡 일반과세",
    "단기세율": "🔴 단기세율",
    "고가주택": "🟠 고가주택",
    "사실관계부족": "⚪ 사실관계부족",
}
