# Mission Implementation Status

This document tracks the repository's current source and engine status for the
Warhammer Event Companion primary mission matrix and the 11th Edition secondary
missions. It is a tracker, not a source of rules text.

Canonical structured source data lives in versioned artifacts and typed source loaders:

- Primary mission matrix cells:
  [`event_primary_mission_matrix_source_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
  and
  [`primary_mission_matrix_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
- Primary scoring coverage:
  [`primary_mission_scoring_coverage_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
- All 25 Primary scoring records and the ten source-backed Primary Mission Action
  descriptors:
  [`primary-scoring.json`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06_artifacts/primary-scoring.json),
  loaded by
  [`event_companion_primary_scoring_2026_06.py`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_primary_scoring_2026_06.py)
- Mission-card scoring grammar:
  [`mission_card_scoring_grammar()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)
- Secondary mission source rows:
  [`secondary_mission_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/chapter_approved_2026_27.py),
  imported by the Event Companion mission pack
- Mission action rows:
  [`mission_action_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/chapter_approved_2026_27.py)
  and
  [`primary_mission_action_source_rows()`](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py)

When any source row, engine support, or scoring policy changes, update this file
in the same PR.

## Status Legend

Primary matrix status:

- `implemented`: the matrix cell, primary mission identity, and three layout IDs
  are represented in the Event Companion mission pack.

Primary scoring status:

- `engine_implemented`: source scoring rows exist and the current engine can build
  a scoring policy for that primary mission.
- `source_known_engine_pending`: source scoring rows exist, but one or more
  required engine condition, marker, action, or choice semantics are still
  missing. These paths must remain fail-closed.
- `awaiting_source`: the mission is known from the matrix, but scoring source text
  is not represented yet.

Secondary status:

- `source_tracked`: the secondary card identity and source scoring rows are in the
  mission source package.
- `policy_loaded`: fixed and tactical scoring rows import into
  `MissionScoringPolicy`.
- `state_backed`: the current engine has concrete evidence handling for the
  listed condition family.
- `generic_condition`: the current source row uses a generic
  `fixed_secondary_condition` or `tactical_secondary_condition`; card-specific
  achievement detection still needs focused source and engine work before it can
  be treated as fully implemented.
- `source_only_rows`: exact card branches or When Drawn/definition rows are
  tracked in source data with non-policy `secondary` source kind. They are not
  imported into `MissionScoringPolicy` until the required engine evidence,
  choices, and adapter-visible payloads exist.

## Summary

- Primary matrix cells: 25 of 25 `implemented`.
- Primary scoring coverage: 25 of 25 `engine_implemented`, 0
  `source_known_engine_pending`, 0 `awaiting_source`.
- Phase 17N Step 4 exposes all ten source-backed Primary Mission Actions:
  `decoy-objective`, `triangulate-objective`, `extract-intelligence`,
  `surveil-enemy-unit`, `sensor-sweep-locate-and-deny`,
  `sensor-sweep-extract-relic`, `commit-sabotage`, `secure-asset`,
  `vanguard-operation`, and `maintain-control`.
- Phase 17N Step 5A routes every ordinary and end-of-battle Primary scoring
  boundary through the shared `score_primary_objective_control_boundary` path
  and immutable, content-addressed `PrimaryScoringStateEvidence`. The bridge
  authenticates the stored objective-control record and carries Primary
  mission progress, assigned Primary Action history, battlefield-departure
  history, exact frozen unit-destruction history membership, and current
  group-aware rules-unit positions with replay-safe hash and context validation.
  The aggregate derives all historical and spatial
  inputs from authoritative `GameState`; award-bearing evidence is persisted
  by objective-control record and ordinary/end-of-battle boundary kind, and
  live or restored Primary VP rows must resolve their ID/hash to that registry.
  Restore proves the frozen Action, progress, departure, destruction-history,
  and component sets are complete against authoritative history, rejects future/stale chronology and
  non-final end-of-battle claims, and keeps full rows replay-only rather than in
  viewer-scoped projections.
  It also implements four simple source-backed objective predicates.
- Phase 17N Step 5B scores consecrated, decoy, and triangulated markers through
  the shared generic condition path and `PrimaryScoringStateEvidence`. Consecrate,
  Smoke and Mirrors, and Triangulation are now `engine_implemented`.
- Phase 17N Step 5C scores completed Primary Mission Actions through the same
  shared path. Secure Asset, Sabotage, and Vanguard Operation are now
  `engine_implemented`. Gather Intel and Extract Relic remain pending on remaining
  marker-state blockers.
- Phase 17N Step 5D scores condemned enemy units that fully left the battlefield
  this turn, including during the opposing player's turn while condemned status
  lasts until the start of the Punishment owner's next turn. The condemned rule
  uses `timing: turn_end` with `turn_scope: any_player_turn`. Punishment is now
  `engine_implemented`. Counts after Step 5D were 20/5 missions and 11/15
  pairings (33/45 variants).
- Phase 17N Step 5E scores operation markers through the shared generic
  condition path. Gather Intel, Extract Relic, Locate and Deny, and Vital Link
  are now `engine_implemented`. Counts after Step 5E were 24/1 missions and
  14/15 pairings (42/45 variants). Pairing-wide certification is not claimed.
- Phase 17N Step 5F scores the Surveil the Foe surveilled-marker exception
  through the same shared path, resolving historical Attached Unit targets onto
  current descendant position witnesses through persisted departure lineage.
  Surveil the Foe is now `engine_implemented`.
  Counts are 25/0 missions and 15/15 pairings (45/45 variants).
- Phase 17N Step 5G certifies every Force Disposition pairing through
  `LocalGameSession` turn-end Primary scoring in both ordinary scoring
  directions, `GameLifecycle` and event-log restore round-trips, and
  viewer-scoped projections that omit full scoring-state evidence rows.
  Layout A of each pairing is the lifecycle certification row; all 45 A/B/C
  variants instantiate two-sided scoring policies. Layouts B and C are not
  lifecycle-certified. This does not capture a `ReplayArtifact` or run
  `ReplayRunner`. This does not claim Phase 20A full-game certification.
- Runtime Mission Actions: 14 total. The ten Step 4 Primary Actions join Death
  Trap's `booby-trap-terrain`, Terraform's `terraform-objective`, Cleanse's
  `cleanse-objective`, and Plunder's `plunder-terrain`. They are automatically
  exposed before Shooting-unit selection only when the active player owns the
  applicable Primary or Secondary.
- Secondary missions: 18 `source_tracked` and `policy_loaded`.
- Secondary scoring rows: 4 fixed policy rows, 20 tactical policy rows, and 28
  source-only branch/procedure rows.
- Tournament fixed secondaries: 4 cards are flagged as fixed-allowed
  (`A Grievous Blow`, `Assassination`, `Bring It Down`,
  `Engage on All Fronts`).

## Battlefield Coverage

- Phase 17N has source-hashed executable battlefield packages for all 45 Event
  Companion layouts: all 15 Force Disposition pairings and each pairing's A/B/C
  variants. No layout identity remains geometry-pending.
- All 15 of the 15 two-sided Force Disposition pairings now have executable
  Primaries in both directions, covering 45 of the 45 A/B/C layout variants.
  Step 5G certifies each pairing through both players' ordinary scoring
  boundaries, lifecycle and event-log restore round-trips, and viewer-scoped
  projections. Layout A is the lifecycle row; A/B/C remain inventory coverage.
- The local [Event Companion Battlefield Viewer](BATTLEFIELD_VIEWER.md)
  consumes `battlefield-view-v4-phase17n-step3` directly for every layout. It provides
  an orbitable 3D schematic of classifications, component footprints, walls,
  floors, source-linked objective terrain-area footprints, deployment zones,
  territories, and No Man's Land. Objective identity records remain labels and
  never become inferred marker disks or selectable solids. The viewer never
  falls back to legacy source-row rectangles or image-derived guesses.
- The battlefield contact semantics come from the page-8 Layouts Key, and the
  45 layout diagrams and coordinates are extracted from pages 9-53 of
  `eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf`, whose
  SHA-256 is
  `97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20`.
  Territory boundaries are reviewed against the attacker/defender triangle
  glyphs on all 45 pages rather than inferred from the horizontal or vertical
  battlefield middle guides.
  The reviewed page-8 key plus pages-9-53 layout extraction SHA-256 is
  `a3e9392adeb52696902a016e3c3529933d1e99f3bfd67069d607410d8e1c137f`,
  the generated artifact SHA-256 is
  `028670e0b1d965b7be90a95ba76f6bc74e7e26d3d1fd93b3dbf9e76e105d9b7f`,
  and its canonical package hash is
  `44ed73534435ab9fc10062024ecb92222898f8aeb0bdf54bd434582a58357972`.
  The generator separately pins the stable runtime identity map at
  `742ab841d1ec1e696f4a5c0e3f2e8c251203d510bf1da85fb30af88023cb64f3`.
  The generated `event-companion-battlefields.json` artifact records source
  affines, objective coordinates and bindings, deployment zones, territories,
  No Man's Land, typed Single/Separate terrain-area contacts, and component
  contacts. Its strict loader pins source, extraction, package, and artifact
  hashes and rejects malformed, stale, or re-hashed coordinate drift.
- The package contains 720 physical terrain-area footprint pieces representing
  608 logical rules areas, plus 1,349 individually placed physical components.
  Every layout has 16 footprint pieces. The page-8 key makes 112 two-piece pairs
  into Single logical areas; the remaining 496 pieces are singletons. Page 9,
  Take and Hold versus Take and Hold Layout A, has the source-backed 29-component
  exception because one downed hovercraft has no tall-crate companion; every
  other layout has 30 components. Fourteen shared archetypes define recurring
  component footprints and wall/floor geometry once for reuse throughout the
  package.
- Source terrain-area anchors and component battlefield centers use a
  0.05-inch placement grid. Reviewed mirror placements, asymmetric local
  transforms, and source-indicated area/component contacts remain explicit
  structured data.
  Objective centers retain the source vector extraction's finer 0.01-inch
  precision rather than discarding source accuracy at the terrain-placement
  boundary.
  Every declared contact retains at most one 0.05-inch placement quantum of
  source-fit gap and at most `0.000001` square inches of numerical overlap. Of
  224 declared contacts, 43 have zero recorded gap and 181 retain a source-fit
  open sliver no wider than 0.05 inches: 80 Single and 101 Separate. Of those
  43 zero-gap contacts, 41 also have zero overlap. Two page-12 Single pairs
  have `0.00000087` square inches of overlap after six-decimal geometry
  quantization; every other pair has zero recorded overlap. Single
  contacts share one logical rules identity; Separate contacts remain distinct.
  Neither identity fills source-drawn open board between physical polygons. The
  artifact records every measured runtime gap and overlap.
- Page 29's two paired contacts are the only terrain-area pose witnesses that
  require either adjustment axis to exceed the usual +/-0.20-inch
  canonical-footprint bound. Exhaustive
  evaluation of all four source-pose candidates on the 0.05-inch grid found no
  non-overlapping contact solution through +/-0.30 inches; +/-0.35 inches is
  the first feasible bound. The committed minimum-total corrections are area
  02 `(+0.10, -0.35)`, area 04 `(-0.10, +0.30)`, area 13
  `(+0.05, -0.35)`, and area 15 `(-0.05, +0.30)` inches. The loader permits
  exactly those four reviewed witnesses and retains the 0.20-inch bound for
  every other non-Meatgrinder area.
- Seven component rasters land across their rules-area boundary after source
  quantization. Exhaustive 0.05-inch-grid searches pin only the minimum
  containment corrections: page 23 areas 08 component 03 `(0, -0.05)` and 09
  component 02 `(0, +0.05)`; page 29 areas 04 component 01 `(-0.10, 0)`, 07
  component 01 `(0, +0.05)`, and 13 component 01 `(+0.05, -0.05)`; page 38 area
  02 component 01 `(0, -0.05)`; and page 45 area 02 component 01 `(0, -0.05)`
  inches. Source centers and rotations remain separate provenance fields. All
  84 non-Meatgrinder long-pipe rules proxies use the nearest feasible 0.05-inch
  grid center of their parent footprint because the source raster intentionally
  overhangs that rules area.
- Pages 36 and 46 repeat one Single-area ruin join whose shared rules proxies
  cannot close on the 0.05-inch grid. Exhaustive searches through +/-0.30
  inches prove the minimum exact normal correction is
  `(+0.005440361094, +0.010510105572)` inches, magnitude
  `0.011834688335` inches, applied only to area 10 after its reviewed grid
  placement. The source 0.05-inch anchors remain unchanged in provenance. Four
  source-ID-bound area-pose witnesses form two paired joins: page 36
  `disruption-vs-disruption-layout-1` areas 07 and 10, and page 46
  `reconnaissance-vs-reconnaissance-layout-2` areas 07 and 10. Only the two
  area-10 rows carry the sub-grid delta from `(-0.20, +0.10)`, so their effective
  runtime anchors use 12-decimal precision. This closes both Single joins with
  zero gap and zero overlap without weakening geometry tolerances.
  Intentional clearance between physical terrain and terrain-area edges is
  preserved, as required by the source, rather than treated as missing geometry.
- All 25 Primary missions' source timing, VP values, structured condition
  tokens, current engine-support status, and the ten source-backed Primary Mission
  Action descriptors are committed in `primary-scoring.json`. Its package hash
  is `8358cc11078b27e8773f58182e40bbf6194c54c3bda16b3aa1e286ee9b646dd1`
  and its raw artifact SHA-256 is
  `4783a4013a485cc4e6ef1669be2c12c19fa44e5175a5a220c17809b8a54774b7`.
  The typed loader pins both hashes, the exact 25-mission/100-rule/10-action
  inventory, the exact nine-token timing vocabulary plus rule-level `turn_scope`, the complete resolution
  group grammar, and the honest 25 `engine_implemented` versus 0
  `source_known_engine_pending` boundary. Repository reviews are pinned to PRs
  #107, #134, #136, and #379. PR #107 is the source-backed origin for Death
  Trap, Immovable Object, and Unstoppable Force. Only Meatgrinder currently
  retains canonical scoring prose; the other cards retain reviewed structured
  transcriptions, and the official card binaries are not committed. The
  GDMissions Meatgrinder transcription and image remain non-official secondary
  corroboration only.
- The artifact also pins the committed official Event Companion v1.1 PDF hash
  `97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20`
  and exact scoring-limit pages. Printed page 2 applies a 15VP Primary limit per
  battle round to every Event Companion Primary mission; printed page 4 states
  that end-of-battle VP is outside that limit. Accordingly, every one of the 25
  Primary rows carries `max_vp_per_turn: 15` (the historical field name is a
  battle-round cap), and cumulative awards share that round bucket. The
  end-of-battle exemption requires a matching assigned scoring-rule ID and the
  final-round Fight-phase `TURN_END` objective-control record; a caller-provided
  timing string is insufficient. The same validator runs for live awards and
  restored ledgers, including ordinary per-round Primary-total validation. The
  derived Event Companion source identity is
  `5a4dcccfa86bbecc8ded95275c39ee5401ce0e27e5f426c28ae4575e02114812`.
- Verify that the committed battlefield artifact still matches its reviewed
  inputs without writing files with
  `uv run python tools/build_event_companion_battlefields.py --check`.
- Completing all battlefield packages does not by itself promote Primary
  Mission scoring.   The eight Step 2 promotions are backed by generic runtime
  timing/resolution and objective, territory, table-quarter, destruction, and
  turn-history evidence. Purge and Secure is the thirteenth executable Primary,
  backed by objective-at-turn-start destruction history and exact-kill
  friendly-source objective occupancy. Step 5B then promotes Consecrate, Smoke
  and Mirrors, and Triangulation on marker scoring evidence. Step 5C then
  promotes Secure Asset, Sabotage, and Vanguard Operation on completed-action
  evidence. Step 5D then promotes Punishment on condemned-departure evidence.
  Step 5E then promotes Gather Intel, Extract Relic, Locate and Deny, and
  Vital Link on operation-marker evidence. Step 5F then promotes Surveil the Foe
  on the surveilled-marker exception. Battlefield pages are authority for layout
  facts, not mission-card scoring clauses.
- Component source-image placement and orientation come from reviewed
  source-page affine records. Ruin and non-ruin envelopes use dimensions rounded
  to the 0.05-inch grid and checked against the reviewed source-image spans.
  Component rules polygons and physical wall/floor primitives remain explicit
  engine models rather than traced raster silhouettes. Floor spacing, wall
  heights and thickness, simplified solids, and Dense non-ruin heights remain
  documented engine modeling assumptions; the PDF does not prescribe them.
- Rendering images remain non-authoritative. Runtime setup, movement, collision,
  visibility, and scoring consume the validated structured package, not a page
  image or a renderer-derived measurement.

## Mission-Card Scoring Grammar

The Primary artifact accepts exactly these timing tokens. "Command boundary"
means the mission pack's configured Primary scoring phase and objective-control
timing. Tokens that name round five are literal and are valid only for a
five-battle-round game, as configured by the current Event Companion package.

| Primary Timing Token | Authoritative Boundary |
| --- | --- |
| `command_phase` | Every configured Command boundary. |
| `turn_end` | Every relevant player-turn end. |
| `turn_end_from_battle_round_two` | Player-turn end in battle round 2 or later. |
| `command_phase_or_round_five_turn_end` | Configured Command boundary in battle rounds 2-4; player-turn end in battle round 5. |
| `end_of_battle` | The explicit end-of-battle boundary only. |
| `first_battle_round_turn_end` | Player-turn end in battle round 1 only. |
| `first_and_second_battle_round_turn_end` | Player-turn end in battle rounds 1 and 2 only. |
| `battle_rounds_two_and_three_command_phase` | Configured Command boundary in battle rounds 2 and 3 only. |
| `battle_round_four_onwards_turn_end` | Player-turn end in battle round 4 or later. |

| Official Rule Token | Source Status | Engine Contract |
| --- | --- | --- |
| `cumulative_condition` | `source_tracked`, `engine_implemented` | Every achieved branch in one typed cumulative group scores; selection evidence lists all achieved and selected rule IDs. |
| `exclusive_or_condition` | `source_tracked`, `engine_implemented` | Only the highest-VP achieved branch in one typed exclusive group scores; rule-ID ordering breaks equal-VP ties deterministically and evidence lists suppressed branches. |
| `exactly_one_condition` | `source_tracked` | Underlined one means exactly one, not one or more. |
| `leaves_battlefield_event` | `source_tracked`, `engine_implemented` | Typed battlefield-departure evidence records destroyed, embarked, and rule-removed models and rules units. Punishment scores when one or more condemned enemy rules units fully left the battlefield this turn. |
| `vp_up_to_limit` | `source_tracked`, `engine_guarded` | Rule caps and ledger caps ignore VP above the stated limit. |
| `when_drawn_tactical_only` | `source_tracked` | When Drawn sections apply only to Tactical Secondary Missions and must not affect Fixed Secondary mode. |

## Primary Mission Matrix

| Player Force Disposition | Opponent Force Disposition | Primary Mission | Mission ID | Matrix Status | Scoring Status | Rules | Actions | Needed Work |
| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |
| `purge-the-foe` | `purge-the-foe` | Meatgrinder | `primary-meatgrinder` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `purge-the-foe` | `take-and-hold` | Unstoppable Force | `primary-unstoppable-force` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `purge-the-foe` | `disruption` | Punishment | `primary-punishment` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `purge-the-foe` | `reconnaissance` | Consecrate | `primary-consecrate` | `implemented` | `engine_implemented` | 5 | 0 | None |
| `purge-the-foe` | `priority-assets` | Destroyer's Wrath | `primary-destroyers-wrath` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `take-and-hold` | `purge-the-foe` | Immovable Object | `primary-immovable-object` | `implemented` | `engine_implemented` | 3 | 0 | None |
| `take-and-hold` | `take-and-hold` | Battlefield Dominance | `primary-battlefield-dominance` | `implemented` | `engine_implemented` | 3 | 0 | None |
| `take-and-hold` | `disruption` | Determined Acquisition | `primary-determined-acquisition` | `implemented` | `engine_implemented` | 3 | 0 | None |
| `take-and-hold` | `reconnaissance` | Purge and Secure | `primary-purge-and-secure` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `take-and-hold` | `priority-assets` | Inescapable Dominion | `primary-inescapable-dominion` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `disruption` | `purge-the-foe` | Delaying Action | `primary-delaying-action` | `implemented` | `engine_implemented` | 3 | 0 | None |
| `disruption` | `take-and-hold` | Death Trap | `primary-death-trap` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `disruption` | `disruption` | Outmanoeuvre | `primary-outmaneuver` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `disruption` | `reconnaissance` | Smoke and Mirrors | `primary-smoke-and-mirrors` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `disruption` | `priority-assets` | Locate and Deny | `primary-locate-and-deny` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `reconnaissance` | `purge-the-foe` | Triangulation | `primary-triangulation` | `implemented` | `engine_implemented` | 5 | 1 | None |
| `reconnaissance` | `take-and-hold` | Reconnaissance Sweep | `primary-reconnaissance-sweep` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `reconnaissance` | `disruption` | Surveil the Foe | `primary-surveil-the-foe` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `reconnaissance` | `reconnaissance` | Gather Intel | `primary-gather-intel` | `implemented` | `engine_implemented` | 5 | 1 | None |
| `reconnaissance` | `priority-assets` | Search and Scour | `primary-search-and-scour` | `implemented` | `engine_implemented` | 4 | 0 | None |
| `priority-assets` | `purge-the-foe` | Vital Link | `primary-vital-link` | `implemented` | `engine_implemented` | 5 | 1 | None |
| `priority-assets` | `take-and-hold` | Secure Asset | `primary-secure-asset` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `priority-assets` | `disruption` | Extract Relic | `primary-extract-relic` | `implemented` | `engine_implemented` | 5 | 1 | None |
| `priority-assets` | `reconnaissance` | Vanguard Operation | `primary-vanguard-operation` | `implemented` | `engine_implemented` | 4 | 1 | None |
| `priority-assets` | `priority-assets` | Sabotage | `primary-sabotage` | `implemented` | `engine_implemented` | 3 | 1 | None |

## Secondary Missions

| Secondary Mission | Mission ID | Availability | Tournament Fixed | Fixed Rules | Tactical Rules | Other Rows | Status | Engine Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| A Grievous Blow | `a-grievous-blow` | `both` | Yes | 1 | 1 | 1 | `source_tracked`, `policy_loaded`, `state_backed`, `source_only_rows` | Tracks `each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn`; When Drawn discard row remains source-only |
| A Tempting Target | `a-tempting-target` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track opponent target selection and target control |
| Assassination | `assassination` | `both` | Yes | 1 | 1 | 4 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track W4+/W3-or-less Character branches and Tactical Character branches |
| Beacon | `beacon` | `tactical` | No | 0 | 1 | 3 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track beacon choice and outside-deployment/territory branches |
| Behind Enemy Lines | `behind-enemy-lines` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track first-round redraw and each-unit scoring |
| Bring It Down | `bring-it-down` | `both` | Yes | 1 | 1 | 1 | `source_tracked`, `policy_loaded`, `state_backed`, `source_only_rows` | Tracks `each_enemy_model_w10_or_more_destroyed_this_turn` with fixed and tactical caps; When Drawn discard row remains source-only |
| Burden of Trust | `burden-of-trust` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track guard selection and guarded-objective scoring |
| Centre Ground | `centre-ground` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track 3VP/5VP centre-distance branches |
| Cleanse | `cleanse` | `tactical` | No | 0 | 2 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks objective cleanse counts; runtime action `cleanse-objective` exists |
| Defend Stronghold | `defend-stronghold` | `tactical` | No | 0 | 2 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks home objective control and enemy absence from own deployment zone |
| Display of Might | `display-of-might` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track own-turn and opponent-turn No Man's Land unit-count branches |
| Engage on All Fronts | `engage-on-all-fronts` | `both` | Yes | 1 | 1 | 5 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track presence definition and fixed/tactical three-/four-quarter branches |
| Forward Position | `forward-position` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track first-round redraw and forward-objective control |
| No Prisoners | `no-prisoners` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `each_enemy_unit_destroyed_this_turn` |
| Outflank | `outflank` | `tactical` | No | 0 | 1 | 2 | `source_tracked`, `policy_loaded`, `source_only_rows` | `generic_condition`; source-only rows track one-edge and opposite-edge branches |
| Overwhelming Force | `overwhelming-force` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `each_enemy_unit_started_turn_in_range_of_objective_destroyed` |
| Plunder | `plunder` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks terrain plunder state; runtime action `plunder-terrain` exists |
| Secure No Man's Land | `secure-no-mans-land` | `tactical` | No | 0 | 1 | 0 | `source_tracked`, `policy_loaded`, `state_backed` | Tracks `control_two_or_more_no_mans_land_objectives_excluding_home` through objective-control records filtered to central/No Man's Land objectives |

## Runtime Caveats

- Event Companion primary matrix identities and all layout IDs are implemented.
  All 45 layout descriptors reference source-hashed executable battlefield
  packages. Geometry completion does not change the independently tracked
  Primary Mission scoring status.
- Meatgrinder's four source scoring rows are state-backed, including the
  comparison of enemy units lost during the current scoring player's turn
  against that player's friendly units lost during the opponent's immediately
  prior player turn, plus control of the opponent's home objective from battle
  round two. Scoring evidence records both resolved turn keys, both destruction
  counts and unit IDs, and the opponent-home objective IDs. Unit completion is
  recorded automatically through the shared destruction owner for shooting and
  fight attacks, mortal wounds, direct rule destruction, Desperate Escape,
  end-turn coherency destruction, and emergency-disembark model destruction.
  Reserve-deadline destruction occurs after the player turn has ended and is
  deliberately excluded from this cross-turn comparison. Generic current-turn
  enemy-loss conditions classify records by the destroyed unit's owner and
  active-turn key, so authoritative transition removals count even when no
  destroying player can be attributed.
- Primary rules use one strict nine-token timing evaluator plus a separate
  rule-level `turn_scope` of `own_player_turn` or `any_player_turn`. Every rule declares
  `independent`, `cumulative`, or `exclusive_highest` resolution. Cumulative
  groups emit every achieved award; exclusive groups emit only the highest-VP
  achieved award, use stable rule-ID ordering for equal-VP ties, and record the
  achieved, selected, and suppressed rule IDs in scoring evidence.
- The eight Step 2 Primaries use engine-owned evidence for current and
  start-of-turn objective control, opponent comparisons, objective roles,
  directed attacker/defender territory, complete attached-rules-unit model
  placement in table quarters, the six-inch center exclusion, turn-scoped unit
  destruction, start-of-turn terrain occupancy, and battle-end enemy absence
  from own territory. Objective-control records must cover the exact mission
  objective inventory and cannot contain unsupported rows. Missing spatial or
  turn-history evidence fails closed instead of scoring by assumption.
- Purge and Secure uses the same generic timing and exclusive-highest grammar,
  plus engine-owned destruction evidence for the destroyed enemy unit's exact
  start-of-turn objective membership and the friendly destroying rules unit's
  objective membership at the destruction event. Its two destruction branches
  cannot score together; the deterministic exclusive group selects one 3VP
  branch and records the suppressed branch when both are achieved.
- Each player-turn boundary records one authoritative, serialized rules-unit
  snapshot. Attached formations remain one rules unit, while nested component
  rows retain every physical unit, every evaluated model, intersected logical
  terrain areas, and the exact models within range of each objective marker.
  Automatic destruction copies the destroyed rules unit's terrain and objective
  unions from that exact turn snapshot. Empty tuples are explicit evidence, not
  missing data; missing snapshots, incomplete groups, unknown terrain/objectives,
  or mismatched model witnesses fail closed.
- Attributed destruction preserves the responsible player, rules unit, model,
  provenance, source `model_destroyed` event, and the source rules unit's exact
  objective-proximity witness at that event. Desperate Escape, emergency
  disembark, coherency, and reserve-deadline losses instead carry an explicit
  unattributed cause; the engine never invents an attacker. Destruction,
  Embark, and in-battle reserve transitions additionally feed one generic
  battlefield-departure history. Reserve-deadline losses were never on the
  battlefield and therefore do not create false departure occurrences.
- Army-list identities and battle-time historical rules-unit snapshots are
  public to both players, including an unplaced Strategic Reserve. Declare
  Battle Formations secrecy applies to the declaration choices before their
  reveal, not to roster/datacard identity. Public destruction events expose the
  same typed source and destroyed objective/model witnesses to each player and
  administrators because those are public battlefield facts.
- The new start-position, central-objective destruction, and battlefield-
  departure primitives are reusable by Locate and Deny, Extract Relic, and
  Punishment. Step 4 supplies their player choices, Mission Actions, and
  persistent operation/condemned-unit state. Punishment's condemned-departure
  scoring condition is now engine-implemented. Locate and Deny and Extract Relic
  scoring conditions are now engine-implemented through Step 5E operation-marker
  occupancy evidence.
- `source_known_engine_pending` primary missions must remain fail-closed until
  the listed card-specific scoring conditions have engine-owned validation and
  evidence paths.
- `decoy-objective`, `triangulate-objective`, `extract-intelligence`,
  `surveil-enemy-unit`, `sensor-sweep-locate-and-deny`,
  `sensor-sweep-extract-relic`, `commit-sabotage`, `secure-asset`,
  `vanguard-operation`, and `maintain-control` are source-backed runtime
  Mission Actions. They use the shared Shooting-phase decision path, generic
  use-limit and completion handling, and engine-owned persistent marker/action
  evidence. Step 4 also supplies the finite condemned-unit and marker-setup
  choices and Surveil the Foe's engine-owned move cleanup for enemy operation
  markers.
- Step 5A's scoring-state bridge and four simple objective predicates are
  complete. Step 5B promotes Consecrate, Smoke and Mirrors, and Triangulation
  through marker scoring conditions. Step 5C promotes Secure Asset, Sabotage,
  and Vanguard Operation through completed-action scoring conditions. Step 5D
  promotes Punishment through condemned battlefield-departure scoring. Step 5E
  promotes Gather Intel, Extract Relic, Locate and Deny, and Vital Link through
  operation-marker scoring. Step 5F promotes Surveil the Foe through the
  surveilled-marker exception. Step 5G certifies every Force Disposition pairing
  through both players' ordinary turn-end boundaries, lifecycle and event-log
  restore round-trips, and viewer-scoped projections. Layout A is the
  lifecycle/restore/viewer certification row; A/B/C remain in the fail-closed
  inventory and instantiate two-sided scoring policies.
- Secondary lifecycle support exists for source rows, fixed/tactical modes,
  tactical draw, scoring, retain/discard, Fixed card states that remain active
  after scoring, the 20 VP per Fixed Mission card cap, state-backed awards, and
  source-only branch/procedure rows. Individual card achievement semantics still
  need card-specific tests before moving from `generic_condition` or
  `source_only_rows` to `state_backed`.
