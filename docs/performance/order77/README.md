# Order 77 / P16B completed-move Action interruption

The workload measures one finite reactive movement submission through `LocalGameSession`,
after a source-backed Maintain Control start. Both revisions stop at the same legal
Shooting choice for a second friendly unit. Preparation is timed separately. Each saved Action-containing lifecycle is also
restored and checked for exact equality, with serialization and equality checks
outside the restore timer.
All five movement forms run three times, serially, without coverage or competing workers.
The first sample is cold; later samples retain process caches. The baseline has the
gameplay defect and is a cost comparison, not a correctness oracle.

Host: provisional Apple M5 Pro, 18 logical CPUs, 64 GiB RAM, macOS 26.7 arm64,
Python 3.14.5. Source seed, three-unit/fifteen-model fixture, terrain layout, library
versions and input hashes are recorded in the JSON.

| Completed move | Base submit mean / max (s) | Head submit mean / max (s) | Head restore mean / max (s) |
| --- | ---: | ---: | ---: |
| translation | 1.3568 / 3.9456 | 1.3607 / 3.9566 | 0.4539 / 0.4559 |
| return | 0.0702 / 0.0862 | 0.0711 / 0.0879 | 0.4537 / 0.4561 |
| zero | 0.0633 / 0.0653 | 0.0625 / 0.0628 | 0.4668 / 0.4918 |
| rotation | 0.0725 / 0.0888 | 0.0730 / 0.0902 | 0.4612 / 0.4624 |
| rotation_return | 0.0638 / 0.0639 | 0.0646 / 0.0651 | 0.4605 / 0.4612 |

The declared limits remain 12 seconds per submission or restore and 3× the matching base
sample plus 50 ms jitter allowance. The fast quality gate authenticates matching
inputs, current runtime identity, all fifteen interrupted outcomes and these budgets.
These component figures exclude game initialization and do not certify complete games.

```sh
uv run --no-sync python scripts/measure_order77.py --runtime-src <base-checkout>/src \
  --revision a28e84025db258825af56769eb90652d69213350 --output docs/performance/order77/base.json
uv run --no-sync python scripts/measure_order77.py --runtime-src src \
  --revision <verified-runtime-id> --output docs/performance/order77/head.json
```

The isolated baseline also requires its committed `contracts/schemas` and `pyproject.toml`.
The measurement helpers and dependency lock come from the proposed checkout for both runs.

R77-001 retains an additional pre-fix baseline in `r77_001/base.json`, measured
from PR commit `10c62302b68252778725d5af6d85a95f7f9ec5c6` before changing runtime
code. The current `head.json` must satisfy the same submission and authenticated
restore limits against both that baseline and the original main baseline. The
workload, fixture hashes, timing boundaries, host and numeric budgets are unchanged.

## Preserved phase-flow diagnostic

The earlier v1 workload has one friendly unit. Its [base](phase-flow-diagnostic/base.json)
and [head](phase-flow-diagnostic/head.json) retain all fifteen samples and the
[original limits](phase-flow-diagnostic/budgets.json). The incorrect base pauses at an
Action-completion decision for return/zero-distance paths; the fixed head proceeds
into the next turn. The per-case relative gate failed because these timed different
amounts of automatic phase work. That failure is not relabelled as a pass.

Workload v2 adds a second friendly unit so both revisions stop at the same Shooting
decision. Every movement form remains in the workload, and all numeric limits are
unchanged. The v1 script is retained locally as `reports/order77/measure_order77_v1.py`;
its exact hash is the v1 reports’ `scripts/measure_order77.py` hash.

## Validation scope

Final results and report hashes are recorded in `validation.json`. Runtime identity
changes also require fresh inherited component evidence for Orders 64–66 and 69–76.
Their original workload definitions, baseline revisions and budgets are retained.
No performance values enter deterministic engine state or replay.

Complete games attempted/completed: 0/0. No representative complete-game driver or
recording is available, so the standing mean <60 s and observed maximum ≤300 s
full-game targets remain uncertified. PFINAL is Order 78 and remains open.
