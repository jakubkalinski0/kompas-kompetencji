---
name: kompas-dane-i-zrodla
description: Buduje deterministycznie dane Kompasu Kompetencji z materiałów Partnera (MC) jednym skryptem build_data.py — model kompetencji (14 kompetencji, 49 wskaźników, 5 poziomów), struktura arkuszy B/C/pierwszej oceny z przypisami dosłownie, załącznik nr 1 z kontrolą zgodności, baza wiedzy asystenta (kb_chunks.jsonl z cytowaniem) i OSP w JSON. Użyj, gdy zespół mówi „zbuduj dane”, „przebuduj bazę wiedzy”, „skąd jest ten cytat”, „dodaj źródło do KB”, „sprawdź model z rozporządzeniem”.
---

# kompas-dane-i-zrodla

Jeden skrypt `scripts/build_data.py` zamienia oryginalne materiały Partnera (katalog `materialy/`) w pliki JSON/JSONL, z których korzystają pozostałe skille: silnik oceny (`kompas-model-i-silnik-oceny`), dokumenty PDF (`kompas-dokumenty-i-terminy`), asystent AI (`kompas-asystent-ai`, `kompas-ewaluacja`) i analiza OSP (`kompas-analiza-osp`). Kształt wyjścia = kontrakt C1 (`references/output_schema.md`).

## Kiedy używać
- Na starcie w repo rozwiązania (dane nie są commitowane albo zespół chce je odtworzyć z oryginałów).
- Po każdej zmianie materiałów (nowa wersja modelu, nowy plik ustawy w `assets/ustawa_sc/`, Q&A w `assets/kprm_qa/`).
- Gdy trzeba sprawdzić, skąd pochodzi fragment bazy wiedzy (`citation`, `source_file`, `page_from`).

## Kiedy NIE używać
- Do liczenia sugerowanego poziomu i reguł pozytywna/negatywna — to `kompas-model-i-silnik-oceny` (czyta `competency_model.json` i `forms/*.json`).
- Do odpowiadania na pytania o przepisy — to `kompas-asystent-ai` (czyta `kb/kb_chunks.jsonl`). Fakty prawne i ich interpretacja: `research/02_proces_i_przepisy.md` (jedna wersja prawdy, nie kopiuj jej tutaj).
- Do parsowania pojedynczego OSP wgranego przez użytkownika — to `kompas-analiza-osp/scripts/osp_parser.py`.

## Uruchomienie (repo rozwiązania)
```bash
python .claude/skills/kompas-dane-i-zrodla/scripts/build_data.py --input materialy --output data/processed
python -m pytest .claude/skills/kompas-dane-i-zrodla/tests --materials materialy -q
```
Wymagania: Python ≥ 3.10 (tylko biblioteka standardowa) i program `pdftotext` z popplera (Windows: jest w Git for Windows; Linux: `apt install poppler-utils`; macOS: `brew install poppler`). Gdy `pdftotext` nie istnieje, skrypt kończy się kodem 2 i komunikatem `BLAD: Brak programu 'pdftotext'…`.

Opcje: `--ustawa <plik.txt>` (domyślnie `assets/ustawa_sc/ustawa_o_sluzbie_cywilnej.txt`), `--allow-model-change` (nie przerywaj, gdy model ma inną liczbę kompetencji/wskaźników niż 14/49 — np. Partner przyśle nową wersję).

Zmienne środowiskowe (`.env.example`): `KOMPAS_MATERIALY` (katalog materiałów dla testów), `KOMPAS_USTAWA_TXT` (inny plik ustawy), `PDFTOTEXT` (pełna ścieżka do pdftotext), `KOMPAS_OSP_PARSER_DIR` (inny katalog z `osp_parser.py`). Brak kluczy i sekretów.

## Co robi (kroki)
1. **Wyszukuje pliki wzorcami nazw** (rekurencyjnie, bez polskich znaków, odporne na sufiksy „(2)”, duplikaty o tej samej treści usuwane po sha256). Dwa PDF „Rozporządzenie o ocenach okresowych z 2016 r.” rozróżnia po liczbie stron: dłuższy = pełny akt, ≤ 5 stron = wyciąg z załącznikiem nr 1.
2. **Model kompetencji** z `Model_kompetencji.xlsx` (ZIP + XML): nazwy z komórki A1 (nazwy arkuszy są ucięte do 31 znaków, jedna ma literówkę „SYTUACJIACH”), znormalizowane do brzmienia kryteriów z zał. nr 1 rozp. 2016; `id` = ASCII snake_case. Asercje: liczby wskaźników zgodne z kolumną „Liczba wskaźników” arkusza zbiorczego i z nagłówkiem „14 kompetencji • 49 wskaźników • 5 poziomów” (inaczej kod 2).
3. **Arkusze** B, C i pierwszej oceny (DOCX): części, sekcje, tabele z polami, kryteria obowiązkowe, skala punktowa, przedziały ogólnego poziomu, **przypisy dosłownie** z `word/footnotes.xml` z numerami, kotwicą (pole, przy którym stoi odnośnik), częścią arkusza i rolą (`result_positive`, `result_negative`, `part3`, `justification`, `exam_not_applicable`…). Numeracja list w przypisach odtwarzana z `numbering.xml`.
4. **Załącznik nr 1** (wykaz kryteriów) z PDF w trybie `-layout` + kontrola: każdy z 49 wskaźników modelu musi wystąpić w opisie właściwego kryterium (normalizacja białych znaków, myślników, „/ ”). Rozbieżności → `build_report.json` i `annex1_criteria.json.model_check` (nie poprawiamy modelu).
5. **Baza wiedzy** `kb/kb_chunks.jsonl`: rozporządzenia 2016 i 2015 per paragraf (`§ N`, a długie paragrafy per ustęp `§ N ust. M`), podstawa prawna i przypis aktu; strony ze wzorami arkuszy (artefakt „UUZZAASSAADDNNIIEENNIIEE”) pomijane i raportowane; poradniki KPRM per rozdział ze spisu treści (300–1200 słów, `heading_path`, strony PDF); model kompetencji (chunk na kompetencję + instrukcja); przypisy arkuszy (`doc_type: arkusz`); załączniki nr 1 obu rozporządzeń (chunk na kryterium/element; opisy elementów pierwszej oceny trafiają też do `forms/first_eval.json.element_descriptions`); ustawa o służbie cywilnej per artykuł (jeśli jest plik z C2); Q&A KPRM z `assets/kprm_qa/*.json` (jeśli są).
6. **OSP**: rozpakowuje `OSP_word.zip` do katalogu tymczasowego i woła `parse_osp_docx` z `kompas-analiza-osp` (kontrakt C4). Brak parsera = ostrzeżenie, nie błąd.
7. **`build_report.json`**: liczniki, kontrole, ostrzeżenia, sha256 każdego wejścia. Bez znaczników czasu — dwa uruchomienia dają identyczne bajty (test `test_deterministic`).

## Przykład (prawdziwe uruchomienie 2026-11-21, szczegóły: `references/test-run.md`)
Wejście: katalog materiałów Partnera (11 plików). Polecenie jak wyżej. Wyjście na stdout:
```
{"counts": {"competencies": 14, "indicators": 49, "levels": 5, "footnotes_periodic_b": 18, "footnotes_periodic_c": 18,
 "footnotes_first_eval": 8, "annex1_criteria": 14, "annex1_description_items": 49, "ustawa_articles": 174, ...,
 "kprm_qa_items": 31, "kb_chunks": 366, ..., "osp_files": 3}, "warnings": 4}
```
Fragment `competency_model.json` (treść wskaźnika i opisy poziomów zastąpione opisem pola – model kompetencji to materiał MC):
```json
{"id": "rzetelnosc", "name": "Rzetelność", "name_in_model": "RZETELNOŚĆ", "sheet": "RZETELNOŚĆ", "lp": 1,
 "mandatory_in": ["periodic_c", "first_eval"],
 "indicators": [..., {"id": "rzetelnosc.2", "text": "<treść wskaźnika z arkusza modelu>",
   "levels": {"1": "<opis zachowania na poziomie 1>", "...": "...",
              "3": "<opis zachowania na poziomie 3>"}}]}
```
Fragment `kb/kb_chunks.jsonl`:
```json
{"id": "rozp2015:par10", "source_id": "rozp2015", "doc_type": "rozporzadzenie", "unit": "§ 10",
 "citation": "§ 10 rozporządzenia Prezesa Rady Ministrów z 23 lipca 2015 r. (Dz. U. poz. 1144)",
 "heading_path": ["rozp. 2015 (pierwsza ocena)", "§ 10"], "page_from": 3, "page_to": 3, "process": ["first"],
 "text": "§ 10. 1. Warunkiem przyznania pozytywnej pierwszej oceny jest: 1) zaliczenie egzaminu ze służby przygotowawczej; …",
 "source_file": "Pierwsza ocena w służbie cywilnej/Rozporządzenie o pierwszej ocenie z 2015 r. (1).pdf"}
```

## Pliki wyjściowe (szczegóły pól: `references/output_schema.md`)
| Plik | Zawartość | Kto czyta |
|---|---|---|
| `competency_model.json` | skala 5 poziomów, instrukcja (wiersze 4–6), 14 kompetencji × wskaźniki × opisy poziomów, `mandatory_in` | silnik oceny, UI |
| `forms/periodic_b.json`, `periodic_c.json`, `first_eval.json` | części/sekcje/pola, `mandatory_criteria`, `scale` (punkty), `overall_levels`, `footnotes[]` | silnik, generator PDF |
| `annex1_criteria.json` | 14 kryteriów zał. nr 1 z opisami + `model_check` | kontrola zgodności, UI „wybór kryteriów dodatkowych” |
| `kb/kb_chunks.jsonl`, `kb/sources.json` | 366 fragmentów z cytowaniem; lista źródeł z sha256/URL | asystent AI, ewaluacja |
| `osp/<slug>.json` | 3 OSP przetworzone parserem C4 | analiza OSP, demo |
| `build_report.json` | liczniki, kontrole, ostrzeżenia, sha256 wejść | CI, zespół |

## Pułapki (sprawdzone na materiałach)
- `pdftotext` bez `-enc UTF-8` psuje polskie znaki — skrypt zawsze dodaje tę opcję.
- Strony wzorów arkuszy w PDF rozporządzenia 2016 (s. 10, 12, 16) dają zdublowane znaki („WWZZÓÓRR”) — pomijamy całe załączniki 2–4; ich treść (przypisy) bierzemy z DOCX.
- Załącznik nr 1 rozp. 2016, s. 3 (kryteria 11–14), i załącznik nr 1 rozp. 2015, s. 4 (5 elementów): w PDF nazwy kryteriów nie są na wysokości swoich opisów. Przydział opisów ustalono przez zgodność całej sekwencji 15 punktów z modelem (`assignment: "sequence_match_with_model"`) — to nie jest niezależna weryfikacja granic między kryteriami 11–14 (ostrzeżenie w raporcie).
- Ustawa (t.j. Dz. U. 2026 poz. 590) zawiera art. 28, 29, 29a, 31, 32, 33 w dwóch wersjach (przed i po zmianie) — osobne chunki `ustawa_sc:art28:v1`/`:v2`, adnotacja w `unit`. Linie `[przypis]` są usuwane z tekstu artykułów.
- Poradnik „Pierwsza ocena”: pozycji spisu treści „6.6 Czynności po zakończeniu pierwszej oceny” nie ma w tekście PDF (ostrzeżenie; treść trafia do sąsiedniego rozdziału).
- Numery stron w KB = numery stron PDF (w poradnikach równe numerom drukowanym; ustawa z pliku TXT nie ma stron → `null`).
- Materiały są z 2015–2016 r.; aktualność względem dzisiejszego stanu prawnego — `research/02_proces_i_przepisy.md`.

## Testy
`tests/test_build_data.py` (18 testów; 15 wymaga materiałów i jest pomijanych bez `--materials`/`KOMPAS_MATERIALY`): liczby 14/49/5, id i nazwy, poziomy, kryteria obowiązkowe B/C/pierwszej oceny, przypisy dosłownie (10, 11, 12, 18, pierwsza ocena 5–6), skale punktowe, opisy 5 elementów pierwszej oceny (20 punktów), zał. nr 1 bez rozbieżności, brak zdublowanych znaków w KB, chunki § 11 rozp. 2016 i § 9/§ 10 rozp. 2015, rozmiary chunków poradników, artykuły ustawy 38/81/83/89, determinizm, czytelny błąd bez pdftotext.

## Zależności i licencje
- Python stdlib (PSF). `pdftotext` z popplera (GPL-2.0/GPL-3.0) wywoływany jako **osobny program** przez `subprocess` — nie linkujemy ani nie dystrybuujemy popplera w kodzie rozwiązania; przy wdrożeniu w MC można go zastąpić biblioteką permisywną (np. `pypdf`, BSD-3) — DO DECYZJI zespołu.
- `pytest` (MIT) tylko do testów.
- Materiały Partnera (model kompetencji MC, OSP MC) mogą nie być publiczne — o ich publikacji w repo rozwiązania decyduje zespół po rozmowie z mentorem (patrz `research/03_materialy_i_dane.md`). Akty prawne nie są przedmiotem prawa autorskiego (art. 4 pkt 2 ustawy o prawie autorskim).

Powiązane wspólne skille: `hn-dane-od-partnera` (profil nieznanych danych), `hn-llm-w-produkcie` (cytowanie źródeł w odpowiedziach LLM), `hn-zgloszenie` (ujawnienie materiałów i licencji).
