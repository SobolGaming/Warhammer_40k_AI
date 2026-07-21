# AGENTS.md — CORE V2 Rules

## Purpose

This repository is a strict bottom-up reconstruction of the Warhammer 40,000 engine.

The legacy repo is a reference, replay corpus, and source of known bug classes. Do not copy legacy files wholesale. Port only small, reviewed concepts after writing strict CORE V2 tests.

CORE V2 exists to avoid the legacy repo's failures: broad exception swallowing, permissive fallbacks, partial stubs masking missing fields, local-only fixes, ambiguous model ownership, scattered rule-text parsing, and divergent UI/headless/network paths.

## Session rule

Before coding or reviewing, read this file, `README.md`, `pyproject.toml`, and relevant tests.

If a request conflicts with this file, stop and ask.

## Pull request publishing

When a user says "create a new PR", treat that as a requirement and authorization
to complete the remote publishing workflow: create or select the scoped branch,
commit the intended changes, push the branch to the configured repository remote,
and create the pull request in that repository. A local branch or commit alone does
not satisfy the request. If remote publication is blocked, report the blocker rather
than presenting local-only work as a created PR.

## Build order

Build bottom-up:

1. governance and quality gates
2. deterministic RNG and dice
3. attributes and modifiers
4. rule text normalization
5. wargear and weapon profiles
6. model geometry
7. units and attached units
8. 2.5D visibility and pathing
9. battlefield and objectives
10. decision system
11. movement
12. shooting
13. charge/fight
14. deployment/reserves/transports
15. adapters: headless, UI, network
16. AI/rankers/training

Do not add AI/ranker/training logic before the deterministic rules core, decision records, replay, and movement/shooting/fight slices are trustworthy.

## Non-negotiable invariants

- Engine core is fail-fast.
- No broad exception handling.
- No silent fallback behavior.
- No backwards-compatibility shims unless explicitly approved.
- No player choice outside `DecisionRequest` / `DecisionResult`.
- UI, headless, network, replay, and tests must use the same engine decision path.
- Engine alone mutates authoritative game state.
- Movement/charge/pile-in/consolidate/disembark/reserves/reactive movement require `PathWitness` or typed invalid result.
- Endpoint-only movement validation is invalid except for explicit teleport/set-up placement.
- Raw rule text is normalized once at the data boundary.
- Generated content is committed as versioned data artifacts (JSON) plus
  typed fail-fast loaders, not as Python modules. Generators emit data;
  loaders validate eagerly and preserve package hashes and provenance.
- Forge World, Crusade, Boarding Action/Boarding Actions, Kill Team, Legends,
  and Warhammer Legends content is out of CORE V2 support scope. Do not ingest,
  scaffold, document, or expose it as supported engine or catalog content unless
  this file is explicitly changed first.
- Runtime engine code consumes structured descriptors, not ad hoc string parsing.
- Reusable rule semantics use source-backed RuleIR, generic semantic handlers,
  or approved runtime hooks before named handlers.
- Named runtime handlers are deliberate exceptions for bespoke resources, state
  machines, setup/mission integration, or phase orchestration that cannot be
  expressed through existing generic surfaces without polluting them.
- Runtime code must not gate behavior on rule or ability display names, normalized rule-text tokens, or locally re-normalized keyword strings. Behavior gates use stable source rule IDs, descriptor IDs, or canonical keyword tokens carried by the catalog.
- Load-support status and semantic-execution status are distinct recorded fields for all runtime content. No manifest, coverage report, or documentation may present a placeholder or load-only module as implemented gameplay support.
- Physical battlefield operations use explicit model-group APIs.
- Attached units are first-class rules units.
- Entity IDs, action IDs, event IDs, and replay payloads are deterministic and serializable.
- Decision records must not contain Python object reprs or memory addresses.
- Unsupported rule paths raise explicit domain errors or return typed unsupported/invalid results.

## Exception and fallback policy

Forbidden by default:

- bare `except`
- `except Exception`
- `except BaseException`
- unparenthesized multi-exception handlers such as `except A, B:`
- `except ...: pass`
- catching an error and returning `None`, `True`, `False`, or a default value to keep going
- catching a typed domain error and returning an empty, False, or None default to keep going. Where absence is a legal domain state (Strategic Reserves, embarked cargo, destroyed units), use an explicit presence-query API on the owning state object; exceptions are not control flow.
- using `getattr(obj, "required_field", default)` to tolerate incomplete domain objects

Allowed exception handling must catch a specific exception, preserve context, and either re-raise a typed domain error or return a typed invalid/unsupported result.

If a test object lacks a required field, fix the fixture. Do not weaken production code.

## Test policy

Stubs are allowed only for pure functions and must be marked `stubbed`.

Full-suite pytest runs must use xdist work stealing by default:
`uv run pytest -n auto --dist=worksteal tests/`. Do not run the full suite
serially unless xdist is unavailable or a specific test is known or suspected
to be distribution-sensitive; document that reason when reporting checks.
Focused test subsets may run serially when that is the simpler or faster
diagnostic path.

Every behavioral test-file addition, deletion, move, or rename must update the
committed four-shard inventory in `ci/test_shards/`. Regenerate
`durations.json` and `shard-1.txt` through `shard-4.txt` from a representative
JUnit profile as documented in `README.md`; do not commit a behavioral test
file that is missing from the shard manifests. Before committing any test-file
change, and before every PR, run this exact fail-closed check:
`uv run --no-sync python scripts/build_test_shards.py --check --shard-count 4`.

Engine behavior tests must use real domain objects or canonical fixtures. This includes movement, shooting, charge, fight, deployment, transports, attached units, damage allocation, replay, decision dispatch, UI routing, and network serialization.

Tests must not replace `lifecycle.decision_controller` directly. Tests must not import from other `test_*.py` modules; shared setup used across test modules lives in named shared helpers. Each major phase family must have facade-driven coverage through `AdapterGameSession` / `LocalGameSession` submissions and viewer-scoped projections or event deltas.

Every bug fix must:

1. name the violated invariant;
2. search for the same bug class elsewhere;
3. replace duplicated local logic with shared code when possible;
4. add a regression test;
5. add a static/code-quality audit when feasible.

Do not fix only the observed call site.

## Unit/model semantics

Do not introduce ambiguous `unit.models` semantics.

Use explicit terminology:

- `unit.own_models`: models physically owned by one unit object
- `unit_group.all_models()`: all models in the attached rules unit
- `unit_group.alive_models()`: alive models in the attached rules unit

Physical operations must use group-aware APIs when rules operate on an attached unit as a whole.

Physical operations include movement, coherency, engagement range, line of sight, range, objective control, damage allocation, event logging, replay payloads, pathing, collision, and visibility.

## Decision/replay policy

Every player choice follows:

DecisionRequest -> DecisionResult -> validation -> engine mutation

UI, network, headless, AI, and replay may choose decisions differently, but they must not use different validation or mutation paths.

Replay and determinism are core features. Same code, seed, config, and inputs must produce the same logical result. It is acceptable for CORE V2 to differ from the legacy repo.

Every `*_DECISION_TYPE` constant defined in `engine/` must be registered in the engine decision dispatch registry or appear in the documented nested-decision allowlist in `docs/ADAPTER_DECISION_CONTRACT.md`. Orphan decision types fail the quality gate. New decision types register their validator and applier in the same PR that defines the constant.

## Adapter decision contract policy

All new player-facing choices must use the Phase 11D adapter decision contract in `docs/ADAPTER_DECISION_CONTRACT.md`.

A player-facing choice must be one of:

- a finite engine-enumerated `DecisionRequest` option selected through `FiniteOptionSubmission -> DecisionResult`; or
- a parameterized proposal request submitted through `ParameterizedSubmission -> DecisionResult`.

Adapters, UI, CLI, network clients, headless AI, replay, and tests must not bypass `GameLifecycle.submit_decision(...)`, `DecisionController`, `DecisionRecord`, `EventRecord`, proposal validation, or engine-owned mutation.

Finite decisions must expose deterministic option IDs and JSON-safe option payloads on the pending `DecisionRequest`. Adapters must select one pending option ID. Adapters must not invent option IDs or mutate state from option payloads.

Parameterized decisions must define or reuse typed proposal payloads with replay-safe source context. They must validate stale, drifted, malformed, schema-invalid, or wrong-context submissions before queue pop when required by the adapter contract. They must return typed invalid diagnostics and must not mutate authoritative state unless engine-owned validators accept the proposal.

Rule-invalid but well-formed proposals may be recorded as rejected attempts only when the adapter contract explicitly allows that behavior and a fresh pending proposal request is emitted for retry.

Any new decision type, finite option family, proposal kind, adapter-visible payload shape, or viewer-visibility behavior must update `docs/ADAPTER_DECISION_CONTRACT.md` in the same PR, or the PR must explicitly justify why the existing contract already covers it.

Hidden or secret pending decisions, proposal requests, decision records, domain events, projections, and adapter event deltas must remain viewer-scoped. They must not leak hidden opponent information through payloads, metadata, counts, option lists, event details, or derived fields.

Hidden-information redaction logic must live in exactly one shared adapters module; projection, event-stream, and server code must consume it rather than defining local hidden-type sets. HTTP responses, status summaries, error payloads, and all other transport-level metadata are adapter-visible payloads and must be viewer-scoped exactly like projections and event deltas.

Tests for new decision work must cover valid submission, stale/drift/malformed invalid submission, replay/payload round-trip, deterministic JSON-safe records, and viewer-scoped projection/event redaction when visibility can differ by viewer.

## RuleIR, runtime hook, and named-handler policy

Named handlers are acceptable only when they represent genuinely bespoke game
subsystems. They are not acceptable when they are content-specific wiring for
reusable semantics.

Use source-backed RuleIR, generic semantic handlers, or approved runtime hooks
when a rule can be expressed as:

- source ownership, phase/window, target, or keyword checks;
- finite decision options or parameterized proposals;
- ability grants, persisting effects, rerolls, modifiers, target restrictions,
  or Objective Control adjustments;
- movement, placement, reserve, reactive-movement, or phase-boundary hooks;
- deterministic event, replay, audit, and source-context payloads.

Keep or add a named handler only when the rule owns at least one of these:

- bespoke army-level resource accounting;
- a multi-step faction state machine or unique cross-phase memory model;
- special setup, mission, army-construction, or non-local orchestration;
- engine-level state that does not fit an existing generic runtime surface;
- semantics that would require faction-specific escape hatches inside generic
  lifecycle modules.

Faction army rules may remain named orchestrators when they own unique faction
concepts, but reusable sub-effects must route through existing generic IR,
runtime modifier, Stratagem, decision, movement, objective-control, or ability
services. Do not duplicate local mutation for a sub-effect already supported by
an engine-owned generic service.

Detachment rules, Enhancements, Upgrades, and Stratagems are generic-first.
Implement them through RuleIR, ability records, Stratagem records, runtime
modifier bindings, and approved hook bindings unless the PR documents the
bespoke subsystem that requires a named handler. Group these migrations by
semantic hook family, not by display name alone.

New generic hook families are allowed only when a real source-backed rule in the
same PR needs them. They must be typed, source-ID-linked, lifecycle/bundle
loaded, consumed by the engine owner of the mutation, and covered by at least
one real consumer-path regression. Do not prebuild speculative generic
registries.

Generic lifecycle modules and runtime hook dispatch must stay content-neutral.
Do not branch on faction, detachment, Enhancement, Stratagem, rule display name,
or source-text tokens in generic lifecycle code. Content-specific builders must
sit behind source-linked provider or registry entries.

Every new named handler must include:

1. a documented justification using the bespoke-subsystem rubric above;
2. generated source/execution IDs and deterministic handler IDs;
3. lifecycle-loading coverage without manual handler injection;
4. replay/audit payload coverage for state-changing behavior;
5. unsupported/invalid diagnostic coverage where semantics are partial;
6. handler identity drift coverage;
7. named-handler budget/classification updates, or proof the current approved
   budget already covers the handler.

If a generic registry defaults module starts accumulating source-specific
builders, split those builders into source/provider modules and compose them
into the default registry. Do not let a defaults module become a new
named-handler sink.

## Architecture boundaries

Dependency direction:

- `core` may import pure `geometry` primitives/helpers; it must not import
  `rules`, `engine`, or `adapters`
- `geometry` must not import `rules`, `engine`, `adapters`, or `interfaces`;
  pure computational geometry modules must not import `core`
- `rules` may import `core` and descriptors, not adapters
- `engine` may import `core`, `geometry`, and `rules`
- `adapters` may import `engine`; engine must not import adapters
- `profiling` and `interfaces` may import `engine`; no package under `src/warhammer40k_core` may import `profiling` or `interfaces`
- `rules` must not import `engine` or `adapters`
- every package under `src/warhammer40k_core` must be covered by an import-linter contract; adding a package without a contract fails the quality gate

Enforce this with import-linter and code-quality tests.

### Module size policy

New modules must stay under 1,500 lines (generated faction-content modules
keep their existing 2,000-line cap). Files above the budget are frozen to
their current responsibilities: extract before extending. The budget is
enforced by a code-quality test with a legacy allowlist that may only shrink;
adding a file to the allowlist is forbidden.

## Legacy migration rule

No wholesale legacy file copies.

Allowed process:

1. identify behavior to preserve;
2. write strict CORE V2 tests first;
3. identify the invariant involved;
4. port the smallest necessary algorithm or data transform;
5. remove fallback behavior;
6. replace duck typing with typed domain objects;
7. add serialization/replay coverage if game state is affected.

Legacy code containing broad exceptions, fallback behavior, ambiguous model access, or runtime string parsing must be rewritten.

## Required commands before PR

Run:

uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pyright
uv run pytest -n auto --dist=worksteal tests/
uv run --no-sync python scripts/build_test_shards.py --check --shard-count 4
uv run lint-imports
uv run pre-commit run --all-files

If a command cannot be run, say so. Do not claim it passed.

## Stop and ask

Stop before coding if the change would:

- add fallback behavior;
- require broad exception handling;
- use stubs in engine integration tests;
- change architecture boundaries;
- copy legacy code wholesale;
- make UI/headless/network paths diverge;
- use endpoint-only movement validation;
- add support, scaffold rows, generated docs, or catalog/runtime exposure for
  Forge World, Crusade, Boarding Action/Boarding Actions, Kill Team, Legends,
  or Warhammer Legends content;
- add a named handler for reusable semantics that fit RuleIR, a generic
  semantic handler, or an approved runtime hook;
- add a named handler without documented bespoke-subsystem justification and
  named-handler budget/classification treatment;
- add faction-, detachment-, Enhancement-, Stratagem-, display-name-, or
  source-text-token branching to generic lifecycle modules or runtime hook
  dispatch;
- add speculative generic hook families not required by real source-backed
  rules in the same PR;
- add or change a player-facing decision, finite option family, proposal kind, or adapter-visible payload without updating or confirming `docs/ADAPTER_DECISION_CONTRACT.md`;
- weaken a CORE V2 invariant.

Agents should prefer review, tests, audit scripts, small typed modules, and migration plans over large production-code changes.
