"""Ścieżka oceny okresowej: OSP → arkusz B/C → kryteria → Część I → wskaźniki → decyzje → wynik → PDF.

Cała logika oceny pochodzi ze skilli: sugestię i wynik liczy `kompas_engine` (reguła, nie LLM),
propozycję arkusza – `propose_form`, PDF – `render_pdf`. Ten moduł trzyma stan procesu i ślad decyzji.
Zasada z pkt 3 i 5 treści zadania: system tylko podpowiada, `final_points` ustawia wyłącznie
przełożony przez `decide()`.
"""
from __future__ import annotations

import json
import secrets
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import settings
from .skills import deadlines, engine, propose_form, render_pdf

CONFIG = engine.load_config()
MODEL = engine.load_model(settings.DATA_DIR / "competency_model.json")
COMPETENCIES: dict[str, dict] = {c["id"]: c for c in MODEL["competencies"]}
CATALOG: dict[str, str] = {c["id"]: c["name"] for c in CONFIG["criteria_catalog"]}
INDICATOR_TEXT: dict[str, str] = {i["id"]: i["text"] for c in MODEL["competencies"] for i in c["indicators"]}
ANNEX1 = json.loads((settings.DATA_DIR / "annex1_criteria.json").read_text(encoding="utf-8"))
ANNEX1_BY_ID: dict[str, dict] = {c["id"]: c for c in ANNEX1["criteria"]}
LEVELS: list[dict] = MODEL["scale"]
TZ = ZoneInfo(settings.TIMEZONE)

FORM_LABELS = {"periodic_b": "Arkusz B", "periodic_c": "Arkusz C", "first_eval": "Arkusz pierwszej oceny"}
FORM_SCOPE = {
    "periodic_b": "stanowisko, na którym praca polega na bezpośrednim kierowaniu pracownikami (§ 3 ust. 3 rozp. 2016)",
    "periodic_c": "pozostałe stanowiska, bez bezpośredniego kierowania pracownikami (§ 3 ust. 4 rozp. 2016)",
}
MANDATORY_BASIS = {"periodic_b": "§ 4 ust. 2 rozp. 2016", "periodic_c": "§ 4 ust. 3 rozp. 2016"}
ROLE_LABELS = {"przelozony": "przełożony", "hr_admin": "HR", "kierujacy_komorka": "kierujący komórką"}
STEPS_PERIODIC = [
    ("osp", "Opis stanowiska (OSP)"),
    ("arkusz", "Arkusz B albo C"),
    ("kryteria", "Kryteria oceny"),
    ("czesc-i", "Część I – daty"),
    ("wskazniki", "Wskaźniki i decyzje"),
    ("podsumowanie", "Wynik i arkusz PDF"),
]
# Pierwsza ocena (rozp. 2015): rozmowa wstępna (§ 3–4) → warunki § 10 ust. 1 pkt 1–2 → 5 elementów (§ 2 pkt 1) → wynik
STEPS_FIRST = [
    ("rozmowa-wstepna", "Rozmowa wstępna i terminy"),
    ("warunki", "Egzamin i sprawozdanie"),
    ("wskazniki", "Elementy oceny"),
    ("podsumowanie", "Wynik i arkusz PDF"),
]
EXEMPTION_LABELS = {k: v for k, v in CONFIG["forms"]["first_eval"]["exam_exemptions"].items() if k != "source"}
# podstawa prawna kroku – na marginesie strony (jak numer części w raporcie)
STEP_BASIS = {
    ("periodic", "osp"): "§ 2 ust. 2 i § 3 ust. 3–4 rozp. 2016 – obowiązki z opisu stanowiska",
    ("periodic", "arkusz"): "§ 3 ust. 3–4 rozp. 2016; przypis 1 arkuszy B i C",
    ("periodic", "kryteria"): "§ 4 ust. 2–3 i § 5 ust. 2 rozp. 2016",
    ("periodic", "czesc-i"): "§ 5–7 rozp. 2016; przypis 6 arkusza; art. 81 ust. 4 ustawy",
    ("periodic", "wskazniki"): "model kompetencji MC; skala § 11 ust. 1 pkt 1 rozp. 2016",
    ("periodic", "podsumowanie"): "§ 11 ust. 1–5 rozp. 2016; art. 83 ust. 1 ustawy",
    ("first", "rozmowa-wstepna"): "§ 3–4 rozp. 2015; art. 38 ust. 2 ustawy",
    ("first", "warunki"): "§ 10 ust. 1–3 rozp. 2015",
    ("first", "wskazniki"): "§ 2 pkt 1 i § 9 ust. 1 rozp. 2015; model kompetencji MC",
    ("first", "podsumowanie"): "§ 7 pkt 3 i § 10 rozp. 2015",
}
TRAIL_LABELS = {
    "osp_parsed": "Wczytano opis stanowiska",
    "osp_skipped": "Pominięto OSP",
    "form_confirmed": "Arkusz potwierdzony przez przełożonego",
    "form_changed": "Przełożony wybrał inny arkusz niż propozycja",
    "criteria_selected": "Kryteria oceny ustalone",
    "part1_saved": "Zapisano daty z Części I",
    "final_points_set": "Ocena cząstkowa zgodna z sugestią",
    "override_suggestion": "Ocena cząstkowa inna niż sugestia",
    "summary_saved": "Zapisano dane do arkusza",
    "pdf_generated": "Wygenerowano arkusz PDF",
    "intro_saved": "Zapisano rozmowę wstępną i terminy",
    "conditions_saved": "Zapisano egzamin i sprawozdanie",
}


class WorkflowError(ValueError):
    """Błąd do pokazania przełożonemu (zła data, za dużo kryteriów, brak decyzji…)."""


# ---------------------------------------------------------------- czas
def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def today_iso() -> str:
    return now().date().isoformat()


def actor_label(user: dict) -> str:
    return f"{user['full_name']} ({ROLE_LABELS.get(user['role'], user['role'])})"


def _date(value: str | None, field: str, required: bool = True) -> str | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise WorkflowError(f"Uzupełnij pole „{field}”.")
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise WorkflowError(f"W polu „{field}” jest niepoprawna data: {value}.") from None


# ---------------------------------------------------------------- proces
def scale_points(form: str) -> list[int]:
    return CONFIG["scales"][CONFIG["forms"][form]["scale"]]["points"]


def scale_labels(form: str) -> dict[str, str]:
    return CONFIG["scales"][CONFIG["forms"][form]["scale"]]["labels"]


def mandatory_for(form: str) -> list[str]:
    return CONFIG["forms"][form]["mandatory_criteria"]


def new_periodic(user: dict, sandbox: str, employee: dict) -> dict:
    ts = now_iso()
    return {
        "id": f"P-{now():%Y}-{secrets.token_hex(2).upper()}",
        "sandbox": sandbox,
        "owner": user["id"],
        "kind": "periodic",
        "status": "nie_rozpoczeta",
        "created_at": ts,
        "updated_at": ts,
        "demo": False,
        "employee": employee,
        "osp": None,
        "proposal": None,
        "candidates": None,
        "steps_done": {"osp": False, "arkusz": False, "kryteria": False, "czesc-i": False},
        "doc": None,
        "trail": [],
        "pdf_generated_at": None,
    }


def touch(proc: dict) -> None:
    proc["updated_at"] = now_iso()


def _trail(proc: dict, user: dict, action: str, note: str | None = None, suggested=None, final=None) -> None:
    proc["trail"].append({"at": now_iso(), "actor": actor_label(user), "action": action, "note": note,
                          "suggested": suggested, "final": final})


def trail(proc: dict) -> list[dict]:
    """Ślad procesu (arkusz, kryteria, daty) + ślad decyzji z dokumentu C3 (audit_log), chronologicznie."""
    items = [dict(e, source="proces") for e in proc.get("trail", [])]
    doc = proc.get("doc") or {}
    for e in doc.get("audit_log", []):
        items.append(dict(e, source="decyzja", criterion_name=CATALOG.get(e.get("criterion_id"), e.get("criterion_id"))))
    return sorted(items, key=lambda e: e.get("at") or "")


def steps_for(proc: dict) -> list[tuple[str, str]]:
    return STEPS_FIRST if proc["kind"] == "first" else STEPS_PERIODIC


def step_state(proc: dict) -> dict[str, str]:
    """Stan kroków do paska: done | open | locked."""
    done = proc["steps_done"]
    doc = proc.get("doc")
    decided = bool(doc) and all(c.get("final_points") is not None for c in doc["criteria"])
    if proc["kind"] == "first":
        return {
            "rozmowa-wstepna": "done" if done.get("rozmowa-wstepna") else "open",
            "warunki": "done" if done.get("warunki") else ("open" if done.get("rozmowa-wstepna") else "locked"),
            "wskazniki": "done" if decided else ("open" if done.get("rozmowa-wstepna") else "locked"),
            "podsumowanie": "done" if proc.get("pdf_generated_at") else ("open" if decided and done.get("warunki") else "locked"),
        }
    st = {
        "osp": "done" if done["osp"] else "open",
        "arkusz": "done" if done["arkusz"] else ("open" if done["osp"] else "locked"),
        "kryteria": "done" if done["kryteria"] else ("open" if done["arkusz"] else "locked"),
        "czesc-i": "done" if done["czesc-i"] else ("open" if done["kryteria"] else "locked"),
        "wskazniki": "done" if decided else ("open" if done["czesc-i"] else "locked"),
        "podsumowanie": "done" if proc.get("pdf_generated_at") else ("open" if decided else "locked"),
    }
    return st


def next_step(proc: dict) -> str:
    st = step_state(proc)
    for key, _ in steps_for(proc):
        if st[key] == "open":
            return key
    return "podsumowanie"


# ---------------------------------------------------------------- pierwsza ocena
def new_first(user: dict, sandbox: str, employee: dict, unit_head: dict) -> dict:
    proc = new_periodic(user, sandbox, employee)
    proc["kind"] = "first"
    proc["steps_done"] = {"rozmowa-wstepna": False, "warunki": False}
    doc = _new_doc(proc, "first_eval", user)
    doc["criteria"] = [_criterion(cid, "first_eval_element") for cid in mandatory_for("first_eval")]
    doc["employee"]["employment_start"] = employee.get("employment_start")
    for key in ("part1", "period", "part3_requested"):
        doc.pop(key, None)
    doc["unit_head"] = {"full_name": unit_head["full_name"], "position": unit_head.get("position") or "",
                        "unit": employee.get("unit") or "", "participated_in_interview": False,
                        "agreement_confirmed": False, "signed_on": None}
    doc["first_eval_intro"] = {"intro_interview_date": None, "report_deadline": {"from": None, "to": None},
                               "evaluation_window": {"from": None, "to": None}}
    doc["exam"] = None
    doc["exam_exemption"] = None
    doc["report_submitted_on_time"] = None
    proc["doc"] = doc
    return proc


def first_calendar(proc: dict, intro_date: str | None = None) -> list[dict]:
    """Terminy pierwszej oceny z podstawą prawną (deadlines.first_calendar): rozmowa wstępna, sprawozdanie, okno oceny."""
    emp = proc["employee"]
    if not emp.get("employment_start"):
        return []
    intro = (proc["doc"].get("first_eval_intro") or {})
    dates = {"employment_start": emp["employment_start"], "contract_end": emp.get("contract_end"),
             "intro_interview_date": intro_date or intro.get("intro_interview_date")}
    rd = intro.get("report_deadline") or {}
    if rd.get("from") and rd.get("to"):
        dates["report_deadline"] = rd
    return deadlines.first_calendar({"dates": {k: v for k, v in dates.items() if v}})


def set_intro(proc: dict, user: dict, form: dict) -> None:
    doc = proc["doc"]
    start = _date(form.get("employment_start"), "Data nawiązania stosunku pracy")
    end = _date(form.get("contract_end"), "Data końca umowy", required=False)
    intro = _date(form.get("intro_interview_date"), "Data rozmowy wstępnej")
    rf = _date(form.get("report_from"), "Termin sprawozdania – od")
    rt = _date(form.get("report_to"), "Termin sprawozdania – do")
    if rt < rf:
        raise WorkflowError("Termin sprawozdania: data „do” nie może być wcześniejsza niż „od”.")
    if intro < start:
        raise WorkflowError("Rozmowa wstępna nie może się odbyć przed nawiązaniem stosunku pracy.")
    head = (form.get("unit_head_name") or "").strip()
    if len(head) < 3:
        raise WorkflowError("Podaj kierującego komórką organizacyjną – pierwszej oceny dokonuje się w porozumieniu z nim "
                            "(art. 38 ust. 2 ustawy).")
    proc["employee"]["employment_start"], proc["employee"]["contract_end"] = start, end
    doc["employee"]["employment_start"] = start
    doc["unit_head"].update(full_name=head[:120], position=(form.get("unit_head_position") or "").strip()[:160])
    window = next((e["window"] for e in first_calendar(proc, intro) if e["task"] == "ocena"), None) or {}
    doc["first_eval_intro"] = {"intro_interview_date": intro, "report_deadline": {"from": rf, "to": rt},
                               "evaluation_window": {"from": window.get("from"), "to": window.get("to")}}
    proc["steps_done"]["rozmowa-wstepna"] = True
    if proc["status"] == "nie_rozpoczeta":
        proc["status"] = "kryteria_ustalone"  # etykieta dla pierwszej oceny: „Rozmowa wstępna odbyta”
    _trail(proc, user, "intro_saved", note=f"Rozmowa wstępna {intro}; sprawozdanie {rf} – {rt}; "
                                           f"okres oceny {window.get('from')} – {window.get('to')}")
    touch(proc)


def set_conditions(proc: dict, user: dict, exam: str, exemption: str | None, report: str) -> None:
    doc = proc["doc"]
    if exam not in ("tak", "nie", "nie_dotyczy"):
        raise WorkflowError("Zaznacz, czy oceniany zaliczył egzamin ze służby przygotowawczej.")
    if exam == "nie_dotyczy" and exemption not in EXEMPTION_LABELS:
        raise WorkflowError("Egzamin „nie dotyczy” – wskaż, który z trzech wyjątków § 10 ust. 3 rozp. 2015 zachodzi.")
    if report not in ("tak", "nie"):
        raise WorkflowError("Zaznacz, czy sprawozdanie zostało złożone w wyznaczonym terminie.")
    doc["exam"] = exam
    doc["exam_exemption"] = exemption if exam == "nie_dotyczy" else None
    doc["report_submitted_on_time"] = report == "tak"
    proc["steps_done"]["warunki"] = True
    if proc["status"] in ("nie_rozpoczeta", "kryteria_ustalone"):
        proc["status"] = "w_trakcie"
    label = {"tak": "zaliczony", "nie": "niezaliczony", "nie_dotyczy": "nie dotyczy"}[exam]
    _trail(proc, user, "conditions_saved", note=f"Egzamin: {label}"
           + (f" ({EXEMPTION_LABELS[exemption]})" if exam == "nie_dotyczy" else "")
           + f"; sprawozdanie w terminie: {'tak' if report == 'tak' else 'nie'}")
    touch(proc)


# ---------------------------------------------------------------- krok 1: OSP
def attach_osp(proc: dict, user: dict, parsed: dict, source: str, filename: str) -> None:
    proposal = propose_form.propose_form(parsed)
    proc["osp"] = {"source": source, "file": filename, "parsed": parsed, "warnings": parsed.get("warnings", [])}
    proc["proposal"] = proposal
    proc["candidates"] = propose_form.additional_candidates(parsed, proposal["proposed_form"])
    proc["steps_done"]["osp"] = True
    _trail(proc, user, "osp_parsed", note=f"{filename}: propozycja {FORM_LABELS[proposal['proposed_form']]} "
                                           f"(pewność: {proposal['confidence']}, reguła {proposal['rule_id']})")
    touch(proc)


def skip_osp(proc: dict, user: dict) -> None:
    proc["osp"] = {"source": "skipped", "file": None, "parsed": None, "warnings": []}
    proc["proposal"] = None
    proc["candidates"] = None
    proc["steps_done"]["osp"] = True
    _trail(proc, user, "osp_skipped", note="Arkusz i kryteria dodatkowe przełożony wybiera bez propozycji z OSP.")
    touch(proc)


# ---------------------------------------------------------------- krok 2: arkusz
def _criterion(cid: str, kind: str) -> dict:
    return {
        "id": cid, "name": CATALOG[cid], "kind": kind,
        "indicator_ratings": [{"indicator_id": i["id"], "level": None, "no_basis": False, "sdr_note": None}
                              for i in COMPETENCIES[cid]["indicators"]],
        "suggestion": None, "final_points": None, "override_note": None,
    }


def _new_doc(proc: dict, form: str, user: dict) -> dict:
    emp = proc["employee"]
    return {
        "schema_version": "1.0",
        "form": form,
        "case_id": proc["id"],
        "office_name": settings.OFFICE_NAME,
        "employee": {k: emp[k] for k in ("full_name", "position", "unit", "corps_status") if emp.get(k)},
        "evaluator": {"full_name": user["full_name"], "position": user.get("position") or "przełożony",
                      "unit": emp.get("unit") or ""},
        "part1": {"criteria_meeting_date": None, "evaluation_deadline": None},
        "interview_date": None,
        "period": {"from": None, "to": None},
        "criteria": [_criterion(cid, "mandatory") for cid in mandatory_for(form)],
        "justification": None,
        "development_conclusions": None,
        "part3_requested": False,
        "audit_log": [],
    }


def confirm_form(proc: dict, user: dict, form: str) -> None:
    if form not in ("periodic_b", "periodic_c"):
        raise WorkflowError("Wybierz arkusz B albo C.")
    suggested = (proc.get("proposal") or {}).get("proposed_form")
    action = "form_confirmed" if suggested in (None, form) else "form_changed"
    doc = proc.get("doc")
    if doc and doc["form"] != form:
        # zmiana arkusza: zostaw oceny wskaźników kryteriów, które są w obu arkuszach
        old = {c["id"]: c for c in doc["criteria"]}
        doc["form"] = form
        doc["criteria"] = [dict(old[c], kind="mandatory") if c in old else _criterion(c, "mandatory")
                           for c in mandatory_for(form)]
        proc["steps_done"]["kryteria"] = False
    elif not doc:
        proc["doc"] = _new_doc(proc, form, user)
    parsed = (proc.get("osp") or {}).get("parsed")
    proc["candidates"] = propose_form.additional_candidates(parsed, form) if parsed else None
    proc["steps_done"]["arkusz"] = True
    _trail(proc, user, action, note=f"{FORM_LABELS[form]} – {FORM_SCOPE[form]}",
           suggested=FORM_LABELS.get(suggested) if suggested else None, final=FORM_LABELS[form])
    touch(proc)


# ---------------------------------------------------------------- krok 3: kryteria
def additional_options(proc: dict) -> list[dict]:
    """Kryteria z zał. nr 1 spoza obowiązkowych; kandydaci z OSP na początku listy."""
    doc = proc["doc"]
    mandatory = set(mandatory_for(doc["form"]))
    chosen = {c["id"] for c in doc["criteria"] if c["kind"] == "additional"}
    cands = {c["id"]: c for c in ((proc.get("candidates") or {}).get("candidates") or [])}
    out = []
    for cid, name in CATALOG.items():
        if cid in mandatory:
            continue
        annex = ANNEX1_BY_ID.get(cid) or {}
        out.append({"id": cid, "name": name, "checked": cid in chosen, "candidate": cands.get(cid),
                    "description": annex.get("description") or [],
                    "indicators": [i["text"] for i in COMPETENCIES.get(cid, {}).get("indicators", [])]})
    out.sort(key=lambda o: (o["candidate"] is None, o["name"]))
    return out


def set_criteria(proc: dict, user: dict, additional_ids: list[str]) -> None:
    doc = proc["doc"]
    errors = propose_form.validate_selection(doc["form"], additional_ids)
    if errors:
        raise WorkflowError(" ".join(errors))
    existing = {c["id"]: c for c in doc["criteria"]}
    crit = [dict(existing.get(cid) or _criterion(cid, "mandatory"), kind="mandatory") for cid in mandatory_for(doc["form"])]
    crit += [dict(existing.get(cid) or _criterion(cid, "additional"), kind="additional") for cid in additional_ids]
    doc["criteria"] = crit
    proc["steps_done"]["kryteria"] = True
    names = ", ".join(CATALOG[c] for c in additional_ids) or "brak (dopuszczalne – § 2 ust. 2 rozp. 2016)"
    _trail(proc, user, "criteria_selected", note=f"Obowiązkowe wg {MANDATORY_BASIS[doc['form']]}; dodatkowe: {names}")
    touch(proc)


# ---------------------------------------------------------------- krok 4: Część I
def part1_hints(proc: dict) -> list[dict]:
    """Terminy z podstawą prawną (deadlines.periodic_calendar) z daty poprzedniej oceny, jeśli ją znamy."""
    prev = proc["employee"].get("previous_evaluation_date")
    if not prev:
        return []
    events = deadlines.periodic_calendar({"dates": {"previous_evaluation_date": prev, "previous_result": "pozytywna"}})
    return [e for e in events if e["task"] in ("kryteria", "ocena")]


def set_part1(proc: dict, user: dict, meeting: str | None, deadline: str | None, goals: str | None) -> None:
    doc = proc["doc"]
    m = _date(meeting, "Data zapoznania ocenianego z kryteriami")
    d = _date(deadline, "Termin sporządzenia oceny")
    if d < m:
        raise WorkflowError("Termin sporządzenia oceny nie może być wcześniejszy niż data ustalenia kryteriów.")
    doc["part1"] = {"criteria_meeting_date": m, "evaluation_deadline": d, "goals": (goals or "").strip() or None}
    doc.setdefault("period", {})["from"] = m  # przypis 6 arkusza B/C
    proc["steps_done"]["czesc-i"] = True
    if proc["status"] == "nie_rozpoczeta":
        proc["status"] = "kryteria_ustalone"
    _trail(proc, user, "part1_saved", note=f"Kryteria ustalone {m}; termin sporządzenia oceny {d}")
    touch(proc)


# ---------------------------------------------------------------- krok 5: wskaźniki i decyzje
def criterion(proc: dict, cid: str) -> dict:
    if not proc.get("doc"):
        raise WorkflowError("Ta ocena nie ma jeszcze wybranego arkusza.")
    for c in proc["doc"]["criteria"]:
        if c["id"] == cid:
            return c
    raise WorkflowError(f"Brak kryterium {cid} w tym arkuszu.")


def suggest(proc: dict, cid: str) -> dict:
    c = criterion(proc, cid)
    c["suggestion"] = engine.suggest_criterion(c["indicator_ratings"], proc["doc"]["form"], CONFIG,
                                               total_indicators=len(COMPETENCIES[cid]["indicators"]))
    return c["suggestion"]


def update_ratings(proc: dict, cid: str, form: dict) -> dict:
    """form: lvl::<indicator_id> = 1..5, nb::<indicator_id> = 1, sdr::<indicator_id> = tekst,
    ai::<indicator_id> = 1..5 – poziom zaproponowany przez asystenta oceny zachowań (zapisany obok wyboru przełożonego,
    żeby w danych było widać, co zaproponowało AI, a co zaznaczył przełożony)."""
    c = criterion(proc, cid)
    for r in c["indicator_ratings"]:
        iid = r["indicator_id"]
        nb = form.get(f"nb::{iid}") == "1"
        raw = (form.get(f"lvl::{iid}") or "").strip()
        r["no_basis"] = nb
        r["level"] = int(raw) if raw.isdigit() and 1 <= int(raw) <= 5 and not nb else None
        ai = (form.get(f"ai::{iid}") or "").strip()
        r["ai_proposed_level"] = int(ai) if ai.isdigit() and 1 <= int(ai) <= 5 else None
        note = (form.get(f"sdr::{iid}") or "").strip()
        r["sdr_note"] = note[:2000] or None
    sug = suggest(proc, cid)
    if proc["status"] in ("nie_rozpoczeta", "kryteria_ustalone"):
        proc["status"] = "w_trakcie"
    touch(proc)
    return sug


def decide(proc: dict, user: dict, cid: str, points: int, note: str | None) -> dict:
    form = proc["doc"]["form"]
    allowed = scale_points(form)
    if points not in allowed:
        raise WorkflowError(f"Ocena cząstkowa musi mieć wartość z arkusza: {', '.join(map(str, allowed))} pkt.")
    suggest(proc, cid)  # świeża sugestia do śladu
    entry = engine.record_decision(proc["doc"], cid, points, actor=actor_label(user),
                                   note=(note or "").strip()[:1000] or None, at=now_iso(), allowed_points=allowed)
    touch(proc)
    return entry


def next_criterion(proc: dict, cid: str) -> str | None:
    ids = [c["id"] for c in proc["doc"]["criteria"]]
    i = ids.index(cid)
    for nxt in ids[i + 1:] + ids[:i]:
        if criterion(proc, nxt).get("final_points") is None:
            return nxt
    return None


# ---------------------------------------------------------------- krok 6: wynik i PDF
def evaluated(proc: dict) -> dict:
    """Pełne przeliczenie silnikiem: sugestie, średnia, ogólny poziom, wynik, walidacja, strażnik."""
    return engine.evaluate(proc["doc"], config=CONFIG, model=MODEL, now=now_iso())


def save_summary(proc: dict, user: dict, form: dict) -> None:
    doc = proc["doc"]
    doc["interview_date"] = _date(form.get("interview_date"), "Data rozmowy oceniającej", required=False)
    doc["justification"] = (form.get("justification") or "").strip() or None
    doc["development_conclusions"] = (form.get("development_conclusions") or "").strip() or None
    if doc["form"] == "first_eval":
        head = doc.setdefault("unit_head", {"full_name": ""})
        head["participated_in_interview"] = form.get("unit_head_participated") == "1"
        head["agreement_confirmed"] = form.get("unit_head_agreement") == "1"
        head["signed_on"] = doc["interview_date"] if head["agreement_confirmed"] else None
        if evaluated(proc).get("result") == "negatywna":
            doc["development_conclusions"] = None  # przypis 8: tylko przy pozytywnej pierwszej ocenie
    else:
        to = _date(form.get("period_to"), "Data sporządzenia oceny", required=False)
        doc.setdefault("period", {})["to"] = to
        if to and doc["period"].get("from") and to < doc["period"]["from"]:
            raise WorkflowError("Data sporządzenia oceny nie może być wcześniejsza niż data ustalenia kryteriów (okres oceny).")
        if doc["employee"].get("corps_status") == "urzednik_sc":
            doc["part3_requested"] = form.get("part3_requested") == "1"
    _trail(proc, user, "summary_saved")
    touch(proc)


def pdf_bytes(proc: dict, user: dict) -> bytes:
    ev = evaluated(proc)
    missing = [c["name"] for c in ev["criteria"] if c.get("final_points") is None]
    if missing:
        raise WorkflowError("Brakuje decyzji przełożonego dla kryteriów: " + ", ".join(missing) + ".")
    errors = ev["validation"]["errors"]
    if errors:
        raise WorkflowError(" ".join(e["message"] for e in errors))
    if ev.get("result") is None:
        raise WorkflowError("Wynik nie jest jeszcze policzony – uzupełnij egzamin i sprawozdanie (§ 10 ust. 1 rozp. 2015)."
                            if ev["form"] == "first_eval" else "Wynik nie jest jeszcze policzony.")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "arkusz.pdf"
        try:
            render_pdf.render(ev, out)
        except render_pdf.InputError as exc:
            raise WorkflowError(str(exc)) from None
        data = out.read_bytes()
    first_pdf = not proc.get("pdf_generated_at")
    proc["pdf_generated_at"] = now_iso()
    if proc["status"] in ("nie_rozpoczeta", "kryteria_ustalone", "w_trakcie"):
        proc["status"] = "do_podpisu"
    if first_pdf:
        _trail(proc, user, "pdf_generated", note=f"{FORM_LABELS[ev['form']]}; wynik: {ev.get('result')}")
    touch(proc)
    return data


# ---------------------------------------------------------------- terminy i przypomnienia (deadlines.py)
def deadline_input(proc: dict, evaluator_name: str) -> dict:
    """Proces w formacie wejścia deadlines.evaluate(): daty z dokumentu oceny i z danych ocenianego."""
    doc = proc.get("doc") or {}
    emp = proc["employee"]
    if proc["kind"] == "first":
        intro = doc.get("first_eval_intro") or {}
        rd = intro.get("report_deadline") or {}
        dates = {"employment_start": emp.get("employment_start") or (doc.get("employee") or {}).get("employment_start"),
                 "contract_end": emp.get("contract_end"),
                 "intro_interview_date": intro.get("intro_interview_date"),
                 "report_deadline": rd if rd.get("from") and rd.get("to") else None,
                 "report_submitted_date": rd.get("to") if doc.get("report_submitted_on_time") else None,
                 "evaluation_written_date": doc.get("interview_date") if proc.get("pdf_generated_at") else None}
    else:
        part1 = doc.get("part1") or {}
        dates = {"previous_evaluation_date": emp.get("previous_evaluation_date"), "previous_result": "pozytywna",
                 "criteria_meeting_date": part1.get("criteria_meeting_date"),
                 "evaluation_deadline": part1.get("evaluation_deadline"),
                 "evaluation_written_date": (doc.get("period") or {}).get("to") if proc.get("pdf_generated_at") else None}
    return {"process_id": proc["id"], "type": proc["kind"], "status": proc["status"],
            "employee": {"full_name": emp["full_name"]},
            "evaluator": {"full_name": evaluator_name, "email": f"{proc['owner']}@example.invalid"},
            "dates": {k: v for k, v in dates.items() if v}}


def calendar_view(proc: dict, evaluator_name: str) -> dict:
    """Kalendarz czynności z podstawą prawną, flagami i najbliższą otwartą czynnością."""
    try:
        cal = deadlines.evaluate(deadline_input(proc, evaluator_name), date.fromisoformat(today_iso()))
    except ValueError:  # np. pierwsza ocena bez daty nawiązania stosunku pracy
        return {"events": [], "flags": [], "next": None}
    open_events = [e for e in cal["events"] if not e.get("done_on") and e["task"] != "sprzeciw"]
    cal["next"] = min(open_events, key=lambda e: e["days_left"] if e["days_left"] is not None else 10 ** 6, default=None)
    return cal


def send_reminder(proc: dict, hr_user: dict, evaluator_name: str) -> list[dict]:
    """Przypomnienie HR → przełożony (wysyłka e-mail zamockowana): o czynnościach z flagą, a bez flag – o najbliższej."""
    p = deadline_input(proc, evaluator_name)
    sender = actor_label(hr_user)
    entries = deadlines.build_reminders([p], date.fromisoformat(today_iso()), sender=sender, now=now_iso())
    if not entries:
        nxt = calendar_view(proc, evaluator_name).get("next")
        if not nxt:
            raise WorkflowError("Ta ocena nie ma otwartych czynności z terminem, więc przypomnienie nie jest potrzebne.")
        due = nxt["due"] or f"{nxt['window']['from']} – {nxt['window']['to']}"
        entries = [{"ts": now_iso(), "sender": sender, "recipient": evaluator_name, "process_id": proc["id"],
                    "task": nxt["task"], "due": due, "flag": None, "channel": "mock-email", "delivered": False,
                    "subject": f"Przypomnienie: {nxt['label']} – {proc['employee']['full_name']}",
                    "body": f"Najbliższa czynność: {nxt['label']}, termin {due} ({nxt['basis']})."}]
    proc.setdefault("reminders", []).extend(entries)
    proc["reminders"] = proc["reminders"][-20:]
    return entries


# ---------------------------------------------------------------- widok HR (biała lista pól, rbac.json)
def hr_record(proc: dict, evaluator_name: str) -> dict:
    doc = proc.get("doc") or {}
    part1 = doc.get("part1") or {}
    intro = doc.get("first_eval_intro") or {}
    cal = calendar_view(proc, evaluator_name)
    if proc["kind"] == "first":
        dates = {"employment_start": proc["employee"].get("employment_start"),
                 "intro_interview_date": intro.get("intro_interview_date"),
                 "report_deadline": (intro.get("report_deadline") or {}).get("to"),
                 "evaluation_deadline": (intro.get("evaluation_window") or {}).get("to")}
    else:
        dates = {"criteria_meeting_date": part1.get("criteria_meeting_date"),
                 "evaluation_deadline": part1.get("evaluation_deadline"),
                 "previous_evaluation_date": proc["employee"].get("previous_evaluation_date")}
    return {
        "process_id": proc["id"],
        "type": proc["kind"],
        "form": doc.get("form"),
        "status": proc["status"],
        "status_label": deadlines.STATUS_LABELS[proc["kind"]].get(proc["status"], proc["status"]),
        "employee": {"full_name": proc["employee"]["full_name"], "unit": proc["employee"].get("unit"),
                     "position": proc["employee"].get("position")},
        "evaluator": {"full_name": evaluator_name},
        "unit_head": {"full_name": (doc.get("unit_head") or {}).get("full_name")},
        "dates": dates,
        "events": cal.get("events", []),
        "flags": cal.get("flags", []),
        "reminders": proc.get("reminders") or [],
        "result": (engine.evaluate(doc, config=CONFIG, model=MODEL).get("result") if doc and doc.get("criteria") else None),
        # pola spoza białej listy – rbac.view_for_role je usunie (test w tests/test_smoke.py):
        "doc": doc,
        "trail": proc.get("trail"),
    }
