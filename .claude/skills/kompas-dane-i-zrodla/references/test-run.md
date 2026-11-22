# Test run – build_data.py (2026-11-21, Windows 10, Python 3.13.1, pdftotext z Git for Windows)

Katalog roboczy: `prep/kompas_kompetencji` (w repo rozwiązania: korzeń repo, `--input materialy`).

## 1. Budowa danych
```bash
.venv/Scripts/python -X utf8 .claude/skills/kompas-dane-i-zrodla/scripts/build_data.py \
  --input "d:/GitHub/setup/KompasKompetencji/HackNation" --output data-samples/processed
```
Kod wyjścia 0. Stderr (3 ostrzeżenia, opisane w SKILL.md → Pułapki):
```
OSTRZEZENIE: Zalacznik nr 1, s. 3: uklad PDF nie wiaze nazw kryteriow z opisami (Współpraca, Wystąpienia publiczne, Zarządzanie ludźmi, Zarządzanie strategiczne); granice opisow ustalono przez zgodnosc sekwencji punktow z modelem - nie jest to niezalezna weryfikacja przydzialu.
OSTRZEZENIE: ustawa: artykuly w kilku wersjach w tekscie jednolitym (np. przed i po zmianie): art. 28, art. 29, art. 29a, art. 31, art. 32, art. 33 - zapisane osobno z sufiksem id ':vN' i adnotacja w 'unit'.
OSTRZEZENIE: poradnik_pierwsza_2016: nie znaleziono w tekscie naglowka ze spisu tresci: 6.6 Czynności po zakończeniu pierwszej oceny
```
Stdout (skrócone):
```
{"counts": {"competencies": 14, "indicators": 49, "levels": 5, "footnotes_periodic_b": 18, "footnotes_periodic_c": 18,
 "footnotes_first_eval": 8, "annex1_criteria": 14, "annex1_description_items": 49, "ustawa_articles": 174,
 "ustawa_article_versions": 180, "rozp2016_paragraphs": 14, "rozp2015_paragraphs": 14,
 "poradnik_okresowa_2016_toc_entries": 27, "poradnik_okresowa_2016_headings_found": 27,
 "poradnik_pierwsza_2016_toc_entries": 29, "poradnik_pierwsza_2016_headings_found": 28, "kprm_qa_items": 31,
 "kb_chunks": 361, "kb_chunks_by_source": {"kprm_qa_oceny/kprm_qa": 31, "model_kompetencji/model_kompetencji": 15,
 "poradnik_okresowa_2016/poradnik": 23, "poradnik_pierwsza_2016/poradnik": 19, "rozp2015/arkusz": 8,
 "rozp2015/rozporzadzenie": 15, "rozp2016/arkusz": 36, "rozp2016/rozporzadzenie": 34, "ustawa_sc/ustawa": 180},
 "osp_files": 3}, "warnings": 3}
```
Kontrole w `build_report.json`: `model_vs_annex1 = {"checked": 49, "mismatches": 0, "annex_extra": 0}`, `rozp2016_pages_with_doubled_chars = [10, 12, 16]` (pominięte), `kb_doubled_char_chunks = []`.

## 2. Determinizm
```bash
.venv/Scripts/python -X utf8 .claude/skills/kompas-dane-i-zrodla/scripts/build_data.py --input "<MAT>" --output "<scratch>/run2"
diff -r data-samples/processed "<scratch>/run2" && echo IDENTICAL
```
Wynik: `IDENTICAL` (to samo sprawdza test `test_deterministic`).

## 3. Testy
```bash
.venv/Scripts/python -X utf8 -m pytest .claude/skills/kompas-dane-i-zrodla/tests --materials "d:/GitHub/setup/KompasKompetencji/HackNation" -q -p no:cacheprovider
```
Wynik: `17 passed in 3.87s`.

Bez materiałów (np. CI bez `materialy/`):
```bash
.venv/Scripts/python -X utf8 -m pytest .claude/skills/kompas-dane-i-zrodla/tests -q -p no:cacheprovider
```
Wynik: `3 passed, 14 skipped in 0.09s`.

## 4. Brak pdftotext
```bash
PDFTOTEXT=/nonexistent/pdftotext .venv/Scripts/python -X utf8 .claude/skills/kompas-dane-i-zrodla/scripts/build_data.py --input "<MAT>" --output "<scratch>/nopdf"
```
Wynik: kod 2, `BLAD: Brak programu 'pdftotext' (poppler). Zainstaluj poppler-utils (Linux: apt install poppler-utils; macOS: brew install poppler; Windows: Git for Windows zawiera pdftotext w usr/bin) albo wskaz sciezke w zmiennej PDFTOTEXT.`
