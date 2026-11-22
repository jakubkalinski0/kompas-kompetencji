---
name: kompas-wiedza-domenowa
description: Słownik pojęć, podstawy prawne, procedura i kluczowe liczby oceniania w służbie cywilnej (ocena okresowa B/C, pierwsza ocena). Użyj, gdy zespół pyta „co znaczy kryterium obowiązkowe", „jaki jest termin sprzeciwu", „kiedy drukować część III", „jak liczyć średnią", „czy to urzędnik czy pracownik SC" albo gdy LLM lub kod ma przytoczyć przepis. Odsyła do research/02 (jedna wersja prawdy), nie kopiuje przepisów.
---

# kompas-wiedza-domenowa

Cel: nikt w zespole (ani LLM) nie powie jurorowi nieprawdy o ocenianiu w służbie cywilnej. Skill nie ma skryptów produkcyjnych. Jedyny skrypt pomocniczy `scripts/fetch_ustawa_sc.py` pobiera tekst ustawy z API ELI (uruchomiony, patrz `references/test-run.md`).

Pełne źródła i tabele kroków: `research/02_proces_i_przepisy.md` (proces, stan prawny, rozbieżności) i `research/05_prawo_etyka_ryzyka.md` (RODO, AI Act). Tekst ustawy: `.claude/skills/kompas-dane-i-zrodla/assets/ustawa_sc/ustawa_o_sluzbie_cywilnej.txt` (t.j. Dz. U. 2026 poz. 590). Liczby i terminy: `references/liczby_i_terminy.md`. Słownik: `references/slownik.md`.

## Kiedy użyć

- Piszesz tekst UI, komunikat walidacji, pytanie do FAQ lub prompt asystenta i musisz podać przepis, termin albo skalę.
- Reviewujesz regułę silnika (progi, ocena pozytywna/negatywna, część III, wyjątek egzaminu).
- Odpowiadasz na pytanie jurora o proces.

## Kiedy NIE używać

- Do liczenia poziomu (to robi `kompas-model-i-silnik-oceny`), parsowania danych (`kompas-dane-i-zrodla`), PDF (`kompas-dokumenty-i-terminy`).
- Do porad prawnych poza ocenami (nabór, wynagrodzenia, postępowanie dyscyplinarne): asystent ma odmawiać.

## Procedura w skrócie

Ocena okresowa: rozmowa o kryteriach (w 30 dni od poprzedniej oceny lub zatrudnienia na czas nieokreślony, w 7 dni po negatywnej) → wpis do Części I, podpis ocenianego → okres oceny (co 24 miesiące) → rozmowa oceniająca → Część II: oceny cząstkowe 1/3/5/7/9, średnia, pozytywna/negatywna, uzasadnienie (obowiązkowe przy negatywnej), wnioski do IPRZ → zapoznanie ocenianego → sprzeciw (7 dni) → skutki (ponowna ocena po 6 mies. przy negatywnej; stopień służbowy dla urzędnika, Część III).

Pierwsza ocena: rozmowa wstępna (21 dni od nawiązania stosunku pracy) → sprawozdanie ocenianego (termin po upływie 8 mies. od zatrudnienia, obejmuje co najmniej 7 mies.) → rozmowa oceniająca → pięć elementów 3/5/7 pkt, średnia → pozytywna/negatywna → zapoznanie. Brak sprzeciwu.

Podstawy i pewność każdego kroku: tabele w `research/02_proces_i_przepisy.md`, sekcje 1-2.

## Najczęstsze pomyłki (zespół i LLM)

1. **Skala punktowa**: okresowa to 1/3/5/7/9 (pięć poziomów), pierwsza ocena 3/5/7 (trzy poziomy). Model MC ma pięć poziomów, więc mapowanie 5→3 to decyzja zespołu, nie przepis (pytanie do mentora).
2. **Ocena negatywna w okresowej** nie wynika tylko ze średniej: wystarczy jedna ocena cząstkowa "znacznie poniżej oczekiwań" (§ 11 ust. 1 pkt 4 ROZP16).
3. **Progi średniej**: 1-2, >2-4, >4-6, >6-8, >8-9. Średnia równo 2, 4, 6, 8 należy do niższego przedziału.
4. **Sprzeciw dotyczy tylko oceny okresowej** (art. 83), nie pierwszej oceny.
5. **Część III** (stopień służbowy) tylko dla urzędnika SC i tylko jeśli składa się wniosek; pracownik SC jej nie ma. Pamiętaj o art. 89 ust. 2: stopień z mocy prawa po dwóch kolejnych pozytywnych ocenach na dwóch najwyższych poziomach.
6. **Urzędnik SC vs pracownik SC**: urzędnik = mianowanie, pracownik = umowa o pracę (art. 3 ustawy). Pracownik na umowie na czas określony 12 mies. podlega pierwszej ocenie, nie okresowej (art. 81 ust. 1 obejmuje umowy na czas nieokreślony).
7. **Arkusz B vs C** wynika ze stanowiska (praca polega na bezpośrednim kierowaniu pracownikami), nie ze stopnia ani nazwy stanowiska. "Koordynuje" to nie "kieruje".
8. **Wnioski rozwojowe w pierwszej ocenie** tylko przy pozytywnej; w ocenie okresowej wnioski do IPRZ są elementem oceny.
9. **Egzamin w pierwszej ocenie**: pole trzystanowe (tak/nie/nie dotyczy); "nie dotyczy" dla absolwenta KSAP bez wniosku o mianowanie, zastępstwa, wyższego stanowiska (§ 10 ust. 3 ROZP15).
10. **Stan prawny**: cytować "ustawa o służbie cywilnej (t.j. Dz. U. 2026 poz. 590)", nie numery z poradników z 2016 r. Nie cytować ustępów uchylonych (art. 81 ust. 2, art. 83 ust. 2). Nabór (art. 4-5, 26-33) ma nowe brzmienia od listopada 2026, to nie temat ocen.

## Przykład pytanie → odpowiedź z cytatem

Pytanie: "Pracownik złożył sprzeciw w 9. dniu po zapoznaniu z oceną okresową. Czy jest w terminie?"

Poprawna odpowiedź: "Nie. Sprzeciw do dyrektora generalnego urzędu służy w terminie 7 dni od dnia zapoznania się z oceną (art. 83 ust. 1 ustawy o służbie cywilnej, t.j. Dz. U. 2026 poz. 590). Dyrektor rozpatruje sprzeciw w 14 dni od jego wniesienia (art. 83 ust. 3). Czy termin można przywrócić, w bazie wiedzy nie ma, więc tego nie rozstrzygam."

Pytanie: "Czy w pierwszej ocenie przysługuje sprzeciw?" Odpowiedź: "Art. 83 ustawy dotyczy sprzeciwu od oceny okresowej. Rozporządzenie o pierwszej ocenie (§ 11) nie przewiduje sprzeciwu; po zapoznaniu oryginał arkusza trafia do akt osobowych. Innych środków prawnych baza wiedzy nie opisuje."

## Zależności i licencje

`scripts/fetch_ustawa_sc.py`: biblioteka standardowa Pythona (PSF) i polecenie `pdftotext` z poppler (GPL, wywoływane jako zewnętrzny proces, nie linkowane; narzędzie developerskie, nie wchodzi do produktu). Brak kluczy API.

## Aktualizacja tekstu ustawy

`python scripts/fetch_ustawa_sc.py --out <katalog> [--eli DU/2026/590]`, potem `python scripts/fetch_ustawa_sc.py --check <plik>`. Bez `--eli` bierze najnowsze obwieszczenie o t.j. Zawsze sprawdź "Akty zmieniające" w https://api.sejm.gov.pl/eli/acts/DU/2008/1505.
