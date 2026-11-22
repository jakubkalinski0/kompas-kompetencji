#!/usr/bin/env python3
"""Propozycja arkusza oceny okresowej (B/C) i kandydatów na kryteria dodatkowe z OSP.

Deterministycznie (bez LLM):
  * arkusz B, gdy OSP wskazuje podległych pracowników (praca polega na bezpośrednim
    kierowaniu pracownikami – § 3 ust. 3 rozporządzenia z 2016 r., przypis 1 arkusza B);
    arkusz C w pozostałych przypadkach (§ 3 ust. 4, przypis 1 arkusza C);
  * ostrzeżenie „kieruje lub koordynuje” / niejednoznaczna liczba podległych;
  * kandydaci na kryteria dodatkowe = „Kompetencje miękkie” z OSP spoza listy
    obowiązkowej arkusza (§ 4 ust. 2–3), limit wyboru 3 (§ 5 ust. 2).
Opcjonalnie (LLM tylko proponuje): prompt z assets/prompt_additional_criteria.md,
walidacja odpowiedzi (dosłowny cytat zadania, poprawne id kryteriów i wskaźników).
Decyzję o arkuszu i o kryteriach dodatkowych zawsze podejmuje przełożony.

CLI:
  python propose_form.py <osp.docx|osp.json> [--model competency_model.json]
         [--prompt-out prompt.json] [--llm-output odpowiedz.json | --ollama MODEL] [--out wynik.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from osp_parser import COMPETENCIES, _norm, parse_osp_docx  # noqa: E402

PROMPT_TEMPLATE = HERE.parent / "assets" / "prompt_additional_criteria.md"
ROZP = "rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. (Dz. U. poz. 470)"
MAX_ADDITIONAL = 3  # § 5 ust. 2

FORMS = {
    "periodic_b": {
        "letter": "B",
        "mandatory": [
            "zarzadzanie_ludzmi", "podejmowanie_decyzji_i_odpowiedzialnosc",
            "organizacja_pracy_i_orientacja_na_osiaganie_celow", "wspolpraca", "komunikacja",
        ],
        "legal_basis": [
            {"citation": f"§ 3 ust. 3 {ROZP}",
             "quote": "Arkusz B, którego wzór jest określony w załączniku nr 3 do rozporządzenia, służy do "
                      "sporządzenia oceny zatrudnionego na stanowisku, na którym praca polega na bezpośrednim "
                      "kierowaniu pracownikami, innym niż stanowisko wymienione w ust. 2."},
            {"citation": "przypis 1 arkusza B (załącznik nr 3 do rozporządzenia; MAT: Arkusz oceny B (2).docx)",
             "quote": "Arkusz służy do sporządzenia oceny okresowej urzędnika służby cywilnej lub pracownika "
                      "służby cywilnej, zatrudnionego na stanowisku, na którym praca polega na bezpośrednim "
                      "kierowaniu pracownikami."},
            {"citation": f"§ 4 ust. 2 {ROZP}",
             "quote": "Ocenianego zatrudnionego na stanowisku, o którym mowa w § 3 ust. 3, ocenia się, stosując "
                      "następujące kryteria obowiązkowe: 1) zarządzanie ludźmi; 2) podejmowanie decyzji i "
                      "odpowiedzialność; 3) organizacja pracy i orientacja na osiąganie celów; 4) współpraca; "
                      "5) komunikacja."},
        ],
    },
    "periodic_c": {
        "letter": "C",
        "mandatory": [
            "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe", "rzetelnosc",
            "organizacja_pracy_i_orientacja_na_osiaganie_celow", "wspolpraca", "komunikacja",
        ],
        "legal_basis": [
            {"citation": f"§ 3 ust. 4 {ROZP}",
             "quote": "Arkusz C, którego wzór jest określony w załączniku nr 4 do rozporządzenia, służy do "
                      "sporządzenia oceny zatrudnionego na innym stanowisku pracy niż stanowiska wymienione "
                      "w ust. 2 i 3."},
            {"citation": "przypis 1 arkusza C (załącznik nr 4 do rozporządzenia; MAT: Arkusz oceny C (2).docx)",
             "quote": "Arkusz służy do sporządzenia oceny okresowej urzędnika służby cywilnej lub pracownika "
                      "służby cywilnej, zatrudnionego na stanowisku, które nie jest: – stanowiskiem kierownika "
                      "urzędu, będącym stanowiskiem pracy w służbie cywilnej, ani – stanowiskiem, na którym "
                      "praca polega na bezpośrednim kierowaniu pracownikami."},
            {"citation": f"§ 4 ust. 3 {ROZP}",
             "quote": "Ocenianego zatrudnionego na stanowisku, o którym mowa w § 3 ust. 4, ocenia się, stosując "
                      "następujące kryteria obowiązkowe: 1) wykorzystywanie wiedzy i doskonalenie zawodowe; "
                      "2) rzetelność; 3) organizacja pracy i orientacja na osiąganie celów; 4) współpraca; "
                      "5) komunikacja."},
        ],
    },
}
ADDITIONAL_BASIS = [
    {"citation": f"§ 2 ust. 2 {ROZP}",
     "quote": "Kryteria oceny dzielą się na kryteria obowiązkowe i kryteria dodatkowe, które oceniający może "
              "wybrać, jeżeli jest to uzasadnione ze względu na charakter obowiązków wynikających z opisu "
              "stanowiska pracy zajmowanego przez ocenianego."},
    {"citation": f"§ 5 ust. 2 {ROZP}",
     "quote": "Oceniający może wybrać z wykazu kryteriów oceny nie więcej niż 3 kryteria dodatkowe, "
              "najistotniejsze ze względu na charakter obowiązków wynikających z opisu stanowiska pracy "
              "zajmowanego przez ocenianego."},
]
ARKUSZ_A_NOTE = ("Arkusz A (kierownik urzędu będący stanowiskiem pracy w służbie cywilnej, § 3 ust. 2) jest poza "
                 "zakresem – Partner nie dostarczył jego wzoru.")
COORD_WARNING = ("Koordynowanie nie musi oznaczać bezpośredniego kierowania – potwierdź, czy praca na stanowisku "
                 "polega na bezpośrednim kierowaniu pracownikami (§ 3 ust. 3 rozporządzenia z 2016 r.).")
CONFIRM_NOTE = "Propozycja pomocnicza. Arkusz wybiera i zatwierdza przełożony (oceniający)."

MANAGE_CODES = {"up_to_4", "5_to_9", "above_9", "manages_managers"}
MANAGE_RE = re.compile(
    r"\b(kieruj\w*|kierowani\w* (?:zespo\w*|pracownik\w*|wydzia\w*|komórk\w*)|zarządza\w* (?:zespo\w*|pracownik\w*|"
    r"wydzia\w*|komórk\w*|ludźmi)|zarządzanie zespołem|deleguj\w*|delegowani\w*|ocenia pracownik\w*|"
    r"nadzoruje pracę (?:zespołu|pracowników|podległych)\w*)", re.IGNORECASE)
COORD_RE = re.compile(r"\bkoordyn\w*", re.IGNORECASE)
INJECTION_RE = re.compile(
    r"(zignoruj|ignore|pomiń)\s+(wszystkie\s+|all\s+)?(poprzednie|previous|powyższe|wcześniejsze)|"
    r"system\s*prompt|jesteś teraz|you are now|</?\s*osp_data|nowe polecenie|new instructions",
    re.IGNORECASE)


def _all_tasks(osp: dict) -> list[dict]:
    t = osp["part2"]["tasks"]
    out = []
    for kind in ("dominant", "other", "unclassified"):
        for task in t.get(kind, []):
            out.append({**task, "kind": kind})
    return out


def _evidence(osp: dict, regex: re.Pattern) -> list[dict]:
    ev = []
    sources = [("cel", None, osp["part2"].get("purpose") or "")]
    sources += [("zadanie", t["no"], t["text"]) for t in _all_tasks(osp)]
    for kind, no, text in sources:
        for sent in re.split(r"(?<=[.;])\s+", text.replace("\n", " ")):
            if regex.search(sent):
                ev.append({"source": kind, "task_no": no, "quote": sent.strip()[:240]})
                break
    return ev


def propose_form(osp: dict) -> dict:
    """Deterministyczna propozycja arkusza (periodic_b / periodic_c) z uzasadnieniem i podstawą."""
    sub = osp["part2"]["subordinates"]
    codes = sub.get("selected_codes", [])
    status = sub.get("status")
    labels = [o["label"] for o in sub.get("options", []) if o.get("checked")]
    manage_ev = _evidence(osp, MANAGE_RE)
    coord_ev = _evidence(osp, COORD_RE)
    warnings: list[str] = []

    if status == "ok" and codes == ["none"]:
        form, conf, rule = "periodic_c", "high", "R1_brak_podleglych"
        reason = ("W OSP zaznaczono „brak podległych pracowników” – praca nie polega na bezpośrednim kierowaniu "
                  "pracownikami, więc arkusz C (§ 3 ust. 4).")
        if manage_ev:
            conf = "medium"
            warnings.append("OSP: brak podległych, ale cel lub zadania mówią o kierowaniu ludźmi – sprawdź, "
                            "czy OSP jest aktualny.")
    elif codes and set(codes) <= MANAGE_CODES:
        form, rule = "periodic_b", "R2_podlegli_pracownicy"
        conf = "high" if status == "ok" else "medium"
        reason = (f"W OSP zaznaczono „{'; '.join(labels)}” – stanowisko z podległymi pracownikami; arkusz B "
                  "służy do oceny na stanowisku, na którym praca polega na bezpośrednim kierowaniu "
                  "pracownikami (§ 3 ust. 3).")
        if status != "ok":
            warnings.append("Zaznaczono więcej niż jeden przedział liczby podległych pracowników.")
        if sub.get("wording_manages_or_coordinates") or (coord_ev and not manage_ev):
            warnings.append(COORD_WARNING)
            if not manage_ev:
                conf = "medium"
    else:
        form = "periodic_b" if manage_ev else "periodic_c"
        conf, rule = "low", "R3_tresc_zadan"
        reason = ("Nie da się jednoznacznie odczytać liczby podległych pracowników z OSP – propozycja na podstawie "
                  "treści celu i zadań (" + ("są sformułowania o kierowaniu ludźmi" if manage_ev
                                              else "brak sformułowań o kierowaniu ludźmi") + ").")
        warnings.append(f"Liczba podległych pracowników niejednoznaczna (status: {status}). {COORD_WARNING}")

    title_n = _norm(osp.get("source", {}).get("template_title") or "")
    if "wyzszym stanowiskiem" in title_n and "niebedacego" not in title_n:
        warnings.append("OSP wyższego stanowiska w służbie cywilnej – sprawdź, czy to nie stanowisko kierownika "
                        "urzędu (arkusz A, poza zakresem).")
    return {
        "proposed_form": form,
        "form_letter": FORMS[form]["letter"],
        "confidence": conf,
        "rule_id": rule,
        "reason": reason,
        "evidence": {
            "subordinates_selected": labels,
            "managing_quotes": manage_ev[:3],
            "coordinating_quotes": coord_ev[:3],
        },
        "legal_basis": FORMS[form]["legal_basis"],
        "mandatory_criteria": [{"id": c, "name": COMPETENCIES[c]} for c in FORMS[form]["mandatory"]],
        "warnings": warnings,
        "requires_confirmation": True,
        "note": CONFIRM_NOTE,
        "out_of_scope": ARKUSZ_A_NOTE,
    }


def additional_candidates(osp: dict, form: str) -> dict:
    """Kandydaci na kryteria dodatkowe z „Kompetencji miękkich” OSP spoza listy obowiązkowej arkusza."""
    mandatory = FORMS[form]["mandatory"]
    soft = osp["part2"]["required_competencies"].get("soft_competencies") or {}
    items = list(soft.get("items", [])) + list((soft.get("additional") or {}).get("items", []))
    cands, overlap, seen = [], [], set()
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        if it["id"] in mandatory:
            overlap.append(it["id"])
            continue
        cands.append({
            "id": it["id"], "name": COMPETENCIES[it["id"]], "source": "osp_kompetencje_miekkie",
            "osp_text": it["text"], "match": it["match"],
            "reason": f"OSP wymienia „{it['text']}” w „Kompetencjach miękkich”; to kryterium nie jest "
                      f"obowiązkowe dla arkusza {FORMS[form]['letter']}.",
        })
    return {
        "form": form,
        "candidates": cands,
        "osp_soft_competencies_already_mandatory": overlap,
        "max_selectable": MAX_ADDITIONAL,
        "over_limit": len(cands) > MAX_ADDITIONAL,
        "legal_basis": ADDITIONAL_BASIS,
        "note": ("Kandydaci to propozycja. Kryteria dodatkowe wybiera oceniający – najwyżej 3, najistotniejsze ze "
                 "względu na obowiązki z OSP (§ 2 ust. 2, § 5 ust. 2); wpisuje je do części I arkusza po "
                 "rozmowie (§ 5 ust. 3). Brak kryteriów dodatkowych jest dopuszczalny."),
    }


def validate_selection(form: str, selected_ids: list[str]) -> list[str]:
    """Błędy wyboru kryteriów dodatkowych przez przełożonego (pusta lista = OK)."""
    errors = []
    if len(selected_ids) > MAX_ADDITIONAL:
        errors.append(f"Wybrano {len(selected_ids)} kryteriów dodatkowych – wolno najwyżej {MAX_ADDITIONAL} "
                      "(§ 5 ust. 2).")
    for cid in selected_ids:
        if cid not in COMPETENCIES:
            errors.append(f"Nieznane kryterium: {cid}")
        elif cid in FORMS[form]["mandatory"]:
            errors.append(f"„{COMPETENCIES[cid]}” jest kryterium obowiązkowym arkusza {FORMS[form]['letter']}.")
    if len(set(selected_ids)) != len(selected_ids):
        errors.append("Powtórzone kryterium.")
    return errors


# --------------------------------------------------------------------------- LLM (tylko propozycje)

def load_competency_model(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {c["id"]: {"name": c["name"], "indicators": [{"id": i["id"], "text": i["text"]} for i in c["indicators"]]}
            for c in data["competencies"]}


def detect_injection(osp: dict) -> list[str]:
    texts = [osp["part2"].get("purpose") or ""] + [t["text"] for t in _all_tasks(osp)]
    return [m.group(0) for t in texts for m in [INJECTION_RE.search(t)] if m]


def _safe_json(obj) -> str:
    """JSON, w którym treść OSP nie może zamknąć bloku <osp_data> (znaki < > jako \\u003c \\u003e)."""
    return json.dumps(obj, ensure_ascii=False, indent=1).replace("<", "\\u003c").replace(">", "\\u003e")


def build_llm_prompt(osp: dict, form: str, model: dict, template_path=PROMPT_TEMPLATE) -> dict:
    tpl = Path(template_path).read_text(encoding="utf-8")
    system = tpl.split("=== SYSTEM ===", 1)[1].split("=== USER ===", 1)[0].strip()
    user = tpl.split("=== USER ===", 1)[1].strip()
    mandatory = FORMS[form]["mandatory"]
    det = [c["id"] for c in additional_candidates(osp, form)["candidates"]]
    allowed = [cid for cid in COMPETENCIES if cid not in mandatory]
    indicators = {cid: [f"{i['id']}: {i['text']}" for i in model[cid]["indicators"]] for cid in COMPETENCIES if cid in model}
    osp_data = {
        "stanowisko": osp["part1"].get("position_name"),
        "cel_istnienia_stanowiska": osp["part2"].get("purpose"),
        "zadania": [{"nr": t["no"], "rodzaj": t["kind"], "tresc": t["text"]} for t in _all_tasks(osp)],
    }
    fill = {
        "{{FORM_LETTER}}": FORMS[form]["letter"],
        "{{MANDATORY}}": "\n".join(f"- {c}: {COMPETENCIES[c]}" for c in mandatory),
        "{{ALLOWED}}": "\n".join(f"- {c}: {COMPETENCIES[c]}" for c in allowed),
        "{{DETERMINISTIC}}": ", ".join(det) or "(brak)",
        "{{MAX_ADDITIONAL}}": str(MAX_ADDITIONAL),
        "{{INDICATORS}}": _safe_json(indicators),
        "{{OSP_DATA}}": _safe_json(osp_data),
    }
    for k, v in fill.items():
        system = system.replace(k, v)
        user = user.replace(k, v)
    return {"system": system, "user": user, "allowed": allowed, "mandatory": mandatory}


def _ws(s: str) -> str:
    s = (s or "").replace("„", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def validate_llm_output(raw, osp: dict, form: str, model: dict) -> dict:
    """Odrzuca propozycje bez dosłownego cytatu zadania, z nieznanym id albo kryterium obowiązkowym."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        return {"accepted": [], "indicators_to_discuss": [], "rejected": [{"item": None, "reason": f"Niepoprawny JSON: {exc}"}]}
    if not isinstance(data, dict):
        return {"accepted": [], "indicators_to_discuss": [], "rejected": [{"item": None, "reason": "Odpowiedź nie jest obiektem JSON"}]}
    tasks = {t["no"]: t["text"] for t in _all_tasks(osp) if t["no"] is not None}
    mandatory = set(FORMS[form]["mandatory"])
    accepted, rejected, inds = [], [], []

    def check_indicator(cid, iid):
        return cid in model and any(i["id"] == iid for i in model[cid]["indicators"])

    for c in data.get("candidates", []) or []:
        if not isinstance(c, dict):
            rejected.append({"item": c, "reason": "Pozycja nie jest obiektem"})
            continue
        cid, no, quote = c.get("criterion_id"), c.get("task_no"), c.get("task_quote") or ""
        if cid not in COMPETENCIES:
            reason = "Nieznane id kryterium"
        elif cid in mandatory:
            reason = "Kryterium obowiązkowe – nie może być dodatkowym"
        elif any(a["criterion_id"] == cid for a in accepted):
            reason = "Duplikat kryterium"
        elif no not in tasks:
            reason = "Brak zadania o tym numerze w OSP"
        elif len(_ws(quote)) < 15 or _ws(quote) not in _ws(tasks[no]):
            reason = "Cytat nie jest dosłownym fragmentem zadania z OSP"
        elif len(accepted) >= MAX_ADDITIONAL:
            reason = f"Przekroczono limit {MAX_ADDITIONAL} propozycji"
        else:
            reason = None
        if reason:
            rejected.append({"item": c, "reason": reason})
            continue
        ok_ids = [i for i in (c.get("indicator_ids") or []) if check_indicator(cid, i)]
        accepted.append({"criterion_id": cid, "name": COMPETENCIES[cid], "task_no": no, "task_quote": quote,
                         "rationale": str(c.get("rationale") or "")[:600], "indicator_ids": ok_ids,
                         "dropped_indicator_ids": [i for i in (c.get("indicator_ids") or []) if i not in ok_ids]})
    for it in data.get("indicators_to_discuss", []) or []:
        if not isinstance(it, dict):
            continue
        cid, iid = it.get("criterion_id"), it.get("indicator_id")
        if check_indicator(cid, iid) and (it.get("task_no") is None or it.get("task_no") in tasks):
            inds.append({"criterion_id": cid, "indicator_id": iid, "task_no": it.get("task_no"),
                         "why": str(it.get("why") or "")[:400]})
        else:
            rejected.append({"item": it, "reason": "Nieznany wskaźnik/kryterium albo numer zadania"})
    return {"accepted": accepted, "indicators_to_discuss": inds, "rejected": rejected,
            "injection_flag_from_model": bool(data.get("injection_suspected")),
            "note": "Propozycje LLM są pomocnicze; wybór kryteriów dodatkowych należy do przełożonego."}


def call_ollama(prompt: dict, model_name: str, url: str | None = None, timeout: int | None = None) -> str:
    url = (url or os.environ.get("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
    timeout = timeout or int(os.environ.get("OLLAMA_TIMEOUT", "600"))
    body = json.dumps({
        "model": model_name, "stream": False, "format": "json",
        "keep_alive": os.environ.get("OLLAMA_KEEP_ALIVE", "5m"),
        "options": {"temperature": 0, "seed": 7, "num_ctx": 8192},
        "messages": [{"role": "system", "content": prompt["system"]}, {"role": "user", "content": prompt["user"]}],
    }).encode("utf-8")
    req = urllib.request.Request(f"{url}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]["content"]


def analyze(osp: dict) -> dict:
    proposal = propose_form(osp)
    return {
        "osp": {"file": osp["source"]["file"], "position_name": osp["part1"].get("position_name"),
                "position_symbol": osp["part1"].get("position_symbol"), "parser_warnings": osp.get("warnings", [])},
        "form_proposal": proposal,
        "additional_criteria": additional_candidates(osp, proposal["proposed_form"]),
        "injection_suspects": detect_injection(osp),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Propozycja arkusza B/C i kandydatów na kryteria dodatkowe z OSP")
    ap.add_argument("osp", help="OSP .docx albo JSON z osp_parser.py")
    ap.add_argument("--form", choices=list(FORMS), help="arkusz potwierdzony przez przełożonego (domyślnie propozycja)")
    ap.add_argument("--model", help="competency_model.json (kontrakt C1) – potrzebny do promptu LLM")
    ap.add_argument("--prompt-out", help="zapisz prompt LLM (JSON: system, user)")
    ap.add_argument("--llm-output", help="plik z odpowiedzią LLM do walidacji")
    ap.add_argument("--ollama", metavar="MODEL", help="wywołaj lokalną Ollamę (OLLAMA_URL) i zwaliduj odpowiedź")
    ap.add_argument("--out", help="plik wynikowy JSON (domyślnie stdout)")
    a = ap.parse_args(argv)
    p = Path(a.osp)
    osp = json.loads(p.read_text(encoding="utf-8")) if p.suffix.lower() == ".json" else parse_osp_docx(p)
    result = analyze(osp)
    form = a.form or result["form_proposal"]["proposed_form"]
    if a.form:
        result["additional_criteria"] = additional_candidates(osp, form)
        result["form_confirmed_by_user"] = form
    if a.model and (a.prompt_out or a.llm_output or a.ollama):
        model = load_competency_model(a.model)
        prompt = build_llm_prompt(osp, form, model)
        if a.prompt_out:
            Path(a.prompt_out).write_text(json.dumps(prompt, ensure_ascii=False, indent=2), encoding="utf-8")
        raw = None
        if a.llm_output:
            raw = Path(a.llm_output).read_text(encoding="utf-8")
        elif a.ollama:
            raw = call_ollama(prompt, a.ollama)
            result["llm_raw"] = raw
        if raw is not None:
            result["llm_proposals"] = validate_llm_output(raw, osp, form, model)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
