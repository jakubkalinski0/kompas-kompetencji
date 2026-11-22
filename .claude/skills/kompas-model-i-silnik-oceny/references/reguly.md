# Reguły silnika: źródło, pewność, test

Pliki źródeł (w repo rozwiązania `materialy/` = MAT): rozp2016 = `Ocena okresowa w służbie cywilnej/Rozporządzenie o ocenach okresowych z 2016 r. (3).pdf` (Dz. U. 2016 poz. 470); rozp2015 = `Pierwsza ocena w służbie cywilnej/Rozporządzenie o pierwszej ocenie z 2015 r. (1).pdf` (Dz. U. 2015 poz. 1144); arkusz B/C = `Ocena okresowa w służbie cywilnej/Arkusz oceny B (2).docx`, `Arkusz oceny C (2).docx` (przypisy z `word/footnotes.xml`); arkusz 1. oceny = `Pierwsza ocena w służbie cywilnej/Arkusz pierwszej oceny (2).docx`; ustawa = `kompas-dane-i-zrodla/assets/ustawa_sc/ustawa_o_sluzbie_cywilnej.txt` (t.j. Dz. U. 2026 poz. 590, stan na 2026-04-14); poradniki KPRM z MAT (strony = numeracja PDF). Wszystko sprawdzone 2026-11-21. Testy: `tests/test_engine.py`.

Pewność: [✔] sprawdzone w tekście źródła; [~] interpretacja projektowa / źródło pośrednie; [?] do potwierdzenia z mentorem MC.

## Ocena okresowa (periodic_b, periodic_c)

| Id | Reguła | Źródło | Pewność | Test |
|---|---|---|---|---|
| P-SCALE | Ocena cząstkowa 1/3/5/7/9 pkt | § 11 ust. 1 pkt 1 rozp2016; arkusz B/C Cz. II | [✔] | `test_first_eval_rejects_additional_and_wrong_scale` (skala), `test_indicator_points_2l_minus_1` |
| P-THRESHOLDS | [1;2] znacznie poniżej, (2;4] poniżej, (4;6] na poziomie, (6;8] powyżej, (8;9] znacznie powyżej | § 11 ust. 1 pkt 2 lit. a–e rozp2016; arkusz B/C tabela „Przyznanie oceny” | [✔] | `test_band_boundaries`, `test_suggestion_at_and_above_boundaries`, `test_periodic_outcome_boundaries` |
| P-AVG | Ogólny poziom = średnia arytmetyczna wszystkich ocen cząstkowych | § 11 ust. 1 pkt 2 rozp2016 | [✔] | `test_anna_civil_servant_part3_attached` (6,00) |
| P-POSITIVE | Pozytywna: poziom ≥ „na poziomie” i żadnej oceny 1 pkt | § 11 ust. 1 pkt 3; przypis 10 | [✔] | `test_periodic_outcome_boundaries` |
| P-NEGATIVE | Negatywna: poziom „poniżej”/„znacznie poniżej” albo ≥1 ocena 1 pkt | § 11 ust. 1 pkt 4; przypis 11 | [✔] | `test_single_significantly_below_forces_negative`, `test_ewa_negative_needs_justification` |
| P-JUSTIFICATION | Uzasadnienie obowiązkowe przy negatywnej, fakultatywne przy pozytywnej | § 11 ust. 3–4; przypis 12 | [✔] | `test_ewa_negative_needs_justification`, `test_cli_exit_codes` |
| P-IPRZ | Wnioski do IPRZ – element każdej oceny (ostrzeżenie, gdy puste) | § 11 ust. 1 pkt 5 rozp2016; art. 81 ust. 5 ustawy; przypis 13 | [✔] | pośrednio `test_examples_are_valid` |
| P-MANDATORY | B: zarządzanie ludźmi, podejmowanie decyzji i odpowiedzialność, organizacja pracy…, współpraca, komunikacja; C: wykorzystywanie wiedzy…, rzetelność, organizacja pracy…, współpraca, komunikacja | § 4 ust. 2–3 rozp2016; arkusz B/C Cz. I–II | [✔] | `test_additional_cannot_duplicate_mandatory_and_missing_mandatory`, `test_integration_with_competency_model` |
| P-MAX-ADDITIONAL | ≤ 3 kryteria dodatkowe z zał. nr 1, różne od obowiązkowych | § 5 ust. 2 rozp2016; przypis 3 | [✔] | `test_more_than_three_additional_is_error` |
| P-PERIOD-FROM | „Od” = data zapoznania z kryteriami (Cz. I); silnik uzupełnia, gdy puste, ostrzega przy niezgodności | przypis 6 arkusza B/C | [✔] | `test_anna_civil_servant_part3_attached`, `test_period_from_mismatch_and_order` |
| P-PERIOD-TO | „Do” = data sporządzenia oceny; przy art. 81 ust. 6 ustawy (ocena niesporządzona przed zmianą stanowiska) – ostatni dzień pracy na stanowisku (`period.to_basis`) | przypis 7; art. 81 ust. 6 ustawy | [✔] | `test_period_from_mismatch_and_order` (kolejność dat) |
| P-PART3 | Część III nie drukuje się i nie dołącza dla pracownika SC i gdy wniosku nie ma | przypis 18 | [✔] | `test_jan_employee_has_no_part3`, `test_part3_requested_for_employee_is_error`, `test_part3_matrix` |
| P-PART3-POSITIVE | Wniosek o kolejny stopień tylko przy ocenie **pozytywnej** urzędnika SC | § 11 ust. 5 rozp2016; art. 89 ust. 1 ustawy; treść Cz. III | [✔] | `test_part3_matrix` |
| P-PART3-FLAG | Pole „Czy dołączono wniosek…”: tak / nie / nie dotyczy (pracownik SC) | arkusz B/C Cz. II, przypis 16 | [✔] | `test_part3_matrix` |
| P-PREVIOUS | Dane poprzedniej oceny drukowane dla urzędnika SC | nagłówek w arkuszu B/C Cz. II, przypisy 14–15 | [~] | `test_jan_employee_has_no_part3` (`include_previous_evaluation`) |
| P-OBJECTION | Pouczenie: sprzeciw do DG w 7 dni od zapoznania (bez DG – do kierownika urzędu) | sprzeciw do DG w 7 dni: art. 83 ust. 1 ustawy (t.j. Dz. U. 2026 poz. 590); kierownik urzędu, gdy brak stanowiska DG: przypis 17 arkuszy B/C (art. 83 ust. 2 ustawy jest dziś uchylony) | [✔] | `test_anna_civil_servant_part3_attached` |

## Pierwsza ocena (first_eval)

| Id | Reguła | Źródło | Pewność | Test |
|---|---|---|---|---|
| F-SCALE | 3 pkt poniżej / 5 pkt na poziomie / 7 pkt powyżej oczekiwań | § 9 ust. 1 rozp2015; arkusz Cz. IV | [✔] | `test_first_eval_rejects_additional_and_wrong_scale` |
| F-TOTAL | 5 elementów (zamknięta lista), ocena łączna = średnia wszystkich ocen cząstkowych | § 2 pkt 1, § 7 pkt 3 rozp2015; przypis 4 | [✔] | `test_piotr_positive_with_exam_not_applicable` (5,40) |
| F-EXAM | Egzamin zaliczony albo „nie dotyczy” (3 wyjątki: absolwent KSAP bez wniosku o mianowanie; zastępstwo; wyższe stanowisko w SC) | § 10 ust. 1 pkt 1 i ust. 3; przypisy 5–6 | [✔] | `test_first_eval_exam_condition`, `test_exam_not_applicable_requires_exemption` |
| F-REPORT | Sprawozdanie złożone w terminie | § 10 ust. 1 pkt 2 | [✔] | `test_first_eval_report_late_is_negative` |
| F-MAX-ONE-LOWEST | Najwyżej jedna ocena cząstkowa 3 pkt | § 10 ust. 1 pkt 3; przypis 6 | [✔] | `test_first_eval_two_lowest_is_negative_even_with_total_5` |
| F-MIN-TOTAL | Ocena łączna ≥ 5 pkt | § 10 ust. 1 pkt 4; przypis 6 | [✔] | `test_first_eval_total_just_below_threshold` (4,6 vs 5,0) |
| F-NEGATIVE | Negatywna przy niespełnieniu któregokolwiek warunku (warunki łączne) | § 10 ust. 2; przypis 6 („łącznie spełnił”) | [✔] | jw. |
| F-JUSTIFICATION | Uzasadnienie obowiązkowe przy negatywnej | § 10 ust. 4–5; przypis 7 | [✔] | `test_first_eval_development_conclusions_blocked_when_negative` |
| F-DEV-ONLY-POSITIVE | Wnioski rozwojowe fakultatywne, tylko przy pozytywnej, w porozumieniu z kierującym komórką | § 10 ust. 6; przypis 8 | [✔] | `test_first_eval_development_conclusions_blocked_when_negative` |
| F-UNIT-HEAD | Ocena w porozumieniu z kierującym komórką; może uczestniczyć w rozmowie; podpisuje potwierdzenie | art. 38 ust. 2 ustawy; § 8 ust. 2 rozp2015; arkusz – „Potwierdzenie dokonania pierwszej oceny” | [✔] | ostrzeżenie w `business_issues` (brak dedykowanego testu) |

## Sugestia („Kompas poziomu”) i ślad decyzji

| Id | Reguła | Źródło | Pewność | Test |
|---|---|---|---|---|
| S-INDICATOR-POINTS | Poziom wskaźnika L → 2L−1 pkt | etykiety poziomów w `Model_kompetencji.xlsx` (wiersz 3 arkuszy) = skala § 11 ust. 1 pkt 1 rozp2016 | [~] | `test_indicator_points_2l_minus_1` |
| S-NO-BASIS | „Brak podstaw do oceny” poza średnią; wszystkie bez podstaw → brak sugestii | instrukcja w `Model_kompetencji.xlsx` (arkusz „Model kompetencji”, w. 4–6); brak sugestii – decyzja projektowa | [✔]/[~] | `test_no_basis_excluded_from_average`, `test_all_no_basis_gives_no_suggestion` |
| S-AGGREGATE | Średnia (albo mediana) punktów → progi P-THRESHOLDS → punkty | analogia do § 11 ust. 1 pkt 2 rozp2016 | [~] | `test_suggestion_at_and_above_boundaries`, `test_median_method_is_configurable` |
| S-HALF-WARNING | Ostrzeżenie, gdy oceniono < 50% wskaźników (połowa – bez ostrzeżenia) | decyzja projektowa | [~] | `test_warning_when_less_than_half_rated`, `test_total_from_model_counts_unrated` |
| S-FIRST-MAPPING | Poziom 1–2 → 3 pkt, 3 → 5 pkt, 4–5 → 7 pkt (konfigurowalne) | wariant z promptu zadania; przepisy nie rozstrzygają | [?] | `test_first_eval_default_mapping`, `test_first_eval_mapping_is_configurable` |
| S-HUMAN-DECIDES | Silnik nie ustawia `final_points`; różnica sugestia→decyzja trafia do `audit_log` z opcjonalną notatką | pełna treść zadania pkt 2, 3, 5 | [✔] | `test_engine_never_sets_final_points`, `test_override_recorded_in_audit_log`, `test_evaluate_reconciles_overrides_once` |

## Strażnik (`guard.py`) – podstawa w poradnikach KPRM

| Id | Komunikat | Źródło | Pewność | Test |
|---|---|---|---|---|
| G-EXTREME-NO-SDR (hint) | Poziom 1 lub 5 wskaźnika bez przykładu S-D-R | Poradnik „Oceny okresowe…” (KPRM 2016) s. 26; poradnik „Pierwsza ocena…” (2016) s. 27; instrukcja modelu | [✔] treść / [~] próg | `test_guard_extreme_without_sdr_and_uniform_and_big_override`, `test_guard_quiet_on_documented_extreme` |
| G-EXTREME-FINAL-NO-SDR (hint) | Ocena cząstkowa 1 lub 9 bez żadnego przykładu w kryterium | poradnik okresowy s. 24 (notatki na bieżąco) i s. 26 | [~] | – (logika jak wyżej) |
| G-SIGNIFICANTLY-BELOW (alert) | 1 pkt → ocena negatywna i obowiązkowe uzasadnienie | § 11 ust. 1 pkt 4 i ust. 3 rozp2016; przypisy 11–12 | [✔] | `test_ewa_negative_needs_justification` |
| G-UNIFORM-LEVELS / G-UNIFORM-ALL (hint) | Identyczne poziomy wszystkich wskaźników (≥3 w kryterium / ≥6 w dokumencie) | poradnik okresowy s. 26 („rzeczywiste zachowania, a nie ogólne postrzeganie”); nazwy efektów z literatury HR | [~] | `test_guard_extreme_without_sdr_and_uniform_and_big_override` |
| G-BIG-OVERRIDE (warning) | Decyzja odbiega od sugestii o ≥ 4 pkt (2 poziomy) | pełna treść pkt 3; próg – decyzja projektowa | [~] | jw. |
| G-ALL-NO-BASIS (info) | Wszystkie wskaźniki „brak podstaw” → wybierz sam | instrukcja modelu | [✔] | – |
| G-FIRST-TWO-LOWEST / G-FIRST-EXAM / G-FIRST-REPORT (alert) | Skutki warunków § 10 rozp2015 | § 10 ust. 1–4, § 5 rozp2015 | [✔] | `test_first_eval_two_lowest_is_negative_even_with_total_5` |

## Różnice względem wskazówek autora promptu (`prompts/gotowe/kompas_kompetencji.md`, `<interpretacja>`)

1. **Część III**: autor – „drukowana wyłącznie dla urzędnika SC przy złożeniu wniosku (przypis 18)”. Przypis 18 to potwierdza, ale § 11 ust. 5 rozp2016 i art. 89 ust. 1 ustawy dodają trzeci warunek: **ocena pozytywna** (treść Cz. III: „W związku z uzyskaniem … pozytywnej oceny okresowej”). Silnik: `P-PART3-POSITIVE`.
2. **Kierujący komórką w pierwszej ocenie**: autor – uczestniczy w rozmowie, uzgadnia wnioski rozwojowe, podpisuje. Art. 38 ust. 2 ustawy mówi szerzej: przełożony **dokonuje całej pierwszej oceny w porozumieniu** z kierującym komórką. Pole `unit_head.agreement_confirmed`.
3. **Strażnik „oparty na poradnikach KPRM”**: poradniki z MAT nie używają pojęć „efekt aureoli”, „tendencja centralna”, „efekt surowości”. Podstawą jest zdanie z poradnika okresowego, s. 26, i zalecenie przykładów zachowań (poradnik pierwszej oceny, s. 27). Nazwy efektów oznaczono [~].
4. **Wnioski IPRZ w ocenie okresowej** nie są fakultatywne: § 11 ust. 1 pkt 5 rozp2016 i art. 81 ust. 5 ustawy czynią je częścią każdej oceny, także negatywnej (inaczej niż wnioski rozwojowe w pierwszej ocenie).
5. Pozostałe reguły z `<interpretacja>` (progi 1–2/>2–4/>4–6/>6–8/>8–9, warunki negatywnej oceny okresowej, uzasadnienie, ≤3 kryteria dodatkowe, przypisy 6–7, skala 3/5/7, cztery warunki pierwszej oceny z trzema wyjątkami egzaminu, wnioski rozwojowe tylko przy pozytywnej) zgadzają się z tekstem źródeł [✔]. Mapowanie 5 poziomów → 3/5/7 pozostaje [?].
6. Wskazówka praktyczna z poradnika okresowego (s. 26), której nie ma w prompcie: punktem wyjścia oceny cząstkowej jest „na poziomie oczekiwań” (5 pkt), a od niej przełożony podnosi lub obniża ocenę – dobry domyślny stan przycisków w UI (bez automatycznego zaznaczania).
