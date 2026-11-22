# Ewaluacja Asystenta formalnego – tryb `retrieval`

Zbiór: eval_holdout.json (rozłączny z faq_kb.json). Data: 2026-11-22 05:18.

| Miara | Wartość |
|---|---|
| n_in_scope | 29 |
| n_out_of_scope | 7 |
| hit@1 | 0.759 |
| hit@3 | 0.828 |
| hit@5 | 0.966 |
| all@5 | 0.862 |
| faq_false_matches | 0 |
| refusal_recall_out_of_scope | 3/7 |
| false_refusals_in_scope | 0/29 |
| thresholds_used | {"coverage_min": 0.2, "dense_min": 0.74} |
| calibration_best | {"coverage_min": 0.4, "dense_min": 0.78, "balanced_accuracy": 0.842, "refusals_correct": "6/7", "answered_in_scope": "24/29"} |
| signals_in_scope | {"coverage_min": 0.23, "dense_top_min": 0} |
| signals_out_of_scope | {"coverage_max": 0.456, "dense_top_max": 0} |
| latency_p50_s | 0.005 |
| latency_p95_s | 0.007 |
| hit@5_first | 0.929 |
| hit@5_periodic | 1.0 |

## Pozycje

- `h_first_01` hit@5=True refuse=False cov=0.67 cos=None top1=['rozp2015:par3 (§ 3)']
- `h_first_02` hit@5=True refuse=False cov=0.492 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_03` hit@5=True refuse=False cov=0.267 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_04` hit@5=True refuse=False cov=0.432 cos=None top1=['rozp2015:par6 (§ 6)']
- `h_first_05` hit@5=True refuse=False cov=0.631 cos=None top1=['rozp2016:par4 (§ 4)']
- `h_first_06` hit@5=True refuse=False cov=0.545 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_07` hit@5=True refuse=False cov=0.399 cos=None top1=['rozp2015:par8 (§ 8)']
- `h_first_08` hit@5=False refuse=False cov=0.23 cos=None top1=['rozp2015:par2 (§ 2)']
- `h_first_09` hit@5=True refuse=False cov=0.507 cos=None top1=['rozp2015:par11 (§ 11)']
- `h_first_10` hit@5=True refuse=False cov=0.625 cos=None top1=['ustawa_sc:art38 (art. 38)']
- `h_first_11` hit@5=True refuse=False cov=0.478 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_12` hit@5=True refuse=False cov=0.751 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_first_13` hit@5=True refuse=False cov=0.647 cos=None top1=['rozp2015:par4 (§ 4)']
- `h_first_14` hit@5=True refuse=False cov=0.498 cos=None top1=['rozp2015:par10 (§ 10)']
- `h_periodic_01` hit@5=True refuse=False cov=0.485 cos=None top1=['rozp2016:par9 (§ 9)']
- `h_periodic_02` hit@5=True refuse=False cov=0.388 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_03` hit@5=True refuse=False cov=0.596 cos=None top1=['rozp2015:par5 (§ 5)']
- `h_periodic_04` hit@5=True refuse=False cov=0.416 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_05` hit@5=True refuse=False cov=1.0 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_06` hit@5=True refuse=False cov=0.573 cos=None top1=['rozp2016:par11:ust1 (§ 11 ust. 1)']
- `h_periodic_07` hit@5=True refuse=False cov=0.453 cos=None top1=['rozp2016:par11:ust1 (§ 11 ust. 1)']
- `h_periodic_08` hit@5=True refuse=False cov=0.3 cos=None top1=['rozp2016:par6 (§ 6)']
- `h_periodic_09` hit@5=True refuse=False cov=1.0 cos=None top1=['rozp2016:par6 (§ 6)']
- `h_periodic_10` hit@5=True refuse=False cov=0.864 cos=None top1=['ustawa_sc:art83 (art. 83)']
- `h_periodic_11` hit@5=True refuse=False cov=0.451 cos=None top1=['ustawa_sc:art83 (art. 83)']
- `h_periodic_12` hit@5=True refuse=False cov=0.468 cos=None top1=['ustawa_sc:art89 (art. 89)']
- `h_periodic_13` hit@5=True refuse=False cov=0.586 cos=None top1=['ustawa_sc:art81 (art. 81)']
- `h_periodic_14` hit@5=True refuse=False cov=0.776 cos=None top1=['rozp2016:par2 (§ 2)']
- `h_periodic_15` hit@5=True refuse=False cov=0.65 cos=None top1=['ustawa_sc:art89 (art. 89)']
- `h_out_01` hit@5=- refuse=False cov=0.456 cos=None top1=['ustawa_sc:art45 (art. 45)']
- `h_out_02` hit@5=- refuse=False cov=0.361 cos=None top1=['ustawa_sc:art28a (art. 28a)']
- `h_out_03` hit@5=- refuse=True cov=0.261 cos=None top1=['rozp2015:par2 (§ 2)']
- `h_out_04` hit@5=- refuse=False cov=0.382 cos=None top1=['ustawa_sc:art86 (art. 86)']
- `h_out_05` hit@5=- refuse=True cov=0.104 cos=None top1=['ustawa_sc:art62 (art. 62)']
- `h_out_06` hit@5=- refuse=False cov=0.233 cos=None top1=['ustawa_sc:art27a (art. 27a)']
- `h_out_07` hit@5=- refuse=True cov=0.117 cos=None top1=['ustawa_sc:art209 (art. 209)']
