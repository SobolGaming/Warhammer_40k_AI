# Order 51 performance evidence

Provisional host: Apple M5 Pro, macOS 26.6.2 arm64, Python 3.14.5,
18 allocated CPUs and 64 GiB RAM. Seven serial samples per revision ran without
coverage, profiling or competing test workers. The reports retain setup separately,
scenario and script hashes, runtime diff, exact engine identity and all samples.
The ordinary measurements precede the Heroic measurements.

| Workload | Mean (s) | Maximum (s) | Decisions | Events |
| --- | ---: | ---: | ---: | ---: |
| Ordinary base | 0.025781 | 0.029906 | 4 | 47 |
| Ordinary head | 0.026038 | 0.030550 | 4 | 47 |
| Heroic base | 0.044001 | 0.083253 | 4 | 67 |
| Heroic head | 0.044221 | 0.081487 | 4 | 67 |

Base runtime is the detached `dc043bf27baf51c02d8db1a177190ecd77ad3254`
checkout. Only the versioned Heroic measurement driver was copied into that
checkout. Runtime modules and fixtures are unchanged. The inherited Order 50
budgets (including 0.5-second slice maximum) are unchanged and enforced by
`tests/code_quality/test_order51_flight.py`.

The original Heroic workload assumed a seeded roll would reach its fixed target.
The new decision payload changes deterministic RNG history and exposed that
assumption. `initial-heroic-base.json` and `initial-heroic-head-failure.json` retain
that attempt. The v2 workload applies a real +20 Charge-roll modifier before the
existing six-inch cap on both revisions, ensuring the same accepted four-inch
path is measured without replacing dice or validators.

Reproduce each revision with its matching runtime and the committed driver:

```sh
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_endpoints.py --include-charge-reroll-window --samples 7 --output ordinary.json
PYTHONPATH=src:. uv run --no-sync python scripts/measure_heroic_intervention.py --samples 7 --output heroic.json
```

These slices assess the shared Charge choice, validation and completion overhead.
Selected flight, reactive movement, attached units, vertical distance and Heavy
are covered behaviorally; no timing certification is claimed for those distinct
workloads. Full-game performance remains uncertified and broader efficiency work
remains deferred under Order 32. The standing full-game targets remain unchanged.

## R51-001: reactive distance enforcement

The reviewed `09aaa696` runtime passed the descriptor's four-inch allowance to
path validation despite reporting the reduced two-inch flight allowance. The
corrected runtime passes the already-computed allowance to the same validator;
there are no new calculations, searches or solver calls. Both finite and
parameterized reactive submissions consume that shared resolver.

`reactive-review-base.json` and `reactive-review-head.json` retain seven serial
samples on the same provisional host and dependencies. Each sample validates
two paths, at two and three inches, for five moving models with flight selected
and no Hover or terrain. Fixture/witness setup is outside the measured calls.
The base incorrectly accepts both paths; the corrected runtime accepts two inches
and rejects three. This base is a cost comparison only.

Base mean / maximum: **0.005375 / 0.006726 s**.
Head mean / maximum: **0.004924 / 0.005834 s**.
The existing mean-ratio, additive allowance and maximum-slice budgets remain
unchanged. A code-quality audit also verifies five path results per request and
the expected acceptance difference; no full-game certification is claimed.

Run each revision with the same committed diagnostic driver (copy only that
script into the reviewed checkout) and dependency environment:

```sh
PYTHONPATH=src:. uv run --no-sync python scripts/measure_reactive_flight.py --output reactive.json
```
