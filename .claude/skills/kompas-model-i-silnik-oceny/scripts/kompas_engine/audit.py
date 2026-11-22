"""Ślad decyzji przełożonego (S-HUMAN-DECIDES).

`record_decision` wywołuje UI/API w imieniu człowieka, który kliknął poziom.
Silnik sam nigdy nie wybiera final_points – `evaluate()` tylko uzupełnia ślad,
gdy dokument przyszedł z decyzjami, które nie mają jeszcze wpisu.
"""
from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _criterion(doc: dict, criterion_id: str) -> dict:
    for c in doc.get("criteria", []):
        if c.get("id") == criterion_id:
            return c
    raise KeyError(f"Brak kryterium {criterion_id!r} w dokumencie")


def record_decision(doc: dict, criterion_id: str, final_points: int, actor: str, note: str | None = None,
                    at: str | None = None, allowed_points: list[int] | None = None) -> dict:
    """Zapisuje decyzję przełożonego i dopisuje wpis do audit_log. Zwraca wpis.

    Notatka jest opcjonalna i nigdy nie blokuje zapisu.
    """
    if allowed_points is not None and final_points not in allowed_points:
        raise ValueError(f"Ocena {final_points} spoza skali formularza {allowed_points}")
    crit = _criterion(doc, criterion_id)
    suggested = (crit.get("suggestion") or {}).get("points")
    crit["final_points"] = final_points
    if note:
        crit["override_note"] = note
    entry = {
        "at": at or now_iso(),
        "actor": actor,
        "action": "override_suggestion" if suggested is not None and suggested != final_points else "final_points_set",
        "criterion_id": criterion_id,
        "suggested": suggested,
        "final": final_points,
        "note": note,
    }
    doc.setdefault("audit_log", []).append(entry)
    return entry


def reconcile_overrides(doc: dict, actor: str, at: str | None = None) -> list[dict]:
    """Dopisuje brakujące wpisy dla różnic sugestia → decyzja (np. dokument z importu)."""
    added = []
    log = doc.setdefault("audit_log", [])
    for c in doc.get("criteria", []):
        sug = (c.get("suggestion") or {}).get("points")
        fin = c.get("final_points")
        if sug is None or fin is None or sug == fin:
            continue
        if any(e.get("criterion_id") == c.get("id") and e.get("final") == fin and e.get("suggested") == sug for e in log):
            continue
        entry = {"at": at or now_iso(), "actor": actor, "action": "override_suggestion", "criterion_id": c.get("id"),
                 "suggested": sug, "final": fin, "note": c.get("override_note")}
        log.append(entry)
        added.append(entry)
    return added
