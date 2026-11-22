# System projektowy Kompasu Kompetencji

Żywa wersja z komponentami: `/design` w aplikacji (renderowana z tego samego `app/static/app.css`).

## Kierunek: Roman Pilaster (wariant lekki)

Neoklasyczny język instytucjonalny w wariancie lekkim: czysty trawertyn (`#f4f1ea`) zamiast wzorzystego tła, głęboka czerwień Oxblood dla decyzji przełożonego, antyczny mosiądz dla sugestii systemu i ornamentu, polska typografia szeryfowa Bona Nova oraz rzymska numeracja kroków `I–VI`. Bez ciężkich głowic, tympanonów i zbędnych zdobień – ornament pełni rolę strukturalną i sygnalizacyjną.

Główna zasada układu pozostaje stała: **okno = narzędzie, którego używasz** (wybór roli, asystent AI, Kompas poziomu, wynik oceny); **linie = dokument, który czytasz** (rejestry, arkusz, przepisy). Okno z fokusem podświetla pasek w Oxbloodzie.

| Motyw architektoniczny | Zastosowanie w Kompasie |
|---|---|
| Okno: romb 45° · tytuł · meander · romb 45°, obrys 1,5 px + linia mosiężna | narzędzia; makro `bar()` w `app/templates/_ui.html` |
| Meander (fryz SVG 24×10) | górna nawigacja `.topbar-mid` oraz paski okien `.win-hatch` |
| Kanelowane pilastry | pionowe krawędzie ekranu `/login` (22 px) oraz marginesy kroków `.sheet-margin` (3 px Oxblood + 8 px kanelury) |
| Kolumnada w znaku wodnym | pasy nagłówkowe `.band` (Pulpit, Panel HR, Źródła, `/design`), wygaszone poziomym gradientem |
| Reaktywny kompas na `<canvas>` (`[data-art]`, `[data-mark]`) | igła na sprężynie śledzi kursor i fokus klawiatury, kwadraciki odsuwają się o jedno pole siatki; na stronie błędu kompas „nie ma północy” |
| Cyfry rzymskie `I–VI` | kroki procesu (`.stepnav`, `.sheet-no`, filtr `roman` w `app/main.py`) w `Bona Nova SC` |

## Tokeny (`:root` w `app.css`)

Kontrast liczony wg WCAG 2.1; wszystkie pary tekst/tło spełniają AA (≥ 4,5:1), główne pary osiągają AAA (≥ 7,0:1).

| Token | Wartość | Znaczenie | Kontrast |
|---|---|---|---|
| `--paper` | `#f4f1ea` | czyste tło stron (trawertyn, bez `field.js`) | – |
| `--field` | `#fcfbf8` | okna, formularze, tabele, kafelki KPI, topbar, stopka | – |
| `--art` | `#eae4d7` | tło próbek, podgląd maskowania RODO | – |
| `--ink` | `#1c1716` | tekst główny, obrysy okien, cienie | 15,7:1 (17,1:1 na `--field`) |
| `--ink-2` | `#433b37` | tekst drugorzędny | 9,7:1 |
| `--ink-3` | `#635953` | etykiety, metadane, `::placeholder` | 6,0:1 (5,7:1 na `--moss`) |
| `--rule` / `--rule-2` | `#c8beae` / `#e0d8ca` | linie sekcji / wierszy | – |
| `--blue` | `#5c1022` | **Oxblood** – decyzja człowieka, karta sprawy, przyciski główne, aktywny krok | 12,0:1; biały na nim 13,5:1 |
| `--blue-deep` | `#3d0916` | odnośniki, najechanie na przycisk główny | 14,9:1 |
| `--blue-ink` | `#f5e8eb` | tło wybranego opisu zachowania / zaznaczonego kryterium | – |
| `--blue-soft` | `#efd1d8` | tekst drugorzędny na karcie sprawy (`.docket`) | 9,5:1 na `--blue` |
| `--brass` / `--blue-art` | `#7c5c1e` | **antyczny mosiądz** – sugestia systemu, nagłówki tabel, obrys przycisków drugorzędnych, akcent rastra kompasu | 5,5:1 (6,0:1 na `--field`, 5,7:1 na `--sug-bg`) |
| `--brass-line` | `#b5934c` | podwójne linie `3px double`, fryz meandrowy, wewnętrzny obrys okien | – |
| `--moss` | `#f2ead7` | „tu jesteś”, tło sugestii, kontrastowa flaga `.docket .flag.soon` (tekst `--ink`: 14,8:1) | – |
| `--sug-bg` | `#faf5e8` | tło pól i komórek sugestii | – |
| `--ok` / `--ok-wash` | `#1f5c3a` / `#e8f3ec` | ocena `POZYTYWNA` i potwierdzenie zapisu | 7,0:1 |
| `--red` / `--red-wash` | `#b91c1c` / `#fdeaea` | wyłącznie skutek prawny: ocena `NEGATYWNA`, termin minął | 5,7:1 (5,6:1 na `--red-wash`) |

## Cztery stałe role znaczeniowe

- **Sugestia systemu** – przerywany antyczny mosiądz (`2px dashed var(--brass)`) na tle `--moss`/`--sug-bg` i etykieta „sugestia”. Tak samo propozycja arkusza z OSP i propozycje AI. Sugerowany przycisk nigdy nie jest automatycznie zaznaczony.
- **Decyzja przełożonego** – pełne wypełnienie Oxblood (`var(--blue)`). Wyłącznie decyzje wchodzą do wyniku i arkusza PDF.
- **Tu jesteś** – jasny mosiądz (`var(--moss)`) z wyraźną linią Oxblood (aktywny krok, kryterium, zakładka). Nie oznacza wyboru oceny.
- **Skutek prawny i potwierdzenie** – czerwień (`var(--red)`) wyłącznie dla oceny negatywnej, obowiązkowego uzasadnienia i przekroczonego terminu; zieleń (`var(--ok)`) dla oceny pozytywnej i potwierdzenia zapisu.

## Kroje (OFL, hostowane lokalnie)

Cztery rodziny na licencji SIL OFL 1.1 w `app/static/fonts/` (zestawy `latin` i `latin-ext` z pełnymi polskimi znakami `ĄĆĘŁŃÓŚŹŻ`; pliki licencji obok `.woff2`). Zero zewnętrznych CDN-ów, pełne działanie offline.

- `--display`: **Bona Nova** (400, 700, 400 italic) – `h1`, `h2`, tytuły pasów, kart, propozycji i sekcji; kursywa dla cytatów prawnych (`.statute`, `blockquote.quote`, `.fragment`).
- `--sc`: **Bona Nova SC** (400, 700) – `.brand`, `.wordmark`, cyfry rzymskie `I–VI` (`.stepnav .no`, `.sheet-no`), liczniki KPI (`.counters dd`), werdykt `.result-word`, `.error-code`.
- `--sans`: **Archivo Variable** (oś szerokości 62–125 %, grubość 100–900) – treść (15/1,55), formularze, tabele, przyciski.
- `--mono`: **IBM Plex Mono** (400, 500, 600) – paski okien `.win-title`, etykiety `.part-label`, nagłówki tabel `th`, flagi, sygnatury, daty, punkty, wzory (przecinek dziesiętny: „6,33”), stopka.
- Pikselowy renderer tekstu `data-px` został usunięty – wszystkie nagłówki i liczniki korzystają z natywnej typografii `Bona Nova` / `Bona Nova SC`.
- Wczytywanie: `<link rel="preload">` w `base.html` dla `archivo`, `bona-nova-700`, `bona-nova-sc-700` i `ibm-plex-mono-400` (`latin` i `latin-ext`), `font-display: swap` i zapasowe metryki (`Bona Nova Fallback`, `Archivo Fallback`, `IBM Plex Mono Fallback`).

## Tło i reaktywny kompas (`app/static/art.js`)

- Skrypt `field.js` (animowane pole magnetyczne i siatka kropek) jest wyłączony – tło stron to spokojny, jednolity trawertyn `#f4f1ea`.
- Reaktywny kompas `<canvas>` (`[data-art="compass"]` oraz miniatura `[data-mark]` w topbarze) pozostaje w pełni aktywny: igła na tłumionej sprężynie ($\zeta \approx 0{,}5$) śledzi kursor i element z fokusem klawiatury, a luźne kwadraciki odsuwają się od kursora o jedno pole siatki. W pasach `.band` i na ekranie logowania kompas jest wizualnie wyciszony (`opacity: 0,26–0,30`), a na stronie błędu (`404`) pozostaje wyraźny i „nie ma północy”.
- Poza ekranem i w ukrytej karcie pętla `requestAnimationFrame` zatrzymuje się. Przy `prefers-reduced-motion: reduce` kompas rysuje pojedynczą statyczną klatkę.

## Nawigacja

Stała u góry (`position: fixed`, miejsce rezerwuje `.app`). Tło `--field`, górna belka `4px solid var(--blue)`, dolna linia `3px double var(--brass-line)`, fryz meandrowy w `.topbar-mid`. Trzy stany w `html[data-nav]` przełączane w `app.js` z histerezą (24 px w dół, 72 px w górę):

- `top` – na górze strony (62 px).
- `compact` – przewijanie w dół (46 px, skrót kroków procesu i subtelny pasek postępu czytania w fryzie).
- `full` – przewijanie w górę lub fokus w pasku (62 px).

PDF arkusza ma własny krój (DejaVu Sans w `kompas-dokumenty-i-terminy`) – wzór urzędowy z rozporządzenia, nie ekran.

## Układ

Nagłówek (kompas, nazwa, nawigacja wg roli, meander, sygnatura, rola) → kroki z cyframi rzymskimi `I–VI` → karta sprawy (`.docket`, Oxblood + podwójna linia mosiężna) → sekcja z marginesem kanelowanym i treścią → okno asystenta. Na ekranie wskaźników okno Kompasu poziomu pływa przy dolnej krawędzi. Od 1280 px trzy obszary; poniżej 1280 px asystent wysuwany; poniżej 1100 px grafika w pasie ustępuje tekstowi; na smartfonach komunikat blokady po wykryciu urządzenia mobilnego (`html.is-mobile`: `Sec-CH-UA-Mobile`, `User-Agent`, `navigator.userAgentData.mobile` oraz dotykowy ekran telefonu – bez blokowania wąskich okien na komputerze).

## Asystent AI

Dwa miejsca, jeden komponent odpowiedzi (`partials/_answer.html`). Panel z prawej towarzyszy każdemu krokowi: najnowsza odpowiedź na górze, rozmowa przechodzi z krokiem (sessionStorage karty, czyszczone przy „Zmień rolę”). Pełny widok `/asystent` to okno rozmowy w kolejności czytania (najnowsza na dole, pole pytania pod rozmową, Enter wysyła), pod nim przykładowe pytania w trzech kolumnach tematów, niżej okno asystenta rozmowy z wyborem oceny i rejestr bazy wiedzy. Na pulpicie drugie okno „Asystent AI” z dwoma kafelkami jak na grafice MC: asystent formalny i asystent rozmowy. Odmowa ma szarą linię z lewej i podpowiedź, jak zapytać inaczej; lista punktów z modelu renderuje się jako `<ul>`, a każdy punkt ma swój odnośnik `[n]`.

Asystent oceny zachowań to okno nad wskaźnikami w karcie kryterium. Propozycja AI ma przerywaną mosiężną ramkę i etykietę „propozycja AI” – ten sam znak co sugestia Kompasu poziomu; po zaznaczeniu ramka przechodzi na poziom w formularzu, a wybór przełożonego zostaje w Oxbloodzie. Przyjęta propozycja traci przerywaną ramkę na liście („Zaznaczono”).

## Profil ocen cząstkowych (ekran „Wynik oceny i arkusz”)

Przyrząd radialny generowany po stronie serwera (`app/radar.py` + `partials/_radar.html`), interakcja w `app/static/radar.js`. Dane wyłącznie z wyniku silnika.

- Decyzja przełożonego: obrys pełnym Oxbloodem z wypełnieniem i pełne kwadraty.
- Sugestia systemu: przerywany obrys w antycznym mosiądzu i puste kwadraty.
- Skutek prawny zgłoszony przez silnik: czerwień `--red`.
- Tabela 1 ze wszystkimi wzorami znajduje się pod wykresem (zwinięta).

## Słownictwo i styl tekstów

Jedno pojęcie – jedna nazwa na wszystkich ekranach:

| Mówimy | Nie mówimy | Uwagi |
|---|---|---|
| ocena (sprawa jednej osoby) | proces | „proces” zostaje tylko w kodzie i API |
| ocena cząstkowa | punktacja, wynik kryterium | punkty z arkusza: 1/3/5/7/9 albo 3/5/7 |
| kryterium (ocena okresowa), element oceny (pierwsza ocena) | kompetencja | kompetencja to pojęcie modelu MC, nie arkusza |
| sugestia systemu | rekomendacja, propozycja oceny | „propozycja” tylko dla arkusza B/C i kryteriów z OSP |
| decyzja przełożonego | ocena końcowa przełożonego | tylko decyzje wchodzą do wyniku |
| wskaźnik, poziom 1–5 | zachowanie, stopień | |
| ślad decyzji | log, historia | |
| Część I, Część II, Część III | część I | jak w arkuszu – wielką literą |

Zasady: do przełożonego zwracamy się w 2. osobie („wybierasz”, „zaznacz”), bez form rodzajowych w czasie przeszłym. Polskie cudzysłowy „…”, półpauza ze spacjami, przecinek dziesiętny, daty `dd.mm.rrrr`. Kody reguł silnika (`P-POSITIVE:`) i znaczniki pewności (`[✓]`, `[~ …]`) usuwa filtr `plain`. Teksty `REFUSAL` i `DECISION_REFUSAL` asystenta są częścią promptu – ich zmiana unieważnia pamięć podręczną odpowiedzi demo.

## Zasady

- Tak: okno tylko dla narzędzia; treść dokumentu na liniach, bez ramek.
- Tak: podstawa prawna przy każdym kroku i komunikacie.
- Tak: 4 lokalne kroje OFL bez zewnętrznych CDN-ów.
- Nie: zaokrąglenia, rozmyte cienie, pikselowy renderer `data-px`, animowane tło `field.js`, emoji jako ikony.
- Nie: czerwień jako ozdoba – tylko skutek prawny.
- Tryb wysokiego kontrastu (`forced-colors`): systemowe pola wyboru zamiast rysowanych.
