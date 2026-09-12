# Order 38 disembark eligibility assessment

Workload `order38-disembark-options-v1` measures the canonical facade submission
selecting an embarked passenger through return of its movement action options.
Setup is retained separately. The five cases have no grant, Assault, Shock, both,
or an Assault grant restricted to a different passenger. Seven fresh sessions per
case retain every sample, option count, completion, mean, median, nearest-rank
P95, maximum and throughput in `base.json` / `head.json`.

The fixture uses the canonical catalog, a five-model embarked passenger, another
five-model friendly unit, a one-model Transport and five enemy models (16 total).
The Transport is at (10, 10), with no terrain or engaged enemies. Selection is
fixed, with no dice or stochastic policy in the measured boundary. Setup uses
the versioned canonical setup helpers. This measures action generation, not
placement geometry, attacks, a complete phase or a complete game.

Base `7800eac718c1b77ca1782f162cad2e10a8e3eb35` and the changed runtime use identical
script/helper/lock hashes on the same provisional Apple M5 Pro host: 18 available
CPUs, 64 GiB RAM, macOS 26.6.2, Python 3.14.5. One unpinned process runs without
coverage, profiling or competing test workers. Both reports name the checkout
HEAD; their runtime-manifest hashes distinguish the uncommitted implementation.
The incorrect base is a cost comparison, never a correctness oracle.

`budgets.json` retains the preimplementation thresholds: 1.5 times the base mean
plus 10 ms, and an observed maximum below 250 ms. The additive allowance absorbs
host scheduling noise in these short samples. At an estimated 20 selections,
the maximum budget contributes 5 seconds toward the standing 60-second game
mean objective; this is an allocation estimate, not complete-game evidence.
The code-quality gate limits each enumeration to one permission query per mode
and one engagement query, with no content-specific branching or cache introduced.

| Case | Base mean (ms) | Head mean (ms) | Head maximum / P95 (ms) |
|---|---:|---:|---:|
| Ordinary | 1.664 | 1.872 | 2.306 |
| Assault | 1.761 | 1.866 | 2.057 |
| Shock | 1.682 | 1.881 | 1.958 |
| Both | 1.706 | 1.897 | 1.931 |
| Restricted | 1.690 | 1.817 | 1.873 |

All five slice comparisons pass. These results do not certify complete gameplay
or the standing full-game 60-second mean / 300-second observed maximum targets.
The broader efficiency deferral remains unchanged.

```sh
PYTHONPATH=. uv run --no-sync python scripts/measure_disembark_eligibility.py --samples 7 --output docs/performance/order38/head.json
uv run --no-sync python scripts/check_disembark_eligibility_performance.py
uv run pytest tests/code_quality/test_phase14i_14h_closeout.py -k order38 --no-cov
```

For base, export the named revision and copy the versioned measurement script and
`tests/disembark_eligibility_helpers.py` into it. Use the same Python executable,
with that checkout and its `src` first on `PYTHONPATH`. Run sequentially on the
same host. Hardware metadata requires access to macOS `sysctl`.
