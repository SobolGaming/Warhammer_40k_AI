# Order 90 performance and validation

The matched `order89-healing-v1` workload compares the base `037e80b4` runtime
with Order 90 using identical fixture/script/dependency hashes. Five samples per
ordinary/attached heal/revival-query case run serially without coverage or
competing test/build workers on the provisional Apple M5 Pro / 64 GiB host.
Setup and query durations are separate. `base-healing.json` and `head-healing.json`
retain all samples, summary statistics, work counts and runtime identities.

The new `order90-offboard-dispatch-restore-v1` diagnostic additionally measures
finite return submission and authenticated lifecycle restore for one-wound and
full-health embarked/reserve models. It uses three samples per case with the
canonical attached-unit checkpoint fixture and checks exact returned wounds and
restored payload equality. `head-offboard.json` retains all setup, submission and
restore timings. This new workload is head-only: the base has incorrect full-health
embarked returns and cannot execute non-spatial reserve returns correctly. The
matched shared query workload remains the base/head cost comparison.

Matched shared query means in milliseconds:

| Case | Base | Head |
|---|---:|---:|
| Ordinary heal | 0.442 | 0.431 |
| Ordinary revival request | 0.515 | 0.528 |
| Attached heal | 0.440 | 0.435 |
| Attached revival request | 0.508 | 0.581 |

The largest observed increase is 0.073 ms (about 14%) in the attached revival
query. These small samples are diagnostics, not timing certification. Input
hashes and resolved-step counts match. Across the four new off-battlefield cases,
mean submission times range from 0.077 to 0.089 seconds and authenticated restore
means from 1.095 to 1.111 seconds. Each sample completed the exact wound and
restored-state assertions; all individual samples remain in the JSON reports.

Reproduce:

```sh
PYTHONPATH=/path/to/base/src:. .venv/bin/python scripts/benchmark_order89_healing.py --output /tmp/base.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order89_healing.py --output /tmp/head.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order90_revival.py --output /tmp/offboard.json
```

Inherited runtime-pinned diagnostics keep their historical baselines, workloads,
work assertions and numeric budgets. All 25 runs completed successfully. Only
current head reports are refreshed;
`inherited-refresh.json` records all 25 commands, identities, outcomes and hashes.
The new diagnostic does not establish a timing budget. Owner-deferred component
budgets remain deferred. Complete-game samples are zero; complete-game mean,
maximum and certification remain unknown.

Final validation passed all 9,497 behavioral tests with 85.17% coverage in 897.53
seconds, followed by all 694 code-quality tests without coverage in 112.54 seconds.
Both used 18 xdist work-stealing workers. The eight-shard inventory was regenerated
from the complete successful local JUnit profile and passed the exact fail-closed
check. Ruff, formatting, mypy, pyright, all eleven import contracts, both source
checks, build identity, exact-base external contract checks and pre-commit passed.
The installed wheel verified 27 schemas and 2,990 runtime resources. Direct Node
entry points passed generated-client and TypeScript checks, all five client tests,
and the HTTP conformance scenario's 342 assertions on Contract 40.0.0; the bundled
Node runtime has no npm executable. Counts, exact commands and log/report hashes
are in [validation.json](validation.json).

The first quality run passed 693 tests and found one outdated static assertion
expecting the disembark phase-history checks at their former physical-component
call sites. The assertion now requires both consumers to use the shared rules-unit
owner and verifies the original phase-start and prior-disembark checks there. The
passing behavioral coverage remains valid because this correction changed only a
code-quality test. Initial logs and JUnit are retained under
`reports/order90/code-quality-attempt1.*`.

Independent review found and rechecked four repairs: destroyed attached-component
cargo/route membership, completed location-history authentication, receiving-unit
Disembark eligibility, and complete living attached cargo on restore. The reviewer
approved the final runtime with no remaining code findings. The final staged
evidence audit also approved with no findings before the first push: it verified
all 77 staged files, raw evidence hashes/counts, benchmark inputs and baseline
preservation, contract identity propagation, and the complete 9,497-test / 264-file
shard profile. The reviewer independently passed the exact shard and engine-build
identity checks.
