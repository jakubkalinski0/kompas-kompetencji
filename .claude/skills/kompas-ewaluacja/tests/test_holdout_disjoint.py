"""Rozłączność zestawu ewaluacyjnego (eval_holdout.json) od bazy wiedzy (faq_kb.json, opcjonalnie Q&A KPRM).

Pytanie holdout uznajemy za parafrazę pozycji bazy, gdy:
  (a) współczynnik Jaccarda rdzeni pytania z pytaniem (lub wariantem) bazy ≥ MAX_Q_JACCARD, albo
  (b) ma DOKŁADNIE ten sam zbiór jednostek-odpowiedzi co pozycja FAQ, a jego punkty kluczowe są w ≥ 80%
      zawarte w odpowiedzi FAQ (czyli FAQ odpowiada na nie wprost – wspólna jednostka jako jedyna treść).
Q&A KPRM (kompas-dane-i-zrodla/assets/kprm_qa/*.json), jeśli istnieje, sprawdzamy warunkiem (a).
"""
import json
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / "kompas-asystent-ai" / "scripts"))
from retrieve import analyze, jaccard  # noqa: E402

HOLDOUT = json.loads((SKILLS / "kompas-ewaluacja" / "assets" / "eval_holdout.json").read_text(encoding="utf-8"))["items"]
FAQ = json.loads((SKILLS / "kompas-asystent-ai" / "assets" / "faq_kb.json").read_text(encoding="utf-8"))["items"]
MAX_Q_JACCARD = 0.40


def unitset(srcs):
    return {(s["source_id"], s["unit"]) for s in srcs}


def kprm_questions():
    out = []
    for p in sorted((SKILLS / "kompas-dane-i-zrodla" / "assets" / "kprm_qa").glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("items") or data.get("qa") or []
        for it in items:
            q = it.get("question") or it.get("pytanie") or ""
            if q:
                out.append((f"{p.name}:{it.get('id', len(out))}", q))
    return out


def test_counts_and_balance():
    inscope = [h for h in HOLDOUT if not h.get("expect_refusal")]
    refusals = [h for h in HOLDOUT if h.get("expect_refusal")]
    assert 25 <= len(inscope) <= 30
    assert 6 <= len(refusals) <= 8
    first = sum(h["process"] == "first" for h in inscope)
    periodic = sum(h["process"] == "periodic" for h in inscope)
    assert abs(first - periodic) <= 2
    assert 20 <= len(FAQ) <= 40
    assert len({h["id"] for h in HOLDOUT}) == len(HOLDOUT)


def test_every_item_has_answer_spec():
    for h in HOLDOUT:
        if h.get("expect_refusal"):
            assert not h["expected_units"]
        else:
            assert h["expected_units"] and h["key_points"], h["id"]
    for f in FAQ:
        assert f["sources"] and all(s.get("source_id") and s.get("unit") for s in f["sources"]), f["id"]


@pytest.mark.parametrize("h", HOLDOUT, ids=lambda h: h["id"])
def test_not_paraphrase_of_faq(h):
    hq = analyze(h["question"])
    for f in FAQ:
        for v in [f["question"], *f.get("alt_questions", [])]:
            j = jaccard(hq, analyze(v))
            assert j < MAX_Q_JACCARD, f"{h['id']} ~ {f['id']}: Jaccard {j:.2f} ({v})"
        if not h.get("expect_refusal") and unitset(h["expected_units"]) == unitset(f["sources"]):
            ans = set(analyze(f["answer"]))
            pts = [set(analyze(p)) for p in h["key_points"]]
            covered = sum(len(p & ans) / len(p) >= 0.8 for p in pts if p) / max(len(pts), 1)
            assert covered < 0.8, f"{h['id']} ma te same jednostki co {f['id']} i FAQ odpowiada wprost ({covered:.0%})"


def test_not_paraphrase_of_kprm_qa():
    qa = kprm_questions()
    if not qa:
        pytest.skip("brak kompas-dane-i-zrodla/assets/kprm_qa/*.json")
    for h in HOLDOUT:
        hq = analyze(h["question"])
        for qid, q in qa:
            j = jaccard(hq, analyze(q))
            assert j < MAX_Q_JACCARD, f"{h['id']} ~ KPRM {qid}: Jaccard {j:.2f} ({q})"
