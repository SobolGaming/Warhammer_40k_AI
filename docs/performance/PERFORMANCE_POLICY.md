# Rules-engine performance policy

Policy ID: `rules-engine-performance-v3`, owner-approved tiered workflow,
2026-10-01. This version supersedes inherited requirements to refresh every
historical head report whenever the global runtime ID or a shared fixture hash
changes. It does not turn any previously failed measurement into a pass.

## Required evidence tiers

Every PR, including documentation and development-tool changes, must provide
`docs/performance/change-assessment.json` and pass the real serial smoke:

```sh
uv run --no-sync python -m scripts.check_performance_policy --base-ref <exact-PR-base-SHA>
```

Run this before the complete quality suite, without coverage, profilers or
competing test workers. CI runs it in the existing required `code-quality` job
before xdist. Both that command and the aggregate reject missing/stale current
evidence. Receipts and failed attempts remain under `reports/`; CI uploads them
in `code-quality-report`. The correctness, live work-count, cache, source,
reconstruction and replay gates remain unconditional.

1. **Historical integrity.** The v3 inventory pins the exact retained reports,
   budgets and migration proofs to revision
   `7f45d87d3094c76beb1be58e0cabb721dec21053`. Their original identities, samples,
   outcomes and numeric-budget checks remain historical claims. Historical input
   assertions resolve hash-checked Git bytes at that revision, with no fallback
   to current files. Keep that ancestor reachable: a shallow clone must fetch
   the required history before validation; missing objects are errors, not
   skipped checks. Mixed quality modules still inspect and execute current
   source for their live semantic/ownership/work/cache assertions.
2. **Current smoke and assessment.** Two real current-runtime cases execute on
   every PR: ten paired candidate/LOS queries in the associated-Woods scene;
   and normal facade Rapid Ingress/Disembark followed by JSON persistence,
   both viewers/event consumers, fork isolation and exact replay. Each fresh
   process has a 60-second limit including imports/setup; the serial workload
   has a 180-second overall limit. The first Windows calibration completed in
   17.73 and 28.74 seconds respectively. These deliberately generous limits
   detect hangs/major slowdowns; they are not old component-budget certification.
3. **Applicable detailed comparisons.** Changes to algorithms/search, cache
   policy, serialization/replay work, hot queries/data structures, measured
   workloads or relevant runtime dependencies require matched detailed evidence
   for the operations actually changed. Use the actual PR base and head,
   identical current workload/fixture bytes and dependency lock, the same
   declared host, original workload sample counts, all hard cases and semantic
   completion checks. Current evidence lives under `docs/performance/current/`;
   never overwrite or repin the original historical comparison to the PR base.
4. **Milestones.** A rules-complete milestone requires comprehensive applicable
   component comparisons and supported complete-game profiling. The initial
   operation map contains ten representative existing drivers; milestone review
   must extend it for every newly supported operation. An unavailable legal
   complete-game driver or missing complete-game evidence is incomplete, not a
   passing substitute. Full-game goals remain mean below 60 seconds and no
   measured game above 300 seconds on declared reference hardware.
   The full-game driver registry is currently empty: a future supported driver
   and its workload must be registered and independently reviewed before this
   milestone can pass. Merely setting a completion/support flag is insufficient.

## Objective applicability and review

The assessment binds an explicit reachable base, actual changed paths and their
before/after hashes, changed Python owner AST hashes, current runtime identity,
and the versioned operation map. Every changed input has a row. Unknown paths,
owners, categories or operations; omitted changed owners; stale hashes; missing
selected evidence; and unrecognized fields are errors. The one fixed assessment
path is excluded from its own content digest to avoid recursion; its schema,
base, map, exact change coverage and obligations are still validated. No other
changed input is excluded from the assessment. Comparison records bind measured
runtime/workload inputs rather than a future self-referential commit hash; the
current CI receipt records the actual checkout and PR head separately.

CI supplies the exact PR base, merge-group base or push-before SHA. The command
requires `--base-ref`; it never guesses `HEAD^`, silently accepts missing history,
or reuses a stale committed assessment. A GitHub merge checkout is recorded as
such and must contain the declared PR head; the assessment describes its actual
effective input changes against the supplied base.

Rows classify changed owner operations, not all consumers of a global build ID.
Ordinary source-backed rule branches/validation/lifetime changes include the
source obligation and an explicit unchanged-work explanation. They require the
smoke and relevant live semantic/work controls; a file's mere participation in
orchestration does not select all historical families. Critical algorithm,
cache, serializer and hot-query selectors cannot be downgraded by prose. An
unlisted owner requires a reviewed map addition. A recognized neighbor in the
same file cannot cover an unrecognized changed owner.

Dependency assessments state the packages' actual roles and effects. Runtime
libraries select relevant comparisons; development-only tool changes do not
automatically select every engine family. The exact lock diff remains bound and
reviewed. The checker verifies the declared coverage/triggers/evidence; independent
exact-head review must judge semantic classification and dependency-role accuracy.
There is no skip/exempt flag or environment-variable bypass.

### Order108 source-backed terrain semantics

The owner's subsequent-order direction in
`docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md` makes the serial current-runtime
smoke the default for bounded rule repairs. Detailed comparisons apply to
deliberate performance changes or a demonstrated serious regression. Order108
changes terrain predicates to implement the reviewed source obligations; it is
not a performance optimization or a claim of full-game certification.

`policy-v3/order108-rule-semantics.json` authenticates the complete before/after
file hashes and changed owner AST hashes for this repair, against exact base
`eebdaa2ccadef14b6115aea7caea3cb1c89eb564`. Only an exact matching `rule_semantics`
row uses smoke instead of the detailed families otherwise selected by
`geometry-search` and `visibility-query`. Those operations remain mandatory and
sensitive in the operation map. A different base, path, file, owner, hash or
category retains the original detailed-comparison requirement. Other sensitive
operations, including cache policy, receive no exception.

Every assessment row, source/unchanged-work explanation, current runtime binding,
serial smoke and live semantic/work/cache check remains required. Historical
measurements and the separate Order103 numerical recognition remain unchanged.
Future orders cannot inherit this exact-base authentication; assess their own
scope under the owner's direction and carry that maintenance into the handoff.

### Single owner-approved Order103 failure

On 2026-10-02 at 11:20:34 UTC the owner approved delivery recognition of
exactly one already-measured failure: Order103 `dice_sustained/shooting/true`
mean 2.481014919979498 seconds against the unchanged 2.262186475022463-second
limit. The recorded approval is `policy-v3/order103-owner-exception.json`.
The original five base/head samples, exact base/runtime/host/workload and
input identities remain immutable. The result is an **owner-approved failure**,
never a numerical pass. Its maximum and all other inequalities remain required.

Enforcement recognizes only the fixed approval and complete original comparison
fingerprint. A changed, missing, unused or unrelated recognition fails closed.
`policy-v3/order103-exception-applicability.json` separately authenticates the
four exact policy/checker/quality input changes needed to implement recognition;
the measured inventory and digest are retained. No engine, workload, fixture or
lock change can inherit those samples. Live smoke always binds the complete
current input inventory and reports approved failures explicitly. This approval
creates no general exception, threshold change, optimization authorization or
waiver of correctness, reviews, CI, smoke or aggregate gates.

## Current-change budgets and historical qualification

`current-change-relative-v1` is a new versioned engineering envelope: arithmetic
mean at most `1.25 * matched_base_mean + 0.05 s`, and observed maximum at most
`1.5 * matched_base_maximum + 0.10 s`. The multiplicative allowance tolerates
ordinary host/process variability, while additive floors avoid overreacting to
very short operations. Retained same-host exact-main/V963 diagnostic mean ratios
were approximately 0.985–1.009 for the long revival/setup cases; this envelope is
deliberately wider. This limited evidence motivates a conservative regression
screen, not a statistical confidence bound or a proof of full-game speed.
Semantic outcomes, sample counts, work/cache limits and the separate hang smoke
remain mandatory. A family's explicitly declared stricter profile must be used;
an unknown profile fails until its versioned enforcement is implemented/reviewed.

Old host-specific absolute component ceilings remain checks on their original
historical records. They are superseded as automatic current-host readiness
criteria by the tiers above. The 62 Windows V963 refresh measurements and 14
failed inequalities, also reproduced on exact main, remain retained failures in
the separately isolated V963 evidence. They are not policy-PR passing evidence.
Record pre-existing/environment-specific failures explicitly in new comparisons;
never discard samples or silently alter baseline, host, workload or threshold.

New detailed records bind both measured runtimes, the exact PR-base runtime,
actual current lock and driver hashes, and the complete shared measurement
fixture/script inventory digest. Matching two stale hashes is insufficient.
Retain raw measurements and preparation qualification, including any reviewed
fixture migration. Timing values remain outside authoritative state and replay.

The earlier guidance below remains applicable subject to the explicit v3 tier
and historical/current separation above. Historical per-order README refresh
instructions describe their earlier policy version; they do not override v3.

## Order 32 owner-directed deferral

Later in the same task on 2026-09-08, the owner explicitly chose to use the
correct continuous/planar formula and defer efficiency work until a complete
head-to-head headless game can be measured. This supersedes Order 32's proposed
component timing thresholds, comparative timing certification, and performance
CI gate as publication/merge-readiness prerequisites. It does not change their
measured results into passes or establish full-game performance certification.
The 60-second mean / 300-second observed maximum full-game objectives remain
recorded for that future assessment. No training system or new game driver is
authorized by this deferral.

Keep the baseline, difficult scenarios, timeouts, and reproducible diagnostic
command. Correctness, complete validation, shared engine authority, deterministic
records, bounded caches and stale-result rejection remain required now. The
general policy below remains the standing guidance for subsequent assessment;
apply this explicit deferral to Order 32.

The owner subsequently approved narrowly scoped exact-solver repairs needed to
complete ordinary gameplay tests and CI. This permits mathematically justified
termination proofs for the observed stalls; it does not resume broader efficiency
work or allow timeouts to become invented visibility answers.

Performance is part of delivery correctness. The supported full-game workload
must achieve an arithmetic mean **below 60 seconds**, with **no measured game
above 300 seconds** on declared reference hardware. Retain incomplete games,
timeouts, and threshold violations as failures. A finite sample cannot prove a
universal worst-case bound. Semantic correctness and deterministic replay remain
separate mandatory gates; interactive and headless execution share authority.

Assess changes to hot paths, algorithms, data structures, caches, and gameplay
orchestration. Extend the existing benchmark/profiling infrastructure; choose
optimizations from measured evidence. Current rules-engine profiling and
optimization are authorized independently of later AI/training work.

Before changing an implementation, version the benchmark workload and measure
the base. Repeat identical base/head measurements on the same machine and
dependency lock. Record CPU model/allocation, memory, OS, interpreter and library
versions, roster/model counts, terrain shapes/complexity, seeds, decision policy,
concurrency, setup/preparation/query timing boundaries, and script/config hashes.
Until production hardware is selected, label the available host provisional.
Run timing samples without coverage, profiler/debug instrumentation, or competing
test workers. Profile work counts and memory separately. Report sample count,
mean, median, percentiles, maximum, completion rate and declared throughput.

Commit numeric component/slice budgets and regression thresholds, with the
measurement variability and workload rationale that selected them. Tie component
budgets to observed calls per phase/game and the 60-second objective; label
extrapolations as estimates. An incorrect base is a cost comparison, never a
correctness oracle. Do not silently change thresholds or discard hard scenarios.

Every affected PR needs a fast meaningful CI gate based on stable work metrics
and/or calibrated timing comparisons, plus a reproducible fuller command and
machine-readable results. Include the fast gate in an appropriate required
aggregate. Missing or skipped evidence is incomplete. A PR with an unmet required
budget is not ready for merge. Independent review assesses performance as well
as semantics; report correctness, performance and CI status separately.

Caches must be bounded and cover all geometry, presence, keyword, terrain and
rules-policy inputs. Demonstrate cached/uncached agreement, invalidation after
movement, casualty, retained-presence cleanup and restoration, and isolation
across independent games. Timing/profiling values stay outside deterministic
authoritative state and replay records. Timeouts and unresolved calculations
must not invent rules answers or bypass validation.

Inspect supported headless capability before claiming full-game certification.
Reuse a legal existing driver or recorded workload. Measure per-game initialization
through normal completion, including legal-action generation, policy decisions,
engine execution and normal replay/log output; report worker startup separately.
Separate policy/search and engine costs without removing either from end-to-end
totals. If complete games are not supported, deliver component/slice gates and
record full-game certification and its missing prerequisites as outstanding.

Order 32 preimplementation evidence and remaining acceptance obligations are in
`ORDER_32_VISIBILITY_REVIEW.md` and `order32/`. A diagnostic baseline or prototype
is not a passing delivery gate.
