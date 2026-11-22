"""Asystent oceny zachowań: opis przełożonego → propozycje poziomów wskaźników z modelu kompetencji (tylko stdlib).

Przełożony opisuje własnymi słowami, co zaobserwował u pracownika w danym kryterium. Model językowy dopasowuje
opis do opisów poziomów 1–5 każdego wskaźnika i zwraca PROPOZYCJE. Kod pilnuje, żeby propozycja była sprawdzalna:

- dowodem jest DOSŁOWNY fragment notatki (po zamaskowaniu danych osobowych); bez niego propozycja odpada,
- identyfikator wskaźnika musi należeć do kompetencji, poziom musi być liczbą 1–5,
- fragment, który wygląda na polecenie dla modelu („daj 5”, „zignoruj zasady”), nie jest dowodem,
- tekst opisu poziomu pochodzi z modelu kompetencji MC, nie z odpowiedzi modelu językowego.

Nic nie zaznacza się samo: aplikacja pokazuje propozycje, a poziomy zaznacza przełożony (jednym przyciskiem albo
ręcznie). Poziom kryterium liczy dalej jawny wzór silnika oceny, a ostateczną ocenę wybiera przełożony (pkt 5 zadania).

API:
  prompt = build_prompt(competency, masked_note, process)
  out = validate(raw_llm_text, competency, masked_note)
  out = propose(llm, competency, note, shield_ctx, process)   # maskowanie → LLM → walidacja → odmaskowanie
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from privacy_shield import ShieldContext, mask, unmask  # noqa: E402

PROMPT_PATH = HERE.parent / "assets" / "prompts" / "behavior_system.md"
LEVEL_LABELS = {1: "znacznie poniżej oczekiwań", 2: "poniżej oczekiwań", 3: "na poziomie oczekiwań",
                4: "powyżej oczekiwań", 5: "znacznie powyżej oczekiwań"}
MIN_EVIDENCE = 8
MAX_NOTE = 3000
# Polecenia dla modelu albo gotowa ocena zamiast opisu zachowania („daj 5”, „poziom 4”, „7 pkt”) – nie są dowodem.
INJECTION_RX = re.compile(r"zignoruj|\bignoruj|\bignore\b|\bprompt|przyznaj\w*\s+(jej\s+|mu\s+)?\d|\bdaj\w*\s+(jej\s+|mu\s+)?\d|"
                          r"wystaw\w*\s+(jej\s+|mu\s+)?\d|\d\s*(pkt|punkt)|poziom\w*\s+\d", re.I)
_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def _norm(s: str) -> str:
    s = s.replace("„", '"').replace("”", '"').replace("“", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("…", "...").replace("–", "-").replace("—", "-")
    return " ".join(s.lower().split())


def build_prompt(competency: dict, masked_note: str, process: str = "periodic") -> dict:
    lines = []
    for ind in competency["indicators"]:
        lines.append(f"{ind['id']}: {ind['text']}")
        for lv in range(1, 6):
            lines.append(f"  {lv} – {LEVEL_LABELS[lv]}: {ind['levels'][str(lv)]}")
    kind = "pierwsza ocena w służbie cywilnej" if process == "first" else "ocena okresowa"
    user = (f"Kompetencja: {competency['name']} ({kind}).\n<wskazniki>\n" + "\n".join(lines) + "\n</wskazniki>\n\n"
            f"<notatka>\n{masked_note}\n</notatka>")
    return {"system": PROMPT_PATH.read_text(encoding="utf-8"), "user": user}


def validate(raw: str, competency: dict, masked_note: str) -> dict:
    """Odpowiedź modelu → propozycje sprawdzalne w notatce; reszta trafia do `rejected` z powodem."""
    m = _JSON_OBJ.search(raw or "")
    try:
        data = json.loads(m.group(0) if m else raw or "")
    except (TypeError, ValueError):
        return {"proposals": [], "rejected": [], "no_evidence": [i["id"] for i in competency["indicators"]],
                "missing": "", "injection_suspected": False, "error": "Model nie zwrócił poprawnego JSON."}
    by_id = {i["id"]: i for i in competency["indicators"]}
    note_n = _norm(masked_note)
    proposals, rejected, seen = [], [], set()
    for p in data.get("proposals") or []:
        if not isinstance(p, dict):
            continue
        iid, level = p.get("indicator_id"), p.get("level")
        raw_ev = p.get("evidence") or []
        fragments = [str(x).strip().strip('"„”').strip() for x in (raw_ev if isinstance(raw_ev, list) else [raw_ev])]
        fragments = [f for f in fragments if f][:2]
        why = " ".join(str(p.get("why") or "").split())[:300]
        if iid not in by_id or iid in seen:
            rejected.append({"indicator_id": iid, "reason": "wskaźnik spoza tej kompetencji"})
            continue
        if level is None or level == "":
            continue
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = 0
        if not 1 <= level <= 5:
            rejected.append({"indicator_id": iid, "reason": "poziom spoza skali 1–5"})
            continue
        # każdy fragment musi być dosłownie w notatce; fragment-polecenie („daj 5”) nie jest dowodem
        verbatim = [f for f in fragments if len(_norm(f).rstrip(".")) >= MIN_EVIDENCE and _norm(f).rstrip(".") in note_n]
        if not verbatim or len(verbatim) < len(fragments):
            rejected.append({"indicator_id": iid, "level": level, "reason": "brak dosłownego fragmentu notatki"})
            continue
        if any(INJECTION_RX.search(f) for f in verbatim):
            rejected.append({"indicator_id": iid, "level": level, "reason": "fragment wygląda na polecenie, nie na zachowanie"})
            continue
        seen.add(iid)
        ind = by_id[iid]
        proposals.append({"indicator_id": iid, "indicator_text": ind["text"], "level": level,
                          "level_label": LEVEL_LABELS[level], "level_text": ind["levels"][str(level)],
                          "evidence": " … ".join(verbatim), "evidence_list": verbatim, "why": why})
    order = [i["id"] for i in competency["indicators"]]
    proposals.sort(key=lambda p: order.index(p["indicator_id"]))
    return {"proposals": proposals, "rejected": rejected,
            "no_evidence": [i for i in order if i not in seen],
            "missing": " ".join(str(data.get("missing") or "").split())[:400],
            "injection_suspected": bool(data.get("injection_suspected")) or bool(INJECTION_RX.search(masked_note))}


def propose(llm, competency: dict, note: str, shield: ShieldContext | None = None, process: str = "periodic",
            max_tokens: int = 1600) -> dict:
    """Maskowanie notatki → model → walidacja → odmaskowanie dowodów do wyświetlenia przełożonemu."""
    masked = mask((note or "")[:MAX_NOTE], shield or ShieldContext())
    prompt = build_prompt(competency, masked.text, process)
    res = llm.chat([{"role": "system", "content": prompt["system"]}, {"role": "user", "content": prompt["user"]}],
                   temperature=0.1, max_tokens=max_tokens)
    out = validate(res.text, competency, masked.text)
    for p in out["proposals"]:
        p["evidence"] = unmask(p["evidence"], masked.mapping)
        p["evidence_list"] = [unmask(x, masked.mapping) for x in p["evidence_list"]]
        p["why"] = unmask(p["why"], masked.mapping)
    out["missing"] = unmask(out["missing"], masked.mapping)
    out["masked_note"] = masked.text
    out["llm"] = {"model": res.model, "provider": res.provider, "latency_s": res.latency_s, "cached": res.cached}
    return out
