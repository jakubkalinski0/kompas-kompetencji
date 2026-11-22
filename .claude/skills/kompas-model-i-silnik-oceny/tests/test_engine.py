"""Testy reguł silnika oceny. Id reguł odpowiadają assets/forms_config.json i references/reguly.md."""
import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from kompas_engine import (band_for_average, evaluate, first_eval_outcome, indicator_points, part3_status,
                           periodic_outcome, record_decision, suggest_criterion)
from kompas_engine.guard import run_guard

SKILL_DIR = Path(__file__).resolve().parents[1]


def ratings(cid, levels):
    return [{"indicator_id": f"{cid}.{i}", "level": None if lv == "nb" else lv, "no_basis": lv == "nb"}
            for i, lv in enumerate(levels, 1)]


def rule_ids(issues):
    return {i["rule_id"] for i in issues}


# ---------- S-INDICATOR-POINTS ----------
def test_indicator_points_2l_minus_1():
    assert [indicator_points(level) for level in range(1, 6)] == [1, 3, 5, 7, 9]
    for bad in (0, 6, None, 2.5, True):
        with pytest.raises(ValueError):
            indicator_points(bad)


# ---------- P-THRESHOLDS: granice 2, 4, 6, 8 i tuż powyżej ----------
@pytest.mark.parametrize("avg,level", [
    (Fraction(1), 1), (Fraction(2), 1), (Fraction(201, 100), 2),
    (Fraction(4), 2), (Fraction(401, 100), 3),
    (Fraction(6), 3), (Fraction(601, 100), 4),
    (Fraction(8), 4), (Fraction(801, 100), 5), (Fraction(9), 5),
])
def test_band_boundaries(config, avg, level):
    assert band_for_average(avg, config)["level"] == level


def test_band_outside_scale(config):
    assert band_for_average(Fraction(1, 2), config) is None
    assert band_for_average(Fraction(19, 2), config) is None


@pytest.mark.parametrize("levels,avg,points", [
    ([1, 2], 2.0, 1),       # (1+3)/2 = 2 → znacznie poniżej
    ([1, 2, 2], 2.33, 3),   # tuż powyżej 2
    ([2, 3], 4.0, 3),       # (3+5)/2 = 4 → poniżej
    ([2, 3, 3], 4.33, 5),
    ([3, 4], 6.0, 5),       # (5+7)/2 = 6 → na poziomie
    ([3, 4, 4], 6.33, 7),
    ([4, 5], 8.0, 7),       # (7+9)/2 = 8 → powyżej
    ([4, 5, 5], 8.33, 9),
])
def test_suggestion_at_and_above_boundaries(config, levels, avg, points):
    s = suggest_criterion(ratings("komunikacja", levels), "periodic_c", config)
    assert s["average"] == avg
    assert s["points"] == points


def test_suggestion_formula_text(config):
    s = suggest_criterion(ratings("wspolpraca", [4, 3, 4]), "periodic_b", config)
    assert s["formula"] == "(7+5+7)/3 = 6,33 → powyżej oczekiwań → 7 pkt"
    assert s["rated_count"] == 3 and s["total_count"] == 3


# ---------- S-NO-BASIS / S-HALF-WARNING ----------
def test_no_basis_excluded_from_average(config):
    s = suggest_criterion(ratings("komunikacja", [4, "nb", 2, "nb"]), "periodic_c", config)
    assert s["formula"].startswith("(7+3)/2 = 5,00")
    assert s["no_basis_count"] == 2 and s["rated_count"] == 2
    assert s["points"] == 5


def test_all_no_basis_gives_no_suggestion(config):
    s = suggest_criterion(ratings("rzetelnosc", ["nb", "nb"]), "periodic_c", config)
    assert s["points"] is None and s["level"] is None and s["average"] is None
    assert "brak podstaw" in s["formula"]


def test_warning_when_less_than_half_rated(config):
    s = suggest_criterion(ratings("organizacja_pracy_i_orientacja_na_osiaganie_celow", [4, 4, "nb", "nb", "nb"]), "periodic_c", config)
    assert any("mniej niż połowę" in w for w in s["warnings"])
    s_half = suggest_criterion(ratings("wspolpraca", [4, 4, 4, "nb", "nb", "nb"]), "periodic_c", config)
    assert not any("mniej niż połowę" in w for w in s_half["warnings"])


def test_total_from_model_counts_unrated(config):
    s = suggest_criterion(ratings("wspolpraca", [4, 4]), "periodic_c", config, total_indicators=6)
    assert s["total_count"] == 6 and s["unrated_count"] == 4
    assert any("2 z 6" in w for w in s["warnings"])


def test_median_method_is_configurable(config):
    lv = [1, 5, 5]  # punkty 1, 9, 9
    assert suggest_criterion(ratings("komunikacja", lv), "periodic_c", config)["points"] == 7  # średnia 6,33
    med = suggest_criterion(ratings("komunikacja", lv), "periodic_c", config, method="median")
    assert med["points"] == 9 and med["formula"].startswith("mediana(1, 9, 9) = 9,00")
    config["suggestion"]["method"] = "median"
    assert suggest_criterion(ratings("komunikacja", lv), "periodic_c", config)["method"] == "median"


# ---------- S-FIRST-MAPPING ----------
@pytest.mark.parametrize("levels,points", [([1, 1], 3), ([2, 2], 3), ([3, 3], 5), ([4, 4], 7), ([5, 5], 7)])
def test_first_eval_default_mapping(config, levels, points):
    s = suggest_criterion(ratings("rzetelnosc", levels), "first_eval", config)
    assert s["points"] == points
    assert "do potwierdzenia" in s["mapping_note"]


def test_first_eval_mapping_is_configurable(config):
    config["first_eval_mapping"]["default"]["2"] = 5
    assert suggest_criterion(ratings("rzetelnosc", [2, 2]), "first_eval", config)["points"] == 5


# ---------- P-POSITIVE / P-NEGATIVE ----------
@pytest.mark.parametrize("finals,result,level", [
    ([1, 3], "negatywna", 1),         # średnia 2
    ([3, 5], "negatywna", 2),         # średnia 4 → poniżej
    ([3, 5, 5], "pozytywna", 3),      # 4,33
    ([5, 7], "pozytywna", 3),         # średnia 6 → na poziomie
    ([7, 9], "pozytywna", 4),         # średnia 8 → powyżej
    ([7, 9, 9], "pozytywna", 5),      # 8,33
])
def test_periodic_outcome_boundaries(config, finals, result, level):
    res = periodic_outcome(finals, config)
    assert res["result"] == result and res["overall_level"]["level"] == level


def test_single_significantly_below_forces_negative(config):
    res = periodic_outcome([9, 1, 7, 7, 5], config)  # średnia 5,8 = na poziomie
    assert res["overall_level"]["key"] == "na_poziomie"
    assert res["result"] == "negatywna"


def test_periodic_incomplete(config):
    assert periodic_outcome([5, None], config)["result"] is None


def test_ewa_negative_needs_justification(example):
    doc = example("ewa_periodic_c_negative")
    out = evaluate(doc, now="2026-11-21T15:00:00+01:00")
    assert out["result"] == "negatywna" and out["validation"]["ok"]
    assert "G-SIGNIFICANTLY-BELOW" in rule_ids(out["guard"])
    doc["justification"] = "  "
    out2 = evaluate(doc)
    assert "P-JUSTIFICATION" in rule_ids(out2["validation"]["errors"])
    assert out2["validation"]["ok"] is False


# ---------- P-PART3 ----------
def test_jan_employee_has_no_part3(example):
    out = evaluate(example("jan_periodic_c"))
    assert out["part3_attached"] == "nie_dotyczy"
    assert out["print"]["include_part3"] is False
    assert out["print"]["include_previous_evaluation"] is False


def test_part3_requested_for_employee_is_error(example):
    doc = example("jan_periodic_c")
    doc["part3_requested"] = True
    out = evaluate(doc)
    assert "P-PART3" in rule_ids(out["validation"]["errors"])


def test_anna_civil_servant_part3_attached(example):
    out = evaluate(example("anna_periodic_b"), now="2026-11-21T15:00:00+01:00")
    assert out["result"] == "pozytywna" and out["average"] == 6.0
    assert out["overall_level"]["key"] == "na_poziomie"
    assert out["part3_attached"] == "tak" and out["print"]["include_part3"] is True
    assert out["period"]["from"] == "2024-11-08"  # przypis 6: uzupełnione z Części I
    assert out["objection_notice"].startswith("Zgodnie z art. 83 ust. 1")


@pytest.mark.parametrize("status,requested,result,attached,err", [
    ("urzednik_sc", False, "pozytywna", "nie", False),
    ("urzednik_sc", True, "pozytywna", "tak", False),
    ("urzednik_sc", True, "negatywna", "nie", True),
    ("pracownik_sc", False, "pozytywna", "nie_dotyczy", False),
])
def test_part3_matrix(status, requested, result, attached, err):
    p3 = part3_status(status, requested, result)
    assert p3["part3_attached"] == attached and bool(p3["error"]) == err


# ---------- P-MAX-ADDITIONAL / P-MANDATORY ----------
def test_more_than_three_additional_is_error(example):
    doc = example("jan_periodic_c")
    for cid in ("kreatywnosc", "negocjowanie", "myslenie_analityczne", "wystapienia_publiczne"):
        doc["criteria"].append({"id": cid, "kind": "additional", "indicator_ratings": [], "final_points": 5})
    out = evaluate(doc)
    assert "P-MAX-ADDITIONAL" in rule_ids(out["validation"]["errors"])
    doc["criteria"].pop()
    assert "P-MAX-ADDITIONAL" not in rule_ids(evaluate(doc)["validation"]["errors"])


def test_additional_cannot_duplicate_mandatory_and_missing_mandatory(example):
    doc = example("anna_periodic_b")
    doc["criteria"] = [c for c in doc["criteria"] if c["id"] != "komunikacja"]
    doc["criteria"].append({"id": "wspolpraca", "kind": "additional", "final_points": 5})
    errs = rule_ids(evaluate(doc)["validation"]["errors"])
    assert {"P-MANDATORY", "P-MAX-ADDITIONAL"} <= errs


def test_period_from_mismatch_and_order(example):
    doc = example("jan_periodic_c")
    doc["period"] = {"from": "2025-01-10", "to": "2024-12-01"}
    out = evaluate(doc)
    assert "P-PERIOD-FROM" in rule_ids(out["validation"]["warnings"])
    assert "P-PERIOD-TO" in rule_ids(out["validation"]["errors"])


# ---------- Pierwsza ocena ----------
def test_piotr_positive_with_exam_not_applicable(example):
    out = evaluate(example("piotr_first_eval_positive"))
    assert out["result"] == "pozytywna" and out["average"] == 5.4
    assert out["overall_level"] is None and out["objection_notice"] is None
    assert out["print"]["include_development_conclusions"] is True
    assert out["validation"]["ok"]


@pytest.mark.parametrize("exam,result", [("tak", "pozytywna"), ("nie_dotyczy", "pozytywna"), ("nie", "negatywna"), (None, None)])
def test_first_eval_exam_condition(config, exam, result):
    assert first_eval_outcome([5, 7, 3, 5, 7], exam, True, config)["result"] == result


def test_first_eval_two_lowest_is_negative_even_with_total_5(example):
    out = evaluate(example("piotr_first_eval_negative"))
    assert out["average"] == 5.0 and out["result"] == "negatywna"
    failed = [c["id"] for c in out["outcome"]["conditions"] if c["met"] is False]
    assert failed == ["F-MAX-ONE-LOWEST"]
    assert "G-FIRST-TWO-LOWEST" in rule_ids(out["guard"])


def test_first_eval_total_just_below_threshold(config):
    res = first_eval_outcome([3, 5, 5, 5, 5], "tak", True, config)  # 4,6
    assert res["result"] == "negatywna"
    assert [c["id"] for c in res["conditions"] if c["met"] is False] == ["F-MIN-TOTAL"]
    assert first_eval_outcome([3, 7, 5, 5, 5], "tak", True, config)["result"] == "pozytywna"  # dokładnie 5,0


def test_first_eval_report_late_is_negative(config):
    assert first_eval_outcome([7, 7, 7, 7, 7], "tak", False, config)["result"] == "negatywna"


def test_first_eval_development_conclusions_blocked_when_negative(example):
    doc = example("piotr_first_eval_negative")
    doc["development_conclusions"] = "Szkolenie X"
    out = evaluate(doc)
    assert "F-DEV-ONLY-POSITIVE" in rule_ids(out["validation"]["errors"])
    assert out["print"]["include_development_conclusions"] is False
    doc["justification"] = None
    assert "F-JUSTIFICATION" in rule_ids(evaluate(doc)["validation"]["errors"])


def test_first_eval_rejects_additional_and_wrong_scale(example):
    doc = example("piotr_first_eval_positive")
    doc["criteria"][0]["final_points"] = 9
    doc["criteria"].append({"id": "kreatywnosc", "kind": "additional", "final_points": 5})
    errs = rule_ids(evaluate(doc)["validation"]["errors"])
    assert {"F-SCALE", "F-TOTAL"} <= errs


def test_exam_not_applicable_requires_exemption(example):
    doc = example("piotr_first_eval_positive")
    doc["exam_exemption"] = None
    assert "F-EXAM" in rule_ids(evaluate(doc)["validation"]["warnings"])


# ---------- S-HUMAN-DECIDES / audit_log ----------
def test_engine_never_sets_final_points(example):
    doc = example("jan_periodic_c")
    for c in doc["criteria"]:
        c["final_points"] = None
    out = evaluate(doc)
    assert all(c["final_points"] is None for c in out["criteria"])
    assert all(c["suggestion"]["points"] is not None for c in out["criteria"])
    assert out["result"] is None and out["validation"]["complete"] is False


def test_override_recorded_in_audit_log(example):
    out = evaluate(example("jan_periodic_c"))
    entry = record_decision(out, "komunikacja", 5, actor="marek.kierownik-demo", note="Pisma wymagały poprawek",
                            at="2026-11-21T15:00:00+01:00", allowed_points=[1, 3, 5, 7, 9])
    assert entry["action"] == "override_suggestion" and entry["suggested"] == 7 and entry["final"] == 5
    assert out["criteria"][-1]["override_note"] == "Pisma wymagały poprawek"
    same = record_decision(out, "rzetelnosc", 5, actor="marek.kierownik-demo", at="2026-11-21T15:01:00+01:00")
    assert same["action"] == "final_points_set" and same["note"] is None
    with pytest.raises(ValueError):
        record_decision(out, "rzetelnosc", 4, actor="x", allowed_points=[1, 3, 5, 7, 9])


def test_evaluate_reconciles_overrides_once(example):
    out = evaluate(example("anna_periodic_b"), now="2026-11-21T15:00:00+01:00")
    entries = [e for e in out["audit_log"] if e["criterion_id"] == "podejmowanie_decyzji_i_odpowiedzialnosc"]
    assert len(entries) == 1 and entries[0]["suggested"] == 7 and entries[0]["final"] == 5
    assert entries[0]["note"].startswith("Decyzje w incydencie")
    again = evaluate(out, now="2026-11-21T15:05:00+01:00")
    assert len(again["audit_log"]) == len(out["audit_log"])


# ---------- Strażnik ----------
def test_guard_extreme_without_sdr_and_uniform_and_big_override(config):
    doc = {"form": "periodic_c", "criteria": [
        {"id": "komunikacja", "name": "Komunikacja", "indicator_ratings": ratings("komunikacja", [5, 5, 5, 5]),
         "suggestion": {"points": 9}, "final_points": 3},
    ]}
    ids = rule_ids(run_guard(doc))
    assert {"G-EXTREME-NO-SDR", "G-UNIFORM-LEVELS", "G-BIG-OVERRIDE"} <= ids
    for m in run_guard(doc):
        assert m["message"] and m["source"] and m["rule_id"].startswith("G-")


def test_guard_quiet_on_documented_extreme(config):
    r = ratings("rzetelnosc", [5, 4])
    r[0]["sdr_note"] = "S: audyt; D: wykrył błąd; R: korekta przed publikacją."
    doc = {"form": "periodic_c", "criteria": [{"id": "rzetelnosc", "indicator_ratings": r, "final_points": 9,
                                               "suggestion": {"points": 9}}]}
    assert run_guard(doc) == []


# ---------- Schemat / CLI ----------
@pytest.mark.parametrize("name", ["anna_periodic_b", "jan_periodic_c", "ewa_periodic_c_negative",
                                  "piotr_first_eval_positive", "piotr_first_eval_negative"])
def test_examples_are_valid(example, name):
    out = evaluate(example(name))
    assert out["validation"]["ok"], out["validation"]["errors"]
    assert out["validation"]["complete"]


def test_schema_errors_reported(example):
    doc = example("jan_periodic_c")
    doc["period"]["to"] = "30.11.2026"
    doc["criteria"][0]["indicator_ratings"][0]["level"] = 7
    errs = evaluate(doc)["validation"]["errors"]
    assert any(e["rule_id"] == "SCHEMA" and e["path"] == "$.period.to" for e in errs)
    assert any(e["rule_id"] == "SCHEMA" and "indicator_ratings[0].level" in e["path"] for e in errs)
    bad = evaluate({"schema_version": "1.0", "form": "periodic_x", "employee": {}, "evaluator": {}, "criteria": []})
    assert bad["validation"]["ok"] is False


def test_cli_exit_codes(tmp_path):
    script = SKILL_DIR / "scripts" / "evaluate.py"
    ok = subprocess.run([sys.executable, str(script), "--input", str(SKILL_DIR / "assets/examples/anna_periodic_b.json")],
                        capture_output=True, text=True, encoding="utf-8")
    assert ok.returncode == 0 and json.loads(ok.stdout)["result"] == "pozytywna"
    doc = json.loads((SKILL_DIR / "assets/examples/ewa_periodic_c_negative.json").read_text(encoding="utf-8"))
    doc["justification"] = None
    p = tmp_path / "ewa.json"
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    bad = subprocess.run([sys.executable, str(script), "--input", str(p)], capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 1


def test_periodic_scale_rejects_even_points(example):
    doc = example("jan_periodic_c")
    doc["criteria"][0]["final_points"] = 3
    doc["criteria"][1]["final_points"] = 1
    assert "P-SCALE" not in rule_ids(evaluate(doc)["validation"]["errors"])
    doc["criteria"][0]["final_points"] = 4  # schemat (enum) i reguła skali
    errs = evaluate(doc)["validation"]["errors"]
    assert "P-SCALE" in rule_ids(errs)


def test_first_eval_without_unit_head_warns(example):
    doc = example("piotr_first_eval_positive")
    del doc["unit_head"]
    assert "F-UNIT-HEAD" in rule_ids(evaluate(doc)["validation"]["warnings"])


def test_guard_all_no_basis_info(example):
    doc = example("jan_periodic_c")
    for r in doc["criteria"][1]["indicator_ratings"]:
        r["level"], r["no_basis"] = None, True
    out = evaluate(doc)
    assert out["criteria"][1]["suggestion"]["points"] is None
    assert "G-ALL-NO-BASIS" in rule_ids(out["guard"])


# ---------- Integracja z modelem kompetencji (agent DANE) ----------
def _model_path():
    env = os.environ.get("KOMPAS_MODEL_JSON")
    if env:
        return Path(env)
    return SKILL_DIR.parents[2] / "data-samples" / "processed" / "competency_model.json"


@pytest.mark.skipif(not _model_path().exists(), reason="brak competency_model.json (uruchom build_data.py agenta DANE)")
@pytest.mark.parametrize("form", ["periodic_b", "periodic_c", "first_eval"])
def test_integration_with_competency_model(config, form):
    model = json.loads(_model_path().read_text(encoding="utf-8"))
    comps = {c["id"]: c for c in model["competencies"]}
    assert len(comps) == 14 and sum(len(c["indicators"]) for c in comps.values()) == 49
    kind = "first_eval_element" if form == "first_eval" else "mandatory"
    criteria = []
    for cid in config["forms"][form]["mandatory_criteria"]:
        assert cid in comps, f"brak {cid} w modelu"
        inds = comps[cid]["indicators"]
        criteria.append({"id": cid, "kind": kind, "final_points": 5,
                         "indicator_ratings": [{"indicator_id": i["id"], "level": 3, "no_basis": False} for i in inds]})
    doc = {"schema_version": "1.0", "form": form, "criteria": criteria,
           "employee": {"full_name": "Jan Testowy", "position": "Radca", "corps_status": "pracownik_sc"},
           "evaluator": {"full_name": "Marek Kierownik-Demo", "position": "Dyrektor"},
           "exam": "tak", "report_submitted_on_time": True, "development_conclusions": "x",
           "unit_head": {"full_name": "Marek Kierownik-Demo"}}
    out = evaluate(doc, model=model)
    for c in out["criteria"]:
        assert c["suggestion"]["points"] == 5
        assert c["suggestion"]["total_count"] == len(comps[c["id"]]["indicators"])
    assert out["result"] == "pozytywna"
    assert not [w for w in out["validation"]["warnings"] if "nie istnieje w modelu" in w["message"]]
