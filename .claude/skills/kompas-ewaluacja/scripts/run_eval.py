"""Ewaluacja Asystenta formalnego na rozłącznym zbiorze eval_holdout.json (jedno polecenie).

  python run_eval.py --kb kb_chunks.jsonl --retrieval-only --out-dir reports/
  python run_eval.py --kb kb_chunks.jsonl --out-dir reports/ [--limit 12] [--ids h_first_01 h_out_03]

Retrieval: hit@1/3/5 (dowolna oczekiwana jednostka w top-k), all@5 (wszystkie), trafienia FAQ (powinno być 0 –
holdout jest rozłączny), sygnały odmowy (pokrycie, cosinus) dla pytań w zakresie i spoza zakresu + kalibracja progów.
Pełny: trafność odmów, poprawność cytatów (cytowane id istnieją i były w kontekście), cytat oczekiwanej jednostki,
pokrycie punktów kluczowych (heurystyka rdzeni słów), czas p50/p95. Raport: eval_<tryb>.json + eval_<tryb>.md.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / "kompas-asystent-ai" / "scripts"))
import retrieve  # noqa: E402
from retrieve import Retriever, analyze, load_jsonl, unit_matches  # noqa: E402

DEFAULT_HOLDOUT = SKILLS / "kompas-ewaluacja" / "assets" / "eval_holdout.json"
DEFAULT_FAQ = SKILLS / "kompas-asystent-ai" / "assets" / "faq_kb.json"


def matches(hit: dict, exp: dict) -> bool:
    return hit.get("source_id") == exp["source_id"] and unit_matches(hit.get("unit") or "", exp["unit"])


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 3)


def keypoint_coverage(answer: str, points: list[str]) -> float:
    ans = set(analyze(answer))
    ok = 0
    for p in points:
        st = set(analyze(p))
        if st and len(st & ans) / len(st) >= 0.6:
            ok += 1
    return ok / len(points) if points else 1.0


def calibrate(rows: list[dict]) -> dict:
    best = None
    for cov in [x / 100 for x in range(20, 85, 5)]:
        for dense in [None] + [x / 100 for x in range(40, 80, 2)]:
            tp = tn = 0
            for r in rows:
                s = r["signals"]
                ref = s["coverage"] < cov or (dense is not None and s.get("dense_top") is not None
                                              and s["dense_top"] < dense) or r.get("decision_rule", False)
                if r["expect_refusal"] and ref:
                    tp += 1
                if not r["expect_refusal"] and not ref:
                    tn += 1
            npos = sum(r["expect_refusal"] for r in rows) or 1
            nneg = sum(not r["expect_refusal"] for r in rows) or 1
            bal = (tp / npos + tn / nneg) / 2
            if best is None or bal > best["balanced_accuracy"]:
                best = {"coverage_min": cov, "dense_min": dense, "balanced_accuracy": round(bal, 3),
                        "refusals_correct": f"{tp}/{npos}", "answered_in_scope": f"{tn}/{nneg}"}
    return best


def run_retrieval(items, retr: Retriever) -> dict:
    rows = []
    from assistant import DECISION_RX  # reguła odmowy decyzji działa przed retrievalem
    for h in items:
        t0 = time.perf_counter()
        faq_hit = retr.match_faq(h["question"]) is not None
        r = retr.search(h["question"], k=5, use_faq=False)
        dt = time.perf_counter() - t0
        exp = h.get("expected_units") or []
        hits = r["hits"]
        row = {"id": h["id"], "process": h.get("process"), "expect_refusal": bool(h.get("expect_refusal")),
               "faq_match": faq_hit, "signals": r["signals"], "refuse": r["refuse"] or bool(DECISION_RX.search(h["question"])),
               "decision_rule": bool(DECISION_RX.search(h["question"])), "latency_s": round(dt, 3),
               "top5": [f"{x['id']} ({x['unit']})" for x in hits]}
        if exp:
            for k in (1, 3, 5):
                row[f"hit@{k}"] = any(matches(x, e) for x in hits[:k] for e in exp)
            row["all@5"] = all(any(matches(x, e) for x in hits[:5]) for e in exp)
        rows.append(row)
    ins = [r for r in rows if not r["expect_refusal"]]
    outs = [r for r in rows if r["expect_refusal"]]
    summary = {
        "n_in_scope": len(ins), "n_out_of_scope": len(outs),
        **{f"hit@{k}": round(sum(r[f"hit@{k}"] for r in ins) / len(ins), 3) for k in (1, 3, 5)},
        "all@5": round(sum(r["all@5"] for r in ins) / len(ins), 3),
        "faq_false_matches": sum(r["faq_match"] for r in rows),
        "refusal_recall_out_of_scope": f"{sum(r['refuse'] for r in outs)}/{len(outs)}",
        "false_refusals_in_scope": f"{sum(r['refuse'] for r in ins)}/{len(ins)}",
        "thresholds_used": {"coverage_min": retrieve.COVERAGE_MIN, "dense_min": retrieve.DENSE_MIN},
        "calibration_best": calibrate(rows),
        "signals_in_scope": {"coverage_min": min(r["signals"]["coverage"] for r in ins),
                             "dense_top_min": min((r["signals"]["dense_top"] or 0) for r in ins)},
        "signals_out_of_scope": {"coverage_max": max(r["signals"]["coverage"] for r in outs),
                                 "dense_top_max": max((r["signals"]["dense_top"] or 0) for r in outs)},
        "latency_p50_s": pct([r["latency_s"] for r in rows], 50), "latency_p95_s": pct([r["latency_s"] for r in rows], 95),
    }
    for proc in ("first", "periodic"):
        sub = [r for r in ins if r["process"] == proc]
        if sub:
            summary[f"hit@5_{proc}"] = round(sum(r["hit@5"] for r in sub) / len(sub), 3)
    return {"summary": summary, "rows": rows}


def run_full(items, kb: str, faq: str, cache_dir: str, use_embeddings: bool = True, pause: float = 0.0) -> dict:
    from assistant import Assistant
    # --no-embed musi działać także w trybie pełnym (tryb hostingu bez Ollamy, np. Render)
    asst = Assistant(kb, faq, cache_dir=cache_dir, use_embeddings=use_embeddings)
    rows = []
    for n, h in enumerate(items):
        if pause and n and rows[-1].get("llm"):
            time.sleep(pause)  # darmowe API (Groq) ma limit tokenów na minutę
        res = asst.answer(h["question"], "formal", {"process": h.get("process")} if h.get("process") else {})
        exp = h.get("expected_units") or []
        cited = res.get("citations", [])
        row = {"id": h["id"], "expect_refusal": bool(h.get("expect_refusal")), "refused": res["refused"],
               "refusal_reason": res.get("refusal_reason"), "source": res.get("source"),
               "latency_s": res["latency_s"], "answer": res["answer"][:600],
               "cited_ids": [c["id"] for c in cited], "invalid_citations": res.get("invalid_citations", []),
               "llm": res.get("llm")}
        row["refusal_correct"] = row["refused"] == row["expect_refusal"]
        if exp and not res["refused"]:
            row["cites_expected_unit"] = any(
                matches(asst.retriever.by_id[c["id"]], e) for c in cited for e in exp)
            row["keypoint_coverage"] = round(keypoint_coverage(res["answer"], h["key_points"]), 3)
        rows.append(row)
        print(f"{h['id']:14s} refused={res['refused']!s:5s} {res['latency_s']:6.1f}s "
              f"kp={row.get('keypoint_coverage', '-')} cites={row['cited_ids'][:3]}", flush=True)
    ins = [r for r in rows if not r["expect_refusal"]]
    outs = [r for r in rows if r["expect_refusal"]]
    answered = [r for r in ins if not r["refused"]]
    lat = [r["latency_s"] for r in rows]
    summary = {
        "n": len(rows), "n_in_scope": len(ins), "n_out_of_scope": len(outs),
        "refusal_accuracy": round(sum(r["refusal_correct"] for r in rows) / len(rows), 3),
        "correct_refusals_out_of_scope": f"{sum(r['refused'] for r in outs)}/{len(outs)}",
        "false_refusals_in_scope": f"{sum(r['refused'] for r in ins)}/{len(ins)}",
        "citation_validity": f"{sum(not r['invalid_citations'] for r in rows)}/{len(rows)} odpowiedzi bez "
                             f"niezweryfikowanych cytatów",
        "answered_with_citation": f"{sum(bool(r['cited_ids']) for r in answered)}/{len(answered)}",
        "cites_expected_unit": f"{sum(r.get('cites_expected_unit', False) for r in answered)}/{len(answered)}",
        "keypoint_coverage_mean": round(statistics.mean(r["keypoint_coverage"] for r in answered), 3) if answered else None,
        "latency_p50_s": pct(lat, 50), "latency_p95_s": pct(lat, 95),
        "model": next((r["llm"]["model"] for r in rows if r.get("llm")), None),
    }
    return {"summary": summary, "rows": rows}


def to_md(report: dict, mode: str) -> str:
    s = report["summary"]
    lines = [f"# Ewaluacja Asystenta formalnego – tryb `{mode}`", "",
             f"Zbiór: eval_holdout.json (rozłączny z faq_kb.json). Data: {time.strftime('%Y-%m-%d %H:%M')}.", "",
             "| Miara | Wartość |", "|---|---|"]
    for k, v in s.items():
        lines.append(f"| {k} | {json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v} |")
    lines += ["", "## Pozycje", ""]
    for r in report["rows"]:
        if mode == "retrieval":
            lines.append(f"- `{r['id']}` hit@5={r.get('hit@5', '-')} refuse={r['refuse']} "
                         f"cov={r['signals']['coverage']} cos={r['signals']['dense_top']} top1={r['top5'][:1]}")
        else:
            lines.append(f"- `{r['id']}` refused={r['refused']} (oczekiwano {r['expect_refusal']}) "
                         f"kp={r.get('keypoint_coverage', '-')} cytaty={r['cited_ids'][:3]} {r['latency_s']} s")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--holdout", default=str(DEFAULT_HOLDOUT))
    ap.add_argument("--faq", default=str(DEFAULT_FAQ))
    ap.add_argument("--cache-dir", default=".cache")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--coverage-min", type=float)
    ap.add_argument("--dense-min", type=float)
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--pause", type=float, default=0.0, help="przerwa (s) po pytaniu, które wywołało model")
    a = ap.parse_args()
    if a.coverage_min is not None:
        retrieve.COVERAGE_MIN = a.coverage_min
    if a.dense_min is not None:
        retrieve.DENSE_MIN = a.dense_min
    items = json.loads(Path(a.holdout).read_text(encoding="utf-8"))["items"]
    if a.ids:
        items = [h for h in items if h["id"] in a.ids]
    if a.limit:
        items = items[: a.limit]
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if a.retrieval_only:
        faq = json.loads(Path(a.faq).read_text(encoding="utf-8"))["items"]
        retr = Retriever(load_jsonl(a.kb), faq, cache_dir=a.cache_dir, use_embeddings=not a.no_embed)
        rep, mode = run_retrieval(items, retr), "retrieval"
    else:
        rep, mode = run_full(items, a.kb, a.faq, a.cache_dir, use_embeddings=not a.no_embed, pause=a.pause), "full"
    (out / f"eval_{mode}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"eval_{mode}.md").write_text(to_md(rep, mode), encoding="utf-8")
    print(json.dumps(rep["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
