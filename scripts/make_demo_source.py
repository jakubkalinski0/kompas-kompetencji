"""Generuje fikcyjne zarządzenie dyrektora generalnego (PDF) do pokazania wgrywania źródeł do bazy wiedzy asystenta.

Dokument jest wymyślony na potrzeby demo: opisuje wewnętrzny obieg dokumentów w urzędzie i nie zmienia terminów
z ustawy ani rozporządzeń. Zawiera fikcyjny e-mail i telefon, żeby było widać maskowanie danych przy wgrywaniu.

Użycie:  python scripts/make_demo_source.py   →  app/static/demo/zarzadzenie_7_2026_DEMO.pdf
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / ".claude" / "skills" / "kompas-dokumenty-i-terminy" / "assets" / "fonts"
OUT = ROOT / "app" / "static" / "demo" / "zarzadzenie_7_2026_DEMO.pdf"

TITLE = ("Zarządzenie nr 7/2026 Dyrektora Generalnego Urzędu Demonstracyjnego z dnia 2 listopada 2026 r. "
         "w sprawie organizacji ocen okresowych w urzędzie")
PARAGRAPHS = [
    "§ 1. Zarządzenie określa wewnętrzny harmonogram i obieg dokumentów w procesie ocen okresowych członków korpusu "
    "służby cywilnej zatrudnionych w Urzędzie Demonstracyjnym. Zarządzenie nie zmienia terminów określonych w ustawie "
    "o służbie cywilnej ani w rozporządzeniu w sprawie ocen okresowych.",
    "§ 2. 1. Komórka do spraw kadr przekazuje oceniającym w styczniu każdego roku wykaz osób, którym w danym roku "
    "upływa termin sporządzenia oceny okresowej. 2. Komórka do spraw kadr przypomina oceniającemu o zbliżającym się "
    "terminie oceny na 30 dni przed jego upływem.",
    "§ 3. Oceniający przekazuje oryginał podpisanego arkusza oceny okresowej do komórki do spraw kadr w terminie "
    "3 dni roboczych od dnia zapoznania ocenianego z oceną.",
    "§ 4. Wnioski dotyczące indywidualnego programu rozwoju zawodowego oceniający przekazuje do komórki do spraw kadr "
    "w terminie 30 dni od dnia sporządzenia oceny, w celu zaplanowania szkoleń w budżecie szkoleniowym urzędu.",
    "§ 5. Oceniający może przygotować ocenę w aplikacji Kompas Kompetencji. Sugestie aplikacji mają charakter "
    "pomocniczy; poziom spełniania kryteriów i wynik oceny ustala oceniający.",
    "§ 6. W sprawach dotyczących ocen okresowych oceniający kontaktują się z komórką do spraw kadr: "
    "kadry-oceny@urzad-demo.example, tel. 22 000 00 00.",
    "§ 7. Zarządzenie wchodzi w życie z dniem podpisania.",
]


def main() -> None:
    pdfmetrics.registerFont(TTFont("DejaVu", str(FONTS / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONTS / "DejaVuSans-Bold.ttf")))
    head = ParagraphStyle("h", fontName="DejaVu-Bold", fontSize=12, leading=16, spaceAfter=6)
    note = ParagraphStyle("n", fontName="DejaVu", fontSize=8.5, leading=11, textColor="#7f1d1d", spaceAfter=10)
    body = ParagraphStyle("b", fontName="DejaVu", fontSize=10.5, leading=15, spaceAfter=8)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm,
                            bottomMargin=20 * mm, title=TITLE, author="Kompas Kompetencji – dokument fikcyjny (demo)")
    story = [Paragraph("DOKUMENT FIKCYJNY – PRZYKŁAD DO DEMO KOMPASU KOMPETENCJI", note), Paragraph(TITLE, head),
             Spacer(1, 4)]
    story += [Paragraph(p, body) for p in PARAGRAPHS]
    doc.build(story)
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
