# T1 — Stratagem WHEN taxonomy

[Taxonomy index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Adapter decision contract](../../ADAPTER_DECISION_CONTRACT.md) · [T6 decision-kind taxonomy](T6_DECISION_KIND_VISIBILITY.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This survey is Track T item T1. It is planning evidence delivered read-only to
Track G's timing-window family. It does not implement engine semantics, add
`TimingTriggerKind` values, populate faction records, or admit content. FM0
regenerates Stratagem window rows from the retained content set and reconciles
them with this document.

Machine-readable window catalog: [`t1_when_windows.json`](t1_when_windows.json).

## 1. Purpose and delivery contract

T1 closes the Stratagem WHEN grammar that Track G must design against before
faction implementation maps every distinct Stratagem onto a timing window.

A Stratagem window is a composition, not a display-name match:

| Axis | Closed token set |
| --- | --- |
| Phase clauses | Ordered alternatives of `{turn_owner, phase, boundary}`. Owner is per clause and must not be lifted over the union |
| Turn owner | `your`, `opponent`, `either`, `any`, `unspecified` |
| Phase | `command`, `movement`, `shooting`, `charge`, `fight`, `any`, `turn`, plus optional `reinforcements_step` |
| Boundary | §3.2 |
| Event | `none` or a §3.3 event ID; unions of events are `event_set` |
| Envelope | finite `use_stratagem`, `ReactionWindow`, `OpportunityWindow`, `OutOfPhaseActionContext` |

The closed window set is those axes and tokens. Observed WHEN clauses are
assignments onto that set. Track G must not explode each observed combination
into its own enum member. A single `turn_owner` plus `phase_set` is not a
legal descriptor: "Your Shooting phase or the Fight phase" is `{your,
shooting}` or `{unspecified, fight}`, not `your` over `{shooting, fight}`.

The roadmap's previous "26 `TimingTriggerKind` values" is stale. The engine
enum has **27** members. This survey gaps against those 27 plus reaction and
opportunity envelopes.

**Track G implements typed window descriptors and engine-owned emission only.**
It must not add speculative trigger kinds from this gap list without a real
source-backed consumer in the same PR. Existing Core Stratagem consumers stay
on their current kinds until a later order remaps them.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Listing inventory | 2,520 Stratagem table rows in `docs/factions/audit/` (inherited repeats included) |
| Retained WHEN corpus | Phase 17S activation profiles dated 2026-06-21: 1,025 rows, 1,002 names, 173 detachments, 23 factions, **236** distinct `when_descriptor` strings |
| Core WHEN | Live [15.00 Stratagems](https://www.40k.app/rules/15-stratagems) fetched for this survey; Core package `when_text` is incomplete (six rows, including a FAQ question and Snap Shooting) |
| Operative samples | Live [War Horde](https://www.40k.app/factions/orks/detachments/war-horde) and [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion) Stratagem WHEN clauses |
| Engine inspection | Read-only: `TimingTriggerKind` (27), `ReactionWindow`, `OpportunityWindow`, `OutOfPhaseActionContext`, adapter `use_stratagem` |

September audits store Name / CP / baseline only. They have no WHEN column.
Per-Stratagem App 946 WHEN assignment over the expected ~1,400 distinct
Stratagems after S2 is therefore **S3a / FM0**, not this survey. T1 still
closes the window *set*: every retained WHEN clause, every Core 15 Stratagem,
and the App 946 samples classify onto §3.

This document does not copy bulk operative text. Sampled clauses are paraphrased
and linked. Exact transcription remains an F00/S3a obligation.

The activation-profile `trigger_kind` field is a heuristic from
`tools/generate_faction_stratagem_activation_support.py` (`_trigger_kind`).
Event phrases are matched first; `"end of"` becomes `end_phase`; **everything
else defaults to `start_phase`**. This survey counts that assignment and the
re-read of `when_descriptor`. It does not change the generator.

## 3. Closed window set

### 3.1 Phase clauses (owner per alternative)

Each alternative in a WHEN head is one phase clause `{turn_owner, phase,
boundary}`. Owner is read from that alternative, not from the Stratagem's
effect and not from the first alternative alone.

`Fight phase.` and `Command phase.` with no "your" / "opponent" are
`unspecified` (either player's matching phase). `Any phase` is `any`.
`Either player's turn; Fight phase` is `either` on the turn clause and
`unspecified` on Fight.

Unions keep every clause's owner. Flattening to one `turn_owner` plus a
`phase_set` is T1-001 and is invalid:

| WHEN head (paraphrased) | Legal clauses | Illegal flatten |
| --- | --- | --- |
| Your Shooting phase or the Fight phase | `{your, shooting}` or `{unspecified, fight}` | `your` + `{shooting, fight}` |
| Your opponent's Shooting phase or the Fight phase | `{opponent, shooting}` or `{unspecified, fight}` | `opponent` + `{shooting, fight}` |
| Your Movement phase or your Charge phase | `{your, movement}` or `{your, charge}` | same owner is still a clause list |

Retained mixed-owner rows: **159** (25 distinct descriptors). Dominant patterns:
opponent Shooting or unspecified Fight (85); your Shooting or unspecified Fight
(71). Same-owner multi-clause rows: 17 (your Movement or your Charge is 12).

The activation profiles' stored `phase_tokens` still collapse those unions
(156 `shooting`+`fight`, 14 `movement`+`charge`) and do not store per-clause
owner. FM0 must not copy that collapse. Track G descriptors carry a clause
list. A single `BattlePhaseKind` cannot represent the union.

### 3.2 Boundaries

| Boundary ID | WHEN shape | Engine kind today |
| --- | --- | --- |
| `during_phase` | `[owner] [phase].` with no event | `during_phase` exists; profiles store `start_phase` |
| `start_phase` | `Start of [owner] [phase]` | `start_phase` |
| `end_phase` | `End of [owner] [phase]` | `end_phase` |
| `event_in_phase` | phase plus `just after` / `when` event | event kind, not the phase boundary |
| `end_turn` | `End of your opponent's turn` | `end_turn` exists; profiles store `end_phase` |
| `command_battleshock_step` | Battle-shock step of Command | none; Insane Bravery currently uses Command `start_phase` |
| `fight_step` | Fight step of the Fight phase | none; Counter-offensive can use `after_unit_attacks_resolved` plus metadata |
| `before_reinforcements_step` | Movement phase, before Reinforcements | none |
| `start_reinforcements_step` | Start of the Reinforcements step | none |
| `during_reinforcements_step` | The Reinforcements step of Movement | none |
| `end_reinforcements_step` | End of the Reinforcements step | none |

`start_of_any_phase`, `end_of_any_phase`, `start_of_any_phase_excluding_command`,
and `end_of_any_of_your_phases` are `any` / `your` owners on those boundaries,
not extra boundary IDs.

Whether a substep is `source_step` metadata on an existing kind or a new kind
is T1-HOLD-SUBSTEP-VS-KIND. Track G must pick one representation with a real
consumer; this survey forbids inventing both.

### 3.3 Events

`none` means the window is the phase boundary alone.

| Event ID | Engine `TimingTriggerKind` | Coverage on the 2026-06-21 profiles |
| --- | --- | --- |
| `none` | phase boundary only | 616 |
| `selected_as_target` | `after_unit_selected_as_target` | 179; includes "selected its targets", "selected ts targets", and "when an enemy unit targets" |
| `ends_fall_back_move` | `just_after_friendly_unit_falls_back` or `after_enemy_unit_ends_move` | 39 |
| `has_shot` | `just_after_friendly_unit_has_shot` / `just_after_enemy_unit_has_shot` | 35 |
| `ends_normal_advance_or_fall_back` | `after_enemy_unit_ends_move` | 32 |
| `unit_destroyed` | `after_unit_destroyed` | 23 stored as `start_phase` |
| `ends_charge_move` | `after_unit_ends_charge_move` | 16 |
| `declares_charge` | **none** | 10 |
| `mortal_wound` | **none** | 9; suffers or is allocated a mortal wound, without naming an attack |
| `selected_to_fall_back` | `just_after_enemy_unit_selected_to_fall_back` | 6 |
| `model_destroyed_deadly_demise` | `after_model_destroyed` | 6 stored as `start_phase` |
| `just_before_consolidate` | **none** | 5 |
| `has_shot_or_fought` | union of shot/fought kinds | 4 |
| `attacks_resolved` | `after_unit_attacks_resolved` | 4 stored as `just_after_enemy_unit_has_fought` |
| `has_fought` | `just_after_enemy_unit_has_fought`; friendly has-fought has **no** kind | 3 |
| `just_after_advance` | **none** | 3 |
| `attack_allocated` | **none** | 2; THIEVES OF PAIN and PROTECTION OF THE DARK PRINCE (`event_set` with `mortal_wound`) |
| `finished_making_attacks` | nearest `after_unit_attacks_resolved` | 2; GUIDED DISRUPTION, SHOCK BOMBARDMENT |
| `selected_to_shoot` | `just_after_friendly_unit_selected_to_shoot` | 2 |
| `selected_to_fight` | `just_after_friendly_unit_selected_to_fight` | 2 |
| `selected_to_advance` | **none** (not `selected_to_move`) | 2 |
| `just_before_advance` | **none** | 2 |
| `unit_destroyed_before_remove` | `after_unit_destroyed` plus before-remove / Deadly Demise ordering | 2 |
| `battle_shock_test_failed` | **none** | 2 |
| `once_per_battle_ability_used` | **none** | 2 |
| `cult_ambush_marker_move` | **none** (`after_enemy_unit_ends_move` is the wrong event) | 2 |
| `dice_roll` | `after_dice_roll` | 1 faction row; Core Command Re-roll is the primary consumer |
| `starts_charge_move` | **none** | 1; SINGLE-MINDED STRIKE |
| `just_before_surge_move` | **none** | 1; SYNAPTIC GOADING |
| `psychic_test_before_ritual` | **none** | 1; ARCANE FOCUS |
| `charge_targets_before_move` | **none** | 1 |
| `unit_set_up` | `model_placed_on_battlefield` | 1 stored as `start_phase` |
| `ends_normal_move` | **none** for a friendly unit; enemy uses `after_enemy_unit_ends_move` | 1 |
| `disembark` | **none** | 1 |
| `psychic_finished` | **none** | 1 |
| `just_before_pile_in` | **none** | 1 |
| `just_before_bondsman` | **none** | 1 |
| `malefic_surge` | **none** | 1 |
| `contract_complete` | **none** | 1 |
| `before_detachment_rule_targets` | **none** | 1 |
| `enemy_ends_move_generic` | `after_enemy_unit_ends_move` if the move is a battlefield move | 1 |

`attack_allocated` is a WHEN event, not an effect clause. Many Stratagems
subtract Damage "each time an attack is allocated" in the EFFECT after
`selected_as_target`; those remain `selected_as_target`. THIEVES OF PAIN and
PROTECTION OF THE DARK PRINCE fire in any phase just after an attack or a
mortal wound is allocated. That is not `mortal_wound` alone.

Live App 946 / Core 15 events still **absent** from the June profile counts
(true zeros):

| Event ID | Sample | Engine kind |
| --- | --- | --- |
| `selected_to_move` | War Horde Fungus-fuel Injection: your Movement phase, when a friendly unit is selected to move | `just_after_friendly_unit_selected_to_move` (unused by June profiles) |
| `becomes_battle_shocked` | War Horde Breakin' Heads | **none** |
| `before_battle_shock_roll` | Core Insane Bravery, Battle-shock step | **none** |

Do not treat "selected to Advance" as `selected_to_move`. The June heuristic
looks for the substring `selected to move` and therefore missed Advance
selection and the App 946 "when … is selected to move" War Horde row (the
Orks rewrite post-dates the extract).

### 3.4 Envelopes (not extra trigger kinds)

Stratagem *use* stays `use_stratagem` (or a parameterized Stratagem target
proposal) in [the adapter contract](../../ADAPTER_DECISION_CONTRACT.md).
T1 names the WHEN envelope. Finite versus parameterized target binding is
T6. Reaction and opportunity types wrap that decision; they do not replace
it.

| Envelope | When T1 assigns it |
| --- | --- |
| Finite `use_stratagem` | Active player, own-turn or unspecified phase, no opponent-only reaction |
| `ReactionWindow` (`eligible_player_ids`, `blocks_parent`) | Opponent-owned phase, or an event on an enemy unit (selected as target, enemy has shot/fought, enemy ends a move, Fire Overwatch / Rapid Ingress / Heroic Intervention at opponent phase end) |
| `OpportunityWindow` | Shared payload around mixed legal actions (`stratagem`, `ability`, `reroll`, `reaction`, `side_action`, `pass`). Command Re-roll is still `use_stratagem` at `after_dice_roll` |
| `OutOfPhaseActionContext` | Fire Overwatch (and other out-of-phase shooting) after the Stratagem is accepted |

Corsair Coterie extra selected-to-move / selected-to-shoot windows already
emit `use_stratagem` without a new decision type. Track G generalizes that
pattern; it does not add a Corsair-named trigger.

## 4. Profile coverage and heuristic mis-maps

1,025 activation profiles classify onto **107** distinct
`(phase_clauses, event)` tuples, where `phase_clauses` is the ordered list of
`{turn_owner, phase, boundary}` alternatives. That tuple count is an
observation, not a kind budget. The previous flatten to one `turn_owner` plus
`phase_set` produced 102 tuples and hid the 159 mixed-owner rows.

Assigned `trigger_kind` histogram (heuristic, not the taxonomy):

| Stored kind | Rows |
| ---: | ---: |
| `start_phase` | 660 |
| `after_unit_selected_as_target` | 178 |
| `end_phase` | 77 |
| `after_enemy_unit_ends_move` | 38 |
| `just_after_enemy_unit_has_shot` | 27 |
| `after_unit_ends_charge_move` | 15 |
| `just_after_friendly_unit_has_shot` | 10 |
| `just_after_enemy_unit_selected_to_fall_back` | 7 |
| `just_after_enemy_unit_has_fought` | 4 |
| `just_after_friendly_unit_falls_back` | 4 |
| `just_after_friendly_unit_selected_to_fight` | 3 |
| `just_after_friendly_unit_selected_to_shoot` | 1 |
| `after_dice_roll` | 1 |

Bare phase heads that dominate the extract: Fight phase (144), Your Shooting
phase (143), Your Movement phase (99), opponent Shooting (86), opponent
Shooting or Fight (82), Your Shooting or Fight (65), Any phase (58), Your
Command phase (56).

**Default-`start_phase` mis-map.** 133 profiles store `start_phase` while the
descriptor names an event (destruction, mortal wounds, declared charge,
Reinforcements, Fall Back, Advance, pile-in, consolidate, and others). All 32
destruction descriptors store `start_phase` even though `after_unit_destroyed`
and `after_model_destroyed` exist. All 58 "Any phase" heads store kinds other
than `any_phase` (54 of them `start_phase`).

Transcription noise in the extract (not extra windows): `orthe Fight phase`,
`selected ts targets`, missing apostrophes. FM0 must not treat those as
distinct families.

## 5. Core 15 mapping

Live [15.00](https://www.40k.app/rules/15-stratagems). Snap Shooting (15.09) is
a shooting type, not a Stratagem.

| Stratagem | WHEN shape | Taxonomy | Current engine note |
| --- | --- | --- | --- |
| Command Re-roll | Any phase, just after one of the listed rolls | `any` + `event_in_phase` + `dice_roll` | `after_dice_roll`; finite `use_stratagem` |
| Epic Challenge | Fight phase, just after a friendly CHARACTER unit is selected to fight | `unspecified` + `fight` + `selected_to_fight` | `just_after_friendly_unit_selected_to_fight` |
| Insane Bravery | Battle-shock step of your Command phase, just before a Battle-shock roll | `command_battleshock_step` + `before_battle_shock_roll` | shipped as Command `start_phase`; gap vs current App |
| Crushing Impact | Your Charge phase, just after a friendly MONSTER/VEHICLE ends a charge move | `your` + `charge` + `ends_charge_move` | `after_unit_ends_charge_move` |
| Explosives | Your Shooting phase | `your` + `shooting` + `during_phase` + `none` | treat as `during_phase`, not start-of-phase |
| Rapid Ingress | End of your opponent's Movement phase | `opponent` + `movement` + `end_phase` | `end_phase` reaction |
| Fire Overwatch | End of your opponent's Movement phase | same boundary; `ReactionWindow` + `OutOfPhaseActionContext` | `end_phase` |
| Smokescreen | Start of your opponent's Shooting phase | `opponent` + `shooting` + `start_phase` | P15A owns the current-App remap |
| Heroic Intervention | End of your opponent's Charge phase | `opponent` + `charge` + `end_phase` | `end_phase` |
| Counter-offensive | Fight step of your opponent's Fight phase, just after an enemy unit has resolved its attacks | `fight_step` + `attacks_resolved` | nearest kind `after_unit_attacks_resolved` / `just_after_enemy_unit_has_fought` |

## 6. App 946 samples versus the June extract

[Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion)
WHEN shapes match the extract: Any-phase destruction before removing the last
model and before Deadly Demise; bare Fight / Command / Shooting; start of
opponent Charge; end of opponent Fight.

[War Horde](https://www.40k.app/factions/orks/detachments/war-horde) is an Orks
v946 rewrite (F-ORK-01). It adds shapes the June extract does not count:
selected to move, selected to shoot, selected to fight, becomes Battle-shocked,
and "when an enemy unit targets" as `selected_as_target`. Track G must keep
`just_after_friendly_unit_selected_to_move` even though June profiles never
stored it.

## 7. Gap list against the 27 kinds

### 7.1 Kinds the retained WHEN corpus needs but profiles do not store

These kinds exist and should be used when FM0 maps Stratagems:

`during_phase`, `any_phase`, `end_turn`, `after_unit_destroyed`,
`after_model_destroyed`, `model_placed_on_battlefield`,
`after_unit_attacks_resolved`, `just_after_friendly_unit_selected_to_move`.

### 7.2 Kinds with no Stratagem demand in retained WHEN

`passive_query`, `before_battle`, `after_battle`, `start_turn`,
`start_battle_round`, `end_battle_round`.

Army rules already use some of these (for example battle-round and turn
boundaries). T1 does not delete them. Track G must not add Stratagem rows
that gate on them without source WHEN.

### 7.3 WHEN shapes with no kind

Demand for Track G, each requiring a real consumer before a new kind exists:

- Command Battle-shock step and just-before Battle-shock roll (Insane Bravery).
- Fight step as distinct from the Fight phase (Counter-offensive).
- Reinforcements-step start / during / end / before.
- Mortal-wound suffered or allocated (Any phase), distinct from `attack_allocated`.
- Attack allocated, including the Any-phase `event_set` with mortal-wound allocation (THIEVES OF PAIN, PROTECTION OF THE DARK PRINCE).
- Unit destroyed before removing the last model / before Deadly Demise.
- Friendly unit has fought / finished making its attacks.
- Charge declared, charge targets selected before the move, starts a Charge move.
- Just before Advance, pile-in, consolidate, Bondsman, or Surge move; just after a friendly Advance.
- Friendly unit ends a Normal move; disembark after a Transport Normal move.
- Becomes Battle-shocked; enemy fails a Battle-shock test.
- Once-per-battle ability used; psychic ability or Psychic test before a Ritual.
- Enemy move relative to Cult Ambush markers.
- Detachment-owned hooks (Malefic Surge, completed Contract, before selecting Detachment-rule targets).
- Multi-event unions (`has shot or fought`, `attack_allocated` with `mortal_wound`) as `event_set`, not a new enum member per pair.

Union **phases** are a list of phase clauses with owner preserved on each
clause. Union **events** are `event_set`. Do not add `shooting_or_fight` as a
`TimingTriggerKind`, and do not lift one turn owner over the list.

## 8. Engine gaps this survey is not fixing

| Gap | Current behavior | Owner |
| --- | --- | --- |
| Heuristic default `start_phase` | 660/1,025 profiles; destruction and Any-phase events mis-tagged | S3d / FM0 remap from retained WHEN |
| `during_phase` unused by profiles | Bare "Your Shooting phase." stored as `start_phase` | Track G + FM0 |
| `after_unit_destroyed` unused by profiles | Spiteful Demise-class WHEN stored as `start_phase` | Track G + FM0 |
| Selected-to-move unused by profiles | Engine kind exists; App 946 War Horde uses the shape | Track G (already emitted for some consumers) |
| Insane Bravery substep | Engine Command `start_phase` vs App Battle-shock step | remaining Core P15 / Track G with that consumer |
| Incomplete Core `when_text` | Six package rows; FAQ question stored as WHEN | P15 source records, not T1 |
| No WHEN in September audits | 2,520 listing rows without a WHEN column | S3a |

## 9. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| T1-HOLD-APP-WHEN | App 946 WHEN text is not retained for every distinct Stratagem | S3a, then FM0 demand-matrix rows |
| T1-HOLD-PROFILE-STALENESS | 1,025 profiles dated 2026-06-21; 40 admitted views at App-data 946; Orks rewrite is later | S3a / S3d |
| T1-HOLD-SUBSTEP-VS-KIND | Reinforcements, Battle-shock step, Fight step: metadata versus new kinds | Track G with a real consumer |
| T1-HOLD-UNION-PHASE | Clause-list versus exploding kinds; owner stays on each alternative | Track G; T1 forbids exploding and forbids a lifted `turn_owner` |
| T1-HOLD-INSANE-BRAVERY-STEP | Current App WHEN versus shipped Command start | Core P15 remainder or Track G remap |
| F-ORK-01 | War Horde and other Orks Stratagem WHEN may be new at v946 | FM0.5 |

## 10. What "T1 delivered to Track G" means

Track G's timing-window family may be designed. It has:

- the closed axes (phase-clause list with owner per alternative, event,
  envelope);
- the event and boundary catalogs, including which existing kinds they bind
  and the `attack_allocated` family;
- the gap list against all **27** `TimingTriggerKind` values plus reaction and
  opportunity envelopes;
- Core 15 and sampled App 946 confirmation that selected-to-move and
  becomes-Battle-shocked remain in the set;
- the heuristic mis-map so FM0 does not trust stored `trigger_kind`;
- the hold that per-Stratagem counts wait on S3a.

T1 does not add enum values, change activation profiles, or emit
`semantic_demand_matrix.json`. FM0 regenerates that matrix from retained
pages and reconciles it with this survey.
