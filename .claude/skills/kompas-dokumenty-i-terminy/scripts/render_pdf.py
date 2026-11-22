"""Generator PDF: oficjalne arkusze (B, C, pierwsza ocena) i robocza karta przygotowania do rozmowy.

Użycie:
    python render_pdf.py --input dokument_oceny.json --output arkusz.pdf            # arkusz wg pola "form"
    python render_pdf.py --input dokument_oceny.json --output karta.pdf --kind karta

Wejście: dokument oceny wg kontraktu C3 (kompas-model-i-silnik-oceny/assets/evaluation_schema.json).
Układ i kolejność części/pól wg DOCX wzorów: zał. nr 3 i 4 do rozp. PRM z 4.04.2016 (Dz. U. poz. 470)
oraz zał. nr 2 do rozp. PRM z 23.07.2015 (Dz. U. poz. 1144). Przypisy drukowane dosłownie
z assets/form_texts.json (wyciąg z DOCX przez extract_form_texts.py).

Zależności: reportlab (BSD), czcionka DejaVu Sans z assets/fonts (licencja Bitstream Vera/DejaVu – permisywna).
Kody wyjścia: 0 OK, 2 błąd danych wejściowych (np. brak decyzji przełożonego).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SKILL_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = SKILL_DIR / "assets" / "fonts"
FORM_TEXTS = SKILL_DIR / "assets" / "form_texts.json"

KARTA_HEADER = "Dokument roboczy przełożonego – nie włączać do akt osobowych"

PERIODIC_SCALE = [
    (1, "Znacznie poniżej oczekiwań", "1 punkt"),
    (3, "Poniżej oczekiwań", "3 punkty"),
    (5, "Na poziomie oczekiwań", "5 punktów"),
    (7, "Powyżej oczekiwań", "7 punktów"),
    (9, "Znacznie powyżej oczekiwań", "9 punktów"),
]
FIRST_SCALE = [(3, "poniżej oczekiwań", "3 punkty"), (5, "na poziomie oczekiwań", "5 punktów"),
               (7, "powyżej oczekiwań", "7 punktów")]
OVERALL_ROWS = [  # § 11 ust. 1 pkt 2 rozp. 2016 / tabela "PRZYZNANIE OCENY" w arkuszu
    ("od 1 punktu do 2 punktów", "znacznie poniżej oczekiwań", 1.0, 2.0),
    ("powyżej 2 punktów do 4 punktów", "poniżej oczekiwań", 2.0, 4.0),
    ("powyżej 4 punktów do 6 punktów", "na poziomie oczekiwań", 4.0, 6.0),
    ("powyżej 6 punktów do 8 punktów", "powyżej oczekiwań", 6.0, 8.0),
    ("powyżej 8 punktów do 9 punktów", "znacznie powyżej oczekiwań", 8.0, 9.0),
]
MANDATORY = {
    "periodic_b": [("zarzadzanie_ludzmi", "Zarządzanie ludźmi"),
                   ("podejmowanie_decyzji_i_odpowiedzialnosc", "Podejmowanie decyzji i odpowiedzialność"),
                   ("organizacja_pracy_i_orientacja_na_osiaganie_celow", "Organizacja pracy i orientacja na osiąganie celów"),
                   ("wspolpraca", "Współpraca"), ("komunikacja", "Komunikacja")],
    "periodic_c": [("wykorzystywanie_wiedzy_i_doskonalenie_zawodowe", "Wykorzystywanie wiedzy i doskonalenie zawodowe"),
                   ("rzetelnosc", "Rzetelność"),
                   ("organizacja_pracy_i_orientacja_na_osiaganie_celow", "Organizacja pracy i orientacja na osiąganie celów"),
                   ("wspolpraca", "Współpraca"), ("komunikacja", "Komunikacja")],
    "first_eval": [("rzetelnosc", "Rzetelność"),
                   ("wykorzystywanie_wiedzy_i_doskonalenie_zawodowe", "Wykorzystywanie wiedzy i doskonalenie zawodowe"),
                   ("organizacja_pracy_i_orientacja_na_osiaganie_celow", "Organizacja pracy i orientacja na osiąganie celów"),
                   ("komunikacja", "Komunikacja"), ("wspolpraca", "Współpraca")],
}
FORM_META = {
    "periodic_b": {"annex": "Załącznik nr 3", "letter": "ARKUSZ B"},
    "periodic_c": {"annex": "Załącznik nr 4", "letter": "ARKUSZ C"},
    "first_eval": {"annex": "Załącznik nr 2", "letter": None},
}
DOTS = "…………………………………."


class InputError(ValueError):
    pass


# ---------------------------------------------------------------- style i czcionki
def register_fonts(fonts_dir: Path = FONTS_DIR) -> None:
    if "DejaVu" in pdfmetrics.getRegisteredFontNames():
        return
    reg, bold = fonts_dir / "DejaVuSans.ttf", fonts_dir / "DejaVuSans-Bold.ttf"
    if not reg.exists() or not bold.exists():
        raise FileNotFoundError(f"Brak czcionek DejaVu w {fonts_dir} – bez nich PDF nie pokaże polskich znaków")
    pdfmetrics.registerFont(TTFont("DejaVu", str(reg)))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(bold)))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")


def styles() -> dict:
    base = ParagraphStyle("base", fontName="DejaVu", fontSize=8.5, leading=10.5)
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7, leading=8.5),
        "label": ParagraphStyle("label", parent=base, fontSize=7, leading=8.5, alignment=TA_CENTER),
        "right": ParagraphStyle("right", parent=base, fontSize=8, alignment=TA_RIGHT),
        "title": ParagraphStyle("title", parent=base, fontName="DejaVu-Bold", fontSize=11, leading=14, alignment=TA_CENTER),
        "h": ParagraphStyle("h", parent=base, fontName="DejaVu-Bold", fontSize=9, leading=12, spaceBefore=6, spaceAfter=3),
        "part": ParagraphStyle("part", parent=base, fontName="DejaVu-Bold", fontSize=10, leading=13, alignment=TA_CENTER,
                               spaceBefore=8, spaceAfter=4),
        "cell_b": ParagraphStyle("cell_b", parent=base, fontName="DejaVu-Bold"),
        "center": ParagraphStyle("center", parent=base, alignment=TA_CENTER),
        "center_b": ParagraphStyle("center_b", parent=base, fontName="DejaVu-Bold", alignment=TA_CENTER),
        "fn": ParagraphStyle("fn", parent=base, fontSize=7, leading=8.6, leftIndent=10, firstLineIndent=-10, spaceAfter=1.5),
        "banner": ParagraphStyle("banner", parent=base, fontName="DejaVu-Bold", fontSize=10, leading=13, alignment=TA_CENTER,
                                 textColor=colors.HexColor("#8a1c1c")),
    }


def fn(n) -> str:
    return f"<super>{n})</super>"


def t(text) -> str:
    return escape("" if text is None else str(text))


GRID = [("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
GREY = colors.HexColor("#e6e6e6")
WIDTH = A4[0] - 30 * mm


def table(rows, widths, extra=None, grid=True):
    tb = Table(rows, colWidths=widths)
    tb.setStyle(TableStyle((GRID if grid else [("FONTNAME", (0, 0), (-1, -1), "DejaVu")]) + (extra or [])))
    return tb


def fmt_date(value) -> str:
    """ISO rrrr-mm-dd -> dd.mm.rrrr (format wzoru arkusza)."""
    if not value:
        return ""
    s = str(value)
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}.{s[5:7]}.{s[0:4]}"
    return s


def fmt_num(x) -> str:
    return "" if x is None else f"{float(x):.2f}".replace(".", ",")


def split_name(person: dict) -> tuple:
    person = person or {}
    if person.get("first_name") or person.get("last_name"):
        return person.get("first_name", ""), person.get("last_name", "")
    parts = (person.get("full_name") or "").split()
    return (parts[0] if parts else ""), " ".join(parts[1:])


def overall_level(avg: float) -> str:
    for _, label, lo, hi in OVERALL_ROWS:
        if (lo == 1.0 and 1.0 <= avg <= hi) or (lo < avg <= hi):
            return label
    raise InputError(f"Średnia {avg} poza skalą 1–9")


# ---------------------------------------------------------------- bloki wspólne
def person_rows(S, person: dict, position_label: str, extra_rows=None):
    first, last = split_name(person)
    rows = [[Paragraph("Imię", S["base"]), Paragraph(t(first), S["base"])],
            [Paragraph("Nazwisko", S["base"]), Paragraph(t(last), S["base"])],
            [Paragraph("Komórka organizacyjna", S["base"]), Paragraph(t(person.get("unit")), S["base"])],
            [Paragraph(position_label, S["base"]), Paragraph(t(person.get("position")), S["base"])]]
    rows += extra_rows or []
    return table(rows, [55 * mm, WIDTH - 55 * mm], [("BACKGROUND", (0, 0), (0, -1), GREY)])


def signature_block(S, labels, values=None, header=None):
    values = values or [""] * len(labels)
    n = len(labels)
    w = WIDTH / n
    rows = []
    if header:
        rows.append([Paragraph(header, S["base"])] + [""] * (n - 1))
    rows.append([Paragraph(t(v) if v else DOTS, S["center"]) for v in values])
    rows.append([Paragraph(lbl, S["label"]) for lbl in labels])
    extra = [("BOX", (0, 0), (-1, -1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
             ("TOPPADDING", (0, 0), (-1, -1), 2)]
    if header:
        extra += [("SPAN", (0, 0), (-1, 0)), ("BOTTOMPADDING", (0, 0), (-1, 0), 10)]
    return table(rows, [w] * n, extra, grid=False)


def _empty_box(h, text, S):
    """Pole tekstowe arkusza: puste pole ma stałą wysokość, wypełnione rośnie z treścią."""
    p = Paragraph(t(text).replace("\n", "<br/>") if text else "", S["base"])
    tb = Table([[p]], colWidths=[WIDTH], rowHeights=[None if text else h])
    tb.setStyle(TableStyle(GRID + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tb


def x_mark(cond: bool) -> str:
    return "X" if cond else ""


def footnotes_block(S, form: str):
    texts = json.loads(FORM_TEXTS.read_text(encoding="utf-8"))["forms"][form]["footnotes"]
    out = [Paragraph("PRZYPISY (brzmienie ze wzoru arkusza)", S["h"])]
    for k in sorted(texts, key=int):
        body = t(texts[k]).replace("\n", "<br/>")
        out.append(Paragraph(f"{k}) {body}", S["fn"]))
    return out


def _on_page(label):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVu", 7)
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"{label} – strona {doc.page}")
        canvas.restoreState()
    return draw


def _criteria_by_id(doc: dict) -> dict:
    return {c.get("id"): c for c in doc.get("criteria", [])}


def _final_points(c: dict, allowed) -> int:
    pts = c.get("final_points")
    if pts is None:
        raise InputError(f"Kryterium '{c.get('name') or c.get('id')}': brak final_points – ostateczny poziom wybiera przełożony")
    if int(pts) not in allowed:
        raise InputError(f"Kryterium '{c.get('name')}': final_points={pts} poza skalą {sorted(allowed)}")
    return int(pts)


def _average(points) -> float:
    return round(sum(points) / len(points), 2)


# ---------------------------------------------------------------- arkusze B / C
def build_periodic(doc: dict, S) -> tuple:
    form = doc["form"]
    meta = FORM_META[form]
    emp, ev = doc.get("employee") or {}, doc.get("evaluator") or {}
    crit = _criteria_by_id(doc)
    missing = [name for cid, name in MANDATORY[form] if cid not in crit]
    if missing:
        raise InputError(f"Brak kryteriów obowiązkowych arkusza: {', '.join(missing)}")
    additional = [c for c in doc.get("criteria", []) if c.get("kind") == "additional"]
    if len(additional) > 3:
        raise InputError("Najwyżej 3 kryteria dodatkowe (przypis 3 arkusza, § 4 ust. 2 rozp. 2016)")
    warnings = []
    pts_all = [_final_points(crit[cid], {1, 3, 5, 7, 9}) for cid, _ in MANDATORY[form]]
    pts_all += [_final_points(c, {1, 3, 5, 7, 9}) for c in additional]
    avg = doc.get("average")
    avg = _average(pts_all) if avg is None else float(avg)
    if abs(avg - _average(pts_all)) > 0.01:
        warnings.append(f"Średnia w dokumencie ({avg}) różni się od policzonej z ocen cząstkowych ({_average(pts_all)})")
    level = overall_level(avg)
    result = doc.get("result") or ("pozytywna" if avg > 4 and 1 not in pts_all else "negatywna")
    is_official = emp.get("corps_status") == "urzednik_sc"
    part3 = doc.get("part3") or None
    wants3 = bool(doc.get("part3_requested") or (doc.get("print") or {}).get("include_part3"))
    print_part3 = bool(part3) and wants3 and is_official
    if part3 and wants3 and not is_official:
        warnings.append("Część III pominięta: oceniany jest pracownikiem SC (przypis 18)")
    if print_part3 and result != "pozytywna":
        warnings.append("Część III pominięta: wniosek o stopień tylko po pozytywnej ocenie (art. 89 ust. 1 ustawy)")
        print_part3 = False
    if result == "negatywna" and not (doc.get("justification") or "").strip():
        raise InputError("Ocena negatywna wymaga uzasadnienia (przypis 12)")
    p1 = doc.get("part1") or {}
    place = doc.get("place", "")
    E = []
    E.append(Paragraph(meta["annex"], S["right"]))
    E.append(Spacer(1, 2 * mm))
    E.append(Paragraph(meta["letter"], S["title"]))
    E.append(Paragraph("OCENA OKRESOWA", S["title"]))
    E.append(Paragraph("URZĘDNIKA SŁUŻBY CYWILNEJ LUB PRACOWNIKA SŁUŻBY CYWILNEJ" + fn(1), S["title"]))
    E.append(Paragraph("CZĘŚĆ I", S["part"]))
    E.append(table([[Paragraph("NAZWA URZĘDU", S["cell_b"]), Paragraph(t(doc.get("office_name")), S["base"])]],
                   [55 * mm, WIDTH - 55 * mm], [("BACKGROUND", (0, 0), (0, -1), GREY)]))
    E.append(Paragraph("DANE OCENIANEGO", S["h"]))
    E.append(person_rows(S, emp, "Stanowisko pracy" + fn(2)))
    E.append(Paragraph("DANE OCENIAJĄCEGO", S["h"]))
    E.append(person_rows(S, ev, "Stanowisko pracy"))
    E.append(Paragraph("KRYTERIA OCENY I TERMIN SPORZĄDZENIA OCENY", S["h"]))
    add_names = [c.get("name", "") for c in additional] + [""] * (3 - len(additional))
    rows = [[Paragraph("Kryteria obowiązkowe", S["center_b"]),
             Paragraph("Kryteria dodatkowe<br/>wybrane przez oceniającego<br/>(nie więcej niż 3)" + fn(3), S["center_b"]), ""]]
    mand = [name for _, name in MANDATORY[form]]
    for i, name in enumerate(mand):
        right = [Paragraph(t(add_names[i]), S["base"]), ""] if i < 3 else (
            [Paragraph("Termin sporządzenia oceny", S["cell_b"]), Paragraph(t(fmt_date(p1.get("evaluation_deadline") or p1.get("deadline"))) or "(dd.mm.rrrr)", S["center"])]
            if i == 3 else ["", ""])
        rows.append([Paragraph(name, S["base"])] + right)
    ext = [("SPAN", (1, 0), (2, 0)), ("SPAN", (1, 1), (2, 1)), ("SPAN", (1, 2), (2, 2)), ("SPAN", (1, 3), (2, 3)),
           ("BACKGROUND", (0, 0), (-1, 0), GREY)]
    E.append(table(rows, [WIDTH * 0.5, WIDTH * 0.28, WIDTH * 0.22], ext))
    E.append(Spacer(1, 2 * mm))
    confirm = ("Potwierdzamy:<br/>– przeprowadzenie rozmowy, o której mowa w § 5 ust. 1 rozporządzenia Prezesa Rady Ministrów "
               "z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników służby "
               "cywilnej i pracowników służby cywilnej (Dz. U. poz. 470), i omówienie w trakcie tej rozmowy wszystkich "
               "wymaganych zagadnień" + fn(4) + ",<br/>– zapoznanie ocenianego z kryteriami oceny oraz terminem sporządzenia oceny.")
    d1 = fmt_date(p1.get("criteria_meeting_date") or (doc.get("period") or {}).get("from"))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "podpis oceniającego"], [place, d1, ""], header=confirm))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "podpis ocenianego"], [place, d1, ""]))

    # ---------------- CZĘŚĆ II
    E.append(Paragraph("CZĘŚĆ II", S["part"]))
    period = doc.get("period") or {}
    E.append(table([[Paragraph("DATA PRZEPROWADZENIA ROZMOWY OCENIAJĄCEJ" + fn(5), S["cell_b"]),
                     Paragraph(t(fmt_date(doc.get("interview_date"))) or "(dd.mm.rrrr)", S["center"]), "", "", ""],
                    [Paragraph("OKRES, W KTÓRYM OCENIANY PODLEGAŁ OCENIE", S["cell_b"]), Paragraph("OD" + fn(6) + ":", S["base"]),
                     Paragraph(t(fmt_date(period.get("from"))), S["center"]), Paragraph("DO" + fn(7) + ":", S["base"]),
                     Paragraph(t(fmt_date(period.get("to"))), S["center"])]],
                   [WIDTH * 0.42, WIDTH * 0.1, WIDTH * 0.19, WIDTH * 0.1, WIDTH * 0.19],
                   [("SPAN", (1, 0), (4, 0)), ("BACKGROUND", (0, 0), (0, -1), GREY)]))
    E.append(Spacer(1, 2 * mm))
    cw = [WIDTH * 0.35] + [WIDTH * 0.13] * 5
    rows = [[Paragraph("KRYTERIA OBOWIĄZKOWE", S["center_b"]), Paragraph("OCENA CZĄSTKOWA" + fn(8), S["center_b"]), "", "", "", ""],
            [""] + [Paragraph(lbl, S["label"]) for _, lbl, _ in PERIODIC_SCALE],
            [""] + [Paragraph(p, S["label"]) for _, _, p in PERIODIC_SCALE]]
    for cid, name in MANDATORY[form]:
        p = int(crit[cid]["final_points"])
        rows.append([Paragraph(name, S["base"])] + [Paragraph(x_mark(p == v), S["center_b"]) for v, _, _ in PERIODIC_SCALE])
    hdr2 = len(rows)
    rows.append([Paragraph("KRYTERIA DODATKOWE WYBRANE PRZEZ OCENIAJĄCEGO" + fn(9), S["center_b"]),
                 Paragraph("OCENA CZĄSTKOWA" + fn(8), S["center_b"]), "", "", "", ""])
    for i in range(3):
        if i < len(additional):
            p = int(additional[i]["final_points"])
            rows.append([Paragraph(t(additional[i].get("name")), S["base"])] +
                        [Paragraph(x_mark(p == v), S["center_b"]) for v, _, _ in PERIODIC_SCALE])
        else:
            rows.append([""] * 6)
    rows.append([Paragraph("Średnia arytmetyczna z ocen cząstkowych przyznanych za poszczególne kryteria oceny:", S["cell_b"]),
                 Paragraph(fmt_num(avg), S["center_b"]), "", "", "", ""])
    last = len(rows) - 1
    ext = [("SPAN", (1, 0), (5, 0)), ("SPAN", (0, 0), (0, 2)), ("SPAN", (1, hdr2), (5, hdr2)), ("SPAN", (1, last), (5, last)),
           ("BACKGROUND", (0, 0), (-1, 2), GREY), ("BACKGROUND", (0, hdr2), (-1, hdr2), GREY)]
    E.append(table(rows, cw, ext))
    E.append(Paragraph("PRZYZNANIE OCENY", S["h"]))
    rows = [[Paragraph("Należy wstawić znak „X” w odpowiednie pole", S["label"]),
             Paragraph("Liczba punktów stanowiąca średnią arytmetyczną ze wszystkich ocen cząstkowych", S["center_b"]),
             Paragraph("Ogólny poziom spełnienia kryteriów oceny", S["center_b"])]]
    for rng, label, _, _ in OVERALL_ROWS:
        rows.append([Paragraph(x_mark(label == level), S["center_b"]), Paragraph(rng, S["base"]), Paragraph(label, S["base"])])
    E.append(table(rows, [WIDTH * 0.2, WIDTH * 0.45, WIDTH * 0.35], [("BACKGROUND", (0, 0), (-1, 0), GREY)]))
    E.append(Spacer(1, 1.5 * mm))
    E.append(table([[Paragraph("OCENA OKRESOWA W SŁUŻBIE CYWILNEJ", S["cell_b"]), Paragraph("POZYTYWNA" + fn(10), S["base"]),
                     Paragraph(x_mark(result == "pozytywna"), S["center_b"]), Paragraph("NEGATYWNA" + fn(11), S["base"]),
                     Paragraph(x_mark(result == "negatywna"), S["center_b"])]],
                   [WIDTH * 0.4, WIDTH * 0.19, WIDTH * 0.1, WIDTH * 0.19, WIDTH * 0.12], [("BACKGROUND", (0, 0), (0, 0), GREY)]))
    E.append(Paragraph("UZASADNIENIE PRZYZNANEJ OCENY OKRESOWEJ" + fn(12), S["h"]))
    E.append(_empty_box(20 * mm, doc.get("justification"), S))
    E.append(Paragraph("WNIOSKI DOTYCZĄCE INDYWIDUALNEGO PROGRAMU ROZWOJU ZAWODOWEGO" + fn(13), S["h"]))
    E.append(_empty_box(20 * mm, doc.get("development_conclusions"), S))
    prev = doc.get("previous_evaluation") or {}
    E.append(Paragraph("DANE DOTYCZĄCE POPRZEDNIEJ OCENY OKRESOWEJ URZĘDNIKA SŁUŻBY CYWILNEJ", S["h"]))
    E.append(table([[Paragraph("Ocena" + fn(14), S["base"]), Paragraph(t(prev.get("result")), S["base"]),
                     Paragraph("Poziom" + fn(15), S["base"]), Paragraph(t(prev.get("level_label") or prev.get("level")), S["base"]),
                     Paragraph("Data sporządzenia", S["base"]), Paragraph(t(fmt_date(prev.get("date"))) or "(dd.mm.rrrr)", S["center"])]],
                   [WIDTH * 0.1, WIDTH * 0.15, WIDTH * 0.12, WIDTH * 0.25, WIDTH * 0.18, WIDTH * 0.2]))
    E.append(Paragraph("CZY DO OCENY OKRESOWEJ DOŁĄCZONO WNIOSEK O PRZYZNANIE KOLEJNEGO STOPNIA SŁUŻBOWEGO?" + fn(16), S["h"]))
    E.append(table([[Paragraph("TAK", S["base"]), Paragraph(x_mark(print_part3), S["center_b"]),
                     Paragraph("NIE", S["base"]), Paragraph(x_mark(is_official and not print_part3), S["center_b"]),
                     Paragraph("NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)", S["base"]),
                     Paragraph(x_mark(not is_official), S["center_b"])]],
                   [WIDTH * 0.08, WIDTH * 0.08, WIDTH * 0.08, WIDTH * 0.08, WIDTH * 0.58, WIDTH * 0.1]))
    E.append(Paragraph("DANE OCENIAJĄCEGO", S["h"]))
    E.append(person_rows(S, ev, "Stanowisko pracy"))
    done = fmt_date(period.get("to"))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "podpis oceniającego"], [place, done, ""]))
    E.append(Spacer(1, 2 * mm))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka ocenianego", "podpis ocenianego"],
                             [place, fmt_date(doc.get("acquainted_on")), emp.get("full_name", ""), ""],
                             header="Przeprowadzono ze mną rozmowę oceniającą oraz zapoznałem(-łam) się z oceną okresową i wnioskami "
                                    "dotyczącymi indywidualnego programu rozwoju zawodowego."))
    E.append(Spacer(1, 2 * mm))
    E.append(table([[Paragraph("Pouczenie", S["center_b"])],
                    [Paragraph("Zgodnie z art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny okresowej "
                               "służy, w terminie 7 dni od dnia zapoznania się z oceną, sprzeciw do dyrektora generalnego urzędu"
                               + fn(17) + ".", S["base"])]], [WIDTH], [("BACKGROUND", (0, 0), (-1, 0), GREY)]))
    if print_part3:
        E += part3_block(doc, S, emp, ev, place)
    E += footnotes_block(S, form)
    return E, warnings, {"average": avg, "overall_level": level, "result": result, "part3_printed": print_part3}


def part3_block(doc, S, emp, ev, place):
    p3 = doc["part3"]
    first, last = split_name(emp)
    E = [PageBreak(), Paragraph("CZĘŚĆ III", S["part"]),
         Paragraph("Wniosek jest wypełniany i dołączany do arkusza oceny okresowej ocenianego tylko w sytuacji skorzystania "
                   "przez oceniającego z możliwości przewidzianej w art. 89 ust. 1 ustawy z dnia 21 listopada 2008 r. "
                   "o służbie cywilnej." + fn(18), S["center"]),
         Paragraph("DANE URZĘDNIKA SŁUŻBY CYWILNEJ", S["h"])]
    rows = [["Imię", first], ["Nazwisko", last], ["Rok mianowania", p3.get("appointment_year") or "(rrrr)"],
            ["Posiadany stopień służbowy", p3.get("current_grade")],
            ["Data przyznania stopnia służbowego", fmt_date(p3.get("current_grade_date")) or "(dd.mm.rrrr)"]]
    E.append(table([[Paragraph(a, S["base"]), Paragraph(t(b), S["base"])] for a, b in rows], [55 * mm, WIDTH - 55 * mm],
                   [("BACKGROUND", (0, 0), (0, -1), GREY)]))
    E.append(Spacer(1, 2 * mm))
    body = (f"W związku z uzyskaniem przez Panią/Pana<br/><b>{t(emp.get('full_name'))}</b><br/>pozytywnej oceny okresowej, "
            f"na podstawie art. 89 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej wnioskuję o przyznanie "
            f"<b>{t(p3.get('requested_grade') or '……….')}</b> stopnia służbowego.")
    E.append(table([[Paragraph("WNIOSEK O PRZYZNANIE URZĘDNIKOWI SŁUŻBY CYWILNEJ KOLEJNEGO STOPNIA SŁUŻBOWEGO", S["center_b"])],
                    [Paragraph(body, S["base"])], [Paragraph("Umotywowanie wniosku", S["cell_b"])],
                    [Paragraph(t(p3.get("motivation")).replace("\n", "<br/>"), S["base"])]], [WIDTH],
                   [("BACKGROUND", (0, 0), (-1, 0), GREY)]))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka oceniającego", "podpis oceniającego"],
                             [place, fmt_date((doc.get("period") or {}).get("to")), ev.get("full_name", ""), ""]))
    return E


# ---------------------------------------------------------------- pierwsza ocena
def build_first(doc: dict, S) -> tuple:
    emp, ev, head = doc.get("employee") or {}, doc.get("evaluator") or {}, doc.get("unit_head") or {}
    crit = _criteria_by_id(doc)
    missing = [name for cid, name in MANDATORY["first_eval"] if cid not in crit]
    if missing:
        raise InputError(f"Brak elementów oceny: {', '.join(missing)}")
    pts = [_final_points(crit[cid], {3, 5, 7}) for cid, _ in MANDATORY["first_eval"]]
    avg = doc.get("average")
    avg = _average(pts) if avg is None else float(avg)
    exam = doc.get("exam", "nie_dotyczy")
    report_ok = bool(doc.get("report_submitted_on_time"))
    computed = ("pozytywna" if exam in ("tak", "nie_dotyczy") and report_ok and pts.count(3) <= 1 and avg >= 5
                else "negatywna")  # przypis 6 arkusza, § 10 ust. 1 rozp. 2015
    result = doc.get("result") or computed
    warnings = []
    if result != computed:
        warnings.append(f"Wynik w dokumencie ({result}) różni się od warunków z przypisu 6 ({computed})")
    if result == "negatywna" and not (doc.get("justification") or "").strip():
        raise InputError("Negatywna pierwsza ocena wymaga uzasadnienia (przypis 7)")
    conclusions = doc.get("development_conclusions")
    if result != "pozytywna" and conclusions:  # przypis 8: tylko przy pozytywnej
        warnings.append("Wnioski rozwojowe pominięte: dopuszczalne tylko przy pozytywnej pierwszej ocenie (przypis 8)")
        conclusions = None
    place = doc.get("place", "")
    E = [Paragraph(FORM_META["first_eval"]["annex"], S["right"]), Spacer(1, 2 * mm),
         Paragraph("ARKUSZ PIERWSZEJ OCENY W SŁUŻBIE CYWILNEJ", S["title"]), Paragraph("CZĘŚĆ OGÓLNA", S["part"]),
         table([[Paragraph("NAZWA URZĘDU", S["cell_b"]), Paragraph(t(doc.get("office_name")), S["base"])]],
               [55 * mm, WIDTH - 55 * mm], [("BACKGROUND", (0, 0), (0, -1), GREY)]),
         Paragraph("DANE OCENIANEGO", S["h"]),
         person_rows(S, emp, "Stanowisko pracy",
                     [[Paragraph("Data nawiązania stosunku pracy" + fn(1), S["base"]),
                       Paragraph(t(fmt_date(emp.get("employment_start"))) or "(dd.mm.rrrr)", S["base"])]]),
         Paragraph("DANE BEZPOŚREDNIEGO PRZEŁOŻONEGO", S["h"]), person_rows(S, ev, "Stanowisko pracy"),
         Paragraph("DANE KIERUJĄCEGO KOMÓRKĄ ORGANIZACYJNĄ", S["h"]), person_rows(S, head, "Stanowisko pracy"),
         Paragraph("ROZMOWA WSTĘPNA", S["h"])]
    intro = doc.get("first_eval_intro") or {}
    rw, ew = intro.get("report_deadline") or {}, intro.get("evaluation_window") or {}

    def rng(w):
        return f"od {fmt_date(w.get('from')) or '(dd.mm.rrrr)'} – do {fmt_date(w.get('to')) or '(dd.mm.rrrr)'}"
    E.append(table([[Paragraph("Data przeprowadzenia rozmowy wstępnej", S["base"]),
                     Paragraph(t(fmt_date(intro.get("intro_interview_date"))) or "(dd.mm.rrrr)", S["base"])],
                    [Paragraph("Termin wyznaczony na złożenie sprawozdania dotyczącego zadań realizowanych przez ocenianego "
                               "w trakcie przepracowanego okresu", S["base"]), Paragraph(rng(rw), S["base"])],
                    [Paragraph("Okres, w którym powinna zostać dokonana pierwsza ocena w służbie cywilnej", S["base"]),
                     Paragraph(rng(ew), S["base"])]], [WIDTH * 0.6, WIDTH * 0.4], [("BACKGROUND", (0, 0), (0, -1), GREY)]))
    E.append(Spacer(1, 2 * mm))
    d_intro = fmt_date(intro.get("intro_interview_date"))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "podpis bezpośredniego przełożonego"], [place, d_intro, ""],
                             header="Potwierdzamy przeprowadzenie rozmowy wstępnej oraz wyznaczenie terminu na złożenie "
                                    "sprawozdania i zapoznanie z nim ocenianego."))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "podpis ocenianego"], [place, d_intro, ""]))
    E.append(Paragraph("ROZMOWA OCENIAJĄCA", S["h"]))
    d_int = fmt_date(doc.get("interview_date"))
    E.append(table([[Paragraph("Data przeprowadzenia rozmowy oceniającej", S["base"]), Paragraph(t(d_int) or "(dd.mm.rrrr)", S["base"])]],
                   [WIDTH * 0.6, WIDTH * 0.4], [("BACKGROUND", (0, 0), (0, -1), GREY)]))
    E.append(Spacer(1, 2 * mm))
    lab4 = ["miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka bezpośredniego przełożonego", "podpis bezpośredniego przełożonego"]
    E.append(signature_block(S, lab4, [place, d_int, ev.get("full_name", ""), ""],
                             header="Potwierdzamy przeprowadzenie rozmowy oceniającej i omówienie w trakcie tej rozmowy wszystkich "
                                    "wymaganych zagadnień" + fn(2) + "."))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka ocenianego", "podpis ocenianego"],
                             [place, d_int, emp.get("full_name", ""), ""]))
    E.append(Paragraph("OCENA POSTAWY OCENIANEGO, JEGO ZAANGAŻOWANIA I POSTĘPÓW W PRACY, RELACJI ZE WSPÓŁPRACOWNIKAMI ORAZ "
                       "TERMINOWOŚCI WYKONYWANIA ZADAŃ", S["h"]))
    rows = [[Paragraph("ELEMENTY OCENY" + fn(3), S["center_b"]),
             Paragraph("OCENA CZĄSTKOWA (należy wstawić znak „X” w odpowiednie pole)", S["center_b"]), "", ""],
            [""] + [Paragraph(lbl, S["label"]) for _, lbl, _ in FIRST_SCALE],
            [""] + [Paragraph(p, S["label"]) for _, _, p in FIRST_SCALE]]
    for (cid, name), p in zip(MANDATORY["first_eval"], pts):
        rows.append([Paragraph(name, S["base"])] + [Paragraph(x_mark(p == v), S["center_b"]) for v, _, _ in FIRST_SCALE])
    rows.append([Paragraph("OCENA ŁĄCZNA" + fn(4), S["cell_b"]), Paragraph(fmt_num(avg), S["center_b"]), "", ""])
    last = len(rows) - 1
    E.append(table(rows, [WIDTH * 0.4] + [WIDTH * 0.2] * 3,
                   [("SPAN", (1, 0), (3, 0)), ("SPAN", (0, 0), (0, 2)), ("SPAN", (1, last), (3, last)),
                    ("BACKGROUND", (0, 0), (-1, 2), GREY)]))
    E.append(Paragraph("PIERWSZA OCENA W SŁUŻBIE CYWILNEJ", S["h"]))
    E.append(table([[Paragraph("OCENIANY ZALICZYŁ EGZAMIN ZE SŁUŻBY PRZYGOTOWAWCZEJ (należy wstawić znak „X” w odpowiednie pole)",
                               S["cell_b"]), "", "", "", "", ""],
                    [Paragraph("TAK", S["base"]), Paragraph(x_mark(exam == "tak"), S["center_b"]), Paragraph("NIE", S["base"]),
                     Paragraph(x_mark(exam == "nie"), S["center_b"]), Paragraph("NIE DOTYCZY" + fn(5), S["base"]),
                     Paragraph(x_mark(exam == "nie_dotyczy"), S["center_b"])]],
                   [WIDTH * 0.14, WIDTH * 0.12, WIDTH * 0.14, WIDTH * 0.12, WIDTH * 0.3, WIDTH * 0.18],
                   [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), GREY)]))
    E.append(Spacer(1, 1.5 * mm))
    E.append(table([[Paragraph("SPRAWOZDANIE ZOSTAŁO ZŁOŻONE W WYZNACZONYM TERMINIE (należy wstawić znak „X” w odpowiednie pole)",
                               S["cell_b"]), "", "", ""],
                    [Paragraph("TAK", S["base"]), Paragraph(x_mark(report_ok), S["center_b"]), Paragraph("NIE", S["base"]),
                     Paragraph(x_mark(not report_ok), S["center_b"])]], [WIDTH * 0.25] * 4,
                   [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), GREY)]))
    E.append(Spacer(1, 1.5 * mm))
    E.append(table([[Paragraph("PIERWSZA OCENA W SŁUŻBIE CYWILNEJ (należy wstawić znak „X” w odpowiednie pole)", S["cell_b"]), "", "", ""],
                    [Paragraph("POZYTYWNA" + fn(6), S["base"]), Paragraph(x_mark(result == "pozytywna"), S["center_b"]),
                     Paragraph("NEGATYWNA", S["base"]), Paragraph(x_mark(result == "negatywna"), S["center_b"])]],
                   [WIDTH * 0.25] * 4, [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), GREY)]))
    E.append(Spacer(1, 1.5 * mm))
    E.append(table([[Paragraph("UZASADNIENIE PRZYZNANEJ OCENY" + fn(7), S["cell_b"])]], [WIDTH], [("BACKGROUND", (0, 0), (-1, -1), GREY)]))
    E.append(_empty_box(20 * mm, doc.get("justification"), S))
    E.append(Paragraph("WNIOSKI DOTYCZĄCE ROZWOJU ZAWODOWEGO OCENIANEGO", S["h"]))
    E.append(table([[Paragraph("WNIOSKI DOTYCZĄCE ROZWOJU ZAWODOWEGO OCENIANEGO" + fn(8), S["cell_b"])]], [WIDTH],
                   [("BACKGROUND", (0, 0), (-1, -1), GREY)]))
    E.append(_empty_box(18 * mm, conclusions, S))
    E.append(Spacer(1, 2 * mm))
    d_done = fmt_date((doc.get("period") or {}).get("to"))
    E.append(signature_block(S, lab4, [place, d_done, ev.get("full_name", ""), ""],
                             header="<b>POTWIERDZENIE DOKONANIA PIERWSZEJ OCENY W SŁUŻBIE CYWILNEJ</b>"))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka kierującego komórką organizacyjną",
                                 "podpis kierującego komórką organizacyjną"], [place, d_done, head.get("full_name", ""), ""]))
    E.append(Spacer(1, 2 * mm))
    E.append(signature_block(S, ["miejscowość", "data (dd.mm.rrrr)", "imię i nazwisko lub pieczątka ocenianego", "podpis ocenianego"],
                             [place, fmt_date(doc.get("acquainted_on")), emp.get("full_name", ""), ""],
                             header="Zapoznałam(-łem) się z pierwszą oceną w służbie cywilnej."))
    E += footnotes_block(S, "first_eval")
    return E, warnings, {"average": avg, "result": result, "computed_result": computed,
                         "development_conclusions_printed": bool(conclusions)}


# ---------------------------------------------------------------- karta przygotowania
LEVEL_LABELS = {1: "znacznie poniżej oczekiwań", 2: "poniżej oczekiwań", 3: "na poziomie oczekiwań",
                4: "powyżej oczekiwań", 5: "znacznie powyżej oczekiwań"}
DEFAULT_QUESTIONS = {
    "periodic": [  # § 10 rozp. 2016 – zakres rozmowy oceniającej
        "Które z głównych obowiązków w okresie oceny uważa Pani/Pan za najważniejsze i jak je Pani/Pan realizowała/realizował?",
        "Jak ocenia Pani/Pan realizację celów ustalonych na początku okresu (jeżeli zostały wyznaczone)?",
        "W jakim kierunku chce się Pani/Pan rozwijać i jakiego wsparcia potrzebuje w podnoszeniu kwalifikacji?"],
    "first": [  # § 7–8 rozp. 2015 – zakres rozmowy oceniającej
        "Co uważa Pani/Pan za najważniejsze osiągnięcia opisane w sprawozdaniu?",
        "Z jakimi problemami spotkała się Pani/spotkał się Pan i jak je rozwiązała/rozwiązał?",
        "Jakie kierunki dalszego rozwoju zawodowego widzi Pani/Pan dla siebie?"],
}


def build_karta(doc: dict, S) -> tuple:
    emp = doc.get("employee") or {}
    process = "first" if doc.get("form") == "first_eval" else "periodic"
    form_label = {"periodic_b": "ocena okresowa – arkusz B", "periodic_c": "ocena okresowa – arkusz C",
                  "first_eval": "pierwsza ocena w służbie cywilnej"}.get(doc.get("form"), doc.get("form", ""))
    period = doc.get("period") or {}
    E = [Paragraph(KARTA_HEADER.upper(), S["banner"]), Spacer(1, 2 * mm),
         Paragraph("KARTA PRZYGOTOWANIA DO ROZMOWY", S["title"]), Spacer(1, 2 * mm),
         table([[Paragraph("Oceniany", S["cell_b"]), Paragraph(t(emp.get("full_name")), S["base"])],
                [Paragraph("Stanowisko / komórka", S["cell_b"]), Paragraph(t(f"{emp.get('position', '')} – {emp.get('unit', '')}"), S["base"])],
                [Paragraph("Rodzaj oceny", S["cell_b"]), Paragraph(t(form_label), S["base"])],
                [Paragraph("Okres", S["cell_b"]), Paragraph(t(f"{fmt_date(period.get('from'))} – {fmt_date(period.get('to'))}"), S["base"])]],
               [45 * mm, WIDTH - 45 * mm], [("BACKGROUND", (0, 0), (0, -1), GREY)])]
    for c in doc.get("criteria", []):
        E.append(Paragraph(t(c.get("name") or c.get("id")), S["h"]))
        sug = c.get("suggestion") or {}
        if sug:
            E.append(Paragraph(t(f"Sugestia Kompasu: {sug.get('level_label', '')} ({sug.get('points', '')} pkt; średnia wskaźników "
                                 f"{sug.get('average', '')}). Decyzja przełożonego: "
                                 f"{c.get('final_points') if c.get('final_points') is not None else 'jeszcze nie podjęta'}."), S["small"]))
        rows = [[Paragraph("Wskaźnik", S["cell_b"]), Paragraph("Wybrany poziom", S["cell_b"]), Paragraph("Przykład S-D-R (sytuacja – działanie – rezultat)", S["cell_b"])]]
        for r in c.get("indicator_ratings", []):
            lvl = "brak podstaw do oceny" if r.get("no_basis") else LEVEL_LABELS.get(r.get("level"), "—")
            rows.append([Paragraph(t(r.get("indicator_text") or r.get("text") or r.get("indicator_id")), S["small"]),
                         Paragraph(t(lvl), S["small"]),
                         Paragraph(t(r.get("sdr_note") or "– brak przykładu: dopytaj w rozmowie –"), S["small"])])
        E.append(table(rows, [WIDTH * 0.38, WIDTH * 0.17, WIDTH * 0.45], [("BACKGROUND", (0, 0), (-1, 0), GREY), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    questions = list(doc.get("interview_questions") or [])
    for c in doc.get("criteria", []):
        for r in c.get("indicator_ratings", []):
            if r.get("no_basis") or not r.get("sdr_note"):
                questions.append(f"[{c.get('name')}] Proszę podać przykład sytuacji z okresu oceny dotyczącej wskaźnika: "
                                 f"„{r.get('indicator_text') or r.get('text') or r.get('indicator_id')}”.")
    questions += DEFAULT_QUESTIONS[process]
    E.append(Paragraph("PYTANIA NA ROZMOWĘ", S["h"]))
    for i, q in enumerate(questions, 1):
        E.append(Paragraph(f"{i}. {t(q)}", S["base"]))
    E.append(Spacer(1, 3 * mm))
    E.append(Paragraph("Karta jest notatką roboczą przełożonego. Nie jest częścią arkusza oceny, nie trafia do akt osobowych "
                       "ani do panelu HR. Ostateczne oceny cząstkowe przełożony wpisuje w arkuszu.", S["small"]))
    return E, [], {"questions": len(questions)}


# ---------------------------------------------------------------- API
def render(doc: dict, output: Path, kind: str = "arkusz", fonts_dir: Path = FONTS_DIR) -> dict:
    register_fonts(fonts_dir)
    S = styles()
    form = doc.get("form")
    if kind == "karta":
        elements, warnings, info = build_karta(doc, S)
        label = KARTA_HEADER
    elif form in ("periodic_b", "periodic_c"):
        elements, warnings, info = build_periodic(doc, S)
        label = f"Arkusz {form[-1].upper()} – ocena okresowa"
    elif form == "first_eval":
        elements, warnings, info = build_first(doc, S)
        label = "Arkusz pierwszej oceny w służbie cywilnej"
    else:
        raise InputError(f"Nieznany formularz: {form!r} (periodic_b|periodic_c|first_eval)")
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=label, author="Kompas Kompetencji",
                            subject=(doc.get("employee") or {}).get("full_name", ""))
    on_page = _on_page(label)
    if kind == "karta":
        def on_page(canvas, d, _base=_on_page(label)):
            _base(canvas, d)
            canvas.saveState()
            canvas.setFont("DejaVu-Bold", 7.5)
            canvas.setFillColor(colors.HexColor("#8a1c1c"))
            canvas.drawString(15 * mm, A4[1] - 9 * mm, KARTA_HEADER)
            canvas.restoreState()
    pdf.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return {"output": str(output), "kind": kind, "form": form, "warnings": warnings, **info}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generator PDF arkuszy oceny i karty przygotowania do rozmowy")
    ap.add_argument("--input", required=True, help="dokument oceny JSON (kontrakt C3)")
    ap.add_argument("--output", required=True, help="plik PDF")
    ap.add_argument("--kind", choices=["arkusz", "karta"], default="arkusz")
    ap.add_argument("--fonts-dir", default=str(FONTS_DIR))
    args = ap.parse_args(argv)
    doc = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        info = render(doc, Path(args.output), args.kind, Path(args.fonts_dir))
    except InputError as exc:
        print(f"BŁĄD DANYCH: {exc}", file=sys.stderr)
        return 2
    for w in info["warnings"]:
        print(f"OSTRZEŻENIE: {w}", file=sys.stderr)
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
