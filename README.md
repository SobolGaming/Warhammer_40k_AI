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
before runtime catalog use.

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
PATH="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:${PATH}" uv run pytest tests --ignore=tests/code_quality -n auto --dist=worksteal --cov=warhammer40k_core --cov-report=term-missing --cov-fail-under=64
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
  --cov=warhammer40k_core --cov-report=term-missing --cov-fail-under=64
```

The `PATH` prefix exposes the Node.js runtime bundled with Codex desktop to the executable
viewer-renderer regressions. It is safe when that directory is absent: an independently installed
`node` later on the existing `PATH` remains available. Keep this prefix on full-suite runs so those
tests do not fail only because the desktop shell omitted the bundled runtime.

CI shards this same behavioral suite, combines branch coverage, and applies the temporary 64%
gate after every shard succeeds. Full type checking and architecture checks also remain required
in CI and run on the `pre-push` pre-commit stage; commit-time hooks are limited to Ruff check and
format for a shorter edit/commit loop.

The current owner-approved coverage floor is 64%; later coverage work must restore 85%. The full
warhammer40k_core package and branch metric remain unchanged, with no added coverage
omissions or exclusions. This policy change does not claim either threshold has passed;
all required tests and other gates must still succeed. See the
[active review policy](docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md).

The twelve behavioral manifests in `ci/test_shards/` use deterministic
largest-processing-time balancing. One heavy, source-bound module is partitioned
into its twenty exact collected cases; every other file remains intact. The
required quality guard checks that partition against real pytest collection.
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
each covering all 4,886 cases. Current scheduling estimates take each case's larger
recorded cost, also including fully passed setup/call/teardown observations from
[40888978899](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/40888978899).
That later run failed; it is not a passing profile. Its 277 failed or unreported
cases keep authentic older measurements. The exact derivation and timing hashes
are recorded in `ci/test_shards/case-partitions.json` under `evidence.weight_refresh`.

Session startup, source-index setup, reporting and runner queues are assessed
separately. Weight totals are planning inputs, not job wall times or proof of the
temporary twelve-minute CI goal. Existing observation-based estimates do not
relax the complete-profile validation below.

A single complete local JUnit XML is also accepted; label its host accurately and
do not mix local and hosted-runner timings in one representative CI profile.
Every supplied run must cover the current behavioral file inventory. Missing files,
duplicate cases, failed/skipped cases, invalid durations, and truncated suite counts
are rejected. Outside the explicit initial migration seed above, new test files
require a fresh complete profile; timings are never filled with zero. `durations.json` preserves report SHA-256 hashes and run descriptions.
Historical profiles measure their recorded case inventory; changed cases within an
existing file require refreshed successful CI reports to reflect their new cost.

Both Python CI lanes upload JUnit, slowest-test output, and per-worker JSON timing
artifacts containing collection node IDs, collection time, setup/call/teardown times,
outcomes, Python/platform/CPU/memory metadata, and commit/run IDs. Enable the same
local evidence with `TEST_TIMING_DIR=reports/timing`. These artifacts distinguish
collection overhead and long individual cases from aggregate file costs.

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
physical terrain-area footprint pieces forming 608 logical rules areas, plus
1,349 physical components. The PDF layout-page Single/Separate glyphs are
rendered at their source coordinates using the page-8 legend; 112 Single joins
pair 224 footprint pieces and the other 496 pieces remain individual areas.
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
