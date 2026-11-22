# Ewaluacja Asystenta formalnego – tryb `full`

Zbiór: eval_holdout.json (rozłączny z faq_kb.json). Data: 2026-11-21 15:00.

| Miara | Wartość |
|---|---|
| n | 36 |
| n_in_scope | 29 |
| n_out_of_scope | 7 |
| refusal_accuracy | 0.694 |
| correct_refusals_out_of_scope | 7/7 |
| false_refusals_in_scope | 11/29 |
| citation_validity | 35/36 odpowiedzi bez niezweryfikowanych cytatów |
| answered_with_citation | 18/18 |
| cites_expected_unit | 18/18 |
| keypoint_coverage_mean | 0.648 |
| latency_p50_s | 23.487 |
| latency_p95_s | 44.173 |
| model | llama3.1:8b |

## Pozycje

- `h_first_01` refused=False (oczekiwano False) kp=0.667 cytaty=['rozp2015:par3'] 25.49 s
- `h_first_02` refused=True (oczekiwano False) kp=- cytaty=[] 0.072 s
- `h_first_03` refused=True (oczekiwano False) kp=- cytaty=[] 13.809 s
- `h_first_04` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:par6'] 17.415 s
- `h_first_05` refused=False (oczekiwano False) kp=0.0 cytaty=['rozp2015:par7', 'rozp2015:par9'] 18.404 s
- `h_first_06` refused=False (oczekiwano False) kp=0.333 cytaty=['rozp2015:par10'] 18.802 s
- `h_first_07` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:par8'] 14.114 s
- `h_first_08` refused=True (oczekiwano False) kp=- cytaty=[] 0.152 s
- `h_first_09` refused=True (oczekiwano False) kp=- cytaty=[] 17.319 s
- `h_first_10` refused=True (oczekiwano False) kp=- cytaty=[] 39.863 s
- `h_first_11` refused=False (oczekiwano False) kp=0.25 cytaty=['rozp2015:par5'] 43.666 s
- `h_first_12` refused=False (oczekiwano False) kp=0.5 cytaty=['model_kompetencji:rzetelnosc', 'rozp2015:par2'] 59.851 s
- `h_first_13` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2015:par4'] 23.487 s
- `h_first_14` refused=True (oczekiwano False) kp=- cytaty=[] 44.173 s
- `h_periodic_01` refused=False (oczekiwano False) kp=0.667 cytaty=['rozp2016:par9'] 22.471 s
- `h_periodic_02` refused=True (oczekiwano False) kp=- cytaty=[] 47.112 s
- `h_periodic_03` refused=True (oczekiwano False) kp=- cytaty=[] 26.568 s
- `h_periodic_04` refused=False (oczekiwano False) kp=0.0 cytaty=['ustawa_sc:art81'] 39.348 s
- `h_periodic_05` refused=False (oczekiwano False) kp=0.25 cytaty=['rozp2016:par8'] 30.681 s
- `h_periodic_06` refused=True (oczekiwano False) kp=- cytaty=[] 28.144 s
- `h_periodic_07` refused=True (oczekiwano False) kp=- cytaty=[] 24.962 s
- `h_periodic_08` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2016:par6', 'rozp2016:par12'] 22.358 s
- `h_periodic_09` refused=False (oczekiwano False) kp=0.333 cytaty=['rozp2016:par6'] 15.15 s
- `h_periodic_10` refused=False (oczekiwano False) kp=1.0 cytaty=['ustawa_sc:art83'] 25.132 s
- `h_periodic_11` refused=False (oczekiwano False) kp=1.0 cytaty=['ustawa_sc:art83'] 33.05 s
- `h_periodic_12` refused=False (oczekiwano False) kp=1.0 cytaty=['rozp2016:par11:ust5'] 24.581 s
- `h_periodic_13` refused=True (oczekiwano False) kp=- cytaty=[] 25.044 s
- `h_periodic_14` refused=False (oczekiwano False) kp=0.667 cytaty=['rozp2016:par4', 'rozp2016:par2'] 25.286 s
- `h_periodic_15` refused=False (oczekiwano False) kp=1.0 cytaty=['ustawa_sc:art89', 'ustawa_sc:art51'] 41.901 s
- `h_out_01` refused=True (oczekiwano True) kp=- cytaty=[] 0.084 s
- `h_out_02` refused=True (oczekiwano True) kp=- cytaty=[] 0.074 s
- `h_out_03` refused=True (oczekiwano True) kp=- cytaty=[] 0.0 s
- `h_out_04` refused=True (oczekiwano True) kp=- cytaty=[] 0.052 s
- `h_out_05` refused=True (oczekiwano True) kp=- cytaty=[] 0.059 s
- `h_out_06` refused=True (oczekiwano True) kp=- cytaty=[] 0.07 s
- `h_out_07` refused=True (oczekiwano True) kp=- cytaty=[] 0.058 s
