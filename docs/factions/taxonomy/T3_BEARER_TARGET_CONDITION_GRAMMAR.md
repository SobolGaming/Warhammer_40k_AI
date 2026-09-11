# T3 — Bearer, target and condition grammar

[Taxonomy index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [T1 WHEN taxonomy](T1_STRATAGEM_WHEN_TAXONOMY.md) · [T2 effect taxonomy](T2_EFFECT_TAXONOMY.md) · [T5 resource and state-token taxonomy](T5_RESOURCE_STATE_TOKEN_TAXONOMY.md) · [T6 decision-kind taxonomy](T6_DECISION_KIND_VISIBILITY.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This survey is Track T item T3. It is planning evidence delivered read-only to
Track G's bearer, target and condition surfaces. It does not implement engine
semantics, add RuleIR kinds, populate faction records, or admit content. FM0
regenerates bearer/target/condition rows from the retained content set and
reconciles them with this document.

Machine-readable catalog: [`t3_bearer_target_conditions.json`](t3_bearer_target_conditions.json).

## 1. Purpose and delivery contract

T3 closes the grammar that Track G must design against before faction
implementation maps abilities, Enhancements, Stratagems and detachment rules
onto who a rule is on, who it selects, and which predicates gate it.

A TARGET line is a **clause list**, not a single stored `target_kind`. "That
unit, or one friendly JUMP PACK unit within 3"" is `{anaphoric, unit}` **or**
`{your, unit, distance}`. Lifting `friendly_unit` over the union hides the
alternate (the T1-001 failure mode applied to targets).

A condition set is not a WHEN window and not an EFFECT. "If your unit has the
PENITENT keyword" is `keyword_effect_gate`. "One PENITENT unit from your army"
is a target-clause keyword require. "Until the end of the phase, melee weapons
have [Lethal Hits]" is T2.

**Track G implements typed bearer, target and condition descriptors and
engine-owned consumers only.** It must not add speculative kinds from this gap
list without a real source-backed consumer in the same PR.

T1 still owns WHEN windows. T2 still owns EFFECT families. T5 delivered which
resources share a `ResourceLedger` in
[T5_RESOURCE_STATE_TOKEN_TAXONOMY.md](T5_RESOURCE_STATE_TOKEN_TAXONOMY.md).
T6 delivered finite versus parameterized decisions in
[T6_DECISION_KIND_VISIBILITY.md](T6_DECISION_KIND_VISIBILITY.md). T3 names
the atoms those tracks bind.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Listing inventory | 1,756 Enhancement/Upgrade and 2,520 Stratagem table rows in `docs/factions/audit/` |
| Retained TARGET corpus | Phase 17S activation profiles dated 2026-06-21: 1,025 rows, **857** distinct `target_descriptor` strings |
| Restrictions column | Every June row stores the same boilerplate `matched play same stratagem per phase`. Conditions are read from TARGET and EFFECT, not from that column |
| Core TARGET | Live [15.00 Stratagems](https://www.40k.app/rules/15-stratagems) |
| Operative samples | Live [War Horde](https://www.40k.app/factions/orks/detachments/war-horde) and [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion) TARGET, bearer and IF clauses |
| Engine inspection | Read-only: `RuleTargetKind`, `RuleConditionKind`, `INITIAL_RULE_TEMPLATES` target/condition templates, stored activation `target_kind` / `target_policy_id` |

September audits have no TARGET or TARGETING column. Per-entity App 946
assignment over the expected ~1,400 distinct Stratagems and ~1,000
Enhancements is **S3a / FM0**. T3 still closes the *set*.

This document does not copy bulk operative text. Sampled clauses are
paraphrased and linked. Exact transcription remains an F00/S3a obligation.

Stored activation RuleIR is **not** this grammar. Every June profile uses
`phase17s:stratagem-activation-target-binding` with `conditions: []`. The
generator's `_target_kind_and_policy` defaults almost every row to
`friendly_unit`. This survey re-reads `target_descriptor` and
`effect_descriptor`. FM0 must not treat stored `target_kind` as the TARGET
clause.

Classification rules that a token hit-list would flatten:

| Flattened token | Published grammar |
| --- | --- |
| "enemy unit" inside "not within Engagement Range of enemy units" | condition `engagement`, not `enemy_select` |
| "That unit, or one friendly JUMP PACK within 3"" | target **clause list**. Do not lift `friendly_unit` |
| "One unit and one objective marker" | `target_pair`. Two objects, not one grain |
| "has not been selected to shoot or fight" | selection-state **action set** `{shoot, fight}` |
| "has not been selected to move or charge" | selection-state **action set** `{move, charge}` |
| "has just destroyed an enemy unit" | not `just_destroyed`. The TARGET object did the destroying |
| "place it into Strategic Reserves" | T2 placement EFFECT, not condition `in_reserves` |
| "excluding modifiers to saving throws" | T2 `ignore_modifiers`, not `keyword_exclude` |
| ALLCAPS name on the TARGET line | target-clause keyword require, not T2 `keyword_grant` |
| "if your unit has the X keyword" | `keyword_effect_gate` (T3), not a grant |
| WHEN-phase "Your Shooting phase." | T1. T3 `phase_condition` is an IF inside EFFECT |
| "Waaagh! is active" | state-token condition. T5 owns the ledger |
| Command Re-roll "you" | bearer `player`, not `army` and not grain `player` |
| Command Re-roll listed roll types | condition `dice_roll_type` (`roll_types`). T2 owns the reroll EFFECT |

## 3. Closed grammar

### 3.1 Bearer

| Bearer ID | Meaning | June Stratagem rows | Existing RuleIR |
| --- | --- | ---: | --- |
| `activation_object` | The TARGET-line object; EFFECT says "your unit" / "your model" | 1025 | `friendly_unit` / `selected_target` / `selected_unit` |
| `enhancement_bearer` | The model given the Enhancement ("the bearer") | 0 as TARGET; 1 EFFECT mention | `this_model` |
| `this_model` | Datasheet "this model" | 0 | `this_model` |
| `this_unit` | Datasheet "this unit" | 0 | `this_unit` |
| `attached_rules_unit` | Leader and Bodyguard as one rules unit | `leading` 2, `attached` 13 as conditions | group-aware APIs; no bearer kind |
| `player` | The player as the activation subject ("you") | 0 as TARGET; Core Command Re-roll | `player` |
| `army` | Army-wide subject | 0 as TARGET | `player` |

`player` is not an alias of `army`. Command Re-roll is on you; an army-wide
clause is on the army. Grain `player` is a TARGET noun ("you" as the selected
object) and is also not that bearer.

June Stratagems always select an activation object, then talk about "your
unit". Enhancement pages use `enhancement_bearer`. Datasheets use `this_model`
/ `this_unit`. Core Command Re-roll uses `player`. Those zeros stay in the
closed set. T4 owns mustering who may *take* an Enhancement; T3 owns the
runtime bearer atom.

### 3.2 Target clauses

Each TARGET alternative or conjunct is one clause `{allegiance, grain, count}`.
Owner and grain stay on that clause.

| Axis | Closed tokens |
| --- | --- |
| Allegiance | `your`, `opponent`, `anaphoric` ("that" / "those"), `unspecified` |
| Grain | `unit`, `model`, `marker`, `objective_marker`, `dice_roll`, `player` |
| Count | `one`, `up_to_n`, `one_or_more`, `that` |
| Composition | `singleton`, `union` (or), `pair` (and) |

June TARGET-line demand (multi-label axes, not exclusive families):

| Token | Meaning | June rows |
| --- | --- | ---: |
| `friendly_allegiance` | From your army / friendly / anaphoric friendly | 1018 |
| `unit_grain` | Selects a unit | 978 |
| `anaphoric` | TARGET starts with "That" | 119 |
| `model_grain` | First clause selects a model, not a unit | 40 |
| `destroyed_permitted` | "even though" the object was just destroyed | 37 |
| `target_pair` | Two objects (unit and marker, unit and unit) | 20 |
| `multi_select` | TARGET starts with "Up to" | 23 |
| `target_union` | Or-alternatives that must not be lifted | 20 |
| `marker` | Cult Ambush marker (EVASIVE VANGUARD, ALONG SHADOWED TRAILS) | 2 |
| `enemy_select` | TARGET line selects an enemy | 0 |
| `dice_roll` | TARGET is a roll (Core Command Re-roll) | 0 |
| `player` | TARGET is you / your army as a player | 0 |

Every June row classifies onto §3.2. The three zeros remain because Core 15
and Enhancement TARGET lines use them.

Stored heuristic (do not copy): `target_kind` is `friendly_unit` on **1,023**
rows and `any_unit` on **2**. `target_policy_id` is `friendly_unit` 627,
`selected_target_unit` 184, `not_selected_to_shoot_unit` 107,
`not_selected_to_fight_unit` 71, `selected_to_move_unit` 32, `just_shot_unit`
2, `enemy_unit` 2. Both stored `enemy_unit` rows (ECSTATIC SLAUGHTER, DUTY
UNENDING) are friendly objects with an engagement condition. PHANTASMAL
MIRAGE is stored `just_shot_unit` while its TARGET is "That HARLEQUINS
VEHICLE unit."

### 3.3 Selection-state action set

When a TARGET says the object has not been selected to do something, the
actions are a set on that clause.

| Action | June TARGET rows | Unions that must keep both actions |
| --- | ---: | --- |
| `shoot` | 171 | 62 also name `fight` |
| `fight` | 138 | those 62 |
| `move` | 32 | 7 also name `charge` |
| `charge` | 9 | those 7 |

`fight` is `selected to fight` **or** `shoot or fight`. Counting only
`selected to fight` (76) hides the 62 unions (the T1-001 failure mode).
Two charge rows name charge alone (BLOOD BEGETS SKULLS, UNHOLY HASTE).
ASSAIL says "eligible to shoot"; that is not selection-state.

A single `not_selected` flag is not a legal descriptor.

### 3.4 Condition families

Counts are June rows whose TARGET or EFFECT demands the family (multi-label),
using the predicates in [`t3_bearer_target_conditions.json`](t3_bearer_target_conditions.json).
Of the 1,025 rows: 158 match zero of these families, 436 one, 280 two, 99
three, 35 four, 15 five, 2 six. **1,520** assignments, equal to the sum of
the family counts.

| Family ID | Meaning | June rows | Existing RuleIR |
| --- | --- | ---: | --- |
| `distance` | Within N" | 217 | `phase17c:distance-predicate` / `DISTANCE_PREDICATE` |
| `selected_as_target` | Was selected as the target of attacks | 183 | TARGET qualifier; charge-as-a-target stays T1 WHEN |
| `not_selected_to_shoot` | Selection-state includes shoot | 171 | no dedicated kind; `TARGET_CONSTRAINT` nearest |
| `engagement` | Within / not within Engagement Range | 165 | `DISTANCE_PREDICATE` / `TARGET_CONSTRAINT` |
| `not_selected_to_fight` | Selection-state includes fight | 138 | same as shoot; includes `shoot or fight` |
| `keyword_exclude` | Excluding listed keywords or models | 126 | `KEYWORD_GATE` negated. Not T2 "excluding modifiers". Stored `excluded_keywords` on 81 rows |
| `battle_shocked` | Is, is not, or must test Battle-shocked | 69 | no condition kind; T2 owns the EFFECT |
| `keyword_effect_gate` | If the unit has / is a listed keyword | 58 | `phase17c:keyword-gate`. Not "if Righteous" / "Below Half-strength" |
| `on_battlefield` | Is on the battlefield | 54 | **none** as a condition kind |
| `wholly_within` | Wholly within a zone or range | 41 | `DISTANCE_PREDICATE` |
| `just_destroyed` | TARGET object was just destroyed | 37 | T1 destruction WHEN; T3 permits the TARGET |
| `not_selected_to_move` | Selection-state includes move | 32 | same as shoot |
| `visibility` | Visible to | 31 | `VISIBILITY_PREDICATE` |
| `state_token` | Named persisting status (see §3.5) | 30 | `contextual-status` nearest; T5 owns ledgers |
| `objective_range` | Within range of an objective (TARGET or EFFECT IF) | 28 | `DISTANCE_PREDICATE` + objective atom |
| `embarked` | Embarked in a Transport | 26 | **none** as a condition kind |
| `frequency` | Once per battle / once per unit | 25 | `FREQUENCY_LIMIT` |
| `in_reserves` | TARGET is in Reserves, Cult Ambush, or arriving | 25 | `PLACEMENT_*` kinds; no condition kind. EFFECT "place into Reserves" is T2 |
| `attached` | Attached unit / Attached restriction | 13 | **none** as a condition kind |
| `deadly_demise` | Has Deadly Demise | 12 | keyword-like; no dedicated kind |
| `disembarked` | TARGET disembarked, or EFFECT "if your unit disembarked" | 10 | **none** as a condition kind |
| `not_selected_to_charge` | Selection-state includes charge | 9 | same as shoot |
| `models_destroyed` | TARGET had one or more models destroyed | 8 | **none** as a condition kind |
| `below_starting_strength` | TARGET object is below Starting Strength | 5 | **none** as a condition kind |
| `count_size` | Contains N+ models, or a model-count exclude | 4 | `TARGET_CONSTRAINT` nearest |
| `leading` | Is leading, or is not leading | 2 | **none** as a condition kind |
| `just_shot` | Has just shot (PSY-CHAFF VOLLEY) | 1 | stored policy exists; kind unused as condition |
| `dice_roll_type` | TARGET roll is one of a listed type set | 0 | `DICE_ROLL_TYPE`; parameter `roll_types` |
| `phase_condition` | If it is a named phase | 0 | `PHASE_GATE` |
| `turn_owner_condition` | If it is your / your opponent's turn | 0 | `PHASE_GATE` parameters |
| `riled_up` | "Riled up" (War Horde Enhancement) | 0 | state token; T5 / F-ORK-01 |

The June zeros stay in the closed set: Core Command Re-roll uses
`dice_roll_type`, Core and datasheet IF-clauses use phase and turn ownership,
and App 946 War Horde uses "riled up". `dice_roll_type` is eligibility of the
`dice_roll` grain, not T2 `reroll`.

Stored `required_keywords` occupy 386 rows. That field is a TARGET-noun
heuristic from ALLCAPS tokens. It is not a condition-family count and is
not the closed keyword-require grammar.

### 3.5 State tokens

T3 names the tokens. T5 delivered which share a `ResourceLedger`.

June EFFECT/TARGET hits: Righteous (6), Halo Override (4), Desperate Pact (3),
Afflicted (4), Waaagh! (7), Focus of Hatred (2), Blessed (2), Malevolent (1),
Shroud of Chaos (1). Roadmap examples "riled up" and "Waaagh! active" both
belong here. "Riled up" has **no** June Stratagem match.

## 4. Existing RuleIR versus this demand

`RuleTargetKind` already has `friendly_unit`, `enemy_unit`, `selected_target`,
`selected_unit`, `this_model`, `this_unit`, `player`, `dice_roll`,
`aura_units`, `weapon`, `stratagem_use`.

`RuleConditionKind` already has `keyword_gate`, `distance_predicate`,
`visibility_predicate`, `phase_gate`, `frequency_limit`, `target_constraint`,
`dice_roll_gate`, `dice_roll_type`, `aura`.

Templates: `phase17c:keyword-gate`, `phase17c:distance-predicate`,
`phase17c:selected-target-constraint`, `phase17c:tracked-target-selection`.

June profiles store none of the condition kinds. Tracked-target (prey /
quarry) is Enhancement/datasheet demand, not a June Stratagem TARGET.

## 5. Core 15 and App 946 samples

Live [15.00](https://www.40k.app/rules/15-stratagems). Snap Shooting is not a
Stratagem.

| Stratagem | Bearer / TARGET / conditions |
| --- | --- |
| Command Re-roll | Bearer `player`. Grain `dice_roll`. Condition `dice_roll_type` (`roll_types`) |
| Epic Challenge | `activation_object` CHARACTER unit. Condition: selected to fight (T1 WHEN) |
| Insane Bravery | `activation_object` + `battle_shocked` |
| Crushing Impact | `activation_object` MONSTER or VEHICLE |
| Explosives | `activation_object` |
| Rapid Ingress | `activation_object` + `in_reserves` |
| Fire Overwatch | `activation_object` |
| Smokescreen | `activation_object` |
| Heroic Intervention | `activation_object` + `engagement` / distance |
| Counter-offensive | `activation_object` |

[War Horde](https://www.40k.app/factions/orks/detachments/war-horde)
Enhancements use `enhancement_bearer` and the `riled_up` state token.
Detachment Get Stuck In is an EFFECT (T2) on units with no extra TARGET
line. Sampled Stratagem TARGETS are `your` + `unit` with keyword require
ORKS, plus selection-state or `battle_shocked` on some rows.

[Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion)
detachment clauses use `keyword_effect_gate` and `this_unit` / army
subjects. Sampled Enhancements use `enhancement_bearer`. Sampled Stratagem
TARGETS are `your` + `unit` or `model`, with `distance`, `engagement`,
`in_reserves` and `keyword_exclude` appearing on the same closed set.

Those samples do not add axes.

## 6. Gap list for Track G

### 6.1 Kinds that exist and profiles do not store

FM0 must bind §3 to `RuleTargetKind` / `RuleConditionKind` and the templates
above. Do not invent a second catalogue. Stored `friendly_unit` plus empty
`conditions` is not that binding.

`enemy_unit`, `dice_roll`, `this_model`, `this_unit`, `player`,
`DICE_ROLL_TYPE`, `VISIBILITY_PREDICATE`, `PHASE_GATE` and `FREQUENCY_LIMIT`
already exist.
June Stratagem TARGET lines do not use all of them. That is
`kind_unused_by_profiles`, not `gap_no_kind`.

### 6.2 Families with no condition kind

Demand, each requiring a real consumer before a new kind exists:

- selection-state action sets (`shoot` / `fight` / `move` / `charge`)
- `on_battlefield`, `embarked`, `disembarked`, `in_reserves` as conditions
- `battle_shocked` as a condition (T2 owns the EFFECT)
- `attached`, `leading`
- `below_starting_strength`, `models_destroyed`, `count_size`
- `just_destroyed` as a TARGET permission (T1 owns the WHEN)
- `deadly_demise` as a gate
- `marker` grain (Cult Ambush, Tunnel)
- `target_pair` and `target_union` as first-class compositions
- `state_token` as a typed gate (T5 splits the ledgers)
- `riled_up` (Enhancement; F-ORK-01)

### 6.3 Families T3 must not steal

- WHEN windows remain T1, including `selected_as_target` as a WHEN event
  and "selected as a target of that charge".
- EFFECT families remain T2, including `keyword_grant`, `ignore_modifiers`
  ("excluding modifiers"), placement "place into Strategic Reserves", and
  the Command Re-roll reroll itself. Listed roll-type eligibility is T3
  `dice_roll_type`.
- Resource ledger identity remains T5.
- Finite versus parameterized target *decisions* are closed in
  [T6](T6_DECISION_KIND_VISIBILITY.md). T3 only names the selectable atoms.

## 7. Engine gaps this survey is not fixing

| Gap | Current behavior | Owner |
| --- | --- | --- |
| Stored target is almost always `friendly_unit` | 1,023 / 1,025; two false `enemy_unit` | S3d / FM0 |
| Stored `conditions` is empty | 1,025 profiles | S3d / FM0 |
| September audits have no TARGET column | 1,756 Enhancement and 2,520 Stratagem listings | S3a |
| Orks v946 rewrite | War Horde bearer/state tokens may be new | FM0.5 / F-ORK-01 |

## 8. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| T3-HOLD-APP-TARGET | App 946 TARGET / IF text is not retained for Enhancements, detachment rules, datasheet abilities, or every distinct Stratagem | S3a, then FM0 |
| T3-HOLD-PROFILE-STALENESS | 1,025 profiles dated 2026-06-21 | S3a / S3d |
| T3-HOLD-UNION-TARGET | Clause-list versus a lifted `target_kind`; action sets stay sets | Track G |
| T3-HOLD-STORED-KIND | Generator `_target_kind_and_policy` is a heuristic | Track G / FM0 |
| T3-HOLD-STATE-SPLIT | Named tokens are T3; which share a ledger is answered in [T5](T5_RESOURCE_STATE_TOKEN_TAXONOMY.md) | this survey / T5 |
| F-ORK-01 | Orks bearer and "riled up" inventory may be new at v946 | FM0.5 |

## 9. What "T3 delivered to Track G" means

Track G's bearer, target and condition work may be designed. It has:

- the closed bearer IDs, target-clause axes and condition family IDs;
- June Stratagem demand counts with unions, pairs and action sets preserved;
- the map onto existing `RuleTargetKind` / `RuleConditionKind` values and
  the gap list;
- Core 15 and sampled App 946 confirmation that Enhancement and detachment
  clauses use the same set;
- the hold that per-entity App 946 counts wait on S3a.

T3 does not add kinds, change activation profiles, or emit
`semantic_demand_matrix.json`. FM0 regenerates that matrix from retained
pages and reconciles it with this survey.
