# Schemat wyjścia build_data.py (kontrakt C1)

Wszystkie pliki: UTF-8, JSON z wcięciem 2 (`kb_chunks.jsonl` – jeden obiekt na linię), końce linii `\n`, kolejność deterministyczna, bez znaczników czasu.

## competency_model.json
| Pole | Typ | Opis |
|---|---|---|
| `source.file`, `source.sha256` | str | ścieżka względna w katalogu materiałów, skrót pliku XLSX |
| `summary_line` | str | liczba kompetencji, wskaźników i poziomów (wiersz 3 arkusza zbiorczego) |
| `scale[]` | `{level 1–5, key, label}` | `znacznie_ponizej`, `ponizej`, `na_poziomie`, `powyzej`, `znacznie_powyzej`; etykiety z nagłówków B–F |
| `instructions[]` | str | wiersze 4–6 arkusza zbiorczego (dobór wskaźników, przykłady SDR, brak podstaw do oceny) |
| `competencies[]` | obiekt | kolejność wg kolumny „Lp.” arkusza zbiorczego |
| `.id` | str | ASCII snake_case nazwy kryterium z rozporządzenia, np. `orientacja_na_klienta_interesanta` |
| `.name` | str | brzmienie kryterium (wielka litera tylko na początku), np. „Organizacja pracy i orientacja na osiąganie celów” |
| `.name_in_model`, `.sheet`, `.lp` | str/int | A1 arkusza, nazwa arkusza (ucięta do 31 znaków), Lp. z arkusza zbiorczego |
| `.mandatory_in[]` | str | arkusze, w których kryterium jest obowiązkowe: `periodic_b`, `periodic_c`, `first_eval` |
| `.indicators[]` | `{id, text, levels}` | `id` = `<id kompetencji>.<n>` (n od 1, kolejność z arkusza); `levels` = `{"1": …, "5": …}` |

## forms/<form>.json (`periodic_b`, `periodic_c`, `first_eval`)
| Pole | Opis |
|---|---|
| `form`, `source` | identyfikator arkusza, plik DOCX + sha256 |
| `annex`, `title_lines[]` | „Załącznik nr 3”, linie tytułu (bez odnośników) |
| `parts[]` | `{id: part1/part2/part3/general, heading, notes[], sections[]}`; sekcja = `{heading, footnote_refs[], fields[]}`; `fields[].rows` = wiersze tabeli (komórki tekstowe, odnośniki usunięte) |
| `mandatory_criteria[]` | `{id, name, name_in_form}`; dla `first_eval` to elementy oceny |
| `criteria_kind` | `mandatory` albo `first_eval_element` (pole `kind` w C3) |
| `additional_criteria_max` | 3 (B/C, z nagłówka „nie więcej niż 3”), `null` dla pierwszej oceny |
| `scale[]` | `{level, key, label, points}`: B/C 1/3/5/7/9 pkt (poziomy 1–5), pierwsza ocena 3/5/7 pkt (poziomy 2–4) |
| `overall_levels[]` | B/C: `{min, min_inclusive, max, max_inclusive, key, label, text}` np. `(2, false, 4, true, "ponizej")` = „powyżej 2 punktów do 4 punktów” |
| `element_descriptions` | tylko `first_eval`: zał. nr 1 do rozp. 2015 (opisy 5 elementów oceny) w kształcie `annex1_criteria.json` (`criteria[{no, id, name, description[], page, assignment}]`) |
| `footnotes[]` | `{number, marker "10)", text, anchor, part, role}` — `text` dosłownie z `word/footnotes.xml` (białe znaki znormalizowane, punkty list odtworzone: „– ”, „1.”), `anchor` = tekst pola z odnośnikiem, `role` ∈ `applies_to`, `additional_criteria`, `period_from`, `period_to`, `partial_score`, `result_positive`, `result_negative`, `justification`, `development_conclusions`, `part3`, `first_eval_elements`, `total_score`, `exam_not_applicable`, `null` |

## annex1_criteria.json
`{source, title, criteria[{no, id, name, name_in_annex, description[], page, assignment}], model_check{checked, mismatches[], annex_items_not_in_model[], normalization}}`. `assignment`: `layout` (pozycja w PDF), `sequence_match_with_model` (s. 3: przydział granic przez zgodność sekwencji z modelem), `ambiguous_layout` (nie przypisano).

## kb/kb_chunks.jsonl
`{id, source_id, doc_type, title, unit, citation, heading_path[], page_from, page_to, process[], text, source_file}`
- `source_id`: `ustawa_sc`, `rozp2016`, `rozp2015`, `poradnik_okresowa_2016`, `poradnik_pierwsza_2016`, `model_kompetencji`, `kprm_qa_oceny`. Przypisy arkuszy mają `source_id` aktu, którego załącznikiem jest wzór (B, C → `rozp2016`; pierwsza ocena → `rozp2015`) i `doc_type: "arkusz"`.
- `doc_type`: `rozporzadzenie`, `ustawa`, `poradnik`, `model_kompetencji`, `arkusz`, `kprm_qa`.
- `id` (przykłady): `rozp2016:par11:ust1`, `rozp2015:par10`, `rozp2016:preambula`, `rozp2016:przypis1`, `rozp2016:zal1:komunikacja`, `rozp2015:zal1:rzetelnosc`, `ustawa_sc:art81`, `ustawa_sc:art28:v2`, `ustawa_sc:art<N>:cz2`, `poradnik_okresowa_2016:6_2_2`, `poradnik_pierwsza_2016:zalacznik_nr_1:cz2`, `model_kompetencji:komunikacja`, `periodic_b:przypis18`, `kprm_qa_oceny:<nr>` (nr z końcówki pola `id` w pliku Q&A).
- `unit`: „§ 11 ust. 1”, „§ 10”, „art. 81”, „rozdz. 6.2.2”, „Załącznik nr 1 (cz. 2)”, „arkusz B, przypis 18)”, „kompetencja: Rzetelność”, „Q&A KPRM nr 3”.
- `citation`: gotowy tekst do pokazania użytkownikowi, np. „§ 11 ust. 1 rozporządzenia Prezesa Rady Ministrów z 4 kwietnia 2016 r. (Dz. U. poz. 470)”, „poradnika KPRM „Oceny okresowe w służbie cywilnej” (wrzesień 2016), rozdz. 6.2.2, s. 21–23”.
- `page_from`/`page_to`: strony PDF; `null` dla ustawy (TXT), DOCX, XLSX i Q&A.
- `process`: `["periodic"]`, `["first"]` albo oba. Ustawa: art. 35–38 → `first`; art. 71, 81–83, 86, 89 → `periodic`; pozostałe → oba.
- Rozmiary: rozporządzenia 13–240 słów (paragraf/ustęp), poradniki 300–1200 słów (krótsze tylko na końcu rozdziału), ustawa: artykuł (> 1200 słów → części po ustępach).

## kb/sources.json
Lista `{source_id, doc_type, title, short_title, process, url, file, sha256}` (+ `eli`, `dz_u`, `stan_prawny_na`, `accessed` dla ustawy z `assets/ustawa_sc/*.meta.json`; `form` dla arkuszy).

## osp/<slug>.json
Wynik `parse_osp_docx` z `kompas-analiza-osp` (schemat: `kompas-analiza-osp/assets/osp_schema.json`). `slug` = nazwa pliku DOCX w ASCII snake_case, np. `osp_dxx_wyy_1_naczelnik_wydzialu`.

## build_report.json
`{builder, inputs{klucz: {file, sha256}}, counts{…}, checks{model_vs_annex1, ustawa_multi_version_articles, rozp2016_pages_with_doubled_chars, kb_doubled_char_chunks, …}, warnings[]}`. Kod wyjścia: 0 = OK (ostrzeżenia możliwe), 2 = błąd (brak pdftotext, niezgodne liczby w modelu, zdublowane id).
