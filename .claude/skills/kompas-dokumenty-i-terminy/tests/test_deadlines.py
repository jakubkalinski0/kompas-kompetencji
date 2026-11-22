from datetime import date

import pytest

import deadlines as dl


def ev(events, task):
    return next(e for e in events if e["task"] == task)


def test_add_months_end_of_month_clamp():
    assert dl.add_months(date(2025, 8, 31), 6) == date(2026, 2, 28)
    assert dl.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert dl.add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


def test_add_months_leap_year():
    assert dl.add_months(date(2023, 6, 29), 8) == date(2024, 2, 29)
    assert dl.add_months(date(2024, 2, 29), 24) == date(2026, 2, 28)
    assert dl.add_months(date(2026, 2, 28), 24) == date(2028, 2, 28)


def test_criteria_30_days_after_previous_evaluation():
    p = {"type": "periodic", "dates": {"previous_evaluation_date": "2026-01-31", "previous_result": "pozytywna"}}
    e = ev(dl.periodic_calendar(p), "kryteria")
    assert e["due"] == "2026-03-02"  # 30 dni od 31.01.2026 (luty 28 dni)
    assert "§ 7 pkt 1" in e["basis"]


def test_criteria_30_days_after_hiring_without_previous():
    p = {"type": "periodic", "dates": {"employment_start": "2026-12-15"}}
    assert ev(dl.periodic_calendar(p), "kryteria")["due"] == "2027-01-14"


def test_negative_previous_evaluation_7_days_and_6_months():
    p = {"type": "periodic", "dates": {"previous_evaluation_date": "2026-10-20", "previous_result": "negatywna",
                                       "previous_acquainted_date": "2026-10-22"}}
    events = dl.periodic_calendar(p)
    assert ev(events, "kryteria")["due"] == "2026-10-27"
    assert "§ 7 pkt 2" in ev(events, "kryteria")["basis"]
    assert ev(events, "ocena")["due"] == "2027-04-22"
    assert "art. 81 ust. 9" in ev(events, "ocena")["basis"]


def test_24_months_matches_kprm_guide_example():
    # poradnik „Oceny okresowe…” 2016, s. 9: poprzednia ocena 4.12.2013 → kolejna 4.12.2015
    p = {"type": "periodic", "dates": {"previous_evaluation_date": "2013-12-04", "previous_result": "pozytywna"}}
    assert ev(dl.periodic_calendar(p), "ocena")["due"] == "2015-12-04"


def test_24_months_default_and_absence_extension():
    p = {"type": "periodic", "dates": {"previous_evaluation_date": "2024-02-29", "previous_result": "pozytywna"}}
    assert ev(dl.periodic_calendar(p), "ocena")["due"] == "2026-02-28"
    p["dates"]["absences"] = [{"from": "2025-03-01", "to": "2025-04-30"}, {"from": "2025-06-01", "to": "2025-06-10"}]
    e = ev(dl.periodic_calendar(p), "ocena")
    assert e["due"] == "2026-04-30"  # +61 dni; nieobecność 10-dniowa (< 1 miesiąc) nie przedłuża
    assert "art. 81 ust. 7" in e["basis"]


def test_objection_7_days_shifted_from_weekend_and_holiday():
    p = {"type": "periodic", "dates": {"previous_evaluation_date": "2024-11-20", "acquainted_date": "2026-11-04"}}
    assert ev(dl.periodic_calendar(p), "sprzeciw")["due"] == "2026-11-12"  # 11.11 święto → 12.11
    p["dates"]["acquainted_date"] = "2026-11-14"  # +7 = sobota 21.11 → poniedziałek 23.11
    assert ev(dl.periodic_calendar(p), "sprzeciw")["due"] == "2026-11-23"


def test_polish_holidays_easter_based():
    h = dl.public_holidays(2027)
    assert date(2027, 3, 28) in h and date(2027, 3, 29) in h  # Wielkanoc 2027 i poniedziałek
    assert date(2027, 5, 27) in h  # Boże Ciało (Wielkanoc + 60)


def test_first_eval_calendar():
    p = {"type": "first", "dates": {"employment_start": "2026-01-12"}}
    events = dl.first_calendar(p)
    assert ev(events, "rozmowa_wstepna")["due"] == "2026-02-02"
    w = ev(events, "ocena")["window"]
    assert w == {"from": "2026-09-13", "to": "2026-12-10"}
    assert ev(events, "sprawozdanie")["window"]["from"] == "2026-09-13"


def test_first_eval_window_matches_kprm_guide_example():
    # poradnik „Pierwsza ocena…” 2016, s. 9: okno 2 maja – 30 lipca 2016 r. (zatrudnienie 1.09.2015, umowa do 31.08.2016)
    w = ev(dl.first_calendar({"type": "first", "dates": {"employment_start": "2015-09-01"}}), "ocena")["window"]
    assert w == {"from": "2016-05-02", "to": "2016-07-30"}


def test_first_eval_end_of_month_start():
    p = {"type": "first", "dates": {"employment_start": "2025-06-30"}}
    w = ev(dl.first_calendar(p), "ocena")["window"]
    assert w["from"] == "2026-03-01"  # 30.06 + 8 mies. → 28.02 (brak 30.02), ocena od dnia następnego
    assert w["to"] == "2026-05-28"  # koniec umowy 29.06.2026 − 1 miesiąc − 1 dzień


def test_first_eval_substitution_anchor():
    p = {"type": "first", "dates": {"employment_start": "2026-01-12", "substitution_agreed_date": "2026-03-02"}}
    assert ev(dl.first_calendar(p), "rozmowa_wstepna")["due"] == "2026-03-23"


def test_flags():
    p = {"type": "periodic", "status": "w_trakcie", "dates": {"previous_evaluation_date": "2024-11-20",
                                                              "criteria_meeting_date": "2024-11-25",
                                                              "evaluation_deadline": "2026-11-25"}}
    assert dl.evaluate(p, date(2026, 11, 21))["flags"] == ["zbliza_sie"]
    assert dl.evaluate(p, date(2026, 11, 26))["flags"] == ["po_terminie"]
    p["dates"]["evaluation_written_date"] = "2026-11-24"
    assert dl.evaluate(p, date(2026, 11, 26))["flags"] == []
    del p["dates"]["criteria_meeting_date"]  # brak odnotowania części I → zaległość
    assert dl.evaluate(p, date(2026, 11, 26))["flags"] == ["po_terminie"]


def test_status_transitions():
    p = {"type": "periodic", "status": "nie_rozpoczeta"}
    p = dl.change_status(p, "kryteria_ustalone", "przelozony", now="2026-11-21T10:00:00")
    assert p["status_history"][-1]["to"] == "kryteria_ustalone"
    with pytest.raises(ValueError):
        dl.change_status(p, "zakonczona")
    with pytest.raises(ValueError):
        dl.change_status({"type": "first", "status": "zakonczona"}, "sprzeciw")


def test_reminders_mock_log(tmp_path, example):
    procs = example("processes_demo")
    entries = dl.build_reminders(procs, date(2026, 11, 21), "Zofia Kadrowa-Demo", now="2026-11-21T14:00:00")
    assert entries and all(e["channel"] == "mock-email" and e["delivered"] is False for e in entries)
    assert {"ts", "sender", "recipient", "process_id", "task", "subject", "body"} <= set(entries[0])
    log = tmp_path / "rem.jsonl"
    dl.append_log(log, entries)
    assert len(log.read_text(encoding="utf-8").splitlines()) == len(entries)
