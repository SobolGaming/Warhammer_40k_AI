# CORE V2 Architecture

## 1. Purpose

CORE V2 is a clean bottom-up reconstruction of the Warhammer 40,000 engine using selected concepts and vetted code from the legacy repository, but not inheriting its permissive fallback behavior, stub-heavy testing style, or divergent UI/headless/network execution paths.

The legacy repository remains valuable as:

- a reference implementation;
- a replay and audit corpus;
- a source of known bugs and invariants;
- a source of selected algorithms that may be ported only after review;
- a comparison harness for deterministic replay and behavior.

CORE V2 is not a blank rewrite. It is a strict reconstruction with enforced invariants.

Source-linked model geometry requires representative model height with provenance
before runtime catalog use. Explicit provisional estimates retain their uncertainty and
source identity under [the geometry authority policy](docs/FACTION_RULES_SOURCE_POLICY.md).

The bounded Stage 2 AI operator fixtures now include a
[witnessed Normal Move alternative](docs/AI_POLICY_INTERFACE.md#witnessed-normal-move-prefix-admission)
from the preservation fixture's exact fifteen-decision pre-choice prefix.
Eighteen ordinary viewer decisions move all five S models one inch in negative X
and consume S's activation, with strict persistence/replay admission. This is
movement feasibility evidence; screening, exposure, opponent threat, E follow-through,
later outcomes and learning eligibility remain unqualified. The original
preservation definition and receipt retain their meaning.

The separate [paired followthrough admission](docs/AI_POLICY_INTERFACE.md#paired-followthrough-and-opposing-shot-probe)
continues both branches with the same witnessed E movement and a stationary
vehicle, reaching B's end-of-Movement Fire Overwatch request. A fixed ordinary
target-binding probe on an independent fork is rejected because B has no legal
shooting declaration at that window. This qualifies movement feasibility and a
specific negative shot result; it supplies no attack outcome or tactical benefit.

The separate [opposing shooter qualification](docs/AI_POLICY_INTERFACE.md#opposing-shooter-qualification)
checks the equipped rifles, shooter eligibility, range and visibility at both exact
endpoints. B is eligible; every A target is outside 24 inches, while E is visible.
A fixed continuation of the stationary branch then approaches through ordinary
Normal Moves and resolves one B rifle attack against E in round three. A remains
stationary and declines reactions. This is one attack-feasibility witness; paired
outcomes, tactical benefit, Stage 2 completion and learning remain unqualified.

The separate [matched attack comparison](docs/AI_POLICY_INTERFACE.md#matched-opposing-attack-comparison)
extends both original endpoints through the same cooperative approach and rifle
attack to round-four player-A Movement. It verifies both complete prefixes by
strict persistence/replay and compares E's wounds, survival and positions at that
common horizon. Both branches retain all three E models with two wounds each and
identical E positions: the observed wound and survival differences are zero.
The report records the shared timing, stationary choices and declined reactions;
adversarial alternatives, tactical benefit, broader costs, Stage 2 completion and
learning remain unqualified. Historical reports retain their narrower meanings.

The [bounded E follow-through operator experiment](docs/AI_POLICY_INTERFACE.md#bounded-e-attack-operator-evidence)
continues those matched endpoints with the same witnessed six-inch E approach,
then compares E's carbine attack with omitting the attack. Both attacks complete
and all four prefixes pass persistence/replay. B loses one wound in the stationary-S
attack arm and zero in the other three arms; no models die and the VP difference
is zero. The historical branches start with different RNG states, so that damage
difference does not establish an S benefit. This retained operator evidence adds
no runtime admission or learning eligibility; Stage 2 remains incomplete.

## 2. Non-negotiable invariants

These rules are enforced from the first commit.

1. Engine core is fail-fast.
2. No broad exception handling: no bare `except`, no `except Exception`, no `except BaseException` in engine/core/rules/geometry without an explicit allowlist entry.
3. No silent fallback behavior. Unsupported rule paths must return typed invalid/unsupported results or raise explicit domain errors.
4. No player choice outside `DecisionRequest` / `DecisionResult`.
5. UI, headless, network, replay, and test drivers all use the same decision and command path.
6. Engine alone mutates authoritative game state.
7. Movement, charge, pile-in, consolidate, disembark, reserves, and reactive movement require `PathWitness` or an explicit typed invalid result.
8. Endpoint-only movement validation is invalid unless the rule explicitly models teleport/set-up placement.
9. Raw rule text is normalized once at the data boundary; runtime engine code consumes structured descriptors.
10. Physical battlefield operations must operate on explicit model groups, not ambiguous `unit.models` semantics.
11. Attached units are first-class rules units, not an afterthought.
12. All entity IDs, action IDs, event IDs, and replay payloads are deterministic and serializable.
13. Decision records must never contain Python object reprs or memory addresses.
14. Tests for movement, shooting, charge, fight, transport, attached unit, replay, UI, and network behavior use real domain objects or canonical fixtures, not partial `SimpleNamespace` stand-ins.
15. Stubs are allowed only for pure functions and must be marked `stubbed`.

## 3. Repository layout

```text
warhammer40k_core/
  core/
    ids.py
    rng.py
    dice.py
    attributes.py
    modifiers.py
    wargear.py
    weapon_profiles.py
    model.py
    unit.py
    attached_unit.py
    unit_group.py
    battlefield.py
    objectives.py
    deployment_zones.py
    datasheet.py
    army_catalog.py
    faction.py
    detachment.py
    ruleset_descriptor.py
  geometry/
    pose.py
    base.py
    volume.py
    spatial_index.py
    visibility.py
    pathing.py
  rules/
    text_normalization.py
    parsed_tokens.py
    source_data.py
    source_catalog.py
    data_package.py
    descriptors.py
    timing.py
    effects.py
    registry.py
  engine/
    decision_request.py
    decision_result.py
    decision_queue.py
    decision_controller.py
    decision_record.py
    event_log.py
    replay.py
    validation.py
    lifecycle.py
    game_state.py
    setup_flow.py
    battle_round_flow.py
    phase.py
    army_mustering.py
    unit_factory.py
    list_validation.py
    battlefield_state.py
    placement.py
    phases/
      command.py
      movement.py
      shooting.py
      charge.py
      fight.py
  adapters/
    headless.py
    ui.py
    network.py
  interfaces/
    cli.py
  tests/
    fixtures/
    unit/
    integration/
    replay/
    code_quality/
```

Dependency direction:

```text
core     -> may import pure geometry helpers; not rules/engine/adapters
geometry -> no rules/engine/adapters/interfaces; pure helpers do not import core
rules    -> may import core and descriptors, not adapters
engine   -> may import core, geometry, rules
adapters -> may import engine, never the reverse
```

## 4. Build order

Develop bottom-up; add the owning invariant and focused tests before dependent behavior:

1. Governance, deterministic RNG/dice, attributes, modifiers and source normalization.
2. Models, attached units, geometry, visibility, pathing, objectives and missions.
3. Typed decisions, events, replay, lifecycle routing and shared adapter contracts.
4. Movement, shooting, charge, fight, setup, reserves and transports.
5. Source-backed catalogs, generic RuleIR execution and faction coverage.
6. Viewer-safe headless, CLI, UI and network adapters.
7. AI/rankers/training after deterministic rules and replay are trustworthy.

Use [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md) for the detailed roadmap and the
[performance policy](docs/performance/PERFORMANCE_POLICY.md) for required assessments.
Keep subsystem progress in its focused documentation instead of this README.

## 5. Test policy

### Pure tests

May use stubs only for pure functions. Must be marked `stubbed`.

### Engine contract tests

Use canonical real fixtures. Required for:

- movement;
- shooting;
- charge;
- fight;
- deployment;
- transports;
- attached units;
- damage allocation;
- replay;
- decision dispatch;
- network serialization.

### Replay tests

Use real games and real replay logs.

Every replay bug must add:

- a narrow regression test;
- a bug-class or invariant test;
- a replay/audit fixture if reproducible.

## 6. Static code-quality gates

Add scripts/tests for:

- no broad exceptions;
- no unparenthesized multi-exception handlers;
- no silent fallback code;
- no forbidden raw model access in physical engine paths;
- no non-serializable decision payloads;
- no Python memory-address reprs in records;
- no generic dice labels;
- no UI mutation of engine state;
- strict import boundaries.

## 7. Legacy migration rule

No legacy file is copied wholesale.

Allowed migration path:

1. Name the invariant.
2. Write strict tests in CORE V2.
3. Port the smallest necessary algorithm or data transform.
4. Remove fallback behavior.
5. Add serialization/replay coverage.
6. Add static audit if the bug class is likely to recur.

## 8. First implementation milestone

Milestone A is complete only when these commands pass:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pyright
PATH="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:${PATH}" uv run pytest tests --ignore=tests/code_quality -n auto --dist=worksteal --cov=warhammer40k_core --cov-report=term-missing --cov-fail-under=67
uv run pytest tests/code_quality -q -n auto --dist=worksteal --no-cov @ci/quality_shards/prototype-comparison-deferred.args
uv run --no-sync python scripts/build_test_shards.py --check --shard-count 12
uv run lint-imports
uv run pre-commit run --all-files
```

and these invariants are enforced by tests:

- broad exceptions fail the gate;
- raw model access in physical modules fails the gate;
- dice rolls require labels;
- dice replay round-trips;
- event/decision serialization contains no memory-address reprs.

## Getting started

Use the [documentation index](docs/README.md) to find current play, integration,
source and contributor guidance. Completed plans and delivery journals remain
in Git history and PRs.


For faction coverage, start with the [faction support guides](docs/FACTION_SUPPORT.md).
They list current army rules, detachments and unit costs, separate historical
implementation evidence from fieldability/playability, and link the
[faction remediation roadmap](docs/FACTION_RULES_REMEDIATION_ROADMAP.md).

```bash
uv python install 3.14.5
uv sync --locked
uv run pytest tests/unit/test_phase10i_terrain_movement.py -q --no-cov
```

## Test commands

Pytest defaults are intentionally lightweight: narrow local and IDE runs do not start xdist
workers or collect coverage unless requested.

Fast local feedback names the affected test files explicitly, for example:

```bash
uv run pytest tests/unit/test_phase10i_terrain_movement.py -q --no-cov
uv run pytest tests/rules/section04/test_completion_boundaries.py -k attack_mortal_choices -q --no-cov
```

Architecture and source-shape audits run independently without behavioral coverage:

```bash
uv run pytest tests/code_quality -q -n auto --dist=worksteal --no-cov @ci/quality_shards/prototype-comparison-deferred.args
```

For final validation, run the behavioral suite once with coverage and the code-quality
suite above once without coverage. A second no-coverage behavioral run is unnecessary.
Focused subsets and `--lf` are for iteration, never replacements for this final gate:

```bash
PATH="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:${PATH}" \
  uv run pytest tests --ignore=tests/code_quality \
  -n auto --dist=worksteal \
  --cov=warhammer40k_core --cov-report=term-missing --cov-fail-under=67
```

The `PATH` prefix exposes the Node.js runtime bundled with Codex desktop to the executable
viewer-renderer regressions. It is safe when that directory is absent: an independently installed
`node` later on the existing `PATH` remains available. Keep this prefix on full-suite runs so those
tests do not fail only because the desktop shell omitted the bundled runtime.

CI shards this same behavioral suite, combines branch coverage, and applies the temporary 67%
gate after every shard succeeds. Full type checking and architecture checks also remain required
in CI and run on the `pre-push` pre-commit stage; commit-time hooks are limited to Ruff check and
format for a shorter edit/commit loop.

Each covered behavioral shard must finish successfully within 27 minutes
(1,620 seconds, inclusive) for approval. Timing alone does not terminate it then:
the supervisor permits execution through exactly 30 minutes and terminates the
workload process group only after 1,800 seconds. A passing workload that finishes
after 27 minutes still fails the gate while retaining its complete results.
Source-history validation, cold index construction, the isolated mirror, parallel
tests and their report finalization all run inside the same supervisor clock.
The 27-minute amendment took effect only after hosted run `43105204846` and its
concurrent local covered run finished under the former 18-minute limit. Their
original outcomes and all historical receipts remain unchanged.
Approval uses observed workload completion; later supervisor log replay and
diagnostic copying have a separately recorded elapsed time. Abnormal exit or
controller cancellation also cleans up the owned process group and fails approval.

The workflow's 32-minute outer safety guard leaves cleanup/reporting grace beyond
the controller's execution allowance; it is not an approval threshold. Reports
always include the supervisor's elapsed time, exit status and termination reason,
the covered-work log, available JUnit and timing journals. On termination or workload failure, available
coverage files/fragments are copied under reports/partial-coverage as diagnostics;
they are not promoted to complete coverage. Report uploads include hidden coverage
files. Missing complete coverage and any late/failed shard keep the combined gate
failed. No complete result is fabricated for a terminated process.

The isolated mirror's existing 120-second bound, separate 180-second performance
command, 600-second quality limits, twelve shards, and 67% branch floor remain
unchanged. Record actual observed completion times separately from configured
limits. Historical fifteen-minute timeout receipts remain historical failures;
their configured limit is not an unobserved test completion duration.

The current owner-approved coverage floor is 67%; later coverage work must restore 85%. The full
warhammer40k_core package and branch metric remain unchanged, with no added coverage
omissions or exclusions. This policy change does not claim either threshold has passed;
all required tests and other gates must still succeed. See the
[active review policy](docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md).

The twelve behavioral manifests in `ci/test_shards/` currently use an explicitly
reviewed derived assignment, admitted by `current-runtime-compatibility.json`.
The strict historical allocator remains available when that descriptor is absent:
it seeds the isolated mirror, then uses largest selectors and improving moves.
The
source-bound S25 module retains its twenty exact cases; canonical coverage
preflight retains its twelve-case partition. Two finite step5g modules add source-bound
partitions of 32 and 30 exact cases. The bounded mirror setup case is a separate
selector; its file selector denotes the remaining cases. CI always deselects that
node from parallel work and runs it once on its owning shard. All other files remain
intact. The resulting 505 selectors select exactly 6,300 cases, including the eighteen terrain-preparation and immutable-geometry cache regressions. The required guards verify the exact selected inventory and partition.
Verify that every selected file or declared case appears exactly once:

```bash
uv run --no-sync python scripts/build_test_shards.py --check --shard-count 12
```

The compatibility descriptor pins the original scheduling snapshot at
`008be8a8cb0b50b232fe022452762b3906489b49`, a complete current covered local baseline,
and `current-derived-assignment.json`. Current validators authenticate every
dispatch-contributing producer and tested checkout against Git, then validate the
original data, runtime, test bytes, cohorts and reserve in a temporary historical
snapshot. Historical Python is never executed and historical receipts are unchanged.
`scripts/fetch_scheduling_sources.py` supplies only the exact declared Git objects;
missing objects remain errors, including after squash merges and branch deletion.

The current baseline must bind unchanged historical gameplay test sources, exactly
the eighteen reviewed additions, current runtime and profile/file/case costs,
32 parallel workers plus the isolated one-worker mirror, 67% full-package branch
coverage and an approved 1,620/1,800-second supervisor receipt. It is local evidence,
not a hosted observation. Dispatch takes each retained case's maximum of its fresh
baseline and historical passed triples; additions use only their fresh baseline.
The assignment discloses every relocated selector. Generator, checker and live
dispatch independently verify exact membership, finite partitions, fixed module
alone on shard 5, pinned module on 4, mirror on 2 and cold role on 1. They recompute
actual four-worker projections and preserve the historical/stress/latest planning
ceilings of 1,076/1,054/1,050 seconds. Original historical scores and partial unknowns
remain separate; additions have no historical observations. No offline allocation
search runs in CI, and planning estimates never qualify hosted timing. The complete
current local covered run passed in 1,146.71 seconds with 67.47% coverage; fresh
hosted CI and its unchanged approval limits remain required.

Download the `behavior-report-*` artifacts from each chosen complete behavioral
run into a separate directory outside the checkout, then regenerate (repeat both
options for additional runs). Each profile must contain every selected case with
passed setup, call and teardown, including the isolated mirror. A complete
all-passed behavioral JUnit profile may supply scheduling measurements even when
the enclosing CI run failed its timing approval; its source description must
retain that failed outcome, run/attempt, tested checkout, source head, runtime,
host and worker topology. It is not an approved CI run or passing coverage gate.
Missing, failed, skipped or incomplete cases remain inadmissible. Authenticate
artifact bytes and attempts independently before use; worker JSON alone does not
identify the attempt. Downloaded profiles are supplied inputs, not generated source:

```bash
uv run --no-sync python scripts/build_test_shards.py \
  --junit ../behavior-reports/run-one \
  --profile-source "RUN_URL; commit SHA; ubuntu-latest; 4 workers per shard" \
  --junit ../behavior-reports/run-two \
  --profile-source "RUN_URL; commit SHA; ubuntu-latest; 4 workers per shard" \
  --shard-count 12
```

The initial measurements are the complete covered hosted runs
[40872329113](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/40872329113)
and [40874478610](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/40874478610),
each covering all 4,886 cases. Historical S25 estimates took each case's larger
recorded cost, also including fully passed setup/call/teardown observations from
[40888978899](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/40888978899).
That later run failed; it is not a passing profile. Its 277 failed or unreported
cases retained authentic older measurements. The exact derivation and timing hashes
are recorded in `ci/test_shards/case-partitions.json` under `evidence.weight_refresh`.

Within each worker's initial duration-balanced bucket, cases from the same module
run together so pytest can reuse module-scoped fixtures. Grouping preserves each
bucket's worker membership and capacity. Modules start in descending order of their longest
case, with descending case costs inside each module and stable node identity
breaking ties. Later work stealing can still split a module group. This scheduling
change preserves every case and does not certify the eighteen-minute approval goal.

Session startup, source-index setup, reporting and runner queues are assessed
separately. Weight totals are planning inputs, not job wall times or proof of the
eighteen-minute approval goal. Existing observation-based estimates do not
relax the complete-profile validation below.

Cold selected-source construction stays inside the same supervised covered workload and
overlaps pytest startup and collection. The controller admits no test execution
until construction succeeds with a completion record bound to the exact input key
and index path. Failure, malformed completion and deadline expiry stop dispatch.
Shard 1 deliberately bypasses source-index cache restore/save on PRs and main so
every run verifies this cold path. Other shards retain exact-key reuse and the
normal source/partition validation; a warm-cache retry is not cold qualification.
In the historical automatic allocation path, the generator swaps the eligible bucket with the lowest
whole-second phase-plus-role planning score into shard 1, breaking ties by its
original bucket number. The explicitly frozen shard is ineligible for this swap. This final
permutation preserves every bucket's selectors and all measured case/selector
weights, while avoiding assigning the cold role by largest-first insertion order.
The execution metadata records this policy. Startup and report finalization are
measured separately; observed role residuals supply conditional planning reserves.
The model does not guarantee a hosted wall time. Empty buckets and committed manifests fail validation, because
an empty pytest selector list would run the default suite.

A complete local JUnit profile is also accepted, either one XML or one directory
containing the isolated mirror and remaining-suite XMLs from the same covered run.
Label its host, worker counts and concurrent validation accurately; do not mix
local and hosted-runner timings in one representative CI profile. Local timing
weights do not establish hosted cost accuracy or a speedup. For a representative
CI-only median baseline, use only complete hosted profiles with the actual
four-worker remainder and isolated one-worker mirror. Preserve replaced local
profiles, their raw JUnit bytes, hashes, source labels and measurements as
historical evidence outside the checkout and retain their Git revision; do not
mix local and hosted measurements or rescale either. A baseline replacement does
not remove historical calibration observations or relax fresh CI qualification.
A separate `hosted-calibration.json` may supply historical planning observations.
It does not replace or alter `profiles`, `case_seconds`, measured file totals, or
complete-profile admission. The generator and four-worker dispatch both use
`max(complete baseline cost, largest admitted hosted setup+call+teardown total)`.
Finite S25 selectors use these same derived node costs for assignment; their old
ratio evidence remains historical and is not applied again to calibrated costs.
Ordinary selector costs sum their exact nodes; the isolated mirror retains its
separate selector and one-worker execution. Summation is canonical and stable
under input dictionary permutations.

The sidecar records every admitted sample's separate setup/call/teardown values,
raw worker SHA-256, artifact ID, run/attempt, enclosing outcome, actual tested
checkout, source head and that source head's recorded engine fingerprint. A failed enclosing run
stays failed. `scripts.hosted_timing_calibration.build_calibration` accepts raw
worker files paired with independently verified artifact/API metadata: worker
JSON itself does not identify the attempt. It checks recorded build fingerprints
and unchanged test-module bytes against each historical source head. Current
module hashes and exact case inventory are separate compatibility checks, not
claims that all historical runtime/helper/context inputs equal current ones.

Only complete passed triples from one worker report are admitted. Every raw node,
including failed/incomplete rows, must belong to that worker's collected baseline
inventory. Duplicate phases, completed cases within an artifact/attempt, worker
invocations, contradictory artifact metadata and count drift fail closed. The
supported invocation identities distinguish the isolated one-worker lane from the
four-worker remainder; repeated observations across artifacts/attempts remain
separate samples before taking the maximum. Unobserved cases are listed explicitly
and retain their complete baseline measurement. Changed/removed/renamed cases or
changed test-module bytes require explicit sidecar regeneration, and behavioral
inventory changes still require a fresh complete all-passed behavioral baseline profile.

The preceding calibration retained 284 compatible source-bound raw worker receipts
and 34,836 passed three-phase samples covering 6,115 cases. All sixty
source collected inventories were authenticated before filtering by exact counts and hashes;
the original 679-node inventory also matches the three independently retrieved,
SHA-authenticated workers in artifacts 13649430067 and 13648072478. The diagonal
generator update changed two behavioral modules, excluding the eight PR656
worker receipts whose collected inventories include them and all 1,139 samples
from those receipts. Every surviving outcome, source identity and phase tuple
is unchanged. At that point, the 139 cases in those two modules had no compatible
retained hosted observation and used the complete local baseline below. No unknown
inventory was guessed and no timing sample was invented. Original receipts and
their outcomes remain in Git history and source artifacts.

All 52 original collected inventories were authenticated by their exact counts
and hashes. Fifty-one reconstruct completely from retained observation membership;
the remaining 679-node inventory was recovered from three SHA-authenticated raw
workers in original artifacts 13649430067 and 13648072478. No unresolved inventory
was guessed or conservatively discarded. The original 263 receipts and 32,637
samples, including the 49 PR651 attempt-1 workers, remain in Git history and their
original artifacts. The earlier split-contract update's 21 excluded incompatible
receipts are not reinstated. No partial progress journal is a calibration receipt.

Retained sources include successful historical run
[42549486854](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42549486854),
failed attempts 1 and 2 of
[42556245215](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42556245215)
and [42602087197](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42602087197),
successful covered PR run
[42641115451](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42641115451),
and completed original workers from attempt 1 of failed main run
[42644169069](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42644169069).
Failed enclosing attempts retain their failed outcomes. Independently downloaded
artifact/API metadata and exact raw hashes rebind every retained receipt; original
source heads and recorded engine fingerprints stay unchanged. Controller and
replacement receipts and inherited successful-job copies remain excluded.

The appended source is attempt 1 of failed PR651 run
[42722507586](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42722507586).
Its 49 completed workers recorded all 6,232 passed three-phase samples. Shard 3
completed all 557 tests but took 1,141.580 seconds, exceeding the 1,080-second
approval limit; it was not terminated. The run and combined coverage approval
remain failed. Independent run/PR/merge/artifact APIs bind attempt 1, source head
`1b50ad339c49231d16b1c07dd9c6165745ef644c`, tested merge checkout `15f6792e5e1a369829825f72d697fbfb197d336f`
and the unchanged recorded runtime. The merge and source head have identical
trees. The unchanged maximum formula incorporates these observations for planning;
it neither promotes this failed run to a passing baseline nor predicts a passing
rerun. These historical receipt and observation tuples remain unchanged in the
subsequent canonical-fixture inventory update.

An earlier appended source is attempt 1 of failed PR656 run
[42810498143](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42810498143).
All twelve behavioral workloads completed successfully, including shard 7's 332
passed tests in 1,178.50 pytest seconds. Its supervisor measured 1,221.417 seconds,
exceeding the unchanged 1,080-second approval limit; it was not terminated and the
run remains failed. Independent run/PR/merge/job/artifact APIs and archive digests
bind its 49 completed workers to source head
`6f55680b0767eb901eae34cd807a5960a47a10af`, tested merge checkout
`d99aa9ce1e5d186f05dd6ac8ef999313237c419b`, and the recorded runtime fingerprint.
The source and merge trees matched, and every collected test module matched the
then-current bytes. The diagonal-generator update excludes the incompatible
receipts as described above. The admitted samples cover the exact 6,254-case baseline once.

The historical PR656 run exposed hosted cost variance absent from its local
baseline: the complete canonical-coverage case took 1,080.002 seconds across its
three phases, compared with 485.673 baseline seconds. The maximum-cost formula
and balancing placed its whole eight-case module alone on shard 3. That shard's
modeled lower bound was 1,080.002 seconds before startup and finalization; the
other eleven modeled lower bounds were 993.692-993.708 seconds. Those are historical
PR656 planning values. The PR657 manifests used the complete diagonal-generator
profile below and the compatible receipts described above. Timing budgets, test
selection and the scheduling algorithm remain unchanged. Reassignment cannot
shorten an individual test, and planning metadata does not establish compliance
with the eighteen-minute limit. A fresh hosted run is required; an over-limit
result remains a blocker.

The preceding complete baseline is the successful local 6,254-case covered diagonal-generator
qualification: Python 3.14.5 under WSL, one isolated mirror worker followed by
32 remainder workers, using a fresh checkout-bound source index. Static/type/
contract checks run separately; no competing validation workers ran during
the complete attempt. The tested working source is based on
`a085db23dbef50237398b226cd24328d337d0e3b`, with runtime fingerprint
`8996a426d3399cdd20243a6083d426d7627ac3ef5afd4597710ef16ccab94d6a`.
Complete successful JUnit measurements supply every current case weight, including
both changed modules. The prior three-order, second-cardinal-ring and five-offset
profiles remain historical. Local and hosted measurements are not mixed into one
representative baseline. The unchanged maximum formula retains every compatible
slower hosted observation; excluded receipts do not become current measurements.
Local timings do not establish hosted cost accuracy or a speedup; fresh hosted
qualification remains required.

The preservation-admission baseline is the successful local 6,257-case covered
preservation-admission qualification on Python 3.14.5 under WSL: one isolated
mirror worker followed by 32 remainder workers and a fresh checkout-bound source
index, without competing validation workers. Its exact base is
`bbba63a57f67b39b2c101d2b07841fb728bc23ef` and its runtime fingerprint is
`df5981b2761ed40b8a87daf2adb3ec56fc0527ad66eaf7470b76697b7ad36dad`.
All 284 compatible hosted receipts and 34,836 samples remain unchanged; no
previously collected test module changed. The three new preservation cases use
their fresh complete-profile measurements, bringing baseline-only membership to
142 cases. The unchanged maximum formula preserves every compatible slower
hosted observation. Local timing is planning evidence, not hosted approval or a
speedup; the twelve manifests still require a fresh passing hosted run.

The preceding complete JUnit baseline records 6,261 passed behavioral tests
for witnessed Normal Move on Python 3.14.5 under WSL: one isolated
mirror worker followed by 32 worksteal workers, without competing validation
workers. Its fresh checkout-bound source index was prepared separately. The
whole-suite controller completed in 1,086.756 seconds, exceeding the unchanged
1,080-second approval limit; it was not terminated. That local timing approval
remains failed. Complete passing-test JUnit data supplies planning weights only.
Its exact base is `e3620316d36ebd5a2ac910fee8d2d429c2d5ae34` and runtime fingerprint
is `785ca6f64b746d062d23eca25a55ca0b851f0331d8c392c07f4b1a63ffd9c5e7`.
Before the hosted append below, all 284 compatible receipts and 34,836 historical
samples remained unchanged. No existing behavioral test module changed; the four
new cases used their complete-profile measurements, bringing baseline-only
membership to 146 at that point.
The twelve manifests retain the same maximum-cost formula and timing limits.
These local scheduling observations neither explain the earlier hosted timing
variability nor establish a performance repair, scenario-cost qualification or
hosted approval. Fresh complete hosted qualification remains required.

The PR659 calibration appends exactly 49 complete original worker receipts and
6,261 passed three-phase samples from attempt 1 of failed PR659 run
[42898953334](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42898953334).
That update retained 333 receipts and 41,097 samples covering all 6,261 then-current cases,
with zero baseline-only cases at that point. Every prior report and observation tuple remains
unchanged, including its original outcome and source identity. The existing
complete local JUnit profile, report hashes and case weights remain the baseline;
the failed hosted run supplies additional scheduling observations and does not
replace that baseline or change its failed local timing approval.

Independent run, PR, tested-merge and artifact API metadata plus all twelve
original artifact ZIP digests bind the 49 original worker receipts to attempt 1,
source head `7e00f43139ab3328996fbd93d3b4dafbbbaa9509` and tested merge
`7d88625203e2b7b5a458868b449791483ed305b8`. Both commits have tree
`cf0b5381df07663e9fb2fdbeb0e902de9a82bce5`; the recorded runtime remains
`785ca6f64b746d062d23eca25a55ca0b851f0331d8c392c07f4b1a63ffd9c5e7`.
All 6,261 tests completed with zero failures, errors or skips. Shard 5 completed
295 passing tests in 1,152.625414316 supervisor seconds, and shard 8 completed
405 passing tests in 1,162.622728803 supervisor seconds. Both exceeded the unchanged
1,080-second approval limit without termination. The run and combined coverage
approval remain failed; no failed enclosing outcome is promoted to a pass.

The PR659 maximum-cost formula and grouping placed canonical coverage on
shard 4, the Normal Move controls on shard 6, and the entire
`test_runner_accounting.py` module alone on shard 9. The execution model gives
shard 9 a test-work wall-time lower bound of 1,052.839 seconds and the other eleven
shards lower bounds of 998.592-998.609 seconds. These exclude startup and
finalization and are neither predictions nor approval evidence. The largest
observed individual three-phase cost is the canonical coverage case at
899.082576920 seconds; Normal Move restore/closed-receipt evidence took
584.844613345 seconds including setup. No observed individual case exceeds
1,080 seconds, but reassignment cannot guarantee a shard finishes within that
limit. Host variance remains unexplained; this metadata change establishes no
performance repair or scenario-cost qualification. Test membership, algorithms,
worker counts, timing limits and coverage requirements are unchanged. Fresh
complete hosted qualification remains required.

The historical paired-followthrough baseline contains 6,264 passed cases
measured on Python 3.14.5 under WSL Ubuntu. This retained planning profile is not
the current test inventory or a current-head qualification. Its exact base is
`efb3172c4ce1b3a912c3f6fc2c26ebaa465ad9c4` and runtime fingerprint is
`3174e16c152ba1febdf0e26360df49e75d1951fbc616eced69546bbb598a5f2e`.
Source-history validation, cold index construction, one isolated mirror worker,
32 worksteal remainder workers and finalization share one supervisor clock.
All tests passed with 67.42% full-package branch coverage, but the whole local
workload took 1,156.755788438 seconds and failed the unchanged 1,080-second timing
approval without termination. Its successful test JUnit data supplies planning
weights; its failed timing approval remains failed.

A reviewed local-only stable sort started the existing eight-case canonical
module first without changing unique node membership; its archived plugin hash
is `18eda01828a226ae2ffed8851fe983af6c268b2167496743cd130bebb69c37f4`.
Contract/conformance checks overlapped setup/mirror, and diagnostic archiving
overlapped part of the remainder. These local observations are not a serial
performance comparison or hosted approval. All 333 historical receipts and 41,097
observation tuples remain unchanged. Only inventory/source binding expands for
the new test module; its three new cases use complete-profile measurements and
remain baseline-only. The twelve manifests are regenerated from that exact full
profile with the existing maximum-cost formula and unchanged limits. Fresh
successful hosted qualification is required for every shard.

The PR660 calibration now appends exactly 49 original worker receipts and 6,264
passed three-phase samples from attempt 1 of failed hosted run
[42928611158](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42928611158).
Independent run/PR/job/artifact APIs and original ZIP digests bind source head
`6a83d934e2f792d5e84b60517e4035dd4d7f1bec`, tested merge checkout
`9ebcd3885efd3a4ea37a78472b324c8823e6373b`, their identical tree, and the recorded
runtime fingerprint. Every extracted worker matches its authenticated archive.
All original 333 receipts and 41,097 observation tuples retain their identities,
values and outcomes. Totals are now 382 receipts and 47,361 samples covering all
6,264 cases, with no baseline-only cases. The complete corrected local baseline,
its source label, JUnit hashes, file totals and case measurements remain unchanged;
the failed hosted run is additional historical planning evidence only.

All 6,264 hosted cases passed without errors or skips. Shard 10 completed its
398 tests in 1,124.426420638 supervisor seconds and failed the unchanged
1,080-second approval limit without termination; shard 9 passed in
1,079.584697890 seconds. The run and combined coverage approval remain failed.
Shard 10's isolated mirror contributed 225.044133079 three-phase seconds before
the parallel remainder. Its longest individual remainder case was preservation
receipt persistence/replay at 433.886318618 seconds on worker gw0. Worker gw3
finished last at 750.782377348 elapsed seconds: its first case was the S25
unused-wound-player-a control (403.703151489 three-phase seconds), followed by
preservation, source-description and canonical-deployment controls. The largest
individual case across the run was complete canonical coverage on shard 1 at
854.437291701 three-phase seconds. These observations distinguish serial work,
case cost and worker order; they do not establish the cause of hosted variance.

The unchanged maximum-cost formula and grouping regenerate all twelve manifests.
The isolated mirror moves to shard 1, canonical coverage to shard 4, Normal Move
to shard 6, paired followthrough to shard 7 and preservation to shard 9. Modeled
test-work wall-time lower bounds are 1,043.481-1,043.496 seconds across the twelve
shards, excluding startup and finalization. These bounds do not predict approval,
qualify scenario costs or demonstrate a performance improvement. Tests, worker
counts, algorithms, coverage and timing limits remain unchanged. Fresh successful
hosted qualification remains required for every shard.

The subsequent PR660 run
[42932156443](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42932156443)
again completed all 6,264 tests, but shard 4 took 1,414.340765547 supervisor
seconds and failed approval without termination. Its complete canonical-coverage
case ran first on its worker and took 1,300.468117872 three-phase seconds by
itself; calibrated dispatch was active. The other eleven shards passed timing.
This failure is retained separately and is not silently promoted into passing
qualification or substituted for the complete local baseline.

The bounded loader repair derives totals from receipt rows before reproduction,
rejecting an internally contradictory total without repeating the engine
campaign. Every internally consistent receipt still receives fresh measurement
and exact comparison. The existing complete test is unchanged; a separate real
coordinated-tampering control preserves that boundary. Matched actual-base
[operation evidence](docs/performance/current/canonical-coverage-preflight.json)
records valid reload and inconsistent-total rejection separately. One serial
sample per arm cannot establish variance, hosted approval or full-game costs.
All existing 382 historical receipts and 47,361 phase observations retain their
original identities, values and outcomes; no historical timing limit changes.

Fixture setup observations are worker/order dependent; taking maxima and regrouping
does not establish new fixture multiplicity, hosted wall time or the eighteen-minute
approval goal. Existing module grouping, twelve shards, four-worker dispatch, the cold
shard-1 role, isolated mirror limit and full coverage requirements remain unchanged.
Fresh complete correctness/coverage qualification remains mandatory. `--check`
re-derives every planning cost/selector and the sidecar digest; worker dispatch
rejects a missing or altered declared sidecar. Run the normal generator command
above with this sidecar in the output directory to reproduce the manifests.

The earlier local baseline contained 6,278 passed cases from the opposing-shooter
qualification on Python 3.14.5 under WSL Ubuntu, against exact base
`5639ccce458e53e154b1f578548ec7f20dfdec18` and runtime fingerprint
`575d1f47b62970089d53ec533482c75cbbd7a06bfe7015fe09d99526dcba781c`.
One isolated mirror worker precedes 32 worksteal remainder workers. A local-only
collection-order hook starts the known long canonical case and the new campaign
early without changing membership or assertions; CI retains its normal calibrated
four-worker dispatch. The complete local workload passed all tests with 67.46%
full-package coverage with branch measurement enabled, but took 1,158.728893934
supervisor seconds and failed the unchanged 1,080-second approval limit without
termination. That failed timing result remains failed. Complete JUnit measurements
supply every current case weight; the new two-case module is included in the
twelve regenerated manifests. All 382 historical receipts and 47,361 observation
tuples retain their exact identities, values and outcomes. At this baseline
construction, fourteen cases had no compatible hosted observation and used
their complete-baseline measurements.
This profile is local planning evidence, not hosted timing approval, tactical
usefulness, scenario-cost qualification or full-game performance.

The subsequent PR661 calibration appends exactly 49 authenticated worker receipts
and 6,278 passed three-phase observations from attempt 1 of failed hosted run
[42965700288](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42965700288).
API-bound archive digests and byte comparisons bind source head
`7ce2d3c85f138e0575fd78386bbf0b4ef37a4783`, tested merge checkout
`24a94682b96a0fe8c85f63a5791c08136b3cc903`, their identical tree and the recorded
runtime fingerprint. All original 382 receipts and 47,361 observation tuples
retain their exact values, indices, identities and outcomes. Totals after that append were 431
receipts and 53,639 observations covering all 6,278 cases, with no baseline-only
cases. The complete 6,278-case local baseline, source label, JUnit hashes, file
totals and case measurements remain unchanged.

Every hosted case passed without errors or skips. Shard 4 took
1,220.530580016 supervisor seconds and shard 12 took 1,186.5076281 seconds;
both exceeded the unchanged 1,080-second approval limit, exited successfully
without termination and still failed approval. The run and combined coverage
gate remain failed. Other shards passed timing. These receipts are historical
planning evidence, not a passing qualification or a timing-limit amendment.

All four workers were busy through the late shards' final workload interval.
Shard 4's three canonical-prefix cases took 538.586, 465.533 and 465.781
three-phase seconds versus prior maximum weights of 356.344, 304.077 and
306.313. Complete canonical coverage took 951.861 seconds versus 899.083.
On shard 12, the new attack witness took 661.544 seconds versus its local-only
319.266 weight; the two followthrough cases took 582.007 and 313.674 seconds
versus prior weights of 386.433 and 162.136. These are observed weight gaps;
they do not establish a hardware cause or a runtime regression.

The existing maximum-cost formula regenerates all twelve manifests and the
same calibrated four-worker dispatch. Canonical coverage moves from shard 4 to
shard 3; followthrough and the opposing attack remain on shard 12 with a revised
surrounding inventory. Reusing the observed case costs gives illustrative
test-work lower bounds of 994.386 and 895.574 seconds for those two new groups.
Those bounds exclude source/history setup, collection and finalization and
assume unchanged case costs across different workers and hosts. They cannot
predict approval or certify a speedup. No test, scheduler algorithm, runtime,
worker count, coverage floor or timing limit changes. Fresh complete hosted
qualification remains required for every shard.

A further PR661 calibration appends 49 authenticated worker receipts and 6,278
passed three-phase observations from attempt 1 of failed hosted run
[42969947321](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/42969947321).
API-bound archive digests and raw-worker byte comparisons bind source head
`566b3cd32fb43a0e96efe878fb0b58482d8d9ea9` and tested merge checkout
`a9d1b923ca10a1e47ef1fbc0c1ecb60897106ae5` to the identical tree
`e729b83c874c4be04cbca8026ea256144d3a6b29` and recorded runtime fingerprint.
The prior 431 receipts and 53,639 observation tuples remain exact prefixes,
with their indices, identities, measurements and outcomes unchanged. Current
totals are 480 receipts and 59,917 observations covering all 6,278 cases, with
zero baseline-only cases. The complete local 6,278-case baseline, source label,
JUnit hashes, file totals and case measurements remain unchanged.

All 6,278 hosted cases passed across 49 workers. Shard 6 took 1,090.60351343
supervisor seconds and shard 8 took 1,085.253981572 seconds. Both exited zero
without termination or remaining descendants but exceeded the unchanged
1,080-second approval limit; the run and combined coverage gate remain failed.
The other ten behavioral shards passed timing. Both failed runs remain historical
evidence and are not relabeled as passing qualifications.

Shard 6's normal-move restore and distance-rejection cases took 677.305 and
370.138 three-phase seconds versus prior maximum weights of 584.845 and
293.387. Shard 8's canonical-preflight case took 965.874 seconds versus
828.223. Comparable S25 cases stayed near prior observations; the concentrated
gaps do not establish a hardware cause or engine regression. Worker progress
shows approximately 93 and 96 seconds of wrapper/startup/finalization time,
excluding worker collection and dispatch.

The unchanged formula and generator regenerate all twelve manifests.
Normal-move stays on shard 6 with a different surrounding inventory; canonical
preflight moves to shard 10. Its indivisible 965.874-second observed cost is
the counterfactual global test-work lower bound. An illustrative 100-second
wrapper allowance leaves only 14.126 seconds before approval, excluding any
unaccounted collection, dispatch or changed context costs. Qualification remains
tight and unproven. No production/test code, scheduler, worker count, coverage
floor or timing limit changes; fresh complete hosted qualification is required.

Every supplied complete baseline JUnit run must cover the current behavioral file inventory. Missing files,
duplicate cases, failed/skipped cases, invalid durations, and truncated suite counts
are rejected. Outside the explicit initial migration seed above, new test files
require a fresh complete profile; timings are never filled with zero. `durations.json` preserves report SHA-256 hashes and run descriptions.
Historical profiles measure their recorded case inventory; added, renamed or
changed cases within an existing file require a refreshed complete all-passed
behavioral profile to provide their exact case weights. Preserve previous measurements in
Git history and retained source artifacts; never invent missing weights or
substitute file averages for CI dispatch.

`allocation-cohorts.json` selects nine complete effective hosted cohorts by their
original worker-report SHA-256 identities. The allocator scores the actual four
initial worksteal chunks for every cohort. Stable node-identity ties make offline
chunks match live dispatch independently of collection order. The isolated mirror
is charged sequentially before the parallel remainder.

For each coherent cohort, artifact-bound supervisor receipts and original worker
phase sums derive the observed maximum phase-to-supervisor residual separately
for parallel-only and isolated-mirror shards. Planning adds the matching role's
residual to that same cohort's phase path, takes the largest coherent estimate,
and rounds it upward to a whole second. It never mixes one cohort's largest phase
path with another's residual. This replaces the earlier fixed 50-second extra
controller allowance. Raw phase costs and reported worker paths remain unchanged.

Whole-selector moves strictly improve the descending rounded planning scores.
The search continues past an indivisible or non-improving worst bucket and may
use space on a higher-scored bucket when the complete objective improves.
Whole-second planning can regress unrounded estimates within a rounded bucket;
raw values remain separate. The earlier eighteen-move sensitivity and its 4.013 /
37.826-second projected margins remain historical diagnostics, not qualification.

For directly declared non-parametrized module fixtures, the conditional setup
estimate is the cohort's largest observed worker setup sum for that fixture group,
charged once per new worker group. Calls and teardown remain their recorded costs.
This accounts for fixture reuse without treating historical cold setup as permanently
owned by its first test. Function-scoped setup can increase with relocated case counts;
overlapping groups can double-charge dependencies. Observed phase-to-supervisor role
residuals are included; unobserved overhead, work stealing and future host variance
are not bounded by this estimate. It is not an upper bound or
timing qualification. Every actual covered shard must pass within the current
1,620-second inclusive approval limit.

The three original complete JUnit sources, hashes and medians remain unchanged.
The calibration retains its original 627 reports and 78,763 observation tuples as
exact prefixes. The subsequent 745 reports / 94,259 observations also remain exact
prefixes. The next 794 reports / 100,541 observations remain exact prefixes too;
another 49 reports / 6,282 observations give totals of 843 / 106,823.
The earlier complete cohort is run `43038116912`, attempt 1, source PR head
`0d281c269759b8a74c915bae3a59fa8e211f9fa6`, tested merge checkout
`d03fb42db79ad431a6fb15801ce6948584bb16fc`. All 6,282 cases passed, but the
enclosing run failed the unchanged timing gate on shards 2, 8 and 11. That failure
remains recorded. The following complete cohort is run `43047121648`, attempt 1,
source PR head `ae751d09ad28b2486d60104e0c753b2d0ef0731b`, tested merge checkout
`831fe9377faaf90b1e3b4787820947c78f19c2a7`. Its 6,282 cases also passed, while
shard 11 exceeded the timing limit at 1,127.106 seconds; that enclosing failure
remains recorded too. Cohorts include failed enclosing attempts, and inherited successful jobs
retain their original producer identities; neither becomes a new passing observation.
The latest complete cohort is run `43081418293`, attempt 1, source head
`b9b1c97a6a2da6fca624c7f30c471d6cfab56320`, tested checkout
`adabf49b8844b26a49c1e87f22c736f69f10f13f`. Its 49 workers completed all 6,282
cases, but shards 2 and 10 exceeded approval at 1,183.686 and 1,090.457 seconds.
The enclosing failure remains recorded. Appending these 49 reports and 6,282
observations gives 892 reports / 113,105 observations, preserving the entire
843 / 106,823 prefix. The unchanged max-with-baseline formula increases 425
case weights; this changes initial dispatch membership without changing raw times.
`--check` regenerates the allocation, and dispatch rejects a missing or changed
declared cohort index. The all-history maximum case weights still drive dispatch;
coherent phases and observed role residuals drive allocation, with their distinct limitations recorded.

The original `allocation-scope.json` and `scoped-worker-evidence.json` remain
byte-identical: 45 completed workers and 6,014 passed cases from failed run
`43059076830`, attempt 1, source head `7963b663dd8fcfd0906f8fb3de26c67b0ca74812`,
tested checkout `9a141902bde5b428c041bf82cea0e5ffb2a47313`. That original scope
excluded all 268 cases of shard 4. The separate versioned `scoped-worker-extension.json`
retains four final worker reports, including replacement `gw4`, with 267 unique
passed setup/call/teardown triples. ZIP/member hashes, producer windows, exact
tested source-tree identity and identical collected inventories bind those reports.
The failed shard's exit code remains 1. Its lost `vehicle-scout-deep` case remains
unknown; no progress journal becomes a completed timing observation and no failed-job
role residual is derived. The combined raw scope has 6,281 known cases and one
unknown. Its full score remains null wherever that unknown case is selected.

`allocation-stress.json` separately reserves 465.533262819 seconds for the unknown
case using the maximum of its other complete-cohort phase totals and original
dispatch cost. This is a derived stress assumption, never a measured case or a
complete cohort. Known-only phase contributions retain full dispatch chunks while
filtering missing observations. Role residuals remain derived solely from the
original eleven complete workloads. No recognized shared module-fixture group is
added by the extension, so the original known-scope setup maxima stay unchanged.

The whole eight-case canonical deployment coverage file stays pinned on shard 4,
which can also receive known work. The whole four-case matched attack module runs
alone on shard 5 with the ordinary four workers. The other 260 newly evidenced
cases can move. Mirror-first construction uses updated measured dispatch maxima
and serial execution weights, then descending selectors and strict whole-second
improving moves. Planning offsets of 0 for the eight earlier complete cohorts,
22 for derived stress, and 26 for the latest complete cohort align ceilings of
1,076 / 1,054 / 1,050 seconds. Feasible groups remain feasible; initially infeasible
groups may only improve or retain their guarded score. Refinement stops when all
bounds fit. Cold normalization excludes pinned/fixed/mirror roles, keeping parallel
shard 1 and the separate mirror on shard 2. These finite planning ceilings retain
their original 18-minute approval basis; the accepted allocation is unchanged.
The owner subsequently raised actual approval to 1,620 seconds inclusive, while
termination remains strictly above 1,800 seconds.

The existing S25 and preflight partition files and every baseline case median remain
unchanged. The two step5g partitions preserve raw Git source bytes, including their
CRLF lines, and original baseline file totals of 645.801 and 504.883 seconds through
derived ratios. Their 62 exact collected nodes add flexibility without changing
tests or observations. All 504 selectors still cover exactly 6,282 cases once.

The chosen conditional peaks are 1,075.779 seconds across the earlier eight cohorts,
1,052.864 seconds for derived stress, and 1,049.687 seconds for the latest complete
cohort: margins of 4.221 / 27.136 / 30.313 seconds to the former 1,080-second
approval limit used during allocation review. The latest
phase paths with the largest retained matching-role residual reach 1,058.166 seconds;
another 20 seconds reaches 1,078.166, while 50 seconds would exceed that former
limit. These retained sensitivities are not new timing observations. Increasing only
the unknown-case reserve by 20 or 50 seconds leaves the overall derived stress peak
unchanged. These conditional estimates and preserved per-shard regressions do not
certify robust future headroom or passing CI. All real exact-head gates and independent
reviews remain required; the earlier worker-loss cause is still unknown.

The inner covered-workload shell also captures separate before/after resource
JSON files. Linux host OOM counters and available cgroup-v2 events/current/peak
readings are read without resetting counters or changing worker behavior. Host
counters may include unrelated work; cgroup peaks cover their lifetime, and missing
or unsupported readings are explicit. Worker exit codes remain unknown without a
public nonblocking source. These observations can help diagnose a recurrence but
cannot identify a worker's death cause by themselves. Diagnostic capture failure
preserves the workload's original exit status and does not change supervisor clocks,
cleanup, approval or execution limits.

Four-worker behavioral CI uses `BEHAVIORAL_DISPATCH_PROFILE` to distribute measured
case costs across xdist's initial worker chunks after deselection. Complete case
weights come from the same successful JUnit profiles as the file totals; CI does
not substitute file averages for missing case costs. Shard assignment separately
accounts for the mirror's serial execution, retaining measured times unchanged
and recording the four-worker execution model. Missing, negative, nonfinite or
boolean weights fail closed; measurements rounded to zero remain valid. Finite S25 case validation,
the complete selected inventory and the eighteen-minute approval deadline remain mandatory.

Behavioral lanes log keyed cold-index start/completion and elapsed construction time.
A case exceeding three minutes emits thread stacks and continues under the existing
thirty-minute execution allowance.

Both Python CI lanes upload JUnit, slowest-test output, and per-worker JSON timing
artifacts containing collection node IDs, collection time, setup/call/teardown times,
outcomes, Python/platform/CPU/memory metadata, and commit/run IDs. Enable the same
local evidence with `TEST_TIMING_DIR=reports/timing`. These artifacts distinguish
collection overhead and long individual cases from aggregate file costs.

Behavioral CI additionally sets `TEST_TIMING_PROGRESS=1` with `TEST_TIMING_DIR`
to append a separate `<worker>.progress.jsonl` diagnostic journal. The flag must
be exactly `1` with a nonempty timing directory; without it the existing behavior
is unchanged. Only xdist workers journal execution. A header records worker/PID,
run/attempt/checkout declarations, UTC start and monotonic origin; collection,
test-start, completed setup/call/teardown phases and entry into session finish
carry elapsed timestamps. Each line is appended and closed without `fsync`,
retaining progress if a later test or shutdown stalls. Existing report uploads
include these journals. A hard termination may leave a partial last line, and
missing finalization is not proof of which earlier stack snapshot was current.

These operator-only journals are best-effort process diagnostics, not durable or
authenticated completion evidence. `session_finish` records hook entry, not
completion of subsequent reporting or process shutdown. The existing final worker
`.json` payload and calibration admission remain unchanged; `.jsonl` progress is
never a substitute for a complete timing receipt or a passing test/CI outcome.
The journal changes neither scheduling nor case selection, worker counts,
coverage requirements or the supervisor's approval/execution policy.

`quality-fast` now aggregates concurrent lint, contract/conformance, code-quality,
and the existing macOS semantic audit. Every child must succeed, including on draft
PRs; failed, cancelled, and unexpectedly skipped children fail the aggregate.
The contract lane executes TypeScript unit tests as well as generated-client checks,
live conformance, base-ref compatibility, and installed-wheel smoke. Code-quality
workers share read-only source/AST data within each process; mutable test fixtures
and generated temporary output remain independently validated.

Twelve standard runners increase behavioral parallel capacity without changing test
selection or the combined branch-coverage measurement. Compare several successful CI
runs before claiming a wall-time reduction: added capacity can increase total runner
minutes, and cold caches or queued jobs can offset the idealized speedup. Keep main
and merge-candidate verification; no previously tested tree is reused as authority.

## Battlefield viewer

Inspect the Event Companion battlefield projection with an orbitable 3D camera:

```powershell
uv run python scripts/mock_event_layout_ui.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. All 15 Event Companion force-disposition
pairings and every A/B/C variant are available: 45 of 45 source-hashed
executable battlefield packages with terrain, regions, source-linked objective
footprints, walls, and floors. Across the package, the viewer exposes 720
physical terrain-area footprint pieces forming 617 logical rules areas, plus
1,349 physical components. The PDF layout-page Single/Separate glyphs are
rendered at their source coordinates using the page-8 legend; 103 Single joins
pair 206 footprint pieces and the other 514 pieces remain individual areas.
Page 9 contains the source-backed 29-component exception, while every other
layout contains 30. See
[docs/BATTLEFIELD_VIEWER.md](docs/BATTLEFIELD_VIEWER.md) for controls, data
authority, complete battlefield geometry, executable Primary scoring for all 25
Event Companion missions, and Step 5G lifecycle, restore, viewer-redaction, and
replay certification of both players' ordinary Primary scoring boundaries on all
45 A/B/C layouts. The 90 layout/direction cases begin at an engine-owned fight
activation decision boundary, round-trip `replay-artifact-v9-sequencing`,
and require exact `ReplayRunner` reproduction. All 18 Secondary Mission cards
are source-backed and executable through turn-end scoring with lifecycle restore
evidence; their lifecycle certification remains Layout-A-only. The broader
mission runtime exposes all 14 Mission Actions.

CI uploads each shard's JUnit report for future median-duration profiles. Full behavioral shards
run for ready pull requests, merge candidates, and pushes to `main`; draft pull requests keep the
faster quality and parallel type-check feedback without repeatedly running the complete suite.
The stable `coverage-gate` aggregate fails closed when any behavioral shard does not succeed, then
combines all twelve coverage artifacts and enforces the branch-coverage threshold. Repositories that
enable branch protection can require `quality-fast`, `mypy`, `pyright`, and `coverage-gate` without
encoding matrix shard names in the protection rule.

## External adapter contract

The canonical Phase 18D language-neutral baseline and completed Phase 18E-18J
session, command, reconnect, authentication, authorization, redaction,
interaction, and battlefield contracts are in [`contracts/`](contracts/README.md).
Phase 18L adds the closed `session-persistence-v3-weapon-instances` operator-only
persistence checkpoint contract and fail-closed recovery semantics. Its
runtime-tree build fingerprint, explicit first-boot initialization, locked and
verified SQLite v2 transaction, and unpruned per-revision commitment chain keep
missing, stale, or internally inconsistent durable state from being accepted as
a recovered authority. The
bundle includes Draft 2020-12 schemas, OpenAPI 3.1, real session-derived examples with explicit
decision-family coverage status, proposal examples, versioned session metadata and idempotent
command outcomes, protected opaque role-bound cursor/resync payloads, explicit principal-role policy,
compatibility/redaction/session/coordinate/persistence semantics, and conformance scenarios.
Verify schema, example, OpenAPI, Python-version, coverage, manifest, and compatibility drift with:

```bash
uv run --no-sync python scripts/build_engine_build_identity.py --check
uv run --no-sync python scripts/build_external_contract.py --check
uv run --no-sync python scripts/smoke_installed_contract_wheel.py
```

After an intentional change to packaged runtime Python/JSON resources or the
packaged contract schemas, regenerate
`src/warhammer40k_core/_engine_build_manifest.json` with
`uv run python scripts/build_engine_build_identity.py` before regenerating the
external examples that publish that build ID.

The Phase 18M-A TypeScript client in
[`conformance/typescript/`](conformance/typescript/README.md) generates models
from that OpenAPI document, validates the canonical JSON Schemas, and completes
the first certified HTTP-only scenario against two clean reference servers:

```bash
cd conformance/typescript
npm ci
npm test
```
