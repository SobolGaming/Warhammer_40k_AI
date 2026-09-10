# T2 — Effect taxonomy

[Taxonomy index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [T1 WHEN taxonomy](T1_STRATAGEM_WHEN_TAXONOMY.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This survey is Track T item T2. It is planning evidence delivered read-only to
Track G's generic effect families. It does not implement engine semantics, add
RuleIR templates, populate faction records, or admit content. FM0 regenerates
effect-family rows from the retained content set and reconciles them with this
document.

Machine-readable family catalog: [`t2_effect_families.json`](t2_effect_families.json).

## 1. Purpose and delivery contract

T2 closes the EFFECT grammar that Track G must design against before faction
implementation maps abilities, Enhancements, Stratagems and detachment rules
onto RuleIR templates.

An EFFECT is a **set of families**, not a single primary tag. "Until the end of
the phase, melee weapons have [Lethal Hits] and you can re-roll Wound rolls of
1" is `weapon_ability_grant` **and** `reroll`. Lifting one family over the
clause hides demand (the T1-001 failure mode applied to effects).

The closed family set is the roadmap catalogue plus families the retained
EFFECT corpus demanded that the roadmap list does not name. Track G must not
explode each observed wording into its own template.

**Track G implements typed RuleIR templates and engine-owned consumers only.**
It must not add speculative templates from this gap list without a real
source-backed consumer in the same PR. Existing generic RuleIR consumers stay
on their current templates until a later order remaps them.

T3 still owns bearer, target and condition grammar. T5 still owns which
resources share a `ResourceLedger`. T2 only names the effect families those
tracks will bind.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Listing inventory | 1,756 Enhancement/Upgrade and 2,520 Stratagem table rows in `docs/factions/audit/` (inherited repeats included) |
| Retained EFFECT corpus | Phase 17S activation profiles dated 2026-06-21: 1,025 Stratagem `effect_descriptor` strings |
| Core EFFECT | Live [15.00 Stratagems](https://www.40k.app/rules/15-stratagems) |
| Operative samples | Live [War Horde](https://www.40k.app/factions/orks/detachments/war-horde) and [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion) Enhancement and detachment-rule EFFECTS |
| Engine inspection | Read-only: `RuleTemplateFamily` and `INITIAL_RULE_TEMPLATES` in `rules/rule_templates.py`; generic Stratagem RuleIR runtime; datasheet-specific catalog templates |

September audits store Enhancement/Stratagem **names and costs** only. They
have no EFFECT column. Per-entity App 946 EFFECT assignment over the expected
~1,000 Enhancements/Upgrades, ~1,400 distinct Stratagems, detachment rules and
datasheet abilities is therefore **S3a / FM0**. T2 still closes the family
*set*: every retained Stratagem EFFECT classifies onto §3, and sampled
Enhancement, detachment and Core EFFECTS use the same families.

This document does not copy bulk operative text. Sampled clauses are
paraphrased and linked. Exact transcription remains an F00/S3a obligation.

Stored activation RuleIR is **not** an effect catalogue. Every June profile
uses `phase17s:stratagem-activation-target-binding`. This survey classifies
`effect_descriptor` text. FM0 must not treat the stored template ID as the
effect family.

Classification rules that a token hit-list would flatten (the T1-001 failure
mode applied to EFFECTS):

| Flattened token | Published family |
| --- | --- |
| "eligible to shoot and declare a charge" | `movement_permission` only. `out_of_phase_charge` is resolve-a-Charge-now |
| "if your unit has the X keyword" | T3 / `keyword-gate`. `keyword_grant` is "gains / has the X keyword until" |
| "Leadership test" | `leadership_test`. `leadership_modifier` is the Leadership characteristic |
| "once per battle" on the Stratagem restriction | not an EFFECT. `once_per_battle_reuse` is using a once-per-battle ability again |
| substring `leader` inside "Leadership" | not `attachment_change` |

## 3. Closed family set

Families are source-neutral IDs. A row may carry several. Counts below are
June Stratagem profile rows that demand the family (multi-label). They are
not distinct-rule denominators.

### 3.1 Attack sequence

| Family ID | Meaning | June Stratagem rows | Existing RuleIR |
| --- | --- | ---: | --- |
| `hit_modifier` | Add or subtract from the Hit roll | 45 | `phase17c:dice-roll-modifier` |
| `wound_modifier` | Add or subtract from the Wound roll | 55 | `phase17c:dice-roll-modifier` |
| `save_modifier` | Saving-throw or AP improve/worsen | 71 | AP: `phase17c:characteristic-modifier`. Saving throw: `phase17c:dice-roll-modifier`. June rows are AP |
| `damage_modifier` | Change a weapon's Damage characteristic | 6 | `phase17c:characteristic-modifier` |
| `strength_modifier` | Strength of a weapon or attack | 33 | `phase17c:characteristic-modifier` |
| `attacks_characteristic` | Attacks characteristic | 9 | `phase17c:characteristic-modifier` |
| `ws_bs_modifier` | Weapon Skill or Ballistic Skill | 19 | `phase17c:characteristic-modifier` |
| `toughness_modifier` | Toughness | 17 | `phase17c:characteristic-modifier` |
| `wounds_modifier` | Wounds characteristic | 2 | `phase17c:characteristic-modifier` |
| `reroll` | Re-roll permission or requirement | 83 | `phase17c:reroll-permission` |
| `critical_hit_threshold` | Unmodified N+ is a Critical Hit | 23 | nearest `dice-roll-override`; no dedicated template |
| `ignore_modifiers` | Ignore any or all modifiers | 16 | **none** |
| `weapon_ability_grant` | Lethal, Sustained, Precision, Lance, Anti-, Rapid Fire, and similar | 126 | `phase17c:weapon-ability-grant` |
| `weapon_profile_grant` | Equipped-weapon characteristic or named-profile rewrite | 135 | `phase17c:characteristic-modifier` plus weapon grants |
| `mortal_wounds` | Inflict mortal wounds | 72 | generic Stratagem mortal-wound resolver; no EFFECT template |
| `damage_reduction` | Subtract from the Damage of an **allocated** attack | 14 | `phase17c:allocated-attack-damage-characteristic-modifier` |

`save_modifier` (AP / saving throw) is not `damage_reduction` (allocated
Damage). AP is a characteristic operation, not a saving-throw modifier.
`weapon_ability_grant` is not `weapon_grant` (giving a new weapon).

### 3.2 Defence, return and survival

| Family ID | Meaning | June Stratagem rows | Existing RuleIR |
| --- | --- | ---: | --- |
| `feel_no_pain` | Feel No Pain N+ | 28 | `phase17c:grant-ability` |
| `invulnerable_save_grant` | Invulnerable save | 16 | `phase17c:grant-ability`; datasheet `conditional-ranged-invulnerable-save` |
| `save_characteristic_set` | Set Save to a value | 1 | `phase17c:characteristic-set` |
| `cover_grant` | Benefit of Cover | 13 | nearest `grant-ability` |
| `ignore_cover` | Ignore Cover or deny Benefit of Cover | 26 | weapon-ability `[Ignores Cover]` or **none** for denial |
| `lone_operative_range` | Can be targeted only within N" | 10 | **none** |
| `fight_on_death` | Destroyed model remains and fights (or shoots) | 28 | datasheet `phase17c:conditional-model-fight-on-death` |
| `healing` | Regain lost wounds | 15 | generic Stratagem restore-lost-wounds runtime |
| `revival_return` | Return destroyed models, set a model back up, or add a replacement unit | 32 | `phase17c:first-death-return` (first death only; D3+ and "set back up" are a gap) |

### 3.3 Movement, placement and phase actions

| Family ID | Meaning | June Stratagem rows | Existing RuleIR |
| --- | --- | ---: | --- |
| `movement_permission` | Eligible to shoot or charge after Advance or Fall Back | 92 | `phase17c:grant-ability` / datasheet charge-after-movement |
| `movement_distance` | Change Move | 26 | `phase17c:movement-distance-modifier` |
| `extra_move` | D6 / Stimulus / Surge / extra Normal move | 68 | nearest `out-of-phase-action` |
| `ignore_terrain` | Move through terrain or models | 21 | `RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION`; no generic template |
| `redeploy_teleport` | Remove from the battlefield into Reserves | 41 | `phase17c:placement-permission-restriction` |
| `reserves_change` | Arrival, ingress, battle-round-as-higher, Deep Strike | 64 | `phase17c:placement-permission-restriction` |
| `placement_setup` | Set up wholly within an edge or area | 30 | `phase17c:placement-permission-restriction` |
| `transport` | Embark, disembark, Transport interactions | 40 | **none** as a generic EFFECT family |
| `pile_in_consolidate` | Pile-in or Consolidate distance or timing | 17 | **none** |
| `desperate_escape` | Force or modify Desperate Escape | 12 | `phase17c:desperate-escape-requirement` |
| `charge_roll_modifier` | Add, subtract, or re-roll a Charge roll | 28 | add/subtract: `phase17c:dice-roll-modifier`. Re-roll: `phase17c:reroll-permission` |
| `advance_roll_modifier` | Add, subtract, or replace an Advance roll | 18 | add/subtract: `phase17c:dice-roll-modifier`. Re-roll: `phase17c:reroll-permission`. Skip-roll +N Move: `movement-distance-modifier` for the Move change; skipping the roll has no template and is not `dice-roll-override` |
| `out_of_phase_shoot` | Shoot as if it were the Shooting phase / Snap | 16 | `phase17c:out-of-phase-action` |
| `out_of_phase_charge` | Resolve a Charge now (not merely become eligible) | 5 | `phase17c:out-of-phase-action` |

`out_of_phase_charge` is FOOLS' FLIGHT, MERCILESS PURSUIT, ECSTATIC SLAUGHTER,
CUT DOWN THE WEAK and ENSNARING TRAP. "Eligible to shoot and declare a charge"
and "cannot declare a charge" are not this family. Core Heroic Intervention is
the same family and is not one of the 1,025 June rows.

### 3.4 Control, resources and status

| Family ID | Meaning | June Stratagem rows | Existing RuleIR |
| --- | --- | ---: | --- |
| `oc_change` | Objective Control characteristic | 8 | runtime OC authority; no generic Stratagem template |
| `sticky_objective` | Marker remains under your control | 28 | datasheet `phase17n:command-end-sticky-objective-control` |
| `cp_gain_refund` | Gain or refund CP | 1 | `phase17c:resource-modifier` |
| `resource_gain_spend` | Miracle dice, Pain, Cabal, Yield, Blessings, pledge, and similar spend/gain | 60 | `phase17c:resource-modifier`; T5 owns the ledger split |
| `battle_shock` | Tests, auto-pass, become or cease Battle-shocked | 68 | generic Stratagem Battle-shock runtime |
| `leadership_modifier` | Leadership characteristic | 2 | `phase17c:characteristic-modifier` |
| `leadership_test` | Take or modify a Leadership test that is not only a Battle-shock test | 8 | **none**; do not collapse into `battle_shock` |
| `order_issue` | Issue an Order as if Command phase | 6 | **none** |
| `doctrine_mode` | Select Combat Doctrine, Mission Tactic, Idol, or similar mode | 7 | `phase17k:command-phase-self-ability-choice` |
| `persisting_status` | Afflicted, focus of hatred, Contract, Malefic Surge, named aura status | 8 | `phase17c:contextual-status` / `phase17k:persistent-selected-target-status` |
| `aura_range` | Change aura, Contagion, Synapse, or "count as 10 models" range | 8 | `phase17c:aura` |

### 3.5 Identity, targeting and structure

| Family ID | Meaning | June Stratagem rows | Existing RuleIR |
| --- | --- | ---: | --- |
| `keyword_grant` | Gain a keyword until a duration | 2 | `phase17c:keyword-gate` is a **gate**, not a grant |
| `ability_grant` | Stealth, Lone Operative, or a named datasheet ability | 14 | `phase17c:grant-ability` |
| `target_restriction` | Must / cannot target; allocate to another unit | 48 | `phase17c:selected-target-constraint` |
| `engagement_override` | Ignore Engagement for shooting, or force target-in-engagement | 5 | **none** |
| `fight_order` | Fights First or must be the next unit selected | 2 | **none** as a generic Stratagem template |
| `fight_eligibility_range` | Models within 3" are eligible to fight | 2 | **none** |
| `attachment_change` | Start leading, or rewrite Bodyguard / Precision allocation | 2 | **none** |
| `unit_split` | Split into one-model units | 1 | `RuleEffectKind.SPLIT_UNIT`; no generic template |
| `scout_infiltrate_deep_strike` | Scouts, Infiltrators, Deep Strike | 14 | `phase17c:grant-ability` |
| `weapon_grant` | Give a new weapon (not a keyword on an existing one) | 0 in June Stratagems | Enhancement demand; **none** |
| `once_per_battle_reuse` | Once-per-battle ability may be used again | 2 | generalize P22B ledgers |
| `stratagem_cost` | Modify another Stratagem's CP cost | 0 in June Stratagems | Core 15.01.01; army-rule demand |
| `action` | Start or lock Actions | 0 in June Stratagems | Core Snap Shooting after-shooting lock |

The three June zeros are not leftovers. They have **no** matching
`effect_descriptor` in the 1,025-row extract. They remain in the closed set
because the roadmap names weapon grants and because Core 15 / army rules
demand cost modification and Action lock. FM0 must recount them from retained
App pages rather than delete the families.

### 3.6 Multi-family rows

Of 1,025 retained Stratagem EFFECTS: 555 match one family, 333 match two, 106
match three, 25 match four, 6 match five. **470** rows are multi-family.
Those sizes weight to **1,669** assignments, equal to the sum of the family
`profile_count` values.

The previously published 332 / 107 histogram still counted MOLECULAR TARGETING
as a third family via a false `keyword_grant`. That row is `ws_bs_modifier`
and `ignore_modifiers` only. GIFT OF CHANGE is a one-family `revival_return`
row. The family counts already reflected both facts; only the histogram was
stale.

Track G descriptors carry a family **set**. A single `template_id` on the
stored activation payload cannot represent that set.

`keyword_grant` examples: DAEMONIC POSSESION, SYNERGISTIC EMPOWERMENT.
`attachment_change` examples: SHOULDER THE MANTLE, SELFLESS BODYGUARD.
`once_per_battle_reuse` examples: SUPERHUMAN RESERVES, GILDED CHAMPION.
`leadership_modifier` examples: HUGE SHOW-OFFS, ANCIENT FURY.

## 4. Existing RuleIR catalogue versus this demand

`RuleTemplateFamily` already has twenty members. Several are **conditions**
(T1/T3), not EFFECT families: `timing_window`, `distance_predicate`,
`keyword_gate`, `selected_target_constraint`, `tracked_target_selection`.

EFFECT-facing templates that already exist and this corpus uses:

- `dice-roll-modifier`, `dice-roll-override`, `reroll-permission`
- `characteristic-modifier`, `characteristic-set`
- `allocated-attack-damage-characteristic-modifier`
- `weapon-ability-grant`, `grant-ability`
- `movement-distance-modifier`, `out-of-phase-action`
- `placement-permission-restriction`
- `resource-modifier`, `first-death-return`
- `desperate-escape-requirement`, `contextual-status`, `aura`

Datasheet-only templates (`conditional-model-fight-on-death`,
`command-end-sticky-objective-control`, `conditional-ranged-invulnerable-save`,
and the phase17n/phase17k catalog extensions) must not stay datasheet-only if
Stratagem and Enhancement rows demand the same family.

## 5. Core 15 and App 946 samples

Live [15.00](https://www.40k.app/rules/15-stratagems). Snap Shooting is not a
Stratagem; its after-shooting Action lock is the `action` family.

| Stratagem | EFFECT family set |
| --- | --- |
| Command Re-roll | `reroll` |
| Epic Challenge | `weapon_ability_grant` (Precision) |
| Insane Bravery | `battle_shock` |
| Crushing Impact | `mortal_wounds` |
| Explosives | `mortal_wounds` |
| Rapid Ingress | `reserves_change` |
| Fire Overwatch | `out_of_phase_shoot` |
| Smokescreen | `cover_grant` |
| Heroic Intervention | `out_of_phase_charge` |
| Counter-offensive | `fight_order` |

[War Horde](https://www.40k.app/factions/orks/detachments/war-horde) detachment
rule Get Stuck In is `weapon_ability_grant` (Sustained Hits 1). Sampled
Enhancements use `extra_move` / once-per-battle state (riled up),
`movement_distance`, `save_modifier` after a charge, and
`movement_permission` (Fall Back then shoot or charge). Sampled Stratagems
use `battle_shock` plus `mortal_wounds`, `weapon_ability_grant`,
`fight_on_death`, `movement_distance`, and `weapon_ability_grant` (Lethal
Hits).

[Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion)
detachment clauses use `keyword_grant`, `ability_grant` (Deep Strike, Stealth),
`movement_permission` (Advance then shoot or charge), `hit_modifier` /
`wound_modifier`, and `resource_gain_spend` (Dark Pacts). Sampled Enhancements
use `redeploy_teleport`, `scout_infiltrate_deep_strike`, `mortal_wounds`, and
`oc_change`. Sampled Stratagems use `mortal_wounds`, `weapon_ability_grant`,
`healing` plus `revival_return`, `weapon_ability_grant` (Ignores Cover),
`charge_roll_modifier` plus `battle_shock`, and `redeploy_teleport`.

Those samples sit on the same closed set. They do not add families.

## 6. Gap list for Track G

### 6.1 Families with an existing template that profiles do not store

June profiles store only target-binding RuleIR. FM0 must bind the §3 families
to the templates in the tables, not invent a second catalogue. Where a family's
published meaning spans several RuleIR operations, bind each operation to its
template. Do not treat `dice-roll-modifier` as covering AP characteristic
changes, Charge re-rolls, or Advance replacements.

### 6.2 Families with no generic template

Demand, each requiring a real consumer before a new template exists:

- `ignore_modifiers`
- `lone_operative_range`
- `ignore_terrain` (`RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION` exists)
- `transport` as an EFFECT (capacity and disembark already have Core owners)
- `pile_in_consolidate`
- `order_issue`
- `leadership_test`
- `keyword_grant` (distinct from `keyword-gate`)
- `engagement_override`
- `fight_order` as a Stratagem-generic template
- `fight_eligibility_range`
- `attachment_change`
- `unit_split` (`RuleEffectKind.SPLIT_UNIT` exists)
- `weapon_grant`
- `stratagem_cost` as a reusable EFFECT (Core 15.01.01 is the first consumer)
- `action` lock/start
- D3 / D3+N / "set back up" `revival_return` beyond first-death return
- Sticky objectives and Fight on Death as generic (not datasheet-only) templates

### 6.3 Families with runtime consumers and no EFFECT template

`mortal_wounds`, `battle_shock` and `healing` already mutate through generic
Stratagem RuleIR resolvers. Track G still needs templates if those EFFECTS
must be stored as RuleIR rather than `effect_kind` strings.

### 6.4 Families T2 must not steal from other tracks

- Timing and reaction windows remain T1.
- Bearer, target atoms and state tokens ("riled up", "Waaagh! active") remain T3.
- Which army resources share one ledger remains T5.
- Finite versus parameterized decisions remain T6.

## 7. Engine gaps this survey is not fixing

| Gap | Current behavior | Owner |
| --- | --- | --- |
| Activation RuleIR is target-binding only | 1,025 profiles; EFFECT unused for family ID | S3d / FM0 |
| Datasheet-only Fight on Death and sticky OC | Stratagem rows demand the same families | Track G |
| Keyword grant versus keyword gate | Gate exists; grant does not | Track G |
| September audits have no EFFECT column | 1,756 Enhancement and 2,520 Stratagem listings | S3a |
| Orks v946 rewrite | War Horde EFFECTS may differ from the June extract | FM0.5 / F-ORK-01 |

## 8. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| T2-HOLD-APP-EFFECT | App 946 EFFECT text is not retained for Enhancements, detachment rules, datasheet abilities, or every distinct Stratagem | S3a, then FM0 demand-matrix rows |
| T2-HOLD-PROFILE-STALENESS | 1,025 profiles dated 2026-06-21 | S3a / S3d |
| T2-HOLD-MULTI-FAMILY | One EFFECT is a family set; stored `template_id` cannot flatten it | Track G |
| T2-HOLD-TOKEN-FLATTENING | Naive token hits flatten eligibility into Charge-now, keyword gates into grants, Leadership tests into characteristic modifiers, and Stratagem frequency into ability reuse | Track G / FM0 |
| T2-HOLD-RESOURCE-SPLIT | `resource_gain_spend` counts mixed ledgers | T5 |
| F-ORK-01 | Orks EFFECT inventory may be new at v946 | FM0.5 |

## 9. What "T2 delivered to Track G" means

Track G's effect-family work may be designed. It has:

- the closed family IDs, including roadmap items and corpus-demanded extras
  (`leadership_test`, charge/advance-roll modifiers, mortal wounds);
- June Stratagem demand counts with multi-family rows preserved and token
  flattening forbidden;
- the map onto existing `RuleTemplate` IDs, operation-aware where one family
  spans several RuleIR operations, and the gap list;
- Core 15 and sampled App 946 confirmation that Enhancement and detachment
  EFFECTS use the same set;
- the hold that per-entity App 946 counts wait on S3a.

T2 does not add templates, change activation profiles, or emit
`semantic_demand_matrix.json`. FM0 regenerates that matrix from retained
pages and reconciles it with this survey.
