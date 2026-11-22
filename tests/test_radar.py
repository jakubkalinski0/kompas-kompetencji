"""Geometria „Profilu ocen cząstkowych” (app/radar.py): dane z silnika bez zmyślania wartości."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.radar import C, R, radar_view  # noqa: E402

PERIODIC = [1, 3, 5, 7, 9]
FIRST = [3, 5, 7]
LABELS = {"1": "znacznie poniżej oczekiwań", "3": "poniżej oczekiwań", "5": "na poziomie oczekiwań",
          "7": "powyżej oczekiwań", "9": "znacznie powyżej oczekiwań"}


def crit(cid, final, sug, kind="mandatory", ratings=None):
    return {"id": cid, "name": cid.title(), "kind": kind, "final_points": final, "override_note": None,
            "suggestion": {"points": sug, "formula": f"wzór {cid}"}, "indicator_ratings": ratings or []}


def test_scale_rings_are_even_steps_and_top_reaches_radius():
    view = radar_view({"criteria": [crit("a", 9, 9), crit("b", 1, 1), crit("c", 5, 5)]}, PERIODIC, LABELS)
    radii = [g["r"] for g in view["rings"]]
    assert radii == sorted(radii) and abs(radii[-1] - R) < 0.01
    steps = {round(b - a, 2) for a, b in zip(radii, radii[1:])}
    assert len(steps) == 1                                     # równe kroki skali
    assert radii[0] > 0                                        # najniższa ocena nie ląduje w środku
    assert [g["mid"] for g in view["rings"]] == [False, False, True, False, False]   # „na poziomie oczekiwań”


def test_missing_decision_is_a_gap_not_zero():
    view = radar_view({"criteria": [crit("a", 7, 7), crit("b", None, 5), crit("c", 5, None), crit("d", 3, 3)]}, PERIODIC, LABELS)
    a = {x["id"]: x for x in view["axes"]}
    assert a["b"]["dx"] is None and a["c"]["sx"] is None       # brak punktu zamiast zera
    assert not view["dec_closed"] and "Z" not in view["dec_path"]
    assert view["dec_path"].count("M") == 2                     # odcinki d–a i c–d; brak b przerywa obrys
    assert view["decided"] == 3 and view["suggested"] == 3


def test_groups_only_when_both_kinds_and_first_select_prefers_deviation():
    plain = radar_view({"criteria": [crit("a", 7, 7), crit("b", 5, 5), crit("c", 5, 5)]}, PERIODIC, LABELS)
    assert not plain["grouped"] and all(x["group"] is None for x in plain["axes"])
    mixed = radar_view({"criteria": [crit("a", 7, 7), crit("b", 5, 7), crit("c", 7, 7, kind="additional")]}, PERIODIC, LABELS)
    assert mixed["grouped"] and mixed["first_select"] == 1     # pierwsze kryterium z decyzją inną niż sugestia
    assert mixed["axes"][1]["delta"] == -2


def test_first_eval_scale_and_many_axes():
    view = radar_view({"criteria": [crit(f"k{i}", 5, 5, kind="first_eval_element") for i in range(8)]}, FIRST, LABELS)
    assert [g["p"] for g in view["rings"]] == FIRST and len(view["axes"]) == 8
    assert view["axes"][0]["deg"] == 0 and view["axes"][2]["deg"] == 90
    assert view["axes"][0]["dx"] == C                           # pierwsza oś pionowo w górę


def test_histogram_counts_real_ratings_and_empty_state():
    ratings = [{"level": 4, "no_basis": False}, {"level": 4, "no_basis": False}, {"level": 2, "no_basis": True}]
    view = radar_view({"criteria": [crit("a", 7, 7, ratings=ratings)]}, PERIODIC, LABELS)
    assert view["axes"][0]["hist"] == [0, 0, 0, 2, 0]           # „brak podstaw” nie liczy się jako poziom
    assert radar_view({"criteria": []}, PERIODIC, LABELS)["empty"]
