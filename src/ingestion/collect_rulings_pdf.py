"""
세법집행기준 PDF 파서

data/rulings/pdf_source/*.pdf → data/rulings/pdf/{pdf_stem}_{idx:04d}.json

집행기준 구조:
  소득세법 제89조 【비과세 양도소득】
    89-0 【표제】 내용...
    89-1 【표제】 내용...
  소득세법 제94조 【양도소득의 범위】
    94-0 ...

각 집행기준 항목 1건 = JSON 1개 (embed_rulings.py 호환 스키마)

사용법:
    python -m src.ingestion.collect_rulings_pdf                              # 전체
    python -m src.ingestion.collect_rulings_pdf --file 양도소득세\ 집행기준-2024.pdf
    python -m src.ingestion.collect_rulings_pdf --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PDF_SOURCE_DIR = Path("data/rulings/pdf_source")
PDF_OUT_DIR = Path("data/rulings/pdf")

# 집행기준 항목 패턴: "89-0", "154-2", "155의2-1" 등
_ITEM_PATTERN = re.compile(
    r"^(\d+(?:의\d+)?-\d+)\s*【([^】]*)】",
    re.MULTILINE,
)

# 조문 헤더 패턴: "소득세법 제89조", "제89조의2" 등
_ARTICLE_PATTERN = re.compile(
    r"(?:소득세법|조세특례제한법|지방세법)?\s*제(\d+조(?:의\d+)?)\s*【([^】]*)】"
)

# 관련 조문 추출 패턴
_LAW_REF_PATTERN = re.compile(
    r"(?:소득세법|조특법|지방세법|소득세법 시행령|소득세법 시행규칙)"
    r"[\s제]*\d+조(?:의\d+)?(?:\s*제\d+항)?(?:\s*제\d+호)?"
)


def _extract_articles(text: str) -> list[str]:
    return list(dict.fromkeys(m.group() for m in _LAW_REF_PATTERN.finditer(text)))[:8]


def _extract_keywords(text: str) -> list[str]:
    kws = []
    for kw in ["1세대1주택", "비과세", "중과", "감면", "조정대상지역",
               "이월과세", "상생임대", "일시적2주택", "장기보유특별공제",
               "양도소득세", "고가주택", "거주요건", "보유기간"]:
        if kw in text:
            kws.append(kw)
    return kws


# ── PDF 파싱 ───────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: Path) -> list[dict]:
    """PDF 1개를 파싱해 집행기준 항목 list 반환."""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber 필요: pip install pdfplumber")

    print(f"  파싱: {pdf_path.name}")
    full_text_pages: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"  총 {total}페이지")
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text_pages.append(text)

    full_text = "\n".join(full_text_pages)

    # 집행기준 항목 분리
    records: list[dict] = []
    matches = list(_ITEM_PATTERN.finditer(full_text))

    if not matches:
        # 항목 구분자를 찾지 못한 경우 페이지 단위로 분할
        print("  ⚠ 집행기준 항목 패턴 미검출 — 페이지 단위 분할")
        for i, page_text in enumerate(full_text_pages):
            if len(page_text.strip()) < 50:
                continue
            records.append(_make_record(
                pdf_path.stem, i, f"p{i+1:04d}", "",
                page_text.strip(), pdf_path
            ))
        return records

    for i, match in enumerate(matches):
        item_code = match.group(1)   # "89-0"
        item_title = match.group(2)  # 표제

        # 항목 내용: 이 match ~ 다음 match 시작 전
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()

        # 조문 번호 추출 (item_code에서)
        art_num = item_code.split("-")[0]  # "89" or "155의2"
        article_ref = f"소득세법 제{art_num}조"

        record = _make_record(
            pdf_path.stem, i, item_code, item_title, content, pdf_path,
            article_ref=article_ref,
        )
        records.append(record)

    print(f"  → {len(records)}건 추출")
    return records


def _make_record(
    pdf_stem: str,
    idx: int,
    item_code: str,
    item_title: str,
    content: str,
    pdf_path: Path,
    article_ref: str = "",
) -> dict:
    title = f"[집행기준 {item_code}] {item_title}".strip(" []")
    related = _extract_articles(content)
    if article_ref and article_ref not in related:
        related.insert(0, article_ref)

    return {
        "id": f"pdf_{pdf_stem}_{idx:04d}",
        "title": title,
        "question": item_title,
        "answer": content[:3000],
        "issued_at": _guess_year(pdf_stem),
        "related_articles": related[:8],
        "keywords": _extract_keywords(content),
        "source_type": "pdf",
        "doc_number": item_code,
        "url": "",
        "pdf_source": pdf_path.name,
        "deprecated": False,
    }


def _guess_year(stem: str) -> str:
    """파일명에서 연도 추출. 예: '양도소득세 집행기준-2024' → '20240101'"""
    m = re.search(r"(20\d{2})", stem)
    return f"{m.group(1)}0101" if m else ""


# ── 메인 ────────────────────────────────────────────────────────────────────────

def collect_pdfs(
    pdf_file: str | None = None,
    dry_run: bool = False,
) -> int:
    """
    pdf_source 폴더의 PDF를 모두 파싱해 data/rulings/pdf/ 에 저장.

    Returns:
        저장된 레코드 수
    """
    PDF_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if pdf_file:
        pdfs = [PDF_SOURCE_DIR / pdf_file]
    else:
        pdfs = sorted(PDF_SOURCE_DIR.glob("*.pdf"))

    if not pdfs:
        print("PDF 파일 없음")
        return 0

    total_saved = 0

    for pdf_path in pdfs:
        if not pdf_path.exists():
            print(f"파일 없음: {pdf_path}")
            continue

        records = parse_pdf(pdf_path)

        if dry_run:
            print(f"  [DRY] {len(records)}건 (저장 안 함)")
            continue

        stem = re.sub(r"[^\w가-힣]", "_", pdf_path.stem)
        for rec in records:
            out_path = PDF_OUT_DIR / f"{stem}_{rec['doc_number'].replace('-', '_')}.json"
            out_path.write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        total_saved += len(records)
        print(f"  저장: {len(records)}건 → {PDF_OUT_DIR}/")

    print(f"\n완료: 총 {total_saved}건")
    return total_saved


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="세법집행기준 PDF 파서")
    parser.add_argument("--file", help="특정 PDF 파일명 (기본: 전체)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    collect_pdfs(pdf_file=args.file, dry_run=args.dry_run)
