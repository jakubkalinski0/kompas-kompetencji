"""Dane demo ładowane przy każdym starcie (dysk darmowego Render jest nietrwały).

Źródło: `kompas-demo-i-pitch/assets/personas.json` (fikcyjne osoby) i przykłady dokumentów oceny
z `kompas-model-i-silnik-oceny/assets/examples/` (te same persony). Procesy demo są tylko do podglądu,
żeby jurorzy logujący się na to samo konto nie nadpisywali sobie przykładów.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import settings
from .store import Store

EXAMPLES_DIR = settings.SKILLS_DIR / "kompas-model-i-silnik-oceny" / "assets" / "examples"
# persona → przykład dokumentu oceny (stanowisko, komórka, status w korpusie)
PERSONA_EXAMPLE = {
    "anna": "anna_periodic_b.json",
    "jan": "jan_periodic_c.json",
    "ewa": "ewa_periodic_c_negative.json",
    "piotr": "piotr_first_eval_positive.json",
}
DEMO_PROCESSES = [
    # (id procesu, persona, status) – oceny już sporządzone, widoczne dla wszystkich sesji
    ("P-2026-001", "anna", "do_podpisu"),
    ("P-2026-002", "jan", "zakonczona"),
    ("P-2026-004", "piotr", "do_podpisu"),
]
USER_POSITIONS = {
    "marek": "Dyrektor Departamentu Cyberbezpieczeństwa (dane fikcyjne)",
    "barbara": "Kierująca komórką organizacyjną (dane fikcyjne)",
    "zofia": "Specjalistka ds. kadr, Biuro Dyrektora Generalnego (dane fikcyjne)",
}


def _example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def employee_record(persona: dict) -> dict:
    ex = _example(PERSONA_EXAMPLE[persona["id"]])["employee"] if persona["id"] in PERSONA_EXAMPLE else {}
    return {
        "persona_id": persona["id"],
        "full_name": persona["full_name"],
        "position": ex.get("position") or persona.get("position", ""),
        "unit": ex.get("unit", ""),
        "corps_status": persona.get("corps_status") or ex.get("corps_status", "pracownik_sc"),
        "previous_evaluation_date": persona.get("previous_evaluation_date"),
        "employment_start": persona.get("employment_start"),
        "contract_end": persona.get("contract_end"),
        "process": persona.get("process"),
        "expected_form": persona.get("expected_form"),
        "scenario": persona.get("scenario"),
    }


def run(store: Store, personas_path: Path = settings.PERSONAS_PATH) -> dict:
    personas = json.loads(Path(personas_path).read_text(encoding="utf-8"))
    for p in personas["oceniajacy"] + personas["hr"]:
        store.upsert_user(p["id"], p["full_name"], p["role"],
                          {"id": p["id"], "full_name": p["full_name"], "role": p["role"],
                           "position": USER_POSITIONS.get(p["id"], p.get("position", ""))})
    for p in personas["oceniani"]:
        store.upsert_employee(p["id"], p["full_name"], employee_record(p))

    from . import workflow  # import tu: workflow ładuje dane z DATA_DIR
    created = 0
    for pid, persona_id, status in DEMO_PROCESSES:
        if store.has_process(pid):
            continue
        doc = _example(PERSONA_EXAMPLE[persona_id])
        doc["case_id"] = pid
        emp = dict(store.get_employee(persona_id))
        kind = "first" if doc["form"] == "first_eval" else "periodic"
        if kind == "first":
            # w scenariuszu demo ocenia Marek (przełożony), a kierującą komórką jest Barbara Komórka-Demo
            marek, barbara = store.get_user("marek"), store.get_user("barbara")
            doc["evaluator"] = {"full_name": marek["full_name"], "position": marek["position"],
                                "unit": doc["employee"].get("unit", "")}
            doc["unit_head"].update(full_name=barbara["full_name"], position=barbara["position"])
            emp["employment_start"] = doc["employee"].get("employment_start")
            steps = {"rozmowa-wstepna": True, "warunki": True}
        else:
            steps = {"osp": True, "arkusz": True, "kryteria": True, "czesc-i": True}
        proc = {
            "id": pid, "sandbox": None, "owner": "marek", "kind": kind, "status": status,
            "created_at": "2026-11-18T09:00:00+01:00", "updated_at": "2026-11-20T15:30:00+01:00",
            "demo": True, "employee": emp, "osp": None, "proposal": None, "candidates": None,
            "steps_done": steps, "doc": doc, "trail": [], "pdf_generated_at": "2026-11-20T15:30:00+01:00",
        }
        # sugestie do widoku (silnik nie zmienia final_points)
        for c in doc["criteria"]:
            if c["id"] in workflow.COMPETENCIES:
                c["suggestion"] = workflow.engine.suggest_criterion(
                    c.get("indicator_ratings") or [], doc["form"], workflow.CONFIG,
                    total_indicators=len(workflow.COMPETENCIES[c["id"]]["indicators"]))
        store.save_process(proc)
        created += 1
    return {"users": len(personas["oceniajacy"]) + len(personas["hr"]), "employees": len(personas["oceniani"]),
            "demo_processes_created": created}
