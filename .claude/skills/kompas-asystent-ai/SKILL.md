---
name: kompas-asystent-ai
description: 'Asystent AI Kompasu Kompetencji: Asystent formalny (FAQ → BM25 + embeddingi → odmowa poniżej progu → odpowiedź z cytatem [id] jednostki redakcyjnej) i Asystent rozmowy (pytania na rozmowę, feedback S-D-R, szkic uzasadnienia, wnioski do IPRZ) z maskowaniem danych osobowych i jednym LLMProvider (Ollama albo darmowe API zgodne z OpenAI). Użyj, gdy zespół mówi „podłącz asystenta”, „odpowiedz z cytatem”, „asystent ma odmawiać”, „zamaskuj dane pracownika”, „przełącz na Groq/Ollamę”, „pytania na rozmowę”.'
---

# kompas-asystent-ai

## Cel

Pkt 5 pełnej treści: asystent ma odpowiadać „przede wszystkim na podstawie udostępnionych mu źródeł”, „umożliwiać identyfikację źródła”, przy braku informacji „jasno to komunikować” i nie może „samodzielnie podejmować decyzji dotyczących poziomu oceny pracownika”. Ten skill daje gotowy backend tych zachowań: jedno wywołanie `answer(question, mode, context)` z odpowiedzią, listą cytatów `{id, citation, fragment}` albo odmową. Architektura i decyzje: `research/04_architektura_i_ai.md`. Ogólne wzorce LLM (schemat JSON, injection, replay): wspólny skill `hn-llm-w-produkcie`.

## Pliki

- `scripts/llm_provider.py` – `LLMProvider` (stdlib `urllib`): `LLM_PROVIDER=ollama|openai_compat`, `chat()`, `embed()`, timeout, ponowienia (429/5xx, `Retry-After`), cache odpowiedzi `.llm_cache/` (`LLM_CACHE=1`), demo offline `LLM_REPLAY=1`. Zmienne: `.env.example`.
- `scripts/retrieve.py` – warstwa 1: dopasowanie do `assets/faq_kb.json` (ze słowami pytającymi i przeczeniem); warstwa 2: BM25 (czysty Python, polska normalizacja, słownik potocznych sformułowań `QUERY_EXPANSIONS`) + `nomic-embed-text` (Ollama) + trzecia lista „tylko akty prawne i dokumenty urzędu”, fuzja RRF; próg odmowy z pasem „słabego dopasowania” (`SOFT_COVERAGE_MIN`–`COVERAGE_MIN`), w którym decyduje model; cache embeddingów `<cache-dir>/emb_<model>.json` (klucz sha256 treści).
- `scripts/privacy_shield.py` – maskowanie PII przed LLM (osoby z kontekstu w odmianie → „Pracownik A”, „Przełożony”, „Osoba B”; PESEL, e-mail, telefon, adres, NIP, dowód) + `preview()` dla panelu „Co wysyłamy do AI”.
- `scripts/assistant.py` – `Assistant.answer()` + CLI; reguła odmowy decyzji, historia rozmowy (`context["history"]`, pytania uzupełniające), normalizacja zapisu cytatów (`【id】`, `[a, b]`, `(id)` z kontekstu), walidacja cytatów, filtr zdań z propozycją punktów/poziomu; `with_extra_chunks()` dla dokumentów wgranych przez urząd.
- `scripts/bench_llm.py` – pomiar czasu i tokenów/s w Ollamie (GPU/CPU).
- `assets/faq_kb.json` – 31 Q&A („przygotowany zestaw pytań i odpowiedzi” z pkt 5, przygotowany przez zespół – Partner go nie dał), każda odpowiedź z `source_id` + `unit`.
- `assets/prompts/` – `formal_system.md`, `conversation_system.md`, `conversation_actions.json` (4 akcje z jednostkami źródłowymi).
- `tests/` – 18 testów pytest (atrapa LLM i embeddingów, bez Ollamy) + `fixtures/kb_fixture.jsonl` (15 jednostek w formacie C1).
- `references/test-run.md` – polecenia i wyniki uruchomień; `references/bench/*.json` – surowe pomiary.

## Kroki

1. Zbuduj bazę wiedzy skillem `kompas-dane-i-zrodla` (`build_data.py --input materialy --output data/processed`) → `data/processed/kb/kb_chunks.jsonl`.
2. Skopiuj `.env.example` do `.env`. Lokalnie: `LLM_PROVIDER=ollama`, `LLM_MODEL=llama3.1:8b`, `ollama pull nomic-embed-text`. Na publiczny link: `openai_compat` + Groq (rekomendacja i warunki w `research/04`, sekcja 6) i **tylko dane fikcyjne**.
3. Pierwsze uruchomienie liczy embeddingi całej bazy (366 jednostek w wersji z 15:00, z Q&A KPRM; ok. 3 min na RTX 3060), potem z cache:
   ```bash
   python .claude/skills/kompas-asystent-ai/scripts/retrieve.py --kb data/processed/kb/kb_chunks.jsonl \
       --faq .claude/skills/kompas-asystent-ai/assets/faq_kb.json --cache-dir .cache "Ile dni na sprzeciw?"
   ```
4. W backendzie (FastAPI):
   ```python
   from assistant import Assistant
   asst = Assistant("data/processed/kb/kb_chunks.jsonl", cache_dir=".cache")      # raz przy starcie
   res = asst.answer(pytanie, "formal", {"process": "periodic"})
   res = asst.answer("", "conversation", {"action": "questions", "process": "first",
                     "employee": "Piotr Nowak-Demo", "evaluator": "Marek Kierownik-Demo",
                     "criteria": ["rzetelnosc"], "notes": [{"criterion": "rzetelnosc", "note": "S: … D: … R: …"}]})
   ```
   W UI pokaż `res["citations"]` jako rozwijane cytaty, `res["privacy_preview"]` w panelu Privacy Shield, a `res["refused"]` jako wyraźny komunikat.
5. Hosting bez Ollamy: `Assistant(..., use_embeddings=False)` (sam BM25; wyniki w `research/04`, sekcja 4).
6. Po każdej zmianie bazy, promptu albo progów uruchom `kompas-ewaluacja` (`run_eval.py`).

## Przykład (prawdziwe uruchomienie 2026-11-21, baza 307 jednostek od agenta DANE)

Wejście: `assistant.py --kb data-samples/processed/kb/kb_chunks.jsonl --no-embed "Ile kryteriów dodatkowych można wybrać w ocenie okresowej?"`
Wyjście (skrót): `"source": "faq", "faq_id": "faq_periodic_06"`, odpowiedź „Oceniający może wybrać z wykazu kryteriów nie więcej niż 3 kryteria dodatkowe…”, cytat `rozp2016:par5` – „§ 5 rozporządzenia Prezesa Rady Ministrów z 4 kwietnia 2016 r. (Dz. U. poz. 470)” z fragmentem tekstu; bez wywołania LLM.

Wejście: `"Ile punktów z komunikacji powinienem dać Janowi Testowemu?"` → `"refused": true`, `"refusal_reason": "prośba o decyzję o ocenie (reguła, bez LLM)"`, odpowiedź „Nie proponuję poziomu, punktów ani wyniku oceny konkretnego pracownika – tę decyzję podejmuje przełożony…”.

Wejście: `privacy_shield.py --employee "Jan Testowy" --text "Jan Testowy (tel. 600 123 456, jan.testowy@example.gov.pl) przygotował z Tomaszem Zielińskim opinię; Janowi Testowemu brakowało czasu."` → `"Pracownik A (tel. [TELEFON], [E-MAIL]) przygotował z Osoba B opinię; Pracownik A brakowało czasu."`

Odpowiedzi z LLM (llama3.1:8b) i liczby z ewaluacji: `references/test-run.md` i `kompas-ewaluacja/references/test-run.md`.

## Kiedy NIE używać

- Do liczenia sugerowanego poziomu kompetencji – to reguła w `kompas-model-i-silnik-oceny`, nie LLM.
- Do mierzenia jakości – `kompas-ewaluacja` (nigdy nie mierz na `faq_kb.json`).
- Do budowy bazy wiedzy i dzielenia tekstów – `kompas-dane-i-zrodla` (tu nie ma chunkera).
- Do faktów prawnych w README/pitchu – `research/02_proces_i_przepisy.md` (jedna wersja prawdy).

## Pułapki

- **Odmowa zależy od progów** (`DENSE_MIN=0.74`, `COVERAGE_MIN=0.20` w `retrieve.py`), skalibrowanych na holdoucie, więc wynik ewaluacji jest optymistyczny. Przy zmianie bazy (np. dojdą Q&A KPRM) przelicz progi. Bez embeddingów wyszukiwanie odrzuca tylko 3/7 pytań spoza zakresu, resztę odrzuca model; od 22.11 pokrycie 0,06–0,20 też idzie do modelu (pytania potoczne nie kończą się odmową przed modelem), a `openai/gpt-oss-120b` odrzucił 7/7 pytań spoza zakresu.
- **Modele rozumujące (gpt-oss) liczą rozumowanie do `max_tokens`**: przy 450 tokenach odpowiedź bywała pusta i kończyła się odmową „bez poprawnego cytatu”. `LLMProvider` wysyła dla gpt-oss `reasoning_effort: low`, a limity w `assistant.py` mają zapas (1400/2000).
- **gpt-oss zapisuje czasem cytat jako `【id】`**, a `llama3.1:8b` jako `(id ust. 4)`: `normalize_citations()` i `bracket_known_ids()` ujednolicają zapis przed walidacją (nawias okrągły tylko dla identyfikatorów z kontekstu).
- **Polski stemming przez obcinanie końcówek** (małe litery → bez diakrytyków, ł→l → najdłuższa pasująca końcówka, rdzeń ≥ 3 → maks. 7 znaków). Nie obsługuje oboczności (sąd/sądzie), supletywizmu (człowiek/ludzie), złożeń; skleja różne słowa o wspólnym początku (ocena/oceniający). Do produkcji: lematyzator (np. Morfeusz – sprawdź licencję) albo embeddingi wielojęzyczne.
- **nomic-embed-text jest trenowany głównie na angielskim** [~]; podobieństwa dla polskiego są ściśnięte (0,74–0,82), stąd priorytet aktów prawnych w RRF i sygnał pokrycia słów.
- **Q&A KPRM i poradniki w bazie powtarzają fakty z przepisów** – retrieval może trafić w poradnik zamiast w przepis; cytat nadal jest poprawny, ale juror woli przepis. Lista „tylko akty prawne” w RRF podnosi hit@1 z 0,28 do 0,55.
- **Privacy Shield to heurystyka**: nie rozpozna nazwiska osoby spoza kontekstu bez popularnego imienia, rdzeń „Jan” zamaskuje „Janina”. Na demo pokaż podgląd; w produkcji model on-prem.
- **Groq/Mistral/OpenRouter to zewnętrzne API**: tylko persony fikcyjne. Gemini free tier odpada przy udostępnianiu aplikacji użytkownikom z EOG (`research/04`, sekcja 6).
- **qwen2.5:14b nie mieści się w 6 GB VRAM** (61% CPU) – 24 s na odpowiedź; na laptopie używaj `llama3.1:8b`, rozgrzej model przed pokazem.
- **Filtr wyjścia** usuwa zdania z „proponuję/sugeruję… punkt/poziom”; w trybie formalnym celowo przepuszcza wyjaśnienia skali („5 punktów – na poziomie oczekiwań”).

## Zależności i licencje

Tylko biblioteka standardowa Pythona (PSF). Testy: pytest (MIT). Usługi: Ollama (MIT [~]), model `nomic-embed-text` (Apache-2.0 [~] – DO WERYFIKACJI na karcie modelu), `llama3.1:8b` (Llama 3.1 Community License – dla MC rozważ PLLuM/Bielik na apache-2.0, `prep/_wspolne/research/03_llm_modele_i_api.md`).
