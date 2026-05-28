"""
RAG 쿼리 입력 스키마 — 사실관계 → 법령 검색 입력값

커버리지 갭 반영 (v3):
- transfer_price 추가 → 고가주택(12억 초과) 판단 가능
- PropertyType enum → 분양권/입주권/다가구/겸용주택 구분
- 조정대상지역 취득시/양도시 명시적 분리 유지
- residence_periods 복수 기간 → 합산 2년 계산 가능
- 특례별 상세 dataclass → 일시적2주택/상속/장기임대/혼인합산
- DateBundle에 관리처분계획인가일 추가 → 조합원입주권
- SangsaengRentalDetail → 상생임대 5개 요건 검증 (소령 §155의3)
- ResidenceExemptionType → 거주요건 면제/단축 특례 통합 관리
  (상생임대 / 임대사업자거주주택 / 해외이주 / 취학근무 / 수용)
- to_text() 도메인 키워드 명시 → 벡터 검색 정확도 향상
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

from .tax_constants import TaxConstantsRegistry as _TCR

# backward-compat aliases — use TaxConstantsRegistry.get() for version-aware lookups
HIGH_VALUE_THRESHOLD: int = _TCR.get("HIGH_VALUE_THRESHOLD", date.today())
SANGSAENG_WINDOW_START: date = _TCR.get("SANGSAENG_WINDOW_START", date.today())
SANGSAENG_WINDOW_END: date = _TCR.get("SANGSAENG_WINDOW_END", date.today())
SANGSAENG_MAX_INCREASE_RATE: float = _TCR.get("SANGSAENG_MAX_INCREASE_RATE", date.today())
HEAVY_TAX_SUSPENSION_END: date = _TCR.get("HEAVY_TAX_SUSPENSION_END", date.today())


# ── Enums ──────────────────────────────────────────────────────────────────


class TaxType(str, Enum):
    TRANSFER = "transfer"
    GIFT = "gift"
    INHERITANCE = "inheritance"


class PropertyType(str, Enum):
    """
    세법상 판단 경로가 달라지는 주택 유형.
    asset_kind(자유형 텍스트)와 별개로 라우팅용으로 사용.
    """
    APARTMENT = "아파트"
    HOUSE = "단독주택"
    VILLA = "연립다세대"
    DAGAGU = "다가구"            # 전체 1동 = 1주택 (소득세법 시행령 §155⑮)
    GYEOMYONG = "겸용주택"       # 주거+상가 혼합 — 주거 비율로 판단
    SUBSCRIPTION_RIGHT = "분양권"   # 2021.01.01 이후 취득분 주택 수 산입
    ASSOCIATION_RIGHT = "입주권"    # 조합원입주권 — 관리처분계획인가일 기준
    OFFICETEL_RESIDENTIAL = "주거용오피스텔"
    OFFICETEL_COMMERCIAL = "업무용오피스텔"
    RURAL_HOUSE = "농어촌주택"   # 조특법 §99의4 — 별도 요건
    LAND = "토지"
    COMMERCIAL = "상가"


class AcquisitionReason(str, Enum):
    PURCHASE = "매매"
    SUBSCRIPTION = "분양"
    INHERITANCE = "상속"
    GIFT = "증여"
    BURDEN_GIFT = "부담부증여"
    DIVORCE = "이혼재산분할"
    AUCTION = "경매"
    RECONSTRUCTION = "재건축"
    REDEVELOPMENT = "재개발"
    EXPROPRIATION = "수용"
    MARRIAGE_MERGE = "혼인합가"


class EntityScope(str, Enum):
    """Stage 1 Symbolic Filter 최상위 분류 — PropertyType보다 넓은 단위"""
    HOUSE = "주택"
    LAND = "토지"
    BUNYANG_RIGHT = "분양권"
    IPJU_RIGHT = "입주권"
    COMMERCIAL = "상가"
    OFFICETEL_RESIDENTIAL = "주거용오피스텔"
    OFFICETEL_COMMERCIAL = "업무용오피스텔"
    STOCK = "주식"


class SpecialEventType(str, Enum):
    INHERITANCE_OPENED = "상속개시일"
    GIFT_EXECUTED = "증여일"
    RECONSTRUCTION_COMPLETED = "재건축준공일"
    MANAGEMENT_DISPOSAL_APPROVED = "관리처분계획인가일"  # 조합원입주권 기산일
    EXPROPRIATION_DECIDED = "수용결정일"
    LOT_CONVERSION = "환지처분일"
    DEEMED_ACQUISITION = "의제취득일"   # 1985-01-01 기준시가 적용


# ── Date 관련 ──────────────────────────────────────────────────────────────


@dataclass
class SpecialEventDate:
    event_type: SpecialEventType
    date: date


@dataclass
class DateBundle:
    """
    법령 버전 앵커 묶음.

    부칙 경과조치 패턴 예시:
      "이 법 시행 후 양도분 적용. 단 2018-09-13 이전 취득분은 종전 규정."
      → transfer_date AND acquisition_date 둘 다 필요.

    조합원입주권:
      관리처분계획인가일이 취득시기 기산점 → special_event_dates에 포함.
    """
    transfer_date: date
    acquisition_date: date
    contract_date: Optional[date] = None
    balance_payment_date: Optional[date] = None   # 잔금청산일
    registration_date: Optional[date] = None      # 등기접수일
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


# ── 거주 기간 ───────────────────────────────────────────────────────────────


@dataclass
class ResidencePeriod:
    """
    단일 거주 구간.
    실거주 요건(2년 이상)은 복수 입·퇴거 구간의 합산으로 계산.
    end_date=None이면 현재 거주 중.
    """
    start_date: date
    end_date: Optional[date] = None

    def days(self, as_of: Optional[date] = None) -> int:
        end = self.end_date or (as_of or date.today())
        return max(0, (end - self.start_date).days)


def total_residence_years(periods: List[ResidencePeriod], as_of: Optional[date] = None) -> float:
    return sum(p.days(as_of) for p in periods) / 365.25


# ── 특례 상세 ──────────────────────────────────────────────────────────────


@dataclass
class TempTwoHouseDetail:
    """
    일시적 2주택 비과세 특례 (소득세법 시행령 §155①).
    신규주택 취득 후 종전주택을 기한 내 양도해야 비과세.
    조정대상지역 여부에 따라 기한이 달라짐(1년 vs 3년).
    """
    new_acquisition_date: date
    old_house_must_sell_by: date     # 종전주택 양도 기한
    new_is_adjustment_area: bool     # 신규주택이 조정대상지역인지
    # 기한 이내 양도 여부는 transfer_date와 비교해서 판단


@dataclass
class InheritanceDetail:
    """
    상속주택 특례 — 3가지 별도 경로.

    경로 A (소령 §155②): 상속주택 + 일반주택 동시 보유 → 일반주택 양도 시 비과세
    경로 B (소령 §155③): 상속주택 자체 양도 → 피상속인 보유기간 합산
    경로 C (소령 §155④ 준용): 동거봉양 합가 상속 → CohabitationCareDetail 별도

    공동상속 시:
      최대지분자가 상속주택 보유자로 간주.
      지분 동일 → 거주자, 최연장자 순으로 1인 지정.
    """
    death_date: date
    same_household_at_death: bool        # 사망 전 동일세대 여부
    inherited_as_only_house: bool        # 상속 당시 상속인이 무주택이었는지
    selling_inherited_house: bool        # True: 상속주택 양도(경로B) / False: 일반주택 양도(경로A)
    donor_acquisition_date: Optional[date] = None  # 피상속인 원취득일 (경로 B 필수, 경로 A 불필요)

    # 공동상속 상세
    is_joint_inheritance: bool = False
    inheritance_share_pct: float = 100.0   # 본인 지분율 (%)
    is_largest_share_holder: bool = True   # 최대지분 보유 여부
    is_designated_holder: bool = False     # 지분 동일 시 지정 보유자 여부

    inherited_holding_years: Optional[float] = None  # 피상속인 보유기간 (경로 B 자동계산용)


@dataclass
class LongTermRentalDetail:
    """
    장기임대주택 감면 특례 (조특법 §97의3~§97의5).
    의무임대기간, 임대료 증액 제한 준수가 핵심 요건.
    """
    registration_date: date               # 임대사업자 등록일
    mandatory_period_years: int           # 의무임대기간 (4/8/10년)
    mandatory_period_fulfilled: bool      # 의무임대기간 충족 여부
    rent_increase_limit_complied: bool    # 임대료 5% 증액 제한 준수 여부


class ResidenceExemptionType(str, Enum):
    """
    거주요건(2년) 면제 또는 단축 특례 유형.
    해당 시 RAG 쿼리에 조문 키워드를 명시적으로 포함해야 함.
    """
    SANGSAENG_RENTAL = "상생임대"              # 소령 §155의3 — 거주요건 전면 면제
    RENTAL_BUSINESS_OWN_HOUSE = "임대사업자거주주택"  # 소령 §155⑳ — 2년 거주 유지
    OVERSEAS_EMIGRATION = "해외이주"           # 소령 §154①2호 — 거주요건 면제
    UNAVOIDABLE_RELOCATION = "취학근무부득이"  # 소령 §154②  — 1년 이상 거주 시 면제
    EXPROPRIATION = "수용"                    # 소령 §154③  — 거주요건 면제


@dataclass
class SangsaengRentalDetail:
    """
    상생임대주택 특례 (소득세법 시행령 §155의3, 2022.02.15 신설).

    조정대상지역 내 주택이라도 상생임대 5개 요건을 모두 충족하면
    1세대 1주택 비과세의 '거주기간 2년' 요건이 면제됨.

    요건:
    ① 계약 체결일: SANGSAENG_WINDOW_START ~ SANGSAENG_WINDOW_END
    ② 직전 임대차계약 존재 (신규 임차인 불가)
    ③ 임대료 인상률 5% 이내
    ④ 실제 임대기간 2년 이상
    ⑤ 양도 시점 조정대상지역 — (RAGQueryInput.fact_vector에서 확인)

    ①~④는 이 객체에서 검증. ⑤는 adjustment_area_at_transfer로 확인.
    """
    contract_date: date              # 상생임대차계약 체결일
    contract_period_months: int      # 실제 임대기간 (월 수)
    previous_monthly_rent: int       # 직전 계약 월세 (전세는 환산월세)
    new_monthly_rent: int            # 상생임대 계약 월세
    has_prior_contract: bool         # 직전 임대차계약 존재 여부 (요건 ②)

    @property
    def increase_rate(self) -> float:
        if self.previous_monthly_rent <= 0:
            return float("inf")
        return (self.new_monthly_rent - self.previous_monthly_rent) / self.previous_monthly_rent

    @property
    def contract_in_window(self) -> bool:
        window_start: date = _TCR.get("SANGSAENG_WINDOW_START", self.contract_date)
        window_end: date = _TCR.get("SANGSAENG_WINDOW_END", self.contract_date)
        return window_start <= self.contract_date <= window_end

    @property
    def requirements_met(self) -> bool:
        """① 계약일 범위 ② 직전계약 존재 ③ 5% 이내 ④ 2년 이상"""
        max_rate: float = _TCR.get("SANGSAENG_MAX_INCREASE_RATE", self.contract_date)
        return (
            self.contract_in_window
            and self.has_prior_contract
            and self.increase_rate <= max_rate
            and self.contract_period_months >= 24
        )

    @property
    def residence_requirement_waived(self) -> bool:
        """거주요건 면제 여부 — requirements_met이 True여야 적용"""
        return self.requirements_met


@dataclass
class MarriageMergeDetail:
    """
    혼인 합산 2주택 특례 (소득세법 시행령 §155①⑤).
    혼인 전 각자 1주택 → 혼인 후 1세대 2주택 → 5년 이내 양도 시 비과세.
    """
    marriage_date: date
    spouse_house_count_before_marriage: int
    own_house_count_before_marriage: int


@dataclass
class GyeomyongDetail:
    """
    겸용주택 (소득세법 §89①3호, 시행령 §154⑦).
    주거면적 비율이 50% 이상이면 전체를 주택으로 보아 비과세 가능.
    """
    total_area_sqm: float
    residential_area_sqm: float

    @property
    def residential_ratio(self) -> float:
        if self.total_area_sqm <= 0:
            return 0.0
        return self.residential_area_sqm / self.total_area_sqm

    @property
    def qualifies_as_house(self) -> bool:
        return self.residential_ratio >= 0.5


@dataclass
class DagaguDetail:
    """
    다가구주택 (소득세법 시행령 §155⑮).
    1동 전체를 단독소유 시 1세대 1주택으로 취급.
    구분소유(일부 세대 매도) 시에는 별도 과세.
    """
    total_units: int              # 전체 임대 세대 수
    owner_occupies_one_unit: bool # 소유자가 1세대로 직접 거주하는지
    is_single_ownership: bool = True  # 1인 단독소유 (공동소유면 False)


@dataclass
class ReconstructionDetail:
    """
    재건축/재개발 조합원입주권 (소득세법 §89①3호나목, 시행령 §156의2).

    보유기간 기산: 종전주택 취득일 ~ 관리처분계획인가일 + 신축주택 입주일 ~ 양도일 합산.
    원조합원: 종전주택 취득일부터 보유기간 인정.
    승계조합원: 입주권 취득일부터만 인정 → 보유기간 불리.
    청산금 수령 시: 그 부분 비례 양도로 과세.
    """
    is_original_member: bool              # 원조합원(True) vs 승계조합원(False)
    management_disposal_date: date        # 관리처분계획인가일 (취득시기 기산점)
    original_house_acquisition_date: date # 종전주택 취득일 (원조합원 보유기간 기산)
    original_house_area_sqm: float        # 종전주택 전용면적

    demolition_date: Optional[date] = None   # 철거일
    completion_date: Optional[date] = None   # 준공일
    move_in_date: Optional[date] = None      # 입주일

    # 청산금 — 수령/납부에 따라 과세 방식 분기
    paid_liquidation_amount: int = 0      # 추가 납부 부담금 (취득가에 가산)
    received_liquidation_amount: int = 0  # 청산금 수령 (수령분 비례 과세)


@dataclass
class RolloverTaxationDetail:
    """
    이월과세 (소득세법 §97의2).
    배우자/직계존비속에게 증여받은 자산을 일정 기간 내 양도 시
    증여자의 원취득가액·원취득일을 적용해 과세 (증여 절세 방지).

    이월과세 적용 기간:
      - 2023년 이전 증여: 증여일로부터 5년 이내
      - 2023년 이후 증여: 증여일로부터 10년 이내 (2023.01.01 개정)

    원취득 정보 없이 배우자/직계 여부만 확인된 경우 partial 상태로 생성되며,
    L2 fact_checker가 원취득 정보 누락을 critical missing으로 차단한다.
    """
    is_gift_from_spouse_or_lineal: bool      # 배우자/직계존비속 증여 여부
    gift_date: date                          # 증여일
    original_donor_acquisition_date: Optional[date] = None   # 증여자 원취득일 (누락 시 L2 차단)
    original_donor_acquisition_price: Optional[int] = None   # 증여자 원취득가액 (누락 시 L2 차단)

    @property
    def iota_period_years(self) -> int:
        """이월과세 적용 기간 — Registry에서 증여일 기준으로 조회."""
        from .tax_constants import TaxConstantsRegistry
        return TaxConstantsRegistry.get("IOTA_PERIOD_YEARS", self.gift_date, anchor_key="gift_date")

    @property
    def iota_applies(self) -> bool:
        """이월과세 적용 여부 — 기간 내 양도인지는 transfer_date와 비교 필요"""
        return self.is_gift_from_spouse_or_lineal


@dataclass
class CohabitationCareDetail:
    """
    동거봉양 합가 특례 (소득세법 시행령 §155④).
    60세 이상 or 중증질환 직계존속과 합가 후 10년 이내 먼저 양도하는 주택 비과세.
    합가 당시 각자 1주택 보유가 전제.
    """
    cohabitation_start_date: date    # 합가일
    parent_age_at_merge: int         # 합가 당시 직계존속 나이
    parent_has_severe_illness: bool  # 중증질환 여부 (나이 미달 시 대체 요건)

    @property
    def age_requirement_met(self) -> bool:
        return self.parent_age_at_merge >= 60 or self.parent_has_severe_illness


@dataclass
class ExpropiationDetail:
    """
    수용/공익사업 (소득세법 시행령 §154①단서).
    협의취득도 수용과 동일하게 거주요건 면제 적용.
    현금보상 외 채권·대토 보상은 과세 특례 별도 적용(조특법 §77).
    """
    acquisition_type: str   # "compulsory"(강제수용) | "negotiated"(협의취득) | "voluntary"(자진매각)
    compensation_type: str  # "cash"(현금) | "bond"(채권) | "land"(대토)
    is_main_residence: bool = False  # 수용된 주택이 1세대1주택 실거주 주택인지 (§154 거주요건면제 조건)

    @property
    def residence_exemption_applies(self) -> bool:
        """§154①단서: 강제/협의 수용 + 실거주 주택이어야 거주요건 면제. 비거주 주택은 §77 감면 트랙."""
        return self.acquisition_type in ("compulsory", "negotiated") and self.is_main_residence


@dataclass
class NonResidentDetail:
    """
    비거주자 상세 (소득세법 §121②).
    비거주자는 원칙적으로 1세대1주택 비과세 불가.
    예외: 해외이주 후 2년 이내 양도는 비과세 가능 (소령 §154①2호나목).
    """
    departure_date: date
    departure_reason: str   # "overseas_dispatch"(해외파견) | "emigration"(해외이주) | "other"
    # 해외이주 후 2년 이내 양도: 비과세 예외 적용 가능
    # departure_to_transfer_months는 transfer_date - departure_date로 계산

    @property
    def emigration_exemption_possible(self) -> bool:
        """해외이주자 비과세 예외 — 이주 후 2년 이내 조건은 transfer_date와 비교 필요"""
        return self.departure_reason == "emigration"


# ── SpecialCaseFlags ───────────────────────────────────────────────────────


@dataclass
class SpecialCaseFlags:
    """
    특례 케이스 집합 — boolean 플래그 + 각 특례의 상세 정보.
    플래그가 True면 대응하는 detail이 있어야 조문 검색이 정확해짐.
    """
    # 소득세법 시행령 §155 계열
    is_temporary_two_house: bool = False
    temp_two_house: Optional[TempTwoHouseDetail] = None

    is_inherited_house: bool = False
    inheritance: Optional[InheritanceDetail] = None

    is_marriage_merge: bool = False
    marriage_merge: Optional[MarriageMergeDetail] = None

    # 조특법 §97의3 계열
    is_long_term_rental_registered: bool = False
    long_term_rental: Optional[LongTermRentalDetail] = None

    # 겸용주택
    is_gyeomyong: bool = False
    gyeomyong: Optional[GyeomyongDetail] = None

    # 분양권/입주권 2021년 기준
    # True = 2021-01-01 이전 취득 → 주택 수 미산입
    # False = 이후 취득 → 주택 수 산입
    # None = 분양권/입주권 아님
    bunyang_acquired_before_2021: Optional[bool] = None

    # 증여 취득 관련
    donor_same_household_at_gift: Optional[bool] = None

    # 비거주자
    is_non_resident: bool = False
    non_resident: Optional[NonResidentDetail] = None

    # 농어촌주택 (조특법 §99의4)
    is_rural_house: bool = False

    # 이월과세 (소득세법 §97의2) — 배우자/직계 증여 후 기간 내 양도
    rollover_taxation: Optional[RolloverTaxationDetail] = None

    # 재건축/재개발
    is_reconstruction: bool = False
    reconstruction: Optional[ReconstructionDetail] = None

    # 동거봉양합가 (소령 §155④)
    is_cohabitation_care: bool = False
    cohabitation_care: Optional[CohabitationCareDetail] = None

    # 다가구주택 상세
    dagagu: Optional[DagaguDetail] = None

    # 수용/공익사업 상세
    expropriation: Optional[ExpropiationDetail] = None

    # 1세대 판정 결과 (별도 세대판정 모듈의 출력을 여기에 싣는다 — 내부 계산 금지)
    # Codex 권고: 세대판정 로직은 상위 모듈, RAG에는 결과만 전달
    household_is_separate: Optional[bool] = None   # None = 판정 불필요/미완료
    household_determination_basis: Optional[str] = None  # 판정 근거 코드

    # ── 거주요건 면제/단축 특례 (통합 관리) ──────────────────────────────
    # 상생임대, 해외이주, 취학·근무, 수용 등 거주 2년 요건이 면제/단축되는 경우
    # 이 플래그가 True이면 to_text()에 해당 조문 키워드 삽입 필수
    residence_requirement_exempted: bool = False
    residence_exemption_type: Optional[ResidenceExemptionType] = None

    # 상생임대 상세 (소령 §155의3)
    # 장기임대(민간임대주택법 등록 + 의무기간)와 완전히 다른 제도
    sangsaeng_rental: Optional[SangsaengRentalDetail] = None

    def active_flags(self) -> List[str]:
        """활성화된 특례 목록 — to_text()용"""
        result = []
        if self.is_temporary_two_house:
            result.append("일시적2주택")
        if self.is_inherited_house:
            result.append("상속주택")
        if self.is_marriage_merge:
            result.append("혼인합산2주택")
        if self.is_long_term_rental_registered:
            years = self.long_term_rental.mandatory_period_years if self.long_term_rental else "?"
            result.append(f"장기임대등록{years}년")
        if self.sangsaeng_rental:
            waived = "거주요건면제" if self.sangsaeng_rental.residence_requirement_waived else "요건미충족"
            result.append(f"상생임대주택{waived}")
        if self.residence_requirement_exempted and self.residence_exemption_type:
            if self.residence_exemption_type != ResidenceExemptionType.SANGSAENG_RENTAL:
                result.append(f"거주요건면제_{self.residence_exemption_type.value}")
        if self.is_gyeomyong and self.gyeomyong:
            ratio = int(self.gyeomyong.residential_ratio * 100)
            result.append(f"겸용주택주거{ratio}%")
        if self.bunyang_acquired_before_2021 is not None:
            result.append("분양권" + ("2021전" if self.bunyang_acquired_before_2021 else "2021후"))
        if self.is_non_resident:
            nd = self.non_resident
            if nd and nd.emigration_exemption_possible:
                result.append("비거주자_해외이주2년이내양도가능")
            else:
                result.append("비거주자")
        if self.is_rural_house:
            result.append("농어촌주택")
        if self.rollover_taxation and self.rollover_taxation.iota_applies:
            period = self.rollover_taxation.iota_period_years
            result.append(f"이월과세{period}년이내")
        if self.is_reconstruction:
            mb = "원조합원" if (self.reconstruction and self.reconstruction.is_original_member) else "승계조합원"
            result.append(f"재건축재개발{mb}")
        if self.is_cohabitation_care:
            result.append("동거봉양합가")
        if self.expropriation:
            if self.expropriation.residence_exemption_applies:
                result.append(f"수용_{self.expropriation.acquisition_type}_거주요건면제")
            else:
                result.append("수용_조특77감면")  # 비거주 주택 수용 → §77 감면 트랙
        return result

    def residence_exemption_article(self) -> Optional[str]:
        """
        거주요건 면제 해당 조문 — to_text()에 삽입할 법령 키워드 반환.
        벡터 검색이 올바른 조문을 찾으려면 조문 번호가 쿼리에 있어야 함.
        """
        article_map = {
            ResidenceExemptionType.SANGSAENG_RENTAL: "소득세법시행령제155조의3 상생임대주택 거주요건면제",
            ResidenceExemptionType.RENTAL_BUSINESS_OWN_HOUSE: "소득세법시행령제155조제20항 임대사업자거주주택",
            ResidenceExemptionType.OVERSEAS_EMIGRATION: "소득세법시행령제154조제1항제2호 해외이주거주요건면제",
            ResidenceExemptionType.UNAVOIDABLE_RELOCATION: "소득세법시행령제154조제2항 취학근무부득이거주요건",
            ResidenceExemptionType.EXPROPRIATION: "소득세법시행령제154조제3항 수용거주요건면제",
        }
        return article_map.get(self.residence_exemption_type)


# ── FactVector ─────────────────────────────────────────────────────────────


@dataclass
class FactVector:
    """
    Stage 2 벡터 검색용 사실관계.

    to_text()가 핵심 — 도메인 키워드를 명시적으로 포함해야
    벡터 검색이 올바른 조문(1세대1주택비과세, 장기보유특별공제 등)을 찾음.
    """

    # --- 자산 식별 ---
    property_type: PropertyType           # 라우팅용 유형
    asset_kind: str                       # 자유형 텍스트 (아파트/단독 등)

    # --- 거래 기본 ---
    acquisition_reason: AcquisitionReason

    # 세대 전체 주택 수 — 반드시 COMPUTED 값 (포함/제외 판단 적용 후)
    # 원시값(물리적 보유 수) 아님. 포함/제외 판단 예:
    #   분양권 2021+ = 포함, 분양권 2021- = 제외
    #   상속주택 5년 이내 = 제외, 지방저가주택(3억↓) = 제외 가능
    #   장기임대등록 충족 = 제외 가능
    # ※ Codex 권고: 이상적으로는 holdings[] → computed_count 구조가 맞지만
    #   현 단계에서는 사전 계산된 값을 여기 싣는다.
    household_house_count: int

    # --- 가액 (고가주택 판단 필수) ---
    transfer_price: Optional[int] = None      # 양도가액 (원)
    acquisition_price: Optional[int] = None   # 취득가액 (원)

    # --- 조정대상지역 (시점별 분리 — 판단 기준이 다름) ---
    # 취득일 기준: 거주 2년 요건 발생 여부 결정
    # 양도일 기준: 다주택자 중과세율 적용 여부 결정
    adjustment_area_at_acquisition: bool = False
    adjustment_area_at_transfer: bool = False

    # --- 보유/거주 기간 ---
    holding_period_years: float = 0.0         # 자동계산 (transfer - acquisition)
    residence_periods: List[ResidencePeriod] = field(default_factory=list)
    # 단일 값이 필요한 곳을 위한 편의 합산 (직접 입력 금지)
    residence_period_years: float = 0.0

    # --- 특례 ---
    special_cases: SpecialCaseFlags = field(default_factory=SpecialCaseFlags)

    # --- 기타 라우팅 ---
    joint_ownership_yn: bool = False
    overseas_residence_yn: bool = False
    rental_business_yn: bool = False
    transfer_date_val: Optional[date] = None   # 경과 연수 계산용 (to_text 내부)

    # 특수관계자간 거래 (소득세법 §101 부당행위계산부인)
    # 배우자·직계존비속·지배법인 등에 저가 양도 시 시가로 재계산됨
    # → 계산된 양도차익·비과세 범위가 완전히 달라질 수 있음
    # JSON 입력에서 항상 받아야 하는 필드 — None은 "미확인" 상태
    is_related_party_transaction: Optional[bool] = None
    related_party_type: Optional[str] = None  # "배우자" | "직계존비속" | "법인" | "주주" | "기타"

    @property
    def is_high_value_house(self) -> bool:
        """고가주택 여부 (양도가액 12억 초과) — 비과세 전액 불가, 초과분 과세"""
        if self.transfer_price is None:
            return False
        return self.transfer_price > HIGH_VALUE_THRESHOLD

    def to_text(self) -> str:
        """
        벡터 임베딩용 텍스트.
        도메인 키워드(고가주택, 분양권, 조합원입주권 등)를 명시적으로 포함.
        키워드가 없으면 유사 조문이 검색되지 않음.
        """
        lines = [
            f"주택유형: {self.property_type.value}",
            f"취득원인: {self.acquisition_reason.value}",
            f"세대보유주택수: {self.household_house_count}주택",
        ]

        # 가액 — 고가주택 키워드 명시
        if self.transfer_price is not None:
            label = "고가주택" if self.is_high_value_house else "일반주택"
            lines.append(f"양도가액: {self.transfer_price:,}원 ({label})")
        if self.acquisition_price is not None:
            lines.append(f"취득가액: {self.acquisition_price:,}원")

        # 조정대상지역 — 취득시/양도시 명시
        lines.append(
            f"조정대상지역_취득시: {'해당' if self.adjustment_area_at_acquisition else '비해당'}"
        )
        lines.append(
            f"조정대상지역_양도시: {'해당' if self.adjustment_area_at_transfer else '비해당'}"
        )

        # 보유/거주
        lines.append(f"보유기간: {self.holding_period_years:.1f}년")
        if self.residence_periods:
            total_yrs = total_residence_years(self.residence_periods)
            lines.append(f"실거주기간합산: {total_yrs:.1f}년 ({len(self.residence_periods)}구간)")
        elif self.residence_period_years:
            lines.append(f"거주기간: {self.residence_period_years:.1f}년")

        # 특례 키워드
        active = self.special_cases.active_flags()
        if active:
            lines.append(f"특례해당: {' / '.join(active)}")

        # 거주요건 면제 — 조문 번호 명시 (이게 없으면 §155의3 등을 검색 못 함)
        if self.special_cases.residence_requirement_exempted:
            article_kw = self.special_cases.residence_exemption_article()
            if article_kw:
                lines.append(f"거주요건면제근거: {article_kw}")

        # 이월과세 — 조문 키워드 없으면 §97의2 검색 안 됨
        rt = self.special_cases.rollover_taxation
        if rt and rt.iota_applies:
            donor_date = str(rt.original_donor_acquisition_date) if rt.original_donor_acquisition_date else "미확인"
            donor_price = f"{rt.original_donor_acquisition_price:,}원" if rt.original_donor_acquisition_price is not None else "미확인"
            lines.append(
                f"이월과세적용: 소득세법제97조의2 배우자직계증여후{rt.iota_period_years}년이내양도 "
                f"증여자원취득일{donor_date} 원취득가액{donor_price}"
            )

        # 재건축/재개발 — 관리처분계획인가일 조문 키워드
        rc = self.special_cases.reconstruction
        if rc:
            member_type = "원조합원" if rc.is_original_member else "승계조합원"
            lines.append(
                f"재건축재개발: {member_type} 관리처분계획인가일{rc.management_disposal_date} "
                f"종전주택취득일{rc.original_house_acquisition_date} "
                f"소득세법시행령제156조의2"
            )

        # 일시적2주택 — 종전주택 양도기한 + 기한 초과 여부 명시
        td = self.special_cases.temp_two_house
        if td:
            if self.transfer_date_val:
                deadline_ok = self.transfer_date_val <= td.old_house_must_sell_by
                label = "기한이내_특례적용" if deadline_ok else "기한초과_특례미적용"
            else:
                label = ""
            lines.append(
                f"일시적2주택: 신규취득일{td.new_acquisition_date} "
                f"종전주택양도기한{td.old_house_must_sell_by}"
                + (f" {label}" if label else "")
                + " 소득세법시행령제155조제1항"
            )

        # 상속주택 — 사망일 및 5년 경과 여부
        inh = self.special_cases.inheritance
        if inh:
            path = "상속주택자체양도" if inh.selling_inherited_house else "일반주택양도"
            if self.transfer_date_val:
                yrs = (self.transfer_date_val - inh.death_date).days / 365.25
                window = "5년이내_주택수제외" if yrs < 5 else "5년초과_주택수산입"
                lines.append(
                    f"상속주택: 사망일{inh.death_date} {path} 경과{yrs:.1f}년 {window} "
                    "소득세법시행령제155조제2항"
                )
            else:
                lines.append(f"상속주택: 사망일{inh.death_date} {path} 소득세법시행령제155조제2항")

        # 동거봉양합가 — 10년 경과 여부
        cc = self.special_cases.cohabitation_care
        if cc:
            if self.transfer_date_val:
                yrs = (self.transfer_date_val - cc.cohabitation_start_date).days / 365.25
                window = "10년이내_특례적용" if yrs < 10 else "10년초과_특례미적용"
                lines.append(
                    f"동거봉양합가: 합가일{cc.cohabitation_start_date} 경과{yrs:.1f}년 {window} "
                    "소득세법시행령제155조제4항"
                )
            else:
                lines.append(
                    f"동거봉양합가: 합가일{cc.cohabitation_start_date} 소득세법시행령제155조제4항"
                )

        # 수용/공익사업
        exp = self.special_cases.expropriation
        if exp:
            if exp.residence_exemption_applies:
                lines.append(
                    f"수용공익사업: {exp.acquisition_type} 보상유형{exp.compensation_type} "
                    "거주요건면제 소득세법시행령제154조제1항단서"
                )
            else:
                lines.append(
                    f"수용공익사업: {exp.acquisition_type} 보상유형{exp.compensation_type} "
                    "조세특례제한법제77조감면신청"
                )

        # 특수관계자간 거래 — §101 부당행위계산부인 조문 키워드 명시
        if self.is_related_party_transaction:
            party = self.related_party_type or "특수관계자"
            lines.append(
                f"특수관계자거래: {party} 소득세법제101조 부당행위계산부인 "
                "시가기준양도가액재계산 저가양도"
            )

        # 공동명의
        if self.joint_ownership_yn:
            lines.append("공동명의: 해당")

        # 비거주자
        if self.overseas_residence_yn or self.special_cases.is_non_resident:
            lines.append("비거주자: 해당")

        # 프로퍼티 타입별 키워드 보강
        if self.property_type == PropertyType.SUBSCRIPTION_RIGHT:
            before = self.special_cases.bunyang_acquired_before_2021
            if before is True:
                lines.append("분양권 2021년이전취득 주택수미산입")
            elif before is False:
                lines.append("분양권 2021년이후취득 주택수산입")
        elif self.property_type == PropertyType.ASSOCIATION_RIGHT:
            lines.append("조합원입주권 관리처분계획인가일 주택수산입")
        elif self.property_type == PropertyType.DAGAGU:
            lines.append("다가구주택 1동전체1주택")
        elif self.property_type == PropertyType.GYEOMYONG:
            if self.special_cases.gyeomyong:
                ratio = int(self.special_cases.gyeomyong.residential_ratio * 100)
                lines.append(f"겸용주택 주거비율{ratio}%")

        return "\n".join(lines)


# ── RAGQueryInput ──────────────────────────────────────────────────────────


@dataclass
class RAGQueryInput:
    """
    RAG 법령 검색 최종 입력.

    Stage 1 (Symbolic Filter):
      date_bundle + tax_type + entity_scope
      → 전체 청크에서 법적으로 유효한 버전 후보 집합 추출

    Stage 2 (Vector Rerank):
      fact_vector.to_text() 임베딩 → 후보 내 의미적 관련도 순위
    """
    date_bundle: DateBundle
    tax_type: TaxType
    entity_scope: EntityScope
    fact_vector: FactVector

    top_k: int = 10
    include_buchik: bool = True   # 부칙 자동 포함 (경과조치/적용례 누락 방지)

    @classmethod
    def from_fact_ledger(
        cls,
        fact_ledger: dict,
        owner_profile: dict,
        user_property: dict,
    ) -> "RAGQueryInput":
        """
        기존 DB 레코드에서 RAGQueryInput 생성.
        user_property의 컬럼명은 orm.py / transfer.yaml 기준.
        """
        date_bundle = _build_date_bundle(user_property)
        special_cases = _build_special_cases(fact_ledger, user_property)
        fact_vector = _build_fact_vector(owner_profile, user_property, special_cases, fact_ledger)

        return cls(
            date_bundle=date_bundle,
            tax_type=TaxType.TRANSFER,
            entity_scope=_resolve_entity_scope(user_property),
            fact_vector=fact_vector,
        )


# ── 내부 빌더 함수 ─────────────────────────────────────────────────────────


def _build_date_bundle(up: dict) -> DateBundle:
    bundle = DateBundle(
        transfer_date=date.fromisoformat(up["transfer_date"]),
        acquisition_date=date.fromisoformat(up["acquisition_date"]),
        contract_date=_pd(up.get("contract_date")),
        balance_payment_date=_pd(up.get("balance_payment_date")),
        registration_date=_pd(up.get("registration_date")),
    )
    # 조합원입주권 — 관리처분계획인가일 추가
    if mgmt := _pd(up.get("management_disposal_date")):
        bundle.special_event_dates.append(
            SpecialEventDate(SpecialEventType.MANAGEMENT_DISPOSAL_APPROVED, mgmt)
        )
    # 상속개시일
    if death := _pd(up.get("death_date")):
        bundle.special_event_dates.append(
            SpecialEventDate(SpecialEventType.INHERITANCE_OPENED, death)
        )
    return bundle


def _build_special_cases(fl: dict, up: dict) -> SpecialCaseFlags:
    sc = SpecialCaseFlags()

    # 일시적 2주택
    if fl.get("is_temporary_two_house"):
        sc.is_temporary_two_house = True
        if (nd := _pd(fl.get("temp_new_acquisition_date"))) and (sd := _pd(fl.get("temp_old_must_sell_by"))):
            sc.temp_two_house = TempTwoHouseDetail(
                new_acquisition_date=nd,
                old_house_must_sell_by=sd,
                new_is_adjustment_area=bool(fl.get("temp_new_is_adjustment_area")),
            )

    # 상속주택 — 경로 A (일반주택 양도) 또는 경로 B (상속주택 양도)
    # 경로 A: 양도 대상은 일반주택(매매 취득)이지만 세대가 상속주택을 보유
    #   → fact_ledger에 selling_inherited_house=False로 신호
    # 경로 B: 상속받은 주택 자체를 양도 → acquisition_cause == "상속"
    is_inheritance_acquisition = up.get("acquisition_cause") == "상속"
    has_inheritance_flags = "selling_inherited_house" in fl
    if is_inheritance_acquisition or has_inheritance_flags:
        sc.is_inherited_house = True
        death = _pd(up.get("death_date") or fl.get("death_date"))
        if death:
            sc.inheritance = InheritanceDetail(
                death_date=death,
                same_household_at_death=bool(
                    fl.get("deceased_same_household") or up.get("deceased_same_household")
                ),
                inherited_as_only_house=bool(
                    fl.get("inherited_as_only_house") or up.get("inherited_as_only_house")
                ),
                selling_inherited_house=bool(
                    fl.get("selling_inherited_house", is_inheritance_acquisition)
                ),
                donor_acquisition_date=_pd(
                    fl.get("donor_acquisition_date") or up.get("donor_acquisition_date")
                ),
                inherited_holding_years=(
                    float(v) if (v := (fl.get("inherited_holding_years") or up.get("inherited_holding_years"))) is not None else None
                ),
            )

    # 혼인합산
    if up.get("acquisition_cause") == "혼인합가":
        sc.is_marriage_merge = True
        if md := _pd(fl.get("marriage_date")):
            sc.marriage_merge = MarriageMergeDetail(
                marriage_date=md,
                spouse_house_count_before_marriage=int(fl.get("spouse_house_count_before_marriage", 1)),
                own_house_count_before_marriage=int(fl.get("own_house_count_before_marriage", 1)),
            )

    # 장기임대
    if up.get("long_term_rental_yn"):
        sc.is_long_term_rental_registered = True
        if rd := _pd(up.get("rental_registration_date")):
            sc.long_term_rental = LongTermRentalDetail(
                registration_date=rd,
                mandatory_period_years=int(up.get("mandatory_rental_years", 8)),
                mandatory_period_fulfilled=bool(up.get("mandatory_period_fulfilled")),
                rent_increase_limit_complied=bool(up.get("rent_increase_limit_complied")),
            )

    # 상생임대 (소령 §155의3) — 장기임대와 별개
    if fl.get("sangsaeng_rental_yn") or up.get("sangsaeng_rental_yn"):
        if cd := _pd(fl.get("sangsaeng_contract_date") or up.get("sangsaeng_contract_date")):
            detail = SangsaengRentalDetail(
                contract_date=cd,
                contract_period_months=int(fl.get("sangsaeng_period_months", 24)),
                previous_monthly_rent=int(fl.get("sangsaeng_prev_rent", 0)),
                new_monthly_rent=int(fl.get("sangsaeng_new_rent", 0)),
                has_prior_contract=bool(fl.get("sangsaeng_has_prior_contract", True)),
            )
            sc.sangsaeng_rental = detail
            if detail.residence_requirement_waived:
                sc.residence_requirement_exempted = True
                sc.residence_exemption_type = ResidenceExemptionType.SANGSAENG_RENTAL

    # 기타 거주요건 면제 특례
    exemption_reason = fl.get("residence_exemption_reason") or up.get("residence_exemption_reason")
    if exemption_reason and not sc.residence_requirement_exempted:
        exemption_map = {
            "해외이주": ResidenceExemptionType.OVERSEAS_EMIGRATION,
            "취학": ResidenceExemptionType.UNAVOIDABLE_RELOCATION,
            "근무": ResidenceExemptionType.UNAVOIDABLE_RELOCATION,
            "직장이전": ResidenceExemptionType.UNAVOIDABLE_RELOCATION,
            "요양": ResidenceExemptionType.UNAVOIDABLE_RELOCATION,
            "수용": ResidenceExemptionType.EXPROPRIATION,
            "임대사업자거주주택": ResidenceExemptionType.RENTAL_BUSINESS_OWN_HOUSE,
            "임대등록말소": ResidenceExemptionType.RENTAL_BUSINESS_OWN_HOUSE,
        }
        for keyword, etype in exemption_map.items():
            if keyword in str(exemption_reason):
                sc.residence_requirement_exempted = True
                sc.residence_exemption_type = etype
                break

    # 겸용주택
    if up.get("asset_kind") == "겸용주택":
        sc.is_gyeomyong = True
        total = float(up.get("total_area_sqm") or 0)
        residential = float(up.get("residential_area_sqm") or 0)
        if total > 0:
            sc.gyeomyong = GyeomyongDetail(total_area_sqm=total, residential_area_sqm=residential)

    # 이월과세 — is_gift_from_spouse_or_lineal=True가 명시된 경우에만 생성
    # 단순 "증여" 취득이더라도 배우자/직계 여부가 확인되지 않으면 생성하지 않음
    # → fact_checker Rule #2가 "is_gift_from_spouse_or_lineal" 재확인 요청
    if fl.get("is_gift_from_spouse_or_lineal"):
        gd = _pd(up.get("gift_date") or fl.get("gift_date"))
        if gd:
            sc.rollover_taxation = RolloverTaxationDetail(
                is_gift_from_spouse_or_lineal=True,
                gift_date=gd,
                original_donor_acquisition_date=_pd(fl.get("original_donor_acquisition_date")),
                original_donor_acquisition_price=_parse_int(fl.get("original_donor_acquisition_price")),
            )

    # 재건축/재개발
    if up.get("asset_kind") in ("입주권",) or fl.get("is_reconstruction"):
        if odat2 := _pd(up.get("original_house_acquisition_date")):
            sc.is_reconstruction = True
            sc.reconstruction = ReconstructionDetail(
                is_original_member=bool(fl.get("is_original_member", True)),
                management_disposal_date=_pd(up.get("management_disposal_date") or fl.get("management_disposal_date")) or odat2,
                original_house_acquisition_date=odat2,
                original_house_area_sqm=float(fl.get("original_house_area_sqm", 0)),
                demolition_date=_pd(fl.get("demolition_date")),
                completion_date=_pd(fl.get("completion_date")),
                move_in_date=_pd(fl.get("move_in_date")),
                paid_liquidation_amount=int(fl.get("paid_liquidation_amount", 0)),
                received_liquidation_amount=int(fl.get("received_liquidation_amount", 0)),
            )

    # 동거봉양합가
    if fl.get("is_cohabitation_care"):
        if csd := _pd(fl.get("cohabitation_start_date")):
            sc.is_cohabitation_care = True
            sc.cohabitation_care = CohabitationCareDetail(
                cohabitation_start_date=csd,
                parent_age_at_merge=int(fl.get("parent_age_at_merge", 60)),
                parent_has_severe_illness=bool(fl.get("parent_has_severe_illness")),
            )

    # 농어촌주택 (조특법 §99의4)
    if fl.get("is_rural_house") or up.get("asset_kind") == "농어촌주택":
        sc.is_rural_house = True

    # 다가구
    if up.get("asset_kind") == "다가구":
        sc.dagagu = DagaguDetail(
            total_units=int(fl.get("dagagu_units", 1)),
            owner_occupies_one_unit=bool(fl.get("owner_occupies_one_unit", True)),
        )

    # 수용/공익사업
    if fl.get("is_expropriation") or up.get("acquisition_cause") == "수용":
        sc.expropriation = ExpropiationDetail(
            acquisition_type=fl.get("expropriation_type", "compulsory"),
            compensation_type=fl.get("compensation_type", "cash"),
            is_main_residence=bool(fl.get("is_main_residence_for_expropriation", False)),
        )
        if sc.expropriation.residence_exemption_applies and not sc.residence_requirement_exempted:
            sc.residence_requirement_exempted = True
            sc.residence_exemption_type = ResidenceExemptionType.EXPROPRIATION

    # 비거주자
    sc.is_non_resident = bool(up.get("overseas_residence_yn"))
    if sc.is_non_resident:
        if dep := _pd(fl.get("departure_date")):
            sc.non_resident = NonResidentDetail(
                departure_date=dep,
                departure_reason=fl.get("departure_reason", "other"),
            )

    # 분양권/입주권 기준일
    sc.bunyang_acquired_before_2021 = _bunyang_before_2021(up)

    return sc


def _build_fact_vector(op: dict, up: dict, sc: SpecialCaseFlags, fl: dict | None = None) -> FactVector:
    fl = fl or {}
    # 거주 기간 — residence_periods 우선, 없으면 단일 값 fallback
    residence_periods: List[ResidencePeriod] = []
    if raw_periods := up.get("residence_periods"):
        for p in raw_periods:
            residence_periods.append(ResidencePeriod(
                start_date=date.fromisoformat(p["start_date"]),
                end_date=_pd(p.get("end_date")),
            ))

    computed_residence_years = (
        total_residence_years(residence_periods)
        if residence_periods
        else float(up.get("residence_period_years", 0))
    )

    _rpt_raw = up["is_related_party_transaction"] if "is_related_party_transaction" in up else fl.get("is_related_party_transaction")

    return FactVector(
        property_type=_resolve_property_type(up),
        asset_kind=up.get("asset_kind", ""),
        acquisition_reason=_resolve_acquisition_reason(up),
        household_house_count=int(op.get("household_house_count", 1)),
        transfer_price=_parse_int(up.get("sale_price_total")),
        acquisition_price=_parse_int(up.get("acquisition_price")),
        adjustment_area_at_acquisition=bool(up.get("adjustment_area_at_acquisition")),
        adjustment_area_at_transfer=bool(up.get("adjustment_area_at_transfer")),
        holding_period_years=float(up.get("holding_period_years", 0)),
        residence_periods=residence_periods,
        residence_period_years=computed_residence_years,
        special_cases=sc,
        joint_ownership_yn=bool(up.get("joint_ownership_yn")),
        overseas_residence_yn=bool(op.get("overseas_residence_yn")),
        rental_business_yn=bool(up.get("rental_business_yn")),
        is_related_party_transaction=bool(_rpt_raw) if _rpt_raw is not None else None,
        related_party_type=up.get("related_party_type") or fl.get("related_party_type"),
        transfer_date_val=_pd(up.get("transfer_date")),
    )


# ── 유틸 ───────────────────────────────────────────────────────────────────


def _pd(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _parse_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _bunyang_before_2021(up: dict) -> Optional[bool]:
    kind = up.get("asset_kind", "")
    if kind not in ("분양권", "입주권"):
        return None
    acq = _pd(up.get("acquisition_date"))
    if acq is None:
        return None
    return acq < date(2021, 1, 1)


def _resolve_property_type(up: dict) -> PropertyType:
    kind = up.get("asset_kind", "")
    mapping = {
        "아파트": PropertyType.APARTMENT,
        "연립": PropertyType.VILLA,
        "다세대": PropertyType.VILLA,
        "단독주택": PropertyType.HOUSE,
        "다가구": PropertyType.DAGAGU,
        "겸용주택": PropertyType.GYEOMYONG,
        "분양권": PropertyType.SUBSCRIPTION_RIGHT,
        "입주권": PropertyType.ASSOCIATION_RIGHT,
        "주거용오피스텔": PropertyType.OFFICETEL_RESIDENTIAL,
        "업무용오피스텔": PropertyType.OFFICETEL_COMMERCIAL,
        "농어촌주택": PropertyType.RURAL_HOUSE,
        "토지": PropertyType.LAND,
        "상가": PropertyType.COMMERCIAL,
    }
    return mapping.get(kind, PropertyType.APARTMENT)


def _resolve_acquisition_reason(up: dict) -> AcquisitionReason:
    cause = up.get("acquisition_cause", "매매")
    mapping = {
        "매매": AcquisitionReason.PURCHASE,
        "분양": AcquisitionReason.SUBSCRIPTION,
        "상속": AcquisitionReason.INHERITANCE,
        "증여": AcquisitionReason.GIFT,
        "부담부증여": AcquisitionReason.BURDEN_GIFT,
        "이혼재산분할": AcquisitionReason.DIVORCE,
        "경매": AcquisitionReason.AUCTION,
        "재건축": AcquisitionReason.RECONSTRUCTION,
        "재개발": AcquisitionReason.REDEVELOPMENT,
        "수용": AcquisitionReason.EXPROPRIATION,
        "혼인합가": AcquisitionReason.MARRIAGE_MERGE,
    }
    return mapping.get(cause, AcquisitionReason.PURCHASE)


def _resolve_entity_scope(up: dict) -> EntityScope:
    kind = up.get("asset_kind", "")
    scope_map = {
        "아파트": EntityScope.HOUSE,
        "단독주택": EntityScope.HOUSE,
        "다가구": EntityScope.HOUSE,
        "다세대": EntityScope.HOUSE,
        "연립": EntityScope.HOUSE,
        "겸용주택": EntityScope.HOUSE,
        "분양권": EntityScope.BUNYANG_RIGHT,
        "입주권": EntityScope.IPJU_RIGHT,
        "주거용오피스텔": EntityScope.OFFICETEL_RESIDENTIAL,
        "업무용오피스텔": EntityScope.OFFICETEL_COMMERCIAL,
        "토지": EntityScope.LAND,
        "상가": EntityScope.COMMERCIAL,
    }
    return scope_map.get(kind, EntityScope.HOUSE)
