# Order 93 source and consumer inventory

This is the targeted implementation inventory for P02I/C02-09, not the final
all-clause Core Rules certification in Order 95. It records the consumers and
producer families inspected, rather than treating membership in
`ModifierIgnoreKind` as proof of gameplay coverage.

## Source boundary

The pinned `core_modifiers_2026_09/artifacts/package.json` contains
`gw-11e-core-modifiers:ignore-individual-modifiers`, Core 02.02.02,
transcription SHA-256
`7c1439a4548907e7648e50c665cab0bfb7e0cf9eb3e92d82ccb453fda838a2a0`.
Its default permission covers unit rolls and unit profile/weapon
characteristics; stated restrictions narrow that coverage. Individual effects
remain selectable regardless of whether their numeric sign is beneficial.
`gw-11e-core-modifiers:ordered-modifiers` and
`gw-11e-core-modifiers:modified-dice-limits` continue to own arithmetic and bounds
after selection.

The September 24 inventory retains Core 01.05.04 as
`rule:01:01.05.04:1`, source SHA-256
`a5605596c8e09097c1451f3ca07febf8528051db9d194bd5e88c8416f1b977c3`, in
[`data/source_audits/order84/audit.json`](../data/source_audits/order84/audit.json).
That artifact deliberately retains hashes, not the operative text. This audit
does not claim to have reconstructed that missing transcription or certified
equivalence to a newly fetched page. The registered 02.02.02 transcription is
the executable permission evidence used here.

`gw-11e-core-random-characteristics:random-characteristics`, Core 02.02.03,
distinguishes a random characteristic's intrinsic expression from later
modifiers (expressly including the operator in a Damage characteristic).
Selecting modifier operations must preserve original dice and intrinsic values.

## Delivered selection owners

Paths below are relative to `src/warhammer40k_core/engine/`.
Every row uses `modifier_evaluation.py` and the same finite decision,
before-pop validation, source inventory, lifecycle continuation and replay
authority. Permission discovery is `catalog_modifier_ignore.py`, including
catalog ownership and applicable persisted `GRANT_ABILITY` effects.

Persisted attack restrictions are evaluated with the actual attacker, defender,
subject role, phase, weapon and available resolved Strength/Toughness. That
context is retained in the request and reconstructed for before-pop validation,
pending restoration and replay. Unit/model beneficiary scope is separate from
which model makes the attack. Pre-declaration and non-attack boundaries lack a
unique attack context; restricted grants needing those missing facts produce an
explicit unsupported-context diagnostic. Strength/Toughness comparisons are
likewise unsupported before both characteristic owners have resolved their
values. Defensive source-unit Starting/Half Strength restrictions are explicitly
unsupported until a separate permission source unit can be authenticated; the
enemy attacker must not stand in for that source. These limitations are distinct
from a correctly evaluated nonmatching
target or role. See R93-001 in the [repair evidence](performance/order93/r93_001/README.md).

| Subject | Owner and source/producer inventory |
| --- | --- |
| Movement, Advance, Charge | `movement_modifier_evaluation.py`; movement/charge phase owners and reaction continuations. Catalog Maulerfiend permission, catalog Charge modifiers, generic IR effects and faction runtime bindings preserve separate operations. Choices belong to the movement/charge occurrence. |
| Weapon Range and Attacks | `weapon_modifier_selection.py`; Shooting requests/declaration, melee selection/commitment and target replacement. `rule_ir_weapon_modifiers.py`, fixed/random profiles, damaged Attacks and Orks/Astra Militarum/Chaos Daemons producers preserve operations. Range choices precede legality; Attacks choices precede count commitment; changed target-dependent inventories re-enter the owner. |
| BS, WS and hit rolls | `attack_modifier_evaluation.py:select_hit_modifiers`; runtime, catalog and generic IR terms, cover, Plunging Fire and weapon skill traces. The Psychic permission remains restricted to BS/WS/hit, source `gw-11e-core-modifiers:psychic-individual-modifiers`. |
| Strength, target Toughness and wound rolls | `attack_modifier_evaluation.py:select_wound_modifiers`; profile/runtime/generic terms and the source-linked Lance term. Target model characteristics use defender ownership. |
| AP, Sv, InSv and saving throws | `attack_save_modifier_selection.py`; AP profile operations, `save_modifier_operations.py`, generic/runtime save terms and separate inherent AP/cover saving-throw terms. InSv-only permission does not grant Sv permission. |
| Damage characteristic and damage rolls | `attack_damage_modifier_selection.py`; profile/runtime/generic operations and the catalog first-failed-save SET 0 replacement. Ignoring that first replacement still consumes its occurrence. |
| Leadership and Leadership/Battle-shock tests | `nonattack_modifier_evaluation.py`; per-model Leadership inventory and source-linked test terms, consumed by Battle-shock, fall-back-denial and command-point-test owners. A CP-generating Leadership test remains a unit roll even though its outcome grants a resource. |
| Objective Control | `objective_control_modifier_evaluation.py`; per-model profile/runtime/generic operations at objective-control refresh/scoring and the automatic Mission Action opportunity, before OC-dependent options are enumerated. The internal explicit request helper is not a separate adapter command. |
| Desperate Escape | `desperate_escape_modifier_evaluation.py`; ordinary Fall Back and forced Desperate Escape inventory, including Battle-shocked penalties from `core_movement_phase_2026_08` and catalog source terms. The catalog producer joins the force clause to sibling roll clauses in the authenticated complete RuleIR and preserves each effect separately; source evidence retains both individual terms and their checked sum. |
| Soulstealer healing trigger | `faction_content/warhammer_40000_11th/chaos_daemons/detachments/daemonic_incursion/soulstealer_sequencing.py`; `phase17f:phase17e:enhancement:chaos-daemons:daemonic-incursion:000008438003` explicitly adds 1 to the bearer's D6 in Shadow of Chaos. The existing completion candidate selects the `healing_roll` term before rolling or healing and resumes once. |

The Soulstealer audit found a real omitted roll producer and added its owner;
it is not classified as an intrinsic expression. The canonical facade
regressions in `tests/unit/test_order93_healing_modifiers.py` cover keep/ignore,
the pending choice before any healing die, one roll, restoration before and
after resolution, and reproduced replay. Weapon, movement, attack, save and
non-attack owner regressions are listed in the implementation scope and test
files rather than inferred from this table.

The independent review additionally traced the loaded Daemonic Icon Leadership
replacements on Bloodcrushers (`000001115:3`) and Plaguebearers (`000001132:3`).
Their source `SET 6` remains independent of other Leadership operations, and
source-bearer presence is evaluated across the relevant rules unit. These are
the Icon rows; the adjacent Instrument rows modify Charge. Evaluated random
Leadership and OC profiles preserve the original rolled value, full operation
inventory and previously ignored IDs through the same owner/history queries.

Source-local limits stay attached to their operation. Take Cover's Save
improvement and 3+ limit form one selectable negative addition; it remains in
the inventory when the native Save is already 3+ or better, so later opposing
effects do not lose it. The same representation preserves Scabrous Soulrot's
and Corsair Coterie Infamy's OC minimum of 1 without making that limit an
independently ignorable operation or imposing it on unrelated reductions.

`tests/unit/test_order93_mission_action_modifiers.py` drives the automatic
Mission Action opportunity through `LocalGameSession`: keeping both operations,
ignoring either sign, and ignoring a source SET 0. The latter retains the
original ADD operation even when SET 0 previously suppressed it. The cases
cover OC-dependent eligibility, Action start/decline, owner-only choices,
pending/completed restoration and exact replay. Checkpoint source joins retain
the full profile inventory as well as applied operations.

## Inspected boundaries with no current selectable operation

These are bounded conclusions about the inspected executable producers. They
do not prohibit a future source from modifying a roll in these families.

| Family | Source and consumer disposition |
| --- | --- |
| Wounds maximum/initialization | `random_wounds_initialization.py`, `random_profile_evaluation.py` and `catalog_model_materialization_runtime.py` consume the source W profile. No loaded executable source that adds/replaces W as a modifier was found in the faction source/producer inventory. `EnhancementCharacteristicModifier` is a generic executor type with no production constructor/provider; its existence and the W permission enum are not evidence of a delivered W choice. A future sourced W modifier needs an initialization/materialization choice owner before support is claimed. Healing and current wounds lost do not modify the W profile. |
| Feel No Pain | `damage_allocation.py:resolve_feel_no_pain_rolls` rolls a D6 against the selected ability's threshold; source grants such as Endless Gift (`phase17f:phase17e:enhancement:chaos-daemons:daemonic-incursion:000008438004`) grant FNP 5+. Source selection, declining an optional ability and a granted threshold are not roll modifiers. No executable source-linked FNP-roll arithmetic producer was found. |
| Hazard/Hazardous | `gw-11e-core-abilities:core:hazardous`; `hazard.py`, `attack_sequence_hazardous.py`, `hazardous_completion.py`. Current sources determine the number of physical-weapon hazard dice and failure threshold, then route mortal wounds. No sourced numeric modifier to those dice was found. Weapon-count changes and failure consequences are not roll modifiers. |
| Deadly Demise | `gw-11e-core-abilities:core:deadly-demise`; `deadly_demise.py` and `deadly_demise_modifiers.py`. Gateway Unto Damnation (`phase17f:phase17e:enhancement:chaos-daemons:blood-legion:000009815005`) expressly replaces the trigger threshold with 2+ and grants the Deadly Demise D3+3 ability instead of the previous ability. `conditional_mortal_wounds_modifier` stores the intrinsic +3 of that replacement ability; it is not a later modifier to a D3 roll. No separate arithmetic modifier producer was found. |
| Healing/revival quantity | `gw-11e-core-modifiers:healing`, `healing.py`, Necrons `phase17f:phase17e:necrons:army-rule`, `manifestation_healing.py` and catalog restoration. They consume an intrinsic heal count/D3 or return a model with source-specified wounds, capped by starting wounds. Those quantities/placement choices are distinct from the Soulstealer D6 modifier above. No additional heal/revival-roll arithmetic producer was found. |
| Triggered/reactive movement distances | `catalog_fight_end_triggered_movement_runtime.py`, `catalog_movement_end_reactive_normal_move_runtime.py`, `stratagems_generic_rule_ir.py`, movement/shooting surge owners and Aeldari Battle Focus. The inspected nonzero additions encode the source's complete D3+3/D6+1 movement allowance. For example, `gw-11e-aeldari-corsair-skyreavers-datasheet-2026-06-09:datasheet:000004196:4` grants an up-to-D3+3 move, and Corsair Coterie's `faction_aeldari_corsair_coterie_ir_support_2026_27.py` grants up-to-D6+1. They do not add a later effect to M or to an existing distance roll. Distance caps and PathWitness legality remain with the movement owner. |
| Reserve arrival, placement, range of an ability | `reserve_arrival_requirements.py`, `reserve_arrival_hooks.py`, `return_placement_legality.py` and healing placement owners consume arrival distances, eligibility and geometry. These are neither unit profile/weapon characteristics nor modified unit rolls. No separate reserve/placement dice-modifier producer was found. |
| Detection and Lone Operative | `gw-11e-core-modifiers:detection-lone-operative-limits`, `hidden_detection.py`, `ranged_rule_effects.py`, `shooting_targets.py`. These are targeting-rule distances/ability restrictions, not weapon Range or unit-profile characteristics; the generic core bounds representation does not turn them into those subjects. Their source-specific changes remain in targeting legality. |
| Stratagem CP cost and player resources | `gw-11e-core-modifiers:stratagem-cost-limits`, `stratagem_cost_modifiers.py`, `command_points.py`, `faction_resources.py`. They modify resource costs/counts, not a unit's roll or profile. Army resource dice, rerolls and substitutions retain their own source decisions. This exclusion does not include a source that actually modifies a unit's test roll. |

## Audit limits

The review searched typed `Modifier`/`RollModifier` production, runtime registry
bindings, generic IR characteristic/dice consumers, named-provider arithmetic
around `current_total`/D3 results, and the corresponding loaded source
descriptors. Enum expansion alone was not used to exclude any family.
No further concrete executable roll/profile modifier producer lacking a choice
owner was identified by this targeted audit after adding Soulstealer. The
unretained 01.05.04 transcription and whole-corpus source equivalence remain
explicit evidence limits; future source promotion must supply a consumer and
tests for any additional modifier family. This document does not certify
currently unsupported catalog rules or arbitrary synthetic W/FNP/Hazardous
modifier grants as implemented.

The generic Stratagem followup inspected 1,208 source activation records and
the Shadow Legion/Path of the Outcast runtime overrides. Its two executable
`force_battle_shock_test` descriptors are Shade Path
(`gw-11e-faction-packs-2026-07:stratagem:chaos-daemons:shadow-legion:000009979006`)
and Eldritch Suppression
(`phase17f:phase17e:aeldari:path-of-the-outcast:stratagems`). Shade Path first
registers its Charge penalty, then starts one terminal test; Eldritch
Suppression has only one test effect. Neither currently exercises a dependent
effect after a suspended test or multiple tests in the same effect loop.
`stratagems_generic_rule_ir.py:_record_generic_rule_ir_stratagem_runtime_effects`
is synchronous around those test helpers; a future descriptor with subsequent
dependent effects requires an explicit resumable effect cursor before promotion.
