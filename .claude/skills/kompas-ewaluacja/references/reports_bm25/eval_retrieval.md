# Ewaluacja Asystenta formalnego – tryb `retrieval`

Zbiór: eval_holdout.json (rozłączny z faq_kb.json). Data: 2026-11-21 14:49.

| Miara | Wartość |
|---|---|
| n_in_scope | 29 |
| n_out_of_scope | 7 |
| hit@1 | 0.724 |
| hit@3 | 0.793 |
| hit@5 | 0.966 |
| all@5 | 0.897 |
| faq_false_matches | 0 |
| refusal_recall_out_of_scope | 3/7 |
| false_refusals_in_scope | 0/29 |
| thresholds_used | {"coverage_min": 0.2, "dense_min": 0.74} |
| calibration_best | {"coverage_min": 0.4, "dense_min": 0.78, "balanced_accuracy": 0.825, "refusals_correct": "6/7", "answered_in_scope": "23/29"} |
| signals_in_scope | {"coverage_min": 0.23, "dense_top_min": 0} |
| signals_out_of_scope | {"coverage_max": 0.457, "dense_top_max": 0} |
| latency_p50_s | 0.005 |
| latency_p95_s | 0.026 |
| hit@5_first | 0.929 |
| hit@5_periodic | 1.0 |

## Pozycje

- `h_first_01` hit@5=True refuse=False cov=0.653 cos=None top1=['rozp2015:par3 (§ 3)']
- `h_first_02` hit@5=True refuse=False cov=0.419 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_03` hit@5=True refuse=False cov=0.266 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_04` hit@5=True refuse=False cov=0.424 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_05` hit@5=True refuse=False cov=0.631 cos=None top1=['rozp2016:par4 (§ 4)']
- `h_first_06` hit@5=True refuse=False cov=0.54 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_07` hit@5=True refuse=False cov=0.399 cos=None top1=['rozp2015:par8 (§ 8)']
- `h_first_08` hit@5=False refuse=False cov=0.23 cos=None top1=['rozp2015:par2 (§ 2)']
- `h_first_09` hit@5=True refuse=False cov=0.507 cos=None top1=['rozp2015:par11 (§ 11)']
- `h_first_10` hit@5=True refuse=False cov=0.673 cos=None top1=['ustawa_sc:art38 (art. 38)']
- `h_first_11` hit@5=True refuse=False cov=0.477 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_12` hit@5=True refuse=False cov=0.685 cos=None top1=['poradnik_pierwsza_2016:1 (rozdz. 1)']
- `h_first_13` hit@5=True refuse=False cov=0.646 cos=None top1=['rozp2015:par4 (§ 4)']
- `h_first_14` hit@5=True refuse=False cov=0.497 cos=None top1=['rozp2015:par10 (§ 10)']
- `h_periodic_01` hit@5=True refuse=False cov=0.482 cos=None top1=['rozp2016:par9 (§ 9)']
- `h_periodic_02` hit@5=True refuse=False cov=0.386 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_03` hit@5=True refuse=False cov=0.595 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_periodic_04` hit@5=True refuse=False cov=0.417 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_05` hit@5=True refuse=False cov=0.595 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_06` hit@5=True refuse=False cov=0.572 cos=None top1=['rozp2016:par11:ust1 (§ 11 ust. 1)']
- `h_periodic_07` hit@5=True refuse=False cov=0.452 cos=None top1=['rozp2016:par11:ust1 (§ 11 ust. 1)']
- `h_periodic_08` hit@5=True refuse=False cov=0.299 cos=None top1=['rozp2016:par6 (§ 6)']
- `h_periodic_09` hit@5=True refuse=False cov=1.0 cos=None top1=['rozp2016:par6 (§ 6)']
- `h_periodic_10` hit@5=True refuse=False cov=0.864 cos=None top1=['ustawa_sc:art83 (art. 83)']
- `h_periodic_11` hit@5=True refuse=False cov=0.378 cos=None top1=['ustawa_sc:art83 (art. 83)']
- `h_periodic_12` hit@5=True refuse=False cov=0.4 cos=None top1=['ustawa_sc:art89 (art. 89)']
- `h_periodic_13` hit@5=True refuse=False cov=0.583 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_14` hit@5=True refuse=False cov=0.875 cos=None top1=['rozp2016:par2 (§ 2)']
- `h_periodic_15` hit@5=True refuse=False cov=0.652 cos=None top1=['ustawa_sc:art89 (art. 89)']
- `h_out_01` hit@5=- refuse=False cov=0.457 cos=None top1=['ustawa_sc:art45 (art. 45)']
- `h_out_02` hit@5=- refuse=False cov=0.36 cos=None top1=['ustawa_sc:art28a (art. 28a)']
- `h_out_03` hit@5=- refuse=True cov=0.169 cos=None top1=['ustawa_sc:art63 (art. 63)']
- `h_out_04` hit@5=- refuse=False cov=0.382 cos=None top1=['ustawa_sc:art86 (art. 86)']
- `h_out_05` hit@5=- refuse=True cov=0.103 cos=None top1=['ustawa_sc:art62 (art. 62)']
- `h_out_06` hit@5=- refuse=False cov=0.233 cos=None top1=['ustawa_sc:art27a (art. 27a)']
- `h_out_07` hit@5=- refuse=True cov=0.117 cos=None top1=['ustawa_sc:art209 (art. 209)']
