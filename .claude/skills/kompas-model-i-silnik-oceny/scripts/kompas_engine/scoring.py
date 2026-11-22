"""Sugerowany poziom kryterium z ocen wskaźników ("Kompas poziomu").

Arytmetyka na ułamkach (fractions.Fraction), więc granice progów (2, 4, 6, 8)
są porównywane dokładnie, bez błędów zmiennoprzecinkowych.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Callable, Iterable


def indicator_points(level: int) -> int:
    """Poziom wskaźnika L (1–5) → punkty 2L−1 (1/3/5/7/9). Reguła S-INDICATOR-POINTS."""
    if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 5:
        raise ValueError(f"Poziom wskaźnika musi być liczbą 1–5, jest: {level!r}")
    return 2 * level - 1


def mean(points: list[int]) -> Fraction:
    return Fraction(sum(points), len(points))


def median(points: list[int]) -> Fraction:
    s = sorted(points)
    mid = len(s) // 2
    if len(s) % 2:
        return Fraction(s[mid])
    return Fraction(s[mid - 1] + s[mid], 2)


AGGREGATORS: dict[str, Callable[[list[int]], Fraction]] = {"mean": mean, "median": median}


def fmt_pl(value: Fraction | int | float, places: int = 2) -> str:
    """6,33 – przecinek dziesiętny, zaokrąglenie połówkowe w górę (do wyświetlania)."""
    if isinstance(value, Fraction):
        d = Decimal(value.numerator) / Decimal(value.denominator)
    else:
        d = Decimal(str(value))
    q = Decimal(1).scaleb(-places)
    return str(d.quantize(q, rounding=ROUND_HALF_UP)).replace(".", ",")


def to_float(value: Fraction, places: int = 2) -> float:
    d = Decimal(value.numerator) / Decimal(value.denominator)
    return float(d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def band_for_average(avg: Fraction, config: dict) -> dict | None:
    """Średnia → pasmo ogólnego poziomu wg § 11 ust. 1 pkt 2 rozp. 2016 (P-THRESHOLDS)."""
    for band in config["overall_level_thresholds"]["bands"]:
        lo, hi = Fraction(band["min"]), Fraction(band["max"])
        above_lo = avg >= lo if band["min_inclusive"] else avg > lo
        below_hi = avg <= hi if band["max_inclusive"] else avg < hi
        if above_lo and below_hi:
            return band
    return None


def _first_eval_label(points: int, config: dict) -> str:
    return config["scales"]["first_eval"]["labels"][str(points)]


def suggest_criterion(
    ratings: Iterable[dict],
    form: str,
    config: dict,
    total_indicators: int | None = None,
    method: str | None = None,
) -> dict:
    """Liczy sugestię dla jednego kryterium. NIE ustawia final_points.

    ratings: [{"indicator_id", "level": 1–5|None, "no_basis": bool, "sdr_note"}]
    form: periodic_b | periodic_c | first_eval
    total_indicators: liczba wskaźników kryterium w modelu (domyślnie len(ratings)).
    method: "mean" | "median" (domyślnie config["suggestion"]["method"]).
    """
    ratings = list(ratings)
    scfg = config["suggestion"]
    method = method or scfg["method"]
    if method not in AGGREGATORS:
        raise ValueError(f"Nieznana metoda sugestii: {method}")
    places = scfg.get("decimal_places", 2)
    warnings: list[str] = []

    rated_points: list[int] = []
    no_basis = unrated = 0
    for r in ratings:
        if r.get("no_basis"):
            no_basis += 1
            if r.get("level") is not None:
                warnings.append(
                    f"Wskaźnik {r.get('indicator_id')}: zaznaczono jednocześnie poziom i „brak podstaw do oceny” – poziom pominięto."
                )
            continue
        if r.get("level") is None:
            unrated += 1
            continue
        rated_points.append(indicator_points(r["level"]))

    total = total_indicators if total_indicators is not None else len(ratings)
    total = max(total, len(ratings))
    base = {
        "method": method,
        "rated_count": len(rated_points),
        "no_basis_count": no_basis,
        "unrated_count": unrated + max(0, total - len(ratings)),
        "total_count": total,
        "mapping_note": None,
    }

    if not rated_points:
        if total and no_basis == total:
            msg = "Wszystkie wskaźniki oznaczono „brak podstaw do oceny” – brak sugestii, poziom wybierz samodzielnie."
        else:
            msg = "Brak ocenionych wskaźników – brak sugestii, poziom wybierz samodzielnie."
        return {**base, "points": None, "level": None, "level_key": None, "level_label": None,
                "average": None, "average_display": None, "formula": msg, "warnings": warnings + [msg]}

    if total and Fraction(len(rated_points), total) < Fraction(str(scfg.get("min_rated_fraction_warning", 0.5))):
        warnings.append(
            f"Oceniono {len(rated_points)} z {total} wskaźników (mniej niż połowę) – sugestia ma słabą podstawę."
        )

    avg = AGGREGATORS[method](rated_points)
    band = band_for_average(avg, config)
    if band is None:  # nie powinno się zdarzyć dla punktów 1..9
        raise ValueError(f"Średnia {avg} poza skalą 1–9")
    avg_txt = fmt_pl(avg, places)
    if method == "mean":
        expr = f"({'+'.join(map(str, rated_points))})/{len(rated_points)} = {avg_txt}"
    else:
        expr = f"mediana({', '.join(map(str, sorted(rated_points)))}) = {avg_txt}"

    if form == "first_eval":
        mapping = config["first_eval_mapping"]["default"]
        pts = int(mapping[str(band["level"])])
        label = _first_eval_label(pts, config)
        note = (f"Mapowanie poziomu {band['level']} z 5 → {pts} pkt w skali pierwszej oceny 3/5/7 "
                f"({config['first_eval_mapping']['status']}).")
        formula = f"{expr} → {band['label']} (poziom {band['level']} z 5) → pierwsza ocena: {pts} pkt ({label}; mapowanie do potwierdzenia z MC)"
        base["mapping_note"] = note
    else:
        pts = int(band["points"])
        label = band["label"]
        formula = f"{expr} → {band['label']} → {pts} pkt"

    return {**base, "points": pts, "level": band["level"], "level_key": band["key"], "level_label": label,
            "average": to_float(avg, places), "average_display": avg_txt, "formula": formula, "warnings": warnings}
