# test-run: fetch_ustawa_sc.py

Data: 2026-11-21. Środowisko: Windows 10, Python 3.13.1 (.venv), poppler pdftotext z Git for Windows.

## 1. Pobranie i zapis (kontrakt C2)
```
.venv/Scripts/python -X utf8 .claude/skills/kompas-wiedza-domenowa/scripts/fetch_ustawa_sc.py --out .claude/skills/kompas-dane-i-zrodla/assets/ustawa_sc --eli DU/2026/590 --accessed 2026-11-21
```
Wynik (exit 0):
```
liczba artykulow (linie 'Art. N.'): 162
Art. 81: Art. 81. 1. Urzędnik służby cywilnej oraz pracownik służby cywilnej zatrudniony na podstaw
Art. 82: Art. 82. Prezes Rady Ministrów określi, w drodze rozporządzenia, warunki i sposób przeprow
Art. 83: Art. 83. 1. Od oceny okresowej służy, w terminie 7 dni od dnia zapoznania się z oceną, spr
Art. 84: Art. 84. 1. Stanowiska pracy w korpusie służby cywilnej podlegają opisowi i wartościowaniu
Art. 89: Art. 89. 1. Urzędnik służby cywilnej może otrzymać kolejny stopień służbowy po uzyskaniu p
fraza 'służba przygotowawcza': 3 wystapien
fraza 'służbę przygotowawczą': 2 wystapien
fraza 'służby przygotowawczej': 6 wystapien
fraza 'pierwsz': 25 wystapien
BRAKUJE: nic
exit=0
```

## 2. Kontrola
```
.venv/Scripts/python -X utf8 .claude/skills/kompas-wiedza-domenowa/scripts/fetch_ustawa_sc.py --check .claude/skills/kompas-dane-i-zrodla/assets/ustawa_sc/ustawa_o_sluzbie_cywilnej.txt
```
```
liczba artykulow (linie 'Art. N.'): 162
Art. 81: Art. 81. 1. Urzędnik służby cywilnej oraz pracownik służby cywilnej zatrudniony na podstaw
Art. 82: Art. 82. Prezes Rady Ministrów określi, w drodze rozporządzenia, warunki i sposób przeprow
Art. 83: Art. 83. 1. Od oceny okresowej służy, w terminie 7 dni od dnia zapoznania się z oceną, spr
Art. 84: Art. 84. 1. Stanowiska pracy w korpusie służby cywilnej podlegają opisowi i wartościowaniu
Art. 89: Art. 89. 1. Urzędnik służby cywilnej może otrzymać kolejny stopień służbowy po uzyskaniu p
fraza 'służba przygotowawcza': 3 wystapien
fraza 'służbę przygotowawczą': 2 wystapien
fraza 'służby przygotowawczej': 6 wystapien
fraza 'pierwsz': 25 wystapien
BRAKUJE: nic
exit=0
```

## 3. Test bez --eli (wybór najnowszego t.j.)
```
fraza 'służby przygotowawczej': 6 wystapien
fraza 'pierwsz': 25 wystapien
BRAKUJE: nic
exit=0
```

Uwagi: plik zawiera art. 28, 29, 31, 33 w dwóch wersjach (przed i po komunikacie PRM Dz. U. 2026 poz. 1423, dotyczy naboru); przypisy dolne oznaczone prefiksem [przypis] i mogą wystąpić w środku artykułu (np. art. 36). Brak testów pytest (skrypt pomocniczy, kontrola wbudowana).

## 4. Po zmianie listy wymaganych artykułów (35-38, 81-84, 86, 89)
`--check` ponownie: BRAKUJE: nic, exit 0.

## 5. fetch_kprm_qa.py (Q&A Służby Cywilnej, gov.pl)
```
.venv/Scripts/python -X utf8 .claude/skills/kompas-wiedza-domenowa/scripts/fetch_kprm_qa.py --out .claude/skills/kompas-dane-i-zrodla/assets/kprm_qa --accessed 2026-11-21
```
Wynik (exit 0): `par Q&A: 31`, numery 1-31. Podział `process`: 1-5 ogólne (periodic+first), 6-23 periodic, 24-31 first. `legal_refs` z regexu; bywa zaszumiony (np. "art. 1013" to art. 101^3 KP po utracie indeksu górnego, pojedyncze "§ 2").
Przykład (kprm_qa_31): pytanie "Czy pracownik może wnieść do dyrektora generalnego urzędu sprzeciw od pierwszej oceny w służbie cywilnej?" odpowiedź: "Nie. Przepisy ustawy o służbie cywilnej nie przewidują trybu odwoławczego od sporządzonej pierwszej oceny ... może dochodzić swoich roszczeń przed sądem pracy." process ["first"].
Licencja treści (stopka gov.pl): CC BY-SA 4.0 (teksty), zapisana w oceny_pracownicze.meta.json.
