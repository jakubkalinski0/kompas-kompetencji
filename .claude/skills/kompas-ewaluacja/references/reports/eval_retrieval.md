# Ewaluacja Asystenta formalnego – tryb `retrieval`

Zbiór: eval_holdout.json (rozłączny z faq_kb.json). Data: 2026-11-21 15:02.

| Miara | Wartość |
|---|---|
| n_in_scope | 29 |
| n_out_of_scope | 7 |
| hit@1 | 0.586 |
| hit@3 | 0.931 |
| hit@5 | 0.931 |
| all@5 | 0.793 |
| faq_false_matches | 0 |
| refusal_recall_out_of_scope | 7/7 |
| false_refusals_in_scope | 2/29 |
| thresholds_used | {"coverage_min": 0.2, "dense_min": 0.74} |
| calibration_best | {"coverage_min": 0.2, "dense_min": 0.74, "balanced_accuracy": 0.966, "refusals_correct": "7/7", "answered_in_scope": "27/29"} |
| signals_in_scope | {"coverage_min": 0.193, "dense_top_min": 0.737} |
| signals_out_of_scope | {"coverage_max": 0.456, "dense_top_max": 0.7691} |
| latency_p50_s | 0.101 |
| latency_p95_s | 0.2 |
| hit@5_first | 0.857 |
| hit@5_periodic | 1.0 |

## Pozycje

- `h_first_01` hit@5=True refuse=False cov=0.654 cos=0.7686 top1=['rozp2015:par3 (§ 3)']
- `h_first_02` hit@5=True refuse=True cov=0.434 cos=0.737 top1=['rozp2015:par5 (§ 5)']
- `h_first_03` hit@5=True refuse=False cov=0.267 cos=0.7816 top1=['rozp2015:par5 (§ 5)']
- `h_first_04` hit@5=True refuse=True cov=0.193 cos=0.7866 top1=['rozp2015:par6 (§ 6)']
- `h_first_05` hit@5=True refuse=False cov=0.631 cos=0.8031 top1=['rozp2016:par4 (§ 4)']
- `h_first_06` hit@5=True refuse=False cov=0.482 cos=0.7935 top1=['rozp2015:par5 (§ 5)']
- `h_first_07` hit@5=True refuse=False cov=0.399 cos=0.7791 top1=['rozp2015:par8 (§ 8)']
- `h_first_08` hit@5=False refuse=False cov=0.231 cos=0.769 top1=['rozp2015:par6 (§ 6)']
- `h_first_09` hit@5=True refuse=False cov=0.507 cos=0.832 top1=['rozp2015:par11 (§ 11)']
- `h_first_10` hit@5=True refuse=False cov=0.673 cos=0.8124 top1=['rozp2015:par1 (§ 1)']
- `h_first_11` hit@5=True refuse=False cov=0.405 cos=0.7748 top1=['rozp2015:par5 (§ 5)']
- `h_first_12` hit@5=False refuse=False cov=0.231 cos=0.7594 top1=['rozp2015:par1 (§ 1)']
- `h_first_13` hit@5=True refuse=False cov=0.647 cos=0.8227 top1=['rozp2015:par4 (§ 4)']
- `h_first_14` hit@5=True refuse=False cov=0.529 cos=0.8556 top1=['rozp2015:par10 (§ 10)']
- `h_periodic_01` hit@5=True refuse=False cov=0.337 cos=0.8225 top1=['rozp2016:par9 (§ 9)']
- `h_periodic_02` hit@5=True refuse=False cov=0.49 cos=0.8033 top1=['rozp2016:par10 (§ 10)']
- `h_periodic_03` hit@5=True refuse=False cov=0.622 cos=0.817 top1=['rozp2016:par9 (§ 9)']
- `h_periodic_04` hit@5=True refuse=False cov=0.361 cos=0.8021 top1=['rozp2016:par9 (§ 9)']
- `h_periodic_05` hit@5=True refuse=False cov=0.316 cos=0.7876 top1=['rozp2016:par6 (§ 6)']
- `h_periodic_06` hit@5=True refuse=False cov=0.655 cos=0.8228 top1=['rozp2016:par11:ust1 (§ 11 ust. 1)']
- `h_periodic_07` hit@5=True refuse=False cov=0.453 cos=0.79 top1=['rozp2016:par11:ust1 (§ 11 ust. 1)']
- `h_periodic_08` hit@5=True refuse=False cov=0.3 cos=0.7796 top1=['rozp2016:par6 (§ 6)']
- `h_periodic_09` hit@5=True refuse=False cov=1.0 cos=0.8066 top1=['rozp2016:par6 (§ 6)']
- `h_periodic_10` hit@5=True refuse=False cov=0.864 cos=0.7609 top1=['ustawa_sc:art83 (art. 83)']
- `h_periodic_11` hit@5=True refuse=False cov=0.378 cos=0.7739 top1=['rozp2016:par10 (§ 10)']
- `h_periodic_12` hit@5=True refuse=False cov=0.466 cos=0.7711 top1=['ustawa_sc:art89 (art. 89)']
- `h_periodic_13` hit@5=True refuse=False cov=0.583 cos=0.8125 top1=['rozp2016:par9 (§ 9)']
- `h_periodic_14` hit@5=True refuse=False cov=0.396 cos=0.7978 top1=['rozp2016:par5 (§ 5)']
- `h_periodic_15` hit@5=True refuse=False cov=0.653 cos=0.8288 top1=['ustawa_sc:art89 (art. 89)']
- `h_out_01` hit@5=- refuse=True cov=0.456 cos=0.7135 top1=['ustawa_sc:art120 (art. 120)']
- `h_out_02` hit@5=- refuse=True cov=0.361 cos=0.7374 top1=['rozp2016:par1 (§ 1)']
- `h_out_03` hit@5=- refuse=True cov=0.102 cos=0.6915 top1=['rozp2015:par9 (§ 9)']
- `h_out_04` hit@5=- refuse=True cov=0.382 cos=0.6773 top1=['ustawa_sc:art79 (art. 79)']
- `h_out_05` hit@5=- refuse=True cov=0.156 cos=0.7691 top1=['ustawa_sc:art25 (art. 25)']
- `h_out_06` hit@5=- refuse=True cov=0.135 cos=0.6992 top1=['ustawa_sc:art33:v1 (art. 33 (wersja 1 z 2 w tekście jednolitym))']
- `h_out_07` hit@5=- refuse=True cov=0.117 cos=0.7242 top1=['ustawa_sc:art23c (art. 23c)']
