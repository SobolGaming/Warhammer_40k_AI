# T6 — Decision-kind and viewer-visibility demand

[Taxonomy index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Adapter decision contract](../../ADAPTER_DECISION_CONTRACT.md) · [Decision submission catalog](../../DECISION_SUBMISSION_CATALOG.md) · [T1 WHEN taxonomy](T1_STRATAGEM_WHEN_TAXONOMY.md) · [T5 resource and state-token taxonomy](T5_RESOURCE_STATE_TOKEN_TAXONOMY.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This survey is Track T item T6. It is planning evidence delivered read-only to
Track G's decision-kind and viewer-visibility work, and as a list of adapter
contract *deltas*. It does not implement engine semantics, add `decision_type`
or `proposal_kind` values, edit
[the adapter contract](../../ADAPTER_DECISION_CONTRACT.md), populate faction
records, or admit content. FM0 regenerates decision-demand rows from the
retained content set and reconciles them with this document.

Machine-readable catalog: [`t6_decision_kinds.json`](t6_decision_kinds.json).

## 1. Purpose and delivery contract

T6 closes how a player answers a rule family: finite engine-enumerated
options versus a parameterized proposal, and whether that answer is public or
owner-secret.

A decision kind is not a display name and not one `decision_type` per faction
rule. "Select a unit", "spend", and "use a Stratagem" are not a single kind
each. Lifting `use_stratagem` over both fully enumerated targets and
non-enumerable target policies hides the catalog split already shipped (the
T1-001 failure mode applied to decisions).

The closed set is two submission kinds, two visibility classes, and the
demand families in §3. Observed player choices are assignments onto that
set. Track G must not explode each observed wording into its own enum
member.

**Track G implements typed decision families, engine-owned validation and
mutation, and adapter-contract updates only.** It must not add speculative
`decision_type`, `proposal_kind`, nested allowlist, or visibility-class
rows from this gap list without a real source-backed consumer in the same
PR. Existing catalog surfaces stay on their current types until a later
order remaps them.

T1 still owns WHEN windows and Stratagem envelopes (`use_stratagem`,
`ReactionWindow`, `OpportunityWindow`, `OutOfPhaseActionContext`). T2 still
owns EFFECT families. T3 still owns bearer, TARGET-clause and condition
atoms. T4 still owns construction constraints. T5 delivered which tokens
share a ledger in
[T5_RESOURCE_STATE_TOKEN_TAXONOMY.md](T5_RESOURCE_STATE_TOKEN_TAXONOMY.md).
T6 only answers: how the player submits, and who may see the pending
request.

Authoritative existing surfaces (read, do not duplicate here):

- [Adapter decision contract](../../ADAPTER_DECISION_CONTRACT.md): finite
  versus parameterized submission, viewer scoping, nested-decision
  allowlist.
- [Decision submission catalog](../../DECISION_SUBMISSION_CATALOG.md):
  concrete `decision_type` and `proposal_kind` rows.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Listing inventory | 2,520 Stratagem and 1,756 Enhancement/Upgrade table rows in `docs/factions/audit/` (inherited repeats included) |
| June Stratagem corpus | Phase 17S activation profiles dated 2026-06-21: 1,025 rows |
| T2 EFFECT demand | `resource_gain_spend` **60** June rows (T2); T6 does not recount families |
| T3 TARGET demand | 1,520 condition assignments (T3); T6 does not rename TARGET atoms |
| T5 token demand | 45 closed tokens; T6 does not re-fit ledgers |
| Core samples | Live [15.00 Stratagems](https://www.40k.app/rules/15-stratagems) |
| Operative samples | Live [War Horde](https://www.40k.app/factions/orks/detachments/war-horde), [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion) |
| Engine inspection | Read-only: adapter contract, submission catalog, `STRATAGEM_DECISION_TYPE`, nested allowlist `WEAPON_ABILITY_SELECTION_DECISION_TYPE` |

September audits store Name / CP / baseline only. They have no decision
column. Per-entity App 946 choice assignment is **S3a / FM0**. T6 still
closes the *axes*.

This document does not copy bulk operative text. Sampled clauses are
paraphrased and linked. Exact transcription remains an F00/S3a obligation.

Naive June EFFECT token hits are **not** a family histogram (T2-001 /
T2-HOLD-TOKEN-FLATTENING). They flatten TARGET clauses, optional EFFECTS,
and extra-move grants into fake decision types:

| Cue in June EFFECT | Rows | Why this survey does not lift it |
| --- | ---: | --- |
| `you can` | 162 | Often optional EFFECT, not a new submission kind |
| `instead` | 121 | EFFECT branching (T2) |
| `select one` | 108 | T3 TARGET; T6 is finite candidate select once the engine lists options |
| `Normal move` | 64 | Extra-move: finite trigger, then parameterized path |
| `place` | 37 | Mix of T2 EFFECT and parameterized placement |
| `set up` | 25 | Parameterized placement |
| `spend` | 20 | T5 ledger identity; T6 is enumerated amount versus a contract-delta quantity |
| `choose` | 6 | Finite mode pick or finite candidate select |
| `select up to` | 3 | Finite candidate select with T3 cardinality |
| `one of the following` | 2 | Finite mode pick |

Every June Stratagem still needs a `stratagem_window_use` assignment onto
finite enumerated use **or** parameterized target binding. Stored
`target_kind` is almost always `friendly_unit` (T3-HOLD-STORED-KIND) and
must not decide that split. This survey does **not** publish a 1,025-row
finite-versus-parameterized histogram.

## 3. Closed axes

### 3.1 Submission kinds (engine)

There are two engine submission paths. There is no third.

| Kind | Adapter answer | When T6 assigns it |
| --- | --- | --- |
| `finite_option` | `FiniteOptionSubmission` selects one engine-emitted option ID | Legal answers are a closed list the engine can enumerate (including use/decline, named modes, listed units/models/dice/faces, and enumerated spend amounts `0..N`) |
| `parameterized_proposal` | `ParameterizedSubmission` on the fixed option ID `submit_parameterized_payload` | The legal set is a continuous or combinatorially unsafe space: `PathWitness`, placement, shooting/melee declaration, or a Stratagem target policy the index must not pre-enumerate |

`hidden_decision` is **not** a third engine kind. Non-actor viewers see
that placeholder for an `owner_secret` pending request. Adapters must not
submit `hidden_decision` as an engine `decision_type`.

Finite enumerated candidates are not a parameterized proposal. A
parameterized path or placement is not a finite "select a unit" list.
Do not lift one `decision_type` over that union.

### 3.2 Visibility classes

There are two content-facing visibility classes. Viewer-scoped redaction
is the mechanism, not a third class.

| Class | Who sees the real request | Existing owners |
| --- | --- | --- |
| `public` | Every viewer sees the same payload | Matched-play CP, normal Stratagem use, ordinary unit/model choices, Primary progress |
| `owner_secret` | Actor sees options; opponent sees `hidden_decision` until the contract's reveal point | Secondaries until all players select, unit split during declarations, Beacon, Burden of Trust, Tactical When Drawn |

Redaction lives in **exactly one** shared adapters module. Projection,
event-stream, HTTP status, and transport metadata consume it. Option
counts, payload fields, event metadata, and derived projection data must
not leak hidden opponent information.

CP totals, CP ledger transactions, and normal Stratagem-use events stay
`public` unless a future hidden rule updates the adapter contract in the
same implementation PR.

### 3.3 Demand families (not one enum member per faction)

Demand families map T1–T5 onto §3.1 and §3.2. They are not a replacement
for the submission catalog's concrete `decision_type` rows.

| Family | Submission | Notes |
| --- | --- | --- |
| `stratagem_window_use` | **Split:** finite `use_stratagem` **or** parameterized `submit_stratagem_target_proposal` | T1 owns WHEN and the envelope. T6 owns the target-binding shape. Do not lift `use_stratagem` over the split. Unsupported handlers must not emit options |
| `finite_candidate_select` | `finite_option` | Engine lists current legal units, models, dice, cards, or observer/spotted pairs. T3 names the TARGET atoms |
| `finite_mode_pick` | `finite_option` | Named options: doctrines, vows, blessings, Ka'tah, Orders, oath, plague, Cabal ritual, Battle Focus manoeuvre, idols. T5 `mode_machine` is the token; this is the pick |
| `finite_binary_activate` | `finite_option` | Call/decline, unleash/decline, spend/decline, mark-done. Shadow in the Warp and Waaagh! are this family, not a new type each |
| `finite_optional_grant` | `finite_option` | Existing grant windows (`select_movement_action_grant`, `select_shooting_unit_grant`, `select_charge_declaration_grant`, `select_fight_unit_grant`, `select_stratagem_cost_modifier_option`). Pain-token spends already use these |
| `finite_enumerated_amount` | `finite_option` | Spend `0..N` when the engine can list every legal integer. Prefer this over a new quantity proposal |
| `parameterized_path` | `parameterized_proposal` | Extra move, surge, charge, pile-in, consolidate, scout. Requires `PathWitness`. Finite trigger select may precede it |
| `parameterized_placement` | `parameterized_proposal` | Reserves, Deep Strike, Cult Ambush marker/ingress, revival, deployment, redeploy, disembark, return-on-death, model materialization |
| `parameterized_declaration` | `parameterized_proposal` | Shooting and melee declarations |
| `secret_setup` | `finite_option` + `owner_secret` | Secondaries, unit split, Beacon, Burden of Trust, When Drawn. Already covered |
| `opponent_reaction` | Same as the wrapped family | T1 owns opponent WHEN. T6 does not add a third submission path |
| `nested_disambiguation` | Nested finite, not a top-level dispatch entry | The allowlist has **one** entry: `WEAPON_ABILITY_SELECTION_DECISION_TYPE`. Do not add nested types without a contract update |

Coverage today is "already a catalog surface" versus "contract delta"
versus "S3a must retain the choice". Unused-by-June is not `gap_no_kind`
when the catalog already owns the family.

### 3.4 Splits this survey must not flatten

| Flattened token | Published split |
| --- | --- |
| Stratagem use | Finite enumerated use **and** parameterized target binding |
| Battle Focus | T5 token ledger **and** T6 `finite_mode_pick` manoeuvre |
| Cult Ambush | T5 Resurgence spend (`finite_binary_activate`) **and** marker/ingress `parameterized_placement` |
| Greater Good | Finite observer/spotted pairs plus done; not parameterized coordinates; not an aura pick (T5) |
| Shadow in the Warp | Finite unleash/decline; Battle-shock sequence after unleash is engine-owned (T5 `protocol`) |
| "Spend" | T5 ledger identity **and** T6 enumerated amount versus a quantity contract delta |
| "Select a unit" | T3 TARGET clause **and** T6 finite candidates once listed |
| Extra Normal Move | Finite trigger **then** parameterized path |
| Command Re-roll | T1 `after_dice_roll` + OpportunityWindow; T3 bearer `player` + `dice_roll`; T6 finite `use_stratagem` |
| Hidden pending request | `owner_secret` plus `hidden_decision` placeholder; not a third engine path |

## 4. Existing catalog coverage (do not fork)

These families already have concrete rows in
[the submission catalog](../../DECISION_SUBMISSION_CATALOG.md). Track G
binds new consumers to them before minting types.

### 4.1 Finite surfaces that already cover T6 families

- Stratagem: `use_stratagem` (enumerable targets), including Command Re-roll
  in an `OpportunityWindow`.
- Faction-rule windows: `select_faction_rule_setup_option`,
  `select_faction_rule_battle_round_option`,
  `select_faction_rule_command_phase_start_option`,
  `select_faction_rule_shooting_phase_start_option`,
  `select_faction_rule_fight_phase_start_option`,
  `select_faction_rule_fight_phase_end_option`,
  `select_faction_rule_turn_end_option`.
- Grants and resource spends already on grant windows (Pain, Aspect Shrine
  override `select_dice_result_override`, Cult Ambush Resurgence).
- Ordinary play: movement/shooting/charge/fight unit and action selects,
  dice reroll, Feel No Pain, healing model, destruction reaction.
- Secret setup: `select_secondary_missions`, `select_unit_split_membership`,
  Beacon, Burden of Trust, When Drawn.

Waaagh! call/decline, Shadow unleash/decline, Greater Good mark/done,
Cabal ritual options, Orders, oath target, Nurgle's Gift plague, Templar
Vows, Blessings of Khorne, Code Chivalric, Ka'tah, and Malice Made Manifest
already sit on those finite faction-rule or grant windows. Do not add
named types for those display names.

### 4.2 Parameterized surfaces that already cover T6 families

- Path: `submit_movement_proposal` (`normal_move`, `advance`, `fall_back`,
  `surge_move`, `charge_move`, `pile_in`, `consolidate`, `scout_move`).
- Placement: reinforcement, Deep Strike, Strategic Reserves, Cult Ambush
  marker and `cult_ambush_placement`, healing revival, deployment,
  redeploy, disembark, return-on-death, catalog model materialization.
- Declaration: `submit_shooting_declaration`, `submit_melee_declaration`.
- Stratagem target: `submit_stratagem_target_proposal` with
  `stratagem_target_binding` (Insane Bravery, Fire Overwatch, Rapid
  Ingress, Heroic Intervention, Explosives, Counteroffensive, Crushing
  Impact, Epic Challenge).

### 4.3 Nested allowlist

`WEAPON_ABILITY_SELECTION_DECISION_TYPE` is the single documented nested
allowlist entry. A new nested family is a contract delta, not a silent
third path.

## 5. T5 crosswalk (decision shape only)

| Token / split | T6 family | Not T6 |
| --- | --- | --- |
| Battle Focus tokens | `finite_optional_grant` or `finite_enumerated_amount` on the existing ledger | Manoeuvre is `finite_mode_pick` (T5-HOLD-BATTLE-FOCUS-SPLIT, answered here) |
| Cult Ambush Resurgence | `finite_binary_activate` on `select_cult_ambush_resurgence` | Marker and ingress stay `parameterized_placement` |
| Shadow in the Warp | `finite_binary_activate` unleash/decline | Synapse range is T5 `aura_zone`; Battle-shock EFFECT is T2 |
| Greater Good | `finite_candidate_select` pairs plus done | Visibility to form a mark is T3 |
| Waaagh! | `finite_binary_activate` call/decline | `riled_up` is a T5 pulse, not this pick |
| Cabal | `finite_mode_pick` / finite ritual options already on Shooting-start | Not an integer spend pick unless S3a retains a pool (T5-HOLD-CABAL-SHAPE) |
| Pain / Yield / Blood Tithe / Flux / Aspect Shrine | Grant, override, or enumerated amount on the T5 token | Ledger identity stays T5 |
| Slaanesh pledge increment | Automatic T2 EFFECT unless S3a retains a pick | If a later threshold pick exists, it is `finite_mode_pick` (T5-HOLD-PLEDGE-SHAPE) |
| Miracle dice | Finite face select or existing override | Face pool stays T5 `specialized_face_pool` |
| Command points | Public `stratagem_window_use` and existing CP events | Not `FactionResourceLedger` |

## 6. Samples (paraphrase only)

Live [Core 15 Stratagems](https://www.40k.app/rules/15-stratagems):
Command Re-roll is a finite `use_stratagem` in an opportunity window after
a dice roll. Insane Bravery is a parameterized Stratagem target (pending
Battle-shock test, not already Battle-shocked). That is the
`stratagem_window_use` split, not two Core-named decision types.

Live [War Horde](https://www.40k.app/factions/orks/detachments/war-horde):
Waaagh! call or decline is `finite_binary_activate` on the existing
Command-start faction-rule window. Stratagem WHEN remains T1. `riled_up`
is not this decision.

Live [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion):
Malice Made Manifest is `finite_candidate_select` on the existing
Fight-start faction-rule window.

Greater Good marks are finite observer/spotted option IDs plus done, not
a coordinate proposal.

Those samples do not add axes.

## 7. Gap list for Track G

### 7.1 Families that exist and must not be forked

Finite faction-rule windows, grant windows, `use_stratagem`, Stratagem
target proposals, PathWitness movement, placement proposals, and
owner-secret setup rows already exist. A new army-rule pick that is
"select one named option" or "select one listed unit" binds to those
surfaces.

### 7.2 Contract deltas (planning evidence, not this PR)

A new `decision_type`, finite option family, `proposal_kind`, interaction
kind, nested allowlist entry, or visibility class must update
[the adapter contract](../../ADAPTER_DECISION_CONTRACT.md) in the **same**
Track G implementation PR. This survey does not edit that file.

| Delta ID | Demand | Why it is a delta |
| --- | --- | --- |
| `T6-DELTA-NEW-FAMILY` | Any new concrete `decision_type` or `proposal_kind` | Existing AGENTS / contract policy |
| `T6-DELTA-HIDDEN-STRATAGEM` | Hidden Stratagem use or hidden CP | Contract already requires an update before implementation; current CP/Stratagem events are public |
| `T6-DELTA-HIDDEN-HEALING` | Hidden healing or revival choice | Healing is public in the current scope |
| `T6-DELTA-HIDDEN-SETUP` | Hidden deployment, reserve, Cult Ambush, or faction-rule setup beyond existing `owner_secret` rows | Contract already names these as future updates |
| `T6-DELTA-UNBOUNDED-SPEND` | Spend any number of a T5 integer when `0..N` cannot be enumerated | `quantity_selection` is an interaction kind; there is no catalog quantity `decision_type` today. Prefer `finite_enumerated_amount` |
| `T6-DELTA-NESTED-ALLOWLIST` | A nested decision other than weapon-ability disambiguation | Allowlist has one entry |

Battle Focus manoeuvre is **not** automatically a new `decision_type`. If
S3a retains a named manoeuvre list, it is `finite_mode_pick` on an
existing faction-rule or grant window unless that window cannot carry the
choice.

### 7.3 Families T6 must not steal

- WHEN windows and Stratagem envelopes remain T1.
- EFFECT families remain T2, including automatic resource increments with
  no player pick.
- Bearer, TARGET and condition atoms remain T3.
- Construction constraints remain T4. Deployment and muster *decisions*
  already in the catalog stay those catalog rows.
- Ledger identity and runtime-fit remain T5.

## 8. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| T6-HOLD-APP-DECISION | App 946 operative text is not retained for every rule's player choice | S3a, then FM0 |
| T6-HOLD-PROFILE-STALENESS | 1,025 profiles dated 2026-06-21; 40 admitted views at App-data 946 | S3a / S3d |
| T6-HOLD-STRATAGEM-KIND | Per-Stratagem finite versus parameterized target is S3a using the real target policy, not stored `target_kind` | S3a / Track G |
| T6-HOLD-UNBOUNDED-SPEND | "Spend any number" of Yield (and similar) may be enumerable `0..N` or a quantity contract delta | S3a, then Track G |
| T5-HOLD-BATTLE-FOCUS-SPLIT | Token ledger versus manoeuvre pick; T6 closes the pick as `finite_mode_pick` | Track G |
| T5-HOLD-PLEDGE-SHAPE | Unbound Arrogance increment is not a pick; a later threshold pick would be `finite_mode_pick` | S3a |
| F-ORK-01 | Orks v946 Waaagh! and War Horde choices may be new | FM0.5 |

## 9. What "T6 delivered to Track G" means

Track G's decision-kind and viewer-visibility work may be designed. It
has:

- the closed submission kinds (`finite_option`,
  `parameterized_proposal`) and the hold that `hidden_decision` is
  redaction only;
- the closed visibility classes (`public`, `owner_secret`) and the
  single shared redaction module;
- demand families that map T1–T5 onto those axes without a type per
  display name;
- the Stratagem use split (finite enumerated versus parameterized
  target) without a 1,025-row histogram;
- the T5 crosswalk for Battle Focus, Cult Ambush, Shadow, Greater Good,
  pledge, and spend-any-number;
- the adapter-contract delta list for hidden families, unbounded spend,
  and nested allowlist growth;
- the hold that per-entity App 946 choice counts wait on S3a.

T6 does not add decision types, change the nested allowlist, edit the
adapter contract, or emit `semantic_demand_matrix.json`. FM0 regenerates
that matrix from retained pages and reconciles it with this survey.

Track T's six pre-gate surveys are now written. FM0 still owns the
demand matrix.
