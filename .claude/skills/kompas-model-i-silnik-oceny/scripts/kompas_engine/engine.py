"""Orkiestracja: dokument C3 → sugestie, wynik, flagi druku, ślad, walidacja, strażnik."""
from __future__ import annotations

import copy

from . import audit
from .config import catalog_names, load_config, load_schema
from .guard import run_guard
from .rules import OBJECTION_FOOTNOTE_17, OBJECTION_NOTICE, first_eval_outcome, part3_status, periodic_outcome
from .scoring import suggest_criterion
from .validate import business_issues, outcome_issues, schema_errors


def _model_counts(model: dict | None) -> dict[str, int]:
    if not model:
        return {}
    return {c["id"]: len(c.get("indicators", [])) for c in model.get("competencies", [])}


def _model_indicator_ids(model: dict | None) -> set[str]:
    if not model:
        return set()
    return {i["id"] for c in model.get("competencies", []) for i in c.get("indicators", [])}


def suggest_all(doc: dict, config: dict | None = None, model: dict | None = None, method: str | None = None) -> dict:
    """Uzupełnia criteria[].suggestion (in place) i zwraca dokument. Nie dotyka final_points."""
    config = config or load_config()
    counts = _model_counts(model)
    for c in doc.get("criteria", []):
        ratings = c.get("indicator_ratings") or []
        total = counts.get(c.get("id"))
        if not ratings and total is None:
            c["suggestion"] = None
            continue
        try:
            c["suggestion"] = suggest_criterion(ratings, doc["form"], config, total_indicators=total, method=method)
        except ValueError as exc:  # np. poziom wskaźnika spoza 1–5 – raportuje walidacja schematu
            c["suggestion"] = {"points": None, "level": None, "level_key": None, "level_label": None,
                               "average": None, "average_display": None, "method": method or config["suggestion"]["method"],
                               "formula": f"Sugestia niepoliczona: {exc}", "rated_count": 0, "no_basis_count": 0,
                               "unrated_count": 0, "total_count": len(ratings), "mapping_note": None, "warnings": [str(exc)]}
    return doc


def evaluate(doc: dict, config: dict | None = None, model: dict | None = None, now: str | None = None,
             method: str | None = None, schema: dict | None = None) -> dict:
    """Pełne przeliczenie dokumentu. Zwraca NOWY dokument (wejście bez zmian).

    - sugestie per kryterium (S-*), wynik (P-*/F-*), flagi druku, pouczenie,
    - uzupełnienie audit_log o niezapisane odejścia od sugestii,
    - validation {ok, complete, errors, warnings} + guard [].
    """
    config = config or load_config()
    schema = schema or load_schema()
    out = copy.deepcopy(doc)
    errors = list(schema_errors(out, schema))
    if any(e["path"] in ("$.form", "$.criteria", "$.employee", "$") for e in errors) or out.get("form") not in config["forms"]:
        out["validation"] = {"ok": False, "complete": False, "errors": errors, "warnings": []}
        out["guard"] = []
        return out

    form = config["forms"][out["form"]]
    names = catalog_names(config)
    for c in out.get("criteria", []):
        if not c.get("name") and c.get("id") in names:
            c["name"] = names[c["id"]]

    suggest_all(out, config, model, method)
    finals = [c.get("final_points") for c in out.get("criteria", [])]
    warnings: list[dict] = []

    if form["process"] == "periodic":
        res = periodic_outcome(finals, config)
        out["average"], out["average_display"] = res["average"], res["average_display"]
        out["overall_level"], out["result"] = res["overall_level"], res["result"]
        period = out.setdefault("period", {})
        meeting = (out.get("part1") or {}).get("criteria_meeting_date")
        if not period.get("from") and meeting:
            period["from"] = meeting  # przypis 6: definicja daty „od”
            warnings.append({"rule_id": "P-PERIOD-FROM", "path": "$.period.from", "source": "przypis 6 Arkusza B/C",
                             "message": f"Datę „od” uzupełniono datą zapoznania z kryteriami z Części I ({meeting})."})
        period.setdefault("to_basis", "data_sporzadzenia_oceny")
        p3 = part3_status(out["employee"]["corps_status"], bool(out.get("part3_requested")), res["result"])
        out["part3_attached"] = p3["part3_attached"]
        if p3["error"]:
            rid = "P-PART3" if out["employee"]["corps_status"] == "pracownik_sc" else "P-PART3-POSITIVE"
            errors.append({"rule_id": rid, "path": "$.part3_requested", "message": p3["error"], "source": ""})
        out["objection_notice"] = OBJECTION_NOTICE
        out["print"] = {
            "include_part3": p3["include_part3"],
            "include_previous_evaluation": out["employee"]["corps_status"] == "urzednik_sc",
            "include_development_conclusions": True,
            "include_objection_notice": True,
            "objection_footnote": OBJECTION_FOOTNOTE_17,
        }
        out["outcome"] = {"formula": res["formula"], "reasons": res["reasons"]}
    else:
        res = first_eval_outcome(finals, out.get("exam"), out.get("report_submitted_on_time"), config)
        out["average"], out["average_display"] = res["average"], res["average_display"]
        out["overall_level"], out["result"] = None, res["result"]
        out["objection_notice"] = None
        out["print"] = {
            "include_part3": False,
            "include_previous_evaluation": False,
            "include_development_conclusions": res["result"] == "pozytywna",
            "include_objection_notice": False,
        }
        out["outcome"] = {"formula": res["formula"], "reasons": res["reasons"], "conditions": res["conditions"]}

    actor = f"{(out.get('evaluator') or {}).get('full_name', 'oceniający')} (przełożony)"
    audit.reconcile_overrides(out, actor=actor, at=now)

    b_err, b_warn = business_issues(out, config)
    o_err, o_warn = outcome_issues(out, config)
    errors += b_err + o_err
    warnings += b_warn + o_warn
    known = _model_indicator_ids(model)
    if known:
        for c in out.get("criteria", []):
            for r in c.get("indicator_ratings") or []:
                if r.get("indicator_id") not in known:
                    warnings.append({"rule_id": "S-INDICATOR-POINTS", "path": f"$.criteria[{c.get('id')}]",
                                     "source": "competency_model.json", "message": f"Wskaźnik {r.get('indicator_id')} nie istnieje w modelu kompetencji."})
    out["validation"] = {
        "ok": not errors,
        "complete": not errors and res["result"] is not None,
        "errors": errors,
        "warnings": warnings,
    }
    out["guard"] = run_guard(out)
    return out
