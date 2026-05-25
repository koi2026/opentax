"""
골든 데이터셋 평가 러너
data/golden/qa_pairs.json → 배치 실행 → 지표 출력

변경 사항(청킹·검색·프롬프트·모델) 배포 전 전체 실행 필수.

verdict_match: verdict_matcher.compute_reward 기반 (alias 정규화)
stale 감지: registry_deps 키가 포함된 케이스는 별도 집계
시계열: 직전 eval 결과와 delta 자동 비교
"""
import json
import time
from datetime import date
from pathlib import Path
from typing import Optional

from src.eval.feedback import compute_citation_precision, compute_retrieval_metrics
from src.eval.retrieval_analyzer import run_analysis
from src.eval.verdict_matcher import compute_reward
from src.domain.tax_answer import TaxVerdict
from src.domain.query_enrichment import enrich_raw_query_text, detect_flags_from_text
from src.rag import answer_with_citations, retrieve_tax_law

GOLDEN_PATH = Path("data/golden/qa_pairs.json")
RESULTS_DIR = Path("data/eval_results")


def _load_golden() -> list[dict]:
    if not GOLDEN_PATH.exists():
        raise FileNotFoundError(f"골든 데이터셋 없음: {GOLDEN_PATH}")
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _extract_verdict(answer_text: str) -> str:
    """TaxVerdict enum 값을 answer 텍스트에서 추출 (첫 매칭 반환)."""
    for tv in TaxVerdict:
        if tv.value in answer_text:
            return tv.value
    return ""


def _is_stale(case: dict) -> bool:
    """
    registry_deps 키 중 하나라도 현재 Registry 값이 케이스 생성 당시와
    다를 가능성이 있으면 True.
    registry_snapshot 필드가 없으면 registry_deps 존재만으로 stale 후보 처리.
    """
    deps = case.get("registry_deps", [])
    if not deps:
        return False
    snapshot = case.get("registry_snapshot", {})
    if not snapshot:
        return True  # snapshot 없으면 확인 불가 → stale 후보
    try:
        from src.domain.tax_constants import TaxConstantsRegistry
        for key in deps:
            current = TaxConstantsRegistry.get(key, date.today())
            stored = snapshot.get(key)
            if stored is not None and str(current) != str(stored):
                return True
    except Exception:
        pass
    return False


def _load_prev_summary() -> Optional[dict]:
    """직전 eval 결과의 summary 반환. 없으면 None."""
    result_files = sorted(RESULTS_DIR.glob("eval_*.json"))
    if not result_files:
        return None
    try:
        data = json.loads(result_files[-1].read_text(encoding="utf-8"))
        return data.get("summary")
    except Exception:
        return None


def _print_delta(current: dict, prev: Optional[dict]) -> None:
    if not prev:
        return
    print("\n=== 직전 eval 대비 delta ===")
    keys = ["verdict_match_rate", "avg_recall_at_k", "avg_citation_precision"]
    for k in keys:
        c = current.get(k)
        p = prev.get(k)
        if c is None or p is None:
            continue
        delta = c - p
        sign = "+" if delta >= 0 else ""
        flag = " ▲" if delta > 0 else (" ▼" if delta < 0 else "  ")
        print(f"  {k}: {p:.3f} → {c:.3f} ({sign}{delta:.3f}){flag}")


def _auto_save_gold_chunks(
    cases: list[dict],
    candidates: list[dict],
    golden_path: Path,
) -> None:
    """eval 실행 중 발견된 gold_chunk 후보를 골든셋 파일에 직접 저장한다.

    question-based qa_pairs.json 케이스는 bootstrap_gold_chunks가 fact_json이 없어
    처리하지 못하므로, eval.py 실행 시 자동으로 채워준다.
    """
    candidate_map = {r["case_id"]: r["_gold_chunk_candidate"] for r in candidates}
    updated = 0
    for case in cases:
        cid = case.get("id") or case.get("case_id")
        if cid in candidate_map and not case.get("gold_chunk_ids"):
            case["gold_chunk_ids"] = candidate_map[cid]
            updated += 1
    if updated == 0:
        return
    try:
        raw = json.loads(golden_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            golden_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            raw["cases"] = cases
            golden_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → gold_chunk_ids {updated}건 자동 저장: {golden_path.name}")
    except Exception as e:
        print(f"  → gold_chunk_ids 저장 실패: {e}")


def run_eval(
    top_k: int = 20,
    rerank_top_n: int = 5,
    save_results: bool = True,
) -> dict:
    """
    골든 데이터셋 전체를 실행하고 지표를 반환한다.
    - retrieval: Recall@k, Precision@k, MRR
    - citation precision: 인용 chunk가 검색 결과에 있는지
    - verdict_match: verdict_matcher.compute_reward 기반 (alias 정규화)
    - stale 케이스: registry_deps 기반 별도 집계
    """
    cases = _load_golden()
    print(f"골든 케이스 {len(cases)}개 평가 시작")

    results = []
    retrieval_metrics_all = []
    citation_precision_all = []
    stale_count = 0

    for i, case in enumerate(cases, 1):
        question = case["question"]
        gold_chunks = case.get("gold_chunk_ids", [])
        as_of_date = case.get("as_of_date")
        expected_verdict = case.get("expected_verdict")
        is_stale = _is_stale(case)
        if is_stale:
            stale_count += 1

        enriched_question = enrich_raw_query_text(question)
        detected_flags = case.get("danger_flags") or detect_flags_from_text(question)

        t0 = time.time()
        chunks = retrieve_tax_law(enriched_question, top_k=top_k, rerank_top_n=rerank_top_n, as_of_date=as_of_date)
        answer = answer_with_citations(enriched_question, as_of_date=as_of_date)
        latency_ms = int((time.time() - t0) * 1000)

        retrieved_ids = [c.id for c in chunks]
        ret_metrics = compute_retrieval_metrics(retrieved_ids, gold_chunks, k=rerank_top_n)
        cit_prec = compute_citation_precision(answer.chunk_ids, retrieved_ids)

        # verdict 추출 및 비교 — verdict_matcher 기반
        actual_verdict = _extract_verdict(answer.answer)
        reward_signal = None
        verdict_match = None
        if expected_verdict and actual_verdict:
            reward_signal = compute_reward(
                case_id=case.get("id", f"case_{i:03d}"),
                expected_verdict=expected_verdict,
                actual_verdict=actual_verdict,
                confidence=answer.confidence,
                chunk_ids=answer.chunk_ids,
            )
            verdict_match = reward_signal.verdict_match

        case_result = {
            "case_id": case.get("id", f"case_{i:03d}"),
            "question": question,
            "as_of_date": as_of_date,
            "expected_verdict": expected_verdict,
            "actual_verdict": actual_verdict,
            "verdict_match": verdict_match,
            "is_stale": is_stale,
            "retrieval_metrics": ret_metrics,
            "citation_precision": cit_prec,
            "gold_chunk_ids": gold_chunks,
            "retrieved_chunk_ids": retrieved_ids,
            "confidence": answer.confidence,
            "missing_facts_count": len(answer.missing_facts),
            "latency_ms": latency_ms,
            "detected_flags": detected_flags,
        }

        # stale 케이스는 gold_chunk_ids 자동 업데이트 후보로 기록
        if verdict_match and not gold_chunks and answer.chunk_ids:
            case_result["_gold_chunk_candidate"] = answer.chunk_ids

        results.append(case_result)
        retrieval_metrics_all.append(ret_metrics)
        citation_precision_all.append(cit_prec)

        stale_mark = " [STALE?]" if is_stale else ""
        status = "✓" if verdict_match else ("✗" if verdict_match is False else "?")
        print(
            f"  [{i:03d}] {status}{stale_mark} "
            f"verdict={actual_verdict or '?':8s} "
            f"recall@{rerank_top_n}={ret_metrics.get('recall_at_k', 'N/A')!s:.4} "
            f"cit_prec={cit_prec:.2f} "
            f"conf={answer.confidence:.2f} "
            f"({latency_ms}ms)"
        )

    def avg(lst):
        vals = [v for v in lst if v is not None]
        return sum(vals) / len(vals) if vals else None

    # stale 제외한 clean 케이스만으로 정확도 계산
    clean_results = [r for r in results if not r["is_stale"]]
    clean_verdict = [r["verdict_match"] for r in clean_results if r["verdict_match"] is not None]

    summary = {
        "total": len(results),
        "stale_count": stale_count,
        "clean_total": len(clean_results),
        "verdict_match_rate": avg(clean_verdict),
        "verdict_match_rate_all": avg([r["verdict_match"] for r in results if r["verdict_match"] is not None]),
        "avg_recall_at_k": avg([r["retrieval_metrics"].get("recall_at_k") for r in results]),
        "avg_mrr": avg([r["retrieval_metrics"].get("mrr") for r in results]),
        "avg_citation_precision": avg(citation_precision_all),
        "avg_confidence": avg([r["confidence"] for r in results]),
        "avg_latency_ms": avg([r["latency_ms"] for r in results]),
        "gold_chunk_candidates": sum(1 for r in results if r.get("_gold_chunk_candidate")),
    }

    prev_summary = _load_prev_summary()

    print("\n=== 평가 결과 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    _print_delta(summary, prev_summary)

    if stale_count:
        print(f"\n[경고] stale 후보 케이스 {stale_count}건 — registry_deps 키 변경 의심. 재생성 권장.")

    gold_candidates = [r for r in results if r.get("_gold_chunk_candidate")]
    if gold_candidates:
        print(f"\n[정보] gold_chunk_ids 자동 부여 후보: {len(gold_candidates)}건")
        _auto_save_gold_chunks(cases, gold_candidates, GOLDEN_PATH)

    if save_results:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = RESULTS_DIR / f"eval_{ts}.json"
        out_path.write_text(
            json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n결과 저장: {out_path}")

    run_analysis(cases, results, save_report=save_results)

    return summary


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    run_eval()
