# Terminy i statusy procesu oceny – tabela dla `scripts/deadlines.py`

Stan na 2026-11-21. Ustawa: tekst jednolity Dz. U. 2026 poz. 590, stan prawny na 2026-04-14 (plik `kompas-dane-i-zrodla/assets/ustawa_sc/ustawa_o_sluzbie_cywilnej.txt`, pobrany przez agenta PRAWO). Rozporządzenia: PDF-y z materiałów Partnera (`materialy/…`). Poradniki KPRM z 2016 r. (materiały Partnera). Szczegóły prawne i zmiany stanu prawnego: `research/02_proces_i_przepisy.md` (jedna wersja prawdy).

Pewność: [✔] sprawdzone w tekście przepisu/poradnika, [~] interpretacja albo źródło wtórne, [?] hipoteza → DO WERYFIKACJI.

## Ocena okresowa

| Czynność (`task`) | Termin | Podstawa | Pewność |
|---|---|---|---|
| Rozmowa i ustalenie kryteriów, zapoznanie z kryteriami i terminem (część I) – `kryteria` | 30 dni od sporządzenia na piśmie poprzedniej oceny albo od zatrudnienia na czas nieokreślony | § 7 pkt 1 rozp. 2016 (Dz. U. poz. 470), s. 2 PDF | [✔] |
| To samo po ocenie negatywnej | 7 dni od sporządzenia na piśmie oceny negatywnej | § 7 pkt 2 rozp. 2016 | [✔] |
| Sporządzenie oceny – `ocena` | co 24 miesiące; liczone od sporządzenia poprzedniej oceny albo zatrudnienia na czas nieokreślony; data końcowa = data odpowiadająca dacie początkowej (np. 4.12.2013 → 4.12.2015). Gdy w części I wpisano termin – używamy go | art. 81 ust. 4 ustawy; poradnik „Oceny okresowe…” 2016, s. 8–9; § 6 ust. 1 rozp. 2016 | [✔] |
| Przedłużenie terminu 24 mies. | o czas usprawiedliwionej nieobecności dłuższej niż miesiąc | art. 81 ust. 7 ustawy | [✔] (zasada) / [~] (czy liczyć dni kalendarzowe całej nieobecności – przyjęto tak) |
| Zmiana terminu przez oceniającego | 4 przypadki, gdy od ostatniej oceny upłynęło > 6 mies.; pisemne zawiadomienie ocenianego, kopia do arkusza | art. 81 ust. 8 ustawy; § 8 rozp. 2016 | [✔] (silnik tylko przyjmuje nowy `evaluation_deadline`) |
| Ponowna ocena po ocenie negatywnej | niezwłocznie po upływie 6 miesięcy od dnia zapoznania się z oceną | art. 81 ust. 9 ustawy; poradnik s. 13 | [✔] |
| Zmiana stanowiska (istotna zmiana obowiązków) – `kryteria_po_zmianie` | gdy w ciągu 6 mies. od ustalenia kryteriów/ostatniej oceny: ponowne czynności z § 5–6 w 30 dni od zmiany; termin oceny bez zmian | § 9 ust. 1 rozp. 2016 | [✔] |
| Ocena przy zmianie stanowiska – `ocena_przy_zmianie` | nie wcześniej niż 7 dni przed i nie później niż 30 dni po zmianie (gdy od ostatniej oceny > 6 mies.) | art. 81 ust. 6 ustawy; § 9 ust. 2 rozp. 2016 | [✔] |
| Zapoznanie z oceną | niezwłocznie (bez liczby dni) | art. 81 ust. 3 ustawy; § 12 ust. 1 rozp. 2016 | [✔] |
| Sprzeciw – `sprzeciw` | 7 dni od dnia zapoznania się z oceną, do dyrektora generalnego urzędu | art. 83 ust. 1 ustawy | [✔] |
| Przesunięcie końca terminu sprzeciwu z soboty/święta | na najbliższy dzień roboczy | art. 115 KC (w zw. z art. 300 KP) – z pamięci | [~] DO WERYFIKACJI: czy MC stosuje art. 115 KC do sprzeciwu; lista świąt w kodzie z ustawy o dniach wolnych (Wigilia od 2025 r. – [~]) |
| Rozpatrzenie sprzeciwu – `rozpatrzenie_sprzeciwu` | 14 dni od wniesienia | art. 83 ust. 3 ustawy | [✔] |
| Odwołanie do sądu pracy | 14 dni od doręczenia decyzji albo upływu terminu na rozpatrzenie | art. 83 ust. 5 ustawy | [✔] (w silniku nieliczone – brak daty doręczenia w modelu) |

## Pierwsza ocena

| Czynność | Termin | Podstawa | Pewność |
|---|---|---|---|
| Rozmowa wstępna – `rozmowa_wstepna` | 21 dni od nawiązania stosunku pracy; przy zastępstwie – 21 dni od ustalenia, że oceniany będzie podlegać pierwszej ocenie | § 3 rozp. 2015 (Dz. U. poz. 1144) | [✔] |
| Umowa na pierwszy okres | 12 miesięcy (koniec = start + 12 mies. − 1 dzień, jeśli brak `contract_end`) | art. 35 ust. 3 ustawy | [✔] / [~] (sposób liczenia dnia końcowego) |
| Okno pierwszej oceny – `ocena` | nie wcześniej niż po upływie 8 mies. od nawiązania stosunku pracy (od dnia następnego po dacie odpowiadającej), nie później niż miesiąc przed upływem umowy (dzień przed datą odpowiadającą) | art. 38 ust. 1 ustawy; poradnik „Pierwsza ocena…” 2016, s. 8 (liczenie wg art. 112 KC) i s. 9 (przykład: 2 maja – 30 lipca 2016 r.) | [~] – reguła odtworzona z przykładu poradnika (data zatrudnienia w przykładzie wywnioskowana: 1.09.2015, bo tylko ona daje obie granice); test `test_first_eval_window_matches_kprm_guide_example` |
| Termin na sprawozdanie – `sprawozdanie` | okno (data początkowa i końcowa) po upływie 8 miesięcy, tak by ocena zmieściła się w oknie; długość okna niesztywna (domyślnie 14 dni – ustawienie, nie przepis) | § 4 ust. 1 rozp. 2015; poradnik s. 9 | [✔] zasada / [~] długość domyślna |
| Zakres sprawozdania | co najmniej 7 miesięcy przepracowanego okresu | § 6 ust. 1 rozp. 2015 | [✔] |
| Nowy termin sprawozdania | przedłużenie o czas usprawiedliwionej nieobecności / pracy poza miejscem pracy | § 5 ust. 1 rozp. 2015 | [✔] (silnik przyjmuje nowe `report_deadline`) |
| Rozmowa oceniająca | niezwłocznie po złożeniu sprawozdania albo po upływie terminu; może uczestniczyć kierujący komórką | § 8 ust. 1–2 rozp. 2015 | [✔] |
| Zapoznanie z pierwszą oceną | niezwłocznie; oryginał do akt osobowych, kopia dla ocenianego | § 11 rozp. 2015 | [✔] |
| Sprzeciw | nie dotyczy (art. 83 ustawy dotyczy oceny okresowej) | art. 83 ust. 1 ustawy | [~] DO WERYFIKACJI z mentorem: brak trybu odwoławczego od pierwszej oceny w rozporządzeniu 2015 |

## Statusy (`STATUSES`, `TRANSITIONS` w `deadlines.py`)

`nie_rozpoczeta` → `kryteria_ustalone` (pierwsza ocena: „rozmowa wstępna odbyta”) → `w_trakcie` → `do_podpisu` → `zakonczona` → (`sprzeciw` → `zakonczona` albo `w_trakcie`, tylko ocena okresowa). Powrót `w_trakcie` → `kryteria_ustalone` przy zmianie stanowiska (§ 9 ust. 1). Flagi zdarzeń: `zbliza_sie` (≤ `--warn-days`, domyślnie 14), `po_terminie` (termin minął, brak `done_on`).

## Liczenie dat (konwencje w kodzie)

- Dni: dzień zdarzenia się nie wlicza (art. 111 § 2 KC) → `data + n dni` [~].
- Miesiące: data odpowiadająca; gdy jej brak – ostatni dzień miesiąca (art. 112 KC) → `add_months` [✔ zgodnie z poradnikami, które powołują art. 112 KC].
- Weekend/święto: przesuwamy tylko koniec terminu na czynność ocenianego (sprzeciw) [~].
