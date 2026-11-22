"""Geometria wykresu „Profil ocen cząstkowych” (ekran „Wynik oceny i arkusz”).

Tylko prezentacja: czyta wynik silnika (`workflow.evaluated`), niczego nie liczy od nowa i nie zmienia logiki oceny.
Każde kryterium (element oceny) ma swoją oś; promień to pozycja na skali punktowej arkusza:
okresowa 1/3/5/7/9, pierwsza ocena 3/5/7. Pierścienie są w równych krokach skali, a środek wykresu leży
o jeden krok poniżej najniższej oceny, więc najniższa ocena nie znika w środku.
Brak decyzji albo sugestii to przerwa w obrysie – nie zero.
"""
from __future__ import annotations

from math import cos, pi, sin

SIZE = 460          # viewBox SIZE × SIZE
C = SIZE / 2        # środek
R = 158             # promień najwyższej oceny
KIND_LABELS = {"mandatory": "kryterium obowiązkowe", "additional": "kryterium dodatkowe",
               "first_eval_element": "element pierwszej oceny"}


def _f(v: float) -> float:
    return round(v, 2)


def _polar(angle: float, radius: float) -> tuple[float, float]:
    return _f(C + cos(angle) * radius), _f(C + sin(angle) * radius)


def _outline(pts: list[tuple[float, float] | None]) -> str:
    """Zamknięty wielokąt, gdy są wszystkie punkty; inaczej odcinki tylko między sąsiednimi istniejącymi punktami."""
    if pts and all(pts) and len(pts) >= 3:
        return "M" + " L".join(f"{x},{y}" for x, y in pts) + " Z"
    segs = []
    n = len(pts)
    for i in range(n if n >= 3 else n - 1):
        a, b = pts[i], pts[(i + 1) % n]
        if a and b:
            segs.append(f"M{a[0]},{a[1]} L{b[0]},{b[1]}")
    return " ".join(segs)


def _sector(a0: float, a1: float, r0: float, r1: float) -> str:
    """Wycinek pierścienia od kąta a0 do a1 (radiany), promienie r0 < r1."""
    x0, y0 = _polar(a0, r1)
    x1, y1 = _polar(a1, r1)
    large = 1 if (a1 - a0) > pi else 0
    if r0 <= 0:
        return f"M{_f(C)},{_f(C)} L{x0},{y0} A{r1},{r1} 0 {large} 1 {x1},{y1} Z"
    x2, y2 = _polar(a1, r0)
    x3, y3 = _polar(a0, r0)
    return f"M{x0},{y0} A{r1},{r1} 0 {large} 1 {x1},{y1} L{x2},{y2} A{r0},{r0} 0 {large} 0 {x3},{y3} Z"


def radar_view(ev: dict, points: list[int], labels: dict[str, str]) -> dict:
    crits = ev.get("criteria") or []
    n = len(crits)
    if not n or not points:
        return {"empty": True, "axes": []}
    step = (points[1] - points[0]) if len(points) > 1 else 1
    lo, hi = points[0] - step, points[-1]

    def radius(p: int | None) -> float | None:
        return None if p is None else _f((p - lo) / (hi - lo) * R)

    alerts = {g["criterion_id"] for g in ev.get("guard") or [] if g.get("severity") == "alert" and g.get("criterion_id")}
    kinds = {c.get("kind") for c in crits}
    grouped = kinds == {"mandatory", "additional"}       # pierścień rodzajów tylko, gdy są obie grupy
    half = pi / n
    axes, dec_pts, sug_pts = [], [], []
    for i, c in enumerate(crits):
        ang = -pi / 2 + 2 * pi * i / n
        ux, uy = cos(ang), sin(ang)
        s = c.get("suggestion") or {}
        dec, sug = c.get("final_points"), s.get("points")
        rd, rs = radius(dec), radius(sug)
        dp = _polar(ang, rd) if rd is not None else None
        sp = _polar(ang, rs) if rs is not None else None
        dec_pts.append(dp)
        sug_pts.append(sp)
        lx, ly = _polar(ang, R + 34)
        ratings = c.get("indicator_ratings") or []
        hist = [sum(1 for r in ratings if not r.get("no_basis") and r.get("level") == lv) for lv in range(1, 6)]
        axes.append({
            "i": i, "no": f"{i + 1:02d}", "id": c["id"], "name": c.get("name") or c["id"], "kind": c.get("kind"),
            "kind_label": KIND_LABELS.get(c.get("kind"), ""),
            "deg": _f(i * 360 / n),                              # obrót od góry, zgodnie z ruchem wskazówek
            "x2": _polar(ang, R + 14)[0], "y2": _polar(ang, R + 14)[1],
            "lx": lx, "ly": ly,
            "dec": dec, "dec_label": labels.get(str(dec), "") if dec is not None else "",
            "sug": sug, "sug_label": labels.get(str(sug), "") if sug is not None else "",
            "dx": dp[0] if dp else None, "dy": dp[1] if dp else None,
            "sx": sp[0] if sp else None, "sy": sp[1] if sp else None,
            "tx": _f(C - dp[0]) if dp else 0, "ty": _f(C - dp[1]) if dp else 0,   # wejście punktu ze środka
            "differs": dec is not None and sug is not None and dec != sug,
            "delta": (dec - sug) if dec is not None and sug is not None else None,
            "alert": c["id"] in alerts,
            "hit": _sector(ang - half, ang + half, 0, R + 52),
            "group": _sector(ang - half + 0.012, ang + half - 0.012, R + 46, R + 52) if grouped else None,
            "formula": s.get("formula") or "", "average": s.get("average_display"),
            "level_label": s.get("level_label"), "mapping_note": s.get("mapping_note"),
            "warnings": s.get("warnings") or [],
            "rated": s.get("rated_count") or 0, "no_basis": s.get("no_basis_count") or 0,
            "total": s.get("total_count") or len(ratings),
            "hist": hist, "hist_max": max(hist + [1]),
            "notes": sum(1 for r in ratings if (r.get("sdr_note") or "").strip()),
            "override_note": c.get("override_note"),
        })
    ring_ang = -pi / 2 + half                                     # etykiety skali między pierwszą a drugą osią
    mid = next((p for p in points if "na poziomie" in labels.get(str(p), "")), None)
    rings = []
    for p in points:
        rr = radius(p)
        tx, ty = _polar(ring_ang, rr)
        rings.append({"p": p, "r": rr, "label": labels.get(str(p), ""), "tx": tx, "ty": ty, "mid": p == mid})
    decided = sum(1 for a in axes if a["dec"] is not None)
    return {
        "empty": False, "size": SIZE, "c": C, "R": R, "rings": rings, "axes": axes, "grouped": grouped,
        "dec_path": _outline(dec_pts), "sug_path": _outline(sug_pts),
        "dec_closed": all(dec_pts) and n >= 3, "decided": decided, "suggested": sum(1 for p in sug_pts if p),
        "scale": points, "first_select": next((a["i"] for a in axes if a["differs"] or a["alert"]), 0),
    }
