"""Silnik terminów i statusów procesu oceny (panel HR) + zamockowane przypomnienia. Czysta stdlib.

Użycie:
    python deadlines.py calendar --input proces.json [--today 2026-11-21] [--warn-days 14]
    python deadlines.py remind   --input procesy.json --log przypomnienia.jsonl --sender "Zofia Kadrowa-Demo" [--today ...]
    python deadlines.py status   --input proces.json --to kryteria_ustalone

Podstawy prawne każdej daty: references/terminy.md (tabela z pewnością [✔]/[~]/[?]).
Liczenie terminów: dni – dzień zdarzenia się nie wlicza (art. 111 § 2 KC w zw. z art. 300 KP) [~];
miesiące – data odpowiadająca dniowi początkowemu, a gdy jej brak, ostatni dzień miesiąca (art. 112 KC) [~].
Przesunięcie końca terminu z soboty/dnia wolnego (art. 115 KC) stosujemy tylko do sprzeciwu i odwołania [~].
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

STATUSES = ["nie_rozpoczeta", "kryteria_ustalone", "w_trakcie", "do_podpisu", "zakonczona", "sprzeciw"]
STATUS_LABELS = {
    "periodic": {"nie_rozpoczeta": "Nierozpoczęta", "kryteria_ustalone": "Kryteria ustalone (Część I)",
                 "w_trakcie": "W trakcie okresu oceny", "do_podpisu": "Ocena sporządzona – do podpisu i zapoznania",
                 "zakonczona": "Zakończona", "sprzeciw": "Wniesiono sprzeciw"},
    "first": {"nie_rozpoczeta": "Nierozpoczęta", "kryteria_ustalone": "Rozmowa wstępna odbyta",
              "w_trakcie": "Okres pracy i sprawozdanie", "do_podpisu": "Ocena sporządzona – do podpisu kierującego komórką",
              "zakonczona": "Zakończona", "sprzeciw": "Nie dotyczy"},
}
TRANSITIONS = {
    "nie_rozpoczeta": {"kryteria_ustalone"},
    "kryteria_ustalone": {"w_trakcie", "nie_rozpoczeta"},
    "w_trakcie": {"do_podpisu", "kryteria_ustalone"},  # powrót: zmiana stanowiska (§ 9 ust. 1 rozp. 2016)
    "do_podpisu": {"zakonczona", "w_trakcie"},
    "zakonczona": {"sprzeciw"},
    "sprzeciw": {"zakonczona", "w_trakcie"},  # uwzględniony sprzeciw: ocena zmieniona albo sporządzona po raz drugi
}

R2016 = "rozp. PRM z 4.04.2016 (Dz. U. poz. 470)"
R2015 = "rozp. PRM z 23.07.2015 (Dz. U. poz. 1144)"
USC = "ustawa o służbie cywilnej"


# ------------------------------------------------------------------ arytmetyka dat
def parse(d) -> date | None:
    if d in (None, ""):
        return None
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def easter(y: int) -> date:  # algorytm Meeusa/Jonesa/Butchera (kalendarz gregoriański)
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def public_holidays(y: int) -> set:
    """Dni ustawowo wolne (ustawa z 18.01.1951 o dniach wolnych od pracy) [~]; Wigilia od 2025 r. [~]."""
    e = easter(y)
    fixed = [(1, 1), (1, 6), (5, 1), (5, 3), (8, 15), (11, 1), (11, 11), (12, 25), (12, 26)]
    days = {date(y, m, d) for m, d in fixed} | {e, add_days(e, 1), add_days(e, 49), add_days(e, 60)}
    if y >= 2025:
        days.add(date(y, 12, 24))
    return days


def shift_to_working_day(d: date) -> date:
    """Art. 115 KC: koniec terminu w sobotę/dzień wolny → następny dzień roboczy [~]."""
    while d.weekday() >= 5 or d in public_holidays(d.year):
        d = add_days(d, 1)
    return d


def absence_extension_days(absences) -> int:
    """Art. 81 ust. 7 ustawy: usprawiedliwiona nieobecność dłuższa niż miesiąc przedłuża termin o czas nieobecności."""
    total = 0
    for a in absences or []:
        f, t = parse(a.get("from")), parse(a.get("to"))
        if f and t and add_months(f, 1) <= t:
            total += (t - f).days + 1
    return total


# ------------------------------------------------------------------ kalendarze
def _ev(task, label, due=None, window=None, basis="", certainty="✔", done=None, note=""):
    return {"task": task, "label": label, "due": due.isoformat() if due else None,
            "window": {"from": window[0].isoformat(), "to": window[1].isoformat()} if window else None,
            "basis": basis, "certainty": certainty, "done_on": done, "note": note}


def periodic_calendar(p: dict) -> list:
    d = p.get("dates") or {}
    prev = parse(d.get("previous_evaluation_date"))
    start = parse(d.get("employment_start"))
    events = []
    if prev and d.get("previous_result") == "negatywna":
        events.append(_ev("kryteria", "Rozmowa i ustalenie kryteriów (Część I) po ocenie negatywnej", add_days(prev, 7),
                          basis=f"§ 7 pkt 2 {R2016}", done=d.get("criteria_meeting_date")))
    elif prev or start:
        base = prev or start
        events.append(_ev("kryteria", "Rozmowa i ustalenie kryteriów (Część I)", add_days(base, 30),
                          basis=f"§ 7 pkt 1 {R2016}", done=d.get("criteria_meeting_date"),
                          note="od sporządzenia poprzedniej oceny" if prev else "od zatrudnienia na czas nieokreślony"))
    ext = absence_extension_days(d.get("absences"))
    acquainted_prev = parse(d.get("previous_acquainted_date"))
    if prev and d.get("previous_result") == "negatywna":
        base = acquainted_prev or prev
        due = add_days(add_months(base, 6), ext)
        events.append(_ev("ocena", "Ponowna ocena po ocenie negatywnej (sporządzenie na piśmie)", due,
                          basis=f"art. 81 ust. 9 {USC}" + (" + art. 81 ust. 7" if ext else ""),
                          certainty="~" if not acquainted_prev else "✔", done=d.get("evaluation_written_date"),
                          note="ocenę sporządza się niezwłocznie po upływie 6 miesięcy od zapoznania się z oceną negatywną (poradnik s. 13)"
                               + ("" if acquainted_prev else "; brak daty zapoznania – liczono od daty sporządzenia [~]")))
    elif d.get("evaluation_deadline"):
        events.append(_ev("ocena", "Sporządzenie oceny na piśmie (termin z części I)", parse(d["evaluation_deadline"]),
                          basis=f"§ 6 ust. 1 {R2016}; art. 81 ust. 4 {USC}", done=d.get("evaluation_written_date")))
    elif prev or start:
        base = prev or start
        events.append(_ev("ocena", "Sporządzenie oceny na piśmie (co 24 miesiące)", add_days(add_months(base, 24), ext),
                          basis=f"art. 81 ust. 4 {USC}; poradnik KPRM 2016 s. 8–9" + (" + art. 81 ust. 7" if ext else ""), certainty="✔",
                          done=d.get("evaluation_written_date"),
                          note="24 miesiące od sporządzenia poprzedniej oceny albo zatrudnienia na czas nieokreślony; "
                               "data końcowa odpowiada dacie początkowej (art. 112 KC) – poradnik KPRM 2016 s. 8–9"))
    change = parse(d.get("position_change_date"))
    if change:
        events.append(_ev("kryteria_po_zmianie", "Ponowne ustalenie kryteriów po zmianie stanowiska", add_days(change, 30),
                          basis=f"§ 9 ust. 1 {R2016}", note="gdy zmiana nastąpiła w ciągu 6 miesięcy od ustalenia kryteriów/ostatniej oceny"))
        events.append(_ev("ocena_przy_zmianie", "Ocena przy zmianie stanowiska (okno)",
                          window=(add_days(change, -7), add_days(change, 30)),
                          basis=f"§ 9 ust. 2 {R2016}; art. 81 ust. 6 {USC}",
                          note="gdy od ostatniej oceny upłynęło więcej niż 6 miesięcy"))
    acq = parse(d.get("acquainted_date"))
    if acq:
        events.append(_ev("sprzeciw", "Termin na wniesienie sprzeciwu (dla ocenianego)", shift_to_working_day(add_days(acq, 7)),
                          basis=f"art. 83 ust. 1 {USC}; art. 115 KC [~]", done=d.get("objection_filed_date"),
                          note="7 dni od dnia zapoznania się z oceną"))
        if d.get("result") == "negatywna":
            events.append(_ev("ocena_ponowna", "Ponowna ocena po ocenie negatywnej", add_months(acq, 6),
                              basis=f"art. 81 ust. 9 {USC}"))
            events.append(_ev("kryteria_po_negatywnej", "Ustalenie kryteriów do ponownej oceny",
                              add_days(parse(d.get("evaluation_written_date")) or acq, 7), basis=f"§ 7 pkt 2 {R2016}"))
    filed = parse(d.get("objection_filed_date"))
    if filed:
        events.append(_ev("rozpatrzenie_sprzeciwu", "Rozpatrzenie sprzeciwu przez dyrektora generalnego", add_days(filed, 14),
                          basis=f"art. 83 ust. 3 {USC}", done=d.get("objection_decided_date")))
    return events


def first_calendar(p: dict) -> list:
    d = p.get("dates") or {}
    start = parse(d.get("employment_start"))
    if not start:
        raise ValueError("Pierwsza ocena: brak dates.employment_start")
    anchor = parse(d.get("substitution_agreed_date")) or start
    contract_end = parse(d.get("contract_end")) or add_days(add_months(start, 12), -1)
    # art. 112 KC: 8 miesięcy upływa z końcem dnia odpowiadającego datą dniowi zatrudnienia → ocena od dnia następnego;
    # „miesiąc przed upływem umowy” → ostatni dzień to dzień przed datą odpowiadającą (poradnik 2016 s. 9: okno 2.05–30.07.2016)
    earliest = add_days(add_months(start, 8), 1)
    latest = add_days(add_months(contract_end, -1), -1)
    window_days = int(p.get("report_window_days", 14))
    events = [
        _ev("rozmowa_wstepna", "Rozmowa wstępna", add_days(anchor, 21), basis=f"§ 3 {R2015}",
            done=d.get("intro_interview_date"),
            note="21 dni od nawiązania stosunku pracy" if anchor == start else "21 dni od ustalenia, że zastępca podlega pierwszej ocenie"),
        _ev("sprawozdanie", "Termin na złożenie sprawozdania (propozycja okna)",
            window=(parse((d.get("report_deadline") or {}).get("from")) or earliest,
                    parse((d.get("report_deadline") or {}).get("to")) or add_days(earliest, window_days - 1)),
            basis=f"§ 4 ust. 1 {R2015}; § 6 ust. 1 (sprawozdanie obejmuje min. 7 miesięcy)",
            certainty="~" if not d.get("report_deadline") else "✔", done=d.get("report_submitted_date"),
            note="musi przypadać po upływie 8 miesięcy; długość okna to ustawienie konfiguracyjne, nie przepis"),
        _ev("ocena", "Dokonanie pierwszej oceny (okno)", window=(earliest, latest),
            basis=f"art. 38 ust. 1 {USC}; art. 35 ust. 3 (umowa na 12 miesięcy)", done=d.get("evaluation_written_date"),
            certainty="~",
            note="nie wcześniej niż po 8 miesiącach od nawiązania stosunku pracy, nie później niż miesiąc przed końcem umowy"
                 + "; granice liczone jak w przykładzie poradnika KPRM 2016 (s. 9) – DO WERYFIKACJI z mentorem"
                 + ("" if d.get("contract_end") else "; koniec umowy = start + 12 miesięcy − 1 dzień")),
    ]
    if latest < earliest:
        events[-1]["note"] += " | UWAGA: okno puste – sprawdź datę końca umowy (art. 35 ust. 4 – przedłużenie)"
    return events


def calendar_for(p: dict) -> list:
    return first_calendar(p) if p.get("type") == "first" else periodic_calendar(p)


def flag(event: dict, today: date, warn_days: int = 14) -> str | None:
    if event.get("done_on"):
        return None
    due = parse(event["due"]) if event.get("due") else parse(event["window"]["to"]) if event.get("window") else None
    if not due:
        return None
    left = (due - today).days
    if left < 0:
        return "po_terminie"
    if left <= warn_days:
        return "zbliza_sie"
    return None


def evaluate(p: dict, today: date, warn_days: int = 14) -> dict:
    events = calendar_for(p)
    for e in events:
        e["flag"] = flag(e, today, warn_days)
        due = e["due"] or (e["window"] or {}).get("to")
        e["days_left"] = (parse(due) - today).days if due else None
    kind = "first" if p.get("type") == "first" else "periodic"
    status = p.get("status", "nie_rozpoczeta")
    return {"process_id": p.get("process_id"), "type": kind, "status": status,
            "status_label": STATUS_LABELS[kind].get(status, status), "today": today.isoformat(), "events": events,
            "flags": sorted({e["flag"] for e in events if e["flag"]})}


def change_status(p: dict, new: str, actor: str = "", now: str | None = None) -> dict:
    old = p.get("status", "nie_rozpoczeta")
    if new not in STATUSES:
        raise ValueError(f"Nieznany status {new}")
    if p.get("type") == "first" and new == "sprzeciw":
        raise ValueError("Pierwsza ocena nie przewiduje sprzeciwu w trybie art. 83 ustawy")
    if new not in TRANSITIONS[old]:
        raise ValueError(f"Niedozwolone przejście {old} → {new}")
    p = dict(p, status=new)
    p.setdefault("status_history", [])
    p["status_history"] = p["status_history"] + [{"from": old, "to": new, "by": actor, "at": now or datetime.now().isoformat(timespec="seconds")}]
    return p


# ------------------------------------------------------------------ przypomnienia (mock)
SUBJECT = "[Kompas Kompetencji] {flag_label}: {label} – {employee}"
BODY = ("Dzień dobry,\n\nprzypominamy o czynności w procesie oceny ({process_type}) pracownika {employee}:\n"
        "• {label}\n• termin: {due}\n• podstawa: {basis}\n\nStatus procesu: {status_label}.\n"
        "Szczegóły w Kompasie Kompetencji. Wiadomość wygenerowana automatycznie przez panel HR.\n\n{sender}")
FLAG_LABELS = {"po_terminie": "Termin minął", "zbliza_sie": "Zbliża się termin"}


def build_reminders(processes: list, today: date, sender: str, warn_days: int = 14, now: str | None = None) -> list:
    out = []
    for p in processes:
        ev = evaluate(p, today, warn_days)
        for e in ev["events"]:
            if not e["flag"] or e["task"] == "sprzeciw":  # sprzeciw to uprawnienie ocenianego – nie przypominamy oceniającemu
                continue
            recipient = (p.get("evaluator") or {})
            due = e["due"] or f"{e['window']['from']} – {e['window']['to']}"
            fields = {"flag_label": FLAG_LABELS[e["flag"]], "label": e["label"], "employee": (p.get("employee") or {}).get("full_name", ""),
                      "process_type": "pierwsza ocena" if ev["type"] == "first" else "ocena okresowa", "due": due,
                      "basis": e["basis"], "status_label": ev["status_label"], "sender": sender}
            out.append({"ts": now or datetime.now().isoformat(timespec="seconds"), "sender": sender,
                        "recipient": recipient.get("full_name", ""), "recipient_email": recipient.get("email", ""),
                        "process_id": p.get("process_id"), "task": e["task"], "due": due, "flag": e["flag"],
                        "channel": "mock-email", "delivered": False,
                        "subject": SUBJECT.format(**fields), "body": BODY.format(**fields)})
    return out


def append_log(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Terminy, statusy i przypomnienia HR (Kompas Kompetencji)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("calendar", "remind", "status"):
        s = sub.add_parser(name)
        s.add_argument("--input", required=True, help="proces JSON (albo lista procesów dla remind)")
        s.add_argument("--today", default=date.today().isoformat())
        s.add_argument("--warn-days", type=int, default=14)
        if name == "remind":
            s.add_argument("--log", required=True, help="plik JSON lines z logiem przypomnień")
            s.add_argument("--sender", required=True)
        if name == "status":
            s.add_argument("--to", required=True, choices=STATUSES)
            s.add_argument("--actor", default="")
    a = ap.parse_args(argv)
    data = json.loads(Path(a.input).read_text(encoding="utf-8"))
    today = parse(a.today)
    if a.cmd == "calendar":
        procs = data if isinstance(data, list) else [data]
        print(json.dumps([evaluate(p, today, a.warn_days) for p in procs], ensure_ascii=False, indent=2))
    elif a.cmd == "remind":
        procs = data if isinstance(data, list) else [data]
        entries = build_reminders(procs, today, a.sender, a.warn_days)
        append_log(Path(a.log), entries)
        print(json.dumps({"reminders": len(entries), "log": a.log, "delivery": "mock (bez wysyłki e-mail)"}, ensure_ascii=False))
    else:
        try:
            print(json.dumps(change_status(data, a.to, a.actor), ensure_ascii=False, indent=2))
        except ValueError as exc:
            print(f"BŁĄD: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
