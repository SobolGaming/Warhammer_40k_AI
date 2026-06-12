# warhammer40k-core-v2

Strict bottom-up Warhammer 40k engine reconstruction.

Start here:

```bash
uv python install 3.14.5
uv lock
uv sync
uv run pytest
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
  tests/
    fixtures/
    unit/
    integration/
    replay/
    code_quality/
```

Dependency direction:

```text
core     -> no project-layer imports
geometry -> may import core, not engine/adapters
rules    -> may import core and descriptors, not adapters
engine   -> may import core, geometry, rules
adapters -> may import engine, never the reverse
```

## 4. Build order

The CORE V2 build order roadmap now lives in [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md).

Current roadmap implementation status: phases 1-15F, phases 16A-16E, and
Phases 17A-17F plus Phase 17J are complete. Phase 14E is
complete: its allocation-group host includes Benefit of Cover and Plunging Fire
BS modifiers, ordered InSv-then-armour Save resolution with no save-kind adapter
choice, automatic allocation groups, defender ordered allocation decisions only
for legal same-tier group choices, grouped fixed-damage save-before-damage
resolution, current group transitions, low-to-high failed-save damage ordering,
normal-damage-before-routed-mortal ordering, grouped-host Precision/Lethal
Hits/Sustained Hits/Devastating Wounds revalidation, derived terrain objectives
that require terrain-area containment rather than marker-radius contribution,
melee Cleave dice gathering, and Lance charge-gated Wound-roll modifiers through
the Phase 15 Charge/Fight host. Phase 14F completes the shooting-type cutover
with finite shooting-type selection, supported grouped attack resolution,
Normal/Assault/Close-quarters/Indirect/Snap routing, Indirect and Snap Hit-roll
reroll bans, and the Shooting-phase Mission Action start lock. Phase 14G
completes the Charge/Fight source contract as typed ruleset descriptor payloads
and deferred unsupported Core Stratagem hooks. Phase 14H is complete for the
current transport/reserve plus attached-unit attack/healing projection slice:
runtime Attached Unit formation uses structured army-list Leader/Support declarations
against catalog attachment eligibility, emits first-class attached rules-unit formation records,
derives attached-unit Starting Strength until
split, and feeds source-backed Bodyguard/Leader/Support evidence used by
Shooting acting-unit selection, mixed-Toughness attacks, healing, revival, persisting effects,
and stratagem target canonicalization. Phase 16D now completes the strict
army-construction records that those runtime hosts consume: Warlord,
Enhancement, roster-legality, Dedicated Transport manifest provenance, and
the source army-definition data from which `GameState` derives
`StartingStrengthRecord` entries. Phase 14H also covers
Movement-phase Combat Disembark fallback with engine-owned Tactical-invalid
evidence, Combat/Emergency hazard rolls through the official 1-2 Hazard Roll
threshold and shared mortal-wound/Feel No Pain service, destroyed-Transport
Emergency Disembark from actual destruction timing before Transport removal and
Deadly Demise, setup-time Strategic Reserve declarations and battle-formation
Transport embarkation, repositioned-unit Advance/Fall Back/Disembark history and
persisting effects, exact At Half-strength replay payload state, and runtime
added-unit Starting Strength records. Phase 14I is complete for the current Core
Stratagem and core ability source cutover: all 11th Edition Core Stratagem source
rows have supported handlers, implemented duplicate weapon ability selection is
adapter-visible and replay-safe, and unimplemented Core ability families are
fail-closed as explicit unsupported descriptors. Phase 14J completes the current
mission/catalog replacement slice with source-tracked 11th Edition Force
Dispositions, the named 25-cell Primary Mission matrix, three layout identifiers
per matrix cell, and engine-achievement-gated finite Tactical Secondary
score/retain decisions; exact 11th Edition Secondary card identities beyond
current source rows, Primary Mission scoring text, and layout geometry remain
pending source work. Phase 14K is complete: attack/save cutover hardening
rejects retired save/allocation decision surfaces, grouped Inflict Damage uses defender
`select_damage_allocation_model` decisions with pre-pop stale-legality rejection,
old Aircraft minimum-move/pivot runtime policy is removed, reserve arrivals use
Move Units records and more-than-8" enemy spacing, and source/audit coverage
rejects retired Core Stratagem names.

Phase 14L and Phase 15A-F are complete for ranged attack grouping, charge declaration/roll/movement, Fight phase activation/pass/interrupt ordering, Pile In/Consolidate proposal routing, melee declarations that reuse the shared Making Attacks sequence, source-backed Heroic Intervention, Counteroffensive, Crushing Impact, and Epic Challenge Stratagem handling, and Charge/Fight completion gates that drain pending phase work before completion.

Phase 16A is complete for source-backed Deploy Armies. The lifecycle now creates an empty source-backed battlefield at Create Battlefield, deploys units through `select_deployment_unit` and `submit_deployment_placement`, validates deployment zones, `INFILTRATORS`, terrain/objective/engagement/coherency endpoints, attached rules-unit model sets, reserves exclusion, stale/malformed submissions, and deterministic replay-safe placement events without using the Phase 10A deterministic bridge.

Phase 16B is complete for redeployments, Scouts, and pre-battle ability resolution. Setup now exposes redeploy and pre-battle finite decisions, uses Phase 12A sequencing when both players have simultaneous pre-battle effects, validates redeploy and Scout reserve setup as typed placement proposals, validates Scout Move proposals with per-model `PathWitness` evidence and shared pathing/terrain/coherency checks, derives `Scouts X"` distances from structured datasheet ability descriptors, applies the official Scouts duplicate-distance rule, records deterministic `PreBattleActionRecord` payloads, and keeps Scout moves out of Movement phase action state. Current catalog ability ownership is datasheet/component-granular; future per-model catalog ownership can narrow mixed-model Scouts eligibility without changing the adapter proposal path.

Phase 16C is complete for reserve declarations during Declare Battle Formations. Setup now exposes `select_reserve_declaration`, records Strategic Reserves and Deep Strike setup choices through lifecycle decisions, enforces source-backed Strategic Reserves points caps and FORTIFICATION exclusions, records AIRCRAFT mandatory reserves as ordinary `ReserveState` payloads, rejects stale reserve submissions before queue pop, and excludes declared reserves from Deploy Armies options.

Phase 16D is complete for source-backed army construction and runtime instantiation. Strict roster requests now validate Strike Force unit points plus selected Enhancement points, unit limits, Warlord selection, Enhancement assignment rules, attached-squad Enhancement limits, Epic Hero restrictions, required Dedicated Transport manifest source data, and provided Dedicated Transport cargo legality with deterministic `RosterLegalityReport` diagnostics. Production `GameConfig` values require strict mustering requests by default; legacy smoke fixtures must opt into `allow_legacy_non_strict_rosters`. Mustered armies preserve Warlord, Enhancement, unit-point, Dedicated Transport, and legality provenance in JSON-safe payloads, promote the selected Warlord with a `WARLORD` keyword, and setup records starting embarked cargo from source-backed manifests before Deploy Armies while explicit empty Dedicated Transport manifests become deterministic setup consequences that exclude the transport from deployment and mark it destroyed in battle round 1. `GameState.record_army_definition(...)` derives the `StartingStrengthRecord` set consumed by later phases.

Phase 16E is complete for setup completion gates. Setup-to-battle transition is now engine-owned: the lifecycle audits drained decision and reaction queues, final setup-step position, source-backed mission and army readiness, Secondary Mission choices, attacker/defender state, reserve declarations, deployment completion, battlefield coherency, and unresolved redeploy/pre-battle actions before battle round one can start. Legal completion emits deterministic setup legality, replay checkpoint, and battle-start payloads; invalid setup returns typed `setup_completion_gate_failed` diagnostics and remains in setup without using the Phase 10A deterministic placement bridge.

Phase 17A is complete for the bridge Wahapedia source mirror and CSV-to-JSON ETL. Source snapshots and package manifests now preserve checksums, upstream identity, source date, source-edition identity, deterministic artifact hashes, source-row provenance, HTML sanitization reports, structured source-text normalization, runtime-field HTML exclusion, and grouped malformed-row diagnostics. The source mirror remains ingest/catalog tooling only; engine runtime is statically blocked from importing raw source mirror or sanitizer modules.

Phase 17A.1 is complete for official 11th Edition transition patch packages.
Transition patches now preserve official source package identity, source date,
faction ID, normalized instruction text, stable source IDs, deterministic
operation ordering, exact or explicit multi-row source targets, target-drift
diagnostics, FAQ classification, unsupported executable-change diagnostics, and
patched source artifact hashes. Rule-text replacement and append operations
rerun HTML sanitization, structured normalization, and parsed-token generation,
profile and weapon characteristic replacements update exact source fields, and
engine runtime is statically blocked from importing transition patch tooling.

Phase 17B is complete for canonical 11th Edition catalog generation from patched
source data. Catalog packages now preserve deterministic datasheet, model,
wargear, weapon, faction, detachment, enhancement, Stratagem, physical geometry,
support-base, z-offset, representative-height, source-unit, canonical-unit,
coordinate-frame, origin, and source-evidence records, and unresolved geometry or
height evidence blocks package emission instead of falling back to runtime
heuristics.

Phase 17C is complete for the rule-language intermediate representation.
Normalized source text now compiles into deterministic, source-spanned, versioned
`RuleIR` payloads with reusable template IDs, typed trigger/condition/target/effect/duration
components, explicit unsupported diagnostics, stable IR hashes, and a static
runtime boundary that keeps engine code from importing parser/compiler tooling.

Phase 17D is complete for generic rule execution handlers. Compiled `RuleIR`
clauses now execute through registered generic handlers for modifiers, reroll
permissions, VP and CP resource changes, Stratagem target binding, and Aura
recomputation from current battlefield positions. Unsupported IR fails closed as
typed unsupported results, source-linked execution events are deterministic and
JSON-safe, and ability/Stratagem bridges can execute replay-safe compiled IR
payloads without importing parser/compiler/template tooling.

Phase 17J is complete for Warhammer Event Companion v1.0 mission-pack
compliance and source geometry inventory. The source package now records Event
Mission Sequence ordering, Tactical/Fixed Secondary procedures, all 25
implemented Primary Mission matrix cells, all 45 source-page layout identities
with pending coordinate-extraction status, no Deployment/Twist card usage,
separate empty card-amendment and FAQ patch records, Base Size Guide source rows
with geometry-resolution statuses, Event Companion mission-pack import,
setup/scoring pack lookup, deployment remainder-drain coverage, and a static
audit that runtime code does not parse Event Companion PDF text or images.

Phase 17E is complete for source-backed faction coverage. The
`gw-11e-phase17e-faction-coverage-2026-27` package validates every official
faction-pack PDF manifest record, links every seeded faction to an army-rule
coverage descriptor, links every seeded detachment to detachment rule,
enhancement, and Stratagem descriptor coverage, and emits deterministic coverage
totals grouped as implemented, generic-supported, named-handler-required, and
unsupported. Exact datasheet-intake rows, enhancement subrows, and Stratagem
subrows that are absent from the update PDFs are fail-closed as approved
unsupported diagnostics, keeping broad datasheet, wargear, and weapon execution
in Phase 17H.

Phase 17F is complete for faction execution dispatch and status over every
Phase 17E coverage row. The
`gw-11e-phase17f-faction-execution-2026-27` package maps every Phase 17E
coverage descriptor to an execution record, and
`engine/faction_rule_execution.py` provides one deterministic engine path that
returns replay-safe results. Current faction army-rule, detachment-rule,
enhancement, Stratagem, and datasheet-intake rows are blocked by explicit
approved execution reasons until native structured rule semantics exist.
Executable statuses also fail closed unless a registered generic IR executor or
named handler runs; APPLIED is not emitted by status alone, and no covered row
falls through as a missing handler or silent fallback.

Phase 17G is planned for actual faction-level semantic execution: army rules,
detachment rules, enhancement effects, and faction/detachment Stratagem timing,
targeting, validation, and effects. Phase 17H is planned for datasheet, wargear,
and weapon ability execution. Phase 17I is planned for source-content coverage,
execution-status, and unsupported-descriptor audits.

Official GW faction-pack PDFs and extracted whole-source text/page files are local-only validation inputs. Do not commit them or put them in Git LFS; commit source manifests, official URLs, retrieval metadata, hashes, page/section references, structured patch operations, diagnostics, and generated catalog artifacts instead. The Phase 17 faction-pack source manifest uses the official Warhammer 40,000 downloads page at `https://www.warhammer-community.com/en-gb/downloads/warhammer-40000/` as its shared source page.

Phase 17B catalog generation source-links physical model geometry.
`Use model`, blank, `No official base size`, bare `Hull`, flying-base, and
other non-circular/non-oval model footprints require reviewed geometry override
records before runtime instantiation. Each unique model profile must carry a
representative model height with provenance so LoS, vertical distance, and
multi-floor terrain collision do not depend on runtime heuristics.

Adapter, UI, CLI, headless, network, AI, replay, and test-driver teams should use [docs/ADAPTER_DECISION_CONTRACT.md](docs/ADAPTER_DECISION_CONTRACT.md) for the shared Phase 11D decision/proposal submission contract plus Phase 11E viewer-scoped scoring projection/event rules.

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
uv run mypy src tests
uv run pyright
uv run pytest
uv run lint-imports
uv run pre-commit run --all-files
```

and these invariants are enforced by tests:

- broad exceptions fail the gate;
- raw model access in physical modules fails the gate;
- dice rolls require labels;
- dice replay round-trips;
- event/decision serialization contains no memory-address reprs.
