---
name: kompas-dokumenty-i-terminy
description: Generuje oficjalne arkusze PDF oceny okresowej (B, C) i pierwszej oceny w służbie cywilnej wg wzorów z rozporządzeń, roboczą kartę przygotowania do rozmowy, liczy terminy z podstawą prawną (panel HR), statusy, przypomnienia (mock) i RBAC oraz daje kontrakt OpenAPI (w tym EZD RP i QNT jako propozycja). Użyj, gdy zespół mówi „wygeneruj PDF arkusza”, „karta przygotowania do rozmowy”, „policz terminy”, „panel HR”, „przypomnienia”, „kto widzi notatki S-D-R”, „API do EZD”.
---

# Kompas – dokumenty, terminy i uprawnienia

Skill daje gotowe klocki do trzech wymagań z pełnej treści zadania (pkt 3 i 5): dokumentacja w PDF, perspektywa HR (statusy, terminy, przypomnienia) oraz uwierzytelnianie, role i udokumentowane API. Wszystko działa offline, a jedyną zależnością spoza biblioteki standardowej jest reportlab (BSD).

| Plik | Co robi |
|---|---|
| `scripts/render_pdf.py` | Dokument oceny (kontrakt C3) → PDF arkusza B / C / pierwszej oceny albo `--kind karta` |
| `scripts/validate_pdf.py` | Sprawdza PDF przez `pdftotext -enc UTF-8`: polskie znaki, nazwisko, kryteria, średnią, X przy wyniku, przypisy 1:1, Część III, brak S-D-R |
| `scripts/extract_form_texts.py` | DOCX wzorów → `assets/form_texts.json` (przypisy dosłownie, sha256 źródeł) |
| `scripts/deadlines.py` | Kalendarz czynności z podstawą prawną, statusy i przejścia, flagi `zbliza_sie`/`po_terminie`, log przypomnień JSONL (mock) |
| `scripts/rbac.py` + `assets/rbac.json` | Widok dokumentu wg roli: `przelozony`, `kierujacy_komorka`, `hr_admin`, `pracownik` |
| `assets/openapi.json` | OpenAPI 3.1 (JSON jest poprawnym YAML 1.2): procesy, wskaźniki, sugestia, decyzja, PDF, przypomnienia, asystent, EZD RP i import kadrowy |
| `assets/examples/*.json` | Persony C5: `anna_b`, `jan_c`, `piotr_first_positive`, `piotr_first_negative`, `ewa_karta`, `processes_demo` |
| `assets/fonts/` | DejaVu Sans + Bold (1,5 MB) i licencja `LICENSE_DEJAVU.txt` |

## Kroki

1. Weź dokument oceny z silnika (`kompas-model-i-silnik-oceny/assets/evaluation_schema.json`, kontrakt C3). Każde kryterium musi mieć `final_points`, czyli decyzję przełożonego. Bez niej renderer kończy się kodem 2.
2. Arkusz: `python scripts/render_pdf.py --input dok.json --output arkusz.pdf`. Formularz bierze się z pola `form`.
3. Karta dla przełożonego: `python scripts/render_pdf.py --input dok.json --output karta.pdf --kind karta`.
4. Kontrola: `python scripts/validate_pdf.py arkusz.pdf --expect dok.json` (kod 1 przy błędzie). W CI uruchamiaj `pytest tests`.
5. Panel HR: `python scripts/deadlines.py calendar --input proces.json --today RRRR-MM-DD`. Przypomnienia: `remind --log przypomnienia.jsonl --sender "…"`. Zmiana statusu: `status --to …`.
6. API: każdy endpoint, który zwraca dokument, przepuszcza go przez `rbac.view_for_role(doc, rola)`.
7. Zmiana wzoru arkusza: podmień DOCX, uruchom `extract_form_texts.py --input <materialy> --output assets/form_texts.json` i testy.

## Przykład (prawdziwe uruchomienie, 2026-11-21)

Wejście `assets/examples/jan_c.json` (skrót): `form: periodic_c`, `employee: {full_name: "Jan Testowy", position: "Radca", corps_status: "pracownik_sc"}`, kryteria obowiązkowe C z `final_points` 5, 7, 5, 5, 5 i dodatkowe „Myślenie analityczne” 7, `average: 5.67`, `result: pozytywna`, `part3_requested: false`.

```
$ python scripts/render_pdf.py --input assets/examples/jan_c.json --output data-samples/pdf/jan_c.pdf
{"output": "data-samples\\pdf\\jan_c.pdf", "kind": "arkusz", "form": "periodic_c", "warnings": [], "average": 5.67,
 "overall_level": "na poziomie oczekiwań", "result": "pozytywna", "part3_printed": false}
$ python scripts/validate_pdf.py data-samples/pdf/jan_c.pdf --expect assets/examples/jan_c.json
data-samples/pdf/jan_c.pdf: 31/31 sprawdzeń OK
```
W PDF są X w kolumnach punktów, „5,67”, X przy „powyżej 4 punktów do 6 punktów”, POZYTYWNA X, X przy „NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)”, pouczenie o sprzeciwie z art. 83 ust. 1 i przypisy 1–18. Części III nie ma.

Terminy (`processes_demo.json`, dziś 2026-11-21):
```
P-2026-003 nie_rozpoczeta ['po_terminie']  kryteria po ocenie negatywnej 2026-10-27 (§ 7 pkt 2 rozp. 2016) po_terminie; ponowna ocena 2027-04-22 (art. 81 ust. 9)
P-2026-004 w_trakcie []  rozmowa_wstepna 2026-02-02 (§ 3 rozp. 2015); ocena 2026-09-13..2026-12-10 (art. 38 ust. 1)
```
Pełny zapis uruchomień: `references/test-run.md`. Wynik testów: 36 passed.

## Reguły zaszyte w generatorze (źródło: przypisy DOCX)

- Część III drukuje się tylko u urzędnika SC (`corps_status: urzednik_sc`) z `part3_requested` i przy pozytywnej ocenie (przypis 18, art. 89 ust. 1). W innym wypadku generator jej nie drukuje i wypisuje ostrzeżenie. Pole „Czy dołączono wniosek” dostaje X przy TAK, NIE albo NIE DOTYCZY.
- W pierwszej ocenie wnioski rozwojowe drukuje się tylko przy ocenie pozytywnej (przypis 8). Przy negatywnej pole zostaje puste, a generator zgłasza ostrzeżenie.
- Ocena negatywna bez uzasadnienia kończy się błędem (przypis 12 B/C, przypis 7 pierwszej oceny). Więcej niż 3 kryteria dodatkowe też (przypis 3).
- Ogólny poziom liczony jest z progów tabeli „PRZYZNANIE OCENY”. Wynik pierwszej oceny sprawdzany jest warunkami przypisu 6, a rozbieżność z polem `result` daje ostrzeżenie. Sam wynik wylicza silnik SILNIK.
- Notatki S-D-R, sugestie i `override_note` nigdy nie trafiają do arkusza, co sprawdza `validate_pdf.py`. Trafiają tylko do karty z nagłówkiem „Dokument roboczy przełożonego – nie włączać do akt osobowych” na każdej stronie.

## Terminy i RBAC

Tabela terminów z podstawą prawną i pewnością jest w `references/terminy.md`. Analiza przepisów i zmian stanu prawnego: `research/02_proces_i_przepisy.md` (agent PRAWO). HR (`hr_admin`) dostaje widok z białej listy pól: statusy, daty, flagi, log przypomnień, nazwisko i komórkę. Nie widzi kryteriów, notatek S-D-R ani historii czatu z asystentem rozmowy (`assistant_chat`). Kierujący komórką i pracownik dostają dokument bez pól z `private_fields`. Logowanie demo 1-click jest opisane w OpenAPI (`/api/v1/auth/demo-login`). Wzorce LLM i maskowanie PII: skill `hn-llm-w-produkcie`. Przed wysłaniem zgłoszenia: `hn-zgloszenie`.

## Kiedy NIE używać

- Do liczenia sugerowanego poziomu i wyniku oceny służy `kompas-model-i-silnik-oceny`. Ten skill tylko renderuje i sprawdza spójność.
- Do odpowiedzi asystenta i bazy wiedzy służą `kompas-asystent-ai` i `kompas-dane-i-zrodla`.
- Arkusza A (kierownik urzędu) Partner nie dał i generator go nie obsługuje.
- Prawdziwej wysyłki e-mail i prawdziwego API EZD RP/QNT tu nie ma. To mock i propozycja kontraktu.

## Pułapki

- `pdftotext` bez `-enc UTF-8` psuje polskie znaki. Walidator zawsze go podaje.
- Przypisy przechodzą przez granice stron. Walidator usuwa stopki „– strona N” przed porównaniem.
- Daty w JSON są w ISO (`2026-11-20`), a w PDF w formacie `dd.mm.rrrr` jak we wzorze.
- Imię i nazwisko dzielone są po pierwszej spacji, chyba że podasz `first_name`/`last_name`. Tak trzeba zrobić przy imionach dwuczłonowych.
- Granice okna pierwszej oceny (+1 dzień od daty odpowiadającej, −1 dzień przed „miesiąc przed końcem umowy”) odtworzono z przykładu w poradniku KPRM. To [~] do potwierdzenia z mentorem.
- Przesunięcie terminu sprzeciwu z weekendu i święta (art. 115 KC) to interpretacja [~]. Lista świąt w kodzie obejmuje Wigilię od 2025 r. [~].
- `openapi.json` jest w JSON, bo biblioteka standardowa nie ma parsera YAML. JSON jest poprawnym YAML 1.2, więc FastAPI może go podać pod `/docs`.

## Zależności i licencje

reportlab 5.1.0 (BSD, metadane paczki), czcionka DejaVu Sans (licencja Bitstream Vera + zmiany DejaVu w domenie publicznej, `assets/fonts/LICENSE_DEJAVU.txt`). Do walidacji potrzebny jest poppler `pdftotext`/`pdftoppm` (GPL, ale tylko jako narzędzie deweloperskie i CI, uruchamiane jako osobny proces i nieredystrybuowane z produktem). Pozostałe skrypty korzystają tylko z biblioteki standardowej. Zmiennych środowiskowych brak, więc nie ma `.env.example`. Porównanie dróg generowania PDF: `references/pdf_podejscia.md`.
