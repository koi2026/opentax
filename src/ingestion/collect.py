"""
법령 데이터 수집 스크립트
www.law.go.kr DRF API → data/raw/ (XML) + data/processed/ (JSON chunks)

버전 관리 전략:
- 각 법령의 개정 이력을 모두 수집 (최근 YEARS_BACK년)
- 각 버전(MST)에 effective_date + expiration_date 부여
- chunk ID = {version_mst}_{law_slug}_{article_slug}_{eff_slug} → 버전별 고유성 + 가독성 보장
"""
import json
import ssl
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import requests
import urllib3
from requests.adapters import HTTPAdapter

from src.config import LAW_API_BASE_URL, LAW_API_OC

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OC = LAW_API_OC
BASE_URL = LAW_API_BASE_URL
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
YEARS_BACK = 30  # 최근 N년치 개정 버전 수집 (취득일 소급 대응)


def _make_session() -> requests.Session:
    """law.go.kr SSL 호환성 우선 세션 — 재시도 3회 포함"""
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=urllib3.Retry(total=3, backoff_factor=2))
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = False  # law.go.kr TLS 핸드셰이크 호환성
    session.headers.update({"User-Agent": "Mozilla/5.0 (tax-rag collector)"})
    return session


_SESSION = _make_session()

TARGET_LAWS = [
    # 소득세법 계열 — §89 비과세, §104 중과, §154 거주요건
    {"name": "소득세법",                    "mst": "285523", "category": "법률"},
    {"name": "소득세법 시행령",              "mst": "285631", "category": "대통령령"},
    {"name": "소득세법 시행규칙",            "mst": "284987", "category": "부령"},
    # 조세특례제한법 계열 — 일시적2주택, 상생임대, 농어촌주택, 공익수용 등
    {"name": "조세특례제한법",              "mst": "285907", "category": "법률"},
    {"name": "조세특례제한법 시행령",        "mst": "286053", "category": "대통령령"},
    {"name": "조세특례제한법 시행규칙",      "mst": "284611", "category": "부령"},
    # 지방세법 계열 — 양도소득세 지방소득세 10% 연동
    {"name": "지방세법",                    "mst": "282559", "category": "법률"},
    {"name": "지방세법 시행령",             "mst": "285497", "category": "대통령령"},
    {"name": "지방세법 시행규칙",           "mst": "282705", "category": "부령"},
    # 국세기본법 계열 — 가산세, 경정청구, 부당행위계산부인 §39
    {"name": "국세기본법",                  "mst": "280373", "category": "법률"},
    {"name": "국세기본법 시행령",           "mst": "283623", "category": "대통령령"},
    {"name": "국세기본법 시행규칙",         "mst": "284607", "category": "부령"},
    # 상속세 및 증여세법 계열 — 이월과세(§97의2) 증여 기준 조회용
    {"name": "상속세 및 증여세법",          "mst": "276123", "category": "법률"},
    {"name": "상속세 및 증여세법 시행령",   "mst": "283637", "category": "대통령령"},
]


# ── 버전 이력 조회 ────────────────────────────────────────────────────────────

def fetch_law_version_list(law_name: str) -> list[dict]:
    """
    법령명으로 개정 이력 상의 모든 버전 조회.
    반환: [{"mst", "effective_date", "promulgation_date", "expiration_date"}, ...]
    시행일 오름차순 정렬, 만료일 자동 계산.
    """
    url = f"{BASE_URL}/lawSearch.do"
    params = {
        "OC": OC,
        "target": "law",
        "query": law_name,
        "display": 100,
        "type": "XML",
    }
    resp = _SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    try:
        root = ET.fromstring(resp.text.encode("utf-8"))
    except ET.ParseError:
        print(f"  ⚠ {law_name} 이력 XML 파싱 실패, 현행 버전만 사용")
        return []

    cutoff = (datetime.now() - timedelta(days=YEARS_BACK * 365)).strftime("%Y%m%d")

    versions = []
    for law_elem in root.findall(".//법령"):
        name_elem = law_elem.find("법령명한글")
        if name_elem is None or name_elem.text is None:
            continue
        if name_elem.text.strip() != law_name:
            continue

        mst_elem = law_elem.find("법령일련번호")
        eff_elem = law_elem.find("시행일자")
        prom_elem = law_elem.find("공포일자")

        if mst_elem is None or mst_elem.text is None:
            continue

        eff_date = eff_elem.text.strip() if eff_elem is not None and eff_elem.text else ""
        if eff_date and eff_date < cutoff:
            continue

        versions.append({
            "mst": mst_elem.text.strip(),
            "effective_date": eff_date,
            "promulgation_date": prom_elem.text.strip() if prom_elem is not None and prom_elem.text else "",
            "expiration_date": "",
        })

    if not versions:
        return []

    # 시행일 오름차순 정렬
    versions.sort(key=lambda x: x["effective_date"])

    # 만료일 = 다음 버전 시행일 전날
    for i, v in enumerate(versions[:-1]):
        next_eff = versions[i + 1]["effective_date"]
        if next_eff:
            exp_dt = datetime.strptime(next_eff, "%Y%m%d") - timedelta(days=1)
            v["expiration_date"] = exp_dt.strftime("%Y%m%d")

    # 마지막(현행) 버전은 만료일 없음
    return versions


# ── XML 수집 ──────────────────────────────────────────────────────────────────

def fetch_law_xml(mst: str) -> str:
    url = f"{BASE_URL}/lawService.do"
    params = {"OC": OC, "target": "law", "MST": mst, "type": "XML"}
    resp = _SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


# ── XML 파싱 → 청크 ───────────────────────────────────────────────────────────

import re

# 부칙 적용례 앵커 키워드 → applicability_anchor 값
_BUCHIK_ANCHOR_PATTERNS: list[tuple[str, str]] = [
    (r"양도하는\s*분부터", "transfer_date"),
    (r"양도분부터",         "transfer_date"),
    (r"취득하는\s*분부터", "acquisition_date"),
    (r"취득분부터",         "acquisition_date"),
    (r"계약을?\s*체결하는?\s*분부터", "contract_date"),
    (r"계약분부터",         "contract_date"),
    (r"증여받는?\s*분부터", "gift_date"),
    (r"증여분부터",         "gift_date"),
    (r"상속이\s*개시되는?\s*분부터", "death_date"),
    (r"상속분부터",         "death_date"),
]


def _extract_buchik_anchor(text: str) -> str:
    """
    부칙 텍스트에서 적용 기준(앵커)을 추출한다.
    "이 법 시행 이후 양도하는 분부터 적용" → "transfer_date"
    "취득분부터" → "acquisition_date"
    매칭 없으면 "effective_date" (시행일 기준 기본값).
    """
    for pattern, anchor in _BUCHIK_ANCHOR_PATTERNS:
        if re.search(pattern, text):
            return anchor
    return "effective_date"


# Pinecone vector ID ASCII 전용 — 법령명 → 짧은 코드 매핑
_LAW_ASCII_CODES: dict[str, str] = {
    "소득세법":              "ita",
    "소득세법시행령":         "itd",
    "소득세법시행규칙":       "itr",
    "조세특례제한법":         "sta",
    "조세특례제한법시행령":   "std",
    "조세특례제한법시행규칙": "stx",
    "지방세법":              "lta",
    "지방세법시행령":         "ltd",
    "지방세법시행규칙":       "ltr",
    "국세기본법":             "fta",
    "국세기본법시행령":       "ftd",
    "국세기본법시행규칙":     "ftr",
    "상속세및증여세법":       "iha",
    "상속세및증여세법시행령": "ihd",
}


def _build_chunk_id(version_mst: str, law_name: str, 조문번호: str, 시행일자: str) -> str:
    """
    Pinecone ASCII 전용 chunk ID: {mst}_{law_code}_{art_code}_{eff}
    예) 285523_ita_a89_20240101  (소득세법 제89조)
        285523_ita_bch1_20240101 (소득세법 부칙 제1조)
        285523_sta_a97_3_20240101 (조세특례제한법 제97조의3 → a97_3)
    """
    law_key = law_name.replace(" ", "")
    law_code = _LAW_ASCII_CODES.get(law_key, "unk")

    if not 조문번호:
        art_code = "unk"
    elif "부칙" in 조문번호:
        digits = re.sub(r"[^0-9]", "", 조문번호)
        art_code = f"bch{digits}" if digits else "bch"
    elif "별표" in 조문번호:
        digits = re.sub(r"[^0-9]", "", 조문번호)
        art_code = f"tbl{digits}" if digits else "tbl"
    else:
        # 제89조 → a89, 제97조의3 → a97_3
        norm = re.sub(r"[^0-9의]", "", 조문번호).replace("의", "_")
        art_code = f"a{norm}" if norm else "unk"

    eff_slug = 시행일자[:8] if 시행일자 else "00000000"
    return f"{version_mst}_{law_code}_{art_code}_{eff_slug}"


def parse_xml_to_chunks(xml_text: str, law_info: dict, version: dict) -> list[dict]:
    """
    version: {"mst", "effective_date", "promulgation_date", "expiration_date"}
    chunk ID = {version_mst}_{law_slug}_{article_slug}_{eff_slug}
    예) 285523_소득세법_제89조_20240101
    """
    root = ET.fromstring(xml_text.encode("utf-8"))
    chunks = []

    law_name_elem = root.find(".//법령명한글")
    law_name = law_name_elem.text.strip() if law_name_elem is not None else law_info["name"]

    for 조문단위 in root.findall(".//조문단위"):
        조문번호_elem = 조문단위.find("조문번호")
        조문여부_elem = 조문단위.find("조문여부")
        조문제목_elem = 조문단위.find("조문제목")
        시행일자_elem = 조문단위.find("조문시행일자")
        내용_elem = 조문단위.find("조문내용")

        조문번호 = 조문번호_elem.text.strip() if 조문번호_elem is not None and 조문번호_elem.text else ""
        조문여부 = 조문여부_elem.text.strip() if 조문여부_elem is not None and 조문여부_elem.text else ""
        조문제목 = 조문제목_elem.text.strip() if 조문제목_elem is not None and 조문제목_elem.text else ""
        시행일자 = 시행일자_elem.text.strip() if 시행일자_elem is not None and 시행일자_elem.text else version["effective_date"]
        내용 = 내용_elem.text.strip() if 내용_elem is not None and 내용_elem.text else ""

        항_list = []
        for 항 in 조문단위.findall(".//항"):
            항번호_elem = 항.find("항번호")
            항내용_elem = 항.find("항내용")
            호_list = []
            for 호 in 항.findall(".//호"):
                호번호_elem = 호.find("호번호")
                호내용_elem = 호.find("호내용")
                호_list.append({
                    "호번호": 호번호_elem.text.strip() if 호번호_elem is not None and 호번호_elem.text else "",
                    "호내용": 호내용_elem.text.strip() if 호내용_elem is not None and 호내용_elem.text else "",
                })
            항_list.append({
                "항번호": 항번호_elem.text.strip() if 항번호_elem is not None and 항번호_elem.text else "",
                "항내용": 항내용_elem.text.strip() if 항내용_elem is not None and 항내용_elem.text else "",
                "호": 호_list,
            })

        if not 내용 and not 항_list:
            continue

        full_text_parts = []
        if 내용:
            full_text_parts.append(내용)
        for 항 in 항_list:
            if 항["항내용"]:
                full_text_parts.append(f"  {항['항내용']}")
            for 호 in 항["호"]:
                if 호["호내용"]:
                    full_text_parts.append(f"    {호['호내용']}")

        # 별표 이미지 태그 감지 (manual_review_required 플래그)
        is_table_article = "별표" in 조문제목 or "별표" in 조문번호
        has_image_placeholder = "<그림>" in 내용 or "[그림]" in 내용
        manual_review_required = is_table_article or has_image_placeholder

        full_text = "\n".join(full_text_parts)

        # 부칙 적용례 앵커 추출: "양도분/취득분/계약분/증여분" → applicability_anchor
        # 구조적 필터링 기반 — LLM 판단에만 의존하는 것보다 훨씬 안정적
        applicability_anchor = "effective_date"  # 기본값 (시행일 기준)
        if 조문여부 == "부칙":
            applicability_anchor = _extract_buchik_anchor(full_text)
            if applicability_anchor != "effective_date":
                print(f"  → 부칙 적용례 감지: {law_name} {조문번호} — anchor={applicability_anchor}")

        chunk = {
            "id": _build_chunk_id(version["mst"], law_name, 조문번호, 시행일자),
            "law_name": law_name,
            "law_mst": law_info["mst"],          # 법령 고유 ID (버전 무관)
            "version_mst": version["mst"],        # 이 버전의 MST
            "law_category": law_info["category"],
            "article_number": 조문번호,
            "article_type": 조문여부,  # "본문" | "부칙" — 부칙은 경과조치, 별도 청크로 분리됨
            "article_title": 조문제목,
            "effective_date": 시행일자,
            "expiration_date": version["expiration_date"],  # 빈 문자열 = 현행
            "promulgation_date": version["promulgation_date"],
            "content": 내용,
            "clauses": 항_list,
            "full_text": full_text,
            "applicability_anchor": applicability_anchor,  # "transfer_date"|"acquisition_date"|"contract_date"|"gift_date"|"death_date"|"effective_date"
            "manual_review_required": manual_review_required,
            "metadata": {
                "law_name": law_name,
                "article": 조문번호,
                "article_number": 조문번호,
                "article_title": 조문제목,
                "effective_date": 시행일자,
                "expiration_date": version["expiration_date"],
                "category": law_info["category"],
                "version_mst": version["mst"],
                "applicability_anchor": applicability_anchor,
                "source": "law.go.kr",
            },
        }
        if manual_review_required:
            print(f"  ⚠ [manual_review_required] {law_name} {조문번호} — 별표/이미지 수동 검토 필요")
        chunks.append(chunk)

    # 부칙 ID 목록 수집 후 본칙 청크에 linked_buchik_ids 주입
    # 같은 버전(MST) 의 부칙은 본칙 전체에 적용될 수 있으므로 전부 연결
    buchik_ids = [c["id"] for c in chunks if c.get("article_type") == "부칙"]
    if buchik_ids:
        for c in chunks:
            if c.get("article_type") != "부칙":
                c["linked_buchik_ids"] = buchik_ids
    # 부칙 청크에는 빈 리스트 (부칙끼리 순환참조 방지)
    for c in chunks:
        if "linked_buchik_ids" not in c:
            c["linked_buchik_ids"] = []

    # 중복 chunk_id 처리 — 같은 조문의 항/호별 청크가 동일 ID를 갖는 경우 카운터로 구별
    from collections import defaultdict
    id_counter: dict = defaultdict(int)
    for c in chunks:
        base_id = c["id"]
        count = id_counter[base_id]
        if count > 0:
            c["id"] = f"{base_id}_c{count}"
        id_counter[base_id] += 1

    return chunks


# ── 메인 수집 ─────────────────────────────────────────────────────────────────

def collect_all():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks = []

    for law in TARGET_LAWS:
        print(f"\n[{law['name']}] 개정 이력 조회 중...")

        # 버전 목록 조회
        versions = fetch_law_version_list(law["name"])

        if not versions:
            # 이력 조회 실패 시 현행 버전 단독 수집
            # effective_date=0, expiration_date=99991231 → Pinecone 날짜 필터에서 항상 통과
            print(f"  → 이력 없음, 현행 버전만 수집 (MST={law['mst']})")
            versions = [{
                "mst": law["mst"],
                "effective_date": "0",
                "promulgation_date": "",
                "expiration_date": "99991231",
            }]
        else:
            # 현행 MST가 목록에 없으면 추가
            existing_msts = {v["mst"] for v in versions}
            if law["mst"] not in existing_msts:
                versions.append({
                    "mst": law["mst"],
                    "effective_date": "",
                    "promulgation_date": "",
                    "expiration_date": "",
                })
            print(f"  → {len(versions)}개 버전 발견")

        law_chunks = []
        for v in versions:
            raw_path = RAW_DIR / f"{law['name'].replace(' ', '_')}_{v['mst']}.xml"

            if raw_path.exists():
                xml_text = raw_path.read_text(encoding="utf-8")
                print(f"  → 캐시 사용: {v['mst']} (시행일: {v['effective_date'] or '불명'})")
            else:
                try:
                    xml_text = fetch_law_xml(v["mst"])
                    raw_path.write_text(xml_text, encoding="utf-8")
                    print(f"  → XML 저장: {v['mst']} (시행일: {v['effective_date'] or '불명'}, {len(xml_text):,} bytes)")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"  ⚠ {v['mst']} 수집 실패: {e}")
                    continue

            chunks = parse_xml_to_chunks(xml_text, law, v)
            print(f"     청크: {len(chunks)}개 | 만료일: {v['expiration_date'] or '현행'}")
            law_chunks.extend(chunks)

        # 법령별 통합 JSON
        processed_path = PROCESSED_DIR / f"{law['name'].replace(' ', '_')}_{law['mst']}.json"
        processed_path.write_text(
            json.dumps(law_chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        all_chunks.extend(law_chunks)

    # 전체 통합 JSON
    all_path = PROCESSED_DIR / "all_chunks.json"
    all_path.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[완료] 총 {len(all_chunks)}개 청크 → {all_path}")
    return all_chunks


if __name__ == "__main__":
    collect_all()
