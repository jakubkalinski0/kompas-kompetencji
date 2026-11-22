import copy
import shutil

import pytest

import render_pdf
import validate_pdf

needs_poppler = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="brak pdftotext (poppler)")


def failed(pdf, doc, kind="arkusz"):
    return [(n, d) for n, ok, d in validate_pdf.check(pdf, doc, kind) if not ok]


@needs_poppler
@pytest.mark.parametrize("name", ["anna_b", "jan_c", "piotr_first_positive", "piotr_first_negative"])
def test_each_form_renders_and_validates(tmp_path, example, name):
    doc = example(name)
    out = tmp_path / f"{name}.pdf"
    info = render_pdf.render(doc, out)
    assert out.stat().st_size > 10_000
    assert failed(out, doc) == []
    assert info["result"] == doc["result"]


@needs_poppler
def test_karta_has_header_and_sdr(tmp_path, example):
    doc = example("ewa_karta")
    out = tmp_path / "karta.pdf"
    render_pdf.render(doc, out, kind="karta")
    assert failed(out, doc, "karta") == []
    text = validate_pdf.pdf_text(out)
    assert "Dokument roboczy przełożonego – nie włączać do akt osobowych" in text


@needs_poppler
def test_part3_printed_for_official_with_request(tmp_path, example):
    doc = example("anna_b")
    out = tmp_path / "a.pdf"
    assert render_pdf.render(doc, out)["part3_printed"] is True
    text = validate_pdf.pdf_text(out)
    assert "CZĘŚĆ III" in text and "drugiego" in text


@needs_poppler
def test_no_part3_for_civil_service_employee_even_if_requested(tmp_path, example):
    doc = example("jan_c")
    doc["part3_requested"] = True
    doc["part3"] = {"appointment_year": 2015, "current_grade": "pierwszy", "requested_grade": "drugiego", "motivation": "X-MOTYWACJA"}
    out = tmp_path / "j.pdf"
    info = render_pdf.render(doc, out)
    assert info["part3_printed"] is False and any("przypis 18" in w for w in info["warnings"])
    text = validate_pdf.pdf_text(out)
    assert "CZĘŚĆ III" not in text and "X-MOTYWACJA" not in text
    assert failed(out, doc) == []


@needs_poppler
def test_no_part3_for_official_without_request(tmp_path, example):
    doc = example("anna_b")
    doc["part3_requested"] = False
    out = tmp_path / "a2.pdf"
    render_pdf.render(doc, out)
    assert "CZĘŚĆ III" not in validate_pdf.pdf_text(out)


@needs_poppler
def test_negative_first_eval_drops_development_conclusions(tmp_path, example):
    doc = example("piotr_first_negative")
    out = tmp_path / "n.pdf"
    info = render_pdf.render(doc, out)
    assert info["development_conclusions_printed"] is False
    assert "NIE MOŻE TRAFIĆ" not in validate_pdf.pdf_text(out)


@needs_poppler
def test_official_sheet_never_contains_sdr_notes(tmp_path, example):
    doc = example("anna_b")
    note = doc["criteria"][0]["indicator_ratings"][0]["sdr_note"]
    assert note
    out = tmp_path / "s.pdf"
    render_pdf.render(doc, out)
    assert note[:30] not in validate_pdf.pdf_text(out)


def test_missing_supervisor_decision_is_rejected(tmp_path, example):
    doc = example("jan_c")
    doc["criteria"][0]["final_points"] = None
    with pytest.raises(render_pdf.InputError):
        render_pdf.render(doc, tmp_path / "x.pdf")


def test_negative_periodic_requires_justification(tmp_path, example):
    doc = copy.deepcopy(example("jan_c"))
    doc["criteria"][1]["final_points"] = 1
    doc["result"], doc["justification"], doc["average"] = "negatywna", None, None
    with pytest.raises(render_pdf.InputError):
        render_pdf.render(doc, tmp_path / "x.pdf")


def test_more_than_three_additional_criteria_rejected(tmp_path, example):
    doc = example("jan_c")
    extra = dict(doc["criteria"][-1])
    doc["criteria"] += [dict(extra, id=f"x{i}") for i in range(3)]
    with pytest.raises(render_pdf.InputError):
        render_pdf.render(doc, tmp_path / "x.pdf")


def test_overall_level_thresholds():
    assert render_pdf.overall_level(2.0) == "znacznie poniżej oczekiwań"
    assert render_pdf.overall_level(2.01) == "poniżej oczekiwań"
    assert render_pdf.overall_level(4.0) == "poniżej oczekiwań"
    assert render_pdf.overall_level(6.0) == "na poziomie oczekiwań"
    assert render_pdf.overall_level(8.5) == "znacznie powyżej oczekiwań"


def test_footnotes_extracted_verbatim():
    import json
    data = json.loads(render_pdf.FORM_TEXTS.read_text(encoding="utf-8"))["forms"]
    assert len(data["periodic_b"]["footnotes"]) == 18 and len(data["first_eval"]["footnotes"]) == 8
    assert data["periodic_c"]["footnotes"]["18"].startswith("Części III nie drukuje się")
    assert "tylko w przypadku przyznania pozytywnej pierwszej oceny" in data["first_eval"]["footnotes"]["8"]
