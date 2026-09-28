# Order 93 modifier evaluation performance

Workload: `order93-no-permission-attack-slices-v1`, versioned in
`scripts/benchmark_order93_modifiers.py`. It reuses the existing deterministic
12-attack Shooting/Fight fixture on the same provisional host and dependency
lock. One warmup and five measured samples per phase separate setup from the
phase/attack execution. All runs are serial without coverage or competing test
workers. Exact fixture/script/build hashes and host information are recorded.

The matched base is `d7bcb10b`, extracted without modifying the working checkout.
The source/archive measurement is a cost comparison, not proof of the missing
base semantics. The final comparison uses identical copies of the benchmark script and shared
fixture helpers in both checkouts. Only test workload code is copied into the
base archive; its production runtime remains the exact base. The current helper
explicitly submits the physical weapon ID supported by both versions.
The base measurements were collected from that unchanged archive after
implementation began. They provide a matched comparison, but do not satisfy
the policy's preimplementation measurement order; no earlier
measurement is claimed.

Before collecting head measurements, the local regression allowance is set to
`head mean <= base mean * 1.25 + 0.05 seconds` separately for Shooting and Fight.
The unchanged no-permission path must preserve the measured wound and decision
counts and emit zero general modifier choices. The allowance accommodates
source inventory validation and local timing variability without treating a
rules correction as an excuse for an unbounded hot-path regression. This is a
provisional slice comparison, not a calibrated complete-game budget.

The fast deterministic gates directly check the expensive branch shape: a
13-operation arbitrary subset stays at no more than four options per pending
request and survives facade persistence/replay; an AST audit rejects power-set
construction and lossy scalar modifier consumers. Existing registry callback
coverage checks that Movement providers are evaluated once per budget query.
New choices have no equivalent complete base implementation; their correctness
and bounded option width are assessed separately from unchanged-path timing.

Commands (same interpreter in each checkout, with that checkout as cwd):

```sh
PYTHONPATH=.:src /path/to/shared/.venv/bin/python scripts/benchmark_order93_modifiers.py --output /path/to/base.json
PYTHONPATH=.:src /path/to/shared/.venv/bin/python scripts/benchmark_order93_modifiers.py --output /path/to/head.json --include-choices
```

The head also records three serial samples after one warmup of a 13-operation
Charge choice, with an arbitrary alternating subset. This diagnostic measures
accepted finite submissions including live historical validation, separately
from setup, persistence export and replay. The base lacks that supported path,
so this is not presented as a matched timing certification; the CI work metric
remains the four-option maximum.

Initial measurements are retained in `base-initial.json` and
`head-before-review.json`: attack budgets and counts passed, and 13 actual
choices averaged 5.521 seconds. Their helper hashes differ because the current
melee proposal explicitly supplies the existing physical weapon ID; the final
comparison repeats the base with the identical workload helper snapshot.
These initial measurements precede the independent review repairs and do not
certify the final runtime.
The subsequent pre-aggregate measurements are retained as
`base-before-aggregate-fixes.json`, `head-before-aggregate-fixes.json` and
`comparison-before-aggregate-fixes.json`; they also precede the final repairs. The next successful behavioral revision's
measurements are retained as `*-before-work-count-repairs.json`; the final
reports below include the subsequently reviewed source-query and no-op expiry
entry guards.

## Final comparison

The final serial measurements in `base.json` and `head.json` use identical
script, fixture and lock hashes on an Apple M5 Pro with 64 GiB RAM, macOS 26.7
and Python 3.14.5. No other test workers were running. `comparison.json` records
the input hashes, matching workload/count checks and unchanged budget results.
The final runtime build ends in `6ba430dc82d3bda374b14daf4cd488144a7f653b7de12d7ef3dcf160f3a403f3`.

| Slice | Base mean | Head mean | Allowed head mean | Result |
| --- | ---: | ---: | ---: | --- |
| Shooting | 0.2382 s | 0.2695 s | 0.3478 s | Pass |
| Fight | 0.1384 s | 0.1533 s | 0.2231 s | Pass |

Each phase completed five measured samples after one warmup, with identical
wound/decision counts and no general modifier choices. The head-only
13-operation Charge diagnostic completed three samples after one warmup:
mean 5.3977 s, maximum 5.4174 s, thirteen accepted choices and maximum option
width four in every sample. This is measured choice-validation cost, not a
full-game timing prediction. Historical reconstruction on each submission is
included; export/replay timing is excluded from this diagnostic boundary.

No full games are measured. The mean below 60 seconds and observed
maximum below 300 seconds full-game objectives remain uncertified.


## Retention fixture evidence

`retention-rng-evidence.json` records why the affected retained-attack fixtures
use new deterministic game IDs. Before the first changed roll, every normalized
history token matches the base until an authenticated retention hash incorporates
the new save evidence. Removing only the redundant save audit fields from that
diagnostic snapshot restores exact equality with the base. Production keeps the
full integrity hash; the fixtures keep all behavioral, restore, replay and
redaction assertions. The first four diagnostic rows predate only the final random-symbolic source
repair and use fixed profiles; the later target-replacement and Ecstatic Death
rows record the runtime identity at their diagnostic comparison; subsequent
no-op work guards do not change those retention fields.


## Inherited performance gates

`inherited-refresh.json` records 25 serial benchmark commands, exit statuses,
report hashes and log hashes for the final runtime. These refresh the required
head reports for Orders 64–88. Original timing baselines and numeric limits
remain versioned; older tables and validation files describe historical runs.

`inherited-fixture-migration.json` proves the two changed shared helpers preserve
the measured logical workloads. The Order 77 extraction produces identical
initial, pending, submitted, final and restored payloads for all five movement
cases on the exact base runtime. The Order 88 helper emits the already-selected
physical melee weapon ID explicitly: both phases preserve twelve wound steps
and identical normalized RNG histories, with only five copies of that validated
wire field differing in the Fight history. The original Order 88 timing baseline
remains unchanged; the schema-equivalence comparison uses the later unchanged
base engine that accepts both declarations.

`action-work-counts.json` retains separate base, pre-repair and final profiles.
A conservative source probe avoids whole-army permission queries when there is
no possible source. The phase-end guard suppresses no-op mutation method entries
using the current effect inventory. The method-entry reduction alone does not
establish reduced expiry work; predicate-count evidence is recorded separately.


## Order 34 geometry measurement correction

Independent review traced a preexisting failure of the live-only visibility
counter to Order 91's target-independent shooting-unit selection. Before that
change, fixture setup performed nineteen geometry calculations and the measured
slice performed seven. The current base and Order 93 each perform two during
setup and twelve during the slice: fourteen total. Five calculations moved
across the measurement boundary and twelve unnecessary observer calculations
were removed. The declared units, decisions, attacks, dice and final state are
unchanged; `visibility-boundary-evidence.json` retains the matched proof.

The unrestricted geometry gate now explicitly resets caches before setup and
measures setup plus execution, with the historical total ceiling of 26 derived
from 19 + 7. This is a versioned measurement-boundary calibration, not an Order 93
geometry optimization or an unchanged slice budget. The historical seven-call
slice limit is retained as evidence. Every non-geometry limit still applies to
the original live slice. Repeated and interleaved runs verify deterministic cold
counts, so prior tests cannot warm the gate into passing.
