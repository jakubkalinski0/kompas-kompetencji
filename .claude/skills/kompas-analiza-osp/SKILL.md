---
name: kompas-analiza-osp
description: Parsuje opis stanowiska pracy (OSP, .docx) do JSON bez danych osobowych, proponuje arkusz oceny okresowej B albo C z podstawą prawną i ostrzeżeniem „kieruje vs koordynuje” oraz kandydatów na kryteria dodatkowe (z „Kompetencji miękkich” OSP i od LLM z dosłownym cytatem zadania). Użyj, gdy zespół mówi „wczytaj OSP”, „sparsuj opis stanowiska”, „arkusz B czy C”, „zaproponuj kryteria dodatkowe”, „wskaźniki do omówienia na start okresu”.
---

# kompas-analiza-osp

Krok 1 ścieżki **Oceny okresowej** z grafiki Partnera (`Kompas Kompetencji_ Ścieżki Oceny.png`): przełożony wgrywa OSP pracownika, a Kompas proponuje arkusz (B/C) i kryteria dodatkowe. Wszystko jest propozycją. Arkusz i kryteria zatwierdza przełożony, bo to on jest oceniającym (§ 2 ust. 1 rozporządzenia z 2016 r.). Pierwsza ocena nie korzysta z OSP ani z kryteriów dodatkowych, więc ten skill jej nie dotyczy.

## Pliki
| Plik | Co robi |
|---|---|
| `scripts/osp_parser.py` | `parse_osp_docx(path\|bytes) -> dict` + CLI. Sama biblioteka standardowa (zipfile + xml.etree). Kontrakt C4: importuje go `kompas-dane-i-zrodla/scripts/build_data.py`. |
| `scripts/propose_form.py` | `propose_form()`, `additional_candidates()`, `validate_selection()`, `build_llm_prompt()`, `validate_llm_output()`, `call_ollama()` + CLI. |
| `assets/osp_schema.json` | JSON Schema wyniku parsera (test `tests/test_schema.py` pilnuje zgodności). |
| `assets/prompt_additional_criteria.md` | Szablon promptu LLM (SYSTEM/USER, blok `<osp_data>`, format JSON). |
| `references/test-run.md` | Polecenia, wyniki uruchomień, ręczna weryfikacja pól z dokumentami. |
| `references/pulapki.md` | Wersje szablonu OSP, pola wyboru, „kieruje vs koordynuje”, PII, upload, prompt injection. |
| `tests/` | 18 testów pytest: 13 na syntetycznym DOCX (bez materiałów) + 5 na OSP Partnera (pomijane bez `KOMPAS_MATERIALY`). |

## Przepływ w aplikacji
1. **Upload `.docx`** (formularz „Nowy proces → Ocena okresowa”). Backend wywołuje `parse_osp_docx(bytes, filename=...)`. `OspParseError` pokazuje komunikat („To nie jest plik DOCX…”), a `warnings` wyświetlają się jako żółte uwagi z możliwością ręcznej poprawki pól.
2. **Podgląd OSP**: stanowisko, komórka, symbol, cel, zadania dominujące i pozostałe, zaznaczone pola ☒. W JSON nie ma nazwisk, tylko `[osoba]`.
3. **Propozycja arkusza**: `propose_form(osp)` zwraca `proposed_form` (`periodic_b`/`periodic_c`, kontrakt C3 `form`), `confidence`, `reason`, `legal_basis` (dosłowne cytaty § 3 ust. 3/4, przypis 1 arkusza i § 4 ust. 2/3), `warnings` i `evidence` (cytaty z zadań). UI wymaga kliknięcia „Potwierdzam arkusz B/C” (albo zmiany arkusza), a decyzja trafia do `audit_log` (`suggested` → `final`).
4. **Kandydaci na kryteria dodatkowe**: `additional_candidates(osp, form)` bierze „Kompetencje miękkie” z OSP spoza listy obowiązkowej. Opcjonalnie LLM (`build_llm_prompt` → model → `validate_llm_output`) dokłada kandydatów z zadań z dosłownym cytatem i rekomenduje wskaźniki do omówienia na starcie okresu. Przełożony zaznacza najwyżej 3 (`validate_selection`, § 5 ust. 2), a wybrane trafiają do `criteria[]` z `kind: "additional"` (kontrakt C3).
5. **Rozmowa na start okresu** (część I arkusza): wybrane wskaźniki idą do asystenta rozmowy (`kompas-asystent-ai`).

## Polecenia
```bash
PY=.venv/Scripts/python   # Windows; na Linux/macOS: .venv/bin/python
S=.claude/skills/kompas-analiza-osp/scripts
# 1) OSP -> JSON (plik .docx, katalog albo .zip; bez --out wypisuje JSON na stdout)
$PY -X utf8 $S/osp_parser.py "materialy/Kompetencje wspierające analizę OSP + przykładowe OSP/OSP_word.zip" --out out/osp
# 2) propozycja arkusza + kandydaci (wejście: .json z kroku 1 albo .docx)
$PY -X utf8 $S/propose_form.py out/osp/<slug>.json --out out/analiza.json
# 3) z LLM: prompt do pliku i/lub wywołanie lokalnej Ollamy + walidacja
$PY -X utf8 $S/propose_form.py out/osp/<slug>.json --model data/competency_model.json \
    --prompt-out out/prompt.json --ollama qwen2.5:14b --out out/analiza_llm.json
# 4) testy (materiały opcjonalne)
KOMPAS_MATERIALY=materialy $PY -m pytest .claude/skills/kompas-analiza-osp/tests -q
```
`--form periodic_b|periodic_c` liczy kandydatów dla arkusza potwierdzonego przez przełożonego, gdy różni się od propozycji. `competency_model.json` generuje `kompas-dane-i-zrodla` (`build_data.py`).

## Przykład wejście → wyjście (prawdziwe uruchomienie 2026-11-21, skrócone)
Wejście: OSP starszego specjalisty z `OSP_word.zip` (persona demo: Ewa Fikcyjna). Symbol stanowiska, komórkę i treść zadań pominięto – OSP to wewnętrzne dokumenty MC.
```json
{"part1": {"office": "Ministerstwo Cyfryzacji", "org_unit": "Departament …",
           "position_name": "starszy specjalista", "position_symbol": "…",
           "supervisor_direct": "naczelnik wydziału"},
 "part2": {"subordinates": {"selected_code": "none", "status": "ok", "raw": "☒ brak podległych pracowników\n☐ …"},
           "tasks": {"dominant": [{"no": 1, "text": "…"}, …3], "other": [… 4]},
           "required_competencies": {"soft_competencies": {"ids": ["organizacja_pracy_i_orientacja_na_osiaganie_celow",
              "wspolpraca", "myslenie_analityczne", "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe"], "unmatched": []}}},
 "warnings": []}
```
`propose_form.py` na tym JSON:
```json
{"form_proposal": {"proposed_form": "periodic_c", "form_letter": "C", "confidence": "high", "rule_id": "R1_brak_podleglych",
   "legal_basis": [{"citation": "§ 3 ust. 4 rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. (Dz. U. poz. 470)", "quote": "Arkusz C, …"}, …],
   "warnings": [], "requires_confirmation": true},
 "additional_criteria": {"candidates": [{"id": "myslenie_analityczne", "osp_text": "myślenie analityczne", "match": "exact"}],
   "osp_soft_competencies_already_mandatory": ["organizacja_pracy_i_orientacja_na_osiaganie_celow", "wspolpraca",
     "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe"], "max_selectable": 3}}
```
Naczelnik wydziału (Anna Przykładowa) dostaje `periodic_b`, `R2_podlegli_pracownicy`, ostrzeżenie „Koordynowanie nie musi oznaczać bezpośredniego kierowania – potwierdź…” (opcja OSP brzmi „bezpośrednio kieruje lub koordynuje pracę od 5 do 9 pracowników”), dowód z zadania 1 (cytat o zarządzaniu zespołem) i kandydata `wykorzystywanie_wiedzy_i_doskonalenie_zawodowe`. Radca (Jan Testowy) dostaje `periodic_c` i zero kandydatów z OSP, bo jego 3 kompetencje miękkie są obowiązkowe dla C. Pełny zapis uruchomienia, z wynikiem LLM dla radcy, jest w `references/test-run.md`; zawiera treść OSP, więc nie trafia do publicznej kopii repozytorium.

## Reguły (deterministyczne, bez LLM)
- **R1**: zaznaczone „brak podległych pracowników” → **C** (§ 3 ust. 4; przypis 1 arkusza C).
- **R2**: zaznaczony przedział z podległymi („do 4”, „5–9”, „powyżej 9”, „podlegają osoby kierujące…”) → **B** (§ 3 ust. 3; przypis 1 arkusza B). Gdy opcja mówi „kieruje lub koordynuje”, zawsze pojawia się ostrzeżenie.
- **R3**: nic nie zaznaczono, zaznaczenia są sprzeczne albo nie ma sekcji → B/C wg cytatów o kierowaniu ludźmi w celu i zadaniach, `confidence: low`, ostrzeżenie „niejednoznaczna”.
- Kandydaci = `soft_competencies.ids` minus kryteria obowiązkowe arkusza (§ 4 ust. 2–3). Limit wyboru 3 (§ 5 ust. 2), uzasadnienie wyboru z OSP (§ 2 ust. 2).
- Fakty prawne i ich aktualność: `research/02_proces_i_przepisy.md` (agent PRAWO). Cytaty w kodzie sprawdzono w PDF rozporządzenia z MAT (s. 1–2) i w przypisach DOCX arkuszy.

## LLM (tylko propozycje)
- Prompt: `assets/prompt_additional_criteria.md`. Treść OSP (cel i zadania, bez części I i III) trafia do bloku `<osp_data>` jako JSON z zakodowanymi `<` `>`. Model dostaje listę dozwolonych kryteriów i id wskaźników z `competency_model.json`.
- `validate_llm_output()` odrzuca kryteria obowiązkowe, nieznane id, duplikaty, numer nieistniejącego zadania i cytat, który nie jest dosłownym fragmentem zadania. Przyjmuje najwyżej 3 kandydatów i odrzuca nieznane id wskaźników.
- Uruchomione 2026-11-21 na OSP radcy. `llama3.1:8b`: 251 s, 3 kandydatów przyjętych (myślenie analityczne, kreatywność, negocjowanie). Ostatni z nich jest naciągany, a wskaźniki to zawsze `.1`, więc liczy się wybór przełożonego. `qwen2.5:14b` na 6 GB VRAM przekroczył limit 600 s. Na demo propozycje LLM trzeba liczyć z wyprzedzeniem (cache) – szczegóły w `references/test-run.md`.
- Wzorce wyjścia JSON i ochrony przed prompt injection opisuje `hn-llm-w-produkcie`. Klient LLM produkcyjny i maskowanie PII są w `kompas-asystent-ai`, a `call_ollama()` służy tylko do demo i testu.

## Kiedy NIE używać
- Pierwsza ocena w służbie cywilnej: stałe 5 elementów (rozporządzenie z 2015 r.), bez arkusza B/C i bez kryteriów dodatkowych.
- Ustalanie poziomu oceny pracownika: to `kompas-model-i-silnik-oceny`, a LLM nie ocenia.
- Kierownik urzędu (arkusz A): poza zakresem, Partner nie dał wzoru.
- Baza wiedzy asystenta: OSP do niej nie należą.
- Pliki `.doc`/`.pdf`/skany: parser czyta tylko `.docx`.

## Pułapki (skrót – pełna lista w `references/pulapki.md`)
- Szablony OSP się różnią, nawet trzy OSP z MC mają dwa układy tabel. Parser szuka etykiet, a braki zgłasza w `warnings`.
- Pole wyboru `w14:checkbox`: stan bierzemy z `w14:checked`, nie z glifu. Dopisane ręcznie „X” nie zostanie rozpoznane, wtedy działa R3.
- „Kieruje lub koordynuje” nie przesądza o arkuszu B. Ostrzeżenie i potwierdzenie przełożonego są obowiązkowe.
- Pola tekstowe OSP nie są anonimizowane, a nazwiska są usuwane tylko z pól osobowych. Przed LLM trzeba zamaskować PII.
- OSP to wewnętrzne dokumenty MC: nie trafiają do publicznego repozytorium ani do bazy wiedzy.

## Zależności i licencje
- Kod produkcyjny: tylko biblioteka standardowa Pythona ≥ 3.10 (PSF).
- Testy: `pytest` (MIT).
- Opcjonalnie: Ollama (MIT) jako lokalny serwer modeli. Model `qwen2.5:14b`: [~] licencja Apache-2.0 wg karty modelu Qwen2.5 (DO WERYFIKACJI na huggingface.co/Qwen/Qwen2.5-14B-Instruct przed wdrożeniem).
- Zmienne: `.env.example` (`OLLAMA_URL`, `OLLAMA_KEEP_ALIVE`, `KOMPAS_MATERIALY`). Sekretów brak.
