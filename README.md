# warhammer40k-core-v2

Strict bottom-up Warhammer 40k engine reconstruction.

Start here:

```bash
uv python install 3.14.5
uv lock
uv sync
PATH="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:${PATH}" \
  uv run pytest -n auto --dist=worksteal tests/
```

## Test commands

Pytest defaults are intentionally lightweight: narrow local and IDE runs do not start xdist
workers or collect coverage unless requested.

Fast local feedback excludes benchmarks and tests marked `slow`:

```bash
uv run pytest -m "not benchmark and not slow" -q -n0 --no-cov
```

Architecture and source-shape audits run serially without behavioral coverage:

```bash
uv run pytest tests/code_quality -q -n0 --no-cov
```

The unsharded full behavioral coverage gate is:

```bash
PATH="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:${PATH}" \
  uv run pytest tests --ignore=tests/code_quality \
  -n auto --dist=worksteal \
  --cov=warhammer40k_core --cov-report=term-missing --cov-fail-under=85
```

The `PATH` prefix exposes the Node.js runtime bundled with Codex desktop to the executable
viewer-renderer regressions. It is safe when that directory is absent: an independently installed
`node` later on the existing `PATH` remains available. Keep this prefix on full-suite runs so those
tests do not fail only because the desktop shell omitted the bundled runtime.

CI shards this same behavioral suite, combines branch coverage, and applies the single 85%
gate after every shard succeeds. Full type checking and architecture checks also remain required
in CI and run on the `pre-push` pre-commit stage; commit-time hooks are limited to Ruff check and
format for a shorter edit/commit loop.

The four behavioral manifests in `ci/test_shards/` are generated from historical JUnit file
durations with deterministic largest-processing-time balancing. Verify that every behavioral test
file appears exactly once with:

```bash
uv run python scripts/build_test_shards.py --check --shard-count 4
```

After collecting a representative full-suite profile, rebalance the manifests with:

```bash
uv run python scripts/build_test_shards.py \
  --junit reports/full-behavior-profile.xml \
  --shard-count 4
```

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
activation decision boundary, round-trip `replay-artifact-v8-phase17n-step5a`,
and require exact `ReplayRunner` reproduction. All 18 Secondary Mission cards
are source-backed and executable through turn-end scoring with lifecycle restore
evidence; their lifecycle certification remains Layout-A-only. The broader
mission runtime exposes all 14 Mission Actions.

CI uploads each shard's JUnit report for future median-duration profiles. Full behavioral shards
run for ready pull requests, merge candidates, and pushes to `main`; draft pull requests keep the
faster quality and parallel type-check feedback without repeatedly running the complete suite.
The stable `coverage-gate` aggregate fails closed when any behavioral shard does not succeed, then
combines all four coverage artifacts and enforces the branch-coverage threshold. Repositories that
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

The detailed phase roadmap belongs in [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md).
This README keeps only the build sequence and the current high-level status.

Build in this order:

1. Governance, quality gates, deterministic RNG, dice, attributes, modifiers,
   and source-text normalization.
2. Wargear, weapon profiles, model geometry, units, attached units, battlefield
   geometry, visibility, pathing, objectives, and mission setup.
3. Decision requests/results, event records, replay, lifecycle routing, and the
   shared adapter contract.
4. Movement, shooting, charge, fight, deployment, reserves, transports,
   reactive movement, and grouped attack/damage resolution.
5. Source packages, catalog generation, rule IR, generic rule execution,
   faction coverage, and faction-specific runtime handlers.
6. Adapters and interfaces: headless, CLI, UI, network, event streams,
   viewer-safe projection, and trigger opportunity windows.
7. AI, rankers, training, and performance work only after the deterministic
   rules core and replay records are trustworthy.

Current status:

- Core rules infrastructure through movement, shooting, charge, fight, setup,
  reserves, transports, missions, replay, source ingestion, catalog generation,
  rule IR, generic rule execution, and adapter decision submission is in place.
- Phase 17O exposes a deterministic `capability-manifest-v2-directed-primary`
  inside the `support-profile-v4-directed-primary` response. It reports load,
  display, mustering, physical, semantic, full-game, network, and replay
  capability independently for the
  selected rosters, units, rules, mission, and geometry. Player views omit every
  opponent-owned row, unsupported reason, count, and derived selection hash;
  current full-game and release claims remain false without certified evidence.
- Phase 18L persists the complete single-authority adapter server state as one
  content-addressed operator artifact. The store distinguishes explicit
  initialization from recovery, validates the exact SQLite v2 schema while
  holding the writer transaction, and verifies the written singleton row before
  publication. Checkpoints retain authoritative session state, accepted command
  outcomes, replay inputs, RNG state, role bindings, protected cursor state, and
  an unpruned revision commitment chain; restart verifies those histories plus
  the generated immutable runtime-tree build fingerprint before exposing a
  recovered session. These hashes detect accidental corruption and internal
  inconsistency. They do not resist a malicious storage writer or prove that an
  older, otherwise valid database was not rolled back; that threat requires an
  external trusted anchor.
- The checked-in Chaos Daemons Strike Force reprices to 2,075 points under the
  July 2026 MFM package and is correctly rejected as 75 points over the
  2,000-point limit; the original three six-model Bloodcrusher units remain
  unchanged. A typed,
  hashed reconciliation reviews its exact five datasheets against the current
  official PDF and pins every historical generator input by hash without
  importing its retired package identity into runtime. It enforces Be'lakor's
  `DAMAGED 1-7` and keeps `SHADOW LEGION` as a detachment grant. Its
  eight selected units, Cavalcade of Chaos and Shadow Legion runtime bundles,
  selected abilities, and Apocalyptic Steeds assignments carry active semantic
  runtime evidence independently of that mustering failure. The accepted
  Bloodcrushers, Bloodhunter, and Be'lakor geometry records are applied at
  runtime; only the four Bloodthirster, Lord of Change, Plaguebearers, and
  Plagueridden representative heights remain review-blocked. Those four blockers
  keep the roster from claiming `PHYSICALLY_PLAYABLE`. This is exact
  selected-component semantic
  support, not a whole-faction or Phase 20 full-game/replay claim.
  Verify the committed catalog with
  `uv run python tools/generate_chaos_daemons_roster_catalog.py --check`.
- `uv run python tools/generate_ability_support_matrix.py` also regenerates the
  typed cross-source semantic-equivalence artifact and report at
  `data/generated/ability_coverage/cross_source_semantic_equivalence.json` and
  `docs/CROSS_SOURCE_SEMANTIC_EQUIVALENCE.md`. Fully structured RuleIR uses a
  provenance-free semantic hash; incomplete IR is grouped by exact normalized
  text only and cannot transfer gameplay support. Every generated faction
  support document consumes the same audit.
- Datasheet RuleIR follows the stable, source-identified shard convention in
  [`docs/FACTION_PACK_RULE_IR_ARTIFACTS.md`](docs/FACTION_PACK_RULE_IR_ARTIFACTS.md).
  Physical shard labels are not faction-support assertions: exact datasheet
  ownership is derived from the committed source snapshot and stored with typed
  provenance. Datasheet work adds records to that registry instead of creating a
  dated, datasheet-named runtime package. The generated Maulerfiend cross-faction
  support report also makes explicit which mechanics are reusable and which
  faction-local records remain unsupported.
- Faction semantic execution is active incremental work. Current runtime
  support includes selected Phase 17G faction slices across Chaos Daemons,
  Chaos Space Marines, Aeldari, Death Guard, World Eaters, Orks,
  Space Marines, Necrons, Leagues of Votann, Thousand Sons, and Tyranids.
  Chaos Daemons Shadow Legion supports Thralls of the First Prince mustering restrictions and keyword
  grants, Murderer's Cowl, Penumbral Puppetry, Gloam Rot, Shadow's Caress,
  Leaping Shadows, Mantle of Gloom, Fade to Darkness, and Disciples of
  Be'lakor Dark Pacts through shared advance, Scouts, objective-control aura,
  target-restriction, runtime-modifier, selected-unit grant, attack-completion,
  turn-end reserves, out-of-phase shooting, and Feel No Pain continuation
  paths. Chaos Space Marines Dark
  Pacts uses shared selected-to-shoot and selected-to-fight grant decisions,
  out-of-phase selected-to-shoot grant routing, attack-sequence weapon keyword
  modifiers, and post-attack Leadership-test D3 mortal-wound routing including
  Feel No Pain continuation decisions. Aeldari Path of the Outcast supports
  Far-reaching Doom,
  Camouflaged Snipers, Assassins' Eye, Eldritch Suppression, Casting Back the
  Veil, and Nomads of the Hidden Way through the shared Shooting, Stratagem,
  Battle-shock, Hidden/detection, and triggered-movement paths. Aeldari
  Corsair Coterie supports Veterans of the Void, Relentless Raiders, Void
  Thieves, Infamy, Webway Pathstone, Archraider, Voidstone, and all six Corsair
  Coterie Stratagems through shared mustering, objective-control, movement/charge-
  completion, reserves, setup, turn-end, Stratagem-cost, attack-reroll,
  triggered-movement, targeting-restriction, and generic RuleIR runtime paths. Space
  Marines Oath of Moment supports Command phase target selection, target-scoped
  Hit-roll rerolls, the Codex Space Marines Detachment Wound-roll bonus gate,
  and Black Templars, Space Wolves, and Deathwatch Chapter mustering
  restrictions. Necrons Reanimation Protocols supports Command phase
  rules-unit activation, source-backed D3 healing, destroyed-model revival,
  attached rules-unit identity, and owning-player healing selections through the
  shared healing decision path. Leagues of Votann Prioritised Efficiency
  supports deterministic Yield Point gains from Command phase objective control,
  derived Hostile Acquisition/Fortify Takeover modes, and mode-scoped Hit/Wound
  modifiers. Orks Waaagh! supports optional once-per-battle Command phase
  activation, active-effect expiry at the next own Command phase, Advance-then-
  Charge eligibility, melee Strength/Attacks modifiers, and a 5+ invulnerable
  save through shared runtime hooks. Chaos Knights Harbingers of Dread supports
  battle-round Dread selections/rolls, Deathly Terror/Despair Leadership auras,
  Dismay forced below-starting Battle-shock tests, Delirium D3 mortal wounds,
  Doom wound modifiers, and the Darkness Stealth hit modifier through shared
  runtime hooks. Delirium mortal-wound Feel No Pain continuation is deferred
  and emits a typed unsupported event without applying wounds. Thousand Sons
  Cabal of Sorcerers supports Shooting-start Ritual selection, Psychic tests
  with optional Channel the Warp perils, Destiny's Ruin hit rerolls, Temporal
  Surge movement proposals and charge lockout, Doombolt mortal wounds, and Twist
  of Fate AP modifiers through shared decision, movement, reroll, and
  mortal-wound routing paths. Tyranids Shadow in the Warp and Synapse support
  once-per-battle either-Command-phase activation, forced enemy Battle-shock
  tests, Synapse 3D6 Battle-shock tests, Shadow Synapse-range penalties, and
  melee Strength modifiers through shared hooks. Broad datasheet,
  wargear, weapon, and remaining faction execution remains later Phase 17 work.
- Matched-play mustering supports Incursion, Strike Force, and Onslaught battle
  sizes, including the Drukhari `Corsairs and Travelling Players` ally rule for
  HARLEQUINS and ANHRATHE units. Player-provided roster artifacts load through
  a strict JSON boundary into the same `ArmyMusterRequest` path, require an
  explicit Force Disposition, and validate declared per-unit and total points
  against a source-identified MFM package before mustering. Artifact unit-array
  order is the repeated-datasheet pricing order; source-backed unit and
  Enhancement/Upgrade point records plus the MFM package identity remain
  authoritative through the mustered army. Historical game result metadata is
  optional so the same schema represents ordinary pre-game lists.
- Drukhari `Power from Pain` runtime support includes a deterministic Pain token
  ledger, token gain at the owning Command phase start, enemy Battle-shock
  failures, and enemy unit destruction, plus Lithe Agility empowerment for
  Advance and Charge rerolls and Hatred Eternal selected-to-shoot and
  selected-to-fight hit-reroll empowerment through shared grant and dice-reroll
  decision paths.
- Local CLI/human decision entry, viewer-safe catalog/live unit-model projection,
  and trigger opportunity-window intent support are documented in
  [docs/ADAPTER_DECISION_CONTRACT.md](docs/ADAPTER_DECISION_CONTRACT.md) and
  [docs/TRIGGER_OPPORTUNITY_WINDOWS.md](docs/TRIGGER_OPPORTUNITY_WINDOWS.md).
- Official source evidence lives in `docs/source_rules`,
  `data/source_manifests`, `data/raw/faction_packs`, and generated source
  package artifacts. Runtime engine code must consume structured descriptors,
  not raw PDFs, CSV rows, HTML, or prose parsing.
- `tools/lookup_39k_reference.py` builds kind-specific HTTPS discovery paths
  and verifies complete 11th Edition faction, detachment, and datasheet URLs
  for 39k PRO. These links are secondary references only; official GW artifacts
  and hashes remain authoritative provenance. Reviewed provider observations may
  be retained as assignment-level evidence under `data/source_audits/39k_pro`,
  but no provider content is loaded by the runtime.
- README milestone anchors retained for code-quality audits: Phase 14H is complete;
  Phase 14I is complete; Phase 14K is complete; Phase 17A.1 is complete.
  Phase 14H anchors: runtime Attached Unit formation; structured army-list Leader/Support declarations; first-class attached rules-unit formation records; healing, revival, persisting effects; Movement-phase Combat Disembark fallback with engine-owned evidence; setup-time Strategic Reserve declarations; repositioned-unit Advance/Fall Back/Disembark history.
  Source-linked model geometry still requires a representative model height with provenance
  before runtime catalog use.

When a phase status changes, update the focused status document or contract
for that subsystem instead of turning this README into a changelog.

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
PATH="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:${PATH}" uv run pytest -n auto --dist=worksteal tests/
uv run --no-sync python scripts/build_test_shards.py --check --shard-count 4
uv run lint-imports
uv run pre-commit run --all-files
```

and these invariants are enforced by tests:

- broad exceptions fail the gate;
- raw model access in physical modules fails the gate;
- dice rolls require labels;
- dice replay round-trips;
- event/decision serialization contains no memory-address reprs.
