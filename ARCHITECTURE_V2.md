# CORE V2 architecture status

This file is the build-order map for the Warhammer 40,000 CORE V2 engine. It records which product phases have landed and which are still ahead. It is current as of `main` `55780340` ([PR #503](https://github.com/SobolGaming/Warhammer_40k_AI/pull/503), Order 83).

Read it with the two remediation roadmaps:

- [Core Rules remediation](docs/CORE_RULES_REMEDIATION_ROADMAP.md) owns categories 01–25. A landed phase here is not a compliance claim. Orders 1–83 are merged. `PFINAL` is Order 84 and is open. `CAUDIT-01` is open.
- [Faction rules remediation](docs/FACTION_RULES_REMEDIATION_ROADMAP.md) owns in-scope factions, detachments, Enhancements, Upgrades, Stratagems, and datasheets. Faction implementation waits on Gate 0, which is core `PFINAL`.

CORE V2 is 11th Edition only. Do not add edition-diff switches or dual-edition behavior unless repository policy changes.

## What has been built

The engine lifecycle is authoritative. Players, AI, UI, network, and replay go through `DecisionRequest`, `DecisionResult`, and `DecisionRecord`. Runtime code executes typed descriptors. Replay payloads are deterministic and fail closed on drift. Unsupported rule shapes stay explicit.

These build slices have landed. Later core-remediation orders replace the rules behavior where the two disagree; the core roadmap is the authority for that replacement.

| Area | Phases | What landed |
|---|---|---|
| Foundation | 0–9D | Governance, dice, modifiers, normalization, wargear, geometry, units, visibility and pathing, battlefield descriptors, decisions, lifecycle, mustering |
| Movement and setup primitives | 10A–10V | Movement, reserves, transports, aircraft foundation, coherency, terrain, movement completion |
| Command, missions, adapter scaffold | 11A–11F | Mission-pack data, objective control, Command phase, parameterized proposals, scoring, game end |
| Timing and core abilities | 12A–12D | Timing windows, CP ledger, Core Stratagem framework, ability registry |
| Shooting | 13A–13F, 14E, 14F, 14L | Visibility and cover foundation, attack sequence, weapon abilities, shooting completion, grouped ranged attacks |
| Cutover | 14A–14G, 14I–14K | 11th Edition source identity, phase skeleton, primitives, movement and objectives, attack allocation, shooting types, Charge/Fight source contract, Core Stratagem source closeout, mission and catalog slice, hardening audits |
| Charge and Fight | 15A–15F | Declaration, charge movement, fight order, Pile In and Consolidate, fight Stratagems, completion gates |
| Battle setup | 16A–16E | Deployment, redeploy and Scouts, reserve declaration, army construction, setup completion |
| Source and catalog | 17A–17F, 17J, 17O | Wahapedia bridge, transition patches, catalog generation, RuleIR, generic execution, faction coverage and dispatch, Event Companion source package, capability manifest |
| Adapters | 18A–18C, 18E–18J, 18L, 18M-A | CLI, replay, session facade, reference server protocol, concurrency, event stream, viewer security, interaction metadata, battlefield coordinates, durable sessions, first conformance client |

Phase 17A.1 is complete. The status row the repository audits require:

| Phase | Status | Purpose |
|---|---:|---|
| 17A.1 | Complete | Official 11th Edition transition patch packages, deterministic patched artifacts, target diagnostics, and FAQ classification |

Phase 14H is complete for runtime Attached Unit formation from structured army-list Leader/Support declarations, first-class attached rules-unit formation records, and the transport and healing slice recorded below. Phase 14I is complete for the Core Stratagem and core-ability source closeout. Phase 14K is complete for cutover hardening.

## What is partial or still ahead

| Phase | Status | Remaining work |
|---|---|---|
| 17G | Existing slices | Selected faction army, detachment, Enhancement, and Stratagem execution exists. Certification is the faction roadmap after Gate 0, not an extension of these slices |
| 17H | Planned | Datasheet, wargear, and weapon-ability execution |
| 17I | Planned | Source-content coverage and unsupported-descriptor audit |
| 17M | Planned | Generic semantic coverage by mechanic family |
| 17N | Partial | Battlefield geometry, all 25 Primary Missions, and all 18 Secondary cards on Layout A are in place. Secondary lifecycle certification for Layouts B and C, and the Phase 20A setup-to-terminal matrix, are open |
| 18D | Partial | Versioned schema and OpenAPI baseline. Some decision families are `envelope_only` until later interaction and conformance work |
| 18K | Planned | Interface intent and opportunity UX |
| 18M-B+ | Planned | Remaining decision-family, race, golden-corpus, persistence, and Phase 20A conformance |
| 19A–19F | Planned | Performance budgets, legal-action masking, AI policy, self-play, training data, observability |
| 20A–20D | Planned | Certified vertical slice, full-game regression, soak, and the 11th Edition release gate |

Phase 17E and Phase 17F coverage rows and the execution dispatcher are loaded. Rows without a registered executor stay typed unsupported results. That is not faction playability. Phase 17O reports capability evidence; the faction status artifact that should feed it is still FM0 in the faction roadmap.

## Source authority

The Core Rules source policy is `core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`. It recognizes 40k.app and Game Datamissions as non-affiliated maintained App-data mirrors. They are not Games Workshop. Live mirror sites are not runtime inputs. `RuleEvidenceRecord` and `RuleSourcePackage` validate provider, URL, version or timestamp, transcription hash, and observation fingerprint against the packaged source-authority registry. The core roadmap owns how those observations close rules findings.

## Rules that stay in force

1. Raw rule text is normalized once at the data boundary. Runtime code does not parse it.
2. Missing or unsafe rules, terrain, abilities, and decisions return typed unsupported or invalid results.
3. CLI, UI, network, and AI answer decisions. The engine validates and mutates state.
4. Datasheets, geometry, factions, detachments, Enhancements, Stratagems, missions, and terrain come from catalog and source packages.
5. CORE V1 is a reference. Port the smallest reviewed behavior only after CORE V2 tests exist.
6. State changes that affect play are replay-facing and deterministic.
7. Headless performance stays a product requirement. Deferred full-game budgets are not treated as passed.
8. The service contract is versioned and transport-neutral. HTTP, long polling, SSE, and WebSocket do not create different command or event semantics.
9. Viewer identity is server-derived. Client-supplied viewer or actor IDs are not authorization.
10. Mutating commands carry a client command ID and expected session revision.
11. Simulation order comes from decision, event, and revision records, not transport timestamps.

## Retained phase-contract records

The headings below are the phase records repository audits still check. They describe the slice that landed. Where a core-remediation order later changed the rule, the [core roadmap](docs/CORE_RULES_REMEDIATION_ROADMAP.md) wins.

## Phase 14H: advanced rules cutover

Status: Complete.

Phase 14H is complete for this slice. Runtime Attached Unit formation uses structured army-list Leader/Support declarations and emits first-class attached rules-unit formation records. Broader real-faction Leader/Support eligibility data remains later catalog work. The landed slice includes setup-time Strategic Reserve declarations, battle-formation Transport embarkation, and repositioned-unit Advance/Fall Back/Disembark history. Movement-phase Combat Disembark fallback now accepts Combat mode only when the pending placement proposal advertises that fallback and the engine first proves the same submitted placement is invalid as Tactical Disembark. Healing Wounds primitive now iterates each healing amount in order, heals wounded models before revived returns, and validates revived placement against Starting Strength, phase-start coherency, removed-model identity, and engagement restrictions.

Assault Disembark, Shock Disembark, empty Dedicated Transport timing, embark locks, and Rapid Disembark inheritance are core-remediation orders on top of this slice.

## Phase 14I: Core Stratagems and core abilities cutover

Status: Complete.

Phase 14I is complete for the Core Stratagem and core-ability source closeout. Implemented handlers execute through the ability registry or phase-owned hosts. Families that were still unimplemented at this closeout remain explicit unsupported descriptors with owning phase IDs. This section does not mark later runtime effects complete. The future ability-runtime families from that closeout keep their owning-phase tests and adapter updates in the core roadmap rather than in this record.

## Phase 14K: cutover hardening and static audits

Status: Complete.

Phase 14K is complete. Cutover hardening rejects retired save and allocation choice surfaces, retired aircraft minimum-move and pivot-limit runtime paths, a 9" reserve-arrival enemy-distance policy, separate Reinforcements-step placement records, retired Core Stratagem source names, and stale grouped Inflict Damage model selections before queue pop.

## Phase 17A.1: official 11th Edition transition patch packages

Status: Complete.

Phase 17A.1 is complete. Official faction update instructions are structured patch packages applied to the normalized bridge source mirror. The layer emits `PatchedSourceArtifact` payloads with source and package hashes, deterministic row payloads, and typed target-drift diagnostics for unresolved, ambiguous, stale, malformed, advisory-only, and unsupported executable paths.

FAQ classifications are `advisory_only`, `executable_patch`, and `unsupported_executable_change`. Executable FAQ changes are patch operations or unsupported diagnostics. Text replacement and append operations rerun normalization before catalog generation. Engine runtime does not import the patch tooling.

## Phase 17B: canonical 11th Edition catalog generation from patched source data

Status: Complete.

Phase 17B generates the canonical 11th Edition catalog from patched source artifacts. Datasheets, profiles, wargear, keywords, factions, detachments, Enhancements, and Stratagems are source-linked catalog records. The Wahapedia bridge is tooling only.

Geometry rules that still govern catalog generation:

- CORE V1's `data/model_geometry_overrides.json` is reference material for the override shape. The implementation does not port a runtime fallback resolver.
- Rows with `Use model`, a blank base size, `No official base size`, bare `Hull`, Base Size Guide `hull` or `unique`, or an unresolved non-circular or non-oval footprint need a source-linked override before physical geometry emission.
- Flying-base models keep the published support base separate from the rules footprint. A flying-base override records support base, body or hull footprint, optional stem or z-offset, representative height, rules-footprint policy, and provenance.
- runtime engine code consumes only accepted catalog geometry. It does not infer hull dimensions from base size.
- Every unique model profile has a representative model height with provenance. Line of sight, vertical engagement, and multi-floor collision use that height through `ModelGeometry`.

Phase 17J can preserve unresolved Base Size Guide rows for roster and event legality. Those rows stay blocked from movement, line of sight, engagement, deployment, and collision until accepted geometry evidence exists.

## Phase 17C: rule language intermediate representation

Status: Complete.

Normalized source text compiles to versioned `RuleIR` with source spans, template IDs, typed trigger, condition, target, effect, and duration components, and explicit unsupported diagnostics. Engine runtime does not import the parser or compiler. Generic execution is Phase 17D. Faction certification does not start from these templates; it starts after Gate 0 in the faction roadmap.
