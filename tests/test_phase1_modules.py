"""
Phase 1 신규 모듈 단위 테스트 — 외부 서비스 불필요.
"""
import pytest
from datetime import date
from src.ingestion.collect import _build_chunk_id
from src.domain.tax_constants import TaxConstantsRegistry
from src.domain.date_resolver import resolve_acquisition_date
from src.domain.acquisition_timeline import (
    resolve_effective_acquisition_date,
    resolve_holding_period_years,
    is_rollover_period_active,
    AcquisitionTimelineResult,
)
from src.domain.confirmation import check_confirmation, CONFIRMATION_ITEMS


class TestTaxConstantsRegistry:
    def test_high_value_threshold_returns_1_2_billion(self):
        val = TaxConstantsRegistry.get("HIGH_VALUE_THRESHOLD", date(2024, 1, 1))
        assert val == 1_200_000_000

    def test_sangsaeng_window_end_returns_2024(self):
        val = TaxConstantsRegistry.get("SANGSAENG_WINDOW_END", date(2024, 1, 1))
        assert val.year == 2024

    def test_iota_period_10_years_after_2023(self):
        val = TaxConstantsRegistry.get("IOTA_PERIOD_YEARS", date(2023, 6, 1))
        assert val == 10

    def test_iota_period_5_years_before_2023(self):
        val = TaxConstantsRegistry.get("IOTA_PERIOD_YEARS", date(2022, 6, 1))
        assert val == 5

    def test_unknown_key_raises_key_error(self):
        with pytest.raises(KeyError):
            TaxConstantsRegistry.get("NONEXISTENT_KEY", date(2024, 1, 1))

    def test_ltshd_table1_has_15_year_rate(self):
        table = TaxConstantsRegistry.get("LONG_TERM_DEDUCTION_RATE_TABLE1", date(2024, 1, 1))
        assert 15 in table
        assert table[15] == 0.30

    def test_ltshd_table2_has_20_year_rate(self):
        table = TaxConstantsRegistry.get("LONG_TERM_DEDUCTION_RATE_TABLE2", date(2024, 1, 1))
        assert 20 in table
        assert table[20] == 0.80


class TestDateResolver:
    def test_min_of_balance_and_registration(self):
        result = resolve_acquisition_date(
            balance_payment_date=date(2023, 5, 10),
            registration_date=date(2023, 5, 20),
        )
        assert result == date(2023, 5, 10)

    def test_registration_earlier_than_balance(self):
        result = resolve_acquisition_date(
            balance_payment_date=date(2023, 5, 20),
            registration_date=date(2023, 5, 10),
        )
        assert result == date(2023, 5, 10)

    def test_only_balance_date(self):
        result = resolve_acquisition_date(
            balance_payment_date=date(2023, 5, 10),
            registration_date=None,
        )
        assert result == date(2023, 5, 10)

    def test_only_registration_date(self):
        result = resolve_acquisition_date(
            balance_payment_date=None,
            registration_date=date(2023, 5, 15),
        )
        assert result == date(2023, 5, 15)

    def test_fallback_to_contract_date_when_both_none(self):
        result = resolve_acquisition_date(
            balance_payment_date=None,
            registration_date=None,
            contract_date=date(2023, 4, 1),
        )
        assert result == date(2023, 4, 1)

    def test_all_none_returns_none(self):
        result = resolve_acquisition_date(None, None)
        assert result is None


class TestAcquisitionTimeline:
    def test_gift_rollover_within_10_years(self):
        result = resolve_effective_acquisition_date(
            declared_acquisition_date=date(2020, 1, 1),
            transfer_date=date(2028, 1, 1),
            acquisition_reason="증여",
            donor_acquisition_date=date(2010, 1, 1),
            gift_date=date(2020, 1, 1),
            is_gift_from_spouse_or_lineal=True,
            iota_period_years=10,
        )
        assert result.effective_acquisition_date == date(2010, 1, 1)
        assert result.rollover_applies is True

    def test_gift_rollover_expired_after_10_years(self):
        result = resolve_effective_acquisition_date(
            declared_acquisition_date=date(2010, 1, 1),
            transfer_date=date(2025, 1, 1),
            acquisition_reason="증여",
            donor_acquisition_date=date(2005, 1, 1),
            gift_date=date(2010, 1, 1),
            is_gift_from_spouse_or_lineal=True,
            iota_period_years=10,
        )
        # 15년 경과 → 이월과세 기간 만료 → 원칙 적용
        assert result.rollover_applies is False
        assert result.effective_acquisition_date == date(2010, 1, 1)

    def test_inheritance_uses_deceased_acquisition_date(self):
        result = resolve_effective_acquisition_date(
            declared_acquisition_date=date(2022, 1, 1),
            transfer_date=date(2025, 1, 1),
            acquisition_reason="상속",
            deceased_original_acquisition_date=date(2015, 6, 1),
        )
        assert result.effective_acquisition_date == date(2015, 6, 1)
        assert result.is_successor_period is True
        assert result.rollover_applies is False

    def test_reconstruction_uses_original_house_date(self):
        result = resolve_effective_acquisition_date(
            declared_acquisition_date=date(2020, 1, 1),
            transfer_date=date(2025, 1, 1),
            acquisition_reason="재건축",
            original_house_acquisition_date=date(2005, 3, 1),
        )
        assert result.effective_acquisition_date == date(2005, 3, 1)

    def test_default_uses_declared_date(self):
        result = resolve_effective_acquisition_date(
            declared_acquisition_date=date(2018, 1, 1),
            transfer_date=date(2025, 1, 1),
            acquisition_reason="매매",
        )
        assert result.effective_acquisition_date == date(2018, 1, 1)
        assert result.rollover_applies is False

    def test_holding_period_years_calculation(self):
        timeline = AcquisitionTimelineResult(
            effective_acquisition_date=date(2018, 1, 1),
            holding_period_base_date=date(2018, 1, 1),
            is_successor_period=False,
            rollover_applies=False,
            source_rule="test",
        )
        years = resolve_holding_period_years(timeline, date(2025, 1, 1))
        assert abs(years - 7.0) < 0.1

    def test_is_rollover_period_active_within_period(self):
        assert is_rollover_period_active(date(2020, 1, 1), date(2025, 1, 1), iota_period_years=10) is True

    def test_is_rollover_period_active_expired(self):
        assert is_rollover_period_active(date(2010, 1, 1), date(2025, 1, 1), iota_period_years=10) is False


class TestConfirmationGate:
    def test_none_confirmed_passes_through(self):
        result = check_confirmation(None)
        assert result.can_proceed is True

    def test_all_confirmed_passes(self):
        confirmed = {k: True for k in CONFIRMATION_ITEMS}
        result = check_confirmation(confirmed)
        assert result.can_proceed is True
        assert result.unconfirmed_items == []

    def test_missing_one_item_blocks(self):
        confirmed = {k: True for k in CONFIRMATION_ITEMS}
        key = list(CONFIRMATION_ITEMS.keys())[0]
        confirmed[key] = False
        result = check_confirmation(confirmed)
        assert result.can_proceed is False
        assert key in result.unconfirmed_items

    def test_empty_dict_blocks_all(self):
        result = check_confirmation({})
        assert result.can_proceed is False
        assert len(result.unconfirmed_items) == len(CONFIRMATION_ITEMS)

    def test_partial_confirmation_blocks(self):
        confirmed = {"household_house_count_verified": True}
        result = check_confirmation(confirmed)
        assert result.can_proceed is False
        assert "household_house_count_verified" not in result.unconfirmed_items


class TestChunkIdFormat:
    """collect.py _build_chunk_id — Pinecone ASCII 포맷 검증"""

    def test_normal_article_format(self):
        chunk_id = _build_chunk_id("285523", "소득세법", "89", "20240101")
        assert chunk_id == "285523_ita_a89_20240101"

    def test_buchik_article_uses_raw_number(self):
        chunk_id = _build_chunk_id("285523", "소득세법", "부칙1", "20240101")
        assert chunk_id == "285523_ita_bch1_20240101"

    def test_empty_article_number_uses_unknown(self):
        chunk_id = _build_chunk_id("285523", "소득세법", "", "20240101")
        assert chunk_id == "285523_ita_unk_20240101"

    def test_empty_effective_date_uses_zeros(self):
        chunk_id = _build_chunk_id("285523", "소득세법", "89", "")
        assert chunk_id == "285523_ita_a89_00000000"

    def test_unknown_law_name_uses_unknown_code(self):
        long_name = "a" * 30
        chunk_id = _build_chunk_id("285523", long_name, "89", "20240101")
        parts = chunk_id.split("_")
        assert parts[1] == "unk"

    def test_spaces_removed_from_law_name(self):
        chunk_id = _build_chunk_id("285523", "소득세법 시행령", "154", "20230101")
        assert chunk_id == "285523_itd_a154_20230101"
        assert " " not in chunk_id

    def test_조세특례제한법_article(self):
        chunk_id = _build_chunk_id("285907", "조세특례제한법", "99", "20231201")
        assert chunk_id == "285907_sta_a99_20231201"
