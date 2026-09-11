# T5 — Resource and state-token taxonomy

[Taxonomy index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [T2 effect taxonomy](T2_EFFECT_TAXONOMY.md) · [T3 bearer/target/condition grammar](T3_BEARER_TARGET_CONDITION_GRAMMAR.md) · [T4 army-construction grammar](T4_ARMY_CONSTRUCTION_GRAMMAR.md) · [T6 decision-kind taxonomy](T6_DECISION_KIND_VISIBILITY.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This survey is Track T item T5. It is planning evidence delivered read-only to
Track G's shared resource-ledger family. It does not implement engine
semantics, add ledger kinds, populate faction records, or admit content. FM0
regenerates resource and state-token rows from the retained content set and
reconciles them with this document.

Machine-readable catalog: [`t5_resource_state_tokens.json`](t5_resource_state_tokens.json).

## 1. Purpose and delivery contract

T5 closes which named army-rule tokens share a typed `FactionResourceLedger`
or `UnitResourceLedger`, and which remain bespoke state machines under the
named-handler budget.

A token is not a display name. "Power From Pain" and the roadmap's "Pain"
are one token. "Synapse/Shadow" is two tokens on one reporting group.
Lifting `resource_gain_spend` over every named pool hides that split (the
T1-001 failure mode applied to ledgers). T2 still owns the gain/spend
EFFECT. T3 still names condition tokens. T5 only answers: same ledger
service, or not.

**Track G implements typed ledger kinds and engine-owned mutation only.**
It must not add speculative ledger kinds from this gap list without a real
source-backed consumer in the same PR. Existing named army-rule handlers
stay on the budget until a later order migrates a reusable sub-effect.

T1 still owns WHEN (including when a Waaagh! is called). T2 still owns
EFFECT families, including `resource_gain_spend`, `persisting_status`,
`doctrine_mode`, and `order_issue`. T3 still owns bearer, TARGET and
condition atoms, including `state_token`. T4 still owns related-army pacts
and construction. T6 delivered finite versus parameterized spend, pick
and target decisions in
[T6_DECISION_KIND_VISIBILITY.md](T6_DECISION_KIND_VISIBILITY.md).

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Reporting groups | 28 faction reporting groups; 40 admitted guides |
| Army-rule headings | Current headings from those 40 guides |
| Detachment headings | All **506** App 946 audit listing rows (T4 unique names **270**) |
| T2 EFFECT demand | `resource_gain_spend` **60** June Stratagem rows |
| T3 condition demand | `state_token` **30** June rows; T3 named tokens in T3 §3.5 and this catalog §4.2 |
| Operative samples | Live [War Horde](https://www.40k.app/factions/orks/detachments/war-horde), [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion), [Adepta Sororitas](https://www.40k.app/factions/adepta-sororitas), [Drukhari](https://www.40k.app/factions/drukhari) |
| Engine inspection | Read-only: `FactionResourceLedger`, `UnitResourceLedger`, `CommandPointLedger`, named-handler budget dated 2026-07-03 |

The roadmap's "28 army rules" is the reporting-group count. The parenthetical
list is **27 names** because "Pain" and "Power from Pain" are one token and
"Synapse/Shadow" is two. T5 does not explode that list into 28 engine
services.

September audits store Enhancement and Stratagem **names and costs** only.
Per-entity App 946 army-rule transcription is **S3a / FM0**. T5 still
closes the *split*.

This document does not copy bulk operative text. Sampled clauses are
paraphrased and linked. Exact transcription remains an F00/S3a obligation.

Classification rules that a token hit-list would flatten:

| Flattened token | Published split |
| --- | --- |
| Pain and Power From Pain | one token `pain` |
| Synapse/Shadow | two tokens: `synapse` is `aura_zone`; `shadow_in_the_warp` is a once-per-battle `protocol` |
| For the Greater Good as an aura | observer/spotted `designated_target` **and** shooting-phase `protocol`; visibility is T3 |
| Battle Focus token spend vs manoeuvre pick | ledger half **and** T6 `finite_mode_pick` |
| Cult Ambush markers vs Resurgence points | placement machine **and** integer ledger |
| Cabal ritual attempt vs a point pool | current named handler is the ritual machine |
| "Waaagh! is active" and "riled up" | two pulse tokens; they do not share a ledger |
| Miracle dice | face pool, not an integer `FactionResourceLedger` kind |
| Command points | Core `CommandPointLedger`, not `FactionResourceLedger` |
| Related-army Pact headings | T4 construction, not T5 ledgers |
| Blessings of Khorne and Blood Tithe | mode pick **and** Khorne Daemonkin BTP ledger |
| Shadow of Chaos and Flux tokens | army aura **and** Scintillating Legion integer spend |
| Thrill Seekers and Slaanesh pledge | army mode **and** Coterie pledge counter |
| Pain tokens and Combat Drugs | army integer pool **and** Spectacle of Spite heading (shape unknown) |
| Miracle dice and Sacred Rites | face pool **and** Army of Faith heading (shape unknown) |
| Strands of Fate as a missing army heading | current **Seer Council** detachment heading; shape unknown |

## 3. Closed split

### 3.1 Closed runtime-fit axis

One token may carry more than one fit. Do not lift a single fit over a
split (the T1-001 failure mode).

| Fit | Shares a typed ledger? | Meaning |
| --- | --- | --- |
| `faction_integer_ledger` | yes: `FactionResourceLedger` | Gain, spend, cap an army-level integer by `resource_kind` |
| `unit_integer_ledger` | yes: `UnitResourceLedger` | Gain, spend, cap a unit-level integer by `resource_kind` |
| `core_command_point_ledger` | yes: `CommandPointLedger` | Core CP only; do not fold into `FactionResourceLedger` |
| `specialized_face_pool` | no | Countable dice that keep rolled faces |
| `pulse_flag` | no | On/off window ("active", "riled up") |
| `mode_machine` | no | Doctrine, vow, order, pact, blessing, ritual, or manoeuvre pick |
| `designated_target` | no | Remember selected subjects (Oath target; observer/spotted pairs) |
| `aura_zone` | no | Contagion, Synapse, Nurgle’s Gift, Shadow of Chaos range |
| `placement_reserve` | no | Markers, off-board setup, reserve identity |
| `protocol` | no | Once-per-battle or phase-scoped resolution (Reanimation, Gate, Shadow unleash, Greater Good shooting-phase done) |
| `composition` | no | Kill Team, Assigned Agents, Drones |
| `contextual_status` | no | T3-named unit status that is not the army pool |

A token shares a `ResourceLedger` only when a listed fit is
`faction_integer_ledger` or `unit_integer_ledger`. Same fit does not imply
the same `resource_kind`. Same T3 token name does not imply a shared
ledger. `pulse_flag` is not a spend pool.

### 3.2 Existing engine surfaces

| Surface | What it already does |
| --- | --- |
| `FactionResourceLedger` | Per-player integer totals and gain/spend transactions |
| `UnitResourceLedger` | Per-unit integer totals and starting allocations |
| `CommandPointLedger` | Core CP gain, spend and refund |
| Named-handler budget | 23 pre-WS14 army-rule execution IDs, package date 2026-07-03 |

Stored integer kinds already on a ledger (do not invent a second catalogue):

| `resource_kind` | Token | Fit |
| --- | --- | --- |
| `drukhari_pain_token` | `pain` | `faction_integer_ledger` |
| `leagues_of_votann_yield_points` | `yield` | `faction_integer_ledger` |
| `battle_focus_token` | `battle_focus` token half | `faction_integer_ledger` |
| `resurgence_points` | `cult_ambush` point half | `faction_integer_ledger` |
| `aeldari:aspect-shrine-token` | `aspect_shrine_token` | `unit_integer_ledger` |

Miracle dice live on the Adepta Sororitas named handler as a face pool.
Cabal of Sorcerers lives on the Thousand Sons named handler as a ritual
attempt machine, not as a stored integer kind.

## 4. Closed token set

### 4.1 Roadmap army-rule tokens

Ledger-fit is the reusable half only. Named handlers may still orchestrate
the token.

| Token ID | Army-rule heading | Runtime fits | Named handler today |
| --- | --- | --- | --- |
| `miracle_dice` | Acts of Faith | `specialized_face_pool` | yes |
| `pain` | Power From Pain | `faction_integer_ledger` (`drukhari_pain_token`) | yes |
| `blessings_of_khorne` | Blessings of Khorne | `mode_machine` | yes |
| `battle_focus` | Battle Focus | `faction_integer_ledger` (`battle_focus_token`) **and** `mode_machine` | yes |
| `waaagh` | Waaagh! | `pulse_flag` | yes |
| `strands_of_fate` | Strands of Fate (Seer Council) | unknown until S3a | no army-rule heading; detachment grain |
| `yield` | Prioritised Efficiency | `faction_integer_ledger` (`leagues_of_votann_yield_points`) | yes |
| `cabal` | Cabal of Sorcerers | `mode_machine`; integer kind only if S3a retains a pool | yes; ritual attempts |
| `doctrina` | Doctrina Imperatives | `mode_machine` | yes |
| `dread` | Harbingers of Dread | `mode_machine` | yes |
| `oath_of_moment` | Oath of Moment | `designated_target` | yes |
| `vows` | Templar Vows | `mode_machine` | yes |
| `katah` | Martial Ka’tah | `mode_machine` | yes |
| `orders` | Voice of Command | `mode_machine` | yes |
| `kill_teams` | Kill Teams | `composition` | no pre-WS14 army-rule row |
| `cult_ambush` | Cult Ambush | `faction_integer_ledger` (`resurgence_points`) **and** `placement_reserve` | yes |
| `reanimation` | Reanimation Protocols | `protocol` | yes |
| `synapse` | Synapse | `aura_zone` | yes |
| `shadow_in_the_warp` | Shadow in the Warp | `protocol` (once-per-battle unleash and Battle-shock sequence) | yes |
| `greater_good` | For the Greater Good | `designated_target` **and** `protocol` | yes |
| `gate_of_infinity` | Gate of Infinity | `protocol` | yes |
| `assigned_agents` | Assigned Agents | `composition` | no pre-WS14 army-rule row |
| `code_chivalric` | Code Chivalric | `mode_machine` | yes |
| `thrill_seekers` | Thrill Seekers | `mode_machine` | yes |
| `dark_pacts` | Dark Pacts | `mode_machine` | yes |
| `nurgles_gift` | Nurgle’s Gift (Aura) | `aura_zone` | yes |
| `shadow_of_chaos` | The Shadow of Chaos | `aura_zone` | yes |

Pinned Tyranids and T’au handlers are the crosswalk for those two
tokens. Shadow in the Warp offers unleash or decline, records
already-unleashed, and then runs a Battle-shock sequence; Synapse range
used in that sequence is the `synapse` token, not an aura half of Shadow.
For the Greater Good stores observer/spotted pairs and Shooting-phase
completion; visibility used to form a mark is T3, not `aura_zone`.
Unleash timing remains T1. Decision shape is T6 `finite_binary_activate`
for Shadow and T6 finite mark/done for Greater Good. App 946 operative
text is not retained (`T5-HOLD-APP-ARMY-RULE`). An aura-shaped source
page would be an unresolved source/runtime distinction, not a closed
aura-only fit.

`strands_of_fate` is not a current **army-rule** heading. Current Aeldari /
Harlequins / Ynnari army headings are Battle Focus and Disparate Paths.
It **is** a current App 946 **Seer Council** detachment heading. June
Stratagems do not spend or gain it. Do not mint a ledger from the
roadmap name or from the heading alone.

### 4.2 T3-named contextual tokens

T3 named these. They are not army-rule pools. They do not share a
`ResourceLedger` with the army token that sits near them.

| Token ID | June Stratagem hits | Runtime fit | Notes |
| --- | ---: | --- | --- |
| `waaagh` | 7 | `pulse_flag` | Same ID as §4.1; still not a ledger |
| `righteous` | 6 | `contextual_status` | Acts of Faith adjacent; not miracle dice |
| `afflicted` | 4 | `contextual_status` | Nurgle’s Gift adjacent; not the aura machine |
| `halo_override` | 4 | `contextual_status` | Doctrina adjacent; not the imperative pick |
| `desperate_pact` | 3 | `contextual_status` | Dark Pacts adjacent |
| `focus_of_hatred` | 2 | `contextual_status` | designated-hatred status |
| `blessed` | 2 | `contextual_status` | not a Blessings-of-Khorne pick |
| `malevolent` | 1 | `contextual_status` | Cabal / Thousand Sons adjacent |
| `shroud_of_chaos` | 1 | `contextual_status` | not army-rule `shadow_of_chaos` |
| `riled_up` | 0 | `pulse_flag` | War Horde Enhancement; F-ORK-01. Not the Waaagh! ledger |

June `state_token` assignments remain **30** as published by T3. T5 does
not recount them.

### 4.3 Core and extra App 946 tokens

| Token ID | Source | Runtime fit |
| --- | --- | --- |
| `command_points` | Core Stratagems / 15.01 | `core_command_point_ledger` only |
| `aspect_shrine_token` | Aeldari datasheet token | `unit_integer_ledger` (`aeldari:aspect-shrine-token`) |
| `drones` | T’au heading | `composition` |
| `da_boss` | Orks v946 heading | unknown until F-ORK-01 / S3a |
| `blood_tithe` | Khorne Daemonkin (detachment) | `faction_integer_ledger`; no kind yet |
| `flux_token` | Fates In Flux (detachment) | `faction_integer_ledger`; no kind yet |
| `slaanesh_pledge` | Pledges to the Dark Prince (detachment) | `faction_integer_ledger`; T5-HOLD-PLEDGE-SHAPE |
| `combat_drugs` | Spectacle of Spite (detachment) | unknown; not `pain` |
| `sacred_rites` | Army of Faith (detachment) | unknown; not `miracle_dice` |

Orks "Unstable energies" and "Special Move Types" are movement EFFECT
demand (T2), not ledgers. Detachment inventory and false friends are §4.5.

### 4.4 Headings T5 must not steal

T4 owns related-army and construction headings: Disparate Paths, Daemonic
Pact, Pact of Blood, Pact of Excess, Pact of Decay, Pact of Sorcery,
Cults of the Dark Gods, Corsairs and Travelling Players, Super-heavy
Walker, Dreadblades, Freeblades, Bondsman, Space Marine Chapters.

Chapter overlay headings (Heirs of Sigismund, Sons of Sanguinius, The
Unforgiven, Ravenwing, Deathwing, Sons of Russ, Sagas, Curse of the
Wulfen) are not extra `ResourceLedger` kinds. S3a records whether any
is a distinct runtime machine.

### 4.5 Detachment pool inventory

T5's first pass followed the roadmap army-rule parenthetical and missed
detachment-owned pools. This inventory closes that hole.

Method: every App 946 audit `Rule headings` line (506 listing rows, 40
views, T4 unique names 270) plus a June scan of all 1,025
`when`/`target`/`effect` descriptors for spend, gain, increment, discard,
or named-token language. September audits still have no EFFECT column.
Detachment rule bodies remain S3a. This is not a new T2 recount; the 60
`resource_gain_spend` rows stay T2.

#### Confirmed detachment integer pools

June text is explicit gain, spend, or increment. No `resource_kind`
exists today. Track G may bind `FactionResourceLedger` only with a real
consumer.

| Token ID | App heading | Listing | June Stratagem demand | Fit |
| --- | --- | --- | --- | --- |
| `blood_tithe` | Blood Tithe | [Khorne Daemonkin](https://www.40k.app/factions/blood-legions/detachments/khorne-daemonkin) (Blood Legions listing; June row filed under `world-eaters`) | A WORTHY SKULL: gain D3 BTP, then spend BTP | `faction_integer_ledger` |
| `flux_token` | Fates In Flux | [Scintillating Legion](https://www.40k.app/factions/chaos-daemons/detachments/scintillating-legion) | four rows spend a Flux token (Impossible Eclipse, Pyrogenesis, Flickering Reality, Delirium Unmade) | `faction_integer_ledger` |
| `slaanesh_pledge` | Pledges to the Dark Prince | [Coterie of the Conceited](https://www.40k.app/factions/emperors-children/detachments/coterie-of-the-conceited) (also Legions of Excess) | Unbound Arrogance: increase the pledge by 1 | `faction_integer_ledger`; thresholds may also be a mode (T5-HOLD-PLEDGE-SHAPE) |

`blood_tithe` is not Blessings of Khorne. `flux_token` is not Shadow of
Chaos. `slaanesh_pledge` is not Thrill Seekers and is not Soulforged
Warpack "Desperate Pledge" (that row invokes a contract).

#### Heading-only pool suspects (no June Stratagem spend)

| Token ID | App heading | Listing | Fit |
| --- | --- | --- | --- |
| `strands_of_fate` | Strands of Fate | [Seer Council](https://www.40k.app/factions/aeldari/detachments/seer-council) (also Harlequins, Ynnari) | unknown; T5-HOLD-STRANDS |
| `combat_drugs` | Combat Drugs | [Spectacle of Spite](https://www.40k.app/factions/drukhari/detachments/spectacle-of-spite) | unknown; not `pain` |
| `sacred_rites` | Sacred Rites | [Army of Faith](https://www.40k.app/factions/adepta-sororitas/detachments/army-of-faith) | unknown; not `miracle_dice` |

#### Not a pool

These headings matched a loose name scan. They are not new
`ResourceLedger` kinds.

| Heading | Listing examples | Why not a ledger |
| --- | --- | --- |
| Combat Doctrines / Mastered Doctrines | Gladius Task Force, Blade of Ultramar | T2 `doctrine_mode` |
| Idols of Khorne | Cult of Blood | mode pick (Brazen Idol) |
| Synaptic Imperatives / Higher Imperatives | Synaptic Nexus, Talons of the Norn Queen | mode pick |
| Mission Tactics / Deathwatch Mission Tactics | Black Spear; Ordo Xenos | mode pick |
| Marks of Chaos | Pactbound Zealots | keyword / mark select |
| Focus of Hatred | Veterans of the Long War | T3 contextual token |
| Vowed Target / Oath of Reclamation | Inner Circle; Reclamation Force | designated target; not army `oath_of_moment` |
| Command / Annihilation / Hypermotility Protocols | Awakened Dynasty and other Necron listings | protocol or mode names; not Reanimation |
| Power Matrix | Canoptek Court | no June spend; spatial until S3a |
| Loci of Power | Lords of the Warp | no June spend; mode until S3a |
| Soul Forge Boons / Debt to the Soul Forge | Cult of the Arkifane; Soulforged Warpack | no integer spend; contract invoke is not `slaanesh_pledge` |
| Infernal Pacts / Warpmeld Sacrifice | Changehost of Deceit; Warpmeld Pact | T4-adjacent or sacrifice; not a point pool |
| Valour’s Reward | Questoris Companions | no June spend; reward table until S3a |
| Red Thirst | Liberator Assault Group | status, not a counter |
| Creeping Dread (Aura) | Null Maiden Vigil | aura |
| Contracted Harvest | Kabalite Agonysts | contract status |
| Malefic Surge | Infernal Lance | T2 `persisting_status` |
| THE STAR CHILDREN’S BLESSINGS | Final Day | not Blessings of Khorne |
| Angelic Judgement | Chorus of Condemnation | not a Judgement-token ledger |
| Order | Armoured Infantry | army `orders` token, not a new kind |
| Powers of da Waaagh! | Wurrband | not the army `waaagh` pulse |
| A Perfect Ambush | Host of Ascension | not Cult Ambush Resurgence points |
| War-form Mantles / Hyper-adaptations | Lords of the Forge; Invasion Fleet | mode picks |
| Boons of the Brood | Serpent’s Brood | not a ledger |
| Shadow Masters / Interlocking Tactics | shared Space Marine listings | not pools |

No other June abbreviation (`BTP`, `YP`, Flux token, Pain token, Miracle
dice, Aspect Shrine token, pledge increment) names a fourth new pool. `YP`
is `yield`. Pain, Miracle dice, and Aspect Shrine tokens are already in
§4.

## 5. Named-handler budget versus this split

The Phase 17I budget (2026-07-03) approves **23** army-rule named
handlers. That is not a licence to keep integer spend off
`FactionResourceLedger` after a real consumer can move it.

| Budget fact | T5 reading |
| --- | --- |
| 23 army-rule execution IDs | Named orchestrators may remain |
| Pain, Yield, Battle Focus tokens, Resurgence points already use ledger kinds | Track G binds those kinds; do not fork |
| Miracle dice, Blessings, Waaagh!, Cabal rituals, Oath, Orders, Doctrina, Ka’tah, Vows, Dread, Dark Pacts, Thrill Seekers, Reanimation, Gate, Synapse, Shadows, Gift, Greater Good | stay bespoke |
| Kill Teams, Assigned Agents | composition; no pre-WS14 army-rule budget row |
| Integer half of a split token | may move onto a ledger without deleting the named orchestrator |

T5 does not change the budget. A later PR that adds a named handler still
needs the bespoke-subsystem rubric in `AGENTS.md`.

## 6. Samples

Live [War Horde](https://www.40k.app/factions/orks/detachments/war-horde):
army Waaagh! is a pulse. Enhancements use `riled_up`. Those are two tokens.
Get Stuck In is a T2 EFFECT.

Live [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion):
detachment clauses gate on Shadow of Chaos. That is `shadow_of_chaos`
(`aura_zone`), not `shroud_of_chaos` and not a ledger.

Live [Adepta Sororitas](https://www.40k.app/factions/adepta-sororitas):
Acts of Faith uses miracle-dice faces. That is `miracle_dice`, not
`pain` and not CP.

Live [Drukhari](https://www.40k.app/factions/drukhari):
Power From Pain is the `pain` integer pool already stored as
`drukhari_pain_token`.

Those samples do not add axes.

## 7. Gap list for Track G

### 7.1 Kinds that exist and must not be forked

`drukhari_pain_token`, `leagues_of_votann_yield_points`,
`battle_focus_token`, `resurgence_points`,
`aeldari:aspect-shrine-token`, and Core `CommandPointLedger` already
exist. Unused-by-June-Stratagem is not `gap_no_kind`.

### 7.2 Splits that require a real consumer before a new kind

- Battle Focus manoeuvre pick (`finite_mode_pick` in [T6](T6_DECISION_KIND_VISIBILITY.md)), distinct from the token ledger
- Cult Ambush marker placement, distinct from Resurgence points
- Cabal ritual machine; mint a Cabal integer kind only if S3a retains a pool
- Miracle-dice face operations (discard, set, substitute) on the existing pool
- Overlay chapter machines, if S3a shows a distinct runtime token
- Blood Tithe, Flux tokens, and the Slaanesh pledge counter (kinds do not exist)
- Seer Council Strands of Fate, Combat Drugs, and Sacred Rites, only after S3a retains a pool shape
- Pledge thresholds versus the integer increment (T5-HOLD-PLEDGE-SHAPE)

### 7.3 Families T5 must not steal

- WHEN windows remain T1, including Waaagh! call timing.
- EFFECT families remain T2, including `resource_gain_spend`.
- Bearer, TARGET and condition atoms remain T3, including `state_token`.
- Related-army pacts and DP remain T4.
- Finite versus parameterized spend and pick decisions are closed in
  [T6](T6_DECISION_KIND_VISIBILITY.md).

## 8. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| T5-HOLD-APP-ARMY-RULE | App 946 army-rule operative text is not retained for every heading | S3a, then FM0 |
| T5-HOLD-STRANDS | Strands of Fate is a Seer Council heading; pool shape is not retained | S3a |
| T5-HOLD-CABAL-SHAPE | Current handler is ritual attempts; June/T2 wording still says Cabal spend | S3a |
| T5-HOLD-PLEDGE-SHAPE | Unbound Arrogance increments an integer; thresholds or picks may also be a mode. T6 closes a later pick as `finite_mode_pick` | S3a |
| T5-HOLD-DETACHMENT-OPERATIVE | App 946 detachment rule bodies are not retained; this inventory is headings plus June Stratagem text | S3a, then FM0 |
| T5-HOLD-BATTLE-FOCUS-SPLIT | Token ledger versus manoeuvre pick. T6 closes the pick as `finite_mode_pick` | Track G |
| T5-HOLD-CULT-AMBUSH-SPLIT | Markers versus Resurgence points | Track G |
| T2-HOLD-RESOURCE-SPLIT | Answered here for the ledger question; T2 EFFECT counts stay T2 | this survey |
| F-ORK-01 | Orks v946 Waaagh!, Da Boss and "riled up" may be new | FM0.5 |

## 9. What "T5 delivered to Track G" means

Track G's shared-ledger work may be designed. It has:

- the closed runtime-fit axis;
- one token ID for Pain / Power From Pain, and two for Synapse / Shadow;
- the map of which tokens already have `resource_kind` values;
- the hold that Miracle dice, Cabal rituals, pulses, modes, auras,
  placement, protocols and composition stay off integer ledgers;
- T3 contextual tokens classified as not sharing those ledgers;
- the hold that per-entity App 946 counts wait on S3a;
- the detachment inventory: 506 listing headings, three new integer
  pools (`blood_tithe`, `flux_token`, `slaanesh_pledge`), and the
  heading-only suspects that are not extra ledgers.

T5 does not add kinds, change named-handler approvals, or emit
`semantic_demand_matrix.json`. FM0 regenerates that matrix from retained
pages and reconciles it with this survey.
