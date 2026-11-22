# PDF arkusza: DOCX Partnera + konwersja czy szablon w kodzie

Wymóg: „Możliwość generowania wymaganej dokumentacji w powszechnie stosowanym formacie, w szczególności PDF” (pełna treść, pkt 5). Kryterium „Poprawność generowanych rezultatów i dokumentacji” (pkt 6). Zwycięzca przenosi autorskie prawa majątkowe na MC (regulamin zadania § 4), więc zależności muszą mieć licencje permisywne.

| | A. Wypełnienie DOCX Partnera + konwersja do PDF | B. Szablon w kodzie (reportlab) – **wdrożone** |
|---|---|---|
| Wierność wzorowi | Najwyższa: oryginalny układ, czcionki i przypisy na dole stron | Odtworzona kolejność części, pól, tabel i znaków „X”; przypisy dosłownie z DOCX (wyciąg `extract_form_texts.py`), ale zebrane na końcu dokumentu |
| Zależności | Wypełnianie: `zipfile` + XML (stdlib) albo python-docx (MIT). Konwersja: LibreOffice headless (`soffice --headless --convert-to pdf`, licencja MPL-2.0 [~], instalacja kilkaset MB, uruchamiany jako osobny proces) albo docx2pdf (wymaga MS Word – tylko Windows/macOS) | reportlab 5.1.0 – „BSD license” (metadane paczki w venv, sprawdzone 2026-11-21) + czcionka DejaVu Sans (licencja Bitstream Vera/DejaVu, plik `assets/fonts/LICENSE_DEJAVU.txt`) |
| Offline Windows/Linux | Tak, jeśli LibreOffice zainstalowany na serwerze. Na tym laptopie LibreOffice nie ma (`which soffice` – brak), więc drogi A nie dało się tu sprawdzić | Tak – sprawdzone na Windows 10 bez sieci; czcionka w `assets/fonts`, więc Linux nie potrzebuje fontów systemowych |
| Polskie znaki | Zależne od fontów na serwerze (Times New Roman/Arial na Linuksie trzeba podmienić np. Liberation – inny krój) | Osadzony DejaVu Sans; `validate_pdf.py` sprawdza znaki przez `pdftotext -enc UTF-8` |
| Wypełnianie pól | Komórki tabel DOCX bez identyfikatorów – trzeba pozycjonować po indeksach tabel/wierszy; zmiana wzoru psuje mapowanie | Pola i reguły (Część III, przypis 18; wnioski rozwojowe, przypis 8) w kodzie z testami pytest |
| Czas | Zimny start LibreOffice zwykle kilka sekund, kłopotliwa współbieżność [~] | ok. 3,3 s z uruchomieniem interpretera (pomiar `time`, arkusz C), sama funkcja w testach – poniżej 1 s na PDF |
| Testowalność | Trudna (render zależny od wersji LibreOffice) | Deterministyczna; 36 testów pytest w `tests/` |
| Ryzyko licencyjne | MPL-2.0 to słaby copyleft na poziomie plików – przy wywołaniu jako zewnętrzny program nie obejmuje naszego kodu [~]; obraz kontenera duży | Brak (BSD + licencja fontu pozwalająca na redystrybucję) |

## Rekomendacja

Droga B do prototypu i dalej do wdrożenia. Działa offline na laptopie demo i na serwerze bez binarnych zależności, ma testy zgodności tekstu z przypisami z DOCX i licencje bez ryzyka dla przeniesienia praw na MC. Wzór arkusza jest załącznikiem do rozporządzenia, więc zmienia się rzadko. Wtedy wystarczy podmienić DOCX, uruchomić `extract_form_texts.py` (test pokaże różnice w przypisach) i poprawić układ w `render_pdf.py`.

Drogę A warto rozważyć tylko jako dodatkowy eksport „DOCX do edycji”, gdyby MC chciało poprawiać arkusz ręcznie. Wypełniony DOCX da się zbudować samym `zipfile`, bez konwersji do PDF i bez LibreOffice.

Do decyzji z mentorem MC: czy przypisy mają być na dole każdej strony, jak w DOCX, czy mogą być zebrane na końcu, jak teraz. Pytanie dotyczy też tego, czy w wydruku zostaje nagłówek „Załącznik nr 3/4/2”. Słowo „WZÓR” pomijamy, bo dokument jest wypełnionym arkuszem.

## Znane ograniczenia drogi B

- Reportlab zawsze deklaruje w PDF nieosadzoną czcionkę Helvetica (domyślna czcionka canvasu). Żaden tekst jej nie używa, co widać w `pdffonts`, a poppler zgłasza ostrzeżenie „No display font for 'Symbol'”. Na treść to nie wpływa.
- Część III zaczyna się od nowej strony (to załącznik do arkusza, przypis 18). Przypisy są numerowane jak w DOCX: 1–18 dla B/C i 1–8 dla pierwszej oceny.
- Puste pola daty drukujemy jako „(dd.mm.rrrr)”, tak jak we wzorze.
