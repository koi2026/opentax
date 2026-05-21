"""
법령 청크 메타데이터 스키마

핵심 설계 결정:
1. 부칙(附則)은 본칙과 분리 청킹 — 본칙만 검색되면 경과조치/적용례 누락
2. applicability_anchors: 이 청크가 "어떤 날짜 기준"으로 적용되는지 명시
3. amendment_type 구분 — 전부개정은 lineage 끊김, 일부개정은 이어짐
4. 타법개정 별도 처리 — 다른 법이 개정하면서 이 법이 바뀌는 silent amendment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional


class LawLevel(str, Enum):
    ACT = "법"                   # 소득세법, 조세특례제한법
    ENFORCEMENT_DECREE = "시행령"
    ENFORCEMENT_RULE = "시행규칙"


class LawId(str, Enum):
    """관리 대상 법령 목록"""
    INCOME_TAX_ACT = "income_tax_act"                          # 소득세법
    INCOME_TAX_DECREE = "income_tax_enforcement_decree"        # 소득세법 시행령
    INCOME_TAX_RULE = "income_tax_enforcement_rule"            # 소득세법 시행규칙
    SPECIAL_TAX_ACT = "special_tax_treatment_act"              # 조세특례제한법
    SPECIAL_TAX_DECREE = "special_tax_treatment_decree"        # 조세특례제한법 시행령
    SPECIAL_TAX_RULE = "special_tax_treatment_rule"            # 조세특례제한법 시행규칙
    LOCAL_TAX_ACT = "local_tax_act"                            # 지방세법
    LOCAL_TAX_DECREE = "local_tax_enforcement_decree"          # 지방세법 시행령
    LOCAL_TAX_RULE = "local_tax_enforcement_rule"              # 지방세법 시행규칙
    FRAMEWORK_TAX_ACT = "framework_tax_act"                    # 국세기본법
    FRAMEWORK_TAX_DECREE = "framework_tax_enforcement_decree"  # 국세기본법 시행령
    FRAMEWORK_TAX_RULE = "framework_tax_enforcement_rule"      # 국세기본법 시행규칙
    INHERITANCE_TAX_ACT = "inheritance_tax_act"                # 상속세 및 증여세법
    INHERITANCE_TAX_DECREE = "inheritance_tax_enforcement_decree"  # 상속세 및 증여세법 시행령


class AmendmentType(str, Enum):
    PARTIAL = "일부개정"     # 조문 lineage 유지
    FULL = "전부개정"        # lineage 끊김 — 새 root로 취급
    OTHER_LAW = "타법개정"   # 다른 법이 이 법을 개정 (silent amendment)
    REPEAL = "폐지"


class AppendixType(str, Enum):
    """
    청킹 단위 구분.
    부칙은 반드시 별도 청크 — 경과조치/적용례가 적용 법령 결정에 핵심.
    """
    MAIN_BODY = "본칙"
    BUCHIK = "부칙"          # 경과조치, 적용례 포함
    BYULTABLE = "별표"       # 세율표, 공제율표
    FORM = "서식"
    REASON = "제개정이유"


class ApplicabilityRuleType(str, Enum):
    """
    이 청크가 적용되는 방식.
    none: 시행일~폐지일 내 transfer_date면 적용 (단순)
    적용례: 특정 행위 시점 기준으로 적용 범위 명시
    경과조치: 시행 전 사실관계에 대한 전환 규정
    의제취득일: 취득일을 법정 간주 처리
    """
    NONE = "none"
    JEOKYONGYE = "적용례"
    GYEONGGWAJOCHIUI = "경과조치"
    DEEMED_DATE = "의제취득일"
    SPECIAL_CASE = "특례"


class ApplicabilityAnchor(str, Enum):
    """
    부칙 적용례가 어떤 날짜 기준으로 적용되는지 구조화.
    수집 시 정규식으로 추출 → Pinecone 메타데이터에 저장 → retriever에서 하드필터 활용.
    """
    TRANSFER_DATE = "transfer_date"          # "이 법 시행 이후 양도하는 분부터"
    ACQUISITION_DATE = "acquisition_date"    # "취득하는 분부터"
    CONTRACT_DATE = "contract_date"          # "계약 체결분부터"
    GIFT_DATE = "gift_date"                  # "증여받는 분부터"
    DEATH_DATE = "death_date"                # "상속이 개시되는 분부터"
    EFFECTIVE_DATE = "effective_date"        # 기본 — 시행일 기준


class TopicTag(str, Enum):
    """검색 후보 필터링용 주제 태그"""
    ONE_HOUSE_EXEMPTION = "1세대1주택비과세"
    LONG_TERM_DEDUCTION = "장기보유특별공제"
    HEAVY_TAX = "다주택중과"
    TEMPORARY_TWO_HOUSE = "일시적2주택"
    INHERITED_HOUSE = "상속주택"
    LONG_TERM_RENTAL = "장기임대주택"
    BUNYANG_RIGHT = "분양권입주권"
    NECESSARY_EXPENSES = "필요경비"
    TAX_RATE = "세율"
    NON_RESIDENT = "비거주자"
    ADJUSTMENT_AREA = "조정대상지역"
    BUSINESS_LAND = "비사업용토지"
    SPECIAL_TAX_REDUCTION = "조특법감면"


@dataclass
class ApplicabilitySpec:
    """
    이 청크가 실제로 적용되는 조건을 구조화.

    anchors: 어떤 날짜를 기준으로 시행일/폐지일을 체크하는지.
             복수 가능 (예: ["transfer_date", "acquisition_date"])

    condition_text: 자연어 조건 — 앵커 날짜 범위 외 추가 조건.
                    LLM이 최종 적용 여부 판단 시 참조.
    예: "이 법 시행 후 양도분부터 적용. 단 2018-09-13 이전 취득분은 종전 규정 적용."
    """
    rule_type: ApplicabilityRuleType
    anchors: List[str] = field(default_factory=lambda: ["transfer_date"])
    condition_text: Optional[str] = None


@dataclass
class LawChunkMetadata:
    """
    법령 청크 1개의 완전한 메타데이터.

    청킹 단위: 조(條) > 항(項) 수준. 너무 세분화하면 맥락 손실,
    너무 크면 여러 적용 regime이 섞임.
    단서/예외 조항은 원칙 조항과 같은 청크 유지 (분리 금지).
    """

    # === Identity ===
    chunk_id: str
    # 예: "income_tax_decree_§154_p1_v20220101_main"
    #     법령ID_조번호_항번호_버전_타입

    law_id: LawId
    law_name: str              # 소득세법 시행령
    law_level: LawLevel

    article_number: str        # 제154조
    paragraph: Optional[str]  # 제1항 (None이면 조 전체)
    item: Optional[str]        # 제1호

    # === Version ===
    lsi_seq: str               # 국가법령정보센터 버전 식별자
    promulgation_date: date    # 공포일
    effective_from: date       # 시행일
    effective_to: Optional[date]  # 폐지일 (None = 현행)

    amendment_type: AmendmentType
    article_lineage_root: str
    # 전부개정이 있으면 새 root 생성. 같은 조번호여도 전부개정 전후는 다른 lineage.

    # === 청크 타입 ===
    appendix_type: AppendixType

    # === Applicability (핵심) ===
    applicability: ApplicabilitySpec

    # === Links ===
    supersedes_chunk_id: Optional[str] = None
    superseded_by_chunk_id: Optional[str] = None

    # 본칙↔부칙 양방향 링크
    # 본칙 청크: 자신에게 적용되는 부칙 청크 ID 목록
    # 부칙 청크: 자신이 수정/규정하는 본칙 청크 ID 목록
    linked_buchik_ids: List[str] = field(default_factory=list)
    parent_main_chunk_id: Optional[str] = None

    cross_refs: List[str] = field(default_factory=list)
    # 예: ["income_tax_act_§89", "special_tax_decree_§97의3"]

    # === Scope Tags (Stage 1 필터용) ===
    entity_scopes: List[str] = field(default_factory=list)
    # 예: ["주택", "분양권"] — EntityScope.value와 매칭
    tax_types: List[str] = field(default_factory=list)
    # 예: ["transfer"]
    topic_tags: List[TopicTag] = field(default_factory=list)

    # === 원본 참조 ===
    source_url: Optional[str] = None
    # 예: https://law.go.kr/LSW/lsLawLinkInfo.do?lsiSeq=XXXXX
    source_hash: Optional[str] = None  # 내용 변경 감지용

    def is_effective_at(self, check_date: date) -> bool:
        """단순 날짜 범위 체크 (Stage 1 1차 필터)"""
        if check_date < self.effective_from:
            return False
        if self.effective_to and check_date > self.effective_to:
            return False
        return True

    def get_applicable_dates(self, date_bundle: "DateBundle") -> List[date]:
        """
        이 청크의 applicability anchor에 해당하는 날짜 목록 반환.
        Stage 1 심화 필터에서 사용.
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
