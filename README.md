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

Each covered behavioral shard must finish successfully within 18 minutes
(1,080 seconds, inclusive) for approval. Timing alone does not terminate it then:
the supervisor permits execution through exactly 30 minutes and terminates the
workload process group only after 1,800 seconds. A passing workload that finishes
after 18 minutes still fails the gate while retaining its complete results.
Source-history validation, cold index construction, the isolated mirror, parallel
tests and their report finalization all run inside the same supervisor clock.
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

The twelve behavioral manifests in `ci/test_shards/` use deterministic
largest-processing-time balancing. One heavy, source-bound module is partitioned
into its twenty exact collected cases. The bounded mirror setup case is a separate
selector; its file selector denotes the remaining cases. CI always deselects that
node from parallel work and runs it once on its owning shard. Other files remain
intact. The required guards verify the exact selected inventory and partition.
Verify that every selected file or declared case appears exactly once:

```bash
uv run --no-sync python scripts/build_test_shards.py --check --shard-count 12
```

Download the `behavior-report-*` artifacts from each chosen successful run into a
separate directory outside the checkout, then regenerate (repeat both options for
additional runs). Downloaded profiles are supplied inputs, not generated source:

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
run together so pytest can reuse module-scoped fixtures. Worker assignments and
capacities remain unchanged. Modules start in descending order of their longest
case, with descending case costs inside each module and original collection order
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
After balancing, the generator swaps the bucket with the lowest unrounded modeled
test load into shard 1, breaking ties by its original bucket number. This final
permutation preserves every bucket's selectors and all measured case/selector
weights, while avoiding assigning the cold role by largest-first insertion order.
The execution metadata records this policy. Startup and report finalization are
not test timings or added scheduling reserves; the model does not guarantee a
hosted wall time. Empty buckets and committed manifests fail validation, because
an empty pytest selector list would run the default suite.

A complete local JUnit profile is also accepted, either one XML or one directory
containing the isolated mirror and remaining-suite XMLs from the same covered run.
Label its host, worker counts and concurrent validation accurately; do not mix
local and hosted-runner timings in one representative CI profile. Local timing
weights do not establish hosted cost accuracy or a speedup.
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
inventory changes still require a fresh complete successful baseline profile.

The current calibration retains 284 compatible source-bound raw worker receipts
and 34,836 passed three-phase samples covering 6,115 current cases. All sixty
source collected inventories were authenticated before filtering by exact counts and hashes;
the original 679-node inventory also matches the three independently retrieved,
SHA-authenticated workers in artifacts 13649430067 and 13648072478. The diagonal
generator update changes two behavioral modules, excluding the eight PR656
worker receipts whose collected inventories include them and all 1,139 samples
from those receipts. Every surviving outcome, source identity and phase tuple
is unchanged. The 139 cases in those two modules have no compatible retained
hosted observation and use the fresh complete local baseline below. No unknown
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

The latest appended source is attempt 1 of failed PR656 run
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
PR656 planning values. The current manifests use the complete diagonal-generator
profile below and the compatible receipts described above. Timing budgets, test
selection and the scheduling algorithm remain unchanged. Reassignment cannot
shorten an individual test, and planning metadata does not establish compliance
with the eighteen-minute limit. A fresh hosted run is required; an over-limit
result remains a blocker.

The complete baseline is the successful local 6,254-case covered diagonal-generator
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

Fixture setup observations are worker/order dependent; taking maxima and regrouping
does not establish new fixture multiplicity, hosted wall time or the eighteen-minute
approval goal. Existing module grouping, twelve shards, four-worker dispatch, the cold
shard-1 role, isolated mirror limit and full coverage requirements remain unchanged.
Fresh complete correctness/coverage qualification remains mandatory. `--check`
re-derives every planning cost/selector and the sidecar digest; worker dispatch
rejects a missing or altered declared sidecar. Run the normal generator command
above with this sidecar in the output directory to reproduce the manifests.

Every supplied complete baseline JUnit run must cover the current behavioral file inventory. Missing files,
duplicate cases, failed/skipped cases, invalid durations, and truncated suite counts
are rejected. Outside the explicit initial migration seed above, new test files
require a fresh complete profile; timings are never filled with zero. `durations.json` preserves report SHA-256 hashes and run descriptions.
Historical profiles measure their recorded case inventory; added, renamed or
changed cases within an existing file require a refreshed successful complete
profile to provide their exact case weights. Preserve previous measurements in
Git history and retained source artifacts; never invent missing weights or
substitute file averages for CI dispatch.

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
