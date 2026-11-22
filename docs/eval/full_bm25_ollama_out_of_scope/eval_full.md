# Ewaluacja Asystenta formalnego – tryb `full`

Zbiór: eval_holdout.json (rozłączny z faq_kb.json). Data: 2026-11-21 16:43.

| Miara | Wartość |
|---|---|
| n | 7 |
| n_in_scope | 0 |
| n_out_of_scope | 7 |
| refusal_accuracy | 0.857 |
| correct_refusals_out_of_scope | 6/7 |
| false_refusals_in_scope | 0/0 |
| citation_validity | 7/7 odpowiedzi bez niezweryfikowanych cytatów |
| answered_with_citation | 0/0 |
| cites_expected_unit | 0/0 |
| keypoint_coverage_mean | None |
| latency_p50_s | 15.891 |
| latency_p95_s | 40.975 |
| model | llama3.1:8b |

## Pozycje

- `h_out_01` refused=False (oczekiwano True) kp=- cytaty=['ustawa_sc:art120', 'ustawa_sc:art45'] 40.975 s
- `h_out_02` refused=True (oczekiwano True) kp=- cytaty=[] 15.891 s
- `h_out_03` refused=True (oczekiwano True) kp=- cytaty=[] 0.0 s
- `h_out_04` refused=True (oczekiwano True) kp=- cytaty=[] 17.016 s
- `h_out_05` refused=True (oczekiwano True) kp=- cytaty=[] 0.004 s
- `h_out_06` refused=True (oczekiwano True) kp=- cytaty=[] 18.53 s
- `h_out_07` refused=True (oczekiwano True) kp=- cytaty=[] 0.003 s
