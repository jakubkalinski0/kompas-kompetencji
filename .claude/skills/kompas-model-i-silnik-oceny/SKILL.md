---
name: kompas-model-i-silnik-oceny
description: Deterministyczny silnik oceny Kompasu Kompetencji (Python, sama stdlib) dla arkuszy B, C i pierwszej oceny. Liczy sugerowany poziom kryterium z ocen wskaźników z jawnym wzorem, średnią, ogólny poziom, ocenę pozytywną/negatywną, Część III, ślad decyzji i podpowiedzi strażnika błędów. Użyj, gdy zespół mówi „policz sugerowany poziom”, „kompas poziomu”, „czy ocena jest negatywna”, „waliduj arkusz”, „schemat dokumentu oceny”, „audit log przełożonego”.
---

# Silnik oceny: model kompetencji → sugestia → decyzja przełożonego → wynik

Zadanie wymaga (pełna treść, pkt 3 i 6), żeby system z wybranych zachowań **obliczał i pokazywał sugerowany
poziom** kompetencji, a ostateczny poziom **zawsze wybierał przełożony**. Ten skill robi to bez LLM, z wzorem
do pokazania na ekranie, i liczy wszystko, co z ocen cząstkowych wynika według przepisów: średnią, ogólny
poziom, wynik oceny, Część III, warunki pierwszej oceny. Fakty prawne (terminy, procedura) są w
`research/02_proces_i_przepisy.md`, a tutaj są tylko reguły zakodowane w silniku, ze źródłem i testem
(`references/reguly.md`).

## Co jest w środku

```
assets/evaluation_schema.json   kontrakt C3: JSON Schema dokumentu oceny (renderuje go kompas-dokumenty-i-terminy)
assets/forms_config.json        skale, progi, kryteria obowiązkowe, limit dodatkowych, mapowanie 5→3/5/7, reguły z polem source
assets/examples/*.json          persony C5: Anna (B, pozytywna, Cz. III), Jan (C, pracownik SC), Ewa (C, negatywna),
                                Piotr (pierwsza ocena: pozytywna z egzaminem „nie dotyczy” i negatywna)
scripts/kompas_engine/          pakiet: scoring.py (sugestia), rules.py (wynik), validate.py, guard.py, audit.py, engine.py
scripts/evaluate.py             CLI: --input dokument.json [--pretty | --summary] [--model] [--method] [--now]
tests/test_engine.py            80 testów pytest (w tym graniczne 2/4/6/8 i integracja z competency_model.json)
references/reguly.md            tabela: reguła → źródło (paragraf/przypis + plik) → pewność → test
references/test-run.md          dokładne polecenia i wyniki uruchomień
```

## Kroki (backend)

1. **Na każdą zmianę wskaźnika** (karta wskaźnika w UI) wywołaj `suggest_criterion(ratings, form, config,
   total_indicators=…)` i odeślij `formula`, `points`, `level_label`, `rated_count/total_count`, `warnings`.
   Liczy się w mikrosekundach, więc wystarczy zwykły endpoint albo port tej samej logiki do JS.
2. **Klik przełożonego** na poziomie kryterium → `record_decision(doc, criterion_id, final_points, actor,
   note=None, allowed_points=…)`. Ustawia `final_points` (decyzja człowieka) i dopisuje wpis do `audit_log`
   (`override_suggestion`, gdy różni się od sugestii). Notatka jest opcjonalna, nic nie blokuje.
3. **Przed zapisem i przed PDF** → `evaluate(doc, model=…)`. Zwraca nowy dokument z: `suggestion` dla
   każdego kryterium, `average`, `overall_level`, `result`, `part3_attached`, `print.*` (co drukować),
   `objection_notice`, `outcome.reasons`/`conditions`, `validation {ok, complete, errors, warnings}`, `guard[]`.
   Wejście nie jest modyfikowane. Silnik **nigdy nie ustawia `final_points`**.
4. PDF z gotowego dokumentu robi `kompas-dokumenty-i-terminy` (czyta pola `print.*`).

Jeden import pod FastAPI (szkic – **FastAPI nie jest zainstalowane w venv pakietu, kodu nie uruchamiano**;
silnik pod nim uruchomiono przez CLI i pytest):

```python
import sys; sys.path.insert(0, ".claude/skills/kompas-model-i-silnik-oceny/scripts")
from kompas_engine import evaluate, suggest_criterion, record_decision, load_config, load_model
from fastapi import FastAPI
app, CFG = FastAPI(), load_config()
MODEL = load_model("data/competency_model.json")          # wynik build_data.py (kompas-dane-i-zrodla)

@app.post("/api/evaluations/evaluate")
def api_evaluate(doc: dict) -> dict:
    return evaluate(doc, config=CFG, model=MODEL)          # zapisz wynik, zwróć do UI

@app.post("/api/suggest/{form}/{criterion_id}")
def api_suggest(form: str, criterion_id: str, ratings: list[dict]) -> dict:
    total = next(len(c["indicators"]) for c in MODEL["competencies"] if c["id"] == criterion_id)
    return suggest_criterion(ratings, form, CFG, total_indicators=total)
```

Uprawnienia (RBAC) i to, kto może wołać `record_decision`, są poza silnikiem – sprawdzaj rolę w endpointzie.
`sdr_note` to notatka robocza przełożonego: nie trafia do arkusza urzędowego i nie powinna być widoczna dla HR.

## „Kompas poziomu” – jak to pokazać na żywo

- Pod kartami wskaźników kryterium: pasek z wzorem z pola `formula`, np.
  `(7+5+7)/3 = 6,33 → powyżej oczekiwań → 7 pkt`, plus „oceniono 3 z 3 wskaźników”, a gdy oceniono mniej
  niż połowę, żółte ostrzeżenie z `warnings`.
- Obok pięć przycisków poziomu (1/3/5/7/9; w pierwszej ocenie 3/5/7). Sugerowany przycisk ma obwódkę
  „sugestia”, ale **nie jest zaznaczony** – zaznacza go dopiero klik człowieka (wymóg pkt 3 i 5 pełnej treści).
- Gdy klik ≠ sugestia: rozwija się pole „Dlaczego? (opcjonalnie)” → `override_note`; zapis i tak przechodzi.
- „Brak podstaw do oceny” to osobny przełącznik na karcie wskaźnika (`no_basis: true`), wyłączony ze średniej.
  Gdy wszystkie wskaźniki mają „brak podstaw”, zamiast wzoru pokaż komunikat z `formula` i zostaw wybór
  przełożonemu.
- W pierwszej ocenie wzór kończy się mapowaniem, np. `… → powyżej oczekiwań (poziom 4 z 5) → pierwsza ocena:
  7 pkt (… mapowanie do potwierdzenia z MC)`. Napis o mapowaniu zostaw, dopóki mentor MC go nie potwierdzi.
- Na dole arkusza: `outcome.formula` (np. `(7+5+5+7+5+7)/6 = 6,00 → na poziomie oczekiwań (powyżej 4
  punktów do 6 punktów)`) i `outcome.reasons`; dla pierwszej oceny lista 4 warunków `outcome.conditions`
  z ✓/✗.
- Komunikaty `guard[]` (`severity`: info/hint/warning/alert) pokazuj przy kryterium (`criterion_id`).
  `alert` = skutek prawny (ocena negatywna), `hint` = podpowiedź metodyczna. Żaden nie blokuje zapisu.

## Przykład wejście → wyjście (prawdziwe uruchomienie, 21.11.2026)

Polecenie (z katalogu skilla):
```
python -X utf8 scripts/evaluate.py --input assets/examples/anna_periodic_b.json --pretty \
  --now 2026-11-21T14:45:00+01:00 --model ../../../data-samples/processed/competency_model.json
```
Wejście (fragment): kryterium `podejmowanie_decyzji_i_odpowiedzialnosc`, wskaźniki na poziomach 4, 3, 4;
przełożony wybrał `final_points: 5` z notatką. Wyjście (fragmenty, kod wyjścia 0):
```json
"suggestion": {"points": 7, "level_label": "powyżej oczekiwań", "average": 6.33,
  "formula": "(7+5+7)/3 = 6,33 → powyżej oczekiwań → 7 pkt", "rated_count": 3, "total_count": 3, "warnings": []}
"average": 6.0, "average_display": "6,00",
"overall_level": {"level": 3, "key": "na_poziomie", "label": "na poziomie oczekiwań",
  "range_label": "powyżej 4 punktów do 6 punktów"},
"result": "pozytywna", "part3_attached": "tak",
"audit_log": [{"at": "2026-11-21T14:45:00+01:00", "actor": "Marek Kierownik-Demo (przełożony)",
  "action": "override_suggestion", "criterion_id": "podejmowanie_decyzji_i_odpowiedzialnosc",
  "suggested": 7, "final": 5, "note": "Decyzje w incydencie z marca wymagały kilku konsultacji z dyrektorem – zostaję przy 5 pkt."}]
"validation": {"ok": true, "complete": true, "errors": [], "warnings": [{"rule_id": "P-PERIOD-FROM", …
  "message": "Datę „od” uzupełniono datą zapoznania z kryteriami z Części I (2024-11-08)."}]}
```
Średnia 6,00 to granica przedziału: § 11 ust. 1 pkt 2 lit. c daje „na poziomie oczekiwań” (powyżej 4 do 6),
więc ocena jest pozytywna, a Część III (urzędniczka SC, wniosek złożony) się drukuje. Pozostałe persony:
`references/test-run.md`.

## Parametry (`assets/forms_config.json`)

- `suggestion.method`: `mean` (domyślnie) albo `median`; można też podać `method=` w wywołaniu / `--method`.
- `suggestion.min_rated_fraction_warning`: 0.5 (ostrzeżenie, gdy oceniono mniej niż połowę wskaźników).
- `first_eval_mapping.default`: `{"1":3,"2":3,"3":5,"4":7,"5":7}` – wariant **do potwierdzenia z mentorem MC**.
- `forms.<form>.mandatory_criteria`, `max_additional_criteria` (3 / 3 / 0), `positive_conditions` (pierwsza ocena).
- Każda reguła ma `source` z oznaczeniem pewności [✔]/[~]/[?]. Zmiana configu nie wymaga zmian w kodzie.

## Kiedy NIE używać

- Do decyzji o ocenie: silnik podpowiada i liczy skutki, ale ocen cząstkowych nie wybiera.
- Do terminów procesu (21 dni, 30 dni, 24 miesiące, 7 dni na sprzeciw z art. 83 ust. 1 ustawy) i PDF – to `kompas-dokumenty-i-terminy`.
- Do pytań o przepisy – asystent AI (`kompas-asystent-ai`) z bazą wiedzy. LLM nie liczy poziomów ani wyniku;
  jeśli asystent ma o nich mówić, niech cytuje pola `formula`/`reasons` z tego silnika.
- Do arkusza A (kierownik urzędu) – Partner go nie dał; config go nie zawiera (dodanie: nowy wpis w `forms`
  z 6 kryteriami z § 4 ust. 1 rozp. 2016, w tym zarządzanie strategiczne).

## Pułapki

- **Granice progów.** Przedziały są lewostronnie otwarte: 2,00 to jeszcze „znacznie poniżej”, 4,00 „poniżej”
  (ocena negatywna!), 6,00 „na poziomie”, 8,00 „powyżej”. Silnik porównuje ułamki (`fractions.Fraction`),
  więc 6,00 nie zamieni się w 6,0000001. Nie przepisuj progów na floaty w JS bez testów granicznych.
- **Jedna ocena 1 pkt = ocena negatywna** niezależnie od średniej (§ 11 ust. 1 pkt 4). Przykład Ewy:
  średnia 5,80 („na poziomie”), a wynik negatywny.
- **Pierwsza ocena: jedna „trójka” wymaga wyrównania.** 3+5+5+5+5 = 4,6 < 5 → negatywna; z jedną „siódemką”
  (3+7+5+5+5 = 5,0) – pozytywna. Dwie „trójki” → negatywna nawet przy łącznej 5,0 (drugi przykład Piotra).
- **Część III wymaga oceny pozytywnej** (§ 11 ust. 5, art. 89 ust. 1 ustawy), nie tylko statusu urzędnika
  i złożenia wniosku. Przy ocenie negatywnej z wnioskiem silnik zgłasza błąd `P-PART3-POSITIVE`.
- **„Brak podstaw” ≠ „nie oceniono”.** Oba są poza średnią, ale tylko „brak podstaw” jest świadomą decyzją
  przełożonego. Licznik `unrated_count` pokazuje wskaźniki jeszcze nieruszone.
- **Ocena wskaźników nie jest w przepisach.** Rozporządzenia punktują kryteria; punktacja wskaźnika 2L−1
  i średnia to interpretacja projektowa [~] – mówcie o „sugestii”, nie o „wyliczonej ocenie”.
- **Nazwy „efekt aureoli” i „tendencja centralna” nie występują w poradnikach KPRM.** Poradnik mówi tylko,
  że oceny mają wynikać z rzeczywistych zachowań, a nie z ogólnego postrzegania (s. 26). W UI można użyć
  tych nazw, ale źródłem podpowiedzi jest poradnik.
- Daty w dokumencie są ISO (`YYYY-MM-DD`); format `dd.mm.rrrr` z arkusza robi dopiero renderer PDF.

## Testy i uruchomienie

```
cd .claude/skills/kompas-model-i-silnik-oceny
python -m pytest tests -q                                  # 80 passed (21.11.2026)
KOMPAS_MODEL_JSON=ścieżka/competency_model.json python -m pytest tests -q   # test integracyjny w repo rozwiązania
python -X utf8 scripts/evaluate.py --input assets/examples/ewa_periodic_c_negative.json --summary
```
Kod wyjścia CLI: 0 – brak błędów walidacji, 1 – są błędy, 2 – nie da się wczytać pliku.
Test integracyjny szuka `data-samples/processed/competency_model.json` w pakiecie przygotowawczym albo pliku
z `KOMPAS_MODEL_JSON` (`.env.example`); bez niego jest pomijany (skip).

## Zależności i licencje

- Silnik: wyłącznie biblioteka standardowa Pythona ≥ 3.10 (PSF). Testowane na Pythonie 3.13.1.
- Testy: `pytest` (MIT). Szkic FastAPI wyżej: FastAPI (MIT) – niezainstalowane w tym pakiecie.
- Dane wejściowe: `competency_model.json` z `kompas-dane-i-zrodla` (kontrakt C1) – opcjonalnie.

Powiązane skille: `kompas-dane-i-zrodla` (model i struktura arkuszy), `kompas-dokumenty-i-terminy` (PDF
i terminy), `kompas-asystent-ai` (asystent nie liczy ocen), `kompas-wiedza-domenowa` (przepisy),
wspólny `hn-llm-w-produkcie` (zasada: liczby z kodu, LLM tylko wyjaśnia).
