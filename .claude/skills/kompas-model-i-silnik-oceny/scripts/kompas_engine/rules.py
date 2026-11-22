"""Reguły wyniku oceny okresowej (rozp. 2016) i pierwszej oceny (rozp. 2015).

Funkcje przyjmują ostateczne oceny cząstkowe wybrane przez przełożonego
(final_points) i zwracają wynik wyliczony z przepisów. Nic tu nie wybiera
ocen cząstkowych za człowieka.
"""
from __future__ import annotations

from fractions import Fraction

from .scoring import band_for_average, fmt_pl, to_float

OBJECTION_NOTICE = (
    "Zgodnie z art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny okresowej "
    "służy, w terminie 7 dni od dnia zapoznania się z oceną, sprzeciw do dyrektora generalnego urzędu."
)
OBJECTION_FOOTNOTE_17 = (
    "W urzędzie, w którym przepisy nie przewidują tworzenia stanowiska dyrektora generalnego urzędu, "
    "sprzeciw składa się do kierownika tego urzędu."
)


def periodic_outcome(final_points: list[int | None], config: dict) -> dict:
    """§ 11 ust. 1 pkt 2–4 rozp. 2016 (reguły P-AVG, P-THRESHOLDS, P-POSITIVE, P-NEGATIVE)."""
    if not final_points or any(p is None for p in final_points):
        return {"complete": False, "average": None, "average_display": None, "overall_level": None,
                "result": None, "reasons": ["Brak ocen cząstkowych dla części kryteriów – wynik niepoliczony."],
                "formula": None}
    avg = Fraction(sum(final_points), len(final_points))
    band = band_for_average(avg, config)
    has_one = any(p == 1 for p in final_points)
    reasons = []
    if band["level"] <= 2:
        reasons.append(f"P-NEGATIVE: ogólny poziom „{band['label']}” (średnia {fmt_pl(avg)}).")
    if has_one:
        reasons.append("P-NEGATIVE: co najmniej jedna ocena cząstkowa „znacznie poniżej oczekiwań” (1 pkt) – ocena negatywna niezależnie od średniej.")
    result = "negatywna" if reasons else "pozytywna"
    if not reasons:
        reasons.append(f"P-POSITIVE: ogólny poziom „{band['label']}” i brak ocen cząstkowych 1 pkt.")
    formula = (f"({'+'.join(map(str, final_points))})/{len(final_points)} = {fmt_pl(avg)} → "
               f"{band['label']} ({band['range_label']})")
    return {
        "complete": True,
        "average": to_float(avg),
        "average_display": fmt_pl(avg),
        "overall_level": {"level": band["level"], "key": band["key"], "label": band["label"],
                          "range_label": band["range_label"]},
        "result": result,
        "reasons": reasons,
        "formula": formula,
    }


def first_eval_outcome(final_points: list[int | None], exam: str | None, report_on_time: bool | None,
                       config: dict) -> dict:
    """§ 7 pkt 3 i § 10 rozp. 2015; przypisy 4–6 arkusza (F-TOTAL, F-EXAM, F-REPORT, F-MAX-ONE-LOWEST, F-MIN-TOTAL)."""
    cond_cfg = config["forms"]["first_eval"]["positive_conditions"]
    lowest = cond_cfg["lowest_points"]
    points_complete = bool(final_points) and all(p is not None for p in final_points)
    avg = Fraction(sum(final_points), len(final_points)) if points_complete else None
    conditions = [
        {"id": "F-EXAM", "label": "zaliczył egzamin ze służby przygotowawczej, chyba że nie dotyczył go ten obowiązek",
         "met": None if exam is None else exam in ("tak", "nie_dotyczy")},
        {"id": "F-REPORT", "label": "złożył sprawozdanie w wyznaczonym terminie",
         "met": None if report_on_time is None else bool(report_on_time)},
        {"id": "F-MAX-ONE-LOWEST", "label": f"nie więcej niż jedna ocena cząstkowa {lowest} pkt",
         "met": None if not points_complete else sum(1 for p in final_points if p == lowest) <= cond_cfg["max_count_of_lowest_points"]},
        {"id": "F-MIN-TOTAL", "label": f"ocena łączna nie niższa niż {cond_cfg['min_total_average']} pkt",
         "met": None if avg is None else avg >= Fraction(cond_cfg["min_total_average"])},
    ]
    failed = [c for c in conditions if c["met"] is False]
    unknown = [c for c in conditions if c["met"] is None]
    if failed:
        result = "negatywna"  # wystarczy jeden niespełniony warunek (warunki łączne – § 10 ust. 2)
    elif unknown:
        result = None
    else:
        result = "pozytywna"
    reasons = [f"{c['id']}: niespełniony warunek – {c['label']}." for c in failed]
    if result == "pozytywna":
        reasons.append("Spełnione łącznie wszystkie 4 warunki § 10 ust. 1 rozp. 2015.")
    formula = None
    if avg is not None:
        formula = f"({'+'.join(map(str, final_points))})/{len(final_points)} = {fmt_pl(avg)} (ocena łączna; próg ≥ {cond_cfg['min_total_average']})"
    return {
        "complete": not unknown,
        "average": to_float(avg) if avg is not None else None,
        "average_display": fmt_pl(avg) if avg is not None else None,
        "overall_level": None,
        "result": result,
        "conditions": conditions,
        "reasons": reasons,
        "formula": formula,
    }


def part3_status(corps_status: str, part3_requested: bool, result: str | None) -> dict:
    """Część III (P-PART3, P-PART3-POSITIVE, P-PART3-FLAG): przypis 18 i 16, § 11 ust. 5 rozp. 2016, art. 89 ust. 1 ustawy."""
    if corps_status == "pracownik_sc":
        error = "P-PART3: Część III dotyczy wyłącznie urzędnika SC – dla pracownika SC nie drukuje się jej i nie dołącza (przypis 18)." if part3_requested else None
        return {"part3_attached": "nie_dotyczy", "include_part3": False, "error": error, "pending": False}
    if not part3_requested:
        return {"part3_attached": "nie", "include_part3": False, "error": None, "pending": False}
    if result == "negatywna":
        return {"part3_attached": "nie", "include_part3": False, "pending": False,
                "error": "P-PART3-POSITIVE: wniosek o kolejny stopień służbowy można sporządzić tylko przy ocenie pozytywnej (§ 11 ust. 5 rozp. 2016, art. 89 ust. 1 ustawy)."}
    return {"part3_attached": "tak", "include_part3": True, "error": None, "pending": result is None}
