"""Deterministyczny strażnik błędów oceniania i reguł (bez LLM).

Podstawa merytoryczna (strony = numeracja PDF, zgodna z numerem na stronie):
- POR_OKR_24: poradnik KPRM „Oceny okresowe w służbie cywilnej” (DSC KPRM, wrzesień 2016), s. 24 –
  informacje o pracy ocenianego gromadzić na bieżąco i pisemnie, by uniknąć ich „zniekształcenia”.
- POR_OKR_26: tamże, s. 26 – punkt wyjścia to ocena na poziomie oczekiwań (5 pkt); „Przyznawane oceny
  cząstkowe powinny wynikać z rzeczywistych zachowań pracownika, a nie ogólnego postrzegania pracownika”.
- POR_PIERW_27: poradnik KPRM „Pierwsza ocena w służbie cywilnej” (2016), s. 27 – przygotować listę
  konkretnych przykładów zachowań uzasadniających poszczególne oceny.
- MODEL_INSTR: Model_kompetencji.xlsx, arkusz „Model kompetencji”, wiersze 4–6 – ocena na konkretnych
  przykładach (S-D-R), „brak podstaw do oceny”.
Nazwy „efekt aureoli” i „tendencja centralna” pochodzą z literatury HR, nie z poradników KPRM [~].
"""
from __future__ import annotations

SRC_POR_OKR_24 = "Poradnik KPRM „Oceny okresowe w służbie cywilnej” (2016), s. 24"
SRC_POR_OKR_26 = "Poradnik KPRM „Oceny okresowe w służbie cywilnej” (2016), s. 26"
SRC_POR_PIERW_27 = "Poradnik KPRM „Pierwsza ocena w służbie cywilnej” (2016), s. 27"
SRC_MODEL = "Model_kompetencji.xlsx, arkusz „Model kompetencji”, wiersze 4–6 (instrukcja)"

LEVEL_LABELS = {1: "znacznie poniżej oczekiwań", 2: "poniżej oczekiwań", 3: "na poziomie oczekiwań",
                4: "powyżej oczekiwań", 5: "znacznie powyżej oczekiwań"}


def _msg(rule_id, severity, message, source, criterion_id=None, indicator_id=None):
    return {"rule_id": rule_id, "severity": severity, "criterion_id": criterion_id,
            "indicator_id": indicator_id, "message": message, "source": source}


def run_guard(doc: dict, big_override_points: int = 4) -> list[dict]:
    """Zwraca listę komunikatów (po polsku, z id reguły i źródłem). Nigdy nie zmienia dokumentu."""
    out: list[dict] = []
    form = doc.get("form")
    periodic = form in ("periodic_b", "periodic_c")
    all_levels: list[int] = []

    for c in doc.get("criteria", []):
        cid = c.get("id")
        name = c.get("name") or cid
        ratings = c.get("indicator_ratings") or []
        rated = [r for r in ratings if not r.get("no_basis") and r.get("level") is not None]
        levels = [r["level"] for r in rated]
        all_levels.extend(levels)
        has_any_sdr = any((r.get("sdr_note") or "").strip() for r in ratings)

        # G-EXTREME-NO-SDR: skrajny poziom wskaźnika bez przykładu
        for r in rated:
            if r["level"] in (1, 5) and not (r.get("sdr_note") or "").strip():
                out.append(_msg(
                    "G-EXTREME-NO-SDR", "hint",
                    f"{name}: wskaźnik {r.get('indicator_id')} ma skrajny poziom „{LEVEL_LABELS[r['level']]}” bez przykładu. "
                    "Dopisz krótko sytuację, działanie i rezultat (S-D-R) – ocena powinna wynikać z rzeczywistych zachowań, a nie z ogólnego wrażenia.",
                    f"{SRC_POR_OKR_26}; {SRC_POR_PIERW_27}; {SRC_MODEL}", cid, r.get("indicator_id")))

        fin = c.get("final_points")
        sug = (c.get("suggestion") or {}).get("points")

        # G-EXTREME-FINAL-NO-SDR: skrajna ocena cząstkowa (1 lub 9) bez żadnego przykładu w kryterium
        if periodic and fin in (1, 9) and not has_any_sdr:
            out.append(_msg(
                "G-EXTREME-FINAL-NO-SDR", "hint",
                f"{name}: ocena cząstkowa {fin} pkt jest skrajna, a w kryterium nie ma żadnego przykładu S-D-R. "
                "Zanotuj przynajmniej jedną konkretną sytuację z okresu oceny.",
                f"{SRC_POR_OKR_24}; {SRC_POR_OKR_26}", cid))

        # G-SIGNIFICANTLY-BELOW: skutek prawny oceny 1 pkt
        if periodic and fin == 1:
            out.append(_msg(
                "G-SIGNIFICANTLY-BELOW", "alert",
                f"{name}: „znacznie poniżej oczekiwań” (1 pkt). Jedna taka ocena cząstkowa oznacza ocenę okresową NEGATYWNĄ "
                "niezależnie od średniej, a uzasadnienie oceny staje się obowiązkowe. Upewnij się, że decyzja opiera się na udokumentowanych przykładach.",
                "§ 11 ust. 1 pkt 4 i ust. 3 rozp. 2016; przypisy 11–12 Arkusza B/C", cid))
        elif periodic and sug == 1 and fin is None:
            out.append(_msg(
                "G-SUGGESTION-SIGNIFICANTLY-BELOW", "warning",
                f"{name}: sugestia wskazuje „znacznie poniżej oczekiwań”. Jeśli ją przyjmiesz, ocena okresowa będzie negatywna i wymaga uzasadnienia.",
                "§ 11 ust. 1 pkt 4 i ust. 3 rozp. 2016", cid))

        # G-UNIFORM-LEVELS: identyczne poziomy na wszystkich (min. 3) wskaźnikach kryterium
        if len(levels) >= 3 and len(set(levels)) == 1:
            extra = " Przy poziomie „na poziomie oczekiwań” to może być tendencja centralna." if levels[0] == 3 else ""
            out.append(_msg(
                "G-UNIFORM-LEVELS", "hint",
                f"{name}: wszystkie {len(levels)} ocenione wskaźniki mają ten sam poziom „{LEVEL_LABELS[levels[0]]}”. "
                f"Sprawdź, czy każdy wynika z osobnych obserwacji, a nie z ogólnego wrażenia (ryzyko efektu aureoli).{extra}",
                f"{SRC_POR_OKR_26} [~ nazwy efektów: literatura HR]", cid))

        # G-ALL-NO-BASIS
        if ratings and all(r.get("no_basis") for r in ratings):
            out.append(_msg(
                "G-ALL-NO-BASIS", "info",
                f"{name}: przy wszystkich wskaźnikach zaznaczono „brak podstaw do oceny”, więc nie ma sugestii. "
                "Wybierz poziom samodzielnie i wskaż jego podstawę w uzasadnieniu lub notatce.",
                SRC_MODEL, cid))

        # G-BIG-OVERRIDE: duża różnica sugestia → decyzja
        if sug is not None and fin is not None and abs(fin - sug) >= big_override_points:
            out.append(_msg(
                "G-BIG-OVERRIDE", "warning",
                f"{name}: wybrana ocena {fin} pkt różni się od sugestii {sug} pkt o {abs(fin - sug)} pkt. Decyzja należy do Ciebie; "
                "rozważ krótką notatkę, co przesądziło (notatka jest opcjonalna i trafia do śladu decyzji).",
                "Pełna treść zadania pkt 3 (ostateczny poziom wybiera przełożony); próg różnicy – decyzja projektowa [~]", cid))

    # G-UNIFORM-ALL: wszystkie wskaźniki w całym dokumencie identyczne
    if len(all_levels) >= 6 and len(set(all_levels)) == 1:
        out.append(_msg(
            "G-UNIFORM-ALL", "hint",
            f"Wszystkie {len(all_levels)} ocenione wskaźniki w dokumencie mają poziom „{LEVEL_LABELS[all_levels[0]]}”. "
            "Jednolity profil bywa skutkiem ogólnego wrażenia (efekt aureoli) albo unikania skrajności (tendencja centralna).",
            f"{SRC_POR_OKR_26} [~ nazwy efektów: literatura HR]"))

    # Pierwsza ocena: skutki ocen 3 pkt
    if form == "first_eval":
        finals = [c.get("final_points") for c in doc.get("criteria", [])]
        threes = sum(1 for p in finals if p == 3)
        if threes >= 2:
            out.append(_msg(
                "G-FIRST-TWO-LOWEST", "alert",
                f"Pierwsza ocena: {threes} oceny cząstkowe po 3 pkt. Dopuszczalna jest najwyżej jedna – pierwsza ocena będzie NEGATYWNA "
                "i wymaga uzasadnienia.",
                "§ 10 ust. 1 pkt 3 i ust. 4 rozp. 2015; przypisy 6–7 Arkusza pierwszej oceny"))
        if doc.get("exam") == "nie":
            out.append(_msg(
                "G-FIRST-EXAM", "alert",
                "Oceniany nie zaliczył egzaminu ze służby przygotowawczej – pierwsza ocena będzie negatywna, chyba że zachodzi jeden z trzech wyjątków („nie dotyczy”).",
                "§ 10 ust. 1 pkt 1 i ust. 3 rozp. 2015; przypis 5 Arkusza pierwszej oceny"))
        if doc.get("report_submitted_on_time") is False:
            out.append(_msg(
                "G-FIRST-REPORT", "alert",
                "Sprawozdanie nie zostało złożone w wyznaczonym terminie – pierwsza ocena będzie negatywna. Sprawdź, czy nie należało wyznaczyć nowego terminu (§ 5 rozp. 2015: nieobecność, przedłużenie umowy).",
                "§ 10 ust. 1 pkt 2 i § 5 rozp. 2015"))
    return out
