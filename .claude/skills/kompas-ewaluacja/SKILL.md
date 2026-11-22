---
name: kompas-ewaluacja
description: Mierzy jakość asystenta AI Kompasu Kompetencji na rozłącznym zbiorze eval_holdout.json (pytania o pierwszą i okresową ocenę + pytania spoza bazy wymagające odmowy) jednym poleceniem run_eval.py i daje checklistę testów akceptacyjnych ścieżki demo z pkt 6. Użyj, gdy zespół mówi „zmierz asystenta”, „policz trafność”, „czy asystent dobrze odmawia”, „jaki mamy wynik na holdoucie”, „liczby do prezentacji”, „testy akceptacyjne” albo „sprawdź prototyp przed zgłoszeniem”.
---

# kompas-ewaluacja

## Cel

Pkt 6 pełnej treści: „Jurorzy mogą zadawać mu przykładowe pytania dotyczące zasad pierwszej oceny lub oceny okresowej. Oceniana będzie poprawność odpowiedzi.” Ten skill mierzy to przed zgłoszeniem na pytaniach, których **nie ma** w bazie FAQ (`kompas-asystent-ai/assets/faq_kb.json`) ani w Q&A KPRM, i daje liczby z opisem zbioru do README i na slajd 6 (`research/07`). Architektura asystenta i znaczenie wyników: `research/04_architektura_i_ai.md`, sekcja 4.

## Pliki

- `assets/eval_holdout.json` – 36 pytań: 29 o zasady (14 pierwsza ocena, 15 ocena okresowa; parafrazy i przypadki brzegowe z przepisów) i 7 spoza zakresu z `expect_refusal: true`. Każde pytanie ma `expected_units` (np. `{"source_id": "rozp2015", "unit": "§ 3"}`) i `key_points` (frazy, które poprawna odpowiedź musi zawierać).
- `scripts/run_eval.py` – jedno polecenie; tryb `--retrieval-only` (bez LLM) albo pełny (retrieval + odpowiedź modelu przez `LLMProvider` ze skilla `kompas-asystent-ai`). Raport `eval_*.json` + `eval_*.md` w `--out-dir`.
- `tests/test_holdout_disjoint.py` – 39 testów pytest: liczności i proporcje, kompletność specyfikacji odpowiedzi, brak parafraz FAQ (każde pytanie osobno) i brak parafraz Q&A KPRM (wyciek danych zawyżyłby wynik).
- `references/testy_akceptacyjne.md` – checklista na żywym prototypie: role i link, ścieżka okresowa (Jan Testowy), pierwsza ocena, asystent, PDF.
- `references/reports*/` – raporty z uruchomień; `references/test-run.md` – polecenia i wyniki.

## Kroki

1. Zbuduj bazę wiedzy (`kompas-dane-i-zrodla`): `data/processed/kb/kb_chunks.jsonl`.
2. Retrieval bez modelu (ok. 12 s z cache embeddingów, pierwsze uruchomienie liczy embeddingi):
   ```bash
   python .claude/skills/kompas-ewaluacja/scripts/run_eval.py --kb data/processed/kb/kb_chunks.jsonl \
       --retrieval-only --cache-dir .cache --out-dir eval_reports
   ```
3. Pełny pomiar z modelem: ustaw `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL` (i `LLM_API_KEY` dla API w chmurze) jak w `kompas-asystent-ai/.env.example`, potem to samo polecenie bez `--retrieval-only`. Lokalnie `llama3.1:8b` trwa ok. 14 min na 36 pytań; `--limit N` albo `--ids h_first_01 …` dla szybkiej próby.
4. Wpisz do README zgłoszenia liczby **z opisem zbioru**, np. „właściwy przepis w top-5 dla 27 z 29 pytań spoza bazy FAQ; 7 z 7 poprawnych odmów; model X”.
5. Przed 07:00 przejdź `references/testy_akceptacyjne.md` na publicznym linku.
6. Po każdej zmianie bazy, promptu, progów albo modelu powtórz krok 2 lub 3.

## Metryki

| Metryka | Znaczenie |
|---|---|
| `hit@1/3/5` | odsetek pytań o zasady, dla których co najmniej jedna oczekiwana jednostka jest w top-k retrievalu |
| `all@5` | wszystkie oczekiwane jednostki w top-5 |
| `refusal_recall_out_of_scope` | poprawne odmowy na pytaniach spoza zakresu |
| `false_refusals_in_scope` | niepotrzebne odmowy na pytaniach o zasady |
| `kp` (tryb pełny) | pokrycie `key_points` w odpowiedzi modelu (heurystyka słów kluczowych) |
| `cites` (tryb pełny) | cytowane id jednostek; poprawny cytat = id istnieje i był w kontekście |
| `latency_p50/p95_s` | czas odpowiedzi |

## Przykład (prawdziwe uruchomienie 2026-11-21, 15:01, baza 366 jednostek)

Wejście: polecenie z kroku 2 na `data-samples/processed/kb/kb_chunks.jsonl`.
Wyjście (`references/reports/eval_retrieval.md`, skrót): `n_in_scope 29`, `n_out_of_scope 7`, `hit@1 0.586`, `hit@3 0.931`, `hit@5 0.931`, `all@5 0.793`, `refusal_recall_out_of_scope 7/7`, `false_refusals_in_scope 2/29`, `latency_p50_s 0.101`, `hit@5_first 0.857`, `hit@5_periodic 1.0`.

Wyniki trybu pełnego z lokalnym modelem: `references/test-run.md`.

## Kiedy NIE używać

- Do budowy bazy wiedzy ani FAQ (`kompas-dane-i-zrodla`, `kompas-asystent-ai`).
- Do strojenia promptu „pod holdout” w kółko – każda poprawka dobrana na tym zbiorze zawyża wynik. Do strojenia używaj własnych pytań roboczych, holdout zostaw na pomiar.
- Jako źródło prawdy o przepisach – `key_points` napisano z tekstu przepisów, ale wiążące są akty (`research/02`).

## Pułapki

- **Progi odmowy (`coverage_min 0.20`, `dense_min 0.74`) dobrano na tym samym holdoucie** (`calibration_best` w raporcie), więc liczby odmów są optymistyczne. Uczciwiej: zamroź progi przed pomiarem albo podziel holdout na część do strojenia i część do pomiaru.
- **Q&A KPRM i poradniki konkurują z przepisami.** Odpowiedź z poradnika bywa poprawna, ale `expected_units` wskazują przepis, więc hit@k ją pomija. Po przebudowie bazy (307 → 366 jednostek, m.in. Q&A KPRM i wersje artykułów ustawy) hit@5 spadł z 0,966 do 0,931.
- **Mały lokalny model odmawia za często.** Retrieval znajduje właściwy przepis, a `llama3.1:8b` przy ścisłym prompcie i tak często pisze, że brak informacji (`references/test-run.md`). Na link jury mierz model docelowy (np. Groq), nie tylko lokalny.
- **`kp` to heurystyka słów kluczowych**: parafraza poprawnej odpowiedzi może dostać 0, a odpowiedź z dobrym słowem i złym sensem – 1. Przy prezentacji liczb przeczytaj kilka odpowiedzi ręcznie.
- **Jury zada inne pytania.** Wynik na 36 pytaniach to sygnał, nie gwarancja; ćwicz też pytania spoza zbioru (`kompas-demo-i-pitch`).
- Bez Ollamy na hostingu (sam BM25) poprawne odmowy spadają do 3/7 (`kompas-asystent-ai`, pułapki) – zmierz ten tryb, jeśli tak wdrażasz.

## Zależności i licencje

Biblioteka standardowa Pythona (PSF); pytest (MIT) do testów; Ollama (MIT [~]) z `nomic-embed-text` do embeddingów; model czatu według `LLMProvider`.
