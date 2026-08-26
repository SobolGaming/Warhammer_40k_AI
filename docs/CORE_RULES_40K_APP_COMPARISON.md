# Core Rules 40k.app Comparison Evidence

This report is generated from the checked-in offline audit artifact. 40k.app is a secondary, unofficial comparison source; it is not an official Games Workshop source and is never runtime catalog input.

Faction review is explicitly excluded, including faction detachments and faction datasheet content.

## Authority boundary

- Official anchor: `docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf` (`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`).
- Official GW artifacts and captured official-App evidence outrank mirror observations.
- A mirror conflict remains blocked until a pinned primary source resolves it.
- Observation hashes protect the committed review rows; they do not authenticate the external website.

## Category inventory

| Category | Provider locator | Provider comparison | Implementation evaluation |
|---|---|---|---|
| 01 Core Concepts | [01.00](https://www.40k.app/rules/01-core-concepts) | mirror_only | not_assessed_in_p00 |
| 02 Datasheets | [02.00](https://www.40k.app/rules/02-datasheets) | mirror_only | not_assessed_in_p00 |
| 03 Moving | [03.00](https://www.40k.app/rules/03-moving) | mirror_only | not_assessed_in_p00 |
| 04 Making Attacks | [04.00](https://www.40k.app/rules/04-making-attacks) | mirror_only | not_assessed_in_p00 |
| 05 Attack Sequence | [05.00](https://www.40k.app/rules/05-attack-sequence) | mirror_only | not_assessed_in_p00 |
| 06 Other Concepts | [06.00](https://www.40k.app/rules/06-other-concepts) | mirror_only | not_assessed_in_p00 |
| 07 The Battle Round | [07.00](https://www.40k.app/rules/07-the-battle-round) | mirror_only | not_assessed_in_p00 |
| 08 Command Phase | [08.00](https://www.40k.app/rules/08-command-phase) | mirror_only | not_assessed_in_p00 |
| 09 Movement Phase | [09.00](https://www.40k.app/rules/09-movement-phase) | mirror_only | not_assessed_in_p00 |
| 10 Shooting Phase | [10.00](https://www.40k.app/rules/10-shooting-phase) | mirror_only | not_assessed_in_p00 |
| 11 Charge Phase | [11.00](https://www.40k.app/rules/11-charge-phase) | mirror_only | not_assessed_in_p00 |
| 12 Fight Phase | [12.00](https://www.40k.app/rules/12-fight-phase) | conflict | not_assessed_in_p00 |
| 13 Terrain | [13.00](https://www.40k.app/rules/13-terrain) | mirror_only | not_assessed_in_p00 |
| 14 Objectives | [14.00](https://www.40k.app/rules/14-objectives) | mirror_only | not_assessed_in_p00 |
| 15 Stratagems | [15.00](https://www.40k.app/rules/15-stratagems) | conflict | not_assessed_in_p00 |
| 16 Actions | [16.00](https://www.40k.app/rules/16-actions) | mirror_only | not_assessed_in_p00 |
| 17 Monsters And Vehicles | [17.00](https://www.40k.app/rules/17-monsters-and-vehicles) | mirror_only | not_assessed_in_p00 |
| 18 Transports | [18.00](https://www.40k.app/rules/18-transports) | mirror_only | not_assessed_in_p00 |
| 19 Attached Units | [19.00](https://www.40k.app/rules/19-attached-units) | mirror_only | not_assessed_in_p00 |
| 20 Strategic Reserves | [20.00](https://www.40k.app/rules/20-strategic-reserves) | mirror_only | not_assessed_in_p00 |
| 21 Flying and Surging | [21.00](https://www.40k.app/rules/21-flying-and-surging) | transcription_not_observed | not_assessed_in_p00 |
| 22 Other Rules And Abilities | [22.00](https://www.40k.app/rules/22-other-rules-and-abilities) | mirror_only | not_assessed_in_p00 |
| 23 Aircraft | [23.00](https://www.40k.app/rules/23-aircraft) | mirror_only | not_assessed_in_p00 |
| 24 Core Abilities | [24.00](https://www.40k.app/rules/24-core-abilities) | transcription_not_observed | not_assessed_in_p00 |
| 25 Muster Armies | [25.00](https://www.40k.app/rules/25-muster-armies) | mirror_only | not_assessed_in_p00 |

## Source and provider findings

### 40k-app-numbering-05-03-02 - Category 05

- How it is currently recorded: The retained July transcription uses 05.03.02 for the post-roll attack-pool statement, while mirror display observations can omit the leading zeroes as 5.3.2.
- How it should be treated: Treat the mirror locator as provider-local display metadata and preserve the stable project rule ID until a captured official App source establishes current numbering.
- Specific rule/source basis: Attack Sequence provider category 05 and source row gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:05.03.02-post-roll-attack-profiles; no official App capture is retained.
- Verification status: `provider_local_only`

### 40k-app-duplicate-09-07-01 - Category 09

- How it is currently recorded: The mirror and July artifact associate both the Desperate Escape definition and the forced Desperate Escape statement with locator 09.07.01.
- How it should be treated: Keep provider numbering separate from canonical project identity; retain the distinct definition and forced-test source-ID suffixes.
- Specific rule/source basis: Movement Phase 09.07.01 observations and the two stable July source rows ending desperate-escape-definition and forced-desperate-escape.
- Verification status: `provider_local_only`

### july-transcription-conflict-12-08 - Category 12

- How it is currently recorded: The July artifact attributes an unengaged endpoint requirement to Objective Consolidation, but the current mirror observation does not substantiate treating that phrase as captured official wording.
- How it should be treated: Block source and semantic certification for this statement until a versioned, hashed official App capture resolves the wording.
- Specific rule/source basis: Fight Phase rule 12.08 at https://www.40k.app/rules/12-fight-phase versus gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:12.08-objective-consolidation.
- Verification status: `needs_official_app_capture`

### official-pdf-mirror-order-15-05-15-06 - Category 15

- How it is currently recorded: The mirror's Stratagem headings assign Crushing Impact to 15.05 and Explosives to 15.06, but its Fight Phase 12.01 example itself refers to Crushing Impact as 15.06. The retained official Core Rules PDF assigns Explosives to 15.05 and Crushing Impact to 15.06.
- How it should be treated: Use the retained official PDF for authoritative numbering. Treat the mirror's 15.05 Crushing Impact heading as an internally inconsistent provider-local locator, not as canonical project identity.
- Specific rule/source basis: Official Core Rules PDF SHA-256 f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833 at Stratagem entries 15.05 and 15.06; https://www.40k.app/rules/15-stratagems headings; and the Crushing Impact reference in the 12.01 example at https://www.40k.app/rules/12-fight-phase.
- Verification status: `official_pdf_controls`

### july-transcription-not-observed-fly-heavy - Category 21

- How it is currently recorded: The July artifact states an explicit FLY and HEAVY horizontal-distance clarification and previously labeled the 40k.app mirror as corroborating evidence. The current mirror pages describe FLY movement and HEAVY separately but do not expose that combined clarification.
- How it should be treated: Preserve the stable source row as an uncaptured repository transcription, but mark it not observed on the mirror and do not claim mirror corroboration until matching text or captured official App evidence is retained.
- Specific rule/source basis: The current https://www.40k.app/rules/21-flying-and-surging page describes ignoring vertical distance while taking to the skies, and https://www.40k.app/rules/24-core-abilities states the HEAVY movement condition; neither page displays the July row's explicit combined FAQ statement.
- Verification status: `needs_official_app_capture`

### july-transcription-not-observed-mixed-hazard - Category 24

- How it is currently recorded: The July artifact states an explicit mixed-keyword Hazard clarification and previously labeled the 40k.app mirror as corroborating evidence. The current mirror pages expose the general Hazard rules but not that clarification.
- How it should be treated: Preserve the stable source row as an uncaptured repository transcription, but mark it not observed on the mirror and do not claim mirror corroboration until matching text or captured official App evidence is retained.
- Specific rule/source basis: The current https://www.40k.app/rules/24-core-abilities page triggers hazard rolls and https://www.40k.app/rules/06-other-concepts distinguishes the damage result based on whether every model is MONSTER/VEHICLE; neither page displays the July row's explicit mixed-keyword FAQ statement.
- Verification status: `needs_official_app_capture`

## P00 implementation boundary

The July App-core rows retain their stable package, document, rule, and source IDs. Their separate evidence records now state that no official App version, build, URL, screenshot, or binary is retained. Fight On Death is recorded as partial runtime execution, and Objective Consolidation is blocked by a source conflict. No gameplay semantics are changed by P00.
