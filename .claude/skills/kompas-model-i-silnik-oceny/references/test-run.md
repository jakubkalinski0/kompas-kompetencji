# Uruchomienia (2026-11-21, Windows 10, Python 3.13.1 z `prep/kompas_kompetencji/.venv`, pytest 9.2.0)

Katalog roboczy: `prep/kompas_kompetencji/.claude/skills/kompas-model-i-silnik-oceny`. `python` poniżej =
`../../../.venv/Scripts/python`. Model kompetencji: `data-samples/processed/competency_model.json` z
`build_data.py` agenta DANE (14 kompetencji, 49 wskaźników).

## 1. Testy

```
$ python -X utf8 -m pytest tests -q -p no:cacheprovider
........................................................................ [ 90%]
........                                                                 [100%]
80 passed in 1.15s
```
80 testów, 0 pominiętych (test integracyjny z `competency_model.json` wykonał się dla `periodic_b`, `periodic_c`,
`first_eval`). Pierwsze uruchomienie dało 2 błędy (75/77): `maxItems: 8` w schemacie przerywał regułę
P-MAX-ADDITIONAL zanim padł czytelny komunikat, a poziom wskaźnika 7 rzucał wyjątek zamiast błędu walidacji.
Oba poprawione (limit kryteriów tylko w regule; wyjątek → sugestia „niepoliczona” + błąd SCHEMA).

## 2. CLI na personach C5

Każde polecenie: `python -X utf8 scripts/evaluate.py --input assets/examples/<plik>.json --summary --model ../../../data-samples/processed/competency_model.json --now 2026-11-21T14:45:00+01:00`

**anna_periodic_b** (arkusz B, urzędniczka SC) – kod wyjścia 0
```
- Zarządzanie ludźmi: sugestia 7 pkt [(7+7+9+5+7)/5 = 7,00 → powyżej oczekiwań → 7 pkt] | decyzja: 7
- Podejmowanie decyzji i odpowiedzialność: sugestia 7 pkt [(7+5+7)/3 = 6,33 → powyżej oczekiwań → 7 pkt] | decyzja: 5
- Organizacja pracy i orientacja na osiąganie celów: sugestia 5 pkt [(5+5+7+5+5)/5 = 5,40 → na poziomie oczekiwań → 5 pkt] | decyzja: 5
- Współpraca: sugestia 7 pkt [(7+7+5+7+7+7)/6 = 6,67 → powyżej oczekiwań → 7 pkt] | decyzja: 7
- Komunikacja: sugestia 5 pkt [(5+7+5+5)/4 = 5,50 → na poziomie oczekiwań → 5 pkt] | decyzja: 5
- Myślenie analityczne: sugestia 7 pkt [(7+7+7)/3 = 7,00 → powyżej oczekiwań → 7 pkt] | decyzja: 7
Średnia/ocena łączna: 6,00 | poziom: na poziomie oczekiwań | wynik: pozytywna
Walidacja: ok=True complete=True błędy=0 ostrzeżenia=1        (P-PERIOD-FROM: „od” uzupełnione z Części I)
  STRAŻNIK G-UNIFORM-LEVELS (hint): Myślenie analityczne: wszystkie 3 ocenione wskaźniki mają ten sam poziom …
```
W JSON (`--pretty`): `part3_attached: "tak"`, `print.include_part3: true`, jeden wpis `audit_log`
`override_suggestion` 7→5 z notatką przełożonego (pełny fragment w SKILL.md).

**jan_periodic_c** (arkusz C, pracownik SC) – kod 0
```
Średnia/ocena łączna: 5,80 | poziom: na poziomie oczekiwań | wynik: pozytywna
Walidacja: ok=True complete=True błędy=0 ostrzeżenia=0
  STRAŻNIK G-UNIFORM-LEVELS (hint): Organizacja pracy …: wszystkie 4 ocenione wskaźniki mają ten sam poziom „na poziomie oczekiwań” …
```
`part3_attached: "nie_dotyczy"`, `print.include_part3: false`.

**ewa_periodic_c_negative** (arkusz C, jedna ocena 1 pkt) – kod 0
```
- Rzetelność: sugestia 1 pkt [(1+3)/2 = 2,00 → znacznie poniżej oczekiwań → 1 pkt] | decyzja: 1
Średnia/ocena łączna: 5,80 | poziom: na poziomie oczekiwań | wynik: negatywna
  STRAŻNIK G-SIGNIFICANTLY-BELOW (alert): Rzetelność: „znacznie poniżej oczekiwań” (1 pkt). Jedna taka ocena cząstkowa oznacza ocenę okresową NEGATYWNĄ …
```

**piotr_first_eval_positive** (egzamin „nie dotyczy” – zastępstwo) – kod 0
```
- Organizacja pracy …: sugestia 3 pkt [(3+3+5+3)/4 = 3,50 → poniżej oczekiwań (poziom 2 z 5) → pierwsza ocena: 3 pkt (poniżej oczekiwań; mapowanie do potwierdzenia z MC)] | decyzja: 3
Średnia/ocena łączna: 5,40 | poziom: — | wynik: pozytywna
Walidacja: ok=True complete=True błędy=0 ostrzeżenia=0
```

**piotr_first_eval_negative** (egzamin „tak”, dwie oceny 3 pkt) – kod 0
```
Średnia/ocena łączna: 5,00 | poziom: — | wynik: negatywna
  STRAŻNIK G-FIRST-TWO-LOWEST (alert): Pierwsza ocena: 2 oceny cząstkowe po 3 pkt. Dopuszczalna jest najwyżej jedna …
```
`outcome.conditions`: niespełniony tylko `F-MAX-ONE-LOWEST`; `print.include_development_conclusions: false`.

## 3. Błąd walidacji i metoda mediany

```
$ python -X utf8 scripts/evaluate.py --input <ewa_periodic_c_negative.json z justification=null> --summary
Walidacja: ok=False complete=False błędy=1 ostrzeżenia=0
  BŁĄD P-JUSTIFICATION: Ocena negatywna wymaga uzasadnienia.
exit=1

$ python -X utf8 scripts/evaluate.py --input assets/examples/jan_periodic_c.json --method median --summary
- Wykorzystywanie wiedzy i doskonalenie zawodowe: sugestia 7 pkt [mediana(5, 7, 7) = 7,00 → powyżej oczekiwań → 7 pkt] | decyzja: 7
```

## Czego nie uruchamiano

- Szkicu FastAPI z SKILL.md (FastAPI nie jest zainstalowane w venv pakietu). Silnik pod nim to te same funkcje,
  które przechodzą testy.
- Renderowania PDF – robi to `kompas-dokumenty-i-terminy` na podstawie `assets/evaluation_schema.json`.
