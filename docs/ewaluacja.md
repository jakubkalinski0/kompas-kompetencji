# Ewaluacja asystenta formalnego

Pomiary z 21.11.2026 i 22.11.2026, skrypt `run_eval.py` ze skilla `kompas-ewaluacja`. Raporty: [docs/eval/](eval/).

## 22.11.2026: pytania potoczne, rozmowa, mniej niepotrzebnych odmów

Przy pytaniach zadanych tak, jak zadaje je przełożony bez przygotowania prawniczego, asystent prawie zawsze odmawiał. Na 8 roboczych pytaniach potocznych (spoza holdoutu, np. „Co jeśli pracownik nie zgadza się z oceną?”, „Kto podpisuje arkusz oceny?”, „Czym się różni ocena okresowa od pierwszej oceny?”) model działającej wersji odpowiedział na 1. Przyczyny i poprawki:

1. `openai/gpt-oss-120b` liczy rozumowanie do `max_tokens`. Przy limicie 450 tokenów odpowiedź bywała pusta, a pusta odpowiedź nie ma cytatu, więc aplikacja pokazywała odmowę. Teraz `reasoning_effort: low` i limit 1400.
2. gpt-oss zapisuje czasem cytat w swoim formacie `【id】`, którego walidator nie rozpoznawał. Teraz zapis jest ujednolicany przed walidacją (także `[a, b]` oraz `(id ust. 4)` dla identyfikatorów z kontekstu). Zmyślony identyfikator dalej kończy się odmową.
3. Próg pokrycia słów odrzucał pytania potoczne przed modelem („nie zgadza się” nie występuje w przepisach). Pokrycie od 0,06 do 0,20 trafia teraz do modelu, który odpowiada z cytatem albo odmawia; poniżej 0,06 odmowa bez modelu. Krótki słownik potocznych sformułowań (14 wzorców, np. „nie zgadza się” → „sprzeciw”) dopisuje słowa przepisów do wyszukiwania.
4. Prompt wymagał pełnej odpowiedzi albo odmowy. Teraz model odpowiada na część, którą pokrywają źródła, i dopisuje, czego w bazie nie ma.
5. Dopasowanie FAQ gubiło słowa pytające i przeczenie, więc „Kto sporządza ocenę okresową?” i „Kiedy nie sporządza się oceny okresowej?” dostawały gotową odpowiedź na „Jak często sporządza się ocenę okresową?”. Słowa pytające i „nie” biorą teraz udział w dopasowaniu.
6. Dwie nowe pozycje FAQ zespołu: różnica między pierwszą oceną a okresową oraz znaczenie poziomów przy wskaźnikach.

Asystent prowadzi też rozmowę: pytanie uzupełniające („A ile dyrektor ma czasu na rozpatrzenie?”) szuka razem z poprzednim pytaniem, a model dostaje dwie poprzednie tury bez identyfikatorów źródeł.

| Pomiar | Przed | Po |
|---|---|---|
| 8 pytań potocznych, `openai/gpt-oss-120b` | 1/8 odpowiedzi | 8/8 odpowiedzi z cytatem |
| 7 pytań spoza zakresu z holdoutu, `openai/gpt-oss-120b` | nie mierzone | 7/7 odmów |
| holdout, samo wyszukiwanie BM25: hit@1 / hit@3 / hit@5 | 0,72 / 0,79 / 0,97 | 0,76 / 0,83 / 0,97 |
| holdout, wszystkie oczekiwane jednostki w top-5 | 0,90 | 0,86 |

Zastrzeżenia: słownik pytań potocznych i wagę dopisanych słów stroiliśmy na tych 8 pytaniach roboczych, więc wynik 8/8 nie jest niezależny. Holdout służył tylko do sprawdzenia, czy zmiany go nie pogarszają; nie dobieraliśmy na nim nowych reguł. Pełnego holdoutu na Groq nie mierzyliśmy z powodu dziennego limitu tokenów, który dzieli z działającą wersją. Pełnego potoku na lokalnym `llama3.1:8b` po zmianach nie powtórzyliśmy. Raporty: `eval/retrieval_bm25/`, `eval/full_bm25_groq_out_of_scope/`.

## Zbiór

`.claude/skills/kompas-ewaluacja/assets/eval_holdout.json`, rozłączny z FAQ asystenta (`faq_kb.json`): 29 pytań o zasady pierwszej i okresowej oceny, każde z oczekiwanymi jednostkami redakcyjnymi i punktami kluczowymi odpowiedzi, oraz 7 pytań spoza zakresu, na które poprawną odpowiedzią jest odmowa. Baza wiedzy: 366 jednostek (ustawa o służbie cywilnej, rozporządzenia z 2015 i 2016 r., wzory arkuszy, poradniki KPRM, model kompetencji MC, pytania i odpowiedzi z gov.pl).

## Wyszukiwanie: hybryda czy sam BM25

W działającej wersji nie ma Ollamy, więc nie ma embeddingów `nomic-embed-text`; asystent korzysta z samego BM25 (`KOMPAS_EMBEDDINGS=0`). Porównanie na 36 pytaniach:

| Wyszukiwanie (top-5) | hybryda BM25 + embeddingi | sam BM25 (działająca wersja) |
|---|---|---|
| hit@1 / hit@3 / hit@5 | 0,59 / 0,93 / 0,93 | 0,72 / 0,79 / 0,97 |
| wszystkie oczekiwane jednostki w top-5 | 0,79 | 0,90 |
| odmowy już na etapie wyszukiwania (7 spoza zakresu) | 7/7 | 3/7 |
| niepotrzebne odmowy (29 w zakresie) | 2/29 | 0/29 |
| czas wyszukiwania p50 | 2,7 s | 0,005 s |

Model dostaje 5 jednostek, więc dla odpowiedzi liczą się hit@5 i komplet jednostek w top-5; tu BM25 wypada lepiej. Słabszy jest przy hit@3 i w odmowie przed wywołaniem modelu, dlatego zmierzyliśmy też pełny potok.

## Pełny potok (wyszukiwanie + model)

Tryb działającej wersji (BM25), lokalny `llama3.1:8b`:

| Metryka | Wynik |
|---|---|
| poprawne odmowy (7 pytań spoza zakresu) | 7/7 |
| odpowiedzi na pytania o zasady | 22/29, wszystkie z cytatem sprawdzonym z kontekstem |
| odpowiedź cytuje oczekiwaną jednostkę | 19/22 |
| pokrycie punktów kluczowych (heurystyka słów) | 0,82 |
| cytaty spoza kontekstu | 0/36 |
| czas p50 / p95 (laptop z GPU 6 GB) | 16 s / 43 s |

Wszystkie 7 niepotrzebnych odmów to odpowiedzi małego modelu bez poprawnego identyfikatora źródła: asystent nie pokazuje odpowiedzi bez źródła i zamienia ją na odmowę. Wcześniejszy pomiar samych pytań spoza zakresu dał 6/7: przy „Ile wynosi płaca minimalna w 2026 roku?” `llama3.1:8b` odpowiedział wymijająco, choć bez zmyślonej kwoty. Model działającej wersji (Groq `openai/gpt-oss-120b`) to pytanie odrzucił, a na pytaniach demo odpowiada z właściwym przepisem w 1–2 s (termin sprzeciwu: art. 83 ustawy; negatywna pierwsza ocena: § 10 rozporządzenia z 2015 r.). Pełnego zbioru na Groq nie mierzyliśmy, bo zużyłby około 80 tys. z 200 tys. tokenów dziennego limitu.

Pomiary wykryły błąd w `run_eval.py`: tryb pełny ignorował `--no-embed`. Poprawka jest w commicie `3004fc5`.

## Powtórzenie pomiarów

Baza wiedzy powstaje z materiałów MC (`build_data.py`), więc pomiary da się powtórzyć tylko z tymi materiałami.

```bash
S=.claude/skills/kompas-ewaluacja/scripts
KB=deploy/processed/kb/kb_chunks.jsonl
python -X utf8 $S/run_eval.py --kb $KB --retrieval-only --out-dir docs/eval/retrieval_hybrid             # wymaga Ollamy
python -X utf8 $S/run_eval.py --kb $KB --retrieval-only --no-embed --out-dir docs/eval/retrieval_bm25
python -X utf8 $S/run_eval.py --kb $KB --no-embed --out-dir docs/eval/full_bm25_ollama                  # model z LLM_* w środowisku
```
