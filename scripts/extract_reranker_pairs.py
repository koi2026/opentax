"""
BGE Reranker 파인튜닝용 positive/negative pair 추출 스크립트.

data/red_wins/  → negative pair 추출 (Red가 지적한 유령인용/요건오판 chunk)
data/blue_wins/ → positive pair 추가 (Blue가 방어에 성공한 chunk)

출력: data/reranker_pairs.jsonl
포맷:
  {"query": "...", "positive": "chunk 텍스트", "negative": "chunk 텍스트", "source": "debate_id"}

사용법:
    python scripts/extract_reranker_pairs.py
    python scripts/extract_reranker_pairs.py --out data/custom_pairs.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

RED_WINS_DIR = Path("data/red_wins")
BLUE_WINS_DIR = Path("data/blue_wins")
DEFAULT_OUTPUT = Path("data/reranker_pairs.jsonl")


# ── 사실관계 → 검색 쿼리 텍스트 변환 ─────────────────────────────────────────

def _fact_json_to_query(fact_json: dict) -> str:
    """
    FactVector.to_text() 방식을 모사해 fact_json을 검색 쿼리 텍스트로 변환.
    파이프라인 내부 FactVector와 동일한 키워드를 사용해야 임베딩 공간이 일치한다.
    """
    parts: list[str] = []

    # 기본 양도 정보
    transfer_date = fact_json.get("transfer_date", "")
    acquisition_date = fact_json.get("acquisition_date", "")
    transfer_price = fact_json.get("transfer_price", "")
    property_type = fact_json.get("property_type", "")

    if property_type:
        parts.append(f"자산유형: {property_type}")
    if transfer_date:
        parts.append(f"양도일: {transfer_date}")
    if acquisition_date:
        parts.append(f"취득일: {acquisition_date}")
    if transfer_price:
        parts.append(f"양도가액: {transfer_price}원")

    # 세대 정보
    household_count = fact_json.get("household_house_count")
    if household_count is not None:
        parts.append(f"세대원 주택수: {household_count}채")

    # 거주 기간
    residence_years = fact_json.get("residence_years")
    if residence_years is not None:
        parts.append(f"거주기간: {residence_years}년")

    # 조정대상지역 여부
    adj_acquisition = fact_json.get("adjustment_area_at_acquisition")
    adj_transfer = fact_json.get("adjustment_area_at_transfer")
    if adj_acquisition is not None:
        parts.append(f"취득시 조정대상지역: {'예' if adj_acquisition else '아니오'}")
    if adj_transfer is not None:
        parts.append(f"양도시 조정대상지역: {'예' if adj_transfer else '아니오'}")

    # 특수 사항
    if fact_json.get("is_gift_from_spouse_or_lineal"):
        parts.append("배우자·직계존비속 증여 후 양도 (이월과세 검토)")
    if fact_json.get("is_temporary_two_house"):
        parts.append("일시적2주택 해당")
    if fact_json.get("inheritance"):
        parts.append("상속주택 포함")
    if fact_json.get("sangsaeng_rental"):
        parts.append("상생임대 요건 해당")
    if fact_json.get("is_related_party_transaction"):
        parts.append("특수관계인 간 거래 (§101 부당행위계산부인 검토)")

    query = " | ".join(parts) if parts else "양도소득세 비과세 요건"

    # 추가 자유형 텍스트가 있으면 append
    question = fact_json.get("question", "")
    if question:
        query = f"{question} {query}"

    return query


# ── chunk_id로 실제 chunk 텍스트 조회 (best-effort) ──────────────────────────

def _fetch_chunk_text(chunk_id: str) -> Optional[str]:
    """
    data/processed/ 또는 Pinecone에서 chunk 텍스트를 가져온다.
    오프라인에서는 processed JSON을 먼저 시도하고, 실패하면 None 반환.
    """
    # 방법 1: data/processed/ 에 저장된 JSON 청크 파일 탐색
    processed_dir = Path("data/processed")
    if processed_dir.exists():
        for chunk_file in processed_dir.glob("*.json"):
            try:
                with chunk_file.open(encoding="utf-8") as f:
                    chunks = json.load(f)
                if isinstance(chunks, list):
                    for chunk in chunks:
                        if chunk.get("id") == chunk_id or chunk.get("chunk_id") == chunk_id:
                            return chunk.get("full_text") or chunk.get("text") or chunk.get("content")
            except (json.JSONDecodeError, KeyError):
                continue

    # 방법 2: chunk_id 자체를 플레이스홀더로 반환 (Pinecone 미접근 환경)
    return None


# ── red_wins 파일에서 negative pair 추출 ─────────────────────────────────────

def _extract_from_red_wins() -> list[dict]:
    """
    Red가 '유령인용' 또는 '요건오판'으로 지적한 chunk를 negative로 사용.
    data/red_wins/의 각 파일에서 challenged_citations를 읽는다.
    """
    pairs: list[dict] = []

    if not RED_WINS_DIR.exists():
        print(f"[경고] {RED_WINS_DIR} 디렉터리 없음 — red_wins 추출 생략")
        return pairs

    files = list(RED_WINS_DIR.glob("*.json"))
    print(f"[red_wins] {len(files)}개 파일 처리 중...")

    for path in files:
        try:
            with path.open(encoding="utf-8") as f:
                record = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        debate_id = record.get("debate_id", path.stem)
        fact_json = record.get("fact_json", {})
        challenge_type = record.get("challenge_type", "")

        # '근거없음' 자동 기각 케이스는 제외
        if challenge_type == "근거없음":
            continue

        # 관련성 있는 challenge_type만 사용 (유령인용, 요건오판)
        if challenge_type not in ("유령인용", "요건오판", "시점오류", "중과회피", "고가주택오류", "이월과세누락"):
            continue

        query = _fact_json_to_query(fact_json)

        # challenged_citations: Red가 잘못됐다고 지적한 chunk_id 목록
        # debate 원본 파일에서 전체 정보를 가져와야 red_challenge.challenged_citations를 볼 수 있음
        # red_wins는 축약 저장이므로 debates/ 원본을 먼저 시도
        challenged_ids: list[str] = []
        debate_orig = Path("data/debates") / f"{debate_id}.json"
        if debate_orig.exists():
            try:
                with debate_orig.open(encoding="utf-8") as f:
                    orig = json.load(f)
                # 멀티라운드: 마지막 라운드의 challenged_citations 사용
                rounds = orig.get("rounds", [])
                if rounds:
                    last_round = rounds[-1]
                    challenged_ids = last_round.get("red_challenge", {}).get("challenged_citations", [])
                else:
                    challenged_ids = orig.get("red_challenge", {}).get("challenged_citations", [])
            except (json.JSONDecodeError, OSError):
                pass

        # blue_wins에서 같은 debate_id의 positive chunk를 매핑
        positive_text: Optional[str] = None
        blue_orig = BLUE_WINS_DIR / f"{debate_id}.json"
        if blue_orig.exists():
            try:
                with blue_orig.open(encoding="utf-8") as f:
                    blue_record = json.load(f)
                new_citations = blue_record.get("new_citations", [])
                for cid in new_citations[:3]:
                    text = _fetch_chunk_text(cid)
                    if text:
                        positive_text = text
                        break
            except (json.JSONDecodeError, OSError):
                pass

        for neg_id in challenged_ids[:3]:
            negative_text = _fetch_chunk_text(neg_id)
            if negative_text and positive_text:
                pairs.append({
                    "query": query,
                    "positive": positive_text,
                    "negative": negative_text,
                    "source": debate_id,
                    "pair_type": "red_challenged",
                    "challenge_type": challenge_type,
                })
            elif negative_text:
                # positive 없으면 chunk_id만 기록 (후처리용)
                pairs.append({
                    "query": query,
                    "positive": None,
                    "negative": negative_text,
                    "negative_chunk_id": neg_id,
                    "source": debate_id,
                    "pair_type": "red_challenged_no_positive",
                    "challenge_type": challenge_type,
                })

    return pairs


# ── blue_wins 파일에서 positive pair 추가 추출 ────────────────────────────────

def _extract_from_blue_wins() -> list[dict]:
    """
    Blue가 방어에 성공한 케이스 → new_citations를 positive로 사용.
    data/blue_wins/ 파일을 순회하며 pair 생성.
    """
    pairs: list[dict] = []

    if not BLUE_WINS_DIR.exists():
        print(f"[경고] {BLUE_WINS_DIR} 디렉터리 없음 — blue_wins 추출 생략")
        return pairs

    files = list(BLUE_WINS_DIR.glob("*.json"))
    print(f"[blue_wins] {len(files)}개 파일 처리 중...")

    for path in files:
        try:
            with path.open(encoding="utf-8") as f:
                record = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        debate_id = record.get("debate_id", path.stem)
        fact_json = record.get("fact_json", {})
        query = _fact_json_to_query(fact_json)

        # new_citations: Blue가 추가 검색으로 발견한 조문 (방어 성공의 핵심 evidence)
        new_citations: list[str] = record.get("new_citations", [])

        # debate 원본에서 멀티라운드 정보 보완
        debate_orig = Path("data/debates") / f"{debate_id}.json"
        if debate_orig.exists() and not new_citations:
            try:
                with debate_orig.open(encoding="utf-8") as f:
                    orig = json.load(f)
                rounds = orig.get("rounds", [])
                if rounds:
                    last_round = rounds[-1]
                    new_citations = last_round.get("blue_defense", {}).get("new_citations", [])
                else:
                    new_citations = orig.get("blue_defense", {}).get("new_citations", [])
            except (json.JSONDecodeError, OSError):
                pass

        for pos_id in new_citations[:5]:
            positive_text = _fetch_chunk_text(pos_id)
            if positive_text:
                pairs.append({
                    "query": query,
                    "positive": positive_text,
                    "negative": None,
                    "positive_chunk_id": pos_id,
                    "source": debate_id,
                    "pair_type": "blue_defended",
                })

    return pairs


# ── pair 병합 및 중복 제거 ────────────────────────────────────────────────────

def _merge_pairs(
    red_pairs: list[dict],
    blue_pairs: list[dict],
) -> list[dict]:
    """
    red_pairs(negative 있음) + blue_pairs(positive 있음)를 같은 source로 조인.
    같은 debate_id끼리 positive/negative를 짝 지어 완전한 triplet으로 합친다.
    """
    # source(debate_id)별로 groupby
    blue_by_source: dict[str, list[dict]] = {}
    for p in blue_pairs:
        blue_by_source.setdefault(p["source"], []).append(p)

    merged: list[dict] = []
    seen: set[tuple] = set()

    for pair in red_pairs:
        if pair.get("positive") and pair.get("negative"):
            key = (pair["query"][:60], pair["positive"][:60], pair["negative"][:60])
            if key not in seen:
                seen.add(key)
                merged.append({
                    "query": pair["query"],
                    "positive": pair["positive"],
                    "negative": pair["negative"],
                    "source": pair["source"],
                })
            continue

        # positive가 없는 경우 blue_wins에서 같은 source의 positive 매핑
        src = pair["source"]
        if src in blue_by_source and pair.get("negative"):
            for bp in blue_by_source[src]:
                if bp.get("positive"):
                    key = (pair["query"][:60], bp["positive"][:60], pair["negative"][:60])
                    if key not in seen:
                        seen.add(key)
                        merged.append({
                            "query": pair["query"],
                            "positive": bp["positive"],
                            "negative": pair["negative"],
                            "source": src,
                        })
                    break

    # blue_wins 전용 positive-only pair (negative 없이도 포함 — in-batch negative 용)
    for pair in blue_pairs:
        if pair.get("positive"):
            key = (pair["query"][:60], pair["positive"][:60], "")
            if key not in seen:
                seen.add(key)
                merged.append({
                    "query": pair["query"],
                    "positive": pair["positive"],
                    "negative": None,
                    "source": pair["source"],
                })

    return merged


# ── 출력 저장 ─────────────────────────────────────────────────────────────────

def _save_jsonl(pairs: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BGE Reranker 파인튜닝용 positive/negative pair 추출"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"출력 JSONL 경로 (기본: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    print("=== BGE Reranker Pair 추출 시작 ===")

    red_pairs = _extract_from_red_wins()
    blue_pairs = _extract_from_blue_wins()

    merged = _merge_pairs(red_pairs, blue_pairs)

    complete = [p for p in merged if p.get("positive") and p.get("negative")]
    positive_only = [p for p in merged if p.get("positive") and not p.get("negative")]

    print(f"\n[결과 요약]")
    print(f"  red_wins에서 추출: {len(red_pairs)}개 후보")
    print(f"  blue_wins에서 추출: {len(blue_pairs)}개 후보")
    print(f"  병합 후 완전 triplet (positive+negative): {len(complete)}개")
    print(f"  positive-only pair (in-batch negative용): {len(positive_only)}개")
    print(f"  총 저장: {len(merged)}개")

    _save_jsonl(merged, args.out)
    print(f"\n저장 완료: {args.out}")


if __name__ == "__main__":
    main()
