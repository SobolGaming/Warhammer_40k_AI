# R48-002 collateral retained-checkpoint restoration

The affected boundary is restoration of a pending Core Stratagem packet whose
continuation is a retained descendant of an original casualty. The workload also
covers the completion receipt after accepted collateral cleanup resumes through
a later declined rule reaction.

`base.json` uses reviewed commit `9dd78ed35fbe757d79232ffe99388007ef184b12`.
`head.json` identifies the revised working tree by its verified runtime hash.
Both use the same script, fixtures, lockfile and provisional local Mac host;
reports record those hashes and hardware details. Samples run serially without
coverage, profiling or competing test workers. Preparation and exact round-trip
comparisons are outside the restore timing boundary. Successful restores must
round-trip identically.

For Crushing Impact and Explosives, source-backed For the Chapter! is offered
for a Deadly Demise collateral casualty. Each scenario saves an offered checkpoint,
an accepted checkpoint, a completed checkpoint declining reactions, and a
completed checkpoint after accepting the first collateral reaction. The fixture
reloads catalog-backed reaction sources alongside its added Deadly Demise before
capturing the initial replay state. Behavioral tests additionally cover two
levels of collateral ancestry and exact replay after both accepting and declining.

Rejected base checkpoints are recorded as correctness failures, never timing
passes. Unchanged valid checkpoints provide matched restore-cost comparisons.
Both accepted/completed paths add a retained completion receipt and its parent
shooting-resumption event. On the base, Crushing Impact still has the removed
retention record and therefore restores, but has not closed that continuation.
Explosives advances past phase expiration, which discards the unclosed record and
makes restoration fail. Both now close the retained continuation explicitly.

Run from both checkouts with identical final fixtures and the same environment:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/measure_stratagem_retention_restore.py --collateral-depth 1 --samples 7 --output docs/performance/order48/r48-002/head.json
```

The predeclared budgets retain a 2x plus 50 ms matched successful-restore mean
and a 10-second maximum for any head restore. The static gate checks every scenario
and sample, matching fixture/environment hashes, expected work counts (including
the two completion/resumption events), exact base outcomes and successful head restores.
These local component bounds do not certify the standing full-game 60-second mean
or 300-second maximum targets; broader efficiency work remains deferred.

| Stratagem / checkpoint | Base outcome / mean | Head mean | Head maximum |
| --- | ---: | ---: | ---: |
| crushing-impact / offered | Rejected | 2.2514 s | 2.2698 s |
| crushing-impact / accepted | 2.2764 s | 2.2879 s | 2.3076 s |
| crushing-impact / completed | 3.4591 s | 3.4378 s | 3.4539 s |
| crushing-impact / accepted_completed | 4.5161 s | 4.5155 s | 4.5389 s |
| explosives / offered | Rejected | 1.3825 s | 1.4148 s |
| explosives / accepted | 1.4091 s | 1.4238 s | 1.4434 s |
| explosives / completed | 1.7588 s | 1.7663 s | 1.7692 s |
| explosives / accepted_completed | Rejected | 1.7843 s | 1.7890 s |

All 56 head samples restored exactly and met the declared bounds. Reports
identify Apple M5 Pro, Python 3.14.5, 18 allocated CPUs and
68,719,476,736 bytes RAM on macOS-26.6.2-arm64-arm-64bit-Mach-O. The verified runtime is
`warhammer40k-core-v2:runtime-tree-sha256-v1:597863f4481249dc938c4b80f11d0a1f366ca1455096af85d1dce7a7528d2850`.
