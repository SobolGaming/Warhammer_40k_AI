# Core Rules 40k.app Comparison Evidence

This report is generated from the checked-in offline audit artifact. By explicit repository-owner policy, 40k.app is treated as a verbatim authoritative mirror of the maintained Warhammer 40,000 App for Core Rules. The site remains a non-affiliated hosting provider and is never queried by the runtime engine.

Faction review is explicitly excluded, including faction detachments and faction datasheet content.

## Authority boundary

- Official anchor: `docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf` (`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`).
- Maintained App wording, represented by the project-authoritative 40k.app mirror, supersedes older PDF wording where they differ.
- Direct user observation of an actual App/40k.app divergence opens a conflict and requires the exception workflow in `docs/CORE_RULES_SOURCE_POLICY.md`.
- Source-observation hashes exclude implementation status and PR planning; full row hashes detect any checked-in review change. Neither authenticates the external website.

## Category inventory

| Category | Provider locator | Provider comparison | Implementation evaluation | Planned PRs |
|---|---|---|---|---|
| 01 Core Concepts | [01.00](https://www.40k.app/rules/01-core-concepts) | authoritative_app_mirror | assessed_remediation_planned | P01 |
| 02 Datasheets | [02.00](https://www.40k.app/rules/02-datasheets) | authoritative_app_mirror | assessed_remediation_planned | P02A, P02B, P02C |
| 03 Moving | [03.00](https://www.40k.app/rules/03-moving) | authoritative_app_mirror | assessed_remediation_planned | P03A, P03B |
| 04 Making Attacks | [04.00](https://www.40k.app/rules/04-making-attacks) | authoritative_app_mirror | assessed_remediation_planned | P04 |
| 05 Attack Sequence | [05.00](https://www.40k.app/rules/05-attack-sequence) | authoritative_app_mirror | assessed_remediation_planned | P05A, P05B, P05C |
| 06 Other Concepts | [06.00](https://www.40k.app/rules/06-other-concepts) | authoritative_app_mirror | assessed_remediation_planned | P06A, P06B |
| 07 The Battle Round | [07.00](https://www.40k.app/rules/07-the-battle-round) | authoritative_app_mirror | assessed_no_standalone_remediation | PFINAL |
| 08 Command Phase | [08.00](https://www.40k.app/rules/08-command-phase) | authoritative_app_mirror | assessed_remediation_planned | P08A, P08B |
| 09 Movement Phase | [09.00](https://www.40k.app/rules/09-movement-phase) | authoritative_app_mirror | assessed_remediation_planned | P09A, P09B |
| 10 Shooting Phase | [10.00](https://www.40k.app/rules/10-shooting-phase) | authoritative_app_mirror | assessed_remediation_planned | P10 |
| 11 Charge Phase | [11.00](https://www.40k.app/rules/11-charge-phase) | authoritative_app_mirror | assessed_remediation_planned | P11A |
| 12 Fight Phase | [12.00](https://www.40k.app/rules/12-fight-phase) | authoritative_app_mirror_controls_repository_conflict | assessed_remediation_planned | P12 |
| 13 Terrain | [13.00](https://www.40k.app/rules/13-terrain) | authoritative_app_mirror_supersedes_pdf | assessed_no_standalone_remediation | PFINAL |
| 14 Objectives | [14.00](https://www.40k.app/rules/14-objectives) | authoritative_app_mirror | assessed_remediation_planned | P14 |
| 15 Stratagems | [15.00](https://www.40k.app/rules/15-stratagems) | authoritative_app_internal_numbering_drift | assessed_remediation_planned | P15A, P15B, P15C, P15D, P15E |
| 16 Actions | [16.00](https://www.40k.app/rules/16-actions) | authoritative_app_mirror | assessed_no_standalone_remediation | PFINAL |
| 17 Monsters And Vehicles | [17.00](https://www.40k.app/rules/17-monsters-and-vehicles) | authoritative_app_mirror | assessed_no_standalone_remediation | PFINAL |
| 18 Transports | [18.00](https://www.40k.app/rules/18-transports) | authoritative_app_mirror | assessed_remediation_planned | P18A, P18B, P18C |
| 19 Attached Units | [19.00](https://www.40k.app/rules/19-attached-units) | authoritative_app_mirror | assessed_remediation_planned | P19 |
| 20 Strategic Reserves | [20.00](https://www.40k.app/rules/20-strategic-reserves) | authoritative_app_mirror | assessed_remediation_planned | P20 |
| 21 Flying and Surging | [21.00](https://www.40k.app/rules/21-flying-and-surging) | repository_transcription_not_observed_on_authoritative_app_mirror | assessed_remediation_planned | P21A, P21B |
| 22 Other Rules And Abilities | [22.00](https://www.40k.app/rules/22-other-rules-and-abilities) | authoritative_app_mirror | assessed_remediation_planned | P22 |
| 23 Aircraft | [23.00](https://www.40k.app/rules/23-aircraft) | authoritative_app_mirror | assessed_remediation_planned | P23 |
| 24 Core Abilities | [24.00](https://www.40k.app/rules/24-core-abilities) | repository_transcription_not_observed_on_authoritative_app_mirror | assessed_remediation_planned | P24A, P24B, P24C1, P24C2, P24D, P24E |
| 25 Muster Armies | [25.00](https://www.40k.app/rules/25-muster-armies) | authoritative_app_mirror | assessed_remediation_planned | P25A, P25B, P25C |

Implementation findings were assessed for every category. Their itemized current behavior, required behavior, exact App rule basis, dependencies, and one-PR-at-a-time sequence are retained in `docs/CORE_RULES_REMEDIATION_ROADMAP.md`. Source/provider findings below are tracked separately so corpus provenance does not imply gameplay execution.

## Source and provider findings

### 40k-app-numbering-05-03-02 - Category 05

- How it is currently recorded: The retained July transcription uses 05.03.02 for the post-roll attack-pool statement, while mirror display observations can omit the leading zeroes as 5.3.2.
- How it should be treated: Treat 5.3.2 as the current authoritative App display locator under the project source policy while preserving the stable project rule/source ID. Formatting differences in leading zeroes do not create a second rule.
- Specific rule/source basis: Authoritative App-mirror Attack Sequence category 05, stable source row gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:05.03.02-post-roll-attack-profiles, and policy core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26.
- Verification status: `authoritative_app_numbering`

### 40k-app-duplicate-09-07-01 - Category 09

- How it is currently recorded: The mirror and July artifact associate both the Desperate Escape definition and the forced Desperate Escape statement with locator 09.07.01.
- How it should be treated: Accept the duplicate 09.07.01 locators as current authoritative App corpus data, keep numbering separate from canonical project identity, and retain distinct definition and forced-test source-ID suffixes.
- Specific rule/source basis: Authoritative App-mirror Movement Phase 09.07.01 observations, the two stable July source rows ending desperate-escape-definition and forced-desperate-escape, and policy core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26.
- Verification status: `authoritative_app_numbering`

### july-transcription-conflict-12-08 - Category 12

- How it is currently recorded: The July artifact attributes an unengaged endpoint requirement to Objective Consolidation, but the current mirror observation does not substantiate treating that phrase as captured official wording.
- How it should be treated: The authoritative App-mirror 12.08 operative text controls. Keep the stale repository row conflict-blocked until P12 replaces or narrows it; implement the mode eligibility, per-model movement, and final unit-within-range requirements shown by the maintained App corpus.
- Specific rule/source basis: Authoritative App-mirror Fight Phase 12.08 at https://www.40k.app/rules/12-fight-phase versus gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:12.08-objective-consolidation, under policy core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26.
- Verification status: `authoritative_app_mirror_controls`

### hidden-unverified-source-13-09 - Category 13

- How it is currently recorded: The engine enables terrain-derived Hidden for Light or Dense terrain areas. The historical owner transcription is uncaptured and unverified on its own, while the separate 40k.app observation matches that wording and the older retained PDF records the narrower Dense-feature condition.
- How it should be treated: Keep the owner transcription unverified as historical provenance, classify the matching 40k.app row as the project-authoritative App mirror, and record the maintained App wording as superseding the older PDF for Hidden. The existing runtime path is executable against that authoritative wording.
- Specific rule/source basis: Authoritative App-mirror Terrain 13.09 at https://www.40k.app/rules/13-terrain; stable source row gw-11e-app-core-rules-hidden-transcription-observed-2026-08-09:rule:13.09-hidden; older official PDF SHA-256 f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833; and policy core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26.
- Verification status: `authoritative_app_mirror_controls`

### official-pdf-mirror-order-15-05-15-06 - Category 15

- How it is currently recorded: The mirror's Stratagem headings assign Crushing Impact to 15.05 and Explosives to 15.06, but its Fight Phase 12.01 example itself refers to Crushing Impact as 15.06. The retained official Core Rules PDF assigns Explosives to 15.05 and Crushing Impact to 15.06.
- How it should be treated: The maintained App corpus controls over the older PDF: use the App headings Crushing Impact 15.05 and Explosives 15.06 as current locators. Bind semantics by stable rule title and complete operative text, and retain the Fight example's stale 15.06 Crushing Impact cross-reference as an internal corpus anomaly rather than changing behavior identity.
- Specific rule/source basis: Authoritative App-mirror headings at https://www.40k.app/rules/15-stratagems, the stale Crushing Impact 15.06 cross-reference at https://www.40k.app/rules/12-fight-phase, older PDF SHA-256 f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833, and policy core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26.
- Verification status: `authoritative_app_text_controls`

### july-transcription-not-observed-fly-heavy - Category 21

- How it is currently recorded: The July artifact states an explicit FLY and HEAVY horizontal-distance clarification and previously labeled the 40k.app mirror as corroborating evidence. The current mirror pages describe FLY movement and HEAVY separately but do not expose that combined clarification.
- How it should be treated: Preserve the stable row as historical uncaptured provenance, but do not certify or implement the combined clarification because it is absent from the authoritative App mirror. Use the current Take to the Skies and HEAVY operative statements independently.
- Specific rule/source basis: Authoritative App-mirror https://www.40k.app/rules/21-flying-and-surging and https://www.40k.app/rules/24-core-abilities under policy core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26; neither observation displays the combined July statement.
- Verification status: `authoritative_app_mirror_controls`

### july-transcription-not-observed-mixed-hazard - Category 24

- How it is currently recorded: The July artifact states an explicit mixed-keyword Hazard clarification and previously labeled the 40k.app mirror as corroborating evidence. The current mirror pages expose the general Hazard rules but not that clarification.
- How it should be treated: Preserve the stable row as historical uncaptured provenance, but do not certify or implement that combined clarification because it is absent from the authoritative App mirror. Apply the current Hazard and mortal-wound operative statements as written.
- Specific rule/source basis: Authoritative App-mirror https://www.40k.app/rules/24-core-abilities and https://www.40k.app/rules/06-other-concepts under policy core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26; neither observation displays the combined July statement.
- Verification status: `authoritative_app_mirror_controls`

## P00 implementation boundary

The July App-core rows retain their stable package, document, rule, and source IDs. Each row is available only through a composed source package that requires both owner-transcription provenance and a separate App-mirror record. The mirror record carries the owner-approved source-policy ID without claiming Games Workshop owns the hosting site. Fight On Death remains partial runtime execution; stale or absent repository transcriptions remain uncertified. Category-13 Hidden matches the authoritative App mirror, whose maintained wording supersedes the older PDF under project policy. No gameplay semantics are changed by P00.
