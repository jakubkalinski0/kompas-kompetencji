# Uruchomienia skryptów – 2026-11-21 (Windows 10, Python 3.13.1, venv PKG: reportlab 5.1.0, pytest 9.2.0, poppler 24.07)

Katalog roboczy: `prep/kompas_kompetencji`, `SK=.claude/skills/kompas-dokumenty-i-terminy`, `PY=.venv/Scripts/python`, `PYTHONIOENCODING=utf-8`.

## 1. Wyciąg przypisów z DOCX Partnera
```
$PY $SK/scripts/extract_form_texts.py --input "d:/GitHub/setup/KompasKompetencji/HackNation" --output $SK/assets/form_texts.json
periodic_b: 18 przypisów z Arkusz oceny B (2).docx
periodic_c: 18 przypisów z Arkusz oceny C (2).docx
first_eval: 8 przypisów z Arkusz pierwszej oceny (2).docx
```

## 2. Generowanie i walidacja PDF (persony C5)
```
$PY $SK/scripts/render_pdf.py --input $SK/assets/examples/anna_b.json --output data-samples/pdf/anna_b.pdf
{"form": "periodic_b", "warnings": [], "average": 6.33, "overall_level": "powyżej oczekiwań", "result": "pozytywna", "part3_printed": true}
$PY $SK/scripts/validate_pdf.py data-samples/pdf/anna_b.pdf --expect $SK/assets/examples/anna_b.json
data-samples/pdf/anna_b.pdf: 31/31 sprawdzeń OK

jan_c.pdf                 → periodic_c, średnia 5.67, „na poziomie oczekiwań”, part3_printed: false → 31/31 OK
piotr_first_positive.pdf  → first_eval, egzamin „nie dotyczy”, ocena łączna 5.0, pozytywna, wnioski wydrukowane → 19/19 OK
piotr_first_negative.pdf  → first_eval, egzamin „tak”, dwie oceny 3 pkt, 4.2, negatywna;
                            OSTRZEŻENIE: Wnioski rozwojowe pominięte: dopuszczalne tylko przy pozytywnej pierwszej ocenie (przypis 8) → 20/20 OK
$PY $SK/scripts/render_pdf.py --input $SK/assets/examples/ewa_karta.json --output data-samples/pdf/ewa_karta.pdf --kind karta
{"kind": "karta", "form": "periodic_c", "warnings": [], "questions": 8} → 10/10 OK
```
Rozmiar 5 PDF-ów razem: 264 KB. Czas jednego uruchomienia CLI (arkusz C): 3,3 s (`time`, z importem reportlab).

Kontrola wizualna: `pdftoppm -png -r 60 -f 1 -l 2 anna_b.pdf anna`. Strona 1 ma kolejność jak DOCX: nagłówek „Załącznik nr 3”, ARKUSZ B, część I (urząd, dane ocenianego i oceniającego, tabela kryteriów z terminem, potwierdzenia z podpisami), początek części II z tabelą 1/3/5/7/9 i znakami X. Strona 2: średnia 6,33, tabela „PRZYZNANIE OCENY” z X przy „powyżej 6 do 8”, POZYTYWNA X, uzasadnienie, wnioski IPRZ, poprzednia ocena, TAK X przy wniosku o stopień, podpisy i pouczenie o sprzeciwie. Część III zaczyna się od nowej strony, a przypisy są na końcu. `pdffonts`: DejaVuSans i DejaVuSans-Bold osadzone. Helvetica jest zadeklarowana przez reportlab, ale nieużywana.

## 3. Terminy, statusy, przypomnienia
```
$PY $SK/scripts/deadlines.py calendar --input $SK/assets/examples/processes_demo.json --today 2026-11-21
P-2026-001 do_podpisu        ['zbliza_sie']  kryteria 2024-12-20 (wykonane), ocena 2026-11-25 zbliza_sie
P-2026-002 kryteria_ustalone ['zbliza_sie']  ocena 2026-12-01 zbliza_sie
P-2026-003 nie_rozpoczeta    ['po_terminie'] kryteria po ocenie negatywnej 2026-10-27 po_terminie; ponowna ocena 2027-04-22
P-2026-004 w_trakcie         []              rozmowa_wstepna 2026-02-02; sprawozdanie 2026-09-14..2026-09-25; ocena 2026-09-13..2026-12-10
$PY $SK/scripts/deadlines.py remind --input $SK/assets/examples/processes_demo.json --log <scratch>/przypomnienia.jsonl --sender "Zofia Kadrowa-Demo" --today 2026-11-21
{"reminders": 3, "log": "<scratch>/przypomnienia.jsonl", "delivery": "mock (bez wysyłki e-mail)"}
$PY $SK/scripts/deadlines.py status --input p.json --to zakonczona      (p.json: status nie_rozpoczeta)
BŁĄD: Niedozwolone przejście nie_rozpoczeta → zakonczona   (exit=2)
```

## 4. RBAC i OpenAPI
```
$PY $SK/scripts/rbac.py --role hr_admin --input $SK/assets/examples/anna_b.json
klucze: ['case_id', 'employee', 'evaluator', 'form', 'result']; 'sdr_note' w wyniku: False
json.load(openapi.json): 3.1.0, 14 ścieżek, 16 operacji (testy: wszystkie $ref rozwiązywalne, x-roles ⊆ role z rbac.json, unikalne operationId)
```

## 5. Testy
```
cd $SK && ../../../.venv/Scripts/python -m pytest tests -q
36 passed in 5.03s
```
Pokrycie: terminy (koniec miesiąca, rok przestępny 29.02, ocena negatywna 7 dni / 6 mies., nieobecność > 1 mies., święto 11.11 i sobota przy sprzeciwie, Wielkanoc/Boże Ciało, przykłady z obu poradników KPRM), statusy, log przypomnień. Generowanie każdego formularza i walidacja tekstu. Brak części III u pracownika SC nawet przy `part3_requested=true` i u urzędnika bez wniosku. Brak wniosków rozwojowych przy negatywnej pierwszej ocenie. Brak notatek S-D-R w arkuszu. Odrzucenie arkusza bez decyzji przełożonego, oceny negatywnej bez uzasadnienia i więcej niż 3 kryteriów dodatkowych. Progi ogólnego poziomu. RBAC: HR bez S-D-R i bez czatu. OpenAPI.
