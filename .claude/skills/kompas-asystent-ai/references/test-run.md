# test-run: kompas-asystent-ai

Uruchomienia z 2026-11-21 na laptopie z GPU (i7-11370H, RTX 3060 Laptop 6 GB, Ollama 0.40.16), z katalogu `prep/kompas_kompetencji/` (w repo rozwiązania: z katalogu głównego, baza w `data/processed/`). Baza wiedzy: `data-samples/processed/kb/kb_chunks.jsonl` z `build_data.py` – 366 jednostek (stan 15:00, z Q&A KPRM i ustawą t.j. Dz. U. 2026 poz. 590).

## Testy pytest (atrapa LLM i embeddingów, bez Ollamy)

```bash
cd .claude/skills/kompas-asystent-ai && ../../../.venv/Scripts/python -m pytest tests -q
```
Wynik 15:01: `18 passed in 0.37s`.

## Retrieval (warstwa FAQ + BM25 + embeddingi)

```bash
python -X utf8 .claude/skills/kompas-asystent-ai/scripts/retrieve.py --kb data-samples/processed/kb/kb_chunks.jsonl \
  --faq .claude/skills/kompas-asystent-ai/assets/faq_kb.json --cache-dir .cache "Ile dni ma pracownik na sprzeciw od oceny okresowej?"
```
Wynik 15:02 (skrót): `"mode": "faq"`, `faq_periodic_13` („W jakim terminie i do kogo wnosi się sprzeciw od oceny okresowej?”), `faq_score 0.8`, trafienie `ustawa_sc:art83` – „art. 83 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej (Dz. U. 2026 poz. 590)”, fragment „Od oceny okresowej służy, w terminie 7 dni od dnia zapoznania się z oceną, sprzeciw do dyrektora generalnego urzędu”, `"refuse": false`.

## Odmowa decyzji o ocenie (reguła, bez LLM)

```bash
python -X utf8 .claude/skills/kompas-asystent-ai/scripts/assistant.py --kb data-samples/processed/kb/kb_chunks.jsonl --no-embed \
  "Ile punktów z komunikacji powinienem dać Janowi Testowemu?"
```
Wynik 15:02: `"refused": true`, `"refusal_reason": "prośba o decyzję o ocenie (reguła, bez LLM)"`, `"source": "rule"`, odpowiedź „Nie proponuję poziomu, punktów ani wyniku oceny konkretnego pracownika – tę decyzję podejmuje przełożony…”.

## Privacy Shield

```bash
python -X utf8 .claude/skills/kompas-asystent-ai/scripts/privacy_shield.py --employee "Jan Testowy" \
  --text "Jan Testowy (tel. 600 123 456, jan.testowy@example.gov.pl) przygotował z Tomaszem Zielińskim opinię."
```
Wynik 15:02: `"masked_text": "Pracownik A (tel. [TELEFON], [E-MAIL]) przygotował z Osoba B opinię."`, 4 zamiany, 0 ostrzeżeń.

## Pomiar modeli w Ollamie (`scripts/bench_llm.py`, uruchomił subagent AI ok. 14:40)

Surowe wyniki: `references/bench/bench_gpu.json`, `references/bench/bench_cpu.json`. Pytania z kontekstem z bazy wiedzy (434–755 tokenów promptu).

| Model | Tryb | Zimny start | Mediana odpowiedzi | Maks. | Tokeny/s (mediana) |
|---|---|---|---|---|---|
| `llama3.1:8b` | laptop z GPU | 26,7 s | 6,1 s | 16,2 s | 10,9 |
| `llama3.2:3b` | CPU (`num_gpu: 0`) | 73,2 s | 37,9 s | 38,8 s | 3,8 |
| `qwen2.5:14b` | laptop z GPU (61% na CPU, nie mieści się w 6 GB) | – | ok. 24 s | – | – |

Przykład odpowiedzi `llama3.1:8b`: „W terminie 21 dni od dnia nawiązania z ocenianym stosunku pracy. [rozp2015:par3]” (5,7 s). Wniosek: na laptopie demo `llama3.1:8b` z rozgrzaniem; `qwen2.5:14b` za wolny. Wiersz `qwen2.5:14b` pochodzi z raportu subagenta (pomiar nie trafił do pliku JSON) [~].

Wyniki z generowaniem odpowiedzi na całym zbiorze testowym: `kompas-ewaluacja/references/test-run.md`.

## Połączenie z Groq (2026-11-21, ok. 16:00)

Pierwsze zapytanie `llm_provider.py chat "…"` z `LLM_PROVIDER=openai_compat` (Groq) skończyło się błędem `HTTP 403 … error code: 1010`: Cloudflare przed `api.groq.com` odrzuca domyślny nagłówek `User-Agent: Python-urllib/3.x`. Poprawka w `scripts/llm_provider.py` (`_post`): własny nagłówek `User-Agent: kompas-kompetencji/0.1 (python-urllib)` i `Accept: application/json`. Po poprawce: odpowiedź w 1,09 s (`openai/gpt-oss-120b`, 107 tokenów promptu); `pytest tests -q` – 18 passed.

Uwaga merytoryczna z tego testu: samo zapytanie do modelu **bez bazy wiedzy** dało błędną odpowiedź („14 dni od dnia jej otrzymania”, a art. 83 ust. 1 ustawy mówi o 7 dniach od zapoznania się z oceną). Dlatego asystent formalny odpowiada wyłącznie z wyszukanych jednostek z cytatem albo odmawia – przez `assistant.py`, nigdy bezpośrednim `chat()`.
