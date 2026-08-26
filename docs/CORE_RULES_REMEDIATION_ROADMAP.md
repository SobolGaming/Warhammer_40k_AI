# CORE V2 Core Rules Remediation Roadmap

## Scope and authority

This roadmap covers only Warhammer 40,000 11th Edition Core Rules categories
01–25. Factions, faction detachments, faction datasheets, and the out-of-scope
content listed in `AGENTS.md` are excluded.

40k.app is the exhaustive Core Rules corpus for this audit. Under repository
policy
`core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26`,
the owner attests that it is verbatim Games Workshop App data. It is therefore
the project-authoritative maintained App mirror. Evidence controls in this
order:

1. Direct official-App evidence when an actual App/40k.app divergence is
   observed.
2. Hash-pinned 40k.app observations under the owner-approved authority policy.
3. Hash-pinned official Games Workshop PDFs for history and material the App
   corpus does not replace.

Maintained App wording supersedes an older PDF where they differ. The site is
still identified honestly as a non-affiliated hosting provider, never falsely
as Games Workshop-owned, and the live website is never queried by the runtime
engine. Reviewed source artifacts remain the loader boundary.

P00 is PR #405. It changes provenance and planning only; it does not change
gameplay semantics. The retained official Core Rules PDF has SHA-256
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.
The retained 40k.app observation is dated 2026-08-25.

Only one roadmap PR is opened at a time. It is reviewed and merged before work
starts on the next PR. Debugging must not use an interactive debugger.

## Status and evidence gates

- `APP-AUTHORITY`: the owner-approved policy and hash-pinned category
  observation establish 40k.app as the controlling source and category
  locator for the planned requirement. The implementation PR must still
  observe and retain an exact operative source row with stable source ID, URL,
  observation timestamp, transcription hash, and immutable source-observation
  fingerprint before
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
execution order. The pinned 40k.app category observation and owner-approved
policy establish project authority for planning, but do not substitute for the
exact operative source row and source-observation fingerprint required in each
implementation PR.
Only an `EXCEPTION-PAUSE` stops an otherwise dependency-ready PR. There is
still only one open roadmap PR.

`T-TRANSPORT` is defined conservatively as P18A, P18C, and P18B all merged. The
user may approve a narrower definition before P20, but it must be recorded in
this document rather than inferred during implementation.

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
- `CAUDIT-01` owns the final all-category audit and certification gate. It is
  not an implementation finding and cannot close while any in-scope finding is
  open.

## Canonical one-PR-at-a-time sequence

| Order | PR | Finding(s) | How it is currently done | How it must be done | Controlling 40k.app locator and operative requirement to pin | Prerequisites | Gate |
|---:|---|---|---|---|---|---|---|
| 1 | P15D | C15-04 | Fire Overwatch’s source row omits exact target/Snap wording; Crushing Impact’s row says Vehicle/Strength while runtime supports Monster-or-Vehicle/Toughness; older PDF numbering conflicts with current App headings and one App example has a stale cross-reference. | Correct only source records, stable identifiers, hashes, and provenance to current complete App text. Keep correct runtime behavior; bind by title/operative text and record the stale example reference. | [15.05–15.09](https://www.40k.app/rules/15-stratagems): current headings make Crushing Impact 15.05 and Explosives 15.06; the category 12 example’s contrary number is internal drift. | — | APP-INTERNAL-DRIFT |
| 2 | P08A | C08-03 | Generic `START_PHASE` dispatch runs before the handler, but the Command-specific start registry runs after Core CP is granted. | Route every start-of-Command rule and choice through one canonical boundary before Core CP is granted. | [08.01–08.02](https://www.40k.app/rules/08-command-phase): resolve start-of-Command rules before Gain Core CP. | — | APP-AUTHORITY |
| 3 | P08B | C08-01, C08-02 | The active player’s Battle-shock is cleared at Command start, and tests are requested only below Half-strength. | Preserve existing Battle-shock until a required test succeeds; test each rules unit that is currently Battle-shocked or at/below Half-strength exactly once. | [08.03](https://www.40k.app/rules/08-command-phase): the required-test candidates are currently Battle-shocked or at/below Half-strength, and success removes Battle-shock. | P08A | APP-AUTHORITY |
| 4 | P09A | C09-01 | Reserve arrivals are delayed until battlefield units are handled, while tactical disembarks are front-loaded separately. | Use one Move Units selection loop containing unselected battlefield, embarked, and Strategic Reserve units so moves, disembarks, and ingress can interleave. | [09.02 Move Units](https://www.40k.app/rules/09-movement-phase): the player selects an eligible unit and resolves its movement before selecting the next. | P08B | APP-AUTHORITY |
| 5 | P09B | C09-02 | Voluntary Desperate Escape is offered but rejected without a forced/overflight cause; its hazard rolls and follow-up test are incomplete. | Permit Ordered Retreat as an optional Desperate Escape, roll once for every model, then test Battle-shock if the unit was not already shocked. | [09.02.02 and 09.07](https://www.40k.app/rules/09-movement-phase): Ordered Retreat may invoke Desperate Escape and its per-model hazard/test sequence. | P09A | APP-AUTHORITY |
| 6 | P06A | C06-01 | Visibility uses zero-width mathematical rays. | Use one 1mm-wide 2.5D visibility corridor across terrain, models, hulls, attacks, and abilities. | [06.01 Visibility](https://www.40k.app/rules/06-other-concepts): visibility requires the rule’s 1mm sight corridor rather than an infinitesimal ray. | — | APP-AUTHORITY |
| 7 | P06B | C06-02 | Mortal-wound routing silently selects the first sorted legal model when several share the active priority tier. | Resolve mortal wounds individually; request a controlling-player finite choice for ties and auto-select only a sole legal model. | [06.02 Mortal Wounds](https://www.40k.app/rules/06-other-concepts): allocate by wounded non-Character, other non-Character, wounded Character, then other Character priority. | — | APP-AUTHORITY |
| 8 | P19 | C19-01 | Bodyguard loss unconditionally splits surviving Leader/Support components into separate rules units. | Preserve the original attached rules-unit identity until the last model that started in it is destroyed, while retaining explicit component lineage. | [19.01.01 Attached Units](https://www.40k.app/rules/19-attached-units): models that began as one attached unit remain one rules unit for the rule’s stated duration. | — | APP-AUTHORITY |
| 9 | P05A | C05-01 | A destroying attack can remove a model, emit destruction, and resolve mandatory or optional destruction reactions before the attacking unit finishes all attacks. | Retain a logically destroyed, non-targetable model only when a destruction-triggered rule applies; finish every attack from the attacking rules unit, then resolve queued triggers and removal. | [05.04.04 Destroyed](https://www.40k.app/rules/05-attack-sequence): destruction-triggered rules wait until the attacking unit has completed its attacks. | P19 | APP-AUTHORITY |
| 10 | P18C | C18-03 | Emergency Disembark placement is requested before hazard rolls and mortal-wound casualties. | Snapshot cargo, resolve hazard rolls/casualties first, then request placement only for survivors. | [18.05 Emergency Disembark](https://www.40k.app/rules/18-transports): make the hazard rolls before moving surviving models. | P05A, P06B | APP-AUTHORITY |
| 11 | P24D | C24-04 | Hazardous pools are deduplicated by profile ID and exactly one hazard roll is made. | Count selected physical Hazardous weapon instances and roll once per selected weapon after all of the unit’s attacks, preserving Shooting/Fight origin. | [24.15 Hazardous](https://www.40k.app/rules/24-core-abilities): roll once for each selected Hazardous weapon after the unit finishes its attacks. | P05A, P06B | APP-AUTHORITY |
| 12 | P14 | C14-01 | Objective consumers duplicate point-marker geometry and do not share terrain-area objective geometry. | Provide one model-group-aware objective geometry query covering markers and mission terrain objectives; make existing Objective Control its first consumer. | [14.01 and 14.01.01](https://www.40k.app/rules/14-objectives): measure base/hull to the closest part of the objective, subject to its vertical limit. | — | APP-AUTHORITY |
| 13 | P12 | C12-01, C12-02 | Objective Consolidation receives only point markers, measures centre-to-centre in 2D, checks only final unit range, and retains a July source phrase absent from current App wording. | Consume P14 geometry for markers and terrain objectives; each moved model ends within range if possible or otherwise closer, and the final rules unit ends in range; remove/narrow the stale phrase. | [12.08 Objective Consolidation](https://www.40k.app/rules/12-fight-phase) with [14.01.01](https://www.40k.app/rules/14-objectives): per-model closest-part geometry, 5″ vertical limit, and final unit requirement. | P14 | APP-DRIFT |
| 14 | P22 | C22-01 | Generic Aura resolution excludes the source unless each descriptor opts in and can apply the same Aura more than once through overlapping models. | Include a model in its own Aura by default and apply the same Aura to a target once, unless source-backed wording expressly excludes self-application. | [22.01 Aura Abilities](https://www.40k.app/rules/22-other-rules-and-abilities): a model is within its own Aura and duplicate applications do not accumulate. | — | APP-AUTHORITY |
| 15 | P24C1 | C24-03A | Duplicate non-Anti weapon abilities are rejected; distinct source instances are not preserved. | Preserve stable source identity for every duplicate core/weapon ability instance without yet adding the player-facing selection. | [24.02 Duplicated Abilities](https://www.40k.app/rules/24-core-abilities): duplicate abilities do not accumulate and the controlling player chooses which instance applies. | — | APP-AUTHORITY |
| 16 | P01 | C01-01 | Battle-shock collection skips rules units with no placed model and tests only below Half-strength. | Extend P08B’s predicate to embarked and Strategic Reserve rules units: currently Battle-shocked or at/below Half-strength. | [01.02.04 Not On the Battlefield](https://www.40k.app/rules/01-core-concepts): off-battlefield units retain their Command-phase Battle-shock obligations. | P08B | APP-AUTHORITY |
| 17 | P02A | C02-01 | The modifier service supports set, multiply, add, floor, and ceiling with integer operands, but not the complete ordered algebra. | Implement exact replacement → multiplication → addition → division → subtraction ordering, one final round-up, and terminal `0`, `-`, and `*` replacement values. | [02.02.01 Modifiers](https://www.40k.app/rules/02-datasheets): apply the listed operation groups in order and round remaining fractions only at the end. | — | APP-AUTHORITY |
| 18 | P02B | C02-02 | Modified dice results can remain below 1, and raw, modified, and domain-limited values are not distinct. | Separate raw roll, post-reroll result, modifier trace, minimum-1 modified result, and any later rule-specific domain result. | [02.02.01 Modifiers](https://www.40k.app/rules/02-datasheets): after ordinary modifiers, a modified dice result below 1 becomes 1. | P02A | APP-AUTHORITY |
| 19 | P02C | C02-03 | Detection Range permits 0, has no upper bound, and Lone Operative range handling does not share one terminal clamp. | Clamp Detection Range and Lone Operative ranges to 9″–30″ after modifiers in the owning modifier service. | [02.02.01 Modifiers](https://www.40k.app/rules/02-datasheets): these ranges have the stated terminal 9″ minimum and 30″ maximum. | P02A | APP-AUTHORITY |
| 20 | P10 | C10-01, C10-02 | Unseen Indirect attacks add an obsolete `-1` to hit, newer restrictions are partial, and selecting Indirect removes non-Indirect weapons. | Remove the extra `-1`; apply Cover, reroll prohibition, and unmodified failure ranges per attack while retaining ordinary weapons against visible eligible targets. | [10.07 Indirect Shooting](https://www.40k.app/rules/10-shooting-phase): unseen Indirect attacks grant Cover, cannot reroll hits, normally fail on unmodified 1–5, or 1–3 when stationary with a friendly observer; its designer note permits mixed declarations. | P02B, P06A, P09A | APP-AUTHORITY |
| 21 | P24A | C24-01 | Stealth applies `-1` to hit and activates if any attached component has it; stale wording is duplicated in generated data. | Require every living model in the rules unit to have Stealth and grant Benefit of Cover instead of a hit modifier; regenerate every in-scope record. | [24.33 Stealth](https://www.40k.app/rules/24-core-abilities): the whole target unit must have Stealth and receives Benefit of Cover. | P10 | APP-AUTHORITY |
| 22 | P15A | C15-01 | Smokescreen triggers after target selection, grants Cover plus `-1` to hit, and affects only the selected Smoke unit. | Offer it at the start of the opponent’s Shooting phase; grant Benefit of Cover to the Smoke unit and to a target obscured by its Smoke models, without `-1` to hit. | [15.10 Smokescreen](https://www.40k.app/rules/15-stratagems): start-of-opponent-Shooting timing and the stated Smoke-obscuration Cover effect last until phase end. | P15D, P06A, P10 | APP-AUTHORITY |
| 23 | P15B | C15-02 | Explosives is a start-phase, GRENADES-only unit action with no selected source model. | During the owner’s Shooting phase, select an unengaged, eligible-to-shoot, non-Advanced `EXPLOSIVES/GRENADES` unit, a matching model, and a visible unengaged enemy within 8″ of that model. | [15.06 Explosives](https://www.40k.app/rules/15-stratagems): the current App heading and complete model/target eligibility statement control. | P15D, P06A, P06B, P10 | APP-AUTHORITY |
| 24 | P11A | C11-01 | Charge modifiers are embedded in the dice expression, one ambiguous value drives reachability, and the movement resolver rejects maxima outside 2–12. | Represent raw 2D6, the post-reroll modified Charge result, and the Charge Move budget separately. Raw 2D6 cannot exceed 12; modifiers applied after the roll may make the modified result exceed 12. Apply any distinct Charge Move modifier/cap only to the movement budget. | [02.02.01](https://www.40k.app/rules/02-datasheets) and [11.02/11.04](https://www.40k.app/rules/11-charge-phase): roll 2D6, then apply modifiers under the normal modifier sequence; the dice maximum is not a blanket post-modifier cap. | P02A, P02B | APP-AUTHORITY |
| 25 | P15E | C11-02, C15-05 | Ordinary Charges and Heroic Intervention mark Command Re-roll unavailable. | After the Charge roll, offer Command Re-roll through the normal CP/decision path and reroll the complete 2D6 before modifiers. | [15.02 Command Re-roll](https://www.40k.app/rules/15-stratagems): the entire Charge roll is an eligible reroll. | P15D, P11A | APP-AUTHORITY |
| 26 | P15C | C15-03 | Heroic Intervention rolls bare 2D6 and caps that unmodified total at 6. | Use the ordinary Charge declaration, reroll, modifier, target, eligibility, and `PathWitness` pipeline; for Into the Fray apply its result cap after modifiers. | [15.11 Heroic Intervention](https://www.40k.app/rules/15-stratagems): Leap to Defend/Into the Fray use the stated Charge process and restrictions. | P15D, P11A, P15E | APP-AUTHORITY |
| 27 | P21A | C21-01 | FLY automatically grants model/terrain transit for ordinary movement and Charges without selecting Take to the Skies. | Before each Normal, Advance, Fall Back, or Charge move, offer Take to the Skies; only selection grants transit/ignored vertical distance and reduces the maximum by 2″ unless Hover applies. | [21.03 Flying Models](https://www.40k.app/rules/21-flying-and-surging): Take to the Skies is a per-move choice with the stated transit, vertical-distance, reduction, and Hover rules. | P09A, P11A | APP-AUTHORITY |
| 28 | P21B | C21-02 | Surge has no target and omits closest-target ties, target-only Engagement, maximum approach, and the complete movement lock. | Choose the closest enemy, use a finite tie decision, require Engagement with that target if possible or maximum approach otherwise, forbid Engagement with others, and lock further movement that phase. | [21.02 Surge Move](https://www.40k.app/rules/21-flying-and-surging): closest-target, tie, maximal movement, Engagement, and phase-lock requirements. | P21A | APP-AUTHORITY |
| 29 | P24E | C24-05 | Generic MOBILE geometry exists, but Super-Heavy Walker has no descriptor, movement behavior, choice, or post-move roll. | For Normal/Advance/Fall Back moves, allow transit through non-Titanic models and terrain sections at most 4″ high; offer the all-model MOBILE choice and apply Battle-shock on a post-move D6 roll of 1. | [24.35 Super-Heavy Walker](https://www.40k.app/rules/24-core-abilities): the stated transit and optional MOBILE/Battle-shock behavior. | P21A | APP-AUTHORITY |
| 30 | P03A | C03-01 | Every deployment model must be wholly within its deployment zone, with no oversized-base fallback. | After proving the base cannot fit, require contact with the player’s battlefield edge and impose the same-turn Normal/Advance/Fall Back/Charge/ranged-attack lock. | [03.02.02 Set Up](https://www.40k.app/rules/03-moving): oversized deployment uses edge contact and the stated same-turn restrictions. | — | APP-AUTHORITY |
| 31 | P03B | C03-02 | Every disembarking model must be wholly within the ordinary 3″/6″ distance. | Only after proving ordinary placement impossible, allow an oversized base within 1″ of the Transport base/hull and outside Engagement Range. | [03.02.02 Set Up](https://www.40k.app/rules/03-moving): the 1″ oversized-base exception applies to disembark placement after ordinary placement is impossible. | P03A | APP-AUTHORITY |
| 32 | P04 | C04-01 | After a selected-target reaction, shooting resumes the stored declaration without revalidation or replacement targets. | Revalidate after target-changing reactions and issue a deterministic retarget request only for weapons whose original target is no longer eligible/viable. | [04.03.03 Target No Longer Eligible](https://www.40k.app/rules/04-making-attacks): affected attacks may select replacement eligible targets after the original target becomes ineligible. | — | APP-AUTHORITY |
| 33 | P24C2 | C24-03B | Only duplicate Anti instances have a player-selection path; other duplicate ability instances cannot be selected through adapters. | Add the controlling-player finite instance decision, validation, replay, and viewer-safe projection; weapon choices occur each time the unit attacks during Select Weapons. | [24.02 Duplicated Abilities](https://www.40k.app/rules/24-core-abilities): duplicate abilities do not accumulate and the controlling player selects the active instance. | P24C1, P04 | APP-AUTHORITY |
| 34 | P05B | C05-02 | A model is recorded removed and emits `model_destroyed`, then is reconstructed and restored if Fight On Death is accepted. | At the P05A boundary, transition atomically from pending destruction to retained Fight On Death without battlefield removal or remove/re-add replay; preserve one-unit activation, fixed bases, cleanup, and living-only authority. | [05.04.05 Fight On Death](https://www.40k.app/rules/05-attack-sequence): do not remove a model while it is retained to fight. | P05A | APP-AUTHORITY |
| 35 | P05C | C05-03 | Authenticated former placements exist, but no generic query can measure to a destroyed model or destroyed unit. | Add source-authorized measurement using the exact former base/hull; a destroyed-unit reference resolves to the last model destroyed and grants no living battlefield authority. | [05.04.06](https://www.40k.app/rules/05-attack-sequence): use the destroyed model’s former footprint, and the last destroyed model for a destroyed-unit reference. | P05B | APP-AUTHORITY |
| 36 | P18A | C18-01 | An empty Dedicated Transport receives a delayed unavailable/setup consequence associated with battle round 1. | At the end of Declare Battle Formations, immediately destroy/remove every empty Dedicated Transport without triggering destroyed-model rules. | [18.01 Transport Capacity](https://www.40k.app/rules/18-transports): empty Dedicated Transports are destroyed at the stated formation boundary without destruction triggers. | — | APP-AUTHORITY |
| 37 | P18B | C18-02 | Emergency Disembark accepts an arbitrary subset, destroys omitted models without proof, and rejects engaged endpoints even when no unengaged placement exists. | Place the maximum possible survivors wholly within 6″ and as close as possible; prefer unengaged placements, allow an engaged endpoint only when no unengaged endpoint exists, and destroy only genuinely unplaceable models. | [18.05 Emergency Disembark](https://www.40k.app/rules/18-transports): maximal placement, closest-possible positioning, unengaged preference, engaged fallback, and casualty rules. | P03B, P18C | APP-AUTHORITY |
| 38 | P20 | C20-01 | Reserve ingress rejects a Strategic Reserve Transport containing cargo as unsupported. | Select and ingress the Transport as one reserve unit while cargo remains embarked; count cargo toward reserve limits but do not make it independently eligible for ingress. | [20.01 and 20.04 Strategic Reserves](https://www.40k.app/rules/20-strategic-reserves): an embarked unit accompanies its reserve Transport and is not selected separately. | P09A, T-TRANSPORT | APP-AUTHORITY |
| 39 | P24B | C24-02 | Firing Deck marks only contributing passenger units and stores the restriction in phase-local `shot_unit_ids`. | Snapshot every unit embarked when Firing Deck resolves and make all of them ineligible to shoot until turn end, including after disembarking. | [24.14 Firing Deck](https://www.40k.app/rules/24-core-abilities): every unit embarked at resolution is subject to the turn-long shooting restriction. | T-TRANSPORT | APP-AUTHORITY |
| 40 | P23 | C23-01 | Aircraft make ordinary moves and enter reserves by crossing a battlefield edge. | Start Aircraft in Strategic Reserves, permit only ingress moves, and return every Aircraft still on the battlefield to Strategic Reserves at the end of its opponent’s turn. | [23.01–23.02 Aircraft](https://www.40k.app/rules/23-aircraft): reserve start, ingress-only movement, and opponent-turn-end return. | P20, P21A | APP-AUTHORITY |
| 41 | P25A | C25-01, C25-02 | Incursion permits 4 Enhancements, ordinary duplicates of 3, Battleline duplicates of 6, and does not independently double Dedicated Transport limits. | Enforce Incursion at 1000 points, 2 DP, 2 Enhancements, ordinary limit 2, and independent Battleline/Dedicated Transport limit 4. | [25.03 Select Battle Size](https://www.40k.app/rules/25-muster-armies): the current Incursion table and duplicate exceptions. | — | APP-AUTHORITY |
| 42 | P25B | C25-03 | Warlord and Enhancement selections carry unit IDs, and `WARLORD` is applied to the whole unit. | Select/persist a specific Character model as Warlord and a specific eligible model as Enhancement bearer; derive unit keywords from membership without changing ownership. | [25.04 Fill Your Army Roster](https://www.40k.app/rules/25-muster-armies): Warlord and Enhancement bearer selections are model-specific. | — | APP-AUTHORITY |
| 43 | P25C | C25-04 | `DetachmentDefinition` cannot express generic required/prohibited units or required/prohibited other detachments. | Add typed source-neutral constraints and fail-closed roster validation, including duplicate-detachment prohibition; do not populate or evaluate faction-specific records here. | [25.04 Fill Your Army Roster](https://www.40k.app/rules/25-muster-armies): apply the stated unit/detachment requirements and prohibitions. | — | APP-AUTHORITY |
| 44 | PFINAL | CAUDIT-01 | No post-remediation artifact certifies the complete Core Rules implementation against one selected maintained-App snapshot, and categories 07, 13, 16, and 17 have no standalone implementation PR. | Re-audit all 25 categories after every implementation PR is merged; verify exact source-row fingerprints, semantic execution, engine/adapters/replay/visibility coverage, and cross-category dependencies. If any new gap appears, assign a canonical finding ID and insert its one-at-a-time remediation PR before PFINAL; PFINAL cannot open or certify until those inserted PRs merge and the full audit is clean. | All category 01–25 locators and the exact operative source rows/fingerprints retained by P15D through P25C, against one explicitly selected maintained-App snapshot. | P25C | FINAL-CERTIFICATION |

Categories 07, 13, 16, and 17 have no standalone remediation PR in this
sequence. Category 13’s current Light/Dense Hidden wording is governed by the
maintained App mirror and supersedes the older PDF’s Dense-only wording; it is
immediately usable without separate confirmation. PFINAL re-audits all four as
part of the complete 25-category gate. If that audit finds a gameplay gap, the
gap receives a canonical finding ID and a new one-at-a-time remediation PR
inserted before PFINAL.

## Exception-only user disambiguation workflow

Routine confirmation against the official Warhammer 40,000 App is not required.
The owner-approved 40k.app snapshot controls source selection, and the exact
source row pinned in each implementation PR controls that semantic change,
unless one of these exceptions is actually encountered:

1. The user observes that the official App and 40k.app differ.
2. The 40k.app text needed by a finding is incomplete or genuinely ambiguous.
3. Two maintained App statements are internally inconsistent and stable title
   plus complete operative text cannot resolve them.
4. More than one App version could govern because a tournament or project
   cutoff has not been selected.
5. The repository owner withdraws or narrows the source-authority policy.

Only the affected PR pauses. Ask the user one narrow question quoting or
paraphrasing the conflicting statements and identifying the affected finding.
If direct official-App evidence is needed to resolve the exception, record:

- platform/OS, App version/build, locale, timestamp, and timezone;
- the complete rule heading, operative text, notes, examples, and expanded
  sections needed for the disputed point;
- original capture hashes and an exact transcription hash when capture bytes
  are retained;
- the affected stable finding/source IDs, selected target version, resolution,
  and exact supersession scope.

Resolution rules:

- Current maintained App wording supersedes older PDFs and stale repository
  transcriptions.
- 40k.app numbering is provider-local metadata; stable project identity binds
  to rule title and complete operative text.
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
- For Charge, no routine question remains: raw 2D6 is at most 12, then Charge
  modifiers apply and may produce a modified result above 12. A distinct rule
  modifying or capping the Charge Move applies to the movement budget, not
  retroactively to the dice.

## Required contents of every implementation remediation PR

Each PR description and its checked-in finding update must itemize:

```text
Status:
Finding IDs:
Dependencies and evidence gate:
Violated invariant:
How it is currently done:
How it should be done:
Specific authoritative 40k.app rule/statement and source ID:
40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
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
2. Pin the controlling 40k.app operative statement, stable source ID, URL,
   observation timestamp, transcription SHA-256, and retained source-observation fingerprint.
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

### P08A — C08-03

Status: Implementation and validation complete; PR publication is pending.

Finding IDs: `C08-03`.

Dependencies and evidence gate: P00/PR #405 and P15D/PR #406 are merged. The maintained-App
sequence is complete and unambiguous, so `APP-AUTHORITY` is satisfied and no
`EXCEPTION-PAUSE` applies.

Violated invariant: Every rule triggered at the start of the Command phase, including every
engine-owned player choice, must resolve at one deterministic, resumable boundary before Gain Core
CP. The engine alone owns that ordering, decision validation, CP mutation, event emission, replay,
and adapter-visible continuation.

How it is currently done: `BattleRoundFlow` dispatches the generic `START_PHASE` window before
entering `CommandPhaseHandler`, but the handler grants both Core CP gains and emits
`command_step_started` before its Command-specific start registry runs synchronous hooks, status
effects, and finite faction-rule choices. A pending Command-start choice therefore observes both CP
totals already increased and resumes after the source-defined start-of-Command boundary has passed.

How it should be done: Keep generic `START_PHASE` as the outer lifecycle boundary. Inside the
Command handler, preserve the existing pre-P08B active-player Battle-shock clear at its current
position, retain the cleared unit IDs across any pause, run the Command-start registry's synchronous
pass exactly once, then its resumable effect pass and finite-choice pass. If any nested or finite
decision remains pending, return without granting Core CP. After each accepted
`GameLifecycle.submit_decision(...)`, auto-advance to the next Command-start request or to boundary
completion. Final completion grants each player 1CP exactly once and then emits
`command_step_started`, including the retained clear IDs. Only scoring, Battle-shock, and later
Command work follow that event. P08A moves Core CP; it deliberately does not move or correct the
P08B-owned clear.

Specific authoritative 40k.app rule/statement and source ID: The pinned authoritative 40k.app
category-08 audit and retained official Core Rules PDF establish `START OF COMMAND PHASE` immediately
before `GAIN CORE CP`, represented by `gw-11e-core-rules:command-phase:start-of-command-phase` and
`gw-11e-core-rules:command-phase:gain-core-cp`. The PDF supplies the exact corresponding 08.01
statement, “Rules that are triggered at the start of the Command phase are resolved now,” and 08.02
statement, “Both players gain 1 Command Point (CP).” A current search-indexed `/rules` result also
showed those headings in that order, but it is retained only as contextual corroboration and is not
classified as an authoritative direct 40k.app observation.

40k.app URL, observation timestamp, transcription SHA-256, and source-observation fingerprint:
`https://www.40k.app/rules/08-command-phase`; the retained category audit was observed
`2026-08-25T00:00:00-04:00` with source-observation SHA-256
`0920fa00c1f4ecbc9e46795c1d72695872b61e7577eeaa693c57eb12c26c871e` and evidence SHA-256
`cd6e35d6f3f22047e79b34ae45a2496f3616b42fc300ea85498b89b949aa664b`. A search-indexed result for
`https://www.40k.app/rules`, project-observed `2026-08-26T14:49:10-04:00`, exposed the Start of
Command Phase → Gain Core CP heading sequence as secondary context. Direct category access returned
a security checkpoint, so no category-body text or authoritative 2026-08-26 provider crawl is
claimed. The retained official Core Rules PDF supplying the exact 08.01/08.02 operative text has
SHA-256
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`. The committed source
artifact has SHA-256 `d1e61f74c91fa73cda51a470b570c6cf8e14ffa67b6d46cd6b6fe405cb3e7709`
and package hash `b29a141391d20acc559e9a19dc08fba5c126d29f451726ea81262e4f8591d4e4`.

- Start of Command Phase: reviewed section-heading transcription
  `c7076d22487eaacd4966ce616ed23632f73c1c1e77e97264779f58571855cd33`; official-PDF operative-text
  transcription `539a37c85bcb22ebe08ae017a6e926489bbc8b311680d80514d5151855ed1c31`; observation
  `9b60e2a9afadea0cf9418cc38175079ebd510e42362bb92c527eaa9c6d4aa18b`.
- Gain Core CP: reviewed section-heading transcription
  `15b5a4c0e0184c03730be6b15d9aad113b1b59bb262028d00173ea5475f7a42f`; official-PDF operative-text
  transcription `6a09ea8b545e04dfbb0755408986862f7cf19991bb023106cafcbbb63b8e55d0`; observation
  `8b7093cccc1d0bbeba477a60449243535b5832eabda56c3a4102acf092956a48`.

Load and execution support: Both source rows are `loaded` and
`executable_engine_runtime`. Their evidence maps the stable IDs to the Command-start boundary and
Core CP step, and the Core CP ledger transaction carries the Gain Core CP source ID; support status
does not infer any P08B Battle-shock semantics.

Scope and explicit exclusions: The Command-phase ordering owner, resumable `CommandStepState`
synchronous-progress and boundary-complete markers, retained pre-P08B clear IDs and replay payload,
exact 08.01/08.02 source/evidence artifact, existing decision/faction/effect regressions, static
ownership audit, generated build identity/contracts, and timing documentation only. P08B remains
excluded: the current automatic Battle-shock clearing and required-test candidate logic are preserved
exactly rather than corrected or represented as compliant here. No Command-start rule semantics,
faction content, option family, proposal kind, movement, geometry, UI, network, headless, or AI
behavior is added.

Owning state/validation/mutation/event/replay path: `BattleRoundFlow` generic `START_PHASE` dispatch
→ `CommandPhaseHandler` canonical Command-start boundary → preserved pre-P08B clear with retained IDs
→ `CommandStepState` one-time synchronous-progress marker → `CommandPhaseStartHookRegistry`
synchronous/effect/finite-choice passes → serialized boundary-complete marker → existing
`DecisionRequest → DecisionResult → GameLifecycle.submit_decision(...)` validation and automatic
resume → engine-owned `CommandPointLedger` Core CP transactions → two `command_points_gained` events
→ `command_step_started` → serialized game state, event log, replay, adapter projection, and event
delta. No adapter owns validation or mutation.

Decision and viewer-visibility impact: The existing
`select_faction_rule_command_phase_start_option` decision type, deterministic option IDs, payload
shape, stale/drift validation, queue behavior, record shape, and public viewer visibility remain
unchanged. The timing changes: while a choice is pending, every viewer sees the same unchanged public
CP totals; after acceptance and automatic resume, the public selection event precedes both public Core
CP gains and `command_step_started`. No hidden-information type or redaction set is added.

Regression scenarios and same-bug-class search: The pre-fix Space Marines Oath of Moment lifecycle
regression proved both CP totals had already increased while its finite request was pending, and the
Leagues of Votann regression proved its synchronous resolution event followed Core CP. Coverage now
pins pending-choice pause/resume, distinct serialized synchronous-progress and boundary-complete
state, event ordering across both CP gains, `command_step_started`, JSON-safe state round-trip, replay
reproduction, both-viewer projection/event deltas, synchronous Votann resolution, and the Fulgrim
poisoned-status effect consumer, including its nested per-wound Feel No Pain decisions across a
serialized pause. It also carries a pre-existing Battle-shocked active-player unit across a paused
Oath request, proving the P08B-owned clear timing remains unchanged and its cleared ID is retained for
the later event. The existing More Dakka lifecycle regression now follows the real intervening Waaagh
choice before asserting the post-boundary CP total. A repository-wide registry/CP-order search found
the same bug class across synchronous, effect, and finite-choice passes; one AST audit now requires
all three passes and the sole Core CP step to remain in the one pre-CP boundary.

Generated artifacts/documentation: Packaged
`core_command_phase_2026_08/artifacts/package.json`, typed fail-closed loader, offline source/hash
builder and documented check command, engine build manifest, affected external contract fixtures,
`ARCHITECTURE_V2.md`, `docs/ADAPTER_DECISION_CONTRACT.md`,
`docs/DECISION_SUBMISSION_CATALOG.md`, and this finding update.

Validation results:

- The focused pre-fix Oath of Moment and Leagues of Votann regressions failed on the old order and
  passed after the canonical boundary change; focused Command-step state and Fulgrim effect-consumer
  coverage, including the nested per-wound Feel No Pain pause, is included in the P08A validation
  set. The five targeted full-suite regression corrections pass together (`5 passed`).
- Every required `AGENTS.md` gate passed: Ruff check, Ruff format check, mypy (`2594` source files),
  Pyright, the coverage-enabled xdist work-stealing suite (`6101 passed`), four-shard inventory,
  import-linter (`11` contracts kept), and all-files pre-commit.
- The Command-phase source builder, engine-build identity, external-contract base-ref check,
  40k.app audit check, and installed-wheel smoke passed. The installed wheel exposed `2424` engine
  resources and `27` schemas and validated all six request families.
- TypeScript generated/type/unit/conformance checks passed (`5` unit tests and `342` conformance
  assertions). This host exposes the required Node 24 binary but no `npm` executable, so the
  repository-pinned direct equivalents (`check-generated`, `tsc --noEmit`, `tsx --test`, and
  `tsx src/main.ts`) were run instead of the unavailable `npm` wrappers.

PR URL and merge commit: pending publication; merge commit pending review and merge.

PFINAL is an audit/certification PR rather than a gameplay-remediation PR. After
P25C and every preceding implementation PR merge, prepare a fresh audit of all
25 categories before opening PFINAL. The audit must select one maintained-App
snapshot, verify every exact operative source row and fingerprint, revisit
every implementation finding and `REVALIDATE` category, and perform the final
cross-category dependency/regression audit. If it discovers any gap, do not
open or certify PFINAL: assign a canonical finding ID, insert its scoped PR
before PFINAL, merge all such PRs one at a time, and repeat the complete audit
from current `main`. PFINAL may open only with a clean audit and must commit the
final audit artifact, generated report, validation results, snapshot identity,
and the evidence supporting `CAUDIT-01` closure.

## Definition of full Core Rules compliance

The project may claim only:

> CORE V2 Core Rules categories 01–25 compliant with the maintained Games
> Workshop App state represented by owner-authoritative 40k.app snapshot X,
> observed on Y, with non-affiliated provider provenance preserved.

That claim requires:

- all 43 implementation remediation PRs and PFINAL merged, plus every
  additional remediation PR inserted by the PFINAL fail-closed audit;
- every governing 40k.app operative statement, stable source ID, URL,
  observation timestamp, transcription SHA-256, and retained source-observation fingerprint
  pinned in the source/finding record;
- no unresolved `EXCEPTION-PAUSE`, source drift, internal App inconsistency, or
  partially executed/unsupported in-scope Core Rules semantic;
- all 25 categories re-audited against the selected maintained App snapshot, including
  `REVALIDATE` categories 07, 13, 16, and 17;
- every closed finding covered through engine, adapter, replay, determinism,
  and visibility layers where applicable;
- support reporting still distinguishes loaded source data from certified
  semantic execution;
- all required validation passing on final `main`; and
- PFINAL's committed cross-category dependency and regression audit finding no
  new gaps and closing `CAUDIT-01`.

The claim continues to exclude faction, faction-detachment, faction-datasheet,
and every other scope prohibited by `AGENTS.md`.

## Exception decisions to record only if encountered

There are no routine source confirmations during the current 44-PR sequence.
Record a user decision only when implementation encounters one of these
concrete exceptions:

1. The actual official App visibly differs from the pinned 40k.app statement.
2. The maintained mirror omits text required to decide the implementation.
3. Stable title plus complete operative text cannot resolve an internal App
   inconsistency.
4. A tournament/project version cutoff would select a different App state.
5. The repository owner withdraws or narrows the source-authority policy.

The default `T-TRANSPORT` milestone remains P18A+P18C+P18B. P15D is the
source-first P00 successor and remains one source-only APP-INTERNAL-DRIFT PR;
P12 remains one atomic APP-DRIFT PR immediately after P14. The numbered
one-PR-at-a-time order is fixed except for fail-closed insertion of newly found
remediation PRs before PFINAL, or unless the user explicitly revises the
roadmap.
