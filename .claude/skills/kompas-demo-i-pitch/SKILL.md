---
name: kompas-demo-i-pitch
description: Scenariusz demo, wideo do 2 minut, prezentacja do 10 slajdów i odpowiedzi na pytania jury dla zadania KOMPAS KOMPETENCJI (Ministerstwo Cyfryzacji, BDG), z fikcyjnymi personami demo i słownictwem Partnera. Użyj, gdy zespół prosi „przygotuj demo”, „scenariusz dla jury”, „persony do demo”, „konspekt prezentacji”, „nagrajmy wideo”, „co jury zapyta”, „jak mówić o AI Act” albo „próba generalna Kompasu”.
---

# Demo i pitch: Kompas kompetencji

Jedna myśl, która ma zostać w głowie jurora z BDG: **„Kompas podpowiada na podstawie zachowań, decyduje przełożony, a każda odpowiedź asystenta ma źródło.”** Wszystko w demo ma ją ilustrować.

Scenariusz minuta po minucie, wideo, konspekt 10 slajdów, plan awaryjny i 10 pytań jury z odpowiedziami są w `research/07_plan_i_demo.md` (po instalacji: `.claude/hn-prep/kompas_kompetencji/research/07_plan_i_demo.md`). Ten skill mówi, jak z tego korzystać i czego pilnować. Ogólne zasady pitchu, pomiaru czasu i zgłoszenia: `hn-pitch-final` i `hn-zgloszenie` – tu tylko to, co specyficzne dla MC.

## Kiedy używać, a kiedy nie

- Używaj od wieczora pierwszego dnia (ścieżka okresowa działa) do pitchu: przygotowanie danych demo, próba, wideo, slajdy, pytania jury.
- Nie używaj do reguł oceny ani przepisów (to `kompas-wiedza-domenowa` i `kompas-model-i-silnik-oceny`) ani do mierzenia jakości asystenta (`kompas-ewaluacja`). Liczby na slajdach biorą się wyłącznie z `run_eval.py` i testów, nigdy z pamięci.

## Kroki

1. **Wgraj persony** z `assets/personas.json` do bazy demo (Anna – arkusz B z Częścią III, Jan – arkusz C bez Części III, Ewa – główna persona demo, Piotr – pierwsza ocena z egzaminem „nie dotyczy”). Oceniający: Marek Kierownik-Demo; HR: Zofia Kadrowa-Demo. Konta demo logują się jednym kliknięciem (pkt 4: linki bez dodatkowych uprawnień).
2. **Sprawdź wymogi pkt 6 na żywym prototypie** checklistą `kompas-ewaluacja/references/testy_akceptacyjne.md`: rozpoczęcie procesu → kryteria i kompetencje → ocena wybranych wskaźników → sugerowany poziom → decyzja przełożonego, plus pytania do asystenta.
3. **Przećwicz 5 pytań do asystenta** na żywo (różnych od pytań w `eval_holdout.json`, żeby nie mylić demo z pomiarem): termin sprzeciwu od oceny okresowej; kiedy ocena okresowa jest negatywna; ile kryteriów dodatkowych można wybrać; kiedy odbywa się rozmowa wstępna w pierwszej ocenie; jedno pytanie spoza bazy (np. o wynagrodzenie) → odmowa. Zapisz odpowiedzi w cache (`.llm_cache/`) na wypadek awarii API.
4. **Wideo do 2 minut i 10 slajdów** według `research/07`. Slajd 6 = liczby z `run_eval.py` z opisem, na jakim zbiorze powstały.
5. **Pytania jury:** tabela w `research/07`; trudne pytania o RODO, AI Act i wdrożenie poprzyj `research/05` i `research/04`.
6. **Próba generalna** z zegarem w dwóch wariantach (3 i 5 minut, czas pitchu nie jest podany – `hn-pitch-final`) i z wyłączonym internetem (`LLM_PROVIDER=ollama`).

## Przykład

Wejście (zespół): „Juror pyta: «A jeśli przełożony się nie zgadza z sugestią?» – daj odpowiedź na 20 sekund.”

Wyjście (skill):
> „Wtedy wybiera inny poziom – sugestia jest tylko podpowiedzią, tak jak wymaga pkt 3 treści zadania. System zapisuje w śladzie decyzji, że przełożony odszedł od sugestii, i prosi o krótką notatkę, ale jej nie wymaga. Pokażę: tu sugestia «na poziomie oczekiwań», wybieram «powyżej oczekiwań», notatka «samodzielnie przygotował analizę ryzyk» – i wpis w historii procesu.”
> (pokaż na ekranie krok 5 scenariusza z `research/07`)

## Słownictwo Partnera (mów jak BDG i przepisy)

| Mów | Unikaj | Dlaczego |
|---|---|---|
| przełożony, oceniający; oceniany | „user”, „ewaluator” | Brzmienie przepisów i arkuszy |
| urzędnik służby cywilnej / pracownik służby cywilnej | „pracownik” zamiennie | Od statusu zależy m.in. Część III arkusza |
| kryteria obowiązkowe, kryteria dodatkowe | „kompetencje wybrane” | Nazwy części arkusza oceny okresowej |
| ocena cząstkowa, ogólny poziom spełnienia kryteriów, ocena pozytywna/negatywna | „score”, „wynik AI” | Nazwy pól arkusza |
| wskaźniki behawioralne, opisy poziomów, poziom spełniania kompetencji | „ankieta”, „pytania” | Język pełnej treści (pkt 3) i modelu MC |
| sugerowany poziom (podpowiedź systemu), decyzja przełożonego | „AI ocenia”, „rekomendacja AI” | Pkt 3 i 5: AI nie decyduje o poziomie |
| opis stanowiska pracy (OSP) | „job description” | Materiały MC |
| rozmowa wstępna, sprawozdanie, pierwsza ocena; rozmowa oceniająca | „onboarding review” | Rozporządzenie z 2015 r. |
| indywidualny program rozwoju zawodowego (IPRZ), wnioski dotyczące rozwoju zawodowego | „plan rozwoju AI” | Arkusze ocen |
| EZD RP, system kadrowy (np. QNT) | „integracja z ERP” | Pkt 5 pełnej treści |

## Pułapki

- **„AI ocenia pracownika”** – jedno takie zdanie w pitchu przekreśla argument zgodności (pkt 5) i otwiera pytanie o załącznik III AI Act. Mów „system liczy podpowiedź z Pana/Pani wyborów, decyduje przełożony”.
- **Prawdziwe dane.** Tylko persony z `assets/personas.json`. Model kompetencji i OSP z MC nie muszą być publiczne – w publicznym wideo i repo pokazuj je dopiero po zgodzie mentora (pytanie 4 w README).
- **Obietnice integracji.** EZD i system kadrowy to w prototypie kontrakty API (pkt 5 nie wymaga integracji). Nie mów „zintegrowane”, mów „gotowe interfejsy do integracji”.
- **Liczby bez kontekstu.** Każda liczba o jakości asystenta z nazwą zbioru i liczbą pytań (np. „N pytań spoza bazy FAQ”).
- **Model offline nierozgrzany.** Pierwsza odpowiedź Ollamy po starcie trwa dłużej – rozgrzej model przed pitchem.
- **Smartfon.** Jeśli juror otworzy link na telefonie, zobaczy celowy komunikat (pkt 2: „System nie ma być dostępny na smartfonach”) – powiedz to wprost w README zgłoszenia, żeby nie wyglądało na błąd.

## Zależności

Brak skryptów i zależności. Persony to dane fikcyjne bez licencji zewnętrznych.
