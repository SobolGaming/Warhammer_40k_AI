# AGENTS.md — CORE V2 Rules

## Purpose

This repository is a strict bottom-up reconstruction of the Warhammer 40,000 engine.

The legacy repo is a reference, replay corpus, and source of known bug classes. Do not copy legacy files wholesale. Port only small, reviewed concepts after writing strict CORE V2 tests.

CORE V2 exists to avoid the legacy repo's failures: broad exception swallowing, permissive fallbacks, partial stubs masking missing fields, local-only fixes, ambiguous model ownership, scattered rule-text parsing, and divergent UI/headless/network paths.

## Session rule

Before coding or reviewing, read this file, `README.md`, `pyproject.toml`, and relevant tests.

If a request conflicts with this file, stop and ask.

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
- Runtime engine code consumes structured descriptors, not ad hoc string parsing.
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
- using `getattr(obj, "required_field", default)` to tolerate incomplete domain objects

Allowed exception handling must catch a specific exception, preserve context, and either re-raise a typed domain error or return a typed invalid/unsupported result.

If a test object lacks a required field, fix the fixture. Do not weaken production code.

## Test policy

Stubs are allowed only for pure functions and must be marked `stubbed`.

Engine behavior tests must use real domain objects or canonical fixtures. This includes movement, shooting, charge, fight, deployment, transports, attached units, damage allocation, replay, decision dispatch, UI routing, and network serialization.

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

Tests for new decision work must cover valid submission, stale/drift/malformed invalid submission, replay/payload round-trip, deterministic JSON-safe records, and viewer-scoped projection/event redaction when visibility can differ by viewer.

## Architecture boundaries

Dependency direction:

- `core` imports no project-layer modules
- `geometry` may import `core`, not `engine` or `adapters`
- `rules` may import `core` and descriptors, not adapters
- `engine` may import `core`, `geometry`, and `rules`
- `adapters` may import `engine`; engine must not import adapters

Enforce this with import-linter and code-quality tests.

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
uv run pytest tests/
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
- add or change a player-facing decision, finite option family, proposal kind, or adapter-visible payload without updating or confirming `docs/ADAPTER_DECISION_CONTRACT.md`;
- weaken a CORE V2 invariant.

Agents should prefer review, tests, audit scripts, small typed modules, and migration plans over large production-code changes.
