# Ewaluacja Asystenta formalnego – tryb `full`

Zbiór: eval_holdout.json (rozłączny z faq_kb.json). Data: 2026-11-21 15:15.

| Miara | Wartość |
|---|---|
| n | 36 |
| n_in_scope | 29 |
| n_out_of_scope | 7 |
| refusal_accuracy | 0.639 |
| correct_refusals_out_of_scope | 7/7 |
| false_refusals_in_scope | 13/29 |
| citation_validity | 36/36 odpowiedzi bez niezweryfikowanych cytatów |
| answered_with_citation | 16/16 |
| cites_expected_unit | 15/16 |
| keypoint_coverage_mean | 0.766 |
| latency_p50_s | 21.641 |
| latency_p95_s | 46.21 |
| model | llama3.1:8b |

## Pozycje

- `h_first_01` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:par3'] 21.641 s
- `h_first_02` refused=True (oczekiwano False) kp=- cytaty=[] 0.073 s
- `h_first_03` refused=True (oczekiwano False) kp=- cytaty=[] 17.865 s
- `h_first_04` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:par6'] 12.817 s
- `h_first_05` refused=False (oczekiwano False) kp=0.0 cytaty=['rozp2015:par7', 'rozp2015:par9'] 36.226 s
- `h_first_06` refused=False (oczekiwano False) kp=0.333 cytaty=['rozp2015:par10'] 20.269 s
- `h_first_07` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:par8'] 15.673 s
- `h_first_08` refused=True (oczekiwano False) kp=- cytaty=[] 0.159 s
- `h_first_09` refused=True (oczekiwano False) kp=- cytaty=[] 11.976 s
- `h_first_10` refused=True (oczekiwano False) kp=- cytaty=[] 38.476 s
- `h_first_11` refused=True (oczekiwano False) kp=- cytaty=[] 59.136 s
- `h_first_12` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:zal1:rzetelnosc', 'rozp2015:par3'] 31.554 s
- `h_first_13` refused=True (oczekiwano False) kp=- cytaty=[] 21.092 s
- `h_first_14` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:par7', 'rozp2015:par10'] 76.598 s
- `h_periodic_01` refused=False (oczekiwano False) kp=0.667 cytaty=['rozp2016:par9'] 31.467 s
- `h_periodic_02` refused=False (oczekiwano False) kp=0.667 cytaty=['rozp2016:par9', 'kprm_qa_oceny:9'] 44.272 s
- `h_periodic_03` refused=True (oczekiwano False) kp=- cytaty=[] 21.025 s
- `h_periodic_04` refused=True (oczekiwano False) kp=- cytaty=[] 23.417 s
- `h_periodic_05` refused=False (oczekiwano False) kp=0.25 cytaty=['rozp2016:par8'] 33.754 s
- `h_periodic_06` refused=True (oczekiwano False) kp=- cytaty=[] 41.453 s
- `h_periodic_07` refused=True (oczekiwano False) kp=- cytaty=[] 36.014 s
- `h_periodic_08` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2016:par6'] 27.282 s
- `h_periodic_09` refused=False (oczekiwano False) kp=0.333 cytaty=['rozp2016:par6'] 27.121 s
- `h_periodic_10` refused=False (oczekiwano False) kp=1.0 cytaty=['ustawa_sc:art83'] 22.698 s
- `h_periodic_11` refused=False (oczekiwano False) kp=1.0 cytaty=['ustawa_sc:art83'] 20.187 s
- `h_periodic_12` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2016:par11:ust5'] 30.648 s
- `h_periodic_13` refused=True (oczekiwano False) kp=- cytaty=[] 22.266 s
- `h_periodic_14` refused=True (oczekiwano False) kp=- cytaty=[] 16.874 s
- `h_periodic_15` refused=False (oczekiwano False) kp=1.0 cytaty=['ustawa_sc:art89', 'ustawa_sc:art51'] 46.21 s
- `h_out_01` refused=True (oczekiwano True) kp=- cytaty=[] 0.286 s
- `h_out_02` refused=True (oczekiwano True) kp=- cytaty=[] 0.321 s
- `h_out_03` refused=True (oczekiwano True) kp=- cytaty=[] 0.0 s
- `h_out_04` refused=True (oczekiwano True) kp=- cytaty=[] 0.338 s
- `h_out_05` refused=True (oczekiwano True) kp=- cytaty=[] 0.651 s
- `h_out_06` refused=True (oczekiwano True) kp=- cytaty=[] 0.311 s
- `h_out_07` refused=True (oczekiwano True) kp=- cytaty=[] 0.3 s
