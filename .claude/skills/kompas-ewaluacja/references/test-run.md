# test-run: kompas-ewaluacja

Uruchomienia z 2026-11-21 na laptopie z GPU (i7-11370H, RTX 3060 Laptop 6 GB, Ollama 0.40.16), z katalogu `prep/kompas_kompetencji/`. Baza wiedzy: `data-samples/processed/kb/kb_chunks.jsonl` – 366 jednostek (stan 15:00). Zbiór: `assets/eval_holdout.json` – 36 pytań (15 ocena okresowa, 14 pierwsza ocena, 7 spoza zakresu z `expect_refusal`).

## Testy pytest (rozłączność i specyfikacja zbioru)

```bash
cd .claude/skills/kompas-ewaluacja && ../../../.venv/Scripts/python -m pytest tests -q
```
Wynik 15:01: `39 passed in 0.14s` (liczności, specyfikacja odpowiedzi, brak parafraz FAQ i Q&A KPRM).

## Retrieval bez modelu

```bash
python -X utf8 .claude/skills/kompas-ewaluacja/scripts/run_eval.py --kb data-samples/processed/kb/kb_chunks.jsonl \
  --retrieval-only --cache-dir .cache --out-dir .claude/skills/kompas-ewaluacja/references/reports
```
Wynik 15:01 (12 s, `references/reports/eval_retrieval.md`): hit@1 0,586; hit@3 0,931; **hit@5 0,931 (27/29)**; all@5 0,793; **odmowy spoza zakresu 7/7**; niepotrzebne odmowy 2/29; p50 0,10 s; hit@5 pierwsza ocena 0,857, okresowa 1,0. Progi odmowy (`coverage_min 0.20`, `dense_min 0.74`) dobrano na tym zbiorze – wynik odmów jest optymistyczny. Wcześniejszy pomiar subagenta AI (14:47, baza 307 jednostek, bez Q&A KPRM): hit@5 0,966 (`references/reports_bm25/` – wariant bez embeddingów).

## Pełny pomiar z modelem lokalnym

```bash
LLM_PROVIDER=ollama LLM_BASE_URL=http://localhost:11434 LLM_MODEL=llama3.1:8b LLM_TIMEOUT=180 \
python -X utf8 .claude/skills/kompas-ewaluacja/scripts/run_eval.py --kb data-samples/processed/kb/kb_chunks.jsonl \
  --cache-dir .cache --out-dir .claude/skills/kompas-ewaluacja/references/reports_full
```
Wynik 15:15 (ok. 14 min, `references/reports_full/eval_full.md`):

| Miara | Wartość |
|---|---|
| Poprawne odmowy spoza zakresu | 7/7 |
| Niepotrzebne odmowy na pytaniach o zasady | **13/29** (2 z progu retrievalu, 11 – model sam uznał, że źródła nie wystarczają) |
| Odpowiedzi z cytatem | 16/16 udzielonych |
| Cytat zawiera oczekiwaną jednostkę | 15/16 |
| Cytaty niezweryfikowane (spoza kontekstu) | 0/36 |
| Pokrycie `key_points` (średnia z udzielonych odpowiedzi) | 0,766 |
| Czas odpowiedzi p50 / p95 | 21,6 s / 46,2 s |

**Wniosek:** retrieval znajduje właściwy przepis (27/29 w top-5), odpowiedzi udzielone są poprawnie cytowane, ale `llama3.1:8b` przy ścisłym prompcie trybu formalnego odmawia w 11 przypadkach, w których odpowiedź była w kontekście (np. `h_first_10`, `h_periodic_03`, `h_periodic_04`). Przed demo: (1) zmierz model z publicznego linku (Groq `openai/gpt-oss-120b`) tym samym poleceniem z `LLM_PROVIDER=openai_compat`; (2) jeśli odmowy zostaną, złagodź w `kompas-asystent-ai/assets/prompts/formal_system.md` warunek odmowy (odpowiadaj, gdy jednostka w kontekście zawiera odpowiedź choćby częściowo, i zaznacz, czego brakuje) i zmierz ponownie na **innych** pytaniach roboczych, nie na holdoucie. Czas: pomiar szedł równolegle z innymi procesami na laptopie; izolowany pomiar `bench_llm.py` dał medianę 6,1 s na krótszym kontekście (`kompas-asystent-ai/references/test-run.md`).

Po pomiarze model zatrzymany: `ollama stop llama3.1:8b`.

## Pomiar na Groq – model z publicznego linku (2026-11-21, 16:07)

Klucz w `.env` repo rozwiązania (`LLM_PROVIDER=openai_compat`, `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=openai/gpt-oss-120b`, Zero Data Retention włączone w konsoli Groq), zmienne wczytane do powłoki (`set -a; . ./.env; set +a`), potem:
```bash
python -X utf8 .claude/skills/kompas-ewaluacja/scripts/run_eval.py --kb data-samples/processed/kb/kb_chunks.jsonl --cache-dir .cache --limit 10 --out-dir <katalog>
```
Wynik (10 pierwszych pytań zbioru – wszystkie o pierwszą ocenę, w zakresie):

| Miara | Groq `openai/gpt-oss-120b` | `llama3.1:8b` lokalnie, te same 10 pytań |
|---|---|---|
| Odpowiedzi | 7/10 | 5/10 |
| Cytat zawiera oczekiwaną jednostkę | 7/7 | 5/5 |
| Pokrycie `key_points` | 0,952 | 0,67 |
| Cytaty spoza kontekstu | 0 | 0 |
| Czas: mediana / najdłuższa odpowiedź | 1,7 s / 23,1 s | 16,8 s / 38,5 s |

Z 3 odmów 2 (`h_first_02`, `h_first_08`) to próg retrievalu (0,1 s, bez wywołania modelu), 1 (`h_first_10`) – odmowa modelu. Czasy 16–23 s to najpewniej czekanie na limit 8000 tokenów/min (darmowy plan Groq: 30 zapytań/min, 1000/dzień, 8000 tokenów/min, 200 000 tokenów/dzień – odczyt z konsoli 16:00). Wniosek: Groq zostaje modelem na link; przed demo poluzować próg retrievalu na osobnych pytaniach roboczych i oszczędzać dzienny limit (testy zespołu na Ollamie, cache odpowiedzi demo).
