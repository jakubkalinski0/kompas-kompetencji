# Wdrożenie

## Render (przygotowana konfiguracja)

Wersja demo na HackNation działa na komputerze zespołu i jest udostępniana przez tunel ngrok, z limitami zapytań jak poniżej. Ta sekcja opisuje konfigurację pod hosting Render.

Konfiguracja: [render.yaml](../render.yaml) (Blueprint, darmowa instancja, Frankfurt, Python 3.13.1, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/healthz`). Zmienna `LLM_API_KEY` ma `sync: false`, więc klucz wpisuje się ręcznie w panelu Render; `SESSION_SECRET` generuje Render. Model: `openai/gpt-oss-120b` przez API Groq zgodne z OpenAI (`LLM_PROVIDER=openai_compat`).

## Skąd dane na serwerze (decyzja z 21.11.2026)

Przetworzone dane leżą w prywatnym repozytorium zespołu, w katalogu `deploy/processed/`, a Render używa natywnego środowiska Python, bez Dockera.

- `build_data.py` potrzebuje `pdftotext` (poppler). Natywne środowisko Render go nie gwarantuje, a pakietów systemowych nie da się w nim doinstalować. Docker z `poppler-utils` wniósłby do obrazu produkcyjnego program na licencji GPL, czego unikamy, bo prawa do kodu mogą przejść na MC.
- Aplikacja w działaniu nie potrzebuje `pdftotext`: PDF tworzy reportlab, a OSP czyta biblioteka standardowa. Poppler służy tylko do zbudowania danych i do testów.
- `build_data.py` jest deterministyczny, więc `deploy/processed/` jest bajtowo równe świeżemu buildowi. Pilnuje tego test `test_deploy_data_matches_fresh_build` (pomijany bez `pdftotext` i materiałów). Po zmianie materiałów: `python .claude/skills/kompas-dane-i-zrodla/scripts/build_data.py --input materialy --output deploy/processed`.
- Dane MC (model kompetencji i OSP) nie trafiają do publicznego repozytorium. Publiczną kopię tworzy `scripts/export_public.py`: wycina katalogi z danymi, a potem skanuje kopię „odciskami” tekstów modelu i OSP i przerywa, jeśli któryś znajdzie.

## Asystent na serwerze

- Wyszukiwanie: sam BM25 (`KOMPAS_EMBEDDINGS=0`), bo na Render nie ma Ollamy. Pomiar wpływu: [ewaluacja.md](ewaluacja.md).
- Odpowiedzi demo: `scripts/warm_demo_cache.py` zapisuje odpowiedzi Groq na pytania z przycisków przykładowych, pytanie spoza bazy i propozycje kryteriów z przykładowych OSP w `deploy/llm_cache/`, a Render czyta je przez `LLM_CACHE_DIR`. Odpowiedzi przetrwają uśpienie instancji i nie zużywają limitu. Klucz cache to skrót całego zapytania (model, prompt, kontekst), więc po zmianie bazy wiedzy albo promptu skrypt trzeba uruchomić ponownie; `LLM_REPLAY=1` sprawdza bez wywołań API, czy wszystkie pytania demo trafiają w cache. Pliki nie zawierają klucza API.
- Limity darmowego Groq: 8000 tokenów na minutę i 200 tys. dziennie. Aplikacja przepuszcza do modelu najwyżej 4 wywołania na minutę na instancję i 30 na godzinę na sesję; odpowiedzi z FAQ i odmowy regułą nie wywołują modelu. Po przekroczeniu limitu użytkownik widzi zrozumiały komunikat.

## Ograniczenia darmowego planu

Instancja usypia po 15 minutach bez ruchu, a pierwsze otwarcie trwa wtedy do minuty. Dysk jest nietrwały: procesy założone przez jurorów znikają po restarcie, a persony i przykładowe oceny ładują się przy każdym starcie. Jurorzy logujący się na to samo konto demo nie widzą swoich procesów nawzajem (osobna piaskownica dla każdej sesji), a przykładowe oceny Anny, Jana i Piotra są tylko do podglądu.

## W urzędzie

- Serwer z Pythonem 3.13 i `pip install -r requirements.txt`; SQLite można zastąpić bazą urzędu.
- Model lokalnie w Ollamie (`LLM_PROVIDER=ollama`), żeby treść notatek i pytań nie opuszczała sieci urzędu; wtedy wraca też wyszukiwanie hybrydowe.
- Integracje (propozycja kontraktu, `/api/v1/integrations/contract`): import danych pracowników i struktury z systemu kadrowego, eksport kompletu dokumentów oceny do EZD RP (w prototypie makieta zwracająca 202 i sumę SHA-256 pakietu), przypomnienia przez pocztę urzędu (w prototypie zapis w logu).
- Role i uprawnienia: przełożony, kadry, kierownik komórki i pracownik dostają dane z białej listy pól (`rbac.json` w `kompas-dokumenty-i-terminy`).
