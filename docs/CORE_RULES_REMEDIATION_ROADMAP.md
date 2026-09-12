# CORE V2 Core Rules Remediation Roadmap

## Scope and authority

This roadmap covers only Warhammer 40,000 11th Edition Core Rules categories
01–25. Factions, faction detachments, faction datasheets, and the out-of-scope
content listed in `AGENTS.md` are excluded.

The separate [Faction Rules Remediation Roadmap](FACTION_RULES_REMEDIATION_ROADMAP.md)
covers faction rules, detachments, datasheets, points and model/equipment fields.
Its [readable faction guides](FACTION_SUPPORT.md) distinguish source, execution,
fieldability and playability evidence. Shared Core Rules prerequisites remain
owned by this roadmap.

The retained 40k.app snapshot is the exhaustive Core Rules corpus for the
completed portion of this audit. Its immutable observations retain historical
policy ID
`core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26`.
Order 11 supersedes that provider-specific policy for new observations with
`core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`, which
recognizes both 40k.app and Game Datamissions as non-affiliated maintained
direct App-data mirrors. Evidence controls in this order:

1. Direct official-App evidence when an actual App/maintained-mirror divergence
   is observed.
2. Complete, hash-pinned observations from either named maintained direct
   App-data mirror under the owner-approved authority policy.
3. Hash-pinned official Games Workshop PDFs for history and material the App
   corpus does not replace.

Maintained App wording supersedes an older PDF where they differ. The site is
still identified honestly as a non-affiliated hosting provider, never falsely
as Games Workshop-owned, and the live website is never queried by the runtime
engine. Reviewed source artifacts remain the loader boundary.

On 2026-09-02 the owner identified
[Game Datamissions](https://game-datamissions.com/11th/rules/changelog) as a
second maintained browser mirror generated from direct Warhammer App data.
For roadmap planning it is co-equal with 40k.app, not secondary interpretation;
waiting for a later 40k.app refresh is unnecessary, though matching observations
remain useful corroboration. App-data version 931, dated 2026-08-26, contains 19
listed Core Rules changes representing 18 distinct obligations because the
01.02.06 Splitting Units erratum duplicates the same operative change. Version
946, dated 2026-09-02, separately exposes 18.04.01 Rapid Disembark And
Limitations. The official
[August 26 Warhammer 40,000 update](https://www.warhammer-community.com/en-gb/articles/b4zj2o7u/the-warhammer-40000-august-update-everything-you-need-to-know/)
and its Universal Rules Updates v1.1 independently establish Assault and Shock
Disembark as new Core Rules concepts; the complete numbered statements and FAQ
snapshot are available through the Game Datamissions App-data changelog.

This roadmap maps all 18 distinct v931 obligations and the v946 Rapid
Disembark obligation. Order 11 (`S-MIRRORS`) now supplies their source-
governance prerequisite: every retained implementation observation must pin
provider, URL, App-data version or observation timestamp, transcription
SHA-256, and source-observation fingerprint. Shared source-package validation
fails closed when named mirrors disagree for the same stable rule ID and
App-data version, pending comparison with the official App.

P00 is PR #405. It changes provenance and planning only; it does not change
gameplay semantics. The retained official Core Rules PDF has SHA-256
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.
The retained 40k.app observation is dated 2026-08-25.

Only one roadmap PR is opened at a time. It is reviewed and merged before work
starts on the next PR. Debugging must not use an interactive debugger.

## Status and evidence gates

- `APP-AUTHORITY`: the owner-approved policy and hash-pinned category
  observation establish a maintained direct App-data mirror as the controlling
  source and category locator for the planned requirement. Existing findings
  retain their 40k.app evidence under P00. The v931/v946 findings additionally
  require S-MIRRORS, now merged, before implementation.
  Every implementation PR must still retain an exact operative source row with
  stable source ID, provider, URL, App-data version or observation timestamp,
  transcription hash, and immutable source-observation fingerprint before
  changing semantics.
- `APP-DRIFT`: a repository row or older PDF differs from current maintained
  App wording; replace or narrow the stale row in the owning PR.
- `APP-INTERNAL-DRIFT`: the maintained App corpus contains a numbering or
  cross-reference inconsistency. Bind behavior by stable title and complete
  operative text; ask the user only if that cannot resolve the inconsistency.
- `EXCEPTION-PAUSE`: implementation pauses only for an observed official-App
  divergence, incomplete or ambiguous mirror text, irreducible internal App
  inconsistency, an unresolved target-version cutoff, or a later owner decision
  that withdraws or narrows the source-authority policy.
- `REVALIDATE`: no standalone implementation PR is currently planned, but the
  category must pass the final audit.
- `FINAL-CERTIFICATION`: all implementation PRs are merged and a fresh
  cross-category audit must certify all 25 categories against one selected,
  hash-pinned maintained-App snapshot before the compliance claim is allowed.

Every PR below also depends on P00 being merged. The numbered order is the
execution order. The pinned direct App-data mirror observations and
owner-approved policy establish project authority for planning, but do not
substitute for the exact operative source row and source-observation
fingerprint required in each implementation PR. The later mirror-policy
expansion recorded above must land before a v931/v946 finding is implemented.
Only an `EXCEPTION-PAUSE` stops an otherwise dependency-ready PR. There is
still only one open roadmap PR.

`T-TRANSPORT` is defined conservatively as P18A, P18C, P18D, P18E, P18F, P18G, P18H, and P18B all
merged. The user may approve a narrower definition before P20, but it must be
recorded in this document rather than inferred during implementation.

`S-MIRRORS` is the source-governance PR immediately after P18C. It is
a documentation/evidence prerequisite, not a gameplay-remediation PR or a
closable implementation finding. It owns `docs/CORE_RULES_SOURCE_POLICY.md`,
the maintained-mirror comparison/audit generator, and shared source-package
mirror-metadata validation. The repository source-governance owner closes it
only after the committed policy and validation evidence name both maintained
direct App-data mirrors, enforce the complete evidence tuple for either
provider, and fail closed on a co-versioned disagreement pending official-App
comparison.

## Canonical finding identity

Closable finding IDs are stable, unique closure keys. A table row that resolves
several findings lists each complete ID separated by a comma; slash notation
and prose suffixes are not finding IDs. A separately identified family ID is a
non-closable grouping label, not a finding ID or closure key.

- `C14-01` owns the shared objective-geometry foundation. `C12-01` owns the
  Objective Consolidation consumer of that foundation, and `C12-02` owns its
  stale source wording and remaining movement/final-position semantics. These
  three IDs form one cross-category dependency family but close independently.
- `C11-02` owns ordinary Charge-roll Command Re-roll support. `C15-05` owns the
  corresponding Heroic Intervention support. They share P15E but remain
  independently auditable findings.
- `C24-03` is the non-closable family ID for duplicated-ability support. Its unique
  child findings are `C24-03A` for source-instance identity/schema and
  `C24-03B` for the player-facing decision/execution path. The parent family is
  satisfied only when both children are closed.
- `C18-03` remains limited to 18.05 Emergency Disembark hazard-before-placement
  ordering. `C18-04` owns 18.06 Assault Disembark, `C18-05` owns 18.07 Shock
  Disembark, and `C18-06` owns the 18.04.01 Rapid Disembark ingress-restriction
  propagation implemented with P20. Closing P18C does not close category 18.
- `C01-02` owns generic 01.02.06 unit splitting and its duplicated v931 erratum;
  the duplicate changelog entry does not create a second finding. `C01-03` owns
  the distinct embarked-ability authority required by the v931 FAQ.
- `C04-01` is widened from a shooting-only repair to the generic target
  no-longer-eligible/viable replacement service. `C11-03` owns its Charge
  consumer when a post-selection modifier changes maximum Charge distance.
  `C04-02` and `C04-03` independently own critical-hit success and the absolute
  Snap Shooting unmodified-6 hit requirement.
- `C05-02` includes the complete v931 Fight On Death battlefield-presence
  authority rather than the superseded living-only plan. `C05-04` separately
  certifies post-save Damage-to-0 ordering.
- `C12-03` records the v931-labeled Ongoing Consolidation queue implementation;
  `C12-04` reopens its source-mode certification under P12B;
  `C14-02` owns the non-Core “objective marker” terminology alias; `C15-06`
  owns Insane Bravery's prohibition on already Battle-shocked targets.
- `C22-02` owns the per-PSYKER-rules-unit, per-phase psychic-ability-use ledger,
  keyed by canonical psychic ability identity rather than by a physical source
  instance. Source-instance and component identity remain evidence only.
  `C24-06` owns model-scoped Deadly Demise source correction and certification,
  while `C24-07` owns alternating Scout resolution.
- `C02-04` owns model keyword contribution under P05B’s retained-presence contract and the model-level schema
  needed to stop destroyed models contributing keywords to a surviving unit.
- `CAUDIT-01` owns the final all-category audit and certification gate. It is
  not an implementation finding and cannot close while any in-scope finding is
  open.

## App-data version 931 obligation map

This table is the exhaustive planning snapshot for the Game Datamissions v931
section observed on `2026-09-02T12:30:09-04:00`. Its provider is Game
Datamissions, its version/date are `931` / `2026-08-26`, and every row uses the
same [Core Rules Data Changelog](https://game-datamissions.com/11th/rules/changelog)
locator. It is a roadmap observation, not a substitute for the exact operative
source row required by `S-MIRRORS` and the owning implementation PR. Those PRs
must retain the rule- or FAQ-specific transcription SHA-256 and immutable
source-observation fingerprint; a future 40k.app v931 observation may
corroborate but is not required to begin that work.

| # | Data 931 change | Repository disposition | Canonical roadmap treatment |
|---:|---|---|---|
| 1 | 01.02.06 Splitting Units | No generic equal-as-possible split, persistent membership record, or attached-component fallback exists. | Add `C01-02` / P01B. |
| 2 | 18.06 Assault Disembark | Missing first-class move, eligibility, 3″ setup, charge state, events, replay, and adapters. | Existing `C18-04` / P18D. |
| 3 | 18.07 Shock Disembark | Missing first-class move, engagement preservation, and forced enemy Fight selections. | Existing `C18-05` / P18E. |
| 4 | 22.03.01 Psychic Abilities with a Psychic Level | No per-PSYKER-rules-unit, per-phase ledger keyed by canonical psychic ability identity or restore validation exists. | Add `C22-02` / P22B, including duplicate sources across attached components. |
| 5 | 24.08 Deadly Demise | Runtime is substantially model-scoped, but the source catalog still says “unit” and uses a unit-destruction trigger. | Add source-first `C24-06` / P24F. |
| 6 | Errata 01.02.06 | Duplicates row 1's operative Splitting Units change. | Reuse `C01-02` / P01B; no duplicate finding or PR. |
| 7 | Errata 12.08 Ongoing Consolidation | Engagement preservation exists, but no persisted queue forces the opponent to select every affected not-yet-selected enemy unit one at a time. | Add `C12-03` to P12; C12-04/P12B now resolves its body/erratum mode conflict. |
| 8 | Insane Bravery FAQ | Direct conflict: the catalog currently permits already Battle-shocked targets. | Add `C15-06` / P15F. |
| 9 | Abilities while embarked FAQ | No generic authority preserves active abilities while allowing visibility/measurement requirements to fail for off-battlefield units. | Add `C01-03` / P01C. |
| 10 | Fight On Death presence FAQ | Direct conflict: the current contract denies ordinary abilities and target geometry while v931 keeps the model present for all rules purposes. | Expand existing `C05-02` / P05B and its adapter contract update. |
| 11 | Modified Charge distance and target replacement FAQ | Raw/modified Charge values are planned, but Charge lacks post-selection target revalidation and replacement. | Add `C11-03` to P11A; widen `C04-01` / P04 as its generic prerequisite. |
| 12 | “Objective marker” means “objective” FAQ | Objective geometry is planned, but no source-bound non-Core terminology alias exists. | Add `C14-02` to P14. |
| 13 | Alternating Scout moves FAQ | Current sequencing drains the first unresolved player's actions instead of alternating unit resolutions. | Add `C24-07` / P24G. |
| 14 | Critical hit on 4+ when 5+ is normally required FAQ | A lowered threshold can make the attack hit, but critical status/effects remain restricted to an unmodified 6. | Add `C04-02` to P04B. |
| 15 | Critical 4+ during Snap Shooting FAQ | Direct conflict: generic minimum-hit thresholds can lower Snap's unmodified-6 requirement. | Add `C04-03` to P04B. |
| 16 | Change Damage to 0 after saves FAQ | Supported failed-save replacement ordering is correct but lacks v931 source, end-to-end regression, and consumer audit certification. | Add `C05-04` / P05D. |
| 17 | Destroyed models stop contributing keywords FAQ | Component loss is handled, but model-specific keywords are structurally absent and unit keywords are immutable. | Add `C02-04` / P02D. |
| 18 | Line of sight from any part to any part FAQ | Already mapped to the visibility-corridor work; implementation remains open. | Existing `C06-01` / P06A; expand acceptance evidence. |
| 19 | Take to the Skies timing FAQ | Broadly mapped, but acceptance did not expressly require choosing before an Advance or Charge roll. | Existing `C21-01` / P21A; expand acceptance evidence. |

## Canonical one-PR-at-a-time sequence

| Order | PR | Finding(s) | How it is currently done | How it must be done | Controlling maintained App-data locator and operative requirement to pin | Prerequisites | Gate |
|---:|---|---|---|---|---|---|---|
| 1 | P15D | C15-04 | Fire Overwatch’s source row omits exact target/Snap wording; Crushing Impact’s row says Vehicle/Strength while runtime supports Monster-or-Vehicle/Toughness; older PDF numbering conflicts with current App headings and one App example has a stale cross-reference. | Correct only source records, stable identifiers, hashes, and provenance to current complete App text. Keep correct runtime behavior; bind by title/operative text and record the stale example reference. | [15.05–15.09](https://www.40k.app/rules/15-stratagems): current headings make Crushing Impact 15.05 and Explosives 15.06; the category 12 example’s contrary number is internal drift. | — | APP-INTERNAL-DRIFT |
| 2 | P08A | C08-03 | Generic `START_PHASE` dispatch runs before the handler, but the Command-specific start registry runs after Core CP is granted. | Route every start-of-Command rule and choice through one canonical boundary before Core CP is granted. | [08.01–08.02](https://www.40k.app/rules/08-command-phase): resolve start-of-Command rules before Gain Core CP. | — | APP-AUTHORITY |
| 3 | P08B | C08-01, C08-02 | The active player’s Battle-shock is cleared at Command start, and tests are requested only below Half-strength. | Preserve existing Battle-shock until a required test succeeds; test each rules unit that is currently Battle-shocked or at/below Half-strength exactly once. | [08.03](https://www.40k.app/rules/08-command-phase): the required-test candidates are currently Battle-shocked or at/below Half-strength, and success removes Battle-shock. | P08A | APP-AUTHORITY |
| 4 | P09A | C09-01 | Reserve arrivals are delayed until battlefield units are handled, while tactical disembarks are front-loaded separately. | Use one Move Units selection loop containing unselected battlefield, embarked, and Strategic Reserve units so moves, disembarks, and ingress can interleave. | [09.02 Move Units](https://www.40k.app/rules/09-movement-phase): the player selects an eligible unit and resolves its movement before selecting the next. | P08B | APP-AUTHORITY |
| 5 | P09B | C09-02 | Voluntary Desperate Escape is offered but rejected without a forced/overflight cause; its hazard rolls and follow-up test are incomplete. | Permit Ordered Retreat as an optional Desperate Escape, roll once for every model, then test Battle-shock if the unit was not already shocked. | [09.02.02 and 09.07](https://www.40k.app/rules/09-movement-phase): Ordered Retreat may invoke Desperate Escape and its per-model hazard/test sequence. | P09A | APP-AUTHORITY |
| 6 | P06A | C06-01 | Visibility uses zero-width mathematical rays. | Use one 1mm-wide 2.5D visibility corridor across terrain, models, hulls, attacks, and abilities; certify that line of sight is drawn from any part of the observer to any part of the observed model. | [06.01 Visibility](https://www.40k.app/rules/06-other-concepts) and [v931 line-of-sight FAQ](https://game-datamissions.com/11th/rules/changelog): visibility requires the rule’s 1mm corridor and any-part-to-any-part model geometry. | — | APP-AUTHORITY |
| 7 | P06B | C06-02 | Mortal-wound routing silently selects the first sorted legal model when several share the active priority tier. | Resolve mortal wounds individually; request a controlling-player finite choice for ties and auto-select only a sole legal model. | [06.02 Mortal Wounds](https://www.40k.app/rules/06-other-concepts): allocate by wounded non-Character, other non-Character, wounded Character, then other Character priority. | — | APP-AUTHORITY |
| 8 | P19 | C19-01 | Bodyguard loss unconditionally splits surviving Leader/Support components into separate rules units. | Preserve the original attached rules-unit identity until the last model that started in it is destroyed, while retaining explicit component lineage. | [19.01.01 Attached Units](https://www.40k.app/rules/19-attached-units): models that began as one attached unit remain one rules unit for the rule’s stated duration. | — | APP-AUTHORITY |
| 9 | P05A | C05-01 | A destroying attack can remove a model, emit destruction, and resolve mandatory or optional destruction reactions before the attacking unit finishes all attacks. | Retain a logically destroyed, non-targetable model only when a destruction-triggered rule applies; finish every attack from the attacking rules unit, then resolve queued triggers and removal. | [05.04.04 Destroyed](https://www.40k.app/rules/05-attack-sequence): destruction-triggered rules wait until the attacking unit has completed its attacks. | P19 | APP-AUTHORITY |
| 10 | P18C | C18-03 | Emergency Disembark placement is requested before hazard rolls and mortal-wound casualties. | Snapshot cargo, resolve hazard rolls/casualties first, then request placement only for survivors. | [18.05 Emergency Disembark](https://www.40k.app/rules/18-transports): make the hazard rolls before moving surviving models. | P05A, P06B | APP-AUTHORITY |
| 11 | S-MIRRORS | — (source-governance gate) | The committed P00 source policy names only 40k.app, so v931/v946 Game Datamissions observations have planning authority but cannot yet satisfy implementation evidence gates. | The repository source-governance owner must replace provider-specific policy with maintained-direct-App-data-mirror policy naming 40k.app and Game Datamissions; require provider, URL, App-data version or observation timestamp, transcription SHA-256, and immutable observation fingerprint; and fail closed when co-versioned mirrors disagree. Closure requires the updated policy artifact, validator/static evidence for complete tuples and mismatch rejection, and a retained review record showing both named providers without falsely presenting either as Games Workshop-owned. | Owner direction recorded in this roadmap; [40k.app](https://www.40k.app/) and the [Game Datamissions Core Rules Data Changelog](https://game-datamissions.com/11th/rules/changelog). | P18C | SOURCE-GOVERNANCE |
| 12 | P18D | C18-04 | The engine has no Assault Disembark move type, source eligibility, 3″ placement path, or distinct post-disembark charge state. | Add a canonical Assault Disembark move for a rule that preserves charge eligibility after disembarking from a Transport that made a Normal Move; require an embarked unit in a battlefield Transport, prohibit a unit that embarked this phase, reject a Transport that Advanced or Fell Back, place the rules unit wholly within 3″, and carry the resulting charge permission through events, replay, decisions, and adapters. | [Game Datamissions App-data v931, 18.06 Assault Disembark Move](https://game-datamissions.com/11th/rules/changelog), independently introduced by the official August 26 Universal Rules Updates v1.1. | P18C, S-MIRRORS | APP-AUTHORITY |
| 13 | P18E | C18-05 | The engine has no Shock Disembark move type and therefore cannot preserve start-of-move enemy engagements or force the opponent's required Fight selections. | Provide source-authorized Shock Disembark eligibility and 3″ setup, preserve the source-defined prior engagements, and queue each affected unselected enemy for a canonical Fight activation. The merged implementation’s Advance-only eligibility is reopened by C18-08/P18G; substitution of Transport engagements remains paused under C18-07/P18F. | [Game Datamissions App-data v931, 18.07 Shock Disembark Move](https://game-datamissions.com/11th/rules/changelog), independently introduced by the official August 26 Universal Rules Updates v1.1. | P18D, S-MIRRORS | APP-AUTHORITY |
| 14 | P24F | C24-06 | Deadly Demise runtime is substantially model-scoped, but the source catalog says “when this unit is destroyed” and uses `after_unit_destroyed`. | Correct and source-back the catalog row to trigger each time a model with the ability is destroyed; audit all consumers and preserve already-correct model-scoped runtime behavior. | [Game Datamissions App-data v931, changed 24.08 Deadly Demise](https://game-datamissions.com/11th/rules/changelog): the bearer model, not its unit, owns the trigger. | P05A, S-MIRRORS | APP-DRIFT |
| 15 | P15F | C15-06 | Insane Bravery sets `allow_battle_shocked_targets=True`, permitting the controlling player to target an already Battle-shocked unit. | Reject an already Battle-shocked target before spend/mutation while retaining the canonical about-to-test decision path and once-per-battle restriction. | [Game Datamissions App-data v931, Insane Bravery FAQ](https://game-datamissions.com/11th/rules/changelog): a controlling player cannot target its Battle-shocked unit with the Stratagem. | P08B, S-MIRRORS | APP-DRIFT |
| 16 | P24G | C24-07 | Pre-battle sequencing repeatedly returns the first unresolved player until that player completes every Scout action. | Persist an alternating player/unit-resolution cursor beginning with the first-turn player, skip only players with no unresolved pre-battle rule, and preserve decisions, restore, replay, and adapters. | [Game Datamissions App-data v931, alternating Scout moves FAQ](https://game-datamissions.com/11th/rules/changelog): players alternate resolving pre-battle rules, starting with the player taking the first turn. | P19, S-MIRRORS | APP-DRIFT |
| 17 | P24D | C24-04 | Hazardous pools are deduplicated by profile ID and exactly one hazard roll is made. | Count selected physical Hazardous weapon instances and roll once per selected weapon after all of the unit’s attacks, preserving Shooting/Fight origin. | [24.15 Hazardous](https://www.40k.app/rules/24-core-abilities): roll once for each selected Hazardous weapon after the unit finishes its attacks. | P05A, P06B | APP-AUTHORITY |
| 18 | P14 | C14-01, C14-02 | Objective consumers duplicate point-marker geometry and no data-boundary rule treats non-Core references to an “objective marker” as an “objective.” | Provide one model-group-aware geometry query for markers and terrain objectives, make Objective Control its first consumer, and normalize the non-Core terminology alias once at the source boundary without rewriting Core Rules text. | [14.01/14.01.01](https://www.40k.app/rules/14-objectives) and [v931 objective terminology FAQ](https://game-datamissions.com/11th/rules/changelog): use closest-part objective geometry, and outside Core Rules treat “objective marker” as “objective.” | S-MIRRORS | APP-AUTHORITY |
| 19 | P12 | C12-01, C12-02, C12-03 | Objective Consolidation has incomplete geometry/final-position semantics; Ongoing Consolidation preserves prior engagements but does not queue every affected unselected enemy unit for opponent-controlled Fight selection. | Consume P14 geometry and complete Engaging, Ongoing and Objective Consolidation per-model/final-unit rules. Extend P18E’s shared forced-Fight queue to suspend and resume ordinary Fight state, activation order and pending continuations; select each affected unselected enemy exactly once through the opponent’s decision path. The shipped both-mode queue remains history; C12-04/P12B reopens source-mode certification. | [12.08](https://www.40k.app/rules/12-fight-phase), [14.01.01](https://www.40k.app/rules/14-objectives), and [v931 Ongoing Consolidation erratum](https://game-datamissions.com/11th/rules/changelog). | P14, P18E, S-MIRRORS | APP-DRIFT |
| 20 | P22 | C22-01 | Generic Aura resolution excludes the source unless each descriptor opts in and can apply the same Aura more than once through overlapping models. | Include a model in its own Aura by default and apply the same Aura to a target once, unless source-backed wording expressly excludes self-application. | [22.01 Aura Abilities](https://www.40k.app/rules/22-other-rules-and-abilities): a model is within its own Aura and duplicate applications do not accumulate. | — | APP-AUTHORITY |
| 21 | P22B | C22-02 | Psychic abilities with levels have no authoritative same-ability-use ledger. | Key each use by canonical PSYKER rules-unit ID, canonical psychic ability identity, and phase. Derive ability identity from its stable source rule/descriptor rather than its physical source instance; retain the selected source-instance and component identities as audit evidence only. Reject a second use exposed by duplicate instances or different attached components, and validate the canonical key plus evidence against authoritative lineage on restore/replay. | [Game Datamissions App-data v931, 22.03.01 Psychic Abilities with a Psychic Level](https://game-datamissions.com/11th/rules/changelog): a PSYKER unit cannot use the same psychic ability more than once per phase. | P08A, P19, S-MIRRORS | APP-AUTHORITY |
| 22 | P24C1 | C24-03A | Duplicate non-Anti weapon abilities are rejected; distinct source instances are not preserved. | Preserve stable source identity for every duplicate core/weapon ability instance without yet adding the player-facing selection. | [24.02 Duplicated Abilities](https://www.40k.app/rules/24-core-abilities): duplicate abilities do not accumulate and the controlling player chooses which instance applies. | — | APP-AUTHORITY |
| 23 | P01 | C01-01 | Battle-shock collection skips rules units with no placed model and tests only below Half-strength. | Extend P08B’s predicate to embarked and Strategic Reserve rules units: currently Battle-shocked or at/below Half-strength. | [01.02.04 Not On the Battlefield](https://www.40k.app/rules/01-core-concepts): off-battlefield units retain their Command-phase Battle-shock obligations. | P08B | APP-AUTHORITY |
| 24 | P01B | C01-02 | Only specialized faction/model materialization paths split units; no generic split preserves chosen model membership or applies the equal-as-possible attached fallback. | Add one canonical split decision and mutation path that records which models enter each successor, balances counts as equally as possible, and ignores an impossible source-specified strength when attached Leader/Support models require the generic fallback. | [Game Datamissions App-data v931, changed and errata 01.02.06 Splitting Units](https://game-datamissions.com/11th/rules/changelog); both changelog rows are one obligation. | P19, S-MIRRORS | APP-AUTHORITY |
| 25 | P01C | C01-03 | Embarked units are often treated as having no generally active abilities, with no shared distinction between active rules and unsatisfied battlefield visibility/measurement conditions. | Keep an embarked unit's abilities active, evaluate each typed restriction normally, and make geometry-dependent requirements fail because the unit is Not On The Battlefield rather than through blanket ability suppression. | [Game Datamissions App-data v931, embarked abilities FAQ](https://game-datamissions.com/11th/rules/changelog): abilities remain active within their own restrictions, while off-battlefield visibility/measurement requirements fail. | P19, S-MIRRORS | APP-AUTHORITY |
| 26 | P02A | C02-01 | The modifier service supports set, multiply, add, floor, and ceiling with integer operands, but not the complete ordered algebra. | Implement exact replacement → multiplication → addition → division → subtraction ordering, one final round-up, and terminal `0`, `-`, and `*` replacement values. | [02.02.01 Modifiers](https://www.40k.app/rules/02-datasheets): apply the listed operation groups in order and round remaining fractions only at the end. | — | APP-AUTHORITY |
| 27 | P02B | C02-02 | Modified dice results can remain below 1, and raw, modified, and domain-limited values are not distinct. | Separate raw dice, post-reroll result, modifier trace, minimum-1 modified result and rule-specific limits. Cap a Charge result at 12 after cumulative modifiers; subsequent move-distance effects remain distinct. | [02.02.01 Modifiers](https://www.40k.app/rules/02-datasheets): modified dice results have a minimum of 1, and Charge results have a maximum of 12 after cumulative modifiers. | P02A | APP-AUTHORITY |
| 28 | P24I | C24-09 | Psychic modifier selection aggregates individual effects into net BS/WS and hit totals; canceling effects can suppress a legal choice. | Preserve each source-linked modifier and allow the controlling player to ignore any subset before combination and caps. Cover Cover/Plunging cancellation, positive and negative effects in the same bucket, deterministic option/proposal identity, stale rejection, restore and Shooting/Fight replay. P22B’s ability-use ledger remains separate. | [24.29 Psychic](https://www.40k.app/rules/24-core-abilities) and [02.02.02 Ignore Modifiers](https://www.40k.app/rules/02-datasheets). | P02A, P02B | APP-AUTHORITY |
| 29 | P02C | C02-03 | Detection Range permits 0, has no upper bound, and Lone Operative range handling does not share one terminal clamp. | Clamp Detection Range and Lone Operative ranges to 9″–30″ after modifiers in the owning modifier service. | [02.02.01 Modifiers](https://www.40k.app/rules/02-datasheets): these ranges have the stated terminal 9″ minimum and 30″ maximum. | P02A | APP-AUTHORITY |
| 30 | P05B | C05-02 | A model is recorded removed and emits `model_destroyed`, then is reconstructed if Fight On Death is accepted; the current contract denies it ordinary abilities and target geometry while retained. | At the P05A boundary, atomically enter a retained Fight On Death state without removal/re-add replay. Until the unit attacks or the phase ends, keep the fixed model present for all rules purposes, including measurement, visibility, datasheet abilities, Stratagem targeting, and enemy engagement, then clean it up exactly once. | [05.04.05](https://www.40k.app/rules/05-attack-sequence) and the [v931 Fight On Death presence FAQ](https://game-datamissions.com/11th/rules/changelog). | P05A, S-MIRRORS | APP-DRIFT |
| 31 | P02D | C02-04 | `ModelInstance` has no keyword authority and `UnitInstance.keywords` is immutable, so a destroyed special model can keep contributing its keyword to a surviving unit. | Preserve source-backed model keywords and derive current rules-unit keywords from authoritative model presence. Consume P05B’s retained Fight On Death presence contract, distinguish it from ordinary removal and attached-ability expiry, and validate lineage through destruction, restore, replay and adapters. | [Game Datamissions App-data v931, destroyed-model keyword FAQ](https://game-datamissions.com/11th/rules/changelog): destroyed models no longer contribute keywords to their prior unit. | P19, P05B, S-MIRRORS | APP-AUTHORITY |
| 32 | P06C | C06-03 | P06A fixes corridor width but retains seven-point model samples and treats all 49 observer/target rays being clear as full visibility. | Certify any-part visibility and every-facing-part full visibility against the supported model geometry, using narrow-opening and partial-occlusion counterexamples. Correct the shared geometry owner where sampling is not equivalent; do not claim complete visibility support from corridor width alone or introduce an unapproved approximate fallback. | [06.01 Visibility](https://www.40k.app/rules/06-other-concepts), including the v931 any-part FAQ. | P06A, S-MIRRORS | APP-AUTHORITY |
| 33 | P10 | C10-01, C10-02 | Indirect restrictions are gated on target invisibility, include an obsolete -1 to hit, and can remove non-Indirect weapons from mixed declarations. | During Indirect Shooting, apply Cover, hit-reroll prohibition and unmodified failure ranges to each INDIRECT FIRE weapon attack, whether its target is visible or unseen. Remove the obsolete -1 and retain ordinary weapons against visible eligible targets. Distinguish the same weapon fired through Normal Shooting. | [10.07 Indirect Shooting](https://www.40k.app/rules/10-shooting-phase): the restrictions attach to INDIRECT FIRE weapon attacks in this shooting mode; stationary plus friendly-observer conditions change the failure range from 1–5 to 1–3. | P02B, P06A, P06C, P09A | APP-AUTHORITY |
| 34 | P16 | C16-01, C16-02 | Action shooting restrictions and prior-shooting checks use ordinary Shooting-phase state despite turn-long and out-of-phase obligations. | Use authoritative rules-unit restriction records with explicit turn/phase expiry. Starting an Action locks non-TITANIC shooting and all charge declarations until turn end; every shooting type, including Snap, locks Action starts until phase end. Preserve ordinary already-shot rejection, and cover phase transitions, completion/cancellation, attached identity, restore, replay and facade consumers. | [16.01 Actions](https://www.40k.app/rules/16-actions), [10.04–10.07](https://www.40k.app/rules/10-shooting-phase), and [15.09 Snap Shooting](https://www.40k.app/rules/15-stratagems). | P19, S-MIRRORS | APP-AUTHORITY |
| 35 | P15G | C15-07 | P15D records missing Rapid Ingress first-round and AIRCRAFT exclusions but assigns no runtime repair. | Reject first-battle-round use and AIRCRAFT targets before CP spend, queue mutation or ingress. Audit every eligibility and target-validation path and preserve canonical ingress proposals, placement restrictions and replay. | [15.07 Rapid Ingress](https://www.40k.app/rules/15-stratagems). | P15D, P09A, P02D | APP-DRIFT |
| 36 | P01D | C01-04 | Generic sequencing exposes permutations without a mandatory/optional tier; round-boundary conflicts can use a roll-off. | Implement active mandatory, active optional, opposing mandatory, opposing optional tiers with each owner choosing within its tier. Defer newly triggered rules until the current timing batch completes. Preserve explicit source exceptions and the 01.03 active-player changes during moves/attacks and between turns; audit every sequencing consumer. | [01.03–01.03.02](https://www.40k.app/rules/01-core-concepts): active-player authority and four-tier Rules Sequencing. | P08A, P24G | APP-DRIFT |
| 37 | P02E | C02-05 | The shared Stratagem cost registry clamps each handler result at zero but has no final +1 ceiling. | Apply the source-defined modifier order, then bound the final CP cost to at least zero and at most the unmodified cost plus one. Share the result across options, affordability, spending, increased-cost failure, events and replay; retain source commitments for all modifiers. | [02.02.01 Other Modified Rules](https://www.40k.app/rules/02-datasheets): final Stratagem CP cost bounds. | P02A, P15D | APP-DRIFT |
| 38 | P18G | C18-08 | P18D hard-codes Normal-only Assault and P18E Advance-only Shock eligibility. | Separate Core move eligibility from the granting rule. With a valid grant, Assault excludes only Advance/Fall Back transport moves; Shock adds no transport-movement gate. Both require an on-battlefield Transport and no embark into it this phase. Cover not selected, stationary, Normal, Ingress, Advance and Fall Back, plus absent/restricted grants, stale proposals and replay. Do not resolve the engagement-owner conflict here. | [18.06–18.07](https://www.40k.app/rules/18-transports): complete When eligible clauses; extra grant restrictions remain source-linked RuleIR. | P18D, P18E, S-MIRRORS | APP-DRIFT |
| 39 | P24A | C24-01 | Stealth applies `-1` to hit and activates if any attached component has it; stale wording is duplicated in generated data. | Require every living model in the rules unit to have Stealth and grant Benefit of Cover instead of a hit modifier; regenerate every in-scope record. | [24.33 Stealth](https://www.40k.app/rules/24-core-abilities): the whole target unit must have Stealth and receives Benefit of Cover. | P10 | APP-AUTHORITY |
| 40 | P15A | C15-01 | Smokescreen triggers after target selection, grants Cover plus `-1` to hit, and affects only the selected Smoke unit. | Offer it at the start of the opponent’s Shooting phase; grant Benefit of Cover to the Smoke unit and to a target obscured by its Smoke models, without `-1` to hit. | [15.10 Smokescreen](https://www.40k.app/rules/15-stratagems): start-of-opponent-Shooting timing and the stated Smoke-obscuration Cover effect last until phase end. | P15D, P06A, P10 | APP-AUTHORITY |
| 41 | P15B | C15-02 | Explosives is a start-phase, GRENADES-only unit action with no selected source model. | During the owner’s Shooting phase, select an unengaged, eligible-to-shoot, non-Advanced `EXPLOSIVES/GRENADES` unit, a matching model, and a visible unengaged enemy within 8″ of that model. | [15.06 Explosives](https://www.40k.app/rules/15-stratagems): the current App heading and complete model/target eligibility statement control. | P15D, P06A, P06B, P10 | APP-AUTHORITY |
| 42 | P04 | C04-01 | Target replacement is shooting-local, so another action such as Charge cannot revalidate and replace a selected target through one authoritative lifecycle. | Provide one deterministic target-invalidation/replacement service reusable by shooting and Charge, preserving decisions, restore, replay, and adapter behavior without taking ownership of hit-roll resolution. | [04.03.03](https://www.40k.app/rules/04-making-attacks) and the [v931 modified-Charge target replacement FAQ](https://game-datamissions.com/11th/rules/changelog). | S-MIRRORS | APP-AUTHORITY |
| 43 | P04B | C04-02, C04-03 | A lowered critical threshold can leave critical status/effects restricted to an unmodified 6, while generic minimum-hit thresholds can lower Snap Shooting below its absolute unmodified-6 requirement. | In the attack hit-roll resolver, make an unmodified roll meeting a source-backed critical threshold both successful and critical even when the ordinary hit value is worse; enforce Snap Shooting's unmodified-6 hit requirement unless a rule explicitly overrides Snap. Cover ordinary and Snap attacks, including lowered critical thresholds, raw/modified roll separation, and Indirect-fire consumers. | [Game Datamissions App-data v931, critical-hit and Snap Shooting FAQs](https://game-datamissions.com/11th/rules/changelog). | P02B, P10, S-MIRRORS | APP-DRIFT |
| 44 | P24H | C24-08 | Critical Lethal Hits unconditionally auto-wound without the controlling player’s legal decline option. | Offer the canonical finite auto-wound/roll-to-wound decision in the shared Shooting/Fight attack host. Cover Lethal plus Devastating Wounds, additional Sustained Hits, deterministic JSON-safe decisions, stale/malformed submissions, restore and adapter/replay equivalence. | [24.23 Lethal Hits](https://www.40k.app/rules/24-core-abilities): the player may decline automatic wounding to attempt a critical wound. | P04B | APP-AUTHORITY |
| 45 | P15H | C15-08 | Phase-end Fire Overwatch still requires a triggering enemy and restricts the shooting declaration to that unit. | At opponent Movement-phase end, select an eligible friendly unengaged non-TITANIC unit and expose the canonical choice of one eligible visible enemy within 24″ through Snap Shooting. Preserve Snap hit/reroll requirements and P16’s Action lock, including phase-end continuation, CP, restore and replay. | [15.08–15.09 Fire Overwatch and Snap Shooting](https://www.40k.app/rules/15-stratagems). | P15D, P04B, P16 | APP-DRIFT |
| 46 | P11A | C11-01, C11-03 | Charge modifiers are embedded in the dice expression, one ambiguous value drives reachability, and post-selection modifier changes cannot trigger target replacement. | Separate raw 2D6, the modified Charge result bounded to 1–12, and movement budget. Apply subsequent move-distance effects separately; select targets within the current permitted maximum and route later target invalidation through P04 before movement. | [02.02.01](https://www.40k.app/rules/02-datasheets), [11.02/11.04](https://www.40k.app/rules/11-charge-phase), and the [v931 modified-Charge target FAQ](https://game-datamissions.com/11th/rules/changelog). | P02A, P02B, P04, S-MIRRORS | APP-AUTHORITY |
| 47 | P11B | C11-04 | ChargeEndpointWitness and closer/preferred-distance checks aggregate distances by target unit, allowing one model to satisfy another model's obligation. | Validate each charging model: end closer to a selected target; end within 1 inch if possible; end engaged if possible. Reuse the shared mandatory-endpoint/path search where applicable, preserve unit-level all-target and no-other-target constraints, and reject unresolved reachability explicitly. Cover attached units, a leading model masking a trailing failure, obstacles, target changes, stale witnesses and exact replay. | [11.04 Charge Move](https://www.40k.app/rules/11-charge-phase): three per-model While moving clauses. | P11A, P12 | APP-DRIFT |
| 48 | P15I | C15-09 | P15D acknowledges Crushing Impact lifecycle/continuation work without a scheduled runtime owner. | Trace the charge-end trigger, enemy/model selections, Toughness-based roll, capped mortal wounds for both sides and suspended Charge continuation. Close the acknowledged gap with real facade, interruption, destruction and replay evidence; retain any already-correct runtime behavior. | [15.05 Crushing Impact](https://www.40k.app/rules/15-stratagems). | P15D, P11A, P06B, P05A | APP-AUTHORITY |
| 49 | P15E | C11-02, C15-05 | Ordinary Charges and Heroic Intervention mark Command Re-roll unavailable. | After the Charge roll, offer Command Re-roll through the normal CP/decision path and reroll the complete 2D6 before modifiers. | [15.02 Command Re-roll](https://www.40k.app/rules/15-stratagems): the entire Charge roll is an eligible reroll. | P15D, P11A | APP-AUTHORITY |
| 50 | P15C | C15-03 | Heroic Intervention rolls bare 2D6 and caps that unmodified total at 6. | Use the ordinary Charge declaration, reroll, modifier, target, eligibility, and `PathWitness` pipeline; for Into the Fray apply its result cap after modifiers. Preserve VEHICLE eligibility only for CHARACTER/WALKER units and restrict Leap to Defend targets to enemies that made a Charge move this phase. | [15.11 Heroic Intervention](https://www.40k.app/rules/15-stratagems): Leap to Defend/Into the Fray use the stated Charge process and restrictions. | P15D, P11A, P11B, P15E | APP-AUTHORITY |
| 51 | P21A | C21-01 | FLY automatically grants model/terrain transit for ordinary movement and Charges without selecting Take to the Skies. | Before each Normal, Fall Back, Advance, or Charge move, offer and commit Take to the Skies; for Advance and Charge this must occur before rolling. Only selection grants transit/ignored vertical distance and reduces the maximum by 2″ unless Hover applies. Gate Heavy's ignored vertical distance on the committed move choice for each FLY model, and preserve all per-model movement distances through the Shooting boundary for the full turn. Order 33 already separated Remain Stationary from Heavy; its deferred Heavy-history gap belongs here. Hover removes only the 2-inch penalty; P23 owns retirement of the legacy AIRCRAFT-keyword toggle. | [21.03 Flying Models](https://www.40k.app/rules/21-flying-and-surging) and [v931 Take to the Skies timing FAQ](https://game-datamissions.com/11th/rules/changelog). | P09A, P11A, S-MIRRORS | APP-AUTHORITY |
| 52 | P21B | C21-02 | Surge has no target and omits closest-target ties, target-only Engagement, maximum approach, and the complete movement lock. | Choose the closest enemy, use a finite tie decision, require Engagement with that target if possible or maximum approach otherwise, forbid Engagement with others, and lock further movement that phase. Require the granting trigger, not Battle-shocked, unengaged and no prior move this phase before offering or accepting Surge. | [21.02 Surge Move](https://www.40k.app/rules/21-flying-and-surging): closest-target, tie, maximal movement, Engagement, and phase-lock requirements. | P21A | APP-AUTHORITY |
| 53 | P24E | C24-05 | Generic MOBILE geometry exists, but Super-Heavy Walker has no descriptor, movement behavior, choice, or post-move roll. | For Normal/Advance/Fall Back moves, allow transit through non-Titanic models and terrain sections at most 4″ high; offer the all-model MOBILE choice and apply Battle-shock on a post-move D6 roll of 1. | [24.35 Super-Heavy Walker](https://www.40k.app/rules/24-core-abilities): the stated transit and optional MOBILE/Battle-shock behavior. | P21A | APP-AUTHORITY |
| 54 | P03A | C03-01 | Every deployment model must be wholly within its deployment zone, with no oversized-base fallback. | After proving the base cannot fit, require contact with the player’s battlefield edge and impose the same-turn Normal/Advance/Fall Back/Charge/ranged-attack lock. Preserve the source-backed AIRCRAFT exception to the oversized setup restrictions. | [03.02.02 Set Up](https://www.40k.app/rules/03-moving): oversized deployment uses edge contact and the stated same-turn restrictions. | — | APP-AUTHORITY |
| 55 | P03B | C03-02 | Every disembarking model must be wholly within the ordinary 3″/6″ distance. | Only after proving ordinary placement impossible, allow an oversized base within 1″ of the Transport base/hull and outside Engagement Range. | [03.02.02 Set Up](https://www.40k.app/rules/03-moving): the 1″ oversized-base exception applies to disembark placement after ordinary placement is impossible. | P03A | APP-AUTHORITY |
| 56 | P24C2 | C24-03B | Only duplicate Anti instances have a player-selection path; other duplicate ability instances cannot be selected through adapters. | Add the controlling-player finite instance decision, validation, replay, and viewer-safe projection; weapon choices occur each time the unit attacks during Select Weapons. Certify the Scouts exception: use the lowest non-shared value when values differ across models; a value shared by every model remains selectable. Cover the source's mixed 6/8-inch and universally shared 6/8-inch examples. | [24.02 Duplicated Abilities](https://www.40k.app/rules/24-core-abilities): duplicate abilities do not accumulate and the controlling player selects the active instance. | P24C1, P04 | APP-AUTHORITY |
| 57 | P05C | C05-03 | Authenticated former placements exist, but no generic query can measure to a destroyed model or destroyed unit. | Add source-authorized measurement using the exact former base/hull; a destroyed-unit reference resolves to the last model destroyed and grants no living battlefield authority. | [05.04.06](https://www.40k.app/rules/05-attack-sequence): use the destroyed model’s former footprint, and the last destroyed model for a destroyed-unit reference. | P05B | APP-AUTHORITY |
| 58 | P05D | C05-04 | The supported failed-save replacement path changes incoming Damage to 0 after the save, but the behavior is not certified against v931 across source, engine consumers, adapters, restore, and replay. | Pin the v931 FAQ, retain the correct post-save ordering, add an end-to-end regression, and audit every Damage-replacement consumer so no path changes Damage before the saving throw. | [Game Datamissions App-data v931, Damage-to-0 timing FAQ](https://game-datamissions.com/11th/rules/changelog): change Damage after saving throws. | S-MIRRORS | APP-AUTHORITY |
| 59 | P18A | C18-01 | An empty Dedicated Transport receives a delayed unavailable/setup consequence associated with battle round 1. | At the end of Declare Battle Formations, immediately destroy/remove every empty Dedicated Transport without triggering destroyed-model rules. | [18.01 Transport Capacity](https://www.40k.app/rules/18-transports): empty Dedicated Transports are destroyed at the stated formation boundary without destruction triggers. | — | APP-AUTHORITY |
| 60 | P18B | C18-02 | Emergency Disembark accepts an arbitrary subset, destroys omitted models without proof, and rejects engaged endpoints even when no unengaged placement exists. | Place the maximum possible survivors wholly within 6″ and as close as possible; prefer unengaged placements, allow an engaged endpoint only when no unengaged endpoint exists, and destroy only genuinely unplaceable models. | [18.05 Emergency Disembark](https://www.40k.app/rules/18-transports): maximal placement, closest-possible positioning, unengaged preference, engaged fallback, and casualty rules. | P03B, P18C | APP-AUTHORITY |
| 61 | P18H | C18-09 | Embark checks same-phase disembark on the selected cargo state; the shared validator has no complete same-turn setup authority. | Reject embark after any setup on the battlefield this turn, including disembark from another Transport, Ingress and repositioning, unless a source explicitly overrides the restriction. Use canonical rules-unit setup history through all ordinary/reactive move and embark validators; verify later-turn expiry, both players, restore and replay. | [18.02 Embarking](https://www.40k.app/rules/18-transports): no setup on the battlefield this turn. | P18G, P01C | APP-DRIFT |
| 62 | P18F | C18-07 | P18E substitutes the Transport's prior engagements for 18.07's moving-model engagement clause; C18-08/P18G separately owns Core eligibility. | Resolve only the engagement-owner interpretation and its forced-Fight consequences. Pin complete versioned mirror or official-App evidence; do not infer that embarked passengers share the Transport's prior engagements. Reconcile live validation, stored start-engagement evidence, queued opponents and replay. Core eligibility alignment proceeds independently in P18G. | [18.06–18.07 Assault and Shock Disembark](https://www.40k.app/rules/18-transports). | P18D, P18E, P18G, S-MIRRORS | EXCEPTION-PAUSE |
| 63 | P20 | C20-01, C18-06 | Reserve ingress rejects a Strategic Reserve Transport containing cargo as unsupported, and Rapid Disembark passengers do not inherit the ingress placement restrictions that governed their Transport. | Select and ingress the Transport as one reserve unit while cargo remains embarked; count cargo toward reserve limits but do not make it independently eligible for ingress. If a passenger then uses Rapid Disembark, apply the same ingress restrictions to every disembarking model. | [20.01/20.04 Strategic Reserves](https://www.40k.app/rules/20-strategic-reserves) and [Game Datamissions App-data v946, 18.04.01 Rapid Disembark And Limitations](https://game-datamissions.com/11th/rules/changelog). | P09A, T-TRANSPORT, S-MIRRORS | APP-AUTHORITY |
| 64 | P20B | C20-02 | Core reserve defaults use end-of-battle destruction and no blocked arrival round; the round-three policy is attributed to Chapter Approved. Repositioning/history and movement restrictions have partial existing owners. | Make round-two-or-later arrival and end-of-round-three destruction Core defaults unless expressly overridden. Track whether a unit ever ingressed and both exemptions: cargo in a Transport that ingressed and repositioned units. Preserve the separate 20.01.02 final-turn cleanup. Certify every 20.02 move-history/effect-lifetime clause and 20.04 prohibition on other move types until the next Charge phase, including reactive moves, cargo, Deep Strike, exact replay and source-bound mission overrides. | [20.01.02–20.04](https://www.40k.app/rules/20-strategic-reserves): Core arrival, destruction, repositioning and ingress lifetimes. | P20, P15G | APP-DRIFT |
| 65 | P24B | C24-02 | Firing Deck marks only contributing passenger units and stores the restriction in phase-local `shot_unit_ids`. | Snapshot every unit embarked when Firing Deck resolves and make all of them ineligible to shoot until turn end, including after disembarking. | [24.14 Firing Deck](https://www.40k.app/rules/24-core-abilities): every unit embarked at resolution is subject to the turn-long shooting restriction. | T-TRANSPORT, P16 | APP-AUTHORITY |
| 66 | P23 | C23-01 | Aircraft make ordinary moves and enter reserves by crossing a battlefield edge. The movement policy also exposes a Hover toggle that removes AIRCRAFT; other category-23 interactions are not certified. | Start Aircraft in Strategic Reserves, permit only ingress moves, and return every Aircraft still on the battlefield to Strategic Reserves at the end of its opponent’s turn. Certify transit through AIRCRAFT for every move, ignore AIRCRAFT in pile-in/consolidation/Surge target and closest-enemy selection unless the mover can FLY, and allow Normal/Advance when engaged solely with AIRCRAFT. Disable Plunging Fire by/on AIRCRAFT. Prohibit AIRCRAFT charges; permit their melee only against FLYING units, charges against them only by FLYING units, and melee against them only by FLYING models. Retire the legacy Hover toggle and its decision/persistence surfaces with an explicit contract migration; retain AIRCRAFT under 24.17 Hover. | [23.01–23.04 Aircraft](https://www.40k.app/rules/23-aircraft), [21.03](https://www.40k.app/rules/21-flying-and-surging) and [24.17 Hover](https://www.40k.app/rules/24-core-abilities). | P20, P20B, P21A, P21B, P11B | APP-AUTHORITY |
| 67 | P25A | C25-01, C25-02 | Incursion permits 4 Enhancements, ordinary duplicates of 3, Battleline duplicates of 6, and does not independently double Dedicated Transport limits. | Enforce Incursion at 1000 points, 2 DP, 2 Enhancements, ordinary limit 2, and independent Battleline/Dedicated Transport limit 4. Preserve the explicit permission to select a single 3-DP detachment at Incursion; it is not a general 3-DP allowance. Certify Upgrade accounting: up to three copies, with second/third copies excluded from the Enhancement count but still paying points. | [25.03 Select Battle Size](https://www.40k.app/rules/25-muster-armies): the current Incursion table and duplicate exceptions. | — | APP-AUTHORITY |
| 68 | P25B | C25-03 | Warlord and Enhancement selections carry unit IDs, and `WARLORD` is applied to the whole unit. | Select/persist a specific Character model as Warlord and a specific eligible model as Enhancement bearer; derive unit keywords from membership without changing ownership. Certify Upgrade eligibility for non-CHARACTER units, per-model bearer restrictions where applicable, and cannot-be-WARLORD precedence over must-be-WARLORD. | [25.04 Fill Your Army Roster](https://www.40k.app/rules/25-muster-armies): Warlord and Enhancement bearer selections are model-specific. | P02D | APP-AUTHORITY |
| 69 | P25C | C25-04 | `DetachmentDefinition` cannot express generic required/prohibited units or required/prohibited other detachments. | Add typed source-neutral constraints and fail-closed roster validation, including duplicate-detachment prohibition; do not populate or evaluate faction-specific records here. Certify the existing requirement that every Support unit is attached to an eligible Bodyguard. Use the T4 army-construction grammar survey as the read-only family catalog: `docs/factions/taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md`. | [25.04 Fill Your Army Roster](https://www.40k.app/rules/25-muster-armies): apply the stated unit/detachment requirements and prohibitions. | — | APP-AUTHORITY |
| 70 | P24J | C24-10 | Intrinsic component Fights First effects are promoted to the attached rules unit by FightsFirstRegistry.from_state without proving every model has the ability. | Require every rules-present model to have Fights First. Distinguish intrinsic model/component sources from a source-authorized grant to the whole unit, including Charge and conditional Leader grants. Recompute after ordinary/retained casualties, cleanup, revival and splitting; certify fight order, Counteroffensive, restored source scope and replay. | [24.13 Fights First](https://www.40k.app/rules/24-core-abilities) and [01.02](https://www.40k.app/rules/01-core-concepts): every-model test and unit-wide grants. | P02D, P05B, P24A | APP-DRIFT |
| 71 | P17 | C17-01 | The shared shooting candidate exempts every CLOSE-QUARTERS weapon from the engaged Monster/Vehicle penalty and records the legacy big_guns_never_tire ID. | Exempt a CLOSE-QUARTERS attack only when the attacker's rules unit is engaged with that target. Preserve the distinct 10.06 attacking-model and 17.03 target-unit scopes, cumulative modifiers and final hit cap. Audit targeting and attack modifiers together; use stable current source IDs, regenerate affected identities and test third-party shooting, attached units, both penalty causes, all shared attack hosts and replay. | [10.06](https://www.40k.app/rules/10-shooting-phase) and [17.03](https://www.40k.app/rules/17-monsters-and-vehicles): weapon AND target-engagement exception. | P10, P02D, P02B | APP-DRIFT |
| 72 | P12B | C12-04 | P12 queues forced fights for both modes, combining the 40k.app Engaging body clause with the v931 Ongoing erratum. Their version equivalence is not established. | Resolve the affected rule body/erratum against a selected App version through the exception workflow. Record the exact resolution and supersession scope before changing or certifying either mode. Revalidate P12's shared queue, suspension, retained presence and historical replay against the resolved source; the union is not a source resolution. | [12.08](https://www.40k.app/rules/12-fight-phase) and retained gw-11e-core-fight:ongoing-consolidation-erratum (Game Datamissions v931). | P12, S-MIRRORS | EXCEPTION-PAUSE |
| 73 | PFINAL | CAUDIT-01 | No complete operative-clause inventory certifies the Core Rules; closing recent changelog deltas alone leaves the newly identified gaps unowned. | Re-audit all 25 categories after every implementation PR merges. Require a complete rule-clause/FAQ → immutable source observation → engine owner → facade regression inventory, including older operative updates, all v931/v946 obligations, reopened certification findings and cross-category lifetimes. Verify exact source fingerprints, semantics, adapters, replay and visibility before claiming compliance. Include the September 10 review dispositions, resolved C12-04/C18-07 evidence, Heavy movement history, and explicit Normal Move, objective-control-first and Action-interruption consumer checks. | All category 01–25 locators, every implementation source row, the September 10 clause review, and complete pinned v931/v946 observations. | All 71 implementation PRs; S-MIRRORS | FINAL-CERTIFICATION |

Categories 07 and 13 have no standalone remediation PR in this
sequence. Category 13’s current Light/Dense Hidden wording is governed by the
maintained App mirror and supersedes the older PDF’s Dense-only wording; it is
immediately usable without separate confirmation. Category 17 is owned by C17-01/P17. PFINAL re-audits both as
part of the complete 25-category gate. If that audit finds a gameplay gap, the
gap receives a canonical finding ID and a new one-at-a-time remediation PR
inserted before PFINAL.

## September 10 independent-review disposition

Reviewed against main `b41e44323f66f494399b763d8c7c23f981d9239f` and browser-visible
40k.app category clauses on 2026-09-10. The [clause-by-clause review](CORE_RULES_ROADMAP_REVIEW_2026_09_10.md)
records substantiation, qualifications, owning functions and certification checks.
It is planning evidence, not a new executable source package or a full-category
compliance certification. Historical source artifacts and observation hashes
remain unchanged. Every semantic PR still pins its exact source tuple.

Orders 1–35 retain their published identities. Nine new scoped PRs are inserted
in the future sequence; there are 71 implementation PRs, S-MIRRORS and PFINAL
(73 rows). C18-07/P18F retains the unresolved Shock engagement interpretation;
C18-08/P18G separately aligns unambiguous Core eligibility. The conservative
T-TRANSPORT milestone includes both plus the new C18-09/P18H setup restriction.
No grant is inferred from Core move availability, and this planning change does
not certify the existing Shock interpretation.

C12-04/P12B records an unresolved body/erratum conflict. Current 40k.app 12.08
places forced enemy selection under Engaging; the retained v931 erratum labels
it Ongoing. P12's shipped union is implementation history, not an approved source
resolution. The unversioned browser observation does not establish co-versioned
mirror disagreement. The affected semantics require the exception workflow and
selected-version evidence before certification. Objective Consolidation's
unengaged endpoint is explicitly present in current 12.08 and is not disputed.

New independent owners also cover general sequencing (C01-04), the CP-cost bound
(C02-05), per-model Charge constraints (C11-04), every-model Fights First
(C24-10), engaged Monster/Vehicle shooting (C17-01), and Core reserve defaults
and lifetimes (C20-02). P23 now enumerates all of 23.01–23.04 and its Hover
migration. P21A includes the actual Heavy helper and its already-recorded
turn-history defect; Order 33 has already fixed the misleading stationary name.

Existing behavior requiring explicit PFINAL consumer certification:

- 09.05.01: ordinary and reactive Normal Moves share the same once-per-phase
  history. Preserve current stale-submission rejection, attached lineage and
  cross-phase reset; do not label this rule wholly absent.
- 14.02.01: objective control precedes all other end-of-phase/end-of-turn
  rules. Audit both boundaries, suspended reactions, sticky control and scoring
  through the facade; existing determination and snapshot tests are evidence.
- 16.01: an Action cannot complete after a move other than pile-in/consolidation
  or after leaving the battlefield. The shared interruption owner covers
  ordinary and out-of-phase completion events, embark and reserve departure.
  Certify all Action families, both viewers, persistence and replay; the
  shooting/charge locks closed in Order 34 do not alone certify these consumers.

P15C, P21B, P24C2 and P25A/B/C carry the additional acceptance clauses identified
by the review. Their existing correct consumers remain evidence, not new gaps
merely because the older roadmap omitted their names. PFINAL cannot close with
any unresolved owner or certification row; discovered failures receive a scoped
finding and PR before it opens.

## September 5 review refinements

The owner authorized these planning corrections in PR #422 after review of
`01033287a7997c2e9cdca4605574f8c08683b868`. Orders 1–17 keep their published
identity; only the future sequence is renumbered. That revision contained 62 implementation
PRs plus S-MIRRORS and PFINAL. The reviewed live locators above and App-data
v946 (September 2) are planning evidence; each future semantic change still
requires the complete immutable source tuple specified by the source policy.

New closure keys are C24-08/P24H (optional Lethal Hits), C24-09/P24I
(individual Psychic modifiers), C15-07/P15G (Rapid Ingress eligibility),
C15-08/P15H (phase-end Overwatch targeting), C15-09/P15I (Crushing Impact
continuation), C16-01 and C16-02/P16 (Action restriction lifetimes),
C06-03/P06C (visibility geometry certification), and C18-07/P18F
(Assault/Shock source interpretation). Each occurs in exactly one canonical
row. P15D's historical exclusions are assigned to these owners rather than
left for PFINAL to discover again.

P06A's merged corridor-width work remains recorded, but does not close
C06-03. P18E's merged implementation remains recorded, but its full semantic
certification is reopened pending C18-07. Its historical Transport-engagement
interpretation is not new source evidence. Only P18F's affected semantics
pause for the unresolved wording; this does not require guessing an answer
or pausing the independent planned repairs.

P12 depends explicitly on P18E's queue abstraction, with ordinary Fight state
suspended and restored rather than cleared at queue completion. P05B moves
before P02D so model-keyword authority consumes the retained Fight On Death
presence contract. Regression lifetimes must distinguish ordinary removal,
retained models, and attached abilities that persist until the attacker has
finished all attacks. P16 supplies the shared restriction owner for Snap
Shooting and Firing Deck. Every new/changed decision still updates or explicitly
confirms the adapter decision contract in its implementation PR.

PFINAL's inventory must cover every operative clause and FAQ, including those
unchanged in v931/v946. A merged PR, passing tests or source load status alone
is not evidence of complete semantic execution.

The PR #422 follow-up also corrects an ordered-identity codec defect in P24D:
continuation deserialization must preserve declaration order for both physical
weapon IDs and failed-weapon IDs. Sorting either list changes positional die
ownership and can misalign the parallel profile list. The regression uses
non-lexicographic IDs, distinct profiles and mixed results, checks exact JSON
source-context round-trip and immediate completion, and restores/submits a
pending Feel No Pain choice through `GameLifecycle`. The existing adapter
contract already requires ordered identity; this correction changes no payload
shape or player-facing choice. Historical four-shard validation records below
remain historical; current PR policy and CI use the eight-shard inventory.

## Exception-only user disambiguation workflow

Routine confirmation against the official Warhammer 40,000 App is not required.
The owner-approved maintained direct App-data mirror snapshot controls source
selection, and the exact source row pinned in each implementation PR controls
that semantic change, unless one of these exceptions is actually encountered:

1. The user observes that the official App and a maintained mirror differ.
2. The mirror text needed by a finding is incomplete or genuinely ambiguous.
3. Co-versioned maintained direct App-data mirrors disagree.
4. Two maintained App statements are internally inconsistent and stable title
   plus complete operative text cannot resolve them.
5. More than one App version could govern because a tournament or project
   cutoff has not been selected.
6. The repository owner withdraws or narrows the source-authority policy.

Only the affected PR pauses. Ask the user one narrow question quoting or
paraphrasing the conflicting statements and identifying the affected finding.
If direct official-App evidence is needed to resolve the exception, record:

- provider, URL, App-data version/build, locale, timestamp, and timezone;
- the complete rule heading, operative text, notes, examples, and expanded
  sections needed for the disputed point;
- original capture hashes and an exact transcription hash when capture bytes
  are retained;
- the affected stable finding/source IDs, selected target version, resolution,
  and exact supersession scope.

Resolution rules:

- Current maintained App wording supersedes older PDFs and stale repository
  transcriptions.
- Mirror numbering is provider-local metadata; stable project identity binds to
  rule title and complete operative text.
- A stale PDF/repository conflict alone is not a reason to pause. P12 therefore
  proceeds from current 12.08 wording and removes or narrows the stale July row.
- P15D runs first after P00 to establish the category-15 source/package
  identity and provenance baseline. It records the contradictory category-12
  cross-reference while using the current Stratagem headings and complete
  operative text. Ask the user only if that contradiction proves irreducible
  during implementation.
- Category 13 Light/Dense Hidden wording proceeds from the maintained mirror.
- The combined FLY/HEAVY and mixed-keyword Hazard transcriptions are not added
  merely because they exist in an older repository row: the retained mirror
  did not show the complete statements. Ask only if a planned PR requires one
  of those unobserved claims.
- For Charge, apply cumulative modifiers after rerolls, then bound the result
  to 1–12 under 02.02.01. A raw 12 with +2 therefore yields a Charge result of
  12. Apply the additional Into the Fray cap and separate move-distance
  effects at their source-defined boundaries; never conflate them with raw dice.

## Required contents of every implementation remediation PR

Each PR description and its checked-in finding update must itemize:

```text
Status:
Finding IDs:
Dependencies and evidence gate:
Violated invariant:
How it is currently done:
How it should be done:
Specific authoritative maintained direct App-data mirror rule/statement and source ID:
Provider, URL, App-data version or observation timestamp, transcription SHA-256, and source-observation fingerprint:
Scope and explicit exclusions:
Owning state/validation/mutation/event/replay path:
Decision and viewer-visibility impact:
Regression scenarios and same-bug-class search:
Generated artifacts/documentation:
Validation results:
PR URL and merge commit:
```

Completion requires all of the following:

1. Rebase from current `main` after every prerequisite merges.
2. Pin the controlling maintained direct App-data mirror operative statement,
   stable source ID, provider, URL, App-data version or observation timestamp,
   transcription SHA-256, and retained source-observation fingerprint.
   Resolve an `EXCEPTION-PAUSE` only when one of the exception conditions above
   was actually observed.
3. Trace the authoritative owner from source data and decisions through
   validation, mutation, events, replay, adapters, and generated artifacts.
4. Add a failing invariant-focused regression before the fix and search the
   whole repository for the same bug class.
5. Route player choices through `DecisionRequest → DecisionResult`; route
   physical movement through `PathWitness` or typed placement validation.
6. Keep engine behavior fail-closed, content-neutral, deterministic, and free
   of runtime display-name/text branching, broad exceptions, or silent fallbacks.
7. Use real domain objects and facade-driven adapter coverage; add stale,
   malformed, replay, JSON-safety, and viewer-redaction cases when applicable.
8. Update source/evidence records, load and semantic status, adapter contract,
   generated JSON, hashes, and test-shard inventory atomically where affected.
9. Audit scope, architecture, and diff before running the final aggregate gates.
10. Run every command required by `AGENTS.md` after the last production change,
    push the branch, open the PR, and stop until the user merges it.

## Implementation finding updates

### P15D — C15-04

Status: Merged through PR #406.

Finding IDs: `C15-04`.

Dependencies and evidence gate: P00/PR #405 is merged. `APP-INTERNAL-DRIFT` is resolved by stable
title plus complete operative text; no `EXCEPTION-PAUSE` applies.

Violated invariant: Current maintained App source rows must cross the runtime boundary through
reviewed, typed, hash-pinned data with stable identity, complete provenance, and truthful separation
of load support from semantic execution. Provider numbering is locator metadata, not behavior
identity.

How it is currently done: The embedded Fire Overwatch row omits its unengaged/non-`TITANIC` target
and Snap Shooting relationship. The embedded Crushing Impact row says Vehicle/Strength despite the
maintained App's Monster-or-Vehicle/Toughness wording. No reviewed exact 15.05–15.09 artifact pins
the text, URL, timestamp, transcription hashes, or source-observation fingerprints. The Fight 12.01
example's stale Crushing Impact `15.06` reference is recorded only in the broad comparison audit.

How it should be done: Load exact reviewed 15.05–15.09 source records from one offline JSON
artifact through a typed fail-closed loader. Preserve the four existing Stratagem source IDs and all
runtime handler/policy/record IDs; add one title-based Snap Shooting source ID. Resolve the stale
Fight example to current Crushing Impact heading 15.05 by stable title and complete operative text,
and retain the contrary number as a typed anomaly.

Specific authoritative 40k.app rule/statement and source ID: Crushing Impact 15.05
`gw-11e-core-stratagems:core:crushing-impact`; Explosives 15.06
`gw-11e-core-stratagems:core:explosives`; Rapid Ingress 15.07
`gw-11e-core-stratagems:core:rapid-ingress`; Fire Overwatch 15.08
`gw-11e-core-stratagems:core:fire-overwatch`; and Snap Shooting 15.09
`gw-11e-core-stratagems:rule:snap-shooting`.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/15-stratagems`, observed `2026-08-26T11:15:23-04:00`:

- Crushing Impact: transcription `63fe27d984e7863a906d1ff7edeaef678fa69cdc1c6a7040869409749353e060`;
  observation `329f378b3cb1f78f28f7f32047e01e2b78295d155c30df9fde775bf0cab3afa4`.
- Explosives: transcription `c3b1f80f88da3e8772eed3d8fa49694c0f2c2539498a74aadd1b39cc859f897f`;
  observation `45c1a404c497f2d3d1cb0feb00ce09371fd3520bce8af43214930bc474dd9c41`.
- Rapid Ingress: transcription `2e9028ed2bf0c1fa19d7774ceb7bb81d415097e38b47c78ab67d7cff303955f6`;
  observation `42c4328d54aa18d826225dedd0b1e0043f4d8e3fe0f2e09d1ab12db7913314a6`.
- Fire Overwatch: transcription `7cbb6c048a5c5420b2209a7c585b6063dafebfbca4f1d6e52af607282c77c8f0`;
  observation `6cfdfa59d51b3bc1302101ac70a142bc3926ac2f532fb035254f4cc08eb6f9a1`.
- Snap Shooting: transcription `d9a660775aab4e7e07277850b27f2930682a232115bc720c81cb1618b50c5545`;
  observation `b88a09f338d839344e4d589dcc17b658cf075d11f20c079a9c55297ed70d1a26`.
- Fight 12.01 complete example statement at `https://www.40k.app/rules/12-fight-phase`:
  transcription `b2a5f5ff431ab3728a163d8d785d3c21a2270b9fc5793444af5ec5f150098dff`;
  observation `561c686491968ed20a2a6dd257a5b34cc02b72b0bcb633356d0baf96f815cc46`.

Load and execution support: All five current source rows are `loaded`. Crushing Impact, Explosives,
Rapid Ingress, Fire Overwatch, and Snap Shooting are each `partial_engine_runtime`. Rapid Ingress
remains partial because the existing runtime does not yet enforce its `AIRCRAFT` exclusion or
first-battle-round prohibition; P15D records those gaps without changing gameplay.

Scope and explicit exclusions: Source/evidence records, descriptive catalog text, stable identity,
the typed numbering anomaly, offline builder, tests, build identity, and affected generated contract
fixtures only. No validation, mutation, decision, movement, shooting, damage, event, replay, adapter,
network, UI, headless, AI, faction, detachment, datasheet, or out-of-scope content semantics change.
P15B still owns Explosives runtime remediation. The same-bug-class audit also records but does not
broaden P15D into Crushing Impact lifecycle/continuation, Rapid Ingress `AIRCRAFT`/battle-round
eligibility, Fire Overwatch trigger-target, or Snap post-shoot Action-lock remediation.

Owning state/validation/mutation/event/replay path: Reviewed JSON → typed
`core_stratagems_2026_08` loader → `RuleSourcePackage`/`SourceEvidenceCatalog` → preserved
`core_stratagems.py` facade → engine Stratagem catalog descriptive fields. Existing engine-owned
target validation, handler mutation, event emission, replay serialization, and adapter submission
paths remain unchanged. Engine build identity and its published external-contract examples consume
the reviewed packaged bytes.

Decision and viewer-visibility impact: None. No decision type, option family, proposal kind, payload
shape, visibility rule, redaction set, or adapter contract changes. Descriptive source text is public;
no hidden information is added.

Regression scenarios and same-bug-class search: A pre-fix regression failed on the stale
Vehicle-only Crushing Impact source. Coverage pins the five heading/title/source/runtime mappings,
operative hashes and fingerprints, stable handler/policy IDs, truthful support states, audit links,
and the complete category-12 anomaly statement; it rejects text, locator, identity, evidence-ID,
status, package, and raw-byte drift with typed errors.
The repository-wide search found no second current runtime-consumed Core Stratagem source copy.
Historical PDF/Wahapedia rows, legacy name aliases, audit prose, and the unrelated Orks rule named
Crushing Impact are explicit non-current exclusions.

Generated artifacts/documentation: Packaged `core_stratagems_2026_08/artifacts/package.json`, typed
loader, offline hash builder and its documented check command, engine build manifest, external
contract examples/manifest, and this finding update.

Validation results:

- All required `AGENTS.md` gates passed: Ruff check, Ruff format check, mypy, Pyright, the
  coverage-enabled xdist work-stealing suite (`6082 passed`), four-shard inventory, import-linter,
  and all-files pre-commit.
- The P15D source/evidence, source-only routing, malformed-artifact, and generated-data focused
  audit passed (`84 passed`); 13 unchanged runtime-path regressions also passed.
- Core-Stratagem builder check, 40k.app audit check, engine-build check, external-contract
  base-ref check, installed-wheel smoke (`2421` resources), generated ability-support audit
  (`19 passed`), and TypeScript generated/type/unit/conformance checks passed (`5` unit tests and
  `342` conformance assertions).
- This host exposes the required Node 24 binary but no `npm` executable, so `npm ci` and the two
  `npm run` wrappers could not be invoked verbatim. Their repository-pinned local equivalents
  (`check-generated`, `tsc --noEmit`, `tsx --test`, and `tsx src/main.ts`) passed.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/406`;
`43ffd74090c06e3b7db5d7e8249706ccecd9e650`.

### P08A + P08B — C08-01, C08-02, C08-03

Status: Combined P08A and P08B implementation is complete and merged in PR #407.

Finding IDs: `C08-01`, `C08-02`, `C08-03`.

Dependencies and evidence gate: P00/PR #405 and P15D/PR #406 are merged. The retained 2026-08-26
40k.app `/rules` search-index observation is authoritative RuleEvidence for the complete normalized
Command-phase heading sequence. The retained category-08 audit row is category metadata only and
does not satisfy exact-row evidence. The retained official Core Rules PDF separately pins the
operative 08.01, 08.02, and 08.03 statements. With those evidence roles kept distinct,
`APP-AUTHORITY` is satisfied and no `EXCEPTION-PAUSE` applies.

Violated invariants: Every rule triggered at the start of the Command phase, including every
engine-owned player choice, must resolve at one deterministic, resumable boundary before Gain Core
CP. Battle-shock must not be cleared merely because the active player's Command phase began. On the
first entry to the 08.03 Battle-shock step, the engine must snapshot the eligibility of every living
active-player canonical rules unit. It must resolve exactly one required test for every eligible
on-battlefield member, report eligible off-battlefield members as typed unsupported without
completing the step, and clear carried phase-start Battle-shock only when that required test
succeeds.

How it was done before this combined remediation: `BattleRoundFlow` dispatched the generic
`START_PHASE` window before entering `CommandPhaseHandler`, but the handler granted Core CP and
emitted `command_step_started` before its Command-specific synchronous hooks, status effects, and
finite choices. It also cleared the active player's existing Battle-shock at Command start, before
08.03 could test it, and the later Battle-shock request collection selected only units below
Half-strength. A currently Battle-shocked unit above Half-strength therefore lost the status without
a test, while a rules unit satisfying both predicates had no explicit immutable one-test snapshot.

Combined implementation: Keep generic `START_PHASE` as the outer lifecycle boundary. Inside the
Command handler, preserve all existing Battle-shock while the Command-start registry runs its
one-time synchronous pass, resumable effect pass, and finite-choice pass. If any nested or finite
decision remains pending, return without granting Core CP. After each accepted
`GameLifecycle.submit_decision(...)`, auto-advance to the next Command-start request or to boundary
completion. Final boundary completion grants each player 1CP exactly once and then emits
`command_step_started`; scoring and other Command-step work follow without clearing Battle-shock.

When the lifecycle first enters 08.03, snapshot every living active-player canonical attached
rules-unit identity together with its eligibility reasons and step-start strength context. Do not
snapshot future dice, Leadership, model placement, modifiers, or test requests. An eligible unit
with no alive placed model produces a typed `off_battlefield_battle_shock_test` unsupported result
containing the 08.03 source ID, canonical rules-unit ID, component IDs, and eligibility reasons; the
step remains unresolved. P01 remains responsible for implementing those off-battlefield tests.

For eligible on-battlefield units, use the existing generic sequencing decision when more than one
test is required. Materialize and persist only the current in-flight request, using the candidate's
actual eligibility reason and live dice, Leadership, model, placement, and modifier state. After
that test and all of its nested outcome continuations finish, record its completion and materialize
the next request from current authoritative state. Persist the candidate order, single in-flight
request, and completed prefix across reroll decisions, serialization, replay, and lifecycle re-entry.
A rules unit satisfying both predicates appears once and receives exactly one required test. A
successful required test clears Battle-shock when that candidate carried it into the step; a failed
test preserves or applies Battle-shock through the ordinary engine-owned outcome path.

Specific authoritative 40k.app rule/statement and source ID: The authoritative August 26 `/rules`
observation pins the complete normalized Command-phase heading order: Start of Command Phase, Gain
Core CP, Battle-shock, Command Abilities, and End of Command Phase. Stable source IDs
`gw-11e-core-rules:command-phase:start-of-command-phase`,
`gw-11e-core-rules:command-phase:gain-core-cp`, and
`gw-11e-core-rules:command-phase:battle-shock` bind the implemented 08.01-08.03 semantics without
runtime display-name or text matching. The official PDF is separate primary evidence for the
complete operative statements: resolve
start-of-Command triggers first; both players then gain 1CP; then test every active-player unit that
is currently Battle-shocked or at/below Half-strength and remove Battle-shock on a successful test.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules`, observed `2026-08-26T14:49:10-04:00`. The source package must retain the
full normalized heading sequence, per-heading transcription hashes, and a source-observation
fingerprint whose hashed payload covers the headings and their order. The category-08 row from the
2026-08-25 category audit remains metadata-only context because its fingerprint covers no heading or
operative text. Direct category access returned a security checkpoint, so no category-body capture
is claimed. The retained five-heading observation hash is
`e646d81ba284b1a4b5572b96d68cbfca52ef8cdf15cedf7c2c69ae8b5066c0ab`; exact per-rule
observation hashes are `9b5ce8b7402b6719772dec0ebca6e477d6f2c9a0ddb3b83f8504d2337d5c6d76`
(08.01), `9809dd16794d824ee12f6b7d6a8e0075e61cabde43c93a9bdfe9b797b5df283a`
(08.02), and `e60b785371c3815fe3a9a2b77ca4dc012c6e5541c95dbcc22f68b5452c576a78`
(08.03). The generated package hash is
`8785dda65406ce76add419f29263be499239122e1330941ab55a1dc3e6f10127`, its canonical
artifact-byte SHA-256 is `78b2264047e263ab5537c71c7d1be681874bdda31191816b6b297eb9a39425e6`,
and the final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:f529cb38565ef94f103e10500ca3a863ce50e50965c4d3c46f79e6ff1d3e45ac`.

Load and execution support: The final source package must record all three implemented rows as
`loaded` only after each row is linked to the authoritative `/rules` observation and the separate
official-PDF operative statement. Rows 08.01 and 08.02 are `executable_engine_runtime`; 08.03 is
truthfully `partial_engine_runtime`: every living active-player canonical rules unit is included in
the eligibility snapshot, but eligible off-battlefield tests stop with a typed unsupported result
until P01 supplies their execution semantics. The runtime consumer mapping covers the Command-start
boundary, Core CP transaction, eligibility snapshot, live one-at-a-time request materialization,
and successful phase-start recovery path.

Scope and explicit exclusions: This combined section covers the Command-phase timing owner,
resumable Command-start progress, one-time Core CP gain, preservation of phase-start Battle-shock,
the active-player canonical-rules-unit eligibility snapshot, typed eligible-off-battlefield
unsupported boundary, deterministic multi-test sequencing, live single-request materialization,
required-test completion progress, success-only recovery, deterministic events/replay/projections,
exact 08.01-08.03 source evidence, static ownership audits, generated build identity/contracts, and
timing documentation. It does not implement Battle-shock testing while embarked or in Strategic
Reserves; that execution work remains P01. It adds no faction content, proposal kind, movement,
geometry, or adapter-owned mutation.

Owning state/validation/mutation/event/replay path: `BattleRoundFlow` generic `START_PHASE` dispatch
→ `CommandPhaseHandler` canonical Command-start boundary with Battle-shock preserved → serialized
one-time synchronous/effect/finite-choice progress → engine-owned Core CP transactions → two
`command_points_gained` events → `command_step_started` → scoring/Command work → one-time 08.03
canonical-rules-unit eligibility snapshot → typed eligible-off-battlefield unsupported boundary or
bounded select-next sequencing choice → one live in-flight Battle-shock request/result and optional-reroll path →
success-only clearing of carried phase-start Battle-shock → exact
`battle_shock_modifier_applications_recorded` producer/source/operand authority → universal
retained Attached Unit identity and immutable battle-start component lineage validation after
component destruction → `battle_shock_step_completed` →
serialized game state, event log, replay, adapter projection, and event delta. No adapter validates
the predicate, constructs the snapshot, rolls the test, or mutates Battle-shock state.

Decision and viewer-visibility impact: The existing
`select_faction_rule_command_phase_start_option` decision type, option IDs, payload shapes,
stale/drift validation, queue behavior, record shapes, and public viewer visibility remain
unchanged. Multiple required Battle-shock tests reuse the public generic
`resolve_sequencing_order` decision with deterministic candidate IDs and one option per remaining
candidate; each selected test and its outcome finish before the next selection is requested, and
the final sole candidate is automatic. No future test request is materialized before its candidate
is selected. Battle-shock rerolls retain decision type
`select_dice_reroll` and their option IDs, but
their adapter-visible `battle_shock_context` now requires `passed_state_policy`: `preserve` for
non-Command forced-test success and `clear_if_step_start_shocked` for 08.03 success. The lifecycle
validates that field and the exact source, request, roll, phase-start IDs, base payload, resolved
event types, snapshot position, and completed-result prefix before queue pop. Public
`battle_shock_test_resolved` payloads now include `cleared_battle_shocked_unit_ids` beside the
engine-owned `state_update`, so adapters can audit success-only recovery without applying it. While
a Command-start choice is pending, both CP totals and all Battle-shock state remain unchanged. The public
Command-start selection events precede both Core CP gains and `command_step_started`; the public
`battle_shock_step_snapshot_created`, required-test request/result, and
`battle_shock_step_completed` events expose only the same Battle-shock information already visible
to both players. The public `battle_shock_modifier_applications_recorded` event exposes the exact
loaded producer, actual source, and modifiers applied to that public test; adapters audit or display
it but never apply it. P19 supersedes the former split events: the canonical Attached Unit and its
Battle-shock row remain stable through component loss, while immutable starting lineage remains
serialized authority. No hidden-information type or redaction set is added.

Regression scenarios and same-bug-class search: Required coverage includes synchronous, effect, and
finite Command-start work before CP; nested decision pause/resume without duplicated work; a
currently Battle-shocked unit remaining shocked through Command start and scoring; above-half,
below-half, and dual-reason snapshot membership; eligible off-battlefield typed unsupported payload
and unresolved step; exact-once attached-rules-unit testing; success-only recovery; failure
persistence; optional reroll pause/round-trip; snapshot drift rejection; destroyed
or detached component handling through canonical rules-unit identity; an outcome-enqueued nested
decision preempting the next required test while retaining the exact completed prefix; event
ordering; generic multi-test sequencing before dice materialization; live recomputation of a later
request after an earlier outcome removes a modifier source; actual forced-reason propagation into
dice hooks; post-Command history validation; authentic clear-before-split and split-before-clear
lineage histories; split-transfer deletion, partial-successor, and payload-tamper rejection;
required-test predicate tamper; loaded modifier producer/source/operand tamper; exact
move-completed trigger and source-binding tamper; attached producer paths for move hooks, generic
RuleIR Stratagems, and named Stratagems; replay; and both-viewer projections/event deltas.
P01-specific embarked and Strategic
Reserve behavior is not presented as covered here.

Generated artifacts/documentation: The combined PR updates the packaged Command-phase source
artifact and typed fail-closed loader, offline source/hash builder, engine build manifest, affected
external contract fixtures, `ARCHITECTURE_V2.md`, `docs/ADAPTER_DECISION_CONTRACT.md`,
`docs/DECISION_SUBMISSION_CATALOG.md`, and this finding record. The final source-package,
artifact-byte, retained-observation, and engine-build hashes are recorded above.

Validation results:

- All required `AGENTS.md` gates passed: Ruff check, Ruff format check, mypy, Pyright, the
  coverage-enabled xdist work-stealing suite (`6198 passed`), four-shard inventory, import-linter,
  and all-files pre-commit.
- The final module-size gate and focused Fight On Death physical-history regressions passed
  (`3` policy tests and `15` focused behavioral tests); the final Fulgrim Command-start/poison
  regressions passed (`5` tests).
- Command-phase source builder check, 40k.app audit check, engine-build check, external-contract
  base-ref check, installed-wheel smoke (`2449` resources), and generated ability-support audit
  (`19 passed`) all passed.
- The repository-pinned TypeScript generated-client, type, and unit checks passed (`5` unit tests),
  and the certified HTTP conformance scenario passed all `342` assertions. This host still exposes
  the required bundled Node runtime without an `npm` executable, so the equivalent pinned local
  binaries were invoked directly.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/407`;
`439072fc59c4defdffa49b1c9b17ef506c10b5ad`.

### P09A — C09-01

Status: Merged through PR #408.

Finding IDs: `C09-01`.

Dependencies and evidence gate: P08A+P08B/PR #407 is merged at
`439072fc59c4defdffa49b1c9b17ef506c10b5ad`. The retained category-09 audit row is category
metadata only. The exact 09.02 statement is retained separately as a reviewed transcription and
an authoritative 40k.app mirror observation, with their evidence roles kept distinct. The latter
is linked to the repository's recorded non-affiliation and project-authority policy. This satisfies
`APP-AUTHORITY`; no `EXCEPTION-PAUSE` applies.

Violated invariant: The 09.02 Move Units step is one player-driven loop. Each friendly unit must
be selected at most once from the union of units on the battlefield, in Strategic Reserves, and
embarked within a Transport; that selected unit must then resolve one eligible move type before
another unit is selected. Reserve arrival and disembark choices must not live in independently
ordered adapter or lifecycle loops.

How it worked before P09A: The movement handler enumerated only battlefield units in its main
selection loop. It front-loaded a separate `select_disembark_unit` loop, delayed ordinary reserve
arrivals until battlefield activations finished, and then opened a separate
`select_reinforcement_unit` loop. Tactical Disembark returned to global selection instead of
preserving the same selected unit for its required immediate Normal Move or Advance. Those split
paths made the legal order diverge from 09.02 and exposed four retired finite tokens:
`select_disembark_unit`, `complete_disembarks`, `select_reinforcement_unit`, and
`complete_reinforcements`.

Implementation: `MovementPhaseHandler` now derives one deterministic candidate set from the
authoritative `GameState`, canonical rules-unit identity, battlefield placement, `ReserveState`,
and Transport cargo state. Every `select_movement_unit` option carries the exact unit location,
complete component and physical model IDs, and Transport ID when embarked. An attached formation
is enumerated exactly once under its synthetic canonical rules-unit ID; component aliases are not
independent Move Units candidates. The subsequent `select_movement_action`
request derives actions from that same revalidated candidate: battlefield actions use the existing
movement resolvers, embarked units may Remain Stationary or Disembark when source-backed Transport
state permits it, and Strategic Reserve units may Remain Stationary or Ingress subject to their
arrival eligibility and requirement. Required arrivals expose only Ingress. Invalid, stale,
ambiguous-location, and unaccounted-model states fail closed before mutation.

Normal Move, Advance, Fall Back, and Remain Stationary preserve that canonical identity across
action selection, grouped path/coherency validation, mutation, completion records, lifecycle state,
replay, and adapter projection. One attached-unit witness contains every alive placed model across
all physical components, and the engine applies all component endpoints atomically or none. Embark,
Disembark, and reserve arrival likewise consume the complete canonical group and reject partial
cargo, placement, component, or model inventories.

An accepted ordinary Ingress action opens the existing typed placement proposal and completes that
unit only after valid engine-owned placement. Rapid and Combat Disembark complete the passenger's
activation after typed placement; attached Combat Disembark performs every component placement and
Hazard Roll as one grouped operation and routes mortal wounds and nested Feel No Pain under the
canonical attached identity. Tactical Disembark preserves the same active selection and binds the
exact emitted `unit_disembarked` event ID as a setup boundary. The engine closes all registered
move-completed/setup hooks for that occurrence, including serialized target and Feel No Pain
continuations, before offering the legal Normal Move or Advance continuation. If those effects
destroy or invalidate the disembarking rules unit, its canonical activation completes without a
stale follow-up action. Transport movement no longer injects a separate passenger selector;
eligible passengers remain ordinary candidates in the unified loop. The retired split decision types, option IDs,
dispatch registrations, interaction metadata, and dead selection helpers are removed rather than
retained as compatibility shims.

Specific authoritative 40k.app rule/statement and source ID: 09.02, `MOVE UNITS STEP`, states that
the active player moves units one at a time until all have been selected and finished; each unit is
selected from the battlefield, Strategic Reserves, or a Transport, then resolves Remain Stationary,
Normal Move, Advance, Fall-back, Disembark, or Ingress. The stable runtime source ID is
`gw-11e-core-rules:movement-phase:move-units-step`. Runtime behavior binds to this ID and structured
state, never the display heading or source-text tokens.

40k.app URL, observation timestamp, transcription SHA-256, and fingerprints:
`https://www.40k.app/rules/09-movement-phase`, observed
`2026-08-29T20:56:52-04:00`. The normalized transcription SHA-256 is
`6ea310aedead79971d092f9ae035b0c0b79499bcc656e3899a5546ba6234c54f`. The reviewed-transcription
observation SHA-256 is `5aa9978655e58af7c7d41cabd57c47d3bc8dc0daa884e2d2243206bd68f17afc`;
the authoritative mirror observation SHA-256 is
`a881b7623692015b3c92772f7fd508da782f832a225a922226735c9ed3e8fbc9`. The generated package hash
is `199be38f35856eddfb6f72395ffff7448f48be1b099db784788a8b64f0e97058`, its canonical artifact-byte
SHA-256 is `d55ccf8fa6f77cd06553be34153ed137b8d5c438dd8a454ff092c8333efcc2ee`, and the final engine build
ID is `warhammer40k-core-v2:runtime-tree-sha256-v1:c32f7a73a0f02ceff271cbae7507c9fbbe702e40d3cd349fe1f3850b3361d63e`.

Load and execution support: The generated rule row and both evidence rows are `loaded`; the rule
and authoritative mirror row are `executable_engine_runtime`. The reviewed transcription remains
truthfully marked `unverified_transcription_only`/`unverified` and is not presented as independent
authority. Runtime consumer IDs cover candidate enumeration, exact selection revalidation, and
move-type derivation.

Scope and explicit exclusions: P09A owns only the unified Move Units orchestration, exact source
identity, movement state/schema changes, ordinary Ingress and Disembark routing, same-unit Tactical
continuation, deterministic events/replay integrity, adapter contract shapes, viewer projections,
and regressions for the ordering bug class. It does not implement P09B Ordered Retreat/Desperate
Escape, P20 reserve Transports with cargo, P21A Take to the Skies, new faction semantics, or any
out-of-scope content. Existing `PathWitness` movement and typed placement proposal validation remain
the sole physical mutation paths.

Owning state/validation/mutation/event/replay path: authoritative army, battlefield,
`ReserveState`, and Transport cargo state -> `MovementPhaseState` unified selected/active/completed
progress -> `MovementPhaseHandler.begin_phase(...)` candidate enumeration -> public
`select_movement_unit` -> exact option/payload revalidation -> public `select_movement_action` ->
existing movement resolver, typed Disembark placement proposal, or typed Ingress placement proposal
-> engine-owned battlefield/reserve/cargo mutation -> deterministic domain and decision events ->
primary reserve-arrival integrity validation -> serialized lifecycle/replay -> shared adapter
projection and event-delta paths. Adapters select or submit; they never derive legality or mutate
authoritative state.

Decision and viewer-visibility impact: The existing public `select_movement_unit` and
`select_movement_action` types remain finite decisions with deterministic option IDs. Their
payloads add `source_rule_id`, unit options add `unit_location` and conditional Transport identity,
and action options now admit `disembark` and `ingress`. Disembark and Ingress retain their existing
parameterized placement proposal kinds and retry semantics. The four split finite tokens above are
retired. These choices and reserve/embarkation facts remain public and symmetric as before; no
hidden-information type, count, option family, or redaction branch is introduced. Contract 11.1.0
widens the live decision-family schema compatibly while preserving Contract 11.0 payload validity
and the closed v3 persistence artifact's 11.0.0 identity.

Regression scenarios and same-bug-class search: Coverage includes battlefield/reserve interleaving,
embarked/battlefield interleaving, required and optional Ingress, invalid and retry placement,
ordinary and Aircraft reserve replay, exact predecessor/source tamper rejection, passenger
eligibility after Transport movement, Rapid/Combat completion, Tactical same-unit continuation,
selection/location payload drift, impossible selected-but-incomplete state rejection, source
package/hash drift, adapter round trips, faction reserve hooks, and both-viewer projections. A
static code-quality audit proves the four retired tokens are absent from engine source, dispatch,
and interaction metadata. The bug-class search also updated every test helper and affected faction
scenario that drove the old split selectors.

PR #408 review remediation additionally covers one-option attached-unit enumeration; grouped
Remain Stationary, Normal Move, Advance, Fall Back, cross-component coherency, partial-cargo
rejection, Embark, Tactical/Combat Disembark, Strategic Reserve arrival, two-viewer adapter replay,
and grouped Hazard/FNP serialization. The real Swooping Hawks Grenade Pack catalog hook proves the
exact `unit_disembarked` occurrence resolves its target and FNP decisions before the follow-up move;
a destruction regression proves no stale movement action survives that setup boundary.

The replay-integrity re-review remediation authenticates a pending Tactical Disembark setup
boundary against exactly one `unit_disembarked` event and its retained player, round, phase,
canonical rules-unit, Transport, accepted action/proposal records, Disembarked state, cargo
transition, and complete component/model placement inventory. Lifecycle restore rejects boundary
ID substitution immediately; live resumption performs the same validation before hook dispatch,
boundary clearing, or any new decision. A same-round two-Disembark regression pauses the second
occurrence on its real Grenade Pack target request, substitutes the first event ID, and proves both
restore and resumption fail without mutation or a deferred post-move setup effect.

Generated artifacts/documentation: P09A adds the typed fail-closed movement source package and
offline builder, updates the 40k.app audit inventory, engine build manifest, Contract 11.1.0 live
decision schema and generated fixtures/manifest, `ARCHITECTURE_V2.md`,
`docs/ADAPTER_DECISION_CONTRACT.md`, `docs/DECISION_SUBMISSION_CATALOG.md`, and this finding record.

Validation results:

- Every required `AGENTS.md` gate passes: Ruff check, Ruff format check, mypy, Pyright, the
  coverage-enabled xdist work-stealing suite (`6311 passed`), four-shard inventory, import-linter,
  and all-files pre-commit.
- The PR #408 review-focused Fall Back, reserve, Transport, Swooping Hawks, and adapter suite passes
  (`243 passed`).
- Unified movement/reserve/Transport and retired-surface regressions pass (`151 passed`); corrected
  faction/replay scenarios pass (`17 passed`); source identity and generated artifact checks pass
  (`99 passed`).
- The movement source builder, 40k.app audit, engine-build check, external-contract exact
  `--base-ref origin/main` check, installed-wheel smoke (`2459` resources and `27` schemas), and
  generated ability-support audit (`19 passed`) all pass.
- The repository-pinned TypeScript generated-client, type, and unit checks pass (`5` unit tests),
  and the certified HTTP conformance scenario passes all `342` assertions on Contract `11.1.0`.
  The repository-pinned scripts were invoked through `npm.cmd` with the bundled Node runtime.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/408`;
`c63900a546c1da65a3400cc5dd8fa057408514f3`.

### P09B — C09-02

Status: Merged in PR #409 at `a4a8c1d3`.

Finding IDs: `C09-02`.

Dependencies and evidence gate: P09A/PR #408 is merged at
`c63900a546c1da65a3400cc5dd8fa057408514f3`. The exact 09.02.02 Selecting Modes and 09.07
Fall-back Move statements are retained separately as reviewed transcriptions and authoritative
40k.app mirror observations, with their evidence roles kept distinct and linked to the recorded
non-affiliation/project-authority policy. This satisfies `APP-AUTHORITY`; no `EXCEPTION-PAUSE`
applies.

Violated invariant: Selecting Desperate Escape is a legal alternative to Ordered Retreat for an
unshocked engaged rules unit. That selection must create one Hazard Roll for every model in the
complete canonical rules unit, apply all casualty and grouped movement mutations through the
engine, and then resolve the source-required Battle-shock test exactly when a model survives and
the unit is not already Battle-shocked.

How it was done before P09B: The finite Fall Back action request exposed
`fall_back:desperate_escape`, but `_fall_back_mode_violation_code(...)` rejected it when no
Battle-shock, overflight, or content source had already manufactured a Desperate Escape
requirement. Requirements and Hazard Rolls therefore covered only models reached by those other
causes, not every model based on the selected mode. The accepted Fall Back terminal path applied
casualties and movement and completed the activation without the 09.07 post-move Battle-shock
test.

How it is done after P09B: The selected Fall Back mode is a required input to the standalone and
group-aware resolvers. Desperate Escape contributes `selected_mode` to every model's typed
requirement; Battle-shock, forced-rule, and overflight reasons can be additive. Validation requires
the selected-mode requirement IDs to equal the exact `PathWitness` model inventory, and the dice
manager rolls each requirement once. Hazard casualties are selected through the existing finite
decision, removed through the authoritative grouped transition and primary destroyed-departure
path, and excluded from current-strength materialization only when those departure records prove
their absence. The engine applies the Fall Back transition, records `fall_back_move_applied`, and
uses the shared Battle-shock service. A surviving unit that is not Battle-shocked after moving
tests with reason/source kind `desperate_escape`; a shocked unit or a unit with no survivors does
not. Optional rerolls serialize and resume the same movement continuation before Embark or
activation completion. Nested Battle-shock outcome decisions use that same serialized parent and
must close before movement can continue.

PR #409 review remediation: the original P09B path preserved an optional reroll, but the shared
Battle-shock outcome registry discarded a provider-returned `LifecycleStatus`. A failed post-move
test under Chaos Knights Delirium could therefore queue Feel No Pain while movement independently
enqueued Embark or completed the activation. The corrected registry propagates exactly one status
and proves that it names the actual sole queue head. A typed parent continuation now spans both
reroll and outcome phases and pins the exact Fall Back occurrence, action/proposal authority,
transition and payload, Battle-shock request/result, optional reroll record, source kind, phase,
and provider claim. Movement resumes only after that outcome queue closes, then reconciles the
historical rules-unit identity before deciding whether Embark remains legal.

PR #409 re-review remediation: the same generalized `resolved_payload` plus `pending_status`
contract exposed a selected-target parent-ordering defect. Immediate catalog Battle-shock effects
now retain a typed, serialized parent across provider-owned healing or Feel No Pain chains for
post-shoot, Shooting-start, and Fight-start selections. The parent pins the original selection
request/result, phase and final event identity, loaded catalog/source/clause/target/effect
authority, resolved prefix and remainder, Battle-shock and optional-reroll identities, and the
provider's exact queue-head claim. Provider closure is authenticated before the resolved
Battle-shock payload is appended once; later effects then resume without reselecting the target,
and the final selected-target event is emitted once. A static caller inventory now fails when any
shared Battle-shock resolution caller is added or stops consuming both result fields without an
explicit no-parent proof.

PR #409 final re-review remediation: a retained selected-target suffix could contain another
immediate Battle-shock effect. When that later occurrence opened an optional reroll, the shared
resolver correctly returned an unresolved `pending_status`, but the parent remained in
`awaiting_remaining_effects` and authenticated only nested mortal-wound Feel No Pain. The retained
parent now records `awaiting_remaining_battle_shock_reroll`, authenticates the normal live
reroll request/roll/permission/event chain, and cross-binds its source record, resolved prefix,
remaining suffix, absolute continuation index, and original selection request/result/payload to
the retained parent. Reroll resolution returns the parent to remaining-effect processing or
progressively replaces it with the later Battle-shock provider continuation. The cohesive reroll
handler was extracted from the near-budget selected-target effects module so both production
modules remain below the 1,500-line limit.

Specific authoritative 40k.app rule/statement and source ID: 09.02.02, `SELECTING MODES`, states
that modes are mutually exclusive and assessed in order, but Ordered Retreat is not mandatory so
Desperate Escape may be selected instead. Its stable source ID is
`gw-11e-core-rules:movement-phase:selecting-modes`. 09.07, `FALL-BACK MOVE`, requires Desperate
Escape to make a Hazard Roll for each model and, after moving, requires a Battle-shock roll if the
unit is not Battle-shocked. Its stable source ID is
`gw-11e-core-rules:movement-phase:fall-back-move`. Runtime behavior binds to those IDs and typed
mode/state records, never headings, display names, or source-text tokens.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/09-movement-phase`, observed
`2026-08-30T13:55:17-04:00`:

- Selecting Modes: transcription
  `094c4bf218bd4c900864ee622364987378851fc06f23610ca95bd6574ee3c2d6`; reviewed-transcription
  observation `d573029a847de5780c46b2f4047b9057ed71c6258f27f9c16690ca7e529f7d7a`; authoritative-mirror
  observation `e5c209da27f60c11654788ed26c561e63374791fb345a032f3ce9a4620838db0`.
- Fall-back Move: transcription
  `2f9a2b3a35e8ca0f2d76a43b788c93b9feccaa66f2bba19a8b0ce348d401db0b`; reviewed-transcription
  observation `10a4ebcba3fb3c33df9e32ac9917d0ba0a2c7b2048cc9767c60ee587c909bd20`; authoritative-mirror
  observation `97d7323f54195e968c0cff8e7c8434ce5b5f8fe9dca4be3dc558359b3d1e9d23`.

The expanded generated package hash is
`0aacec8d0c56e882c0b03329a202a00512d9ace632d2b5f0e3bb53370e001105` and its canonical artifact
byte SHA-256 is `f3e378e933f70c8b4b579acdd7d46a5c8ec519ee3fbfb5efda1611edc747cff2`.
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:d0763f9c1beba10641fe9b52c4280d7c949dfa29e26b08b411296edd41edee57`.

Load and execution support: All three movement rule rows and all six evidence rows are `loaded`.
Move Units and Fall-back Move are `executable_engine_runtime`. Selecting Modes is truthfully
`partial_engine_runtime` because this package certifies its Fall Back consumer, not every mode in
the complete rules corpus. Reviewed-transcription rows remain
`unverified_transcription_only`/`unverified`; only the linked mirror observations carry project
authority.

Scope and explicit exclusions: P09B owns Fall Back mode validation, per-model Desperate Escape
requirements/Hazard Rolls, Hazard casualty transition evidence, the post-move Battle-shock and
reroll continuation, source identities/artifacts, replay integrity, adapter documentation, and
regressions for this bug class. It does not change general Hazard semantics, Ordered Retreat
movement geometry, non-Fall-Back modes, Transport rules, faction-specific effect semantics,
Command-phase Battle-shock, AI, or any out-of-scope content. Existing typed `PathWitness` and
canonical rules-unit movement remain the sole physical movement path.

Owning state/validation/mutation/event/replay path: reviewed generated JSON and fail-closed loader
→ stable Selecting Modes/Fall-back source IDs → finite `select_movement_action` mode option → typed
`submit_movement_proposal` with the same mode and group `PathWitness` → group-aware Fall Back
resolver and exact requirement/roll inventory → optional casualty selection → engine-owned
battlefield transition and primary departure/destruction events → `fall_back_move_applied` →
shared Battle-shock request/result/reroll/outcome continuation → identity reconciliation → Embark
or movement activation completion →
historical physical/source authority validation → lifecycle serialization/replay → shared adapter
projection and event-delta paths.

Decision and viewer-visibility impact: No new decision type or proposal kind is introduced. The
existing unshocked Fall Back action space now truthfully accepts both deterministic mode options;
the existing Desperate Escape casualty choice and `select_dice_reroll` family handle nested
choices. Fall Back payloads add stable source IDs, `selected_mode` reasons,
`battle_shocked_after_move`, and the exact requirement/roll/casualty inventory. Public
`fall_back_move_applied` authenticates the mutation while a follow-up test is pending. These facts
are public and symmetric, so the one shared adapter redaction path needs no hidden-type branch.
`docs/ADAPTER_DECISION_CONTRACT.md` confirms that the additive payload/event fields remain within
Contract 11.1.0.

Regression scenarios and same-bug-class search: Coverage includes voluntary Desperate Escape with
no forced or overflight cause, exact all-model selected-mode requirements and rolls, facade-driven
LocalGameSession submission, grouped movement/casualty application, the post-move Battle-shock
source/event ordering, optional reroll lifecycle serialization and resumption, shocked/no-survivor
predicate behavior, forced-source coexistence, Ordered Retreat exclusion, exact source/package
identity, and retained stale/malformed mode rejection. The repository-wide search updated every
direct Fall Back resolver caller to supply a typed mode, replaced the permissive
`desperate_escape_has_no_requirements` branch with exact inventory validation, and found no second
local voluntary-mode rejection or post-move Battle-shock implementation.

Review regressions add a facade-driven, full-lifecycle occurrence with an unshocked below-Half-
strength unit, voluntary Desperate Escape, an eligible Transport, a failed post-move test inside
the enemy Chaos Knights Delirium aura, and the resulting mortal-wound Feel No Pain chain. Direct
and optional-reroll variants prove the exact FNP queue head blocks Embark and activation
completion across serialization. A surviving target resumes into Embark and then completes; a
destroyed target emits no stale Embark request, records an empty-survivor identity reconciliation,
and restores/replays with the same authoritative result. The regression also pins the Fall Back
event, action/result/proposal identities, transition, movement payload, Battle-shock request/result,
phase, and provider-owned pending authority.

Selected-target re-review regressions drive the same loaded Chaos Knights Delirium provider
through `LocalGameSession` after both a direct and rerolled immediate Battle-shock test. They
prove the provider request is the sole queue head, a later persisting effect cannot execute early,
restoration retains the exact parent, replay produces one Battle-shock occurrence and one final
selection event, and the original target-selection group is not offered again. Equivalent
Shooting-start and Fight-start facade cases pin the phase-specific final event identities.

The final selected-target continuation regression uses one supported selection containing two
immediate Battle-shock effects followed by a persisting effect. Only the second effect receives a
reroll permission. It proves that the first provider request remains the sole queue head, provider
closure exposes the second reroll as the sole queue head, the new parent substate round-trips,
reroll resolution orders a second provider outcome before the persisting effect, both Battle-shock
occurrences and the final event are unique, target selection is not repeated, and replay reproduces
the complete state, decision, dice, and event histories.

Generated artifacts/documentation: P09B expands
`core_movement_phase_2026_08/artifacts/package.json` and its typed loader/source catalog, updates
the offline movement-source builder, engine build manifest, affected external-contract fixtures and
manifest, adapter decision contract, decision-submission catalog, P09A merge record, and this
finding record. No behavioral test file was added, removed, moved, or renamed, so the committed
four-shard inventory does not change.

Validation results:

- Every required `AGENTS.md` gate passes: Ruff check, Ruff format check, mypy, Pyright, the
  xdist work-stealing suite (`6330 passed`), four-shard inventory, import-linter,
  and all-files pre-commit.
- The final P09B Fall Back/static regression set and the cross-faction outcome-provider regression
  set pass (`74` and `77` tests respectively).
- The selected-target re-review facade set passes for direct, rerolled, Shooting-start, and
  Fight-start provider continuations plus the later-effect reroll boundary (`5 passed`); the final
  selected-target/provider/static focused set passes (`63 passed`), and the shared-result caller
  inventory plus module-size policy remain clean.
- Movement source builder check, 40k.app audit check, engine-build check, external-contract base-ref
  check, installed-wheel smoke (`2466` resources and `27` schemas), and generated ability-support
  audit (`19 passed`) all pass.
- The repository-pinned TypeScript generated-client, type, and unit entrypoints pass (`5` unit
  tests), and the certified HTTP conformance scenario passes all `342` assertions on Contract
  `11.1.0`. This macOS host's bundled Node 24 runtime did not expose an `npm` executable, so the
  equivalent pinned `node`, `tsc`, and `tsx` entrypoints ran directly; `npm ci` and the npm wrapper
  commands could not be executed.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/409`;
`a4a8c1d3`.

### P06A — C06-01

Status: Merged in PR #410 at `dab7d128`.

Finding IDs: `C06-01`.

Dependencies and evidence gate: P00 is merged. P06A has no gameplay prerequisite. The exact
06.01 Visibility statement is retained as a reviewed transcription and a separately classified,
project-authoritative 40k.app mirror observation linked to the recorded non-affiliation and
source-authority policy. This satisfies `APP-AUTHORITY`; no `EXCEPTION-PAUSE` applies.

Violated invariant: The visibility rule requires an imaginary straight line 1mm wide from any
part of the observing model to any part of the observed model. A zero-width mathematical segment
can pass through a slit that is narrower than 1mm or miss terrain or a model hull by less than half
the required width, incorrectly granting visibility to attacks and abilities.

How it was done before P06A: `VisibilityQuery` used a broad phase bounded by the unexpanded
segment and exact zero-width segment intersections for physical terrain and dynamic model hulls.
`TerrainVisibilityContext` separately used zero-width polygon intersections for terrain-feature
rules footprints and logical terrain areas. Attacks and visibility-gated abilities shared the
context, so the same infinitesimal-ray defect propagated to every consumer.

How it is done after P06A: One geometry-owned visibility-corridor module defines the fixed
1mm width, its inch conversion, half-width, expanded broad-phase bounds, and the exact physical
intersection surfaces. Every sampled source-to-target line is buffered horizontally by 0.5mm
with flat endpoint caps. Physical terrain and model hull checks combine that shared horizontal
corridor with the authoritative interpolated line height and obstacle vertical interval. Terrain
feature rules footprints and logical terrain-area unions use the same corridor footprint. The
central `TerrainVisibilityContext` remains the sole engine visibility owner, so shooting,
Stratagems, mission actions, and generic RuleIR ability predicates all receive the correction
without local rules or string parsing.

Specific authoritative 40k.app rule/statement and source ID: 06.01, `VISIBILITY`, states that an
observing model has line of sight only when an imaginary straight line 1mm wide can be drawn from
any part of it to any part of the observed model; models in the observing and observed models'
own units are ignored, while terrain applies its additional visibility rules. Its stable source
ID is `gw-11e-core-rules:other-concepts:visibility`. Runtime behavior binds to fixed geometry and
that source-backed execution record, never a display name or source-text token.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/06-other-concepts`, observed
`2026-08-31T11:41:03-04:00`; transcription
`eefe89c9c39b6d8560ba274d414567faebfad2aa17f2b84b5745eb714ffd9883`;
reviewed-transcription observation
`7c9700d51718a74421b3a992336fef7ed34ba40e77c1f3ad6f70a4c91e2f7a30`;
authoritative-mirror observation
`cf12c5ecc2b7fdc082246161fcbab2e301df0a1eb8134f4b69175f0884a35a9a`.
The generated package hash is
`409c0bd79aa7e8f70495f714ecb05b45bff971520c3cac52360fcbdcf42fca99` and its canonical artifact
byte SHA-256 is `bd3efb8e43386a951343915595b7d7eb5e189380f0e0e85a83c731baac44423b`.
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:155062a0cdb997a61d61d61f9378993336897f88e4f93bbaee1c446bf89f8ce1`.

Load and execution support: The Visibility rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked mirror observation carries project
authority. The fail-fast typed loader pins schema, document identity, rule identity, text hash,
both evidence fingerprints, package hash, and canonical artifact byte hash.

Scope and explicit exclusions: P06A owns the fixed corridor unit, 2.5D physical intersections,
broad-phase expansion, terrain-feature and terrain-area use, source identity/artifact, consumer
regressions, static bypass audit, adapter-contract confirmation, and build identity. It does not
change which source/target-unit models are ignored, model-volume sampling, terrain-specific
visibility exceptions, cover semantics, hidden-information policy, movement/pathing collision,
decision families, event payload schemas, or out-of-scope content.

Owning source/validation/mutation/event/replay path: reviewed generated JSON and fail-closed
loader → stable Visibility source ID and executable consumer inventory → geometry-owned fixed
corridor constants and Shapely exact intersections → expanded `VisibilityQuery` broad phase →
`TerrainVisibilityContext` physical, feature-policy, and logical-area resolution → shared engine
shooting/Stratagem/mission-action/generic-ability targeting services → unchanged deterministic
line-of-sight witness, cache, decision, event, projection, and replay paths. Visibility is a pure
query and does not mutate authoritative state.

Decision and viewer-visibility impact: No new decision type, option family, proposal kind,
adapter-visible payload shape, replay schema, or hidden-information family is introduced.
Existing deterministic option lists can change only because the engine now computes correct
visibility. Existing witness payload field names remain stable even though their sampled lines
are evaluated as corridors. Visibility geometry and eligibility are public and symmetric in the
current scope, so the shared redaction path needs no new branch.
`docs/ADAPTER_DECISION_CONTRACT.md` confirms this remains within Contract 11.1.0.

Regression scenarios and same-bug-class search: Geometry regressions prove a terrain edge and a
dynamic circular model hull 0.01in from a centerline block, an edge 0.021in away remains clear,
and a corridor above the obstacle's 2.5D height remains clear. Terrain-policy regressions cover
both feature rules footprints and logical terrain-area unions. Consumer regressions prove a
shooting target and a visibility-gated generic ability cannot exploit a 0.02in slit that remains
clear to a zero-width line but is narrower than 1mm. Payload round trips retain deterministic
results. A static audit fails if any central visibility module reintroduces the prior zero-width
terrain/model/polygon helpers or if an engine module bypasses the central visibility owner by
importing low-level corridor/query geometry directly.

Generated artifacts/documentation: P06A adds
`core_other_concepts_2026_08/artifacts/package.json`, its typed loader/source catalog, and its
offline builder; regenerates the engine build manifest and affected external-contract fixtures;
and updates the adapter decision contract and this finding record. No behavioral test file was
added, removed, moved, or renamed, so the committed four-shard inventory does not change.

Validation results:

- Every required `AGENTS.md` gate passes: Ruff check, Ruff format check, mypy (`2641` source
  files), Pyright (zero errors or warnings), the 18-worker xdist work-stealing suite
  (`6339 passed`), four-shard inventory, all 11 import-linter contracts, and all-files pre-commit.
- The final P06A geometry, terrain-policy, attack, ability, source-identity, and static regression
  set passes (`125 passed`); the complete code-quality suite passes (`335 passed`).
- Other Concepts source builder check, 40k.app audit check, engine-build check, external-contract
  `--base-ref origin/main` check, and installed-wheel smoke pass (`2470` resources and `27`
  schemas).
- The repository-pinned TypeScript generated-client, type, and unit entrypoints pass (`5` unit
  tests), and the certified HTTP conformance scenario passes all `342` assertions on Contract
  `11.1.0`. This macOS host's bundled Node 24 runtime did not expose an `npm` executable, so the
  equivalent pinned `node`, `tsc`, and `tsx` entrypoints ran directly; `npm ci` and the npm wrapper
  commands could not be executed.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/410`;
`dab7d128`.

### P06B — C06-02

Status: Merged in PR #411 at `eae5b7f1`.

Finding IDs: `C06-02`.

Dependencies and evidence gate: P00 is merged. P06B has no gameplay prerequisite. The exact
06.02 Mortal Wounds statement is retained as a reviewed transcription and a separately
classified, project-authoritative 40k.app mirror observation linked to the recorded
non-affiliation and source-authority policy. This satisfies `APP-AUTHORITY`; no
`EXCEPTION-PAUSE` applies.

Violated invariant: Mortal wounds are resolved individually and the target unit's controlling
player selects the model for each wound under a mandatory four-tier priority. When multiple
models share the active tier, silently selecting the first sorted model bypasses the decision
contract and lets iteration order mutate authoritative wounds, destruction state, events, and
replay.

How it was done before P06B: The shared mortal-wound continuation reused ordinary attack damage
allocation and selected `legal_model_ids[0]`. The direct helper likewise selected the first
sorted legal model. Neither path represented an active-tier tie as a player choice, and several
generic and faction producer continuations recognized only Feel No Pain requests, so a model
choice could not pause and resume through one common engine-owned route.

How it is done after P06B: The typed mortal-wound model allocator recomputes the legal tier before
every individual wound in this exact order: wounded non-Character, other non-Character, wounded
Character, then other Character. A sole legal model is selected automatically. A tie emits the
finite public `select_mortal_wound_model` request to the target unit's controlling player with
deterministic model IDs and complete serialized progress. Lifecycle validation recomputes the
current tier before queue pop or mutation and rejects stale, drifted, malformed, wrong-actor, or
wrong-context submissions. The selected model then resumes the same per-wound route, including
Feel No Pain, destruction authority, event recording, producer continuation, and replay.

The model-selection-to-Feel-No-Pain continuation is independently authenticated. Before a child
Feel No Pain request is emitted, the engine records a private per-wound allocation occurrence that
binds the application and ordinal wound, canonical target, exact 06.02 tier and legal inventory,
selected model, automatic-or-player disposition, exact parent request/result closure when chosen,
and the selected model's loaded Feel No Pain sources and decline policy. Restore and lifecycle
prevalidation reconstruct the occurrence, parent closure, child request, and exact events before
queue pop, recording, RNG, damage, or completion. Damage application separately requires the
supplied model to belong to the retained target rules unit. Each application also freezes the
target's owner, exact physical component-unit inventory, and Character-component classification.
Freeze and validation share one state-derived Character-component owner: the retained formation
uses its actual Leader/Support roles plus authoritative Character keywords, cross-checked against
the exact matching `StartingAttachedUnitRecord`. The retained set
must equal that reconstruction, so a coordinated rewrite of progress, application-started event,
allocation occurrence, parent closure, child request, and request events cannot reclassify a
Character as a non-Character or bypass living Bodyguards.
If destruction removes an Attached Unit component before the packet finishes, the allocator keeps
the original canonical target, continues across every living placed model in that frozen lineage,
and recomputes the four tiers over that packet-wide population. Restore, Feel No Pain authority,
logical-death validation, and final destruction evidence consume the same lineage; they do not
terminate a packet while any model from the retained rules unit survives. Shared
attack-sequence ownership now classifies the complete decision family once; Fight-owned deferred
mortal wounds, including active reaction frames, keep their Fight host across model selection,
Feel No Pain, serialization, and replay.

Specific authoritative 40k.app rule/statement and source ID: 06.02, `MORTAL WOUNDS`, states that
the controlling player resolves each mortal wound one at a time and must select, in order, a
wounded non-Character model, another non-Character model, a wounded Character model, or another
Character model; the selected model loses one wound. Its stable source ID is
`gw-11e-core-rules:other-concepts:mortal-wounds`. Runtime behavior binds to the typed allocator
and this source-backed execution record, never a display name or source-text token.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/06-other-concepts`, observed
`2026-08-31T13:01:46-04:00`; transcription
`9b8eedb42371fc609796c18ede005681d025fba136d3a8b9578f74c5a550d831`;
reviewed-transcription observation
`57b9542afdef85452b316c1bf695591d5d66165a01bf2b0a6fc0b9104890516d`;
authoritative-mirror observation
`faa8f4b08ebb8663e2ae5f84373465d5691b58ca56d67e461b9e81fdea4abc8a`.
The generated package hash is
`3e7a13f4483549fda41111147601d4f51fd6f513203ca328143df2eb3fa7335a` and its canonical artifact
byte SHA-256 is `d2ed90878ed9b54bee86c89432e0c9a452705da959b7bc7cf4934ada1e1cf16d`.
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:a037e6022153168221c9b30efd361c333ed14ee93ea1e762196524ac08a64760`.

Load and execution support: The Mortal Wounds rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked mirror observation carries project
authority. The fail-fast typed loader pins schema, document identity, rule identity, text hash,
both evidence fingerprints, package hash, and canonical artifact byte hash.

Scope and explicit exclusions: P06B owns the four priority tiers, per-wound recomputation, finite
tie choice, sole-model auto-selection, serialized progress, lifecycle validation and dispatch,
producer continuation migration, public adapter projection/event behavior, source identity,
regressions, and static bypass audit. It does not change Mortal Wounds generation, Feel No Pain
eligibility or dice rules, damage spill semantics, Character keyword ownership, ordinary attack
damage allocation, out-of-scope content, or hidden-information policy.

Regression coverage includes facade submission and replay after the last Bodyguard is destroyed
mid-packet while the original Attached Unit identity remains. One case leaves Leader and Support
Character models and exercises the Character-tier model decision plus Feel No Pain across
serialized checkpoints; a second leaves one Character model and proves deterministic
automatic continuation rather than an erroneous unit-destroyed termination. Coordinated
classification-drift regressions modify every retained authority copy at both the pending model
choice and pending Feel No Pain boundaries and prove restore and lifecycle submission reject before
any queue, decision, RNG, wound, destruction, or completion mutation.

Owning source/validation/mutation/event/replay path: reviewed generated JSON and fail-closed
loader → stable Mortal Wounds source ID and executable consumer inventory → producer-owned
`MortalWoundApplicationProgress` → typed mortal-wound model allocator → deterministic finite
`DecisionRequest`/`DecisionResult` → lifecycle prevalidation and shared decision dispatch →
engine-owned one-wound mutation and optional Feel No Pain → destruction authority, producer
continuation, events, projections, and replay. Adapters only submit an option ID and never select
or mutate the model independently.

Decision and viewer-visibility impact: P06B adds one finite decision family,
`select_mortal_wound_model`, with deterministic model-instance option IDs. Its public request
payload includes target unit, source rule, remaining wounds, active priority tier, legal model
IDs, and replay-safe serialized progress; the selected option payload identifies the model and
tier. The target unit's controlling player is the actor, while both viewers receive the same
public pending request and public event delta. Shared adapter redaction remains the sole
projection/event owner. `docs/ADAPTER_DECISION_CONTRACT.md` and
`docs/DECISION_SUBMISSION_CATALOG.md` record the new family and stale-context behavior.

Regression scenarios and same-bug-class search: Real attached-unit regressions walk all four
tiers, prove serialization/restore, reject priority drift without queue pop or mutation, and
prove model choice → Feel No Pain → later model choice continuation. Adapter coverage submits
the option through `LocalGameSession` and verifies both public viewer projections and public event
deltas. Producer regressions cover shooting/fight damage, Hazardous, Deadly Demise, transport and
movement hazards, generic RuleIR mortal wounds, Explosives, Corsair Lethal Ruse, Daemonic Terror,
Malice Made Manifest, Spiteful Demise, and existing faction army-rule continuations. The bug-class
search migrated every production caller to the shared resolution request; the only remaining
`apply_mortal_wounds_to_unit` production occurrence is its fail-closed wrapper definition. A
static audit pins the allocator, lifecycle validator, direct-helper tie guard, adapter contract,
and absence of the sorted-first fallback.

Generated artifacts/documentation: P06B extends
`core_other_concepts_2026_08/artifacts/package.json`, its typed loader/source catalog, and its
offline builder; adds the typed allocator and shared attack-sequence decision-family modules;
regenerates the engine build manifest and affected external-contract fixtures; and updates both
decision-contract documents and this finding record. No behavioral test file was added, removed,
moved, or renamed, so the committed four-shard inventory does not change.

Validation results:

- Focused allocation-authority, source, tier-order, stale-decision, Fight-host, reaction-frame,
  replay, adapter, redaction, producer, faction-continuation, and static-audit regressions pass.
- Repository-wide Ruff check and Ruff format check pass; mypy passes across `2646` source files;
  Pyright reports `0 errors, 0 warnings`; all `11` import-linter contracts pass; the exact
  four-shard inventory check and all-files pre-commit gate pass.
- The required xdist work-stealing suite passes (`6364 passed` in `402.70s`), including the
  complete code-quality suite.
- The Other Concepts source artifact, final engine build identity, and external contract all pass
  fail-closed drift checks, including the `origin/main` compatibility comparison.
- Installed-wheel smoke passes with `2475` packaged engine resources and `27` schemas. Generated
  TypeScript client drift and type checks pass, and the two-server HTTP conformance scenario passes
  all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/411`;
`eae5b7f1`.

### P19 — C19-01

Status: Implementation, required local validation, source/contract regeneration, and remote PR
publication are complete; review and merge are pending.

Finding IDs: `C19-01`.

Dependencies and evidence gate: P09B, P06A, and P06B are merged. The exact 19.01.01 statement is
retained as a reviewed transcription and a separately classified, project-authoritative 40k.app
mirror observation linked to the recorded non-affiliation and source-authority policy. This
satisfies `APP-AUTHORITY`; no `EXCEPTION-PAUSE` applies.

Violated invariant: Models that began as one Attached Unit remain one rules unit for the stated
duration. Bodyguard, Leader, or Support component loss must not retire the original rules-unit ID,
mint singleton successor rules units, or transfer authoritative state to component IDs while any
model that started in the Attached Unit remains.

How it was done before P19: Shared destruction reconciliation dissolved an Attached Unit whenever
only Bodyguard models or only Leader/Support models remained. It removed the formation and original
Starting Strength row, generated component Starting Strength rows, expanded historical identity
lookups into successor units, and transferred Battle-shock, ReserveState, persisting effects,
Mission Action, Fight, selected-target, and replay-visible state through bespoke split events.
Several history validators and scoring snapshots accepted either the root or a reconstructed set of
singleton component rows.

How it is done after P19: The original `AttachedUnitFormation`, canonical rules-unit ID,
`StartingStrengthRecord`, and `StartingAttachedUnitRecord` remain authoritative through every
component loss. The immutable starting record supplies explicit Bodyguard, Leader, Support,
component, and starting-model lineage. Dead components remain in that lineage but contribute no
living models, keywords, abilities, or required battlefield placement. Shared destruction hosts
validate that the retained formation, owner, source, component inventory, and root-only Starting
Strength still match battle-start authority. Rules-unit identity lookup returns exactly one current
root for either the canonical ID or a physical component alias; historical successor expansion and
split-state mutation are removed.

`RulesUnitView.living_components` is the single authority for semantic component contribution.
Rules-unit keyword aggregation, grouped battlefield placement, Embark capacity profiles, Gate of
Infinity ability/presence/engagement checks, Datasheet/RuleIR/Enhancement reserve-entry authority,
ordinary and Stratagem reserve-arrival proposal context, Deep Strike placement-kind authority,
arrival drift/integrity validation, Daemonic Incursion keyword checks, movement-location
enumeration, and Disembark eligibility and proposal authority all consume that view. Immutable
`component_unit_instance_ids` remain the lineage and replay identity surface; they are not a proxy
for current semantic or physical presence.

Transport cargo is current physical authority rather than Attached Unit lineage. Embark records
only the living component IDs present in its accepted `RulesUnitPlacement`; Disembark removes that
same physical set; and primary departure evidence retains the complete canonical lineage while
recording only components and models that actually departed. Both damage-based and rule-based
model destruction converge on shared cargo reconciliation: when the last model in an embarked
physical component is destroyed, its ID is removed from current cargo without rewriting
start-of-phase history or treating destruction as a Disembark. An unarrived Transport's current
ReserveState cargo manifest is updated with that cleanup, and transport-state integrity
rejects any payload that retains a wholly destroyed component as current cargo.

During-battle reserve departure likewise records affected/departed component IDs from the accepted
living `RulesUnitPlacement`, while retaining the complete Attached Unit lineage on the evidence
row. Gate of Infinity prepares and validates that evidence against the prospective battlefield
before changing ReserveState or battlefield state, so a departure-evidence rejection cannot leave
a partially moved unit. Ordinary, Rapid Ingress, and generic Stratagem arrival requests advertise
only living physical components, and reserve placement plus replay integrity require that exact
historical request inventory rather than every immutable lineage component.

Battle-shock, ReserveState, persisting effects, Mission Actions, Fight activation consumption,
selected-target chains, healing, scoring witnesses, and adapter-visible unit identities stay on the
canonical root. Exact physical model and component IDs remain in placement, attack attribution,
departure evidence, and component lineage where physical ownership matters. Turn-start snapshots
fail closed unless the retained root owns the exact frozen component set. The obsolete
`attached_rules_unit_split_reconciled`,
`battle_shock_state_transferred_after_attached_unit_split`, and
`reserve_state_transferred_after_attached_unit_split` routes are no longer emitted; restore owners
reject those legacy events instead of reconstructing successor state.

Specific authoritative 40k.app rule/statement and source ID: 19.01.01, `ATTACHED UNITS AFTER THEIR
BODYGUARD UNIT IS DESTROYED`, states that when a rule would separate attached Leader/Support units
after Bodyguard destruction, all of those Leader/Support units remain one unit for all rules
purposes. Its stable source ID is
`gw-11e-core-rules:attached-units:bodyguard-unit-destroyed`. Runtime behavior binds to the typed
retained-identity validator and this source-backed execution record, never a display name or
source-text token.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/19-attached-units`, observed
`2026-09-01T09:02:35-04:00`; transcription
`cb8ea6a1b9633420c8a2c59989edf8bfd97987ce1847faca6820f08b99931bbe`;
reviewed-transcription observation
`29c65f1de8ddfd855323b8d0ef6f99b5ce6d28e322034ca2e68097398e408aec`;
authoritative-mirror observation
`ee513960052396784786dee07ff736c25c0c120f06e56d6940b020fdf71f2d5d`;
category-audit source observation
`9328cc0ae8f0c22dc52418c3238a105d7031cdfdb5daf78bd377c56f36c795bd`.
The generated package hash is
`3f6e0c6b6c3b9a96d19967e2ef5c8ab0429fd7fc8b025304b84e3dc5cb243570` and its canonical artifact
byte SHA-256 is `748cf1bc4cbd2749655abab43e97c7e04acfa4e63e79b9f84b565001b9c17b66`.
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:dbd3e0a74057c2fe69ad90b478795cfeffa6260f342881d6869124147a68a17e`.

Load and execution support: The Attached Units rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked mirror observation carries project
authority. The fail-fast typed loader pins schema, document identity, rule identity, text hash,
both evidence fingerprints, package hash, and canonical artifact byte hash.

Scope and explicit exclusions: P19 owns retained Attached Unit identity after component loss,
explicit component/start-model lineage, root Starting Strength, placement treatment for dead
components, cross-cutting authoritative state identity, history/restore rejection of obsolete
split routes, source identity, adapter-contract documentation, regressions, and static bypass
audit. It does not change legal attachment declarations, Bodyguard allocation priority, Leader or
Support eligibility, model-return limits, the source rules that grant reserve entry, scoring rules,
hidden-information policy, or any out-of-scope content. Existing reserve and transport eligibility
checks now correctly ignore wholly destroyed lineage components.

Owning source/validation/mutation/event/replay path: reviewed generated JSON and fail-closed loader
→ stable Attached Units source ID → `AttachedUnitFormation` plus battle-start
`StartingAttachedUnitRecord`/root `StartingStrengthRecord` → shared destruction mutation → retained
identity validation → current rules-unit/placement/Battle-shock/ReserveState/effect/Action/Fight and
scoring consumers → deterministic events, projections, serialization, and replay. The engine alone
mutates model state; adapters continue to submit existing decisions and never derive successor
units or transfer state.

Decision and viewer-visibility impact: P19 adds no decision type, finite option family,
parameterized proposal kind, payload field, visibility rule, or replay schema. Existing unit-ID
fields now consistently retain the canonical Attached Unit ID after component loss while existing
physical model/component fields continue to report exact ownership. No hidden-information type or
redaction set is added. `docs/ADAPTER_DECISION_CONTRACT.md` records that existing contract.

Regression scenarios and same-bug-class search: Real destruction covers Bodyguard-only loss,
Leader-only loss, Leader-plus-Support survivors, Feel No Pain continuations, Battle-shock,
selected-target effects, persisting effects, Mission Actions, Fight on Death, activation
consumption, reserve arrival, later healing, primary departure/scoring evidence, adapter viewer
projections and deltas, serialization, and replay. Horror Split materialization still performs its
source-backed datasheet/model handoff while preserving the Attached Unit root. Static audit scans
all engine calls for the removed split/recovery/transfer APIs and requires every shared model-loss
host to invoke retained-identity validation. Follow-up regressions cover Embark after either Leader
or Bodyguard loss, including capacity exclusion and transition-model precision; Gate of Infinity
after either loss, with the destroyed component lacking the ability and battlefield placement;
mission-backed Gate departure evidence, actual living-only reserve arrival, lifecycle replay, and
failure atomicity; Daemonic Incursion keyword aggregation; and complete affected-file behavior.
Static audit also
requires grouped Embark placement and every identified ability, keyword, reserve-authority, and
capacity consumer to use `living_components` instead of directly scanning immutable lineage. The
post-loss Embark-to-Disembark regression proves cargo drains completely and the retained root is
enumerated on the battlefield again. Damage and direct-rule destruction regressions prove shared
cleanup for components destroyed while already embarked, including current unarrived-Reserve
manifest reconciliation. The obsolete split-history and reserve-transfer modules are absent.

Generated artifacts/documentation: P19 adds
`core_attached_units_2026_09/artifacts/package.json`, its typed loader/source package, and the
offline builder; regenerates the engine build manifest and external-contract identity examples;
updates generated Emperor's Children support documentation, the adapter contract, decision
catalog, source-audit instructions, and this finding record. No behavioral test file was added,
removed, moved, or renamed, so the committed four-shard inventory does not change.

Validation results:

- Focused source, identity, component-loss, Battle-shock, ReserveState, effect, Action, Fight,
  healing, scoring, adapter, replay, Horror materialization, and static-audit regressions pass. The
  review follow-up's complete affected-file cluster passes all `227` tests, including Embark and
  Gate of Infinity after either Leader or Bodyguard loss and Daemonic Incursion keyword authority;
  the remaining-blocker transport/static cluster passes all `118` tests, including post-loss
  Embark-to-Disembark, already-embarked destruction cleanup, unarrived-Reserve synchronization,
  and stale-cargo rejection; the reserve-lifecycle follow-up cluster passes all `225` tests,
  including mission-backed Gate departure, both component-loss arrival directions, replay,
  failure atomicity, ordinary/Stratagem arrival authority, and the expanded static audit; the
  complete affected reserve/departure/Stratagem/aircraft/static cluster passes all `529` tests;
  the complete code-quality suite passes all `342` tests.
- Repository-wide Ruff check and Ruff format check pass; mypy passes across `2647` source files;
  Pyright reports `0 errors, 0 warnings`; all `11` import-linter contracts pass; the exact
  four-shard inventory check and all-files pre-commit gate pass.
- The required final xdist work-stealing suite passes (`6361 passed` in `445.00s`), including the
  complete code-quality suite.
- The Attached Units source artifact, final engine build identity, and regenerated external
  contract pass fail-closed checks, including the `origin/main` compatibility comparison.
- Installed-wheel smoke passes with `2477` packaged engine resources and `27` schemas. The host has
  no `npm` executable, so `npm ci` and npm wrapper commands could not run; the already locked
  dependencies were exercised directly with the bundled Node runtime. Generated-client drift,
  TypeScript type checks, and all `5` client unit tests pass, and the two-server HTTP conformance
  scenario passes all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/412`; merge commit
pending review and merge.

### P05A — C05-01

Status: Implementation, source/contract updates, required local validation, and remote PR
publication are complete; review and merge are pending.

Finding IDs: `C05-01`.

Dependencies and evidence gate: P19 is merged. The exact 05.04.04 statement is retained as a
reviewed transcription and a separately classified, project-authoritative 40k.app mirror
observation linked to the recorded non-affiliation and source-authority policy. This satisfies
`APP-AUTHORITY`; no `EXCEPTION-PAUSE` applies.

Violated invariant: A model destroyed by an attack that has a destruction-triggered rule must
become logically dead and non-targetable at damage resolution, but its trigger resolution and
battlefield removal must wait until every attack made by the attacking rules unit has resolved.
Shooting and Fight must use one persisted, replay-safe boundary.

How it was done before P05A: Ordinary and grouped damage removed a destroyed model, emitted
`model_destroyed`, ran mandatory reactions, and requested optional reactions inline with the
current attack. An accepted or declined decision then resumed the remaining attack pool. A first
casualty's Deadly Demise or optional reaction could therefore occur before a later attack rolled or
applied damage. Destroyed Transport continuation inherited the same early timing. The sequence had
no explicit attacks-resolved evidence or serialized destruction queue for checkpoint validation.

How it is done after P05A: Damage still reserves the authoritative attack-destruction cause and
records logical death immediately. When the destroyed model has a registered destruction reaction,
or a destroyed Transport has embarked cargo requiring its destruction continuation, the engine
captures the exact attack context and pool, damage/FNP result, controller, reaction sources,
original damage event ID, and pre-removal placement in an ordered
`PendingAttackDestruction`. The fixed placement remains solely as pending-destruction evidence;
alive/group/selection/targeting queries continue to exclude the logically dead model. Damage then
advances through every remaining attack and gathered pool from the attacking rules unit. The
deferral event also commits the complete canonical attack-pool payload with SHA-256, including the
attacker model, full weapon profile, targeting state, and declaration provenance.

After deferred Devastating Wounds routing and all ordinary attacks have completed, a sequence with
deferred destructions emits one `attack_sequence_attacks_resolved` event carrying the stable
05.04.04 source ID and persists that event ID on `AttackSequence`. It drains pending destructions
in attack order:
destroyed-Transport cargo continuation, mandatory destruction reactions, placement validation,
battlefield removal and the canonical `model_destroyed` event, then any optional reaction request.
The original damage step is reused rather than emitted twice. Shooting and Fight already converge
on this resolver, so no adapter or phase-local timing path is introduced.

Checkpoint restore validates each pending record against one logical-death authority, original
damage event, deferral event, complete attack-pool commitment, captured sources and placement,
attacks-resolved event, and event ordering. Before the boundary, restore requires the boundary
event to be absent and requires the serialized queue's ordered damage-event/context pairs to equal
the complete deferral-event order. It accepts that retained queue only while ordinary attacks
remain or a typed Devastating Wounds continuation is still pending. Once all pre-boundary work is
complete, the attacks-resolved event is mandatory. After the boundary, the serialized queue must
be an exact suffix of deferral-event order because resolution can only remove index zero. A queued
record may remain while its post-removal optional decision is pending, but a pre-removal record
cannot be restored without its retained placement and unfinalized cause. Damage, deferral,
attack-pool, queue-order, boundary, removal, optional decision, and cause identities reject
missing, duplicate, forged, or reordered evidence.

Specific authoritative 40k.app rule/statement and source ID: 05.04.04, `DESTROYED`, states that if
a destruction-triggered rule applies to a model destroyed as the result of an attack, unless
otherwise stated that rule is resolved and the model is removed only after the attacking unit's
attacks have resolved. Its stable source ID is `core_rules_05_04_04_destroyed`. Runtime behavior
binds to the typed source package constant and never a display name or source-text token.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/05-attack-sequence`, observed
`2026-09-01T14:18:39-04:00`; transcription
`0f3cb2ce7fb896aa9d2404eafdf6bde0d701e89ff895dc680a7ca6d56780e9f2`;
reviewed-transcription observation
`0f588f6a3973735c0afee2936b0c6e7950274a0b8606e986b7c254e251c5942e`;
authoritative-mirror observation
`ceb8fca60471aea370514c919ea7bf991f9a1d84b8c43f3fb560793fd0569bef`;
category-audit source observation
`c771b8acbb62f912cc21c649a6a1ec0cac5d5a1f02e5454747b9427a8571892e`.
The generated package hash is
`ec4bf56033c8c90db0a2870051a5ea472a42f7767ed48299bc0352a2b1092a5f` and its canonical artifact
byte SHA-256 is `161c67830d5976033e04f9ab64830e0ddc4ddca93e95e270945839b60d53bdd9`.
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:626e1cc6ae12885b263c667b6b18f0ad7b4fecc90cffdbd08c91a8238fe54777`.

Load and execution support: The Destroyed rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked mirror observation carries project
authority. The fail-fast typed loader pins schema, document identity, rule identity, text hash,
both evidence fingerprints, package hash, and canonical artifact byte hash.

Scope and explicit exclusions: P05A owns attack-caused destruction deferral, ordered persisted
queueing, the shared attacks-resolved boundary, destroyed-Transport entry into that boundary,
mandatory/optional destruction-reaction timing, restore integrity, source identity, adapter
documentation, regressions, and a static convergence audit. Models without an applicable
destruction-triggered continuation retain the existing immediate removal path. P05A does not alter
reaction eligibility or effects, Hazardous timing, mortal-wound allocation order, Emergency
Disembark hazard/placement order, or the Fight On Death remove/re-add behavior assigned to P05B.

Decision and viewer-visibility impact: P05A adds no decision type, option family, proposal kind, or
viewer-visibility rule. It changes the timing of existing `select_destruction_reaction` requests and
adds replay-safe sequence/event payload fields. Retained models are already excluded from living
projections and legal target sets. Existing shared adapter redaction remains authoritative.

Regression scenarios and same-bug-class search: The Order 9 regression uses real domain objects
and multiple attacks from one rules unit. Its first casualty owns mandatory Deadly Demise and an
optional Shoot on Death source; it proves the later attack's damage precedes the attacks-resolved
event, both reaction classes and removal follow that event, and the queue survives pre-boundary and
post-boundary JSON/full-lifecycle round trips. Two retained casualties prove that reversing the
queue fails both before and after the boundary while the legitimate remaining suffix restores.
Forged early or missing completed boundary evidence, damage-event binding, attacker-model
attribution, and full weapon-profile payloads fail restore.
Existing grouped damage,
Destroyed Transport, Deadly Demise secondary casualty, Fight On Death, optional reaction, and
invalid-submission suites exercise the shared changes. Static audit requires attack damage to use
the boundary owner, requires boundary ordering before completion, and requires Shooting and Fight
to consume the same attack resolver. No behavioral test file was added, removed, moved, or renamed,
so the committed four-shard inventory does not change.

Generated artifacts/documentation: P05A adds
`core_attack_sequence_2026_09/artifacts/package.json`, its typed loader/source package, and the
offline builder; regenerates the engine build manifest and external contract; and updates both
decision-contract documents and this finding record.

Validation results:

- The focused Shooting and attack-resolution convergence cluster passes all `184` tests. The
  focused Order 9 regression additionally covers pre-boundary restore, rejects reversed two-entry
  queues before and after the boundary, accepts the legitimate post-boundary suffix, and rejects
  forged or missing boundary evidence, damage-event drift, attacker substitution, and full
  weapon-profile substitution. The complete code-quality suite is included in the final full run.
- Repository-wide Ruff check and Ruff format check pass; mypy passes across `2653` source files;
  Pyright reports `0 errors, 0 warnings`; all `11` import-linter contracts pass; the exact
  four-shard inventory check and all-files pre-commit gate pass.
- The required final xdist work-stealing suite passes (`6366 passed` in `427.80s`), including the
  complete code-quality suite. The four CI-equivalent behavioral coverage shards also pass and
  their combined branch report satisfies the repository's `85%` threshold.
- The Attack Sequence source artifact, final engine build identity, and regenerated external
  contract pass fail-closed checks, including the `origin/main` compatibility comparison.
- Installed-wheel smoke passes with `2484` packaged engine resources and `27` schemas. The host has
  no `npm` executable, so npm wrapper commands could not run; the existing locked dependencies were
  exercised with the bundled Node runtime and `pnpm`. Generated-client drift, TypeScript type
  checks, and all `5` client unit tests pass, and the two-server HTTP conformance scenario passes
  all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/413`; merge commit
pending review and merge.

### P18C — C18-03

Status: Merged in PR #414 at `44a9b52e`.

Finding IDs: `C18-03`.

Dependencies and evidence gate: P05A and P06B are merged. The exact 18.05 statement is retained as
a reviewed transcription and a separately classified, project-authoritative 40k.app mirror
observation linked to the recorded non-affiliation and source-authority policy. This satisfies
`APP-AUTHORITY`; no `EXCEPTION-PAUSE` applies.

Violated invariant: Emergency Disembark says to make a Hazard Roll for each embarked model before
moving it. The authoritative damage/FNP path must therefore finish every hazard casualty while the
cargo is still embarked and unplaced, and the later placement proposal must contain only the exact
surviving models. Adapters, replay restore, and event authority must observe that same order.

How it was done before P18C: The destroyed-Transport continuation emitted a placement proposal for
the complete living cargo unit first. After accepting that placement, the resolver rolled each
model's Hazard Roll and applied the resulting mortal wounds to the now-placed unit. A model that
should have died before moving could therefore appear in the placement submission and battlefield
transition, and its casualty evidence was ordered after the placement request.

How it is done after P18C: When the P05A deferred destruction boundary reaches destroyed-Transport
cargo, the engine freezes the exact embarked model lineage and creates a typed, source-linked
`DestroyedTransportHazardRolls` snapshot before requesting any placement. The shared P06B mortal-
wound allocator applies failed-roll wounds and any finite model/FNP decisions against living,
unplaced cargo. A lethal result updates wounds and the removed-model authority without creating a
placed-model logical-death or `model_destroyed` event. Checkpoint restore reconstructs those
alive-unplaced to dead-unplaced mutations from the typed transport-hazard completion event.

Only after the hazard application completes does the attack continuation derive the exact living
survivor inventory. If no model survives, it records that the cargo unit was destroyed before
placement and advances without emitting a placement decision. Otherwise it emits the existing
`submit_placement_proposal` request with immutable `hazard_rolls` and
`surviving_model_instance_ids` context. Proposal prevalidation rejects any attempted placement
containing a hazard casualty before queue pop. Accepted placement consumes the precomputed rolls,
records pre-placement casualties separately from genuinely unplaceable survivors, and then
continues Battle-shock/no-charge state, Transport removal, and Deadly Demise in the existing order.

Post-review correctness hardening makes that snapshot canonical for attached passengers: one
hazard packet carries the attached rules-unit ID, the complete sorted physical-component IDs, and
one roll for every living model across those components. The packet is applied once through the
frozen canonical embarked lineage. One canonical placement proposal then carries all surviving
physical components in `attempted_rules_unit_placement`; grouped validation, battlefield
placement, cargo removal, `DisembarkedUnitState`, and terminal event evidence commit in one engine
operation, so no component-level checkpoint can expose a partially disembarked attached unit.
The pending cargo queue preserves the rules-unit-grouped order chosen by the engine; validation and
payload round trips reject duplicates without lexicographically separating attached components.
Hazard casualties are recorded at that completion boundary through primary
battlefield-departure and logical unit-destruction tracking, so a passenger killed before placement
is visible to mission evidence and scoring. Restore now requires the persisted survivor tuple to
equal both the typed completion-event result and authoritative living-model state, and requires the
queued canonical placement request to carry that same full survivor set and hazard packet.

Specific authoritative 40k.app rule/statement and source ID: 18.05, `EMERGENCY DISEMBARK MOVE`,
states under “Before moving” to make a Hazard Roll for each model in the unit. Its stable source ID
is `gw-11e-core-rules:transports:emergency-disembark-move`. Runtime behavior binds to the typed
source package constant and never a display name or source-text token.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/18-transports`, observed `2026-09-01T18:46:11-04:00`;
transcription `3d2ae5c7c61267b25d42f7139353d31528f5b4f7c66acbc63c64b596f3f8eb56`;
reviewed-transcription observation
`41830aeaa0b2d711ad77a31e60092acf543b4d31b24c6cd286e1818948237b63`;
authoritative-mirror observation
`645e8e96af35d4aefe38c755c2ce6b72579d925865ace9e5b16e5b58158c5b98`;
category-audit source observation
`d9a06d3c5b350f66bad9e4b89f62242fd0f0b4c54579ea3ad6bbf2c2674b8d0e`.
The generated package hash is
`11ef8c6081238b8271effc171f9cd90cd85f1ec0028589db833b517bbe3fede0` and its canonical artifact
byte SHA-256 is `661543a9aa9084cf9d4c583940baab0a75382ef7e08efdb2a09f6e35678dc7d2`.
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:78023c3fa5ef5da68ccccd1437c9af93e07b9c94b3fd55c4e45a99b3dfd60d2b`.

Load and execution support: The Emergency Disembark Move rule and both evidence rows are `loaded`
and `executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked mirror observation carries project
authority. The fail-fast typed loader pins schema, document identity, rule identity, text hash,
both evidence fingerprints, package hash, and canonical artifact byte hash.

Scope and explicit exclusions: P18C owns the hazard-before-placement timing, embedded/unplaced
mortal-wound lineage, survivor-only request context and validation, replay/event authority,
source identity, adapter documentation, regression coverage, and static bug-class audit. It does
not implement P18B's maximum-placeable-set, closest-possible positioning, unengaged preference,
engaged fallback, or proof that an omitted survivor is genuinely unplaceable. It does not change
ordinary, Rapid, Tactical, or Combat Disembark timing, nor the generic P06B placed-model path. It
is deliberately limited to 18.05 Emergency Disembark and does not implement 18.06 Assault
Disembark, 18.07 Shock Disembark, or the 18.04.01 Rapid Disembark ingress restrictions. P18C
therefore remains correctly scoped, but neither PR #414 nor closure of C18-03 establishes complete
category 18 compliance.

Owning abstraction and architecture: `attack_sequence_destroyed_transport.py` owns the persisted
destruction continuation and request timing; `emergency_disembark.py` owns the typed pre-placement
hazard service; `destroyed_transport_pending.py` owns exact pending restore binding;
`mortal_wound_target_lineage.py` owns the frozen embarked lineage policy; and the shared mortal-
wound, fight-history, primary-history, and mission-boundary authority modules reconstruct the
unplaced casualty transition and its scoring provenance.
`destroyed_transport_rules_unit_disembark.py` owns the canonical grouped placement result and its
typed event evidence. The public transport API remains stable while the new implementation is
extracted from the frozen oversized `transports.py`; the new engine modules remain below the
1,500-line budget, and the
legacy transport module does not exceed its historical ceiling.

Decision and viewer-visibility impact: P18C adds no decision type, option family, proposal kind,
or viewer-visibility rule. The existing public `submit_placement_proposal` request gains additive
engine-authored survivor/hazard context. Its typed hazard packet now also carries additive
`component_unit_instance_ids` identifying the complete canonical attached snapshot. Any P06B
model-allocation or Feel No Pain choice resolves
through its existing finite decision registrations before placement. Existing shared adapter
redaction remains authoritative.

Regression scenarios and same-bug-class search: The Order 10 end-to-end regression wounds the
last passenger model, injects a failed Emergency Disembark Hazard Roll for that model, resolves
the shared mortal-wound allocation before placement, and proves the subsequent request contains
only the other four survivors. It proves the casualty is dead, removed, never placed, and never
emitted as a placed `model_destroyed`, and that hazard completion precedes placement request,
`unit_disembarked`, Deadly Demise, and Transport removal. Full lifecycle JSON restore preserves the
result. Proposal prevalidation separately rejects a casualty ID with
`destroyed_transport_non_survivor_placement`. Existing direct transport payload/drift tests cover
typed roll/disembark round trips and context mismatch. The bug-class search covers direct and
grouped attack destruction, deferred destruction restore, every destroyed-Transport request and
retry site, shared P06B allocation/FNP, event authority reconstruction, and the normal placed-model
hazard path. A static audit enforces roll/application calls before placement request, survivor
context and validation, absence of new placement-time dice, the embedded lineage policy, replay
event authority, stable source identity, and module-size boundaries. No behavioral test file was
added, removed, moved, or renamed, so the four-shard inventory does not change.

Review regressions additionally cover one attached passenger snapshot across multiple physical
components, one canonical grouped survivor placement with no intermediate component state, an
immediate lifecycle round trip after that placement, zero-survivor primary destruction/scoring
evidence, and rejection of a forged restore that deletes a living survivor from both pending state
and its queued request. Final review regressions authenticate both pre-embark attached-component
loss directions: a retained Bodyguard after Leader loss and a retained Leader after Bodyguard loss
each preserve the immutable canonical lineage while the hazard packet contains only the living,
embarked component, complete one canonical placement, and restore through the full lifecycle. A
separate partial-hazard regression destroys the last living Bodyguard model, proves shared
destruction cleanup removes that physical component from live cargo, and then completes the
surviving Leader's grouped placement from frozen hazard/completion authority.

Generated artifacts/documentation: P18C adds
`core_transports_2026_09/artifacts/package.json`, its typed loader/source package, and the offline
builder; regenerates the engine build manifest and external contract; and updates README, both
decision-contract documents, and this finding record.

Validation results:

- The final P18C-focused transport, Shooting, and closeout cluster passes (`13` tests), and the
  complete code-quality suite passes (`346` tests). Fresh branch-inclusive behavioral coverage
  passes (`6036 passed`) at the repository's `85.00%` threshold.
- Repository-wide Ruff check and Ruff format check pass; mypy passes across `2658` source files;
  Pyright reports `0 errors, 0 warnings`; all `11` import-linter contracts pass; the exact
  four-shard inventory check and all-files pre-commit gate pass.
- The required final xdist work-stealing suite passes (`6382 passed` in `444.55s`), including the
  complete code-quality suite.
- The Core Transports source artifact, final engine build identity, and regenerated external
  contract pass fail-closed checks, including the `origin/main` compatibility comparison.
- Installed-wheel smoke passes with `2490` packaged engine resources and `27` schemas. This host
  has no `npm` executable, so `npm ci` and npm wrapper commands could not run; the existing locked
  dependencies were exercised with the bundled Node runtime and `pnpm`. Generated-client drift,
  TypeScript type checks, and all `5` client unit tests pass, and the two-server HTTP conformance
  scenario passes all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/414`;
`44a9b52e44f26f9357c36363a32129b3bd4212bc`.

### S-MIRRORS — source-governance gate

Status: Merged in PR #416 at `6b115220`.

Finding IDs: None. `S-MIRRORS` is a source-governance prerequisite and does not close a gameplay
finding.

Dependencies and evidence gate: P18C/PR #414 is merged on `main` at `44a9b52e`. The repository-
owner direction already recorded in this roadmap names 40k.app and Game Datamissions as maintained
direct App-data mirrors. The retained provider review records the historical 40k.app observation,
Game Datamissions App-data versions 931 and 946, both provider identities and URLs, and the
non-affiliation boundary. No co-versioned rule observation from both providers is retained in this
governance PR, so no source disagreement or `EXCEPTION-PAUSE` applies.

Violated invariant: Project-authoritative source evidence must carry a complete immutable evidence
tuple and fail closed on disagreement. The shared source-evidence boundary must not authorize only
one provider when repository policy recognizes two maintained direct App-data mirrors.

How it was done before S-MIRRORS: `docs/CORE_RULES_SOURCE_POLICY.md` and
`RuleEvidenceRecord._validate_evidence_authority(...)` named and accepted only 40k.app. Mirror
records required a 40k.app observation timestamp and canonical 40k.app URL, rejected App-data
version metadata, and could not represent Game Datamissions. `SourceEvidenceCatalog` checked
unique evidence IDs but did not compare same-rule, same-App-data-version observations across
providers. The repository had no two-provider governance audit or generated review.

How it is done after S-MIRRORS: Current policy ID
`core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02` explicitly recognizes
40k.app and Game Datamissions while preserving both as non-affiliated third-party providers. Shared
validation allowlists each provider with its canonical HTTPS surface and requires the provider,
URL, App-data version or offset-bearing observation timestamp, transcription SHA-256, immutable
observation SHA-256, linked audit tuple, policy ID, and non-affiliation marker. The complete audit
tuple is authenticated against a hash-pinned packaged registry; invented audit IDs or rows and
mismatched row fingerprints fail record construction. Historical 40k.app records keep their
superseded policy ID only when evidence ID, stable rule source ID, and observation hash match the
registry's exact immutable legacy inventory. Every `RuleSourcePackage` carries the typed
`warhammer_40000_11th_core_rules` scope and must match one of nine registered Core Rules package
identities and its complete registered stable source-ID inventory exactly, so neither omitted Core
Rules rows nor added faction content can reuse this policy.
`SourceEvidenceCatalog` groups project-authoritative mirror records by stable rule source ID and
App-data version and rejects differing transcription hashes before a source package can load or
certify semantics.

Specific authoritative maintained direct App-data mirror statement and source ID: S-MIRRORS does
not introduce or change a gameplay source row, stable gameplay source ID, or operative rule text.
Its authority is the owner decision recorded in this roadmap and policy artifact. The provider
surfaces are `https://www.40k.app/rules` and
`https://game-datamissions.com/11th/rules/changelog`. Exact rule-specific statements remain an
obligation of each owning implementation PR.

Provider, URL, App-data version or observation timestamp, transcription SHA-256, and source-
observation fingerprint: Retained governance observation
`40k-app-core-rules-observed-2026-08-25` uses 40k.app,
`https://www.40k.app/rules`, timestamp `2026-08-25T00:00:00-04:00`, transcription
`c392a03e240536e5fe5ca489c777b596047cd9c0bb9023ff902392dd30c360de`, and observation
`ae80bd86900f54bc80f2ab711b80a3dc8b1ba70d1e8764a9a831bb63cc2742a5`. Retained observations
`game-datamissions-core-rules-data-931` and `game-datamissions-core-rules-data-946` use Game
Datamissions and `https://game-datamissions.com/11th/rules/changelog`; their App-data versions are
`931` and `946`, transcriptions are respectively
`99d400c59b8879a6c0bc6b9324435c677f22af27e0610810fb8fae0d21770d81` and
`d5b30faddcf23204073ca566ccb53a0a355ec893382413c542e74738f27296ab`, and observation fingerprints
are respectively `1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668` and
`d56418ca2a27645d032519c4fe11c97ae5520c50d0cb5b54201e97534a2d3279`. Both were reviewed at
`2026-09-02T12:30:09-04:00`. These provider-level statements establish governance only and are not
substitutes for future rule-specific operative transcriptions. The audit artifact byte SHA-256 is
`9fe12e806c461d930de62f7b781392b30eb67bbefff831e616a06e10997f50c2`; the generated report byte
SHA-256 is `79204b29bf28d74b2fc05b24bc9a4454f0d97b179b250c7444db492d92413238`. The packaged source-
authority registry byte SHA-256 is
`edf13cf6091cd64450a5dd627eb727d626dc631f1b7b7dd6d55eec0c6a2b5c79`. The regenerated engine
build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:668358d15be7fce321182af0f3d5e2001d76f9fb657b552dca7ae19e6f5e457a`.

Scope and explicit exclusions: S-MIRRORS changes source governance, shared evidence validation,
offline review artifacts, tests, and documentation only. It does not change gameplay semantics,
load or certify any v931/v946 operative rule, query a live provider at runtime, modify decisions or
adapters, add faction content, or expand any scope prohibited by `AGENTS.md`.

Owning state/validation/mutation/event/replay path: Repository-owner policy -> checked-in provider
review artifact -> offline typed audit loader/generator -> pinned packaged source-authority
registry -> `RuleEvidenceRecord` audit-row and legacy-observation authentication ->
`SourceEvidenceCatalog` co-version comparison -> `RuleSourcePackage` typed scope, package identity,
stable source-ID, catalog, and execution-evidence validation. There is no authoritative game-state
mutation, domain event, decision, adapter payload, or replay effect.

Decision and viewer-visibility impact: None. S-MIRRORS adds no decision type, option family,
proposal kind, adapter-visible payload, hidden-information classification, or redaction path.

Regression scenarios and same-bug-class search: Tests accept a complete Game Datamissions record
using App-data version in place of timestamp; reject a tuple missing both; reject a Game
Datamissions record using the superseded 40k.app-only policy; reject a non-canonical provider URL;
reject nonexistent audit IDs and row IDs; reject a registered row with a mismatched fingerprint;
reject a newly timestamped/evidence-identified record that reuses the superseded policy; reject a
faction source ID presented under the Core-only scope; reject a July package presenting only one
of its sixteen registered source IDs; accept matching co-versioned provider fingerprints; and
reject their transcription mismatch. Audit tests pin both provider identities,
non-affiliation, ownership and runtime-input flags, versions/timestamps, transcription hashes,
observation fingerprints, exact provider surfaces, registry/report output, and tamper rejection. A
static code-quality audit prevents regression to a provider-specific policy, unauthenticated audit
tuple, unscoped source package, or omission of mismatch rejection. No behavioral test file was
added, removed, moved, or renamed, so the four-shard inventory does not change.

Generated artifacts/documentation: S-MIRRORS adds
`data/source_audits/maintained_app_mirrors/core_rules_2026_09_02.audit.json`, its offline typed
validator/generator, `docs/CORE_RULES_MAINTAINED_MIRROR_REVIEW.md`, and the hash-pinned packaged
`source_authority_registry.json` with its typed fail-fast loader; replaces the active source policy;
documents the shared validation boundary in README and `ARCHITECTURE_V2.md`; preserves the older
40k.app audit as historical evidence; and updates this roadmap record. Engine-build and external-
contract artifacts are regenerated because shared packaged source validation changed; their final
identities are recorded after generation.

Validation results: Focused source-identity and code-quality coverage passes (`94 passed`). `ruff
check`, `ruff format --check`, `mypy`, and `pyright` pass; the complete xdist work-stealing suite
passes (`6394 passed`); and the completed behavioral coverage database
passes `coverage report --fail-under=85` at `85%`. The exact four-shard inventory check and all
`11` import-linter contracts pass. The historical 40k.app audit, maintained-mirror audit, all seven
Core Rules source generators, engine-build identity, base-ref external contract, and installed-wheel
smoke checks pass. The repository-pinned client generated-artifact check, TypeScript check, all `5`
client unit tests, and the two-server HTTP conformance scenario pass (`342` assertions for contract
version `11.1.0`). The all-files pre-commit hooks pass.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/416`;
`6b1152203b1976ea1b74cdcdc0970c67c8a17606`.

### P18D — C18-04

Status: Implemented in Order 12 and published in PR #417; local validation is complete, with
remote review, CI, and merge pending.

Finding IDs: `C18-04`.

Dependencies and evidence gate: P18C/PR #414 is merged on `main` at
`44a9b52e44f26f9357c36363a32129b3bd4212bc`, and S-MIRRORS/PR #416 is merged on `main` at
`6b1152203b1976ea1b74cdcdc0970c67c8a17606`. The exact 18.06 statement is retained as a reviewed
transcription and a separately classified, project-authoritative Game Datamissions v931 App-data
mirror observation authenticated against the S-MIRRORS provider audit. This satisfies
`APP-AUTHORITY`; no co-versioned contrary observation is retained, so no `EXCEPTION-PAUSE`
applies.

Violated invariant: Assault Disembark is a source-permitted Transport move with its own setup and
post-move state. A local ability exception or Rapid Disembark alias cannot authoritatively preserve
the permitting rule identity, require the exact eligible canonical rules unit, enforce wholly
within 3″, or make only that resulting unit eligible to declare a charge through decisions,
events, restore, replay, and adapters.

How it was done before P18D: A Transport that completed a Normal Move exposed only Rapid
Disembark. The resulting passenger state always prohibited a charge, no typed source-bound
permission could select a distinct move, and the Charge phase did not consume
`DisembarkedUnitState.can_declare_charge`. Placement proposal validation bound the mode and
Transport movement status but did not bind the submitted Transport ID or restriction overrides to
the pending engine-authored request, leaving the same forged-context gap for every standard
disembark proposal.

How it is done after P18D: A typed `assault_disembark_permission` persisting effect binds one
permitting source rule, owning player, battlefield Transport, and exact eligible canonical
rules-unit IDs. After that Transport completes a Normal Move, the shared movement owner derives a
source-carrying restriction override and emits the first-class `assault_disembark` candidate. The
existing engine-owned placement proposal path validates and atomically sets up every living model
in the canonical attached rules unit wholly within 3″ of the Transport. Existing Transport
authority rejects a passenger that is not embarked, is not friendly, embarked this phase, or is
otherwise absent or drifted; the Assault mode separately requires Normal Move status and its exact
permission override, so Advance, Fall Back, and ingress status fail closed.

The committed `DisembarkedUnitState` prohibits a further move and Remain Stationary, preserves
charge eligibility, records both the Core 18.06 source ID and the distinct permitting rule ID, and
round-trips those fields through game state, events, restore, and replay. The Charge-phase selector
now consumes the shared state: ordinary Rapid, Combat, and Emergency states remain ineligible,
while Assault Disembark remains eligible. Placement request context, lifecycle status, accepted
events, and proposal payloads carry the exact restriction override, and prevalidation rejects a
forged Transport ID or permission before queue pop or mutation.

Review hardening binds every retained disembark state to the `turn_player_id` that created it,
which is distinct from passenger ownership during opponent-turn destroyed-Transport timing.
Turn-end cleanup removes all records created in the completed turn, so an Emergency Disembark
owned by the inactive player cannot leak its no-charge restriction into that player's next turn.
Restore now requires exact correspondence among the retained state, one ordered
`unit_disembarked` event, the recorded placement request/result and their decision-history events,
the Transport movement status, and the complete restriction-override payload. An Assault charge
permission is accepted only when that authenticated override's source is exactly the stored
`permission_source_rule_id`; a rewritten Rapid state therefore fails closed. Move-completed
mortal-wound and Battle-shock hooks derive the triggering passenger owner from that authenticated
embedded state rather than conflating it with the event's active-turn identity.

Specific authoritative maintained direct App-data mirror statement and source ID: Game
Datamissions App-data v931 section 18.06, `ASSAULT DISEMBARK MOVE`, requires the unit to be set up
as in Set Up when a rule permits the move; the unit must be embarked in a battlefield Transport,
must not have embarked in it this phase, and the Transport must not have Advanced or Fallen Back;
every model is set up wholly within 3″ of that Transport. Its stable source ID is
`gw-11e-core-rules:transports:assault-disembark-move`. Runtime behavior gates on that source ID,
typed mode, and source-carrying permission effect, never on display names or source-text tokens.

Provider, URL, App-data version, transcription SHA-256, and source-observation fingerprint: Game
Datamissions, `https://game-datamissions.com/11th/rules/changelog`, App-data version `931`, reviewed
at `2026-09-02T12:30:09-04:00`; transcription
`93b5d311d7bce309e94f93c6b501a6980a820505786f59e0cb2bbfc6e53e4bee`; reviewed-transcription
observation `21dde0c665b4a09fecc0ddc6f4e09ee252b6a3b27af1779f858aa8a4fcfc0dae`;
authoritative-mirror observation
`afa51f8bbba769ecf4c34cf7acfa62c02addc247f11b42d830cc91bbded0066b`; authenticated provider-audit
observation `1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668`. The expanded Core
Transports package hash is
`b7c5f73b5e8299c5c6e29936b6fdf6d20d4a78148b83ac93b2be3e298b3d45b5`, and its canonical artifact
byte SHA-256 is `861a86d603ea1c9e676c2f9c505760b3130eb006a278f7e387fbffaedfe6e190`.
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:91bceab654863c3ec6bd5bbe67b0b4ba066a1e9b8fb679a4de7deb729a89700b`.

Load and execution support: The 18.06 rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked Game Datamissions observation carries
project authority. The fail-fast loader pins both Transport source documents, both rule rows,
their complete evidence inventory, runtime consumers, package hash, and artifact byte hash.

Scope and explicit exclusions: P18D owns the generic typed permission surface, first-class Assault
mode, source eligibility, Normal-Move-only lifecycle candidate, canonical 3″ grouped placement,
charge state, typed invalid outcomes, event/replay/adapter context, exact pending-request binding,
source package, documentation, regressions, and static bug-class audit. Content-specific rules that
grant this permission remain responsible for producing the typed effect from their own stable
source IDs through RuleIR or an approved runtime hook. P18D does not add a faction named handler,
implement Shock Disembark/P18E, implement Rapid Disembark ingress-restriction propagation/P20, or
change Emergency Disembark maximum-placement behavior/P18B. It adds no out-of-scope content.

Owning source/validation/mutation/event/replay path: reviewed generated Core Transports JSON and
fail-closed loader -> stable 18.06 source identity and executable consumer inventory -> typed
source-rule permission effect -> movement-owned candidate enumeration -> existing parameterized
placement `DecisionRequest`/`DecisionResult` -> request-context and proposal prevalidation ->
engine-owned grouped `resolve_disembark` validation and battlefield mutation -> typed
`DisembarkedUnitState` -> public event/status projection, restore/replay, and Charge eligibility.
Adapters echo engine-authored context and never grant permission or mutate placement independently.

Decision and viewer-visibility impact: P18D adds no decision type, option family, or visibility
classification. The existing public disembark finite option can name `assault_disembark`, and its
public `submit_placement_proposal` request/payload/status/event surfaces carry the additive exact
permission override and permitting source ID. Both viewers observe the same public movement and
charge state. Shared adapter redaction remains the sole projection/event owner.

Regression scenarios and same-bug-class search: A real lifecycle test records a source-backed
permission, moves the Transport normally, selects the eligible canonical passenger, submits the
engine-authored grouped placement, verifies the 3″ limit, state and event sources, serializes and
restores the lifecycle, and confirms deterministic replay. Direct resolver tests reject missing
permission, a passenger that embarked this phase, wrong movement status, and a model outside 3″.
An attached-unit regression places Bodyguard and Leader components atomically under one canonical
rules-unit identity. Charge coverage proves Rapid is excluded and Assault is retained. Adapter
coverage forges both the Transport ID and the permission override and proves typed rejection before
queue pop. Lifecycle regressions also prove opponent-owned Emergency state expires with the turn
that created it and that persisted state cannot drift from its exact event, request, decision
history, or restriction override. The bug-class search binds those fields for every standard
disembark proposal and every `unit_disembarked` emitter, and a static audit pins source identity,
generic permission ownership, grouped resolution, turn-keyed cleanup, authenticated restore,
lifecycle selection, charge consumption, adapter contract, and absence of display-name dispatch. No
behavioral test file was added, removed, moved, or renamed, so the four-shard inventory does not
change.

Generated artifacts/documentation: P18D expands the existing
`core_transports_2026_09/artifacts/package.json`, typed loader/source package, authority registry,
and offline builder for 18.06; adds the bounded disembark-state and generic Assault-permission
modules while shrinking the frozen legacy Transport facade; regenerates the engine build identity
and affected external-contract artifacts; and updates README,
`ARCHITECTURE_V2.md`, `docs/ADAPTER_DECISION_CONTRACT.md`, and this finding record.

Validation results: All required `AGENTS.md` gates pass: Ruff check, Ruff format check, mypy,
Pyright, the exact xdist work-stealing full suite (`6413 passed`), the four-shard inventory check,
all `11` import-linter contracts, and all-files pre-commit. The separate coverage-enabled
behavioral suite passes (`6065 passed`), and its completed coverage database passes
`coverage report --fail-under=85` at `85%`. The historical 40k.app and maintained-mirror audits,
all seven Core Rules source generators, final engine-build identity check, base-ref external
contract check, and installed-wheel smoke pass. The repository-pinned TypeScript client generated
artifact and type checks pass, all `5` client unit tests pass, and the two-server HTTP conformance
scenario passes all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/417`; merge commit
pending review and merge.

### P18E — C18-05

Status: Implemented in Order 13; local validation and publication details are recorded in the PR.

Finding IDs: `C18-05`.

Dependencies and evidence gate: P18D/PR #417 is merged on `main` at
`2fb55409b816ce80925f7edca10c219b23048d86`, and S-MIRRORS/PR #416 remains the controlling
source-governance gate. The exact 18.07 statement is retained as a reviewed transcription and a
separately classified, project-authoritative Game Datamissions v931 App-data mirror observation
authenticated against the S-MIRRORS provider audit. This satisfies `APP-AUTHORITY`; no
co-versioned contrary observation is retained, so no `EXCEPTION-PAUSE` applies.

Violated invariant: Shock Disembark is a distinct source-permitted Transport move. It cannot be an
Advance exception on Rapid Disembark because the engine must authenticate the enemy rules units
engaged with the Transport at move start, preserve every one of those engagements after 3″ grouped
setup, then give the opponent one canonical selected-to-fight activation for each affected unit
that has not already been selected in the current phase. Those identities and the temporary
cross-phase Fight control state must remain deterministic through decisions, events, adapters,
restore, and replay.

How it was done before P18E: an Advanced Transport exposed no Disembark candidate. There was no
Shock mode, typed source permission, start-engagement snapshot, grouped preservation check, or
source-tagged way to run an opponent Fight activation while Movement remained the active phase.
The ordinary Fight selection and selected-unit hook context assumed the global Fight phase, so a
local forced-selection event would have bypassed canonical validation and mutation.

How it is done after P18E: the shared typed Transport-disembark permission service now owns exact
effect payload validation for both Assault and Shock consumers. A `shock_disembark_permission`
effect binds one permitting source, owner, battlefield Transport, battle round, and exact eligible
canonical passenger IDs. When that Transport has Advanced, movement-owned candidate enumeration
emits only `shock_disembark`, captures the sorted canonical enemy rules-unit IDs physically engaged
with the Transport under the active handler's configured ruleset descriptor, and carries the exact
permission override and engagement snapshot into the public placement request. Candidate creation
and resolution use that same descriptor. The submission must echo both unchanged before queue pop.
The grouped resolver requires every living passenger model wholly within 3″, rejects engagement
with any enemy outside the snapshot, and proves every starting enemy engagement still exists after
the atomic placement. The committed `DisembarkedUnitState` records the Core 18.07 source,
permitting source, and engagement snapshot while prohibiting further movement, Remain Stationary,
and charging.

Each starting enemy not already selected to fight in the current phase enters one transient
`ForcedFightActivationContext` owned by the existing Fight state. It binds the triggering
`unit_disembarked` event, Core source ID, Movement source phase, passenger, Transport, opponent,
and eligible canonical enemy IDs. The ordinary `select_fight_activation` request is reused with no
pass option; the opponent chooses one unit at a time, and the normal selection validation,
selected-to-fight hooks, melee declaration/attack execution, `fight_activation_selected`, and
`unit_has_fought` paths run unchanged. The selected-unit hook context accepts a non-Fight source
phase only when the active state contains the matching typed forced context. Movement resumes only
after every still-eligible affected enemy resolves and the queue-completion event clears that
transient state. Restore reconstructs the exact outstanding rules-unit lineage set from the
authenticated disembark snapshot, prior and queue-local Fight selection decision/event chains, and
authoritative model-destruction history. A skipped or completed queue is accepted only when that
history proves no mandatory activation remains, and an active queue must retain the exact derived
eligibility context and exact authenticated selections. Each persisted forced selection is also
reconstructed through the same canonical Fight request/option builder used at runtime: the
historical forced context, typed ordered eligibility contexts, descriptor-legal Fight types,
finite option IDs and payloads, selected result, and complete
`fight_activation_selection_requested` event must all match exactly. Cross-linked forged copies
cannot turn a Normal activation into an Overrun activation during restore.

Specific authoritative maintained direct App-data mirror statement and source ID: Game
Datamissions App-data v931 section 18.07, `SHOCK DISEMBARK MOVE`, requires setup as in Set Up when
the permitting rule applies; the unit must be embarked in a battlefield Transport and must not
have embarked in it this phase; each model is set up wholly within 3″; every enemy unit engaged at
move start must remain engaged; and the opponent selects each such not-yet-selected unit one at a
time, making it eligible and selected to fight. Its stable source ID is
`gw-11e-core-rules:transports:shock-disembark-move`. Runtime behavior gates only on that source ID,
typed mode, permission effect, and canonical identities, never on display names or source text.

Provider, URL, App-data version, transcription SHA-256, and source-observation fingerprint: Game
Datamissions, `https://game-datamissions.com/11th/rules/changelog`, App-data version `931`, reviewed
at `2026-09-02T12:30:09-04:00`; transcription
`d8dae354aabcc30c582b66e70939dd67c010055637f86923292c0c76ffe7252c`;
reviewed-transcription observation
`3c866ae008d4085ac1c09d21b794221bb72eb18d62a9dd7415668733bfb722cc`;
authoritative-mirror observation
`cc8a85d4bcd88e7eb0ec3d9228721e5c1e4d1e4287b57d02a18ae3e8b3523efe`; authenticated
provider-audit observation
`1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668`. The expanded Core
Transports package hash is
`62c267ae792834ddd371541f177e78056492656db964cfdcaaa1a3de6581472f`, and its canonical artifact
byte SHA-256 is `a5d78f54c1507625a7911397f181e0f6466cb6f168d78febf0412628408287c5`.
The engine build ID after review hardening is
`warhammer40k-core-v2:runtime-tree-sha256-v1:77ff44b7023cd761f2f30db5b9f483a903487607dc5262ce1175d481602dd1fc`.

Load and execution support: the 18.07 rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked Game Datamissions observation carries
project authority. The fail-fast loader pins all three Transport source documents, all three rule
rows, their complete evidence inventory and runtime consumers, package hash, and artifact byte
hash.

Scope and explicit exclusions: P18E owns the shared exact permission extraction, first-class Shock
mode, Advance-only candidate, source eligibility, canonical 3″ grouped placement, start-engagement
authentication/preservation, transient opponent Fight activation queue, decision/event/adapter and
restore/replay integrity, source package, documentation, regressions, and static bug-class audit.
Content rules that grant Shock permission must still produce the typed effect through RuleIR or an
approved runtime hook. P18E adds no faction named handler, does not implement Rapid Disembark
ingress-restriction propagation/P20, Ongoing Consolidation/P12, or Emergency maximum-placement
behavior/P18B, and exposes no out-of-scope content.

Owning source/validation/mutation/event/replay path: reviewed generated Core Transports JSON and
fail-closed loader -> stable 18.07 identity -> typed source permission -> movement-owned candidate
and start-engagement snapshot -> parameterized placement decision/prevalidation -> grouped
Transport validation and atomic battlefield mutation -> typed disembarked state -> transient
source-tagged canonical Fight selection/activation -> public status/events/projection -> strict
restore/replay authentication. Engine state remains the sole mutation owner.

Decision and viewer-visibility impact: P18E adds one public disembark mode and two additive public
fields to existing request/event families: `start_engaged_enemy_unit_instance_ids` and
`forced_activation_context`. It adds no decision type or proposal kind. The placement submission
echoes the pending snapshot; the forced queue uses the existing public `select_fight_activation`
decision. Both players receive the same request and event payloads under the current public
battlefield-information scope through shared adapter redaction. Adapters cannot infer eligibility,
alter ordering, pass, or mutate Fight state.

Regression scenarios and same-bug-class search: focused tests cover missing permission, wrong
snapshot, configured-descriptor engagement calculation, broken preserved engagement, 3″ grouped
setup, no-charge/no-further-move state, canonical attached enemy identity, malformed omission
before queue pop, deterministic option selection, opponent ownership, no pass, canonical
selected-to-fight hooks, queue completion, both-viewer request/event projection, active and
completed restore, forged queue skip, forged empty completion, reduced active eligibility, forged
completion selection summary, malformed selection/context/request authority, missing selection
decision authority, decision/event authority drift, event-source drift, a cross-linked
Normal-to-Overrun payload forgery retaining the Normal option ID, a fully rewritten but
rules-illegal Overrun option ID/payload forgery, a later-activation forgery that removes
`currently_engaged` from every persisted eligibility/selection copy before rewriting the active
selection to Overrun, and payload round-trip. The same-bug-class audit
binds the new mode/snapshot through every standard candidate, proposal, selection, state, event,
and lifecycle restore path, factors duplicated Assault/ Shock permission parsing into one
fail-closed service, pins use of the configured descriptor, and pins runtime/restore reuse of the
canonical Fight request and selection-request-event builders. Restore now reconstructs the exact
remaining candidate set, model poses, closest-enemy distance, and physical Engagement state at each
selection-request event from authenticated battlefield authority; persisted eligibility reasons
are compared with that reconstruction and are never used as its input. No behavioral test file was
added, removed, moved, or renamed, so the four-shard inventory does not change.

Generated artifacts/documentation: P18E expands the existing
`core_transports_2026_09/artifacts/package.json`, typed loader/source package, authority registry,
and offline builder for 18.07; adds bounded shared-permission and Shock modules; regenerates the
engine build identity and affected external-contract examples; and updates README,
`ARCHITECTURE_V2.md`, `docs/ADAPTER_DECISION_CONTRACT.md`, and this finding record.

Validation results: all required `AGENTS.md` gates pass: Ruff check, Ruff format check, mypy,
Pyright, the exact xdist/work-stealing full suite (`6420 passed`), the four-shard fail-closed check,
all 11 import-linter contracts, and the all-files pre-commit suite. The separate behavioral
coverage run passes `--cov-fail-under=85` with `6071 passed` at `85.000165%` across `195971`
statements and `77472` branches. All seven Core source-package generator checks, engine-build
identity verification,
base-ref external-contract verification, installed-wheel smoke, generated TypeScript contract
check, TypeScript typecheck, five TypeScript unit tests, and the 342-assertion external conformance
scenario also pass.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/418`; merge commit
pending review.

### P24F — C24-06

Status: Implemented in Order 14; local validation and publication details are recorded in the PR.

Finding IDs: `C24-06`.

Dependencies and evidence gate: P05A/PR #413 and S-MIRRORS/PR #416 are merged on `main`. The
corrected 24.08 text is retained as a reviewed transcription and a separately classified,
project-authoritative Game Datamissions v931 App-data mirror observation authenticated against
the S-MIRRORS provider audit. This satisfies `APP-DRIFT`; no co-versioned contrary observation is
retained, so no `EXCEPTION-PAUSE` applies.

Violated invariant: a rule owned by a bearer model must retain that model identity from the source
boundary through timing classification and runtime dispatch. Deadly Demise triggers each time a
model with the ability is destroyed. A unit-owned description and `after_unit_destroyed` timing
can suppress non-last-model triggers and conflates model destruction with the distinct event in
which the rules unit ceases to exist.

How it was done before P24F: the runtime destruction-reaction path already materialized one Deadly
Demise source per bearer model and consumed it before that model's removal, but the inline Core
Abilities row said `when this unit is destroyed` and indexed the handler under
`after_unit_destroyed`. The generic RuleIR catalog builder also mapped both `MODEL_DESTROYED` and
`UNIT_DESTROYED` clauses to that unit timing. Return-on-death runtime consumers depended on the
collapsed index even though their semantic classifier supported both trigger kinds.

How it is done after P24F: the reviewed Core Abilities JSON artifact is the source of the stable
Deadly Demise ability ID, handler ID, source ID, exact descriptors, and
`after_model_destroyed` timing. `TimingTriggerKind` now represents model destruction separately;
both the single-clause and compound-clause RuleIR catalog paths use one shared destruction-timing
mapper. The default Deadly Demise handler is bound only to the model event. Generic
return-on-death lookup deliberately reads both model- and unit-destruction indexes, preserving
valid semantics for either source shape without restoring the old conflation. Existing per-model
source materialization, `model_destroyed` events, mandatory trigger roll, collateral resolution,
and before-removal ordering remain the authoritative mutation path.

Specific authoritative maintained direct App-data mirror statement and source ID: Game
Datamissions App-data v931 changed section 24.08 to state that each model with the ability triggers
Deadly Demise when that model is destroyed, after any embarked units make their Emergency
Disembark moves. The stable source ID remains
`gw-11e-core-abilities:core:deadly-demise`; runtime behavior gates on typed ability, handler,
timing, and model-source identities, never on the display name or reparsed source text.

Provider, URL, App-data version, transcription SHA-256, and source-observation fingerprint: Game
Datamissions, `https://game-datamissions.com/11th/rules/changelog`, App-data version `931`, reviewed
at `2026-09-02T12:30:09-04:00`; transcription
`a5ca19362fe04090968372fe83f3398cfa1236d52d69a2a87ad6ca555f429ff4`;
reviewed-transcription observation
`18455fe967731b81b8ceacbe9e0121c3750b6bf648e4ec3a781113aaf5b12511`;
authoritative-mirror observation
`3b3c615e97dab76873c0ab7974cf593480baa4a028eb88a1312254d0c3a6252b`; authenticated
provider-audit observation
`1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668`. The Core Abilities package
hash is `805db3a2131ceef3e4a120dd1bfa2605dc9a1e4cc1508619e02ed9bc1ec72d4a`, and its canonical
artifact byte SHA-256 is
`bd3dda22e3b39c18fa50c76e3131563feaa887ea25807bf8c67cd6e895e6ff6f`. The engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:872a1bfe4a99032de422434aebc29e21ae0dcfa05cd206dec45e2c1f63eaea18`.

Load and execution support: the 24.08 rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked Game Datamissions observation carries
project authority. The fail-fast loader pins the source document, rule and runtime identity,
descriptors, timing, evidence inventory, runtime consumers, package hash, and artifact byte hash.

Scope and owning path: P24F owns the 24.08 source package, Core Abilities catalog correction,
distinct shared timing identity, the generic destruction-timing bug-class correction, deliberate
dual-index return-on-death lookup, documentation, and focused regressions. The path is reviewed
JSON and typed loader -> stable ability catalog record -> per-model destruction-reaction source ->
model destruction validation -> mandatory Deadly Demise resolution -> collateral damage -> model
removal and deterministic event/replay records. P24F adds no named handler, faction content,
decision type, proposal kind, mutation path, or out-of-scope content.

Decision and viewer-visibility impact: none. This correction changes an internal ability timing
token and source descriptor, not a player-facing choice or adapter payload family. Existing
DecisionRequest/DecisionResult routing and shared viewer redaction are unchanged, so
`docs/ADAPTER_DECISION_CONTRACT.md` already covers all affected surfaces and requires no update.

Regression scenarios and same-bug-class search: source tests pin the v931 wording, model trigger,
evidence tuple, package identity, runtime consumers, and text/timing/byte tamper rejection. Catalog
tests prove Deadly Demise rejects unit timing and accepts model timing, and prove generic
single-clause model destruction stays distinct from compound unit destruction. The behavior
regression destroys a bearer while another model in its unit remains alive and on the battlefield,
then proves the mandatory per-model Deadly Demise reaction resolves before removal. Existing
coverage continues to prove one registered source per bearer, successful collateral damage,
Emergency Disembark ordering, secondary casualties, chained explosions, state round-trip, and
replay-safe records. Return-on-death tests prove model-triggered records remain discoverable after
the split; unit-triggered catalog consumers remain indexed only as unit destruction. No behavioral
test file was added, removed, moved, or renamed, so the four-shard inventory does not change.

Generated artifacts/documentation: P24F adds
`core_abilities_2026_09/artifacts/package.json`, its typed loader/source package and offline builder;
updates the source-authority registry; regenerates the engine build identity and affected external
contract examples; and updates README and this finding record.

Validation results: all required `AGENTS.md` gates pass: Ruff check, Ruff format check, mypy,
Pyright, the exact xdist/work-stealing full suite (`6425 passed`), the four-shard fail-closed
check, all 11 import-linter contracts, and the all-files pre-commit suite. The separate behavioral
coverage run passes `6075` tests and the `--fail-under=85` gate across `196138` statements and
`77494` branches. All eight Core source-package generator checks, engine-build identity
verification, base-ref external-contract verification, and installed-wheel smoke pass with `2502`
packaged resources and `27` schemas. The repository-pinned TypeScript generated-client and
typechecks pass, all five client unit tests pass, and the two-server HTTP conformance scenario
passes all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/419`; merge commit
pending review and merge.

### P15F — C15-06

Status: Implemented in Order 15; local validation and publication details are recorded in the PR.

Finding IDs: `C15-06`.

Dependencies and evidence gate: P08B/PR #405 and S-MIRRORS/PR #416 are merged on `main`. The
Insane Bravery FAQ is retained as a reviewed transcription and separately classified,
project-authoritative Game Datamissions v931 App-data mirror observation authenticated against
the S-MIRRORS provider audit and authorized Core Stratagem source package. It is deliberately
excluded from the superseded 40k.app policy's exact 33-entry immutable legacy-observation
inventory. This satisfies `APP-DRIFT`; no co-versioned contrary observation is retained, so no
`EXCEPTION-PAUSE` applies.

Violated invariant: a controlling player cannot target its already Battle-shocked unit with a
Stratagem. This restriction must be applied by the shared Stratagem target validator both when an
optional window is exposed and again before queue pop, CP spend, use recording, or effect mutation.

How it was done before P15F: the Insane Bravery catalog row set
`allow_battle_shocked_targets=True`. The about-to-test query correctly retained an already
Battle-shocked unit when that unit still had to take a Command-phase Battle-shock test, but the
catalog override converted that test obligation into permission to target the unit. A pending
parameterized request could consequently spend CP and register the auto-pass effect even when the
unit was already Battle-shocked or became Battle-shocked before submission.

How it is done after P15F: the stable Insane Bravery catalog row consumes the reviewed FAQ source
ID and restriction descriptor and no longer opts out of the shared friendly Battle-shocked target
rule. The canonical about-to-test query remains unchanged. Command-phase request preflight now
requires at least one legal, affordable target, while the existing proposal validator and atomic
apply path repeat full target validation before mutation. The source-backed once-per-battle
restriction remains unchanged. Generic target validation also resolves Battle-shock through the
explicit rules-unit identity API, so an Attached Unit's synthetic and component identities cannot
disagree about the restriction.

Specific authoritative maintained direct App-data mirror statement and source ID: Game
Datamissions App-data v931 records the Insane Bravery FAQ answer that a unit's controlling player
cannot target an already Battle-shocked unit with Stratagems. The stable source ID is
`gw-11e-core-stratagems:core:insane-bravery`; runtime behavior gates on the typed catalog policy,
target-policy ID, handler ID, and rules-unit identity, never on display-name or source-text parsing.

Provider, URL, App-data version, transcription SHA-256, and source-observation fingerprint: Game
Datamissions, `https://game-datamissions.com/11th/rules/changelog`, App-data version `931`, reviewed
at `2026-09-02T12:30:09-04:00`; transcription
`caf8973ed7c25c2c99db11bc0e489e3d9803300012b40b4f29eb878df54b1a25`;
reviewed-transcription observation
`e95e71061c9703aa78e104616ae95beb6391454de0c442aa6cbb317c55cc6fad`;
authoritative-mirror observation
`11af8114a1e14df4c9e2d6f52425c29a46c17385791480dc364129b84fe77252`; authenticated
provider-audit observation
`1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668`. The Core Stratagem package
hash is `f373b194b005a56b5caa0f52f540e26ddee45655ac9e89e8f8e85d4d642616d7`, its canonical artifact
byte SHA-256 is `25a89aadcee9ec31939dd08fedcec76e2bd1983aea1b94472a17c4721d89f17c`, and the engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:316e9503a93552cd8560c0cadb24c088303e1bb822fb496fa9259dd80a5d7641`.

Load and execution support: the FAQ rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked Game Datamissions observation carries
project authority. The fail-fast loader pins both source documents, rule/runtime identity, FAQ
text, evidence inventory, provider/version/audit tuple, runtime consumers, package hash, and raw
artifact hash.

Scope and owning path: P15F owns the Insane Bravery FAQ source row, catalog restriction,
parameterized-request strict preflight, shared rules-unit target validation, documentation, and
focused regressions. The authoritative path is reviewed JSON and typed loader -> stable Core
Stratagem catalog record -> canonical Command start timing window -> parameterized target proposal
-> validation before queue pop -> CP spend/use record -> auto-pass effect -> Battle-shock result.
P15F adds no named handler, decision type, proposal kind, faction content, or out-of-scope content.

Decision and viewer-visibility impact: the existing `submit_stratagem_target_proposal` payload
family is unchanged. The adapter contract now explicitly records that Insane Bravery is offered
only with a legal non-Battle-shocked pending-test target and is revalidated before mutation.
Existing viewer-scoped projection, event redaction, deterministic option/request identity, and
DecisionRequest/DecisionResult routing remain unchanged.

Regression scenarios and same-bug-class search: behavior tests prove that an already
Battle-shocked pending-test unit does not produce the optional Insane Bravery window, that a unit
which becomes Battle-shocked after request emission is rejected before queue pop or CP/effect
mutation, and that legal use and the once-per-battle restriction still work. A shared regression
proves any Battle-shocked component suppresses every target alias of its Attached Unit. Source and
code-quality tests pin the exact FAQ/evidence tuple, package identities and hashes, executable
status, catalog policy, and document/rule/evidence tamper rejection. A static identity-set audit
also pins all 33 superseded-policy legacy evidence IDs and rejects any current-policy or Game
Datamissions addition to that immutable inventory. No behavioral test file was added, removed,
moved, or renamed, so the four-shard inventory does not change.

Generated artifacts/documentation: P15F extends
`core_stratagems_2026_08/artifacts/package.json` and its typed loader/offline builder, updates the
source-authority registry's package authorization while preserving its exact legacy inventory,
regenerates the engine build identity and affected external-contract examples, and updates README,
the adapter/decision submission contracts, and this finding record.

Validation results: all required `AGENTS.md` gates pass: Ruff check, Ruff format check, mypy,
Pyright, the exact xdist/work-stealing full suite (`6432 passed`), the four-shard fail-closed
check, all 11 import-linter contracts, and the all-files pre-commit suite. The separate behavioral
coverage run passes `6081` tests and the `--fail-under=85` gate at `85.01%` across `196196`
statements and `77506` branches. Applicable Core source-package generator checks, engine-build
identity verification, PR-base external-contract verification, and installed-wheel smoke pass
with `2502` packaged resources and `27` schemas. The repository-pinned TypeScript generated-client
and typechecks pass, all five client unit tests pass, and the two-server HTTP conformance scenario
passes all `342` assertions for contract version `11.1.0`. This Windows environment exposes Node
24.18.1 but no `npm` executable, so `npm ci` itself could not be run; the existing lockfile-matched
dependencies were used to execute the underlying checks directly.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/420`; merge commit
pending review and merge.

### P24G — C24-07

Status: Implemented in Order 16; local validation and publication details are recorded in the PR.

Finding IDs: `C24-07`.

Dependencies and evidence gate: P19/PR #412 and S-MIRRORS/PR #416 are merged on `main`. The
alternating-Scout FAQ is retained as a reviewed transcription and separately classified,
project-authoritative Game Datamissions v931 App-data mirror observation authenticated against
the S-MIRRORS provider audit and authorized Core Abilities source package. This satisfies
`APP-DRIFT`; no co-versioned contrary observation is retained, so no `EXCEPTION-PAUSE` applies.

Violated invariant: simultaneous pre-battle unit rules must resolve one unit at a time in player
alternation, beginning with the player who will take the first turn. Sequencing state must be
engine-owned, persistent, replay-safe, and shared by UI, headless, network, tests, and restore. A
generic once-per-window ordering followed by repeated first-unresolved lookup is not alternation.

How it was done before P24G: `resolve_prebattle_actions` reused the generic Phase 12A
`resolve_sequencing_order` conflict. After that one ordering decision, every lifecycle advance
scanned the resolved participant order from its beginning and returned the first player who still
had an available Scout action. That player therefore resolved every Scout unit before the other
player acted. The selected order lived in the decision/event ledger rather than a dedicated
player/unit-resolution cursor.

How it is done after P24G: the engine creates a typed `PreBattleAlternationCursor` from the
first-turn `GameState.turn_order`, aligns it to the next player with an unresolved pre-battle unit
rule, and persists it in `GameState`. Each accepted Scout Move, Dedicated Transport Scout Move,
Scout reserve setup, or completion action advances the cursor atomically with its
`PreBattleActionRecord`. The next lifecycle pass scans once from that position, skipping only
players with no unresolved action. `resolve_prebattle_actions` no longer emits a generic
sequencing request; redeploy conflicts retain their existing Phase 12A sequencing path. Restore
requires unique request/result ownership for every action, closes the set of terminal Scout
decisions against the action ledger, and validates completion records or the complete
selection -> proposal -> accepted transition chain. It then derives the cursor history from those
verified actions and current engine candidates instead of trusting the stored count and final
metadata while the lifecycle remains in `SETUP` / `RESOLVE_PREBATTLE_ACTIONS`. After that timing
window closes, restore validates the finalized cursor from the immutable verified action/decision
ledger and does not recompute eligibility from evolved battlefield, reserve, or transport state.
Pending-actor, semantic, ownership, and transition-order drift all fail closed.

Specific authoritative maintained direct App-data mirror statement and source ID: Game
Datamissions App-data v931 asks whether players with Scouts units alternate resolving Scout moves
and answers that players alternate resolving any pre-battle rules their army's units may have,
starting with the player who will take the first turn. The stable source ID is
`gw-11e-core-abilities:faq:alternating-scout-moves`; runtime gates on the typed cursor, setup-step,
turn-order, action-record, and decision identities, never on display-name or source-text parsing.

Provider, URL, App-data version, transcription SHA-256, and source-observation fingerprint: Game
Datamissions, `https://game-datamissions.com/11th/rules/changelog?v=931`, App-data version `931`,
reviewed at `2026-09-02T12:30:09-04:00`; transcription
`e2e4740b73d2ea159eecb42da7246c399dc157bef038a623f9ecd94d07ba1296`;
reviewed-transcription observation
`4df59af220872b1b09a3dcd36acef6b792b5e8c11245bd6ca2bea2f12433e9fe`;
authoritative-mirror observation
`cb6c3244b50cff6017b30f269dff2530f1a8c8a461627710cc149064034d1453`; authenticated
provider-audit observation
`1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668`. The extended Core
Abilities package hash is `37e11c8e58049b5a0804c131e84714dba9c4fd192cbaac63eab915b8ca638f0e`,
its canonical artifact byte SHA-256 is
`4a33e49c5d7c0c043a0f074ae3c89fce9dae688452da4e752593dc7a76a1ad12`, the source-authority
registry byte SHA-256 is `78b96059f2bb2aed28768e93b54d238ff4567b54a328c3cd7d2659dc2d964abd`,
and the engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:aec768dc93f5bc8e2716a7829b0f3c76dc3f5db5afab8ce395987593ded803b2`.

Load and execution support: the FAQ rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked Game Datamissions observation
carries project authority. The fail-fast loader pins both Core Abilities rules, descriptors,
timing, evidence inventory, runtime consumers, package hash, and artifact byte hash.

Scope and owning path: P24G owns the FAQ source row, typed alternation cursor, pre-battle timing
selection, action-ledger coupling, restore validation, adapter contract, and focused regressions.
The authoritative path is reviewed JSON and typed loader -> first-turn order -> persisted cursor ->
engine-enumerated `select_prebattle_action` -> optional parameterized proposal -> validation ->
engine mutation and `PreBattleActionRecord` -> cursor advance -> next engine-selected actor. P24G
adds no named handler, decision type, proposal kind, faction content, generic hook family, or
out-of-scope content.

Decision and viewer-visibility impact: the existing finite and parameterized decision families
are unchanged, but `prebattle_timing_state` and serialized `GameState` now carry the JSON-safe
cursor payload. The adapter contract and decision submission catalog explicitly prohibit clients
from reconstructing or advancing it. Pre-battle deployment and movement data remain public in the
current rules scope, so the shared projection/event redaction path does not gain a hidden type.

Regression scenarios and same-bug-class search: lifecycle coverage gives both players two Scout
units and proves the actor sequence starts with the first-turn player and alternates by unit without
`resolve_sequencing_order`; the same test round-trips a pending request, rejects a drifted cursor,
and replays both accepted actions from a checkpoint. A second regression proves that a player with
no unresolved rule is the only player skipped. The LocalGameSession smoke proves adapters receive
the same first-turn/next-player decisions. Source tests pin exact FAQ text, evidence, executable
status, consumer IDs, package identity, and fail-fast loader behavior. [GitHub review
5117317180](https://github.com/SobolGaming/Warhammer_40k_AI/pull/421#pullrequestreview-5117317180)
identified that the first restore validator allowed multiple action
records to reuse one decision and did not bind action semantics. Added restore regressions reject
the exact duplicated request/result exploit, result-only duplication, relabeling a Scout action as
completion, unit/source/transition-payload drift, and action order that disagrees with decision
order; positive restore coverage includes Scout Move, Scout reserve setup, and completion. The
same-bug-class search found that redeploy shares `PreBattleActionRecord` storage, so request/result
uniqueness is enforced by the shared state owner for both setup steps; semantic cursor
reconstruction remains scoped to `RESOLVE_PREBATTLE_ACTIONS`, while redeploy keeps its valid
generic sequencing subsystem. [GitHub re-review
5118357793](https://github.com/SobolGaming/Warhammer_40k_AI/pull/421#pullrequestreview-5118357793)
identified that the corrected validator still recomputed live Scout candidates after setup. The
new full-lifecycle regression makes a Scouts unit legitimately unavailable during pre-battle by
embarking it in a non-Dedicated Transport, completes setup without a completion record, disembarks
the unit through the real movement decision path so it becomes Scout-candidate-shaped in battle,
and proves that the later lifecycle payload restores exactly. Candidate recomputation is now
restricted to the live pre-battle timing window; the same-bug-class search found no other restore
validator coupling a persisted setup cursor to these live Scout candidate helpers. No behavioral
test file was added, removed, moved, or renamed, so the four-shard inventory does not change.

Generated artifacts/documentation: P24G extends
`core_abilities_2026_09/artifacts/package.json` and its typed loader/offline builder, updates the
source-authority registry, regenerates the engine build identity and affected external-contract
examples, and updates README, the adapter/decision submission contracts, and this finding record.

Validation results: all required `AGENTS.md` gates pass: Ruff check, Ruff format check, mypy,
Pyright, the exact xdist/work-stealing full suite (`6442 passed`), the four-shard fail-closed
check, all 11 import-linter contracts, and the all-files pre-commit suite. The separate behavioral
coverage run passes `6091` tests and the `--cov-fail-under=85` gate at `85.01%` across `196558`
statements and `77668` branches. The Core Abilities source generator, engine-build identity,
PR-base external-contract verification, and installed-wheel smoke pass with `2504` packaged
resources and `27` schemas. A clean Node 24.18 `npm ci`, the repository-pinned generated-client
check and TypeScript typecheck pass, all five client unit tests pass, and the two-server HTTP
conformance scenario passes all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/421`; merge commit
pending review and merge.

### P24D — C24-04

Status: Implemented in Order 17; required local validation and remote PR publication are complete;
review and merge are pending.

Finding IDs: `C24-04`.

Dependencies and evidence gate: P05A/PR #413 and P06B are merged on `main`. The exact 24.15
Hazardous statement is retained in the reviewed Core Abilities artifact with a separately
classified, project-authoritative Game Datamissions v931 App-data mirror observation authenticated
against the S-MIRRORS provider audit and authorized source package. The retained 40k.app category
24 observation independently locates the same rule. This satisfies `APP-AUTHORITY`; no
`EXCEPTION-PAUSE` applies.

Violated invariant: after a unit resolves all attacks in Shooting or Fight, the engine must make
one Hazard Roll for every physical Hazardous weapon selected in the Select Weapons step. Physical
weapon identity, profile identity, the simultaneous roll packet, failure-to-weapon mapping,
phase origin, and any paused mortal-wound continuation must remain deterministic, serializable,
source-linked, and engine-owned.

How it was done before P24D: the shared attack-sequence boundary filtered Hazardous pools, reduced
them to a sorted set of `weapon_profile_id` values, and requested exactly one D6. Multiple physical
weapons using the same profile therefore collapsed into one test. The reason string always said
"after shooting" even when the shared resolver was completing Fight attacks. Resolution and
mortal-wound events retained only deduplicated profile IDs, one roll, and no explicit phase or
physical weapon identity, so replay could not prove which selected weapons produced or failed the
rolls.

How it is done after P24D: every selected attack pool already carries its canonical physical
`weapon_instance_id`, selected `weapon_profile_id`, full typed profile, and `AttackSequence`
`source_phase`. At the existing post-attack boundary, the engine keeps Hazardous pools in their
deterministic declaration order, collapses repeated pools for one physical weapon that split
attacks across targets, rejects one physical weapon selecting multiple profiles, and makes one
simultaneous unmodified D6 expression whose quantity equals the unique physical weapon count. Each
die is positionally bound to one weapon instance. Values of 1 or 2 identify the failed physical
weapons; the shared Hazardous keyword policy determines mortal wounds per failed roll, and the
engine routes their aggregate through the existing progressive P06B
mortal-wound/model-allocation/Feel No Pain service. Nothing rolls or mutates in an adapter.

Both Hazardous events now preserve `source_phase`, ordered physical weapon IDs, aligned profile
IDs (including intentional repeated values), failed physical weapon IDs, complete roll state,
mortal wounds per failure, and the aggregate wound total. A paused P06B continuation stores the
same fields. Typed parsing verifies D6 shape, roll count, ordered failure mapping, and wound
arithmetic; continuation and lifecycle restore additionally close those values against the active
attack sequence and its Shooting/Fight origin. Pre-submission validation returns a typed invalid
status before queue pop or mutation if a pending Hazardous mortal-wound context drifts.

Specific authoritative maintained App-data mirror statement and source ID: 24.15 Hazardous states,
"Each time a unit is selected to shoot or selected to fight, after that unit has resolved all of
its attacks, make a number of hazard rolls (06.03) for that unit equal to the number of
[HAZARDOUS] weapons you selected in the Select Weapons step." The stable source ID is
`gw-11e-core-abilities:core:hazardous`; runtime events, ability-catalog identity, evidence, and
continuations use that source ID rather than a display name or locally normalized source text.

Provider, URL, App-data version, transcription SHA-256, and source-observation fingerprint: Game
Datamissions, `https://game-datamissions.com/11th/rules/changelog?v=931`, App-data version `931`,
reviewed at `2026-09-02T12:30:09-04:00`; transcription
`2ecefae469a748d8f5b337dcbbb4a1c3211bfa4c3555626fbbd05ee6fbde3832`;
reviewed-transcription observation
`a80ec4f83e554f7004a396a7363977db41f9ca0e3a8675df1c0163bab3967ffd`;
authoritative-mirror observation
`8292a0b2aaa7640ee6b82b2dca9e822aa2ce26d59759dfb72a276a9e63b77e1b`; authenticated
provider-audit observation
`1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668`.
The extended Core Abilities package hash is
`ceda170f6ff51083eb2976ea97ee4d9096095dc3276d25ff7335d1cacabb9bfb`, its canonical artifact
byte SHA-256 is `fbfb7dae154292d33963a9c81d5c14025aa6c44873b7ee7a60c1fce754909bf7`,
and the source-authority registry byte SHA-256 is
`19bd1891e5519473cb431f09b1a472f30ef30a3ed883f615e3817a4356985ece`.
The final PR #422 engine build ID after the ordered-decoder and polygon follow-ups is
`warhammer40k-core-v2:runtime-tree-sha256-v1:98875fd2bc5f327b840909de61fd3bbc625c92292ae2c518682d96b7c2763d39`.

Load and execution support: the Hazardous rule and both evidence rows are `loaded` and
`executable_engine_runtime`. The reviewed-transcription row remains
`unverified_transcription_only`/`unverified`; only the linked Game Datamissions observation carries
project authority. The fail-fast loader pins all three Core Abilities rules, descriptors, timing,
evidence inventory, runtime consumers, package hash, and artifact byte hash. The source-backed
ability row consumes the exact Hazardous source ID and descriptors.

Scope and owning path: P24D owns physical selected-weapon Hazardous accounting at the shared
attack-sequence completion boundary, simultaneous roll/failure mapping, Shooting/Fight provenance,
P06B continuation authority, source/catalog identity, adapter-visible event documentation, and
focused regressions. The authoritative path is reviewed JSON and typed loader -> selected typed
attack pools -> shared attack completion -> simultaneous engine dice -> failed physical weapon
mapping -> shared mortal-wound routing -> events/replay/adapter deltas. P24D adds no named handler,
player-facing decision type, option family, proposal kind, faction branch, or out-of-scope content.
The source-backed `after_unit_attacks_resolved` timing descriptor is a real 24.15 consumer marker;
it does not introduce an alternate lifecycle dispatch or mutation path.

Decision and viewer-visibility impact: no new choice is introduced. Existing
`select_mortal_wound_model` and `select_feel_no_pain` requests may pause the aggregate Hazardous
packet, now with stronger replay-safe source context. Hazardous rolls, selected weapon identities,
and phase origin are public battlefield information after weapon selection in the current rules
scope, so shared projection/event redaction does not gain a hidden type. Adapters must preserve
repeated profile IDs and must not deduplicate, reroll, map failures, or apply wounds locally.

Regression scenarios and same-bug-class search: the direct Order 17 regression gives one rules
unit three distinct physical Hazardous weapon IDs in non-lexicographic declaration order
(`zeta`, `mu`, `alpha`), parameterized over one shared profile and three distinct profiles. Both
profile cases repeat the second weapon pool to model split targeting and require exactly three
rolls, proving that shared profiles do not collapse separate weapons and split pools do not count
one weapon twice. Each profile case covers immediate Fight completion with `(1, 2, 6)` and pending
Shooting/Feel No Pain resolution with `(1, 6, 6)`. The mixed pass/fail results map positionally to
the original weapons, apply the expected aggregate mortal wounds, and preserve phase origin and
aligned physical/profile order in both Hazardous events. Exact source-context JSON round-trips and
full lifecycle checkpoint/restore/submission retain those identities. Existing end-to-end attack
coverage proves the roll occurs only after the unit's attacks resolve and covers Infantry,
Vehicle, Monster, and mixed-keyword wound values. The existing optional Feel No Pain regression
now checkpoint-restores the full pending lifecycle, resumes through `GameLifecycle.submit_decision`,
and rejects a tampered phase/source-authority payload. Source/catalog tests pin the exact 24.15
text, timing, evidence and runtime consumers. The same-bug-class search found destroyed-Transport
and other hazard services already issue one roll per physical model; only the attack-sequence
Hazardous path deduplicated profile identity. The follow-up codec search found that both physical
identity collections require ordered, duplicate-rejecting validation; the static audit protects
that choice as well as physical-weapon counting. These regression follow-ups add cases within an
existing behavioral test file; they do not change file membership in the eight-shard inventory.

Generated artifacts/documentation: P24D extends
`core_abilities_2026_09/artifacts/package.json` and its typed loader/offline builder, updates the
source-authority registry and source-backed core ability catalog, regenerates engine and external
contract identities, and updates README, both adapter/decision contract documents, and this
finding record.

Initial Order 17 validation (before the PR #422 follow-ups): the focused Hazardous regressions pass
`12` tests; the focused source-package and ability-catalog regressions pass `6` tests; and the P24D
static audit passes. The exact required
xdist/work-stealing full suite passes `6445` tests in `675.69s`. The unsharded behavioral coverage
run passes `6093` tests with `10` pre-existing resource warnings and reaches the
`--cov-fail-under=85` threshold at `85.00%` across `196662` statements and `77714` branches. Ruff
check and format pass; mypy reports no issues across `2670` source files; Pyright reports zero
errors or warnings; all `11` import-linter contracts are kept; and the four-shard inventory is
current. The Core Abilities package, engine build identity, and generated external contract are
current, including the external-contract base-ref check against `origin/main`. A clean installed
wheel validates `2504` packaged resources, `27` schemas, and all six request families. The
TypeScript generated-client check and typecheck pass, all `5` client tests pass, and the clean
two-reference-server conformance scenario passes all `342` assertions for contract version
`11.1.0`. This Windows environment exposes the bundled `node.exe` but no `npm` executable, so
`npm ci` could not be run; the equivalent generated, type, unit, and conformance commands were run
directly through the repository's existing locked `node_modules` tools. The all-files pre-commit
run passes both configured hooks.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/422`; merge
commit pending review and merge.

### P14 — C14-01, C14-02

Status: Implemented in Order 18; all required local validation and remote PR publication are
complete in PR #423. Review and merge are pending.

Finding IDs: `C14-01`, `C14-02`. Dependencies and evidence gate: S-MIRRORS and APP-AUTHORITY
are merged on `main`; the preceding Order 17 is merged in PR #422, commit `52673fa1`.
The two maintained App-data providers were inspected directly, with the v931 changelog selected
through its version navigation. The provider audit records that these are separate observations,
not a claimed co-version comparison. No conflicting co-version source was observed and no
EXCEPTION-PAUSE applies. Provider non-affiliation is explicit. The existing policy is
`core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`.

Violated invariant: every generic objective-range consumer must use the closest part of the
actual objective and retain canonical rules-unit/model ownership. An objective linked to terrain
must use its complete footprint, not the point marker's radius. Outside the 11th Edition Core
Rules, the v931 terminology alias must be applied at source ingestion before parsing, without
altering raw provenance or literal Core Rules marker mechanics.
Every Battle-shock ID accepted by a scenario-only OC context must be canonical in its army
inventory; component aliases and unknown IDs must fail validation rather than be ignored.

Before: Objective Control independently implemented point-marker and terrain calculations;
generic conditional rerolls and Primary historical witnesses always used point-marker disks.
A model occupying a long linked terrain objective could control it while being omitted from
reroll eligibility or the historical scoring evidence. `RuleSourceText` carried no objective
scope and left non-Core marker wording unchanged. Clause merging duplicated the parser's
literal marker-only conditional-reroll pattern.

After: `objective_geometry` returns deterministic per-model distances to a marker disk or the
union of the objective's actual polygons, including concave and separately placed footprint
pieces. Horizontal and vertical distances stay paired to the same model. The group query resolves
canonical `RulesUnitView.alive_models()`, retains attached component ownership, rejects identity
drift, and uses the battlefield's explicit presence query for absent models. Source-linked
geometry is resolved once through the same mission/ruleset authority used by Objective Control.
OC modifiers, Battle-shock, score aggregation, and the existing terrain vertical-occupancy policy
remain with their owners. The generic reroll and Primary position/destruction witness consumers
use the same geometry. Historical evidence measures its authenticated physical snapshot, including
an explicitly included destroyed model, rather than substituting current living-model membership.

Attached Unit Battle-shock is evaluated through `rules_unit_is_battle_shocked` using the
measurement's canonical rules-unit ID. Component ownership remains available for model modifiers
and contribution payloads. State-backed OC contexts reject a Battle-shock ID collection that
differs from GameState, including substituted component aliases; scenario-only contexts use
canonical rules-unit IDs derived from `scenario.armies`. Their constructor rejects component
aliases, unknown IDs and mixed valid/invalid inventories before OC resolution. The same physical-ID
defect was found in adapter current-OC display and now uses the shared authority there as well.
Mission-action eligibility/history already
used that helper. Geometry, mutation ownership and decision/visibility schemas are unchanged.
The Shadow of Chaos phase-start OC caller now evaluates its recorded Battle-shock IDs through
a read-only state copy, retaining generic runtime OC effects without mixing a historical ID
collection with live-state context fields. It does not mutate the authoritative GameState.

`RuleSourceText` now requires and serializes `objective_scope`: `core_rules`, `non_core_rules`,
or `historical_text`. Non-Core 11th Edition singular/plural marker references normalize before
tokens and RuleIR are built; Core text stays literal. Raw text, source IDs and evidence remain
unchanged. Explicit historical producers retain the legacy reference corpus. There is no
implicit/unclassified scope. Scope and normalized payload drift fail closed on restore. Parser
clause merging and effect parsing share the objective conditional-reroll expression. Historical
row conversion was extracted from both bridge modules, keeping the oversized bridge below its
frozen module budget and avoiding a second local normalization path.

Source authority: the exact reviewed statements are committed under the four stable IDs below
in `core_objectives_2026_09/artifacts/package.json`. Sections 14.01 and 14.01.01 require
"measure to and from the closest part of it." Section 14.01.01 specifies a disk "40 mm in diameter"
and a model range of 3 inches horizontally and 5 inches vertically. Section 14.02 requires terrain
objective range "while it is within that terrain area." The selected v931 FAQ states:
"If a rule refers to an 'objective marker', does this mean an 'objective'?"
"Yes (excluding rules in the Core Rules)'." The final apostrophe is retained from the observed
provider text, not silently edited. The historical official Core PDF remains recorded as
`gw-11e-core-rules`, SHA-256 `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`;
it is not presented as independent official corroboration of this newer App wording.

All four source IDs have prefix `gw-11e-core-objectives:`. The complete 40k.app URL is
`https://www.40k.app/rules/14-objectives`, observed at `2026-09-05T08:38:21-04:00` without a
published App version. The Game Datamissions version locator is
`https://game-datamissions.com/11th/rules/changelog?v=931`; the canonical evidence URL is
`https://game-datamissions.com/11th/rules/changelog`, App-data `931`, reviewed at the same timestamp.
The typed evidence selects version 931 rather than pretending the provider exposes a second
independent same-version observation.

| Source ID suffix | Provider | Transcription SHA-256 | Provider-audit observation SHA-256 |
| --- | --- | --- | --- |
| `terrain-objectives` | 40k.app | `99e2404a6648e40162a7703012d4283218ce5601c79b2afa5a49e7a259037d66` | `0d48eb98a9be49808743e1c2e75163093163ee177a1d8818836ddf0f854ac189` |
| `objectives-not-within-a-terrain-area` | 40k.app | `f2d880bb3b9df994d34faca73ea716f003f995eb751b291e404603ad9f0cdc0d` | `0c4c710383443babf10c595244156d0b374ddae5ae5c7ce0dc29c6e25184278a` |
| `terrain-objective-control-range` | 40k.app | `df777fe4fb14a8d482eccb72b78644872819b65b4fccaed4507a30ea157bf257` | `a35eeb99c8a34665eb1cd42d1e0a1a878e588e7610fd9ba446897985fe72d451` |
| `objective-marker-terminology-faq` | Game Datamissions | `7c16a67d7d2835bdfac943b3bebad62e415cac68b9028c5da64ce04a677b831e` | `d4679f1c484d3c3f38ba8fd9f1a557060563ef8cebfad807fd41c9e1fad961c4` |

Reviewed-transcription and authoritative-mirror observation fingerprints are separately recorded:

| Source ID suffix | Reviewed transcription observation | Authoritative mirror observation |
| --- | --- | --- |
| `terrain-objectives` | `1b93141c8d3b007520a844d0850bfd0364f663e2767582333571693424340909` | `7d06eccb9332134ebf951fe18b1c6ff7187451c2b8f459dea31f31dfb91cd2ea` |
| `objectives-not-within-a-terrain-area` | `273c421e3a9bb19a1e9f2e779fea14845dbe4bcd2032a268a765b2c5eb0a563b` | `5b7fbbc37099ea1ed50e06d9aae53955b0a7d191b79a0791e2ad293a7864118d` |
| `terrain-objective-control-range` | `e93fd9a04b1e574d85482cc2d02337502f48d495702663b4fab1deafb720161c` | `00170a92b84cb09e0ab863a90e0a0675ca8b8bf87e71a8d38f4119de0827bb0b` |
| `objective-marker-terminology-faq` | `35bec9596ad53cade4ce8aa48698dfeed7eff4729175a895539e5979dbc547eb` | `9edb6e6a0ceefba7a4e88a6079ff0deef8b41de0580ab1ab77618fb470f9f515` |

Package hash: `864a6a549fb3260004bee04146c0d2de885955adbbac534d380b61c4a235dfec`.
Artifact byte SHA-256: `184a3fe08b6da5ce85dc2bfd99c72d1d0bbd3b7b2a136d4f0c374d31de374be1`.
Provider-audit byte SHA-256: `562de20e2f8cc5229a162b87c808c75f9a61f857f67f3fdac99560be3fe30cb6`.
Source-authority registry byte SHA-256: `7ae2913a6ff6ccacd894b1e112e652d60a9b8e0aff8283730f75e7d8a871a2cf`.

Load and execution status are distinct fields: all four rules and their evidence are `loaded`
and `executable_engine_runtime`, with explicit geometry/OC or source-normalizer consumers. The
reviewed transcription remains `unverified_transcription_only`; only its authenticated maintained
mirror row receives project authority. The eager typed loader pins bytes, schema, source IDs,
transcriptions, execution inventory and provider evidence. No source-only placeholder is claimed
as gameplay support.

Scope and owning path: reviewed JSON/evidence -> typed source boundary or mission objective links
-> immutable objective geometry -> canonical model-group query -> engine OC, generic reroll, and
historical witness owners -> existing decisions/events/replay/viewer projections. The extraction
adds no mutation service, named handler, faction branch, speculative hook, or support for excluded
content. P12 separately owns Objective Consolidation consumption and movement/final-position
semantics; P13's broader terrain/visibility work and faction-specific aura policies are excluded.
The consumer search reviewed `models_controlling_objective_marker`,
`objective_marker_controls_model`, `from_objective_marker_to_model`, and polygon-distance calls.
Literal Core marker endpoint mechanics, low-level geometry primitives, Cult Ambush markers, and
P12 consolidation are separate policies. Chaos Daemons' corrupted-realspace marker aura is a
faction source-review follow-up, not certified by this Core finding. Existing source-backed
mission geometry selection still rejects unknown links and unsupported source combinations.

Decision and visibility impact: no new choice, finite option family, proposal kind, or payload
field is added. Existing `objective_marker_id`/`objective_marker_witnesses` fields identify the
mission objective, including terrain, as clarified in `ADAPTER_DECISION_CONTRACT.md`. Engine
geometry is read-only; canonical submissions and mutation remain unchanged. Historical public
mission evidence follows existing viewer-scoped projection/event redaction and delayed spectator
rules. The runtime fingerprint changes, preserving the existing incompatible-build restore gate.

Regression coverage: marker-edge versus center distance, terrain occupancy beyond marker radius,
concave notches and separated polygons, rectangular bases, exact upper/lower vertical boundaries,
attached component IDs, absent models, deterministic ordering, drifted identities, invalid shapes,
source-byte tampering, source/catalog JSON round-trip, explicit/invalid scopes, singular/plural
case/word boundaries, and normalized conditional-reroll compilation. Three real Event Companion
layouts require OC, generic reroll, destruction evidence and turn-start witnesses to agree at a
terrain vertex more than seven inches from the marker center. Existing facade-driven mission
certification exercises lifecycle submission, restore, replay and viewer evidence. The focused
static audit prevents local objective geometry from returning to these four consumers and
prevents runtime text substitution. All regression additions extend existing test files; the
eight-shard inventory has no membership change.

Attached/Battle-shocked regressions muster a real bodyguard and Leader, record a failed
Battle-shock result under only the synthetic attached ID, and require all six model contributions
to be Battle-shocked with zero effective OC and no controller. Marker and source-linked Event
Companion terrain objectives exercise both state-backed and scenario-only queries. Component
alias queries, missing/substituted/extra context IDs, deterministic OC payload round-trips, and
facade projections for both players are covered. A static audit prevents physical-ID membership
checks from returning to OC and adapter display.
Scenario-only constructor regressions reject each attached component alias, the complete
component tuple, an unknown ID, and canonical IDs mixed with either an alias or an unknown ID.
Existing marker/terrain regressions continue to accept canonical IDs with and without state.
The phase-start consumer regression distinguishes current Battle-shock from its recorded
snapshot, preserves an executed RuleIR OC modifier, and checks that live state is unchanged.

Generated artifacts and documentation: offline P14 source builder and JSON/audit, eager loader,
source-authority registry/pin, engine build manifest, external contract examples/manifest, README,
adapter contract and this finding. Explicit producer classifications preserve historical generated
content; generator checks must prove committed output remains current. No faction generated
content or support inventory is expanded.

Validation: the final complete behavioral suite passes `6145` tests in `468.15s`, with `9`
reported SQLite resource warnings, using the required Node PATH prefix, xdist work stealing and
coverage command. Branch-inclusive coverage is `85.01%`, above the required 85% threshold.
The behavioral suite was not repeated without coverage. The focused OC, scenario-only inventory,
historical checkpoint and static audit run passes 77 tests. All six new invalid-inventory cases
failed before the constructor guard and pass after it; existing canonical-ID and state-backed
alias queries remain covered. The final complete code-quality suite passes `365` tests in
`103.76s` with xdist work stealing and no coverage, including generated ability-support/semantic
audit checks on macOS.
Ruff check/format, mypy (`2677` source files), Pyright (zero errors/warnings), all 11 import
contracts, the exact eight-shard inventory check and all-files pre-commit pass. The P14 source
builder and runtime build check pass. Generated external contracts pass with `--base-ref
origin/main` at `52673fa184673ee59a8f30cad40c8dba4e027c79`. Installed-wheel smoke passes with
`2511` packaged resources, `27` schemas and all six request families. Node 24.18 with temporary
pinned npm 11.6.2 runs a clean `npm ci`, generated-client/type checks, all `5` TypeScript unit
tests, and the two-server conformance scenario (`342` assertions, contract `11.1.0`).
The final engine build ID is
`warhammer40k-core-v2:runtime-tree-sha256-v1:1913b07d46dc949d86269aa10574f004bd0234fa28e5550b07aa7f502acc4534`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/423`; merge
commit pending review and merge.

### Post-P18C v931/v946 findings

Status: This section was introduced as planning documentation in PR #414. The P18D and P18E
finding records above now implement C18-04 and C18-05 without expanding P18C's production,
contract, source-package, or generated-runtime scope. P18C remains scoped to C18-03 and category
18 remains incomplete until its remaining scheduled findings close.

Evidence and sequencing: Game Datamissions records 19 changed items in direct App-data version 931,
dated 2026-08-26. The duplicated 01.02.06 changed/errata entries are one semantic obligation, so
the canonical map above contains 18 distinct obligations. Version 946, dated 2026-09-02, adds the
separate 18.04.01 Rapid Disembark And Limitations row. The official August 26 Universal Rules
Updates v1.1 independently confirms that Assault and Shock Disembark are new Core Rules concepts.
S-MIRRORS closes after P18C as the explicit source-governance gate. P18D follows S-MIRRORS and
owns C18-04; P18E follows P18D and owns C18-05; P20 owns C18-06 together with C20-01. Its policy
artifact, evidence-tuple validation, co-version mismatch rejection, and retained two-provider
review evidence satisfy the acceptance criteria in the canonical sequence row.

The remaining v931 obligations are closure gates, not deferred audit suggestions. Seven new scoped
PRs own C24-07/P24G, C22-02/P22B, C01-02/P01B,
C01-03/P01C, C02-04/P02D, C05-04/P05D, and C04-02+C04-03/P04B. Existing future PRs are expanded
atomically: P14 adds C14-02; P12 adds C12-03; P04 widens only C04-01 as the generic target-lifecycle
and reselection service; P11A adds C11-03;
P05B replaces its living-only Fight On Death plan with full battlefield-presence authority; P06A
must retain any-part-to-any-part line-of-sight evidence; and P21A must prove the Take to the Skies
choice precedes an Advance or Charge roll. The repeated Splitting Units erratum reuses C01-02 and
does not inflate the finding or PR count.

The highest-priority remaining contradictions are explicit: Snap Shooting can currently be lowered
below an unmodified 6; the current
Fight On Death contract denies authority v931 preserves; Scout actions do not alternate by unit;
and model-specific keyword loss is not representable. None may be treated as `REVALIDATE`-only or
implicitly closed by an adjacent implementation.

C18-04 requires a first-class Assault Disembark move rather than a local ability exception. Its
implementation must own source eligibility, canonical attached rules-unit setup wholly within 3″,
the charge-eligibility state granted by the permitting rule, typed invalid outcomes, engine events,
payload restore/replay, adapter submissions/projections, and deterministic tests.

C18-05 is implemented by the P18E record above as a separate first-class Shock Disembark move. Its
source-bound Advance permission, canonical 3″ grouped setup, exact start-engagement preservation,
one-at-a-time opponent Fight activations, attached identities, events, restore/replay, adapter
visibility, invalid-submission handling, and determinism are all owned by that record.

C18-06 is scheduled with P20 because the missing behavior belongs at the common Transport-ingress
boundary: a unit using Rapid Disembark after its Transport ingresses must inherit every setup rule
and restriction applied to that Transport, including source-defined enemy-distance and deployment-
zone restrictions. Although 18.04.01 is newly numbered/exposed in App data version 946, the
operative Rapid Disembark limitation was already present in the retained official Core Rules PDF;
the numbering is newly exposed, not the gameplay obligation. The engine compliance gap is still
open.

Each owning implementation PR must first use the updated maintained-direct-App-data-mirror policy
and pin its exact provider, URL, App-data version or observation timestamp, transcription SHA-256,
and source-observation fingerprint. Matching 40k.app data is corroboration, not a prerequisite. A
same-version mismatch between mirrors is an `EXCEPTION-PAUSE` requiring official-App comparison.

PFINAL is an audit/certification PR rather than a gameplay-remediation PR. After
every implementation PR in the canonical sequence merges, prepare a fresh audit of all
25 categories before opening PFINAL. The audit must select one maintained
direct App-data snapshot, verify every exact operative source row and
fingerprint, revisit every implementation finding and `REVALIDATE` category,
and perform the final cross-category dependency/regression audit. It must
explicitly prove all 18 v931 obligations, C18-06 and the September 10 findings closed, including every new
finding and expanded acceptance gate above, and must compare co-versioned
40k.app and Game Datamissions observations when both are available. A mirror
disagreement fails closed pending official-App comparison. If the audit
discovers any gap, do not open or certify PFINAL: assign a canonical finding
ID, insert its scoped PR before PFINAL, merge all such PRs one at a time, and
repeat the complete audit from current `main`. PFINAL may open only with a clean
audit and must commit the final audit artifact, generated report, validation
results, snapshot identity, provider/version evidence, and the evidence
supporting `CAUDIT-01` closure.

## Definition of full Core Rules compliance

The project may claim only:

> CORE V2 Core Rules categories 01–25 compliant with the maintained Games
> Workshop App-data snapshot X, represented by owner-authoritative direct-data
> mirror observation(s) from provider(s) Z, observed on Y, with non-affiliated
> provider provenance preserved.

That claim requires:

- all 71 implementation remediation PRs, S-MIRRORS, and PFINAL merged, plus every
  additional remediation PR inserted by the PFINAL fail-closed audit;
- every governing operative statement, stable source ID, provider, URL,
  App-data version or observation timestamp, transcription SHA-256, and
  retained source-observation fingerprint pinned in the source/finding record;
- no unresolved `EXCEPTION-PAUSE`, source drift, internal App inconsistency, or
  partially executed/unsupported in-scope Core Rules semantic;
- all 25 categories re-audited against the selected maintained App snapshot, including
  `REVALIDATE` categories 07 and 13;
- every closed finding covered through engine, adapter, replay, determinism,
  and visibility layers where applicable;
- support reporting still distinguishes loaded source data from certified
  semantic execution;
- all required validation passing on final `main`; and
- PFINAL's committed cross-category dependency and regression audit finding no
  new gaps, explicitly closing every v931 obligation and C18-06, and closing
  `CAUDIT-01`.

The claim continues to exclude faction, faction-detachment, faction-datasheet,
and every other scope prohibited by `AGENTS.md`.

## Exception decisions to record only if encountered

There are no routine source confirmations during the current 73-step
one-PR-at-a-time sequence (71 implementation PRs, S-MIRRORS, and PFINAL).
Record a user decision only when implementation encounters one of these
concrete exceptions:

1. The actual official App visibly differs from a pinned direct App-data mirror
   statement.
2. The maintained mirror omits text required to decide the implementation.
3. Stable title plus complete operative text cannot resolve an internal App
   inconsistency.
4. A tournament/project version cutoff would select a different App state.
5. The repository owner withdraws or narrows the source-authority policy.
6. 40k.app and Game Datamissions disagree for the same App-data version.

The default `T-TRANSPORT` milestone is now P18A+P18C+P18D+P18E+P18F+P18G+P18H+P18B. P15D is
the source-first P00 successor and remains one source-only APP-INTERNAL-DRIFT
PR; the original P12 remains recorded immediately after P14, with its
source-resolution follow-up in P12B. The numbered
one-PR-at-a-time order is fixed except for fail-closed insertion of newly found
remediation PRs before PFINAL, or unless the user explicitly revises the
roadmap.


## P12 implementation evidence - Order 19

P12 consumes P14 objective geometry and P18E forced-Fight execution. Reviewed
12.07/12.08 and the v931 Ongoing Consolidation erratum are committed in
`core_fight_2026_09/artifacts/package.json`, with a hash-pinned loader and
`data/source_audits/maintained_app_mirrors/fight_2026_09_05.audit.json`.
Observation: 2026-09-05T18:32:47-04:00; 40k.app exposes no App version; the Game
Datamissions erratum is version 931. The official Core Rules PDF hash
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833` remains historical
evidence. The original review reported no co-versioned mirror conflict; the
September 10 review below reopens mode-specific certification as C12-04.
40k.app did not expose a version, so co-version equivalence cannot be asserted.
The July Objective
Consolidation source continues to support its narrower unengaged-endpoint fix,
while the new source owns complete P12 semantics. Check artifacts offline with
`uv run --no-sync python tools/build_core_fight_source.py --check`.

C12-01 uses closest model bases, marker disks, vertical gaps and complete terrain
footprints through the P14 owner. C12-02 shares per-model closer/required-endpoint
validation between standalone and attached units, with full path/terrain checks,
coherency, Ongoing base-contact/prior-engagement constraints, Engaging all-target
engagement and Objective final unengaged/in-range constraints. The closest selected
unit is determined before movement, including ties.

Mandatory-endpoint search takes immutable geometry and movement/coherency policy,
uses direct paths before lazy deterministic navigation, and returns only witnesses
accepted by ordinary validators. A bounded 512-entry cache cannot reuse results
when poses, bases, terrain, permissions, budgets or proposed peer positions change.
A rotation-conservative distance lower bound covers circular, oval and rectangular
bases and both full-distance and horizontal-only policies. It certifies obvious
impossibility in empty space without running navigation. Exhausting navigation is not a
certificate: `consolidation_reachability_unresolved` rejects that proposal and
permits retry or decline. This conservative diagnostic covers narrow or complex
routes where the bounded search cannot establish a legal alternative; it never
accepts a closer-only move on a speculative impossibility verdict.

C12-03 queues every physically engaged enemy rules unit with a placed living model
that has not been selected this Fight phase, for Ongoing and Engaging consolidation.
The opponent chooses existing Normal/Overrun options. The shared queue suspends and
resumes ordinary Fight step/order/continuations; forced selections and allocation
history survive. Restore authenticates movement, trigger, inventory, decisions and
completion. Shared public-event redaction removes internal continuation snapshots.
Forced actors are derived again from canonical ownership during restore. The
ordinary continuation is reconstructed from its preceding phase, decisions and
events, including exact movement completion and player progress, before comparing
either queue snapshot. Forced entitlement is distinct from the original engagement
snapshot, preserving Normal/Overrun choices and mandatory unengaged responses.
Historical request, option, event and status builders retain the owning Fight
round after time advances. Frozen Fight registries survive turn-scoped effect
expiration: consolidation uses the suspended ordinary registry, while a new
forced Fight step records its initial registry in a redacted internal event.
Facade regressions complete both consolidation modes in both source-player
directions, advance normally into Round 2, restore and replay exactly, and reject
altered historical round/context fields after the effects have expired.
Closed-loop Fight paths, including rotation away and back, are centrally rejected;
stationary repeated poses preserve their evidence in attached-unit resolutions.
Historical physical queries distinguish retained destroyed models from living
models, preserving Fight On Death geometry without granting living authority.

Focused regressions cover per-model endpoints, marker/terrain consumers, cache
reuse/invalidation, blocker detours, both modes and both players, attached movement,
retained destroyed models, checkpoints and replay. No new rule family, named
handler, player-facing decision type or unsupported catalog content is introduced.
The user authorized the expanded reachability and ordinary-Fight suspension scope.

The violated history invariant is that physical validation must start from an
authenticated state, including damage and later movement of the same model.
The already-selected-enemy regression also covers damage followed by a later
Consolidation move. Historical affected-model inventory now examines individual
events; the full transition chain is then validated from its authenticated anchor.
The bug-class search found that the other inventory owners already inspect one
event at a time, while sequence owners supply their initial authority. Static
coverage prevents restoring the unanchored suffix replay. Source-registry bytes
and their loader pin use LF on every platform, as required by `.gitattributes`.

Final validation after merging main and the cross-round review corrections: the
complete behavioral suite passes `6311` tests with `85.02%` coverage; the separate
code-quality suite passes `372` tests. Ruff lint/format, mypy (`2695` files),
Pyright (zero errors/warnings),
all `11` import contracts, the exact eight-shard inventory check, and all-files
pre-commit pass. No behavioral test file was added, removed, moved or renamed.

All ten Core Rules source builders, F00 governance generation, the historical
40k.app audit, maintained-mirror audit, engine-build identity check, and
external-contract `--base-ref origin/main` check pass at base
`f47762b3790b2e709b0f11d9f8fd7aa8b0a1033f`. Installed-wheel smoke
validates `2529` resources and `27` schemas. TypeScript dependency installation,
generated-client/type checks, all five client unit tests, and the two-server HTTP
conformance scenario pass (`342` assertions, contract `11.1.0`). Windows validation
uses the bundled Node runtime on PATH and a local integrity-verified npm package.

## P22 + P22B implementation evidence — Orders 20 and 21

Status: Implemented together at the owner's explicit request and published in
PR #427. All final local gates pass. Merge remains an owner action.

Finding IDs: `C22-01`, `C22-02`.

Dependencies and evidence gate: `P00`, `P08A`, `P19` and `S-MIRRORS` are merged.
The branch starts at `a44dc2fa` (Order 19, PR #426), equal to fetched `origin/main`.
`APP-AUTHORITY` applies. No source-policy exception or observed mirror divergence
was encountered. The requested combined PR preserves one open roadmap PR.

Violated invariant: A placed model is in range of its own Aura and duplicate
instances of the same Aura cannot accumulate on a target. A canonical PSYKER
rules unit cannot use the same Psychic-level ability twice in one phase,
including through different models or attached components.

How it is currently done: Before this change generic Aura resolution required
per-descriptor self-inclusion, persisted instances could remain independently
applicable, and the Stealth consumer used separate range/keyword logic. Psychic
level had no shared unit/ability/phase use authority. Existing optional
once-per-battle limits were physical-source limits and could not enforce 22.03.01.

How it should be done: Shared Aura targeting defaults to self-inclusion while
retaining allegiance, keywords, alive/placed geometry and explicit source
exclusions. Persisted source/clause/effect slots apply once across canonical and
component aliases without deleting physical evidence or suppressing distinct
Auras/sub-effects. Psychic use keys contain game, canonical rules-unit ID, stable
ability source ID, round, active player and phase. Level, physical instance,
catalog record, component and model are evidence rather than independent uses.

Specific authoritative maintained direct App-data mirror rule/statement and
source ID: Complete 22.01 Aura Abilities is retained as
`gw-11e-core-aura-psychic:aura-abilities`. It establishes own-range inclusion on the
battlefield and one application of the same Aura. Complete 22.03.01 is retained as
`gw-11e-core-aura-psychic:psychic-abilities-with-a-psychic-level`; it prohibits a
PSYKER unit from using the same Psychic ability more than once per phase.

Provider, URL, App-data version or observation timestamp, transcription SHA-256,
and source-observation fingerprint:

| Statement | Provider and retained URL | Version / observation | Transcription SHA-256 | Source-observation fingerprint |
|---|---|---|---|---|
| 22.01 | [40k.app](https://www.40k.app/rules/22-other-rules-and-abilities) | `2026-09-06T12:57:51Z` | `930015bed3490c7c24cf3e3952d925a17dd6144874dc9a56c2ab68d3fd452b60` | `c0a99fff77e5c50a9c81a359e878aba62ec8bf045dc53963982cec416487fe30` |
| 22.03.01 | [Game Datamissions](https://game-datamissions.com/11th/rules/changelog) | App data `931`, dated 2026-08-26; observed `2026-09-06T12:57:51Z` | `e94feeb3d390500884ff9ceba0c0717087303e578d182efa444a7ad1f41906c4` | `a79192183fa0e5ebb080a145d335c6b363e6a84bea650f9ce74f68215aa3a9d2` |
| 22.03.01 corroboration | [40k.app](https://www.40k.app/rules/22-other-rules-and-abilities) | `2026-09-06T12:57:51Z` | `e94feeb3d390500884ff9ceba0c0717087303e578d182efa444a7ad1f41906c4` | `b4b6e75ae6463e3d10a4a7e177b83560bc4ce804c6e31e174fb54a7c6ff81374` |

Both providers are explicitly recorded as non-affiliated under the maintained
direct App-data mirror policy. Matching Psychic text does not establish matching
App-data versions: 40k.app exposes no version for this observation. The retained
official PDF remains historical evidence, SHA-256
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

Scope and explicit exclusions: Category 22 shared Aura and Psychic-use semantics,
source artifacts, catalog activation eligibility, adapter/replay integrity and
tests. No new faction/catalog content, spell effects, named handlers, movement
paths, AI, architecture boundary, compatibility shim or out-of-scope content is
added. The restriction applies to supported structured Psychic-level RuleIR;
unsupported effect semantics remain unsupported. Named-handler budgets do not
change. Small extractions keep frozen modules within their existing caps and
remove `rule_execution.py` from the oversized allowlist.

Owning state/validation/mutation/event/replay path: Source-bound parsing produces
typed Aura scope and Psychic frequency conditions. `rule_aura_resolution` owns
physical Aura targeting; `aura_applications` owns shared non-stacking queries;
catalog Stealth and numeric persisted modifiers consume those shared surfaces.
`execute_rule_ir` validates Psychic use before effect mutation and appends one
`psychic_ability_used` event after successful execution. That event-backed ledger
retains the pre-mutation canonical lineage. Catalog enumeration and lifecycle
pre-submission validation consult the same authority. Restore verifies the
canonical key, authoritative RuleIR hash/provider, historical attached lineage,
component/model ownership and accepted decision ordering; deletion of a use event
cannot unlock a recorded activation. Replay uses ordinary decision submission.

Decision and viewer-visibility impact: Existing finite catalog activation
families and option IDs remain authoritative. A queued duplicate returns typed
invalid before queue pop, record creation or mutation and remains declinable.
Declines and invalid attempts consume nothing. Added Aura provenance and Psychic
use events are public battle ability evidence under the existing shared viewer
policy. JSON-safe round-trips and both player event streams are covered. The
adapter contract documents the payloads; its existing opaque event/option schemas
cover them without a new contract version.

Regression scenarios and same-bug-class search: Failing tests first demonstrated
missing Aura self-inclusion and duplicate Psychic use across attached components.
Additional regressions cover source exclusion, keyword/allegiance/model anchors,
persisted numeric consumption, overlapping attached aliases, distinct source and
effect slots, conflicting Aura semantics, duplicate levels/models/components,
independent abilities/units/phase occurrences, malformed context, pre-pop repeat
rejection, accepted/declined decisions, save/restore, replay, JSON safety, deleted
or altered history, and bodyguard/caster/full-unit loss. Repository searches traced
Aura targeting, persisted queries, Stealth, charged weapon-characteristic Auras,
enhancement grants, battle-shock rerolls and contextual-status consumers. Existing
weapon source-ID and boolean grant/reroll consumers already apply once. Physical
source-specific once-per-battle limits remain additional restrictions. Static
audits prohibit physical/display identity in the Psychic key and runtime parsing
in the new authority modules.

The test-only follow-up also drives one `LocalGameSession` naturally from
round-one Command through Movement, the opponent's turn and round-two Command.
The same unit uses the same Psychic ability in all three selected phase
occurrences through three physical sources. A persistence checkpoint restores
the earlier phase/round use records unchanged, preserves both viewers' event
history and reproduces the complete decision/event history exactly through
replay. This covers historical-time validation without changing engine behavior.

Generated artifacts/documentation: Versioned
`core_aura_psychic_2026_09/artifacts/package.json`, typed pinned loader, maintained
mirror audit, source-authority registry/pin, package classification, engine-build
manifest, generated external-contract examples/manifest, README, adapter contract
and this finding record. `tools/build_core_aura_psychic_source.py --check`
reproduces the source and audit offline. Behavioral tests extend existing files;
the eight-shard membership remains unchanged and is checked fail-closed.

Validation results: The complete behavioral suite passes once with coverage:
`6333 passed`, `85.03%`, `805.94s`, using xdist work stealing and the bundled
Node runtime on PATH. The final no-coverage code-quality suite passes with
`373 passed` in `309.51s`, also using xdist work stealing.
Ruff check and format check, mypy (`2705` source files), pyright (zero errors or
warnings), all `11` import-linter contracts, the exact eight-shard inventory check,
and all-files pre-commit pass. The final focused invariant subset passes
(`34 passed`); an earlier broader focused pass covered `281` tests.

The new source/audit builder, engine-build identity check and external-contract
`--base-ref origin/main` check pass at base
`a44dc2fa295012d9c5dd8e26eebf4e793efe8e22`. Installed-wheel smoke validates
`2540` engine resources and `27` schemas. TypeScript dependency installation,
generated-client/type checks, all `5` client unit tests and the two-server HTTP
conformance scenario pass (`342` assertions, contract `11.1.0`). Windows client
validation uses the bundled Node runtime and the local integrity-verified npm
package. The final scope/architecture audit and `git diff --check` pass.

Follow-up validation: all `16` Psychic-selected behavioral tests pass (`88.94s`),
as do `10` focused test-policy/RuleIR quality audits, Ruff check/format, full mypy
and pyright, all-files pre-commit and the exact eight-shard check. These are
additional focused results for the test-only historical-time scenario; the
runtime build identity remains unchanged from the aggregate gates above.

PR URL and merge commit:
[PR #427](https://github.com/SobolGaming/Warhammer_40k_AI/pull/427); not merged.

## P24C1 implementation evidence — Order 22

Status: Source-instance identity/schema implementation complete and published in
PR #428; all final local gates pass. This closes only `C24-03A` after review/merge.
`C24-03B` / P24C2 (Order 52), the parent `C24-03` family and category 24 remain open.

Finding IDs: `C24-03A`.

Dependencies and evidence gate: No implementation dependency is listed for
P24C1. P00 and S-MIRRORS supply the merged source-governance foundation.
The branch starts at `e9fec4d4a30a0b1461c7828de2a7da6d2fe5c615`, equal to
fetched `origin/main`; Orders 20/21 are merged in PR #427. No other roadmap PR
was open. `APP-AUTHORITY` applies; no official-App divergence was observed.

Violated invariant: Distinct physical/source occurrences of a core or weapon
ability must remain identifiable even when their family, number, keyword or
complete descriptor is equal. Storing those occurrences must neither stack their
effects nor silently choose one for the controlling player.

How it is currently done: Before this change profile validation rejected duplicate
non-Anti families, imports rejected repeated descriptors, core descriptors were
unique only by ability ID, and runtime grants merged keyword/descriptor sets.
Those paths could erase the source of a second grant before an instance decision
could be made.

How it should be done: Typed occurrence records bind carrier owner, stable source
ID, source-instance ID and source slot to a deterministic instance ID. The referenced
ability definition is separate from that identity. Native profile descriptors and
otherwise undescribed keywords each own an occurrence; an explicit grant snapshots
the native inventory and appends its own occurrence. Equal definition records may
be shared by several occurrences. Reapplying the same occurrence is idempotent;
conflicting source identity fails closed. Core descriptors retain distinct source
rows and component-scoped identity. Non-Core catalog definition uniqueness remains
unchanged.

Specific authoritative maintained direct App-data mirror rule/statement and
source ID: Complete **24.02 Duplicated Abilities**, including numbered core and
weapon examples, Scouts and keyword-bearing Anti duplicates, is retained as
`gw-11e-core-duplicated-abilities:duplicated-abilities`. Duplicate abilities do
not accumulate; the controlling player selects the instance, with weapon
selection in Select Weapons each time the unit attacks. The source package is
recorded as `loaded` / `partial_engine_runtime`, since selection belongs to P24C2.

Provider, URL, App-data version or observation timestamp, transcription SHA-256,
and source-observation fingerprint:

| Statement | Provider and retained URL | Version / observation | Transcription SHA-256 | Source-observation fingerprint |
|---|---|---|---|---|
| 24.02 | [40k.app](https://www.40k.app/rules/24-core-abilities) | `2026-09-06T14:49:36Z`; no App-data version asserted | `34244f9733c5d16731e52e23636b68afd931761b0077431bba2010275f980ab4` | `4a37e2adbecc617bc913a16d9548f68f895393887bdc9f6e33fcea33fa11da49` |

The provider is explicitly non-affiliated. The complete operative section was
observed through the search index; direct retrieval returned HTTP 403. No
co-version comparison is claimed. The retained official PDF remains historical
evidence, SHA-256
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

Scope and explicit exclusions: The shared identity/schema foundation, existing
source-erasing grant consumers, source evidence and adapter/persistence contract.
Existing faction wrappers migrate only their generic grant operation; no faction
rules, catalog content, named handlers or support claims are added. No new
player decision, Scouts choice, stacking algorithm, combat selection timing,
movement validation, AI or excluded content is included. P24C2 must implement
the controlling-player decision and certify execution; this PR does not claim
that duplicate abilities are fully playable. No architecture boundary changes
or compatibility shims are introduced. Named-handler budgets and classifications
remain unchanged.

Owning state/validation/mutation/event/replay path: `core.ability_sources` owns
occurrence identity and core source-row validation; `core.weapon_ability_sources`
owns native inventory, grants and source-preserving descriptor/carrier changes.
Catalog ingress retains repeated structured descriptors. `WeaponProfile` owns
its explicit occurrence payload and validates identity, coverage, owner and
provenance. `UnitInstance` exposes component-scoped core occurrences. Engine
grant owners call these shared pure transformations; enhancement mutation
continues through its existing engine owner and event. Gathered attacks keep
their contributing attack pools and rebind the synthetic carrier while retaining
original source evidence. Existing checkpoint/catalog/replay serialization carries
the records and restores them through the same typed validators.

Decision and viewer-visibility impact: Contract `11.2.0` adds optional, closed,
nonempty `weapon_profile.ability_sources` records. Absent records denote the
native definition inventory; explicitly empty, malformed, duplicated, stale or
unprovenanced records fail closed. No decision family, submission, finite option
or visibility rule changes. Existing shared viewer scoping applies to containing
catalogs/proposals/checkpoints. Boolean keyword presence stays non-stacking.
Unresolved repeated descriptor occurrences fail explicitly at attack consumers;
distinct existing Anti descriptor selections retain their current path. No
automatic maximum/first-instance choice is introduced.

Regression scenarios and same-bug-class search: Failing tests first exposed the
missing identity APIs. Regressions cover equal and different values, multiple
sources of one definition, native and granted keywords, repeated-source
idempotence, source conflicts, canonical JSON round-trips, payload drift and
missing fields, owner/provenance/coverage rejection, value changes, synthetic
carriers, core duplicates and catalog ingestion. A real `LocalGameSession`
submits an ordinary finite decision with duplicate core/weapon sources in its
catalog, then checks checkpoint restoration, component identity, both viewers'
projections/event streams and exact replay reproduction.

A further failing catalog regression identified repeated keyword-only source
entries (`Assault, Assault`) being erased by the bridge. Ingress now retains
those native slots while the profile's canonical keyword membership remains
unique. Numbered/conditional descriptors retain their own source occurrences.
The existing event-history RNG incorporates enriched profile payloads; one
deterministic non-reroll fixture expectation was refreshed from 6 to 5 while
retaining its original ineligible-reroll assertion.

Repository searches covered descriptor/keyword set merging, core grant
deduplication, `replace` calls changing profile abilities/keywords/identity,
RuleIR and persistent-effect grants, enhancement auras, tracked-target grants,
Epic Challenge and the existing faction wrappers. Shared source-preserving
helpers replace the instances of that bug class. Static audits bind grant
owners to the shared helper and prohibit display/value identity in instance IDs.

Generated artifacts/documentation: Versioned
`core_duplicated_abilities_2026_09/artifacts/package.json`, pinned typed loader,
maintained-mirror audit, source-authority registry/pin, package classification,
engine-build manifest, external-contract schema/examples/manifest and generated
TypeScript client; README, adapter contract and this evidence record.
`tools/build_core_duplicated_abilities_source.py --check` reproduces source and
audit offline. Behavioral test additions extend existing files, so the eight
shard inventories retain the same membership.

Validation results: The complete behavioral suite passes once with coverage:
`6348 passed`, `85.04%`, `752.82s`, with 64 xdist workers and work stealing.
The no-coverage code-quality suite passes with `375 passed` in `299.26s`, using
16 xdist workers and work stealing. The bundled Node runtime is on PATH. The final
focused boundary subset passes (`67 passed`).
Ruff check and format check, mypy (`2708` source files), pyright (zero errors or
warnings), all `11` import-linter contracts, all-files pre-commit and the exact
eight-shard inventory check pass.

The new source/audit builder, engine-build identity check and external-contract
`--base-ref origin/main` check pass at base
`e9fec4d4a30a0b1461c7828de2a7da6d2fe5c615`. Installed-wheel smoke verifies
`2544` engine resources and `27` schemas. TypeScript dependency installation,
generated-client/type checks, all `5` client unit tests and the two-server HTTP
conformance scenario pass (`342` assertions, contract `11.2.0`). Windows client
validation uses the bundled Node runtime and npm from the local Node environment.
The final architecture/scope audit and `git diff --check` pass.

PR URL and merge commit:
[PR #428](https://github.com/SobolGaming/Warhammer_40k_AI/pull/428); not merged.


## P01 implementation evidence — Order 23

Status: implemented and locally validated; PR ready for review.
This closes only `C01-01` after review/merge; category 01 and P01B/P01C remain open.

Finding IDs: `C01-01`.

Dependencies and evidence gate: P08B and its later shared Battle-shock authority
are merged; implementation starts from current `main` at `2d04a9f1` after Order
22. `APP-AUTHORITY` uses the maintained-mirror policy approved by S-MIRRORS.

Violated invariant: a living rules unit's mandatory Command Battle-shock test
must not depend on battlefield placement. Embarked and Strategic Reserve units
must test when currently Battle-shocked or at/below Half-strength, once per
canonical rules unit even when both predicates apply.

How it is currently done: P08B already snapshots all living candidates and uses
the corrected predicate, but its phase gate returns unsupported for an eligible
off-battlefield candidate. The collection helper also rejects it, while live
request materialization, pending reroll validation and historical request
validation require placed living models.

How it should be done: one shared living-model authority recognizes complete
battlefield, embarked and reserve membership. Command test materialization and
pending reroll validation consume its exact model IDs for strength and
Leadership. Historical validation selects the corresponding authenticated
physical rows at the request event. Existing sequencing, dice, outcome hooks,
Battle-shock state updates and continuation keep their ownership.

Specific authoritative maintained direct App-data mirror rule/statement and
source ID: 01.02.04 Not On The Battlefield, the unit-location definition and the
complete final Battle-shock paragraph. Stable source ID:
`gw-11e-core-off-battlefield-battle-shock:off-battlefield-battle-shock`.
The versioned source artifact certifies only these retained clauses as
`loaded` / `executable_engine_runtime`; it does not certify the remaining
visibility, measurement or general ability clauses of 01.02.04.

Provider, URL, App-data version or observation timestamp, transcription SHA-256,
and source-observation fingerprint:

- Provider: non-affiliated 40k.app;
  <https://www.40k.app/rules/01-core-concepts>.
- Observed: `2026-09-06T16:04:16Z` through the search-index page observation;
  direct retrieval returned HTTP 403. No App-data version is inferred.
- Retained clause transcription SHA-256:
  `cadc6f7705726995ad1a0c8329e0fe5763798c9f004e6e1d9086a6e8fbfa3a9b`.
- Audit-row source-observation fingerprint:
  `c139623d48440f0dd104f51333e4200bd14d5c8839713c2a932ca3e6f94ae31e`.
- RuleEvidence observation fingerprint:
  `ccf5632c66e344f27b90e72f89762f2f5dbec1c2994a8feedc7e4b7e0e92dabd`.
- The original official Core Rules PDF remains historical evidence with SHA-256
  `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

Scope and explicit exclusions: this change completes the Command Battle-shock
obligation. It adds no named handler, faction rule, player-choice family,
movement permission, visibility or measuring authority. General embarked-ability
semantics remain P01C. Setup deployment has a separate component/canonical-ID
mismatch in `deployment._unavailable_component_unit_ids` for directly reserved
attached units; that setup repair is outside this finding. Attached embarked
fixtures cover canonical identity including bodyguard loss, while reserve
fixtures and the existing authenticated during-battle reserve-entry regression
cover the Battle-shock consumer independently of that setup defect.

Owning state/validation/mutation/event/replay path:
`command_battle_shock_candidates` snapshots eligibility;
`command_battle_shock_phase_authority` validates remaining candidates and orders
them; `battle_shock_model_authority` resolves living model membership from the
engine's explicit cargo/reserve presence APIs; `battle_shock_test_service` and
`battle_shock_pending_authority` use that same model authority before rolling or
queue pop. `HistoricalBattleShockAuthorityContext` reconstructs historical
strength independently of geometry. The existing shared result service mutates
Battle-shock and records deterministic events consumed by adapters and replay.

Decision and viewer-visibility impact: existing finite sequencing and reroll
requests are reused. Public Battle-shock events and options stay public for
both viewers; no private mission or deployment content is added. The documented
unsupported scope becomes `battle_shock_model_presence` for unexplained or
conflicting model presence. Missing placements do not silently grant permission.

Regression scenarios and same-bug-class search: an existing regression first
failed with typed unsupported after real damage and an authenticated Gate of
Infinity reserve entry. It now resolves once, restores and re-enters without a
second test. Additional real-domain cases cover both off-battlefield locations,
healthy/damaged/already-shocked/destroyed candidates, dual-predicate deduplication,
attached Half-strength and bodyguard loss, singleton wounds, facade completion,
public event equivalence, mixed finite sequencing, replay, reroll acceptance and
decline, stale/malformed/incorrect-actor rejection and lost cargo/reserve
authority before queue pop. The whole Battle-shock family was searched for
placement-derived strength and request gating: the collector, phase preflight,
materializer, pending validator and historical validator are fixed together.
Geometry-dependent faction rules and non-Command forced tests retain their
existing boundaries. An AST audit prevents these consumers reverting to
placement-only Battle-shock authority.

Generated artifacts/documentation: added an offline P01 source builder, typed
hash-pinned loader, versioned JSON and immutable mirror audit; registered its
exact source scope and fingerprint. Updated this finding, README, the adapter
contract, engine build identity and external-contract examples. All eight
committed shards and their duration inventory were regenerated from the complete
successful behavioral JUnit profile, including the new integration test file.

Validation results: the complete behavioral suite passes once with coverage:
`6374 passed`, `85.04%`, `755.79s`, with 64 xdist workers and work stealing.
The bundled Node runtime is on PATH. That run emitted 10 ResourceWarnings for
unclosed SQLite connections. The final focused subset passes (`247 passed` in
`48.08s`). The full no-coverage code-quality suite passes (`377 passed` in
`366.31s`) with 64 xdist workers and work stealing, after correcting its
source-package inventory expectation from 14 to 15. Production code did not
change after the coverage run.

Ruff check and format check, mypy (`2712` source files), pyright (zero errors or
warnings), all `11` import-linter contracts, all-files pre-commit and the exact
eight-shard inventory check pass. The new source/audit builder, engine-build
identity check and external-contract `--base-ref origin/main` check pass at base
`2d04a9f167c2839ed2233fd0fa75aa55254a1155`. Installed-wheel smoke verifies
`2547` engine resources and `27` schemas. TypeScript dependency installation,
generated-client/type checks, all `5` client unit tests and the two-server HTTP
conformance scenario pass (`342` assertions, contract `11.2.0`). Windows client
validation uses bundled Node `24.19.0` and npm from the local Node environment;
regenerating the client corrected checkout line endings without a semantic diff.
The architecture/scope audit and `git diff --check` pass.

PR URL and merge commit:
[PR #429](https://github.com/SobolGaming/Warhammer_40k_AI/pull/429); not merged.

## P01B implementation evidence — Order 24

Status: implemented and all required local validation gates pass. This closes only
`C01-02` after review/merge. The changed and errata v931 rows are one obligation;
P01C and other category 01 findings remain separate.

Dependencies and approved scope: P19 and S-MIRRORS are merged at the reviewed
base `b8805911de434f9b53b4c209e896012998e0e95f`. The user approved the shared
ownership/history expansion documented in `docs/ORDER_24_SCOPE_PLAN.md`.

Violated invariant: an authorized split must partition the existing models
exactly once into two independent rules units, record the player's chosen
membership, and preserve physical identity and source provenance. Model-ID
prefixes formerly required the original physical owner, attached formations
were treated as the live inventory, and no generic decision represented this
partition. Renaming models or leaving both successors with the original
unpartitioned components would invalidate that authority.

Implemented ownership and execution path: the data-boundary compiler emits a
typed `split_unit` RuleIR effect for the real pre-battle Combat Squads wording.
`unit_split_permissions` validates the source, trigger and target;
`unit_split_decisions` emits a linear sequence of finite membership choices;
the lifecycle dispatch validates the complete request and candidate state
before queue pop. `unit_split_runtime` atomically installs both successors
and their Starting Strength records and emits `unit_split_applied`.
`UnitSplitRecord` archives the original components, formation and partition;
`SplitUnitOrigin` proves each fragment's physical ownership while retaining
the original model IDs. A model cannot be subdivided again. Feasible specified
strengths apply; otherwise the two counts differ by at most one, including
attached Leader/Support models.

Shared consumers distinguish original source identity, current rules-unit
identity and frozen battle membership. Placement, movement ownership,
destruction, Battle-shock and scoring history consume that authority. Original
attached component roles survive bodyguard loss within each successor.
Existing unit effects resolve through historical aliases, conditional Leader
effects stay with their source models, and unit resources retain one original
account rather than creating extra uses. Runtime lifecycle code remains
content-neutral; no named handler or import-boundary exception was added.

Source authority: the registered package `gw-11e-core-unit-splitting`, version
`maintained-app-mirrors-observed-2026-09-06`, retains only the reviewed 01.02.06
baseline and balancing clauses as loaded/executable. Core regulates a split;
it does not grant every unit permission. The supported permission window is
the start of Declare Battle Formations before placements, reserves or cargo
declarations. Other source/timing shapes fail explicitly. No arbitrary
mid-battle split permission or additional faction support is claimed.

Provider and retained evidence, observed `2026-09-06T17:29:03Z`:

- [40k.app category 01](https://www.40k.app/rules/01-core-concepts), search-index
  observation, direct retrieval HTTP 403, no inferred App-data version.
  Source ID `gw-11e-core-unit-splitting:unit-splitting`; transcription SHA-256
  `cfbc728ec6c5d07a9d6497db3f37754bb7b0c227d4194ee13a2e2f7cdf40793f`;
  audit-row fingerprint
  `5fb98bc5cfbaac54399e77eff6cb25006fdc2dcbb93ff3a605f4090ad540face`;
  RuleEvidence fingerprint
  `a16c905b92d71c18ce0b660b756614f404f2e47ab22fbd22be97be24d4ad8ecf`.
- [Game Datamissions v931 changelog](https://game-datamissions.com/11th/rules/changelog?v=931),
  complete embedded v931 change and erratum entries; the default rendered v946
  page alone is not the evidence. Source ID
  `gw-11e-core-unit-splitting:balanced-unit-splitting`; transcription SHA-256
  `0c9515272839227cdd4070b2e7fca961f2892388992adf9db80c6345f667edca`;
  audit-row fingerprint
  `19d99e87b14fd7f286ade01e8a70ee64759b5f685ac7dc27f0ec303fbfd7ddd8`;
  RuleEvidence fingerprint
  `435db305787a7eb1fa519346e1ba2ffaa38f2ad861bed5bee987dc495ee2f06b`.
- Package hash
  `741dba74d805647ae5317f91dc914d7e60779abe748af9496533fee81a8a413d`;
  byte-level artifact SHA-256
  `c8e2d5ff82146cf127ef890e32e9c946251c549c03efdc2398a7326627915ecc`.
  The existing official PDF remains historical evidence with SHA-256
  `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

Decision, adapters and replay: external contract 11.3.0 documents
`select_unit_split_membership` and optional closed `split_origin` payloads.
Finite submissions use the existing common engine path. Actor, option,
payload, source, membership and checkpoint drift are rejected before mutation.
The shared redaction module keeps choices, records, events and successor
membership owner-secret during declarations. Opponents see the original
inventory until reveal. Checkpoints authenticate original muster configuration,
decision transcript and the application event; session persistence replays the
same submissions. The TypeScript placement client uses published current
ownership and its optional proof instead of deriving unit IDs from model IDs.

Regression and bug-class evidence: real-domain tests cover ordinary and attached
facade setup, both viewers, deployment and battle entry, exact checkpoint and
persistence replay, independent successor damage, even/odd partitions,
10/11/12-model source-count fallback, duplicate/foreign/repeated membership,
once-only lineage, unsupported permission shapes, stale and malformed
submissions, source/event/checkpoint drift, retained effects/resources and
Leader effects confined to the correct successor. The shared ownership AST
audit prevents local model-prefix validation from bypassing the new authority.
The search also replaced duplicated live-group reconstruction in physical,
history and scoring consumers rather than patching only split construction.
PR review exposed two remaining consumers of the same ownership invariant:
enhancement activation/live queries still required the original physical bearer,
and generic modifier gates discarded effects found through predecessor aliases.
The shared enhancement resolver now preserves assignment provenance while
returning the live component that contains the original bearer model. Activation,
generic Aura/application, fight hooks and existing source-specific consumers use
that resolver. Historical effect target validation recognizes authenticated
source components. Typed effect applications retain the original effect and
matched predecessor targets separately from current membership, with once-per-
instance deduplication. Generic hit and characteristic consumers use those
applications. Regressions exercise Targetin Squigs and Slaughterthirst through
facade splitting, deployment, checkpoint restore and exact persistence replay;
the Aura also stops when the live bearer dies. Numerical regressions verify
whole-unit, Leader-model and multiple-alias behavior after restoration.
Gateway unto Damnation's existing Deadly Demise consumer also validates its
unchanged source record separately from current bearer ownership; its split,
checkpoint and exact replay regression preserves the original modifier.
Static audits reject local enhancement ownership reconstruction and historical-only
generic target gates. This completes source-bound behavior preservation within
the approved scope; it adds no new split timing or reserve valuation behavior.
Two older Stratagem fixtures inferred attachments from Starting Strength
source strings; they now muster real Leader attachments. That regression
exposed component IDs reaching canonical mortal-wound target freezing.
Explosives and Crushing Impact now resolve current rules-unit IDs before
damage application and continuation; frozen lineage remains strict.

Quality-gate corrections keep physical/attached ownership validation in the
existing `attachment_mustering_validation` owner and leave the mustering
module below its frozen size budget. Split application installs membership
and Starting Strength together through a validating `GameState` mutator.
The decision submission catalog includes the new finite family, and the
attachment/strength audit follows the extracted shared owners.

Scope boundary: reserve point allocation and transport capacity still require
their existing source-backed configuration. P01B does not invent prices or
capacities for split fragments; source points keyed only to the original unit
do not supply successor reserve valuation. The executable split window occurs
before reserve/cargo declarations. General embarked-ability behavior is P01C.

Generated artifacts: offline source/audit builder and typed hash-pinned loader,
source authority registry, semantic-support artifacts, engine build identity,
contract schemas/examples/manifest and generated TypeScript client. The complete
behavioral JUnit profile supplies the eight-shard inventory before publication.

Validation results: the final complete behavioral suite passes with coverage:
`6412 passed`, `85.06%`, `807.23s`, with 64 xdist workers and work stealing.
The bundled Node runtime is on PATH. The run emitted 10 ResourceWarnings for
unclosed SQLite connections. No production code changed after this run.
All eight shards and the duration inventory were regenerated from its complete
successful JUnit profile, and the exact eight-shard inventory check passes.

Ruff check and format check (`2816` files), mypy (`2728` source files), pyright
(zero errors or warnings), all `11` import-linter contracts and all-files
pre-commit pass. The source/audit builder and engine-build identity check pass;
the validated runtime-tree SHA-256 is
`88f06d14cc00bcb3dfda0eaf2184a44d604174f1e2898242a1ec942638079952`.
External-contract `--check --base-ref origin/main` passes at base
`b8805911de434f9b53b4c209e896012998e0e95f`. TypeScript generated-client/type
checks, all `5` client unit tests and two-server HTTP conformance pass
(`342` assertions, contract `11.3.0`). Installed-wheel smoke verifies
`2562` engine resources and `27` schemas against the same build identity.
Windows validation uses bundled Node `24.19.0` and a local npm executable.
The architecture/scope audit and `git diff --check` pass.

The complete no-coverage code-quality suite passes: `380 passed`, `312.86s`,
with 64 xdist workers and work stealing. Its earlier failures were corrected
without relaxing the mutation, module-size or decision-documentation gates.

PR URL and merge commit:
[PR #430](https://github.com/SobolGaming/Warhammer_40k_AI/pull/430); not merged.


## Order 25 — P01C: embarked abilities and spatial conditions

Status: implemented and locally validated; awaiting PR review/merge. This finding
closes only after review/merge; category 01 is not certified by this PR.

Finding IDs: `C01-03`.

Dependencies and evidence gate: P19 and S-MIRRORS are merged. The reviewed base
is `064982c1ece761111cc3687fafe10adb7c63dacc` (`origin/main`, Order 24 merged).
APP-AUTHORITY applies under the maintained-direct-App-data-mirrors policy.

Violated invariant: an embarked unit retains its abilities within their own
restrictions; lack of battlefield geometry must not globally deactivate the
source. Range and visibility to another unit must fail independently, while
the unit remains visible to and within range of its own abilities.

How it is currently done: generic source enumeration used placed/alive models
as a proxy for ability availability. This suppressed optional activations,
CP effects, weapon grants and other non-spatial rules. Aura evaluation either
returned no targets or demanded a source model's missing geometry. Historical
Battle-shock providers repeated placement-only source and proximity checks.

How it should be done: `ability_presence` resolves current component ownership
and living membership from explicit placement, cargo or unarrived reserve
records. `active_ability_model_ids_for_unit` supplies source enumeration.
One shared spatial relationship distinguishes self, battlefield, off-battlefield
and unavailable sources/targets. Typed battlefield, keyword, phase, leading,
target and frequency conditions still govern individual abilities. Missing
placement alone never authorizes an ability; contradictory or incomplete
cargo/battlefield membership fails closed.

Specific authoritative maintained direct App-data mirror rule/statement and
source ID: the complete v931 embarked-abilities FAQ, including the Azrael/Firing
Deck example, is `gw-11e-core-embarked-abilities:embarked-abilities`. The
01.02.04 ability, visibility and measurement clauses are
`gw-11e-core-embarked-abilities:off-battlefield-ability-conditions`. The latter
also covers Strategic Reserves and army-wide/non-spatial rules. Its final
Battle-shock obligation remains separately pinned by P01.

Provider, URL, App-data version or observation timestamp, transcription SHA-256,
and source-observation fingerprint:

- [Game Datamissions](https://game-datamissions.com/11th/rules/changelog), version `931`
  observed `2026-09-07T00:02:56Z`; source `gw-11e-core-embarked-abilities:embarked-abilities`.
  Transcription SHA-256 `4c186dc9730e3431986655c2d8a81be7dc788c44382e0f508ccd30ee0c9376e6`.
  Audit observation `570d6afeb3ba563bdb5cdda85018ad948694af7c7d869ec99bc5fe13aa6aadb0`.
  RuleEvidence observation `51b787a9204ce20ed0c7f0028be5f4171113f7f739eeafa8a02db44180ab5d5d`.

- [40k.app](https://www.40k.app/rules/01-core-concepts), no recorded App version,
  observed `2026-09-07T00:02:56Z`; source `gw-11e-core-embarked-abilities:off-battlefield-ability-conditions`.
  Transcription SHA-256 `d54813925aec1839fd755c822f9b9662b5e2f25c9e5d33e1dcc7eb51e10205bd`.
  Audit observation `fddababef28f6b2c98b06804e86f4827236c5c8e2502ea5d09f443d1a2d5fb7d`.
  RuleEvidence observation `8533bb05f31daf52df28e1a5e1435a99ff62b91352f92cccd0dd6a5529d8b131`.

The Game Datamissions observation used the rendered v931 changelog selection;
the default v946 entry is not substituted. The 40k.app observation is from its
search-index page; direct retrieval returned HTTP 403 and no App version is
inferred. These are recorded as non-affiliated providers under the approved
policy. No same-version comparison is claimed. Package hash
`81e006418aa305b53635b0f7a51a1b99922d380795506ad023e08efd894d8dbf`; byte SHA-256
`3102868123dc8f612999dffcc069fad97a1d0ed1bbf6f3e663e39cc97c4d05ff`.
The official historical PDF hash remains
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

Scope and explicit exclusions: this is shared Core ability availability and
spatial eligibility for existing consumers, including the reserve/self clauses
explicitly referenced by the FAQ. Movement, placement, attacks, coherency,
collision and reserve arrival retain their physical requirements. It adds no
faction content, named handler, speculative hook, decision family, or unsupported
rule-text shape. Firing Deck keeps the transport as the weapon's attacking owner;
active passenger/attached-Leader grants do not become transport grants.

Owning state/validation/mutation/event/replay path: `GameState` owns cargo,
reserves, placements, membership and wounds. The new read-only authority feeds
existing catalog runtime providers, generic Aura/selection services, CP and
restoration consumers. Existing engine services still apply effects and record
events. Historical Battle-shock reads authenticated event-bound physical rows
through the same pure presence/spatial policy. No live geometry is fabricated
for historical or off-battlefield units. Existing finite decisions re-enumerate
their options before accepting the result; queue, effects and replay stay on the
normal lifecycle path.

Decision and viewer-visibility impact: existing finite activation and target
families can expose eligible off-battlefield sources. Option payload shapes and
IDs retain the existing contract; public/owner-scoped projections and event
streams use shared redaction. The adapter contract documents this behavior and
the more accurate failed-heal diagnostic `source_unit_unavailable`. It introduces
no hidden-info field, wire schema or transport-only source enumeration.

Regression scenarios and same-bug-class search: initial CP and model/unit Aura
regressions failed against placed-only source enumeration. Tests cover explicit
battlefield restrictions, self/other range and visibility, non-spatial army
selection, attached/unattached activate/decline choices through LocalGameSession,
actor/payload/cargo/phase drift before queue pop, checkpoint restoration,
viewer-scoped event equality and deterministic replay, Firing Deck ownership,
reserve/cargo live-versus-historical proximity, missing/conflicting/incomplete
presence and dead sources. The audit searched placed-model source loops and
geometry lookups across generic catalog/runtime consumers. Source-only gates
now use the shared authority; explicit move, engagement, reserve-arrival and
physical-target checks remain physical. AST guards prevent source enumeration
and live/historical geometry policy from diverging again.

Review correction: Stratagem-cost eligibility now evaluates the existing typed
`source_model_on_battlefield` condition after resolving active source presence.
The shared eligibility owner covers automatic modifiers, optional-opportunity
enumeration and result-side revalidation. The initial 12-case regression matrix
reproduced four failures for restricted embarked/reserve sources, with the eight
unrestricted or battlefield-present cases already passing. Both runtime modes
are covered without adding a parser shape. A per-function AST audit requires the
condition helper in CP gain/cost eligibility and shared eligibility in all three
cost entry points. The existing adapter decision contract and payloads apply.
The same-class search found this condition at the command-point parser boundary;
phase-gain execution already enforces it, while the cost path was missing it.

The reserve regression uses a standalone rules unit: the existing attached-reserve
deployment accounting issue is outside P01C and is not presented as fixed here.

Generated artifacts/documentation: committed JSON source/audit, typed eager
hash-pinned loader, source authority registry/classification, engine build
identity, external-contract examples/manifest, eight-shard behavioral inventory,
README and adapter contract. The builder's `--check` reproduces both evidence
artifacts offline.

Validation results after the review correction: the complete behavioral suite
passes once with coverage: `6456 passed`, `85.07%`, `799.81s`, 64 xdist workers
with work stealing and the bundled Node runtime on PATH. It emitted 10
ResourceWarnings for unclosed SQLite connections. The subsequent complete
no-coverage code-quality suite passes: `383 passed`, `305.09s`, 64 workers with
work stealing. No production code changed after the behavioral run began.
The correction adds cases to an existing behavioral test file; the committed
eight-shard file inventory remains valid and the exact eight-shard check passes.

Ruff check, Ruff format check (`2822` files), mypy (`2733` source files), pyright
(zero errors or warnings), all 11 import-linter contracts and all-files
pre-commit pass. The source/audit builder and engine-build identity checks pass;
the validated runtime-tree SHA-256 is
`502c1db13e5010b375b5e7e7b7bb8396897e8cb6378cbf3b2197481f9363d852`.
External-contract `--check --base-ref origin/main` passes at the reviewed base.
TypeScript generated-client/type checks, all five client unit tests and the
two-server HTTP conformance scenario pass (`342` assertions, contract `11.3.0`).
Installed-wheel smoke verifies `2565` runtime resources and `27` schemas against
the same engine identity. The full quality suite includes the generated semantic
support artifact checks. Contract JSON differences are limited to engine identity
and dependent persistence/manifest hashes; no wire schema change is claimed.
The scope/architecture audit and `git diff --check` pass. The focused CP/embarked
regression run passes all 57 tests, including the new 12-case cost matrix and
the per-function condition audit.

PR URL and merge commit: [PR #431](https://github.com/SobolGaming/Warhammer_40k_AI/pull/431); not merged.


### P02A / P02B / P02C — Orders 26, 27 and 29

Status: Implemented and published for review; all local gates passed. The owner
explicitly requested these three orders as one PR. This combines their shared arithmetic
and terminal-boundary owner without changing the remaining roadmap sequence.

Finding IDs: `C02-01`, `C02-02`, `C02-03`.

Dependencies and evidence gate: branch base is current merged Order 25,
`55c06d4dad60c34a77b381d864db7e7d1c3f98a8` (PR #431). P00/S-MIRRORS source policy
permits the reviewed maintained direct App-data mirror. No exception-pause
condition was observed. Order 28 is independent of these numeric changes.

Violated invariant: cumulative modifiers must follow exact replacement,
multiplication, addition, division and subtraction order with one final upward
rounding step. Characteristic replacements of 0, dash and star are terminal.
Post-reroll dice, arithmetic, minimum-1 results and rule-specific limits must
remain distinct; Charge results cannot exceed 12. Detection and Lone Operative
ranges must end within 9–30 inches after all modifiers.

How it was done: arithmetic omitted division/subtraction, used timing/priority
to order signed additions and exposed a separate late Damage-halving shortcut.
Zero replacements could receive later additions. Advance/Charge put modifiers
inside the raw dice expression; Charge then rejected results outside natural
2D6 bounds. Modified dice, hit/wound/save results could fall below 1. Random
Damage incorrectly assigned a modified value to an immutable raw-roll record.
Detection allowed zero/unbounded range and Lone Operative had a separate path.

How it is done: `core.modifiers` shares exact Fraction arithmetic and canonical
operation ordering between characteristics and dice. Stable priority/ID ordering
breaks ties inside an operation step. Typed terminal value kinds survive
restoration, including Damage conversion; symbolic numeric consumption fails.
Division replaces the unused late-halving shortcut. `core.modified_dice`
records post-reroll faces, intrinsic source-expression offset, ordered modifier
IDs, unbounded arithmetic, minimum-1 value and rule-limited final value.
Advance/Charge use raw D6/2D6 and consume the bounded result for movement.
Random Damage preserves the original expression and emits a separate modified
trace. Hit/wound/save consumers use the same terminal minimum. Detection and
Lone Operative share one terminal range policy; base, source bonus and Gone to
Ground penalty are combined before that policy.

Specific authoritative maintained direct App-data mirror rule/statement and
source ID: 02.02.01 Applying Modifiers, When Modifying Dice Rolls, and Other
Modified Rules at [40k.app](https://www.40k.app/rules/02-datasheets). The committed
transcription retains the complete operative clauses for these three findings,
including the terminal characteristic exceptions, rerolls, above-natural-maximum
dice, hit/wound ±1 limit, Charge cap and targeting-range bounds.

Provider, URL, App-data version or observation timestamp, transcription SHA-256,
and source-observation fingerprint: 40k.app, the URL above, observed
`2026-09-07T02:46:54Z` through its indexed page. Direct retrieval returned HTTP
403; no App build/version or co-version comparison is asserted. The source is
project-authoritative under the maintained-mirror policy, not claimed to be a
direct official capture. Each audit row also records provider non-affiliation.

| Stable source ID | Transcription SHA-256 | RuleEvidence observation | Retained audit observation |
| --- | --- | --- | --- |
| `gw-11e-core-modifiers:ordered-modifiers` | `3fe2b25367c04c5648e0b572c9a802a3afd7fe69b03e4e4b11058920d0ce5044` | `0a8006428bebaa7de19f3aad606b23b7b12957e801355533ff95f2d47ea9b0b5` | `ce29e604dda147708960150e85b167e1a195c308d3714b6125da6ec586e5536a` |
| `gw-11e-core-modifiers:modified-dice-limits` | `21d051f1c9f037ac11d4957a94dd93cba1bab969ffd1f9bf9ffc7c847ddc5d29` | `6029a91ce8f8988f0c6e17c56735d0f017fb5c2b6d141d2988eba3589ddad104` | `4b24c317d0bf608322ce332c58246d2a202834f261228d28db10640fb820422b` |
| `gw-11e-core-modifiers:detection-lone-operative-limits` | `0bb1eb9564822364cae638f8db886fe5186524fd999f16c382f1d4b73a9afccc` | `52cd07070b01404d9d16ea568f87c51de9977e2ede3ca0d8ee3d9315f51b29ad` | `293e62779134a817b3f697aa75e459c2f53616b9e577bfaef36404d3264c64f8` |

Package hash: `9ec39b854ae8180904d99c361b1f2df78024cdcf6b8362637c3ae5f7e3e632b6`.
Artifact bytes: `6467f2a059d7ce28d870160782124ecee957f43b8486c9bb5652eb670b8db958`.
The historical official source `gw-11e-core-rules`, SHA-256
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`, remains
provenance context; the maintained observation controls the reviewed clauses.

Scope and explicit exclusions: only C02-01/02/03 close here. No faction content,
new hook family or named handler is added. Order 28 retains individual Psychic
modifier selection. Order 43 retains target replacement/declaration sequencing;
future Into the Fray/Command Re-roll orchestration stays with its named owner.
The numerical Charge cap is implemented now, rather than deferred with those
independent tasks. Category 02 and whole-engine certification remain open.

Owning state/validation/mutation/event/replay path: pinned source JSON and eager
loader → shared core arithmetic/typed value records → existing effect registries
and Charge/Advance/attack owners → engine decision controller and validated
movement budget → event records, session projection, persistence and exact
replay. Raw dice and rerolls retain `DiceRollState` ownership. Physical movement
still requires the existing PathWitness validation. Extraction of Advance
records, modified dice, Hidden detection and dynamic model blockers keeps frozen
large modules from growing; the shooting-target size allowlist shrinks.

Decision and viewer-visibility impact: contract 11.4 adds zero/star value kinds
and documents engine-produced roll traces. Existing client submissions, choice
families and finite option IDs retain their validation paths. Source/context
and trace drift fail closed. Engine build identity rejects incompatible old
persistence/replay instead of inferring missing fields. Existing public Charge
results are equal in both viewer streams; hidden information continues through
the shared adapter redaction owner. No new player choice or visibility class.

Regression scenarios and same-bug-class search: pre-fix failures covered missing
division, operation ordering, terminal zero and missing range bounds. A separate
pre-fix real Damage-consumer regression reproduced rejection of both positive
and negative modifiers as raw-roll drift. Coverage includes all 120 operation
permutations, exact large-integer and fractional arithmetic, signed AP rounding,
terminal symbols/zero restoration, roll zero versus characteristic zero,
rerolls, above-natural-maximum Advance, Charge 1/12 limits, drifted/bool payloads,
real hit/wound/save consumers, intrinsic D6+1 Damage, Hidden cumulative bonuses,
Lone Operative, facade submission, both viewer streams, checkpoint restoration
and exact replay. Static audits require shared limit consumers and unmodified
Advance/Charge expressions. Source loader tests verify retained bytes/evidence
and reject drift. The repository-wide consumer search includes Battle-shock,
Desperate Escape, ordinary Charge, Heroic Intervention and reactive movement.
Existing Heroic Intervention uses natural 2D6, already within 1–12; its separate
Into the Fray move cap remains separate. Positive reactive distance bonuses are
movement budgets, not rewrites of raw dice. Conditional Lone Operative's fixed
12-inch descriptor already lies inside the terminal interval.

Generated artifacts/documentation: versioned modifier source package, retained
transcription/audit, source authority registry/pins, engine build manifest,
contract 11.4 schema/examples/manifest and generated TypeScript client, eight-shard
JUnit duration inventory, adapter contract, README and scope audit. Load and
execution status are separately recorded for exactly the three supported clauses.

Initial published-commit validation (`e5aba9edf8ab603523ff3d5a52c09e95cad4608b`):
the complete behavioral suite passed once with coverage:
`6495 passed`, `85.09%`, `765.57s`, 64 xdist workers with work stealing and the
bundled Node runtime on PATH. It emitted 10 unclosed SQLite connection
ResourceWarnings. No production code changed after this final run began.
The subsequent complete no-coverage code-quality suite passes: `385 passed`,
`305.51s`, 64 workers with work stealing. Its stale source-package inventory
assertion was updated from 17 to 18 for the added pinned modifier package;
the corrected audit passes all nine focused tests and the complete quality gate.
The eight-shard inventory was regenerated from that successful local Windows
Python 3.14.5 JUnit profile, with its report hash and host description retained;
the exact fail-closed eight-shard check passes.

Ruff check, Ruff format check (`2831` files), mypy (`2741` source files), pyright
(zero errors or warnings), all 11 import-linter contracts and all-files
pre-commit pass. The offline source/audit builder and engine-build identity
checks pass. The final runtime-tree SHA-256 is
`e1b27970a0bc4735b724489605068ce31ebbb17ecf37d77c501e1fa094c9f600`.
External-contract `--check --base-ref origin/main` passes against the unchanged
reviewed base. TypeScript generated-client/type checks, all five client unit
tests and two-server HTTP conformance pass (`342` assertions, contract `11.4.0`).
Installed-wheel smoke verifies `2571` runtime resources, `27` schemas and six
request families against that same engine identity. The scope/architecture audit
and `git diff --check` pass. The corrected fixed-seed and stale-expectation
focused regression run passes all 20 tests before the final complete suite.

The aggregate iteration also identified old expression/zero-result/version
expectations, coordinated tamper fixtures missing the newly required roll
stages, and fixed seeds tied to the former event-history hashes. Their intended
scenario and rejection assertions are retained; deterministic fixture IDs are
refreshed for the new schema without changing the RNG owner or its history
semantics.

PR URL and merge commit: [PR #432](https://github.com/SobolGaming/Warhammer_40k_AI/pull/432);
not merged. Merge remains an owner action.

The approved review correction closes the remaining cumulative runtime gap:
registered characteristic providers now emit typed operations and combine with
deduplicated generic effects before the shared final bound. The concrete
Toughness 6 / -8 / +4 regression produces 2 in either source order for ordinary
and attached attack targets, including JSON-restored effects and duplicate
source-slot occurrences. The same owner covers OC and movement characteristics;
later distance deltas remain separate and preserve fractional inches. Registered
historical Leadership uses the same ordering and bounds. Source-specific limits
are explicit operations, and replacements retain their operation/value kinds.

Checkpoint provenance retains original binding/effect IDs even when a source
contributes several operations. Structural OC lineage permits replacement base
and value-kind changes with source identity; exact runtime checkpoint
reconstruction continues to authenticate every resolved field. Source-terminal
values remain unchanged. Rehashed forged replacement provenance fails restore.
The correction introduces no new faction rule, hook family, named handler,
decision, adapter payload shape, or visibility class. See the approved scope
record for the consumer audit and deterministic fixture updates.

Validation at 441631a6:

Validation results: the final complete behavioral suite passes with coverage:
`6535 passed`, `85.08%`, `744.10s`, 64 xdist workers with work stealing and the
bundled Node runtime on PATH. The run reports 10 existing SQLite connection
ResourceWarnings. The first aggregate iteration's seven fixture cases pass
their focused regressions before this successful full run.

The subsequent complete code-quality suite passes once without coverage:
`388 passed`, `305.07s`, 64 xdist workers with work stealing.

Ruff check, Ruff format check (2833 files), mypy (2743 source files), pyright
(zero errors/warnings), all 11 import-linter contracts, and all-files pre-commit
pass. The exact eight-shard inventory check passes; this correction adds no
behavioral test file. The source/audit builder and runtime build-identity checks
pass. Engine identity:
`warhammer40k-core-v2:runtime-tree-sha256-v1:a10ca235c1b439bdec1ab473ba347953e49fbb7052dcdee037f45eb4af872224`.

External-contract `--check --base-ref origin/main` passes against
`55c06d4dad60c34a77b381d864db7e7d1c3f98a8`. TypeScript generated-client/type checks,
all five client unit tests, and two-server HTTP conformance pass (342 assertions,
contract 11.4.0). Installed-wheel smoke verifies 2572 runtime resources, 27 schemas
and six request families against the same engine identity. Scope, architecture,
module-size and diff audits pass. No production code changed after the aggregate
coverage runs began.

Historical generic Leadership follow-up: completed Battle-shock requests now
reconstruct generic characteristic effects at their original event boundary,
combine them with registered historical operations, and retain the exact
Leadership comparison. The reconstruction authenticates loaded source semantics,
ownership, creation/activation and expiration evidence, while sharing live
applicability, source-slot deduplication and operation IDs. Later expiry does not
substitute the restored current-effect inventory for historical authority.
Generic-only and combined/duplicate-source tests require exact lifecycle/session
restoration and replay after normal Command-phase completion; altered source,
target, delta, duration, creation clock and activation evidence are rejected.
See `ORDERS_26_27_29_SCOPE_PLAN.md` for the invariant, extraction audit and scope.

Final historical Leadership validation:

The complete behavioral suite passes once with coverage: `6564 passed`,
`85.06%`, `795.05s`, 64 xdist workers with work stealing and the bundled
Node runtime on PATH. The 10 warnings are existing SQLite connection
ResourceWarnings. The subsequent complete code-quality suite passes once without
coverage: `389 passed`, `347.53s`, also using 64 workers with work stealing.

Ruff check, Ruff format check (2836 files), mypy (2746 source files), pyright
(zero errors/warnings), all 11 import-linter contracts and all-files pre-commit
pass. The exact eight-shard inventory check passes. The source/audit artifact
check and runtime build-identity check pass. Engine identity:
`warhammer40k-core-v2:runtime-tree-sha256-v1:a88ba836f139acb5f7c74451b1939927f3084d60b6ae85dd53bd23002a01128b`.

External-contract `--check --base-ref origin/main` passes against
`55c06d4dad60c34a77b381d864db7e7d1c3f98a8`. TypeScript generated-client/type
checks, all five client unit tests and two-server HTTP conformance pass
(342 assertions, contract 11.4.0). Installed-wheel smoke verifies 2574 runtime
resources, 27 schemas and six request families against that engine identity.
Scope, architecture, module-size and diff audits pass. No production code changed
after the aggregate coverage run began.


### P24I — Order 28

Status: Implemented; all required local gates passed. Published in [PR #433](https://github.com/SobolGaming/Warhammer_40k_AI/pull/433); not merged.
Finding ID: `C24-09`. Dependencies P00, P02A and P02B are merged; reviewed base
`67c60842ef87d3df646ec762f4e328eeff46ee0b` includes Orders 26, 27 and 29 via PR #432.
The owner approved the upstream BS/WS provenance repair recorded in
[Order 28 scope review](ORDER_28_SCOPE_PLAN.md) on 2026-09-07.

Violated invariant: each individual modifier to a Psychic attack's BS/WS or hit
roll must retain its source until the controlling player has chosen the ignored
subset. Combination and final bounds follow that selection. Equal numerical
outcomes cannot identify distinct source selections.

How it was done: Cover and Plunging Fire were combined into one skill total,
and declared, persisting, registered and generic hit effects into one hit total.
Cancelling totals suppressed the choice. Options represented only whole numeric
buckets. Upstream BS/WS providers also clamped each delta and overwrote the raw
skill, losing both source operations and correct arithmetic order.

How it is done: `WeaponProfile.skill_modifiers` retains typed source-linked
operations against the original skill. Existing RuleIR and Adeptus Mechanicus,
Astra Militarum and T'au BS/WS producers use the same core operation owner.
`RangedAttackPool.hit_roll_modifiers` preserves declaration contributions;
registered bindings and generic/persisting effects contribute their own IDs.
`attack_modifier_snapshots` supplies the same ordered source inventory to the
Psychic request and hit resolver, including Cover and Plunging as separate terms.
Gathered attack signatures retain these records instead of merging their totals.

Finite per-source keep/ignore choices permit every subset, with whole-set
shortcuts and at most six options per request. Deduplication uses decided/ignored
source identity rather than arithmetic. Each continuation records a canonical
prefix; the hit resolver applies only retained operations through `ModifierStack`
and then the existing hit cap. Hit events preserve the completed selection.

Specific authoritative maintained direct App-data mirror statements:
[24.29 Psychic](https://www.40k.app/rules/24-core-abilities) permits ignoring any
or all BS/WS and hit modifiers for each Psychic attack;
[02.02.02 Ignore Modifiers](https://www.40k.app/rules/02-datasheets) permits
retaining only some modifiers, including opposing modifiers in the same bucket.
Complete operative transcriptions are retained in the Core modifiers JSON package.

Provider: non-affiliated 40k.app. Observation timestamp:
`2026-09-07T16:05:47Z`, through the indexed pages. Direct retrieval returned HTTP
403. No App-data version, direct official capture or co-versioned comparison is
asserted. The owner-approved maintained-mirror policy supplies project authority;
no source exception-pause condition was observed. The existing historical official
Core Rules PDF and SHA-256 remain provenance context, not the controlling wording.

| Stable source ID | Transcription SHA-256 | RuleEvidence observation | Retained audit observation |
| --- | --- | --- | --- |
| `gw-11e-core-modifiers:psychic-individual-modifiers` | `4a6d83c584957daf12e931a840822fee1a46c25814eb14fc6f563bf39f82c4d0` | `0c2099e07a6c3b6db8c974975be03eef02da5cc0a33fbf9919065a6d307f8cc4` | `7a0858e8559dec4c4c8cd135e6865be496f91e94e26fab51582504ce8f8fb5cc` |
| `gw-11e-core-modifiers:ignore-individual-modifiers` | `7c1439a4548907e7648e50c665cab0bfb7e0cf9eb3e92d82ccb453fda838a2a0` | `b84f3f6f4c819e14dfcc300768303dde1a40eef2de44dbf5626d0efcdc62cccc` | `5416540cae6e3d3c1d4c006550573651951dd4fe4ee21cebb70abc8aaabbe4ff` |

Package hash: `69eab05ecbc5a23aaa08fe499005b01a0f58a360a823e22dc102a1e6aef51e89`.
Artifact bytes: `07db393dbbcbe13435a3c24c1f999bb96271c6d696e80892803cc633d6ae0995`.
The eager source loader and source-authority registry pin the new evidence rows.
Load support is recorded as `loaded`; semantic execution is separately recorded
as `executable_engine_runtime` with the shared Psychic attack consumer.

Owning state/validation/mutation/event/replay path: retained source JSON and eager
loader → original catalog skill plus source-linked runtime operations → attack
pool and common modifier snapshots → `DecisionRequest` / finite submission /
`DecisionResult` → lifecycle prevalidation → engine-owned attack resolution →
hit/decision events, viewer projections, persistence and exact replay.

Decision and viewer impact: contract 11.5 adds optional nonempty skill-operation
inventories to runtime weapon profiles and documents the individual finite choices,
source hashes and hit-event trace. The finite submission envelope remains the same.
Pending choices bind the weapon/pool, actor, attack context, phase and canonically
ordered current persisting-effect inventory. This conservatively rejects a change
to any persisting effect before submission, including same-total BS/WS source swaps.
The global effect hash is engine-private; the shared adapter redaction owner
removes it recursively from all viewer projections, decision/event payloads and
status metadata. Invalid submissions do not pop the queue, record a choice, consume
RNG or mutate state. Restore verifies continuation history, pending source context and hit-event
selection/arithmetic. Session restoration and replay additionally reproduce the
recorded tail from its captured initial state. Build identity rejects older runtime
saves lacking the new provenance. Both phase families use the same facade and shared
adapter redaction module; no new visibility class is introduced.

Regression scenarios and same-bug-class search: pre-fix Cover/Plunging cancellation
and BS 2 modifier ordering failures were reproduced with real domain objects.
Regressions cover opposing hit and skill terms, bounded BS/WS results, all sixteen
subsets of a four-source inventory, distinct equal-valued sources, source swaps with
unchanged totals, duplicated/foreign/bool/arithmetic/context payload corruption,
partial-history/actor/option restore drift, profile provenance loss, Shooting/Fight
facade submissions, both viewer streams, partial/completed persistence and replay.
The producer search covered generic/catalog skill effects and all existing faction
skill producers, declaration hit rules, Smokescreen, runtime bindings, gathering
and attack hosts. Static audits require shared source collection, core arithmetic,
lifecycle prevalidation and restored-history validation. Existing attack routing
audits follow the extracted prevalidation owner.

Scope and architecture: only C24-09 is implemented here. The existing faction
producer migration repairs the shared numeric/provenance invariant; it does not
add or certify faction rules. P22B's Psychic ability-use ledger and P24C2's duplicate
ability-instance choice remain separate. No new named handler, generic hook family,
content-name branch, movement semantics or architecture boundary is introduced.
Attack prevalidation and its private checks are extracted from the frozen lifecycle
module. New modules remain below 1,500 lines. Category and whole-engine certification
remain open.

Initial implementation validation (reviewed head `15d4efc5`): the complete behavioral suite passed once with coverage:
6,609 tests, 85.07% combined statement/branch coverage, 64 xdist workers with work
stealing and the required Node PATH prefix. The final code-quality suite passed
390 tests without coverage. Ruff check/format, mypy (2,754 source files), pyright,
all 11 import contracts, pre-commit and the exact eight-shard check passed.
Focused iteration included the 45 Order 28 regressions and broader attack/skill
coverage. The eight-shard inventory is regenerated from the successful complete
JUnit profile (Python 3.14.5, Windows, 219 behavioral files, 6,609 cases), with
its SHA-256 and accurate host/runtime metadata committed in `durations.json`.

The retained modifier-source generator check and isolated external-contract
regeneration/base-ref compatibility against `origin/main` passed. The generated
TypeScript check and typecheck, five client unit tests and live HTTP conformance
passed (342 assertions, contract 11.5.0). Installed-wheel smoke validates 2,580
runtime resources, 27 schemas and six request families against engine build
`warhammer40k-core-v2:runtime-tree-sha256-v1:b4d2c59bad74ec2d47ec309cb0af0a9041b4a01b628e5b3ff5b2125164c96de8`.

The contract addition crossed the generated TypeScript module budget. Its
operation interface is now generated separately, retaining the public type
exports and shared contract source; drift checking covers both file contents
and the complete generated-file inventory. The modules are 1,368 and 151 lines.
Only conformance generation/artifacts, code-quality assertions, documentation and
the shard inventory changed after the successful engine coverage run; client and
quality gates were then revalidated. Scope, architecture and final diff audits
pass. No engine production code changed after that coverage run began.

PR URL: [#433](https://github.com/SobolGaming/Warhammer_40k_AI/pull/433). Merge commit: not merged.

#### PR #433 completed-history review correction

Reviewed head `15d4efc5db38f1d38fb45c30a804b6a312f5507b` passed all remote CI lanes
(run #1560). The following correction addresses the subsequent C24-09 review;
those earlier results do not validate this revised runtime.

Violated invariant: completed Psychic choices must authenticate the modifiers
available at the original attack boundary. Matching copies in decision requests,
options/results and hit events establish internal agreement, not source authority.
A same-total substitution of a non-first hit/skill source, both source commitments,
or the controlling actor was reproduced as accepted by standalone lifecycle restore
in both Shooting and Fight: all ten strict pre-fix regressions failed to reject.

The corrected owner is `psychic_modifier_history_origin`. It retains one immutable
pre-declaration lifecycle origin, prepared before queue pop and installed only after
the controller accepts the result. Origins are nonrecursive and cannot include an
earlier attack declaration or Psychic decision. Catalog/config identity and exact
ledger-prefix checks bind the origin to the restored game. The existing engine
replay owner then reconstructs declarations, profile operations, effects and finite
requests from these original inputs and demands exact request/options and event-tail
equality. Coordinated copies of a false source, hash or actor fail against the live
request reconstructed at the historical boundary. Existing continuation, source
selection and hit-arithmetic validation remains in place.

This uses the same lifecycle validators and mutation owners as live play; it adds
no source-specific historical handlers and never consults current effects as a
replacement for expired attack sources. The preserved origin also authenticates
completed history in a replay's captured initial lifecycle, where replaying only
that artifact's tail would otherwise miss the prefix. Original catalog and
pre-attack state remain the authority root, as for ordinary exact replay; this is
not cryptographic authentication of an arbitrary externally replaced game.

The bug-class search covered pending and completed Psychic validation, session
persistence replay, captured initial lifecycles, and existing historical Leadership
and mission source-authority implementations. Scope stays on C24-09: a single
engine origin and replay owner replace a second implementation of historical
modifier semantics. One origin is retained per lifecycle; restoring recorded Psychic
choices adds a replay of the decision tail. The operator-only checkpoint field is
covered by the existing persistence/replay JSON contract and shared redaction owner;
no public decision, event family, faction rule or named handler changes.

Regressions cover coordinated completed source/commitment/actor corruption in both
phase families, absent/recursive/late/foreign origins, ledger-prefix substitution,
real phase expiry followed by exact standalone and session restoration, captured
completed initial histories, and exact replay. Static guards require origin capture,
standalone restoration validation and the shared replay consumer. Final revised validation passed: 6,631 behavioral tests with 85.07% combined
statement/branch coverage, followed by all 390 code-quality tests without coverage,
both using 64 xdist workers and work stealing. The focused Order 28 suite passed
67 tests. Ruff check/format, mypy (2,755 files), pyright, all 11 import contracts,
pre-commit and the exact eight-shard inventory check passed. The refreshed shard
manifests use the successful complete Windows JUnit profile (Python 3.14.5,
219 behavioral files, 6,631 cases), with its report SHA-256 and runtime metadata.

Source regeneration, engine identity and isolated external-contract regeneration
with `--base-ref origin/main` passed. TypeScript generation/typecheck, five client
unit tests and live conformance (342 assertions, contract 11.5.0) passed.
Installed-wheel smoke verifies 2,581 resources, 27 schemas and six request families.
The revised runtime identity is
`warhammer40k-core-v2:runtime-tree-sha256-v1:c90ed5c08e063f34eb3930e82c5c6ac116c39ca2fca7eee57227c1011fc3fc98`.
No production code changed after the successful aggregate coverage run began.
The correction is published through PR #433; merging remains separate.

### Order 30 / P05B implementation record

Finding `C05-02` is implemented with the approved extension to executable Shoot On
Death and source-authorized shoot-or-fight alternatives. Logical death now opens
one typed retained destruction record before removal or other destruction
triggers. Acceptance preserves the exact original base for measurement,
visibility, abilities, Stratagem targeting, Charge/attack targets, enemy
Engagement and Fight movement constraints. Living movement actors and damage
recipients remain distinct from retained battlefield presence.

Fight entitlement uses the unit's ordinary activation under 05.04.05 and cleans
up after that activation or at phase end. Shooting uses the ordinary out-of-phase
proposal and attack executor, with weapons restricted to the destroyed model.
One source selection chooses one action; it cannot activate unrelated models or
grant both attacks. Deferred destruction, Deadly Demise, collateral casualties,
Feel No Pain and destroyed transports share the same cleanup and exact-once
physical-removal owner. Nested retained shooting preserves and restores each
parent executor. Own-Hazardous deaths use the existing applied-mortal-wound
destruction service, including casualties waiting for their individual reactions.

Source authority is preserved by the offline generators and typed data loaders:

- `core_fight_on_death_2026_09` pins the complete 05.04.05 observation and v931
  retained-presence FAQ. Its artifact SHA-256 is
  `2465e094b0c30db3321924367db7a995660e1524c7fde5876482397bd69acd9d`.
- `retained_attack_sources_2026_09` pins For the Chapter! and Unending Fidelity,
  browser-observed at `2026-09-08T01:39:45+00:00`, with App-data version 946
  (released 2026-09-02). Its artifact SHA-256 is
  `db0180dc622c1b77fc8963a271024bd005e676402dbb103528dfe5d16c091f87`.
  Historical official faction-pack provenance remains separate from the current
  maintained-mirror observations. Execution status and catalog fieldability are
  recorded separately; these consumers do not certify complete faction coverage.

For the Chapter! executes after enemy attacks or its own Hazardous death, allows
prior shooting, and automatically passes Hazardous tests for the granted shots.
Unending Fidelity uses the generic timed RuleIR grant and Stratagem pipeline,
spends 1CP, and offers shoot or fight on a successful 4+ only when that model has
neither shot nor fought in the phase. The common completed-pools event records
model participation before deferred destruction or Hazardous tests.

Contract 12 records the selected action, retained presence and nested shooting
execution. Viewer projections and event streams use the shared redaction owner;
operator persistence and replay authenticate source/cause, decisions, original
placement, attack participation and completion against the exact engine build.
Obsolete remove/re-add histories fail closed. See
`ORDER_30_SCOPE_PLAN.md`, `ADAPTER_DECISION_CONTRACT.md` and
`../contracts/migrations/11-to-12.md` for ownership and migration details.

Facade regressions cover both executable actions, both source consumers,
acceptance/decline/failed triggers, prior-action restrictions, own Hazardous and
Feel No Pain, nested retaliatory shooting, collateral cleanup, transport
decisions, stale submissions, checkpoint tampering and both viewers. Existing
phase consumers and historical integrity regressions use retained presence.
Initial PR-head `e4444cd` local Windows validation passed on 2026-09-08: 6,712 behavioral tests with
85.01% coverage, then 391 code-quality tests without coverage, both using xdist
work stealing. The eight-shard inventory was regenerated from that successful
JUnit profile and its exact fail-closed check passed. Ruff check/format, mypy,
Pyright, import-linter and pre-commit passed. Source generators and engine identity
checks passed; the external contract passed its isolated base-ref check against
`8668a87a1b45e0cc58a05e07802771fcb2dad06f`. The regenerated TypeScript client,
five client unit tests, 342 live conformance assertions and installed-wheel smoke
(2,609 runtime resources, 27 schemas, six request families) passed.

The initial published runtime identity was
`warhammer40k-core-v2:runtime-tree-sha256-v1:a493d05a282ded9d4da39df68cd32ece932e070302ac1fcd39d2f907c3b05232`.
Source-authority JSON uses platform-stable LF bytes with reviewed SHA-256
`d729fc2d567b59321c4d8ffa0bc981632cda3aa402a56978a37e7932d14ac2d5`.
No production code changed after that initial successful aggregate coverage run began.

Scope remains C05-02 plus the two approved shooting consumers. P02D's model-keyword
schema and P05C's post-removal former-footprint measurement remain separate.
No new named handler, speculative hook family, architecture boundary or
out-of-scope catalog support is introduced.

PR #434 review corrections preserve these owners. Retained shooting now carries
a required parent cause; execution, resumption and historical validation share a
validated nesting chain independent of globally sorted effect IDs. Persisted
grants resolve through the existing rules-unit effect applications, including
canonical attached identities, split predecessors and duplicate-alias handling.
The selected-target Stratagem comparison also recognizes physical options as
members of the attacked rules unit, allowing the real Unending Fidelity consumer
to persist its canonical grant for both executable alternatives.

New regressions deliberately cover both lexical parent/child orders, pending
child restoration, exact replay, invalid parent links and exactly-once removal.
Attached Unending Fidelity exercises Shoot and Fight through facade submissions
and restored checkpoints; split successors discover each grant once per model.
The corrected runtime identity is
`warhammer40k-core-v2:runtime-tree-sha256-v1:39acb9c8f509be9dac75cf49f98bbde371b2d2690a9aaecff2f48291628843df`.

Review-correction validation passed on 2026-09-08: 6,718 behavioral tests with
85.01% coverage and 391 code-quality tests without coverage, both using xdist
work stealing. Both attached-unit cases also passed after the final fixture
placement adjustment; production code was unchanged. The eight-shard profile
was refreshed from the successful JUnit report and its exact inventory check
passed. Ruff, mypy, Pyright, import-linter, pre-commit, source/identity generators,
base-ref contract checks, five TypeScript unit tests, 342 live conformance
assertions and the installed-wheel smoke all passed.

## Order 31 — P02D model keyword authority

**Status:** Implemented and locally validated in
[PR #435](https://github.com/SobolGaming/Warhammer_40k_AI/pull/435); awaiting merge.

**Finding IDs:** C02-04. **Dependencies and evidence gate:** P19, P05B and
S-MIRRORS are present on main base `14e7bcfc7e733477cc7ab1309f803494a70b9c78`;
APP-AUTHORITY. No new exception pause
or faction-support claim is introduced.

**Violated invariant:** A rules unit receives a keyword only from a model that
currently belongs to its rules population. Previously `ModelInstance` had no
keyword ownership and immutable unit inventories allowed a removed specialist
to keep contributing its keyword while other models survived.

**How it should be done:** Preserve source-linked assignments on each model;
derive current rules-unit inventories from living models plus P05B retained
presence. Ordinary destruction and retention cleanup remove contribution without
changing surviving component abilities or deleting historical model identity.

**Authoritative statement and source ID:** The complete Game Datamissions
App-data v931 FAQ says destroyed models do not contribute keywords to their prior
unit and illustrates the last Aspiring Sorcerer's loss of PSYKER in Rubric Marines.
Stable source ID: `gw-11e-core-model-keywords:destroyed-model-keywords`.

**Provider and provenance:** Game Datamissions,
<https://game-datamissions.com/11th/rules/changelog>, v931 selected through the
page's version navigation (`?v=931`), observed 2026-09-08T13:35:55Z. Transcription
SHA-256 `d2f96dfeb423592623f05012e82c181a7737b12c791f7fbd237202a1968025be`;
source-observation fingerprint
`74930ebc501e1e6ff74b53e83f94d7ac728ef9f6eef8cd6d4355e4b42f800b3e`.
The reviewed audit records the provider's non-affiliation and preserves the
existing official historical source hash. The separately pinned P05B statement
continues to own the retained-presence exception.

**Scope and exclusions:** Catalog model keyword ownership, canonical factories,
current rules-unit aggregation, affected model/historical consumers, lineage
validation and adapter projections. Existing Warlord/Enhancement assignment
scope is preserved; Order 62 owns specific bearer selection. No new named rule
handler, generic hook family, unsupported content, or faction certification.

**Owning path:** Source keyword rows retain model scope at the catalog boundary;
complete typed catalog assignments feed UnitFactory and materialization. Engine
mustering grants update model-owned assignments with provenance. Destruction and
healing retain immutable model identity while current queries follow authoritative
presence. Split records retain exactly their model memberships. Restore compares
against canonical muster/split/materialization lineage; historical Psychic uses
consult the existing sparse model-authority timeline at the accepted event.
Existing materialization descriptor IDs distinguish Blue and Brimstone models
that share a stat profile, including after the existing datasheet handoff. Source
labels resolve at ingestion, with regular plural normalization and fail-closed
unknown or ambiguous ownership; runtime consumers use IDs and canonical tokens.

**Decision and visibility impact:** Existing facade submissions remain unchanged.
Contract 13 updates game views, session projections, metadata/outcomes and operator
persistence. Model rows expose intrinsic keyword/source inventories; current unit
rows reflect model presence. Secret formation choices remain viewer-scoped.

**Regressions and bug-class search:** The initial specialist-removal regression
failed before implementation. Coverage includes exhaustive scope, source bridge,
ordinary casualty, retained Fight On Death, cleanup, both viewers, malformed finite
selection, checkpoint source forgery, replay and split lineage. Searches cover
unit keyword field replacement, direct model constructors, catalog model-scope
loss, physical model visibility, historical Psychic/Character classification,
transport destruction and retained-source eligibility. Existing fixture keyword
changes now update real model assignments.
The shared redaction module also removes unrevealed attachment tags from model
keyword provenance and unit inventories; a two-viewer regression covers the leak.

The PR #435 review correction routes live RuleIR target preflight and Stratagem
required, any-of, excluded and faction-keyword gates through state-backed
`RulesUnitView`. The same-class audit also migrated single-keyword target policies,
companion enumeration/validation and shared generic Stratagem effect conditions.
Those shared effect helpers now require `RulesUnitView` explicitly. The casualty
regression checks actual RuleIR preflight and parameterized Stratagem submission
validation while alive, retained, restored and removed, including ordinary
casualties and both companion directions. Exact replay and both viewers remain
covered. Static guards protect the current-eligibility boundary. Model-owned
queries keep their applicable presence policy; roster/mustering and historical
source-snapshot queries keep their separate identity populations. `UnitInstance`
continues to expose only living physical component keywords.

**Generated artifacts and documentation:** Pinned source JSON and maintained-mirror
audit/registry; engine build identity; Contract 13 schemas, examples, immutable new
baseline and TypeScript models; adapter contract/migration documentation and the
complete eight-shard test inventory.

**Validation results:** Final production tree passed on 2026-09-08: 6,732
behavioral tests with 85.02% coverage, followed by 394 code-quality tests without
coverage, both using xdist work stealing. The successful coverage run used 18
workers and an isolated coverage database; its JUnit report regenerated all eight
shards and the exact fail-closed inventory check passed. Ruff check/format, mypy,
Pyright, import-linter and pre-commit passed. Source and catalog generators,
engine identity and base-ref external-contract checks passed. The TypeScript
generated-client/type checks, five unit tests and 342 live conformance assertions
passed; the package scripts ran directly with bundled Node because npm was not
available. Installed-wheel smoke passed with 2,617 runtime resources, 27 schemas
and six request families. No production code changed after this successful
aggregate coverage run began.

Published runtime identity:
`warhammer40k-core-v2:runtime-tree-sha256-v1:b3b62ca8b174a3eb04f67254ba508cd8fa612d55a9c204a6b9e565b6f7a45437`.

**PR URL and merge commit:**
<https://github.com/SobolGaming/Warhammer_40k_AI/pull/435>. Merge pending; merge
remains user-owned.

## Orders 32–35 — implementation-record index

These links backfill the roadmap index against current main. Merge status was
checked on 2026-09-10; validation numbers inside the linked records apply to
their stated heads, not to this planning PR or complete Core Rules compliance.

| Order / PR / findings | Status and merge commit | Authoritative implementation and review record |
|---|---|---|
| 32 / P06C / C06-03 | [#436](https://github.com/SobolGaming/Warhammer_40k_AI/pull/436) merged; `8ef8cb83622eb30066fbd113aa94bd87e2ec4fe3` | [Order 32 visibility review](performance/ORDER_32_VISIBILITY_REVIEW.md), including R32-001 retained visibility correction and explicit performance deferral. |
| 33 / P10 / C10-01 | [#437](https://github.com/SobolGaming/Warhammer_40k_AI/pull/437) merged; `e56c1a4caf2a6915548222caed0872627f8dbf43` | [Order 33 scope and review](ORDER_33_SCOPE_PLAN.md), including R33-001/002 and the deferred Heavy-history issue now assigned to P21A. |
| 34 / P16 / C16-01, C16-02 | [#438](https://github.com/SobolGaming/Warhammer_40k_AI/pull/438) merged; `51952e49c2b360f1dacffc03d53916324a1e9253` | [Order 34 scope and review](ORDER_34_SCOPE_PLAN.md), including retained shooting and historical activity repairs; other Action interruption consumers remain explicitly listed above. |
| 35 / P15G / C15-07 | [#441](https://github.com/SobolGaming/Warhammer_40k_AI/pull/441) merged; `b41e44323f66f494399b763d8c7c23f981d9239f` | [Order 35 scope and review](ORDER_35_SCOPE_PLAN.md); Rapid Ingress eligibility does not close C20-02 Core reserve policy. |


## Order 36 — P01D owner-tiered Rules Sequencing

**Status:** Implemented and locally validated; ready for PR review. This closes
C01-04. The full consumer inventory, source record, scope explanation and
acceptance matrix are in [Order 36 scope and validation](ORDER_36_SCOPE_PLAN.md).

The shared timing owner now resolves active mandatory, active optional, opposing
mandatory and opposing optional tiers, preserving each owner's choice and the
original trigger population. New triggers wait for the original batch to finish.
Temporary active-player authority follows selected moves and attacks; between
turns it follows the first-turn player. Source-explicit exceptions remain intact.
Phase/round/turn, Command Battle-shock, movement, attack, casualty and mission
consumers use the shared authority, with historical ownership and viewer redaction.

The pinned `gw-11e-core-sequencing` JSON package records the maintained-mirror
observation separately from official historical evidence. Contract 15,
persistence v7 and replay v9 carry the new authority; incomplete older payloads
are rejected. No load-only content is promoted to executable support.

Final local validation on 2026-09-11: **7,202 behavioral tests at 85.01% coverage**,
**427 code-quality tests**, and **19 macOS semantic-audit tests** passed. Ruff,
mypy, Pyright, all 11 import contracts, pre-commit, regenerated eight-shard
inventory, source/engine identity, base-ref contract, TypeScript client and unit
checks, 342 live conformance assertions and installed-wheel smoke passed.
[Order 36 performance evidence](performance/order36/README.md) passes the unchanged
Order 34 and Order 35 component budgets and retains initial failures. Complete-game
performance remains uncertified. The source's move/shoot-back example has
compositional coverage rather than a new playable load-only Stratagem scenario.

Requested main refreshes include documentation PRs through #450 (`f9f33e47`).
The delivered runtime manifest SHA-256 is
`390231096e85983215cb4c0ba841706c59bbe79dd049f6670c3df594463838a0`.

## Order 37 — P02E final Stratagem CP costs

C02-05 is implemented by the shared Stratagem cost registry and the exact core
modifier arithmetic owner. Existing catalog, generic and faction providers now
return typed operations; final costs are bounded to zero through the selected
use's unmodified cost plus one after all operations and rounding. Source
commitments survive terminal limits and explicit non-cumulative restrictions.
All existing option, target, spending, increased-cost failure, event and replay
consumers share that result. See the [scope and validation record](ORDER_37_SCOPE_PLAN.md)
for the source observation, consumer audit, acceptance matrix and publication gates.
Other category 02 and Stratagem findings retain their own owners.


## Order 38 — P18G Core disembark eligibility

Status: implemented, locally validated and published in [PR #454](https://github.com/SobolGaming/Warhammer_40k_AI/pull/454); awaiting review and merge.

C18-08 separates the granting rule from Core 18.06/18.07 movement eligibility.
Assault excludes only Advance and Fall Back; Shock has no Core movement gate.
Every eligible permitted mode is selectable alongside ordinary disembarkation,
and placement revalidates current cargo, battlefield presence and permission.
The retained v931 operative source rows and observation fingerprints are unchanged;
their runtime consumer inventory and package hashes are regenerated.

The [scope and validation record](ORDER_38_SCOPE_PLAN.md) contains the source
provenance, owner trace, full six-state acceptance matrix, same-class search,
contract impact, performance evidence and publication gates. It supersedes the
Normal-only P18D and Advance-only P18E eligibility claims above. Their engagement
and forced-Fight claims are not recertified here; the engagement-owner conflict
remains assigned to its existing finding. Category 18 remains incomplete.
