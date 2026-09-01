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
and Daemonic Incursion keyword checks all consume that view. Immutable
`component_unit_instance_ids` remain the lineage and replay identity surface; they are not a proxy
for current semantic or physical presence.

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
`warhammer40k-core-v2:runtime-tree-sha256-v1:067c680a617dbae85543d77c8558bf984a5625b9a99788a8ef9f4ef7683750ba`.

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
Daemonic Incursion keyword aggregation; and complete affected-file behavior. Static audit also
requires grouped Embark placement and every identified ability, keyword, reserve-authority, and
capacity consumer to use `living_components` instead of directly scanning immutable lineage. The
obsolete split-history and reserve-transfer modules are absent.

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
  the complete code-quality suite passes all `340` tests.
- Repository-wide Ruff check and Ruff format check pass; mypy passes across `2646` source files;
  Pyright reports `0 errors, 0 warnings`; all `11` import-linter contracts pass; the exact
  four-shard inventory check and all-files pre-commit gate pass.
- The required final xdist work-stealing suite passes (`6353 passed` in `491.84s`), including the
  complete code-quality suite.
- The Attached Units source artifact, final engine build identity, and regenerated external
  contract pass fail-closed checks, including the `origin/main` compatibility comparison.
- Installed-wheel smoke passes with `2476` packaged engine resources and `27` schemas. The host has
  no `npm` executable, so `npm ci` and npm wrapper commands could not run; the already locked
  dependencies were exercised directly with the bundled Node runtime. Generated-client drift,
  TypeScript type checks, and all `5` client unit tests pass, and the two-server HTTP conformance
  scenario passes all `342` assertions for contract version `11.1.0`.

PR URL and merge commit: `https://github.com/SobolGaming/Warhammer_40k_AI/pull/412`; merge commit
pending review and merge.

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
