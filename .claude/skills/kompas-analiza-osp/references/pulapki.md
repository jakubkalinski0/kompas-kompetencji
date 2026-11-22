# Pułapki analizy OSP

Stan: 2026-11-21, sprawdzone na 3 OSP z `OSP_word.zip` (MC). Oznaczenia: [✔] sprawdzone w źródle, [~] częściowo, [?] hipoteza.

## 1. Różne wersje szablonu OSP
- [✔] Już trzy OSP z MC mają dwa układy tabel. W OSP radcy część I i „Miejsce stanowiska pracy w strukturze” leżą w jednej tabeli, zadania dominujące i pozostałe w jednej tabeli (wiersz „POZOSTAŁE ZADANIA” w środku), a po zadaniach jest pusta tabela. Dlatego parser szuka **etykiet** (np. „LICZBA PODLEGŁYCH PRACOWNIKÓW”), a nie numerów tabel i wierszy.
- [✔] Wszystkie trzy to szablon „OPIS STANOWISKA PRACY NIEBĘDĄCEGO WYŻSZYM STANOWISKIEM W SŁUŻBIE CYWILNEJ”. OSP wyższych stanowisk i OSP innych urzędów nie były testowane.
- [?] Inne urzędy mogą inaczej nazywać sekcje (np. „Kompetencje behawioralne” zamiast „Kompetencje miękkie”) albo nie mieć pól wyboru liczby podległych. Wtedy parser zwraca ostrzeżenia w `warnings` (np. „Nie znaleziono sekcji: subordinates”), a aplikacja musi pozwolić uzupełnić pola ręcznie. Nowe etykiety dopisuje się w `SECTION_HEADERS` / `PART1_LABELS` w `osp_parser.py`.
- Obsługiwany jest tylko `.docx`. `.doc`, `.odt` i skany PDF trzeba przekonwertować albo wypełnić formularz ręcznie.

## 2. Pola wyboru (☒/☐)
- [✔] OSP z MC używają pól `w14:checkbox` (kontrolki zawartości Word 2010+, znak ☒ U+2612 w MS Gothic). Stan bierzemy z `w14:checked`, a nie z wyświetlanego znaku. Gdy atrybutu brak, rozstrzyga znak.
- Parser obsługuje też starsze pola formularza FORMCHECKBOX (`w:ffData/w:checkBox`), symbole Wingdings (`w:sym`, np. F0FE/F078 = zaznaczone, F0A8/F06F = puste) i znaki ☒/☐ wpisane jako tekst. Te warianty pokrywa tylko test syntetyczny, w dokumentach MC ich nie ma.
- Ktoś może „zaznaczyć” opcję po swojemu, np. dopisać „X” albo pogrubić tekst. Parser tego nie rozpozna: zwróci `status: none_selected`, a `propose_form` przejdzie na regułę R3 (treść zadań) z niską pewnością i ostrzeżeniem.
- Dwa zaznaczone przedziały to `multiple_selected`. Jeśli oba oznaczają podległych, wychodzi arkusz B ze średnią pewnością. Jeśli jednym z nich jest „brak podległych”, decyduje treść zadań (R3).
- Pola rozwijane z niewybraną wartością („Wybierz element.”, `w:showingPlcHdr`) dają `null`, nie tekst.

## 3. „Kieruje” a „koordynuje”
- [✔] Opcje w szablonie MC brzmią „bezpośrednio kieruje **lub koordynuje** pracę … pracowników”. Arkusz B przysługuje stanowisku, „na którym praca polega na bezpośrednim kierowaniu pracownikami” (§ 3 ust. 3 rozporządzenia z 2016 r.; przypis 1 arkusza B). Samo pole wyboru tego nie przesądza, bo koordynowanie nie musi oznaczać bezpośredniego kierowania.
- Dlatego przy każdej takiej opcji `propose_form` dodaje ostrzeżenie „Koordynowanie nie musi oznaczać bezpośredniego kierowania – potwierdź” i podaje cytaty z zadań. U naczelnika jest „Koordynuje pracę zespołu…”, a obok „zarządzanie zespołem… delegowanie obowiązków”. Arkusz potwierdza przełożony, a UI nie powinno pozwolić przejść dalej bez tego kliknięcia.
- Przy opcji „bezpośrednio podlegają osoby kierujące pracą innych pracowników” reguła proponuje B, bo podlegli kierownicy też są pracownikami. To interpretacja, oznaczona [?]: potwierdzić z mentorem MC.
- Arkusz A (kierownik urzędu, § 3 ust. 2) jest poza zakresem, bo Partner nie dał jego wzoru. Reguła nigdy go nie proponuje, a przy OSP wyższego stanowiska wyświetla ostrzeżenie.

## 4. Kompetencje miękkie → kryteria
- [✔] OSP z MC używają nazw kryteriów z załącznika nr 1, więc wszystkie pozycje dopasowały się jako `exact`. Skróty („orientacja na klienta”, „podejmowanie decyzji”) dopasowują się jako `alias`, literówki jako `fuzzy` (próg 0,85). Pozycje, których nie da się dopasować, trafiają do `unmatched` z ostrzeżeniem i nie są mapowane po cichu.
- [✔] U radcy wszystkie trzy kompetencje miękkie są obowiązkowe dla arkusza C, więc kandydatów z OSP brak. To poprawny wynik, bo kryteria dodatkowe są opcjonalne („może wybrać”, § 2 ust. 2). Kandydatów z zadań może wtedy zaproponować LLM.
- [✔] Limit: najwyżej 3 kryteria dodatkowe (§ 5 ust. 2). `validate_selection()` sprawdza wybór przełożonego, a walidator LLM obcina propozycje do 3.
- Kandydat to tylko podpowiedź: kryterium wybiera oceniający po rozmowie (§ 5 ust. 1–3) i wpisuje je do części I arkusza.

## 5. Dane osobowe i poufność
- OSP zawiera pola „IMIĘ I NAZWISKO” (zapoznanie pracownika) i podpisy w części III. Parser zwraca w tych miejscach tylko `[osoba]` / `[podpis/data]` albo znacznik typu `/elektroniczna akceptacja/`. Nie czyta `docProps/core.xml` (autor, ostatnio modyfikujący).
- Pola tekstowe (zadania, przykłady) nie są anonimizowane. Ktoś może tam wpisać „współpracuje z p. Kowalskim”. Przed wysłaniem do LLM aplikacja musi przepuścić tekst przez maskowanie PII (Privacy Shield w `kompas-asystent-ai`). Heurystyka `redact_names()` (2–3 wyrazy z wielkiej litery) działa tylko w części III i może przepuścić nazwisko pisane inaczej.
- OSP to wewnętrzne dokumenty MC. Nie commituj ich do publicznego repozytorium i nie umieszczaj w bazie wiedzy asystenta (OSP opisują konkretne stanowiska). Testy czytają je przez `KOMPAS_MATERIALY`.

## 6. Bezpieczeństwo uploadu
- Limit 30 MB na plik i 25 MB na `document.xml`. Dokumenty z `<!DOCTYPE`/`<!ENTITY` są odrzucane (ochrona przed XXE i „billion laughs”), a makra (`vbaProject.bin`) ignorowane z ostrzeżeniem.
- Archiwum ZIP czytamy w pamięci, bez rozpakowywania na dysk (brak zip-slip). Nazwy plików bez flagi UTF-8 dekodujemy jako cp437→UTF-8/cp852.
- Treść OSP jest danymi, a nie poleceniem. W prompcie leży w bloku `<osp_data>` jako JSON, ze znakami `<` `>` zakodowanymi (`<`, `>`), więc tekst z dokumentu nie zamknie bloku. Walidator przyjmuje kandydata tylko z dosłownym cytatem zadania. `detect_injection()` ostrzega, gdy w OSP jest tekst przypominający polecenie.

## 7. Stan prawny
- Reguły opierają się na rozporządzeniu Prezesa Rady Ministrów z 4 kwietnia 2016 r. (Dz. U. poz. 470) z materiałów Partnera. [?] Czy § 2–5 obowiązują dziś w tym brzmieniu, sprawdza agent PRAWO w `research/02_proces_i_przepisy.md`. DO WERYFIKACJI: ISAP, tekst jednolity rozporządzenia; przy zmianie trzeba poprawić cytaty w `FORMS` / `ADDITIONAL_BASIS` w `propose_form.py`.
