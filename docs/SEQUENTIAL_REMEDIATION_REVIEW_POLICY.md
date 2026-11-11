# Approved review policy for subsequent remediation orders

The repository owner approved this policy on 30 September 2026 during Order101.
It applies to subsequent orders, beginning with `THROUGHPUT-AFTER-101`, then
Order102 onward. Order101 finishes under its existing acceptance and review gates.

Prioritize complete playable rules and faction support. This priority does not
expand an order's authorized implementation scope, authorize prohibited content,
or present load-only faction content as implemented gameplay.

## Blocking findings

Block on incorrect rules, normal legal gameplay failures, and save/load or replay
failures reproducible from engine-generated valid state. Explicitly required
trust-boundary failures also block. Every blocking finding must state:

1. The reproduced entry path and exact reviewed head.
2. The concrete user impact.
3. Whether normal engine-generated state reaches the failure, including evidence
   and any unproven step.
4. The violated order acceptance requirement or explicitly required supported-input
   boundary.

A source suspicion or hypothetical attack is not a reproduced normal-play defect.
Distinguish incorrect rules, normal gameplay, genuine save/load/replay, supported
input validation, and manually modified historical state in the report.

## Separately queued work

Queue deeper tamper resistance and coordinated hand-edited-history findings as
separate integrity-hardening work when no normal path or necessary supported-input
boundary is demonstrated. Preserve the reproduction and evidence without claiming
the queued issue is fixed or that snapshot integrity is universally certified.
The queue is not authorization to implement or merge that work silently.

Keep review focused on the order's acceptance criteria and affected behavior.
Expanding implementation or blocking scope requires an explicit decision. A
reviewer must identify the new scope and why the current acceptance requirement
cannot be completed locally before asking for expansion.

## Unchanged delivery gates

Preserve required regression tests, positive legal-path controls, truthful source
evidence, shared engine authority and exact-head validation. This approval removes
neither complete covered behavioral validation nor complete remote CI. For PR591,
the owner-approved exception below uses required hosted covered shards as the
final complete run, without a duplicate local full run. Both type checkers and
all other applicable quality/generated/contract/package gates,
required behavior shards and coverage thresholds remain mandatory.

Independent coding and fresh parent Astra reviews must be clean under this scoped
policy on the exact final head. Any subsequent change invalidates stale reviews
and applicable evidence. This policy grants no merge authorization by itself.

## Required prompt text

Include the following in each subsequent implementation/reviewer prompt and parent
Astra audit packet, together with the order's explicit acceptance criteria:

> Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`. Prioritize the complete
> playable behavior in this order. Block on incorrect rules, normal legal-play
> failures, engine-generated valid-state save/load/replay failures, and explicitly
> required trust-boundary failures. For each blocker provide the reproduced entry
> path, impact, normal reachability and violated acceptance requirement. Queue
> coordinated hand-edited-history hardening separately when no necessary supported
> input boundary or normal path is demonstrated. Keep scope within this order;
> expansion requires an explicit decision. Preserve positive controls, regression
> tests, source truthfulness and every required local/remote exact-head gate.

The author must give reviewers the selected source obligations, affected owners,
consumer paths, supported input boundaries, pending checks and exact base/head.
Reviewers derive requirements from that evidence rather than treating the author's
conclusions as approval.

## Roadmap completion record

Every implementation PR must update its own Orders-table **How it is currently
done** cell in `CORE_RULES_REMEDIATION_ROADMAP.md` before the final input freeze.
Replace generic audit-gap text with the concrete prior behavior and the resulting
shared implementation, grounded in the scoped source, code and tests. Preserve
unrelated table content and carry this requirement into the next-order handoff.

## Subsequent-order model plan and evaluation

The owner's subsequent direction supersedes the earlier Sol High/Ultra plan:
explicitly select GPT-6 Astra (`gpt-6-astra`) with High (`high`) for
implementation and separate independent coding review, beginning with
`THROUGHPUT-AFTER-101`. Preserve the additional fresh parent Astra audit and
its exact-head verdict; an author's or coding reviewer's selection does not
satisfy that separate audit. Stop rather than silently substitute a model.

Verify accepted explicit model/effort selection and retain any limit on resolved
runtime attestation. Do not silently substitute a model or claim effort tiers have
independent capacity. No measured speed or quality advantage is asserted here.

The owner updated this workflow on 2 October 2026 after Order 103: High replaces
Extra High; use the requested 1.5x speed when the execution environment exposes
that control, without claiming an unavailable runtime setting. Use one
implementation/review cycle with necessary fixes. Run the independent coding
review alongside validation and the fresh parent audit alongside hosted CI.
Keep automatic evidence capture off the critical path; archive transfers are not
publication prerequisites. Do not add repeated intermediate planning, benchmark,
or evidence reviews. Preserve both clean exact-head reviews, complete correctness
inventories, covered behavior at the active threshold below, quality/type/lint/contracts,
required hosted CI and branch protections.

On 29 October 2026, the owner raised the temporary coverage floor to 64%
(from the 50% floor approved on 28 October),
superseding the active 85% requirement. Coverage still measures the complete
warhammer40k_core package with branches; the denominator and default omissions
and exclusions are unchanged. CI must combine all required successful behavioral
shards before enforcing the threshold. Retained test failures and every other
required gate continue to block merge. This authorization is not a coverage,
CI, publication or merge success claim.

Post-merge coverage work must rebuild coverage and restore the 85% requirement
in configuration, CI and active documented commands. Historical 85% receipts,
source pins and prior qualification records retain their original meaning and
bytes; the temporary floor does not reclassify a historical failure as a pass.

For these bounded repairs, the default performance evidence is the existing
serial current-runtime smoke and exact-base assessment. Detailed benchmarks are
required for deliberate performance changes or a demonstrated serious regression.
Preserve historical measurements and live semantic/work/cache checks. This
owner direction supersedes broader comparison defaults, without extending the
Order 103-only numerical exception or claiming full-game performance certification.

For the next few orders, retain timestamped phase transitions and actual command
durations, review findings and their normal reachability, repair/revalidation
cycles, invalidated evidence, interruptions and first/final head identities. Track
elapsed time and rework separately. Concurrent command sums are not wall time;
unknown active time remains unknown. Evaluate measured results before claiming a
throughput or quality improvement from this model plan.

## PR591 prototype cutover exception — 28 October 2026

The owner explicitly approved removing fresh comparative benchmark evidence as
a prerequisite for this cutover and deferring the exact 260 comparison/preservation
quality cases recorded in the cutover ledger. Preserve historical reports with
their original outcomes; deferred comparisons and checks are not passing results.
All 4,886 selected gameplay cases remain required. Keep active quality, both type
checkers, lint, source/dependency integrity and the serial absolute performance
smoke with its unchanged 180-second complete-command allowance.

For this PR only, focused local checks plus the required hosted twelve covered
shards replace the duplicate complete local covered run. The hosted shards must
all succeed and their combined full-package branch coverage must meet 64%. No
local partial result substitutes for that gate. Preserve all other required CI
checks and branch protections. Restore 85% through the documented post-merge work.

On 29 October 2026, the owner separately approved deferring the exact 103
historical-preservation controls in addition to the prior 157 comparison controls.
The 260-case list remains finite and code-pinned. These include adversarial checks
of retained historical helpers; they are not passing results. Keep helper code,
active production and preflight/postflight validators, 1,848 active quality checks
and all 4,886 selected gameplay cases. No additional omission is authorized.

## Coverage floor update — 1 November 2026

After Defiler PR604, the owner directed raising the active coverage requirement
from 64% to 65%. Configuration, the combined CI coverage gate and active local
commands enforce 65%. Full-package branch measurement, default omissions and
exclusions, required behavioral selection, the exact 260 deferred quality cases,
and all timing budgets remain unchanged. Later coverage work must restore 85%.

The PR591 cutover ledger and its authenticated 64% field remain historical source
records. Their admission checks retain that exact value; they do not configure the
active coverage threshold. Prior measurements, approvals and qualification records
retain their original meaning. This update does not claim any gate has passed.

## CI and coverage update - 6 November 2026

The owner approved a thirteen-minute CI goal and raised the active coverage
threshold from 65% to 66.5%. Behavioral source-index setup and covered execution
use a 780-second step cutoff. Local configuration, documented commands and the
combined CI coverage gate enforce 66.5%, with two decimal places so the fractional
boundary is checked precisely.

Full-package branch measurement, the selected tests, coverage omissions and
exclusions, the exact 260 deferred quality cases, the 120-second bounded mirror
runner, performance comparisons and every other delivery gate remain unchanged.
The separate 180-second complete performance command and 600-second quality-lane
limits remain in force. Post-merge coverage work must still restore 85%.
Historical records retain their original thresholds and outcomes; no prior failed
CI run is reclassified. A per-step cutoff does not prove the end-to-end CI goal.

The owner's subsequent conditional authorization took effect after behavioral
shard 12 in run 42285919569 completed all 259 cases but timed out during
finalization at thirteen minutes. The active CI goal and behavioral setup/test
cutoff are now fourteen minutes (840 seconds), superseding the earlier
thirteen-minute limit. The 66.5% coverage floor, complete branch denominator,
selected cases, exact 260 deferrals, 120-second mirror runner, 180-second serial
smoke, 600-second quality limits and every other check remain required. Earlier
failed runs retain their original outcomes; this update is not a qualification
claim.

## CI and coverage update - 9 November 2026

After PR647, the owner directed raising the active full-package branch-coverage
floor from 66.5% to 67% and allowing a fifteen-minute CI limit. Configuration,
active local commands and the combined CI coverage gate enforce 67%, retaining
two decimal places. The behavioral source-index setup and covered-test step,
including its internal source-index deadline, now allow 900 seconds. The total
CI goal is fifteen minutes; a per-step cutoff does not prove that goal passed.

The complete branch denominator, selected tests and inventories, omissions and
exclusions, exact 260 deferred quality cases, 120-second bounded mirror runner,
180-second serial performance command and 600-second quality limits remain
unchanged. Exact-base assessment, independent reviews and all other required
local and remote gates remain mandatory. Later coverage work must restore 85%.

Earlier thresholds and outcomes remain historical. PR647 main run 42625649279
attempts 1 and 2 failed behavioral shard 8 at the fourteen-minute limit; combined
coverage did not run. Incomplete worker progress journals do not establish
completed tests or passing coverage. This policy update does not reclassify those
failures or establish that the fifteen-minute limit is sufficient.

## Covered-shard timing amendment - 9 November 2026

The owner's subsequent direction supersedes the fifteen-minute timing target
above. Every covered behavioral shard must complete successfully within 18 minutes
(1,080 seconds inclusive) for approval. Timing alone must not terminate a running
shard at that approval boundary: execution is allowed through exactly 30 minutes,
with process-group termination only when elapsed time exceeds 1,800 seconds.

A shard whose tests pass after 18 minutes still fails approval. Preserve its full
JUnit, coverage and timing results. On termination or failure, preserve available
logs, progress journals, partial reports and coverage fragments as diagnostics;
never fabricate completed tests, complete coverage or a passing timing result.
The combined coverage gate continues to fail if any shard is late, failed or
incomplete, even when available tests passed.

One monotonic supervisor clock includes source-history validation, source-index
construction, the isolated mirror, parallel tests and child report finalization.
The cold construction barrier consumes the same exact monotonic execution deadline.
Supervisor diagnostic copying/log replay is recorded separately from observed
workload completion. The workflow's 32-minute outer safety guard supplies cleanup
and reporting grace; it is not an approval allowance.

Keep twelve shards, all existing behavioral tests, the complete 67% branch
coverage floor, mirror 120-second bound, serial performance 180-second bound and
quality 600-second limits. Verify exact boundaries, late passing-test result
retention, descendant cleanup and partial-result failure behavior. Report observed
durations separately from limits. Earlier fifteen-minute timeout records remain
historical failures and do not reveal when unfinished tests would have completed.

## Covered-shard timing amendment - 11 November 2026

After the current hosted run `43105204846` and concurrent local covered run
finished, the owner raised covered behavioral approval to 27 minutes
(1,620 seconds inclusive). This supersedes the active 18-minute approval target
above. Timing alone still permits execution through exactly 30 minutes and
terminates the owned process group only when elapsed time exceeds 1,800 seconds.
A successful workload completing after 1,620 seconds fails approval while its
complete results are retained. Failed, interrupted, terminated or incomplete
workloads still fail, and the combined coverage gate still requires every shard
to succeed. The monotonic clock scope and 32-minute outer cleanup guard are unchanged.

Earlier 1,080-second receipts, validators of that historical evidence and all
original run outcomes remain unchanged; this amendment does not reclassify any
prior failure. The accepted allocation retains its finite 1,076 / 1,054 / 1,050
planning budgets on their original 18-minute basis. Keep all 6,282 behavioral
cases, twelve shards, four hosted workers, local 32-worker qualification, 67%
full-package branch coverage, exact 260 deferred quality cases, mirror 120-second
bound, serial performance 180-second bound and quality 600-second limits. Fresh
exact-head local and hosted gates and both independent reviews remain required.
