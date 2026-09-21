# Order 69 roster construction validation

These measurements reuse the unchanged `order68-roster-validation-v1` workload:
100 calls to the shared roster validator, with two, four and twenty units
(six, sixteen and ninety-six models). Each case has seven serial samples.
Catalog/request preparation is outside the timer. The existing synthetic
rosters have empty construction constraints, matching the shipped catalog at
P25C completion; selector correctness is covered by behavioral regressions.
This assesses the cost added to ordinary roster validation, not a maximum over
arbitrary future constraint records.

Base `28df017e` was measured before implementation. Head runtime `b258a14e` was
measured after the final production change, on the same Windows 11 host,
Python 3.14.5, Threadripper 3970X, dependency lock and workload source. Both
measurements ran without competing test/build workers. Raw samples, machine
details, input hashes and full runtime identities are retained in `base.json`
and `head.json`.

| Units / models | Base mean (s) | Head mean (s) | Base maximum (s) | Head maximum (s) |
| --- | ---: | ---: | ---: | ---: |
| 2 / 6 | 0.035546 | 0.036161 | 0.036263 | 0.036410 |
| 4 / 16 | 0.043717 | 0.044054 | 0.044404 | 0.044152 |
| 20 / 96 | 0.107525 | 0.108386 | 0.108750 | 0.109057 |

Every mean and maximum passes the unchanged inherited budget:
`head <= base * 1.5 + 0.02 seconds` per 100-call batch. The code-quality audit
checks the matched conditions, sample completion, workload hashes, budget and
current runtime identity. No threshold was raised or hard case removed.

Reproduce with the corresponding checkout and no competing workers:

```powershell
uv run python -m scripts.measure_order68 --output docs/performance/order69/base.json --revision 28df017e
uv run python -m scripts.measure_order68 --output docs/performance/order69/head.json --revision b258a14e
```

The exact-runtime reconstruction, Firing Deck and Aircraft evidence in Orders
64, 65 and 66 was also freshly measured for this build, retaining those orders'
baselines and budgets. These are component results on provisional hardware.
Complete gameplay-slice and full-game performance, the 60-second mean and
300-second maximum game targets, and deferred Order 32 budgets remain
uncertified. Final checks and diagnostic history are recorded in `validation.json`.
