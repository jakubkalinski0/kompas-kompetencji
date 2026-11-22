"""Testy build_data.py. Uruchomienie:
    python -m pytest .claude/skills/kompas-dane-i-zrodla/tests --materials materialy
(albo zmienna KOMPAS_MATERIALY). Testy na materialach sa pomijane, gdy katalogu brak.
"""
import json
import re
from pathlib import Path

import pytest

import build_data as bd

EXPECTED_IDS = {
    "rzetelnosc", "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe",
    "organizacja_pracy_i_orientacja_na_osiaganie_celow", "wspolpraca", "komunikacja", "zarzadzanie_ludzmi",
    "podejmowanie_decyzji_i_odpowiedzialnosc", "myslenie_analityczne", "kreatywnosc", "negocjowanie",
    "wystapienia_publiczne", "orientacja_na_klienta_interesanta", "radzenie_sobie_w_sytuacjach_kryzysowych",
    "zarzadzanie_strategiczne",
}
KB_KEYS = {"id", "source_id", "doc_type", "title", "unit", "citation", "heading_path", "page_from", "page_to",
           "process", "text", "source_file"}


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def kb(built):
    return [json.loads(l) for l in (built / "kb" / "kb_chunks.jsonl").read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------- bez materialow
def test_doubled_char_detector():
    assert bd.has_doubled_chars("UUZZAASSAADDNNIIEENNIIEE PPRRZZYYZZNNAANNEEJJ")
    assert bd.has_doubled_chars("WWZZÓÓRR ARKUSZA")
    assert not bd.has_doubled_chars("Uzasadnienie przyznanej oceny okresowej – zarządzanie, współpraca, Rzetelność")


def test_slug_and_normalization():
    assert bd.slugify("Orientacja na klienta/interesanta") == "orientacja_na_klienta_interesanta"
    assert bd.slugify("Zarządzanie ludźmi") == "zarzadzanie_ludzmi"
    assert bd.norm_cmp("ORIENTACJA NA KLIENTA/ INTERESANTA") == bd.norm_cmp("Orientacja na klienta/interesanta")
    assert bd.norm_ws("a\nb  c") == "a b c"


def test_missing_pdftotext_is_readable_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bd, "_PDFTOTEXT", None)
    monkeypatch.setenv("PDFTOTEXT", str(tmp_path / "nie_ma_pdftotext.exe"))
    (tmp_path / "in").mkdir()
    rc = bd.main(["--input", str(tmp_path / "in"), "--output", str(tmp_path / "out")])
    assert rc == 2
    assert "pdftotext" in capsys.readouterr().err
    monkeypatch.setattr(bd, "_PDFTOTEXT", None)


# ---------------------------------------------------------------- model kompetencji
def test_model_counts(built):
    m = load(built / "competency_model.json")
    assert len(m["competencies"]) == 14
    assert sum(len(c["indicators"]) for c in m["competencies"]) == 49
    assert [s["level"] for s in m["scale"]] == [1, 2, 3, 4, 5]
    assert len(m["instructions"]) == 3


def test_model_ids_names_levels(built):
    m = load(built / "competency_model.json")
    ids = {c["id"] for c in m["competencies"]}
    assert ids == EXPECTED_IDS
    names = {c["id"]: c["name"] for c in m["competencies"]}
    assert names["orientacja_na_klienta_interesanta"] == "Orientacja na klienta/interesanta"
    assert names["radzenie_sobie_w_sytuacjach_kryzysowych"] == "Radzenie sobie w sytuacjach kryzysowych"
    for c in m["competencies"]:
        assert c["name"] in bd.CANONICAL_CRITERIA
        assert c["name"][0].isupper() and c["name"][1:] == c["name"][1:].lower() or "/" in c["name"]
        for i, ind in enumerate(c["indicators"], 1):
            assert ind["id"] == f"{c['id']}.{i}"
            assert "\n" not in ind["text"] and "  " not in ind["text"]
            assert sorted(ind["levels"]) == ["1", "2", "3", "4", "5"]
            assert all(v.strip() for v in ind["levels"].values())


# ---------------------------------------------------------------- arkusze
@pytest.mark.parametrize("form,expected", [
    ("periodic_b", ["zarzadzanie_ludzmi", "podejmowanie_decyzji_i_odpowiedzialnosc",
                    "organizacja_pracy_i_orientacja_na_osiaganie_celow", "wspolpraca", "komunikacja"]),
    ("periodic_c", ["wykorzystywanie_wiedzy_i_doskonalenie_zawodowe", "rzetelnosc",
                    "organizacja_pracy_i_orientacja_na_osiaganie_celow", "wspolpraca", "komunikacja"]),
    ("first_eval", ["rzetelnosc", "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe",
                    "organizacja_pracy_i_orientacja_na_osiaganie_celow", "komunikacja", "wspolpraca"]),
])
def test_form_mandatory_criteria(built, form, expected):
    f = load(built / "forms" / f"{form}.json")
    assert [c["id"] for c in f["mandatory_criteria"]] == expected


def test_form_footnotes_verbatim(built):
    b = {n["number"]: n for n in load(built / "forms" / "periodic_b.json")["footnotes"]}
    c = {n["number"]: n for n in load(built / "forms" / "periodic_c.json")["footnotes"]}
    fe = {n["number"]: n for n in load(built / "forms" / "first_eval.json")["footnotes"]}
    assert len(b) == 18 and len(c) == 18 and len(fe) == 8
    for notes in (b, c):
        assert notes[10]["text"].startswith("POZYTYWNA – w przypadku ustalenia ogólnego poziomu")
        assert notes[11]["text"].startswith("NEGATYWNA – w przypadku ustalenia ogólnego poziomu")
        assert "co najmniej jednej oceny cząstkowej na poziomie „znacznie poniżej oczekiwań”" in notes[11]["text"]
        assert notes[18]["text"].startswith("Części III nie drukuje się")
        assert notes[18]["role"] == "part3" and notes[10]["role"] == "result_positive"
        assert notes[12]["text"].startswith("Uzasadnienie jest obligatoryjne")
    assert "bezpośrednim kierowaniu pracownikami" in b[1]["text"]
    assert "stanowiskiem kierownika urzędu" in c[1]["text"]
    assert fe[6]["text"].startswith("Pozytywną pierwszą ocenę należy przyznać")
    assert "– złożył sprawozdanie w wyznaczonym terminie" in fe[6]["text"]
    assert fe[5]["role"] == "exam_not_applicable"


def test_form_scales(built):
    b = load(built / "forms" / "periodic_b.json")
    fe = load(built / "forms" / "first_eval.json")
    assert [s["points"] for s in b["scale"]] == [1, 3, 5, 7, 9]
    assert [s["level"] for s in b["scale"]] == [1, 2, 3, 4, 5]
    assert [s["points"] for s in fe["scale"]] == [3, 5, 7]
    assert [s["level"] for s in fe["scale"]] == [2, 3, 4]
    assert [(o["min"], o["max"], o["min_inclusive"]) for o in b["overall_levels"]] == [
        (1, 2, True), (2, 4, False), (4, 6, False), (6, 8, False), (8, 9, False)]
    assert b["additional_criteria_max"] == 3
    assert [p["id"] for p in b["parts"]] == ["part1", "part2", "part3"]


# ---------------------------------------------------------------- zalacznik nr 1
def test_first_eval_element_descriptions(built):
    fe = load(built / "forms" / "first_eval.json")
    el = fe["element_descriptions"]["criteria"]
    assert [c["id"] for c in el] == [c["id"] for c in fe["mandatory_criteria"]]
    assert sum(len(c["description"]) for c in el) == 20


def test_annex1_and_model_check(built):
    a = load(built / "annex1_criteria.json")
    assert len(a["criteria"]) == 14
    assert {c["id"] for c in a["criteria"]} == EXPECTED_IDS
    assert sum(len(c["description"]) for c in a["criteria"]) == 49
    assert a["model_check"]["checked"] == 49
    assert a["model_check"]["mismatches"] == []


# ---------------------------------------------------------------- baza wiedzy
def test_kb_schema_and_unique_ids(built):
    chunks = kb(built)
    assert len(chunks) > 100
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))
    for c in chunks:
        assert KB_KEYS <= set(c), c["id"]
        assert c["doc_type"] in {"rozporzadzenie", "ustawa", "poradnik", "model_kompetencji", "arkusz", "kprm_qa"}
        assert set(c["process"]) <= {"periodic", "first"} and c["process"]
        assert c["text"].strip() and c["citation"].strip()
    sources = load(built / "kb" / "sources.json")
    assert {"rozp2016", "rozp2015", "poradnik_okresowa_2016", "poradnik_pierwsza_2016",
            "model_kompetencji"} <= {s["source_id"] for s in sources}


def test_kb_no_doubled_chars(built):
    bad = [c["id"] for c in kb(built) if bd.has_doubled_chars(c["text"])]
    assert bad == []


def test_kb_key_paragraphs(built):
    by_id = {c["id"]: c for c in kb(built)}
    par11 = [c for i, c in by_id.items() if re.match(r"rozp2016:par11(:|$)", i)]
    assert par11, "brak § 11 rozp. 2016"
    assert any("znacznie poniżej oczekiwań – 1 punkt" in c["text"] for c in par11)
    assert "Dz. U. poz. 470" in par11[0]["citation"]
    assert by_id["rozp2015:par9"]["text"].startswith("§ 9.")
    assert "3 punkty – poniżej oczekiwań" in by_id["rozp2015:par9"]["text"]
    assert by_id["rozp2015:par10"]["text"].startswith("§ 10. 1. Warunkiem przyznania pozytywnej pierwszej oceny")
    assert "Dz. U. poz. 1144" in by_id["rozp2015:par10"]["citation"]
    assert by_id["rozp2015:par9"]["process"] == ["first"]


def test_kb_guides_chunk_sizes(built):
    for sid in ("poradnik_okresowa_2016", "poradnik_pierwsza_2016"):
        ch = [c for c in kb(built) if c["source_id"] == sid]
        assert len(ch) >= 10
        assert all(c["page_from"] and c["heading_path"] for c in ch)
        assert max(len(c["text"].split()) for c in ch) <= 1300


def test_kb_ustawa_if_present(built):
    rep = load(built / "build_report.json")
    arts = [c for c in kb(built) if c["source_id"] == "ustawa_sc"]
    if not bd.DEFAULT_USTAWA.exists():
        assert any("ustawy" in w for w in rep["warnings"])
        pytest.skip("brak pliku ustawy (C2)")
    ids = {c["id"] for c in arts}
    for art in ("38", "81", "83", "89"):
        assert any(i == f"ustawa_sc:art{art}" or i.startswith(f"ustawa_sc:art{art}:") for i in ids), art


# ---------------------------------------------------------------- determinizm
def test_deterministic(materials, built, tmp_path):
    out2 = tmp_path / "again"
    assert bd.main(["--input", str(materials), "--output", str(out2)]) == 0
    files1 = sorted(p.relative_to(built).as_posix() for p in built.rglob("*") if p.is_file())
    files2 = sorted(p.relative_to(out2).as_posix() for p in out2.rglob("*") if p.is_file())
    assert files1 == files2
    for f in files1:
        assert (built / f).read_bytes() == (out2 / f).read_bytes(), f
