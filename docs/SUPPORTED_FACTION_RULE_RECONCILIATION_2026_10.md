# Supported faction rule reconciliation — 30 October 2026

This bounded change repairs existing World Eaters Blessings and Icon consumers at
base `764b5321af2b05d6537861910dba0540abaa6d94`. It adds no faction, detachment,
battlefield layout or mission support. The [compact audit](../data/source_audits/supported_rules_2026_10/reconciliation.json)
records the source receipts, declaration inventory, selected comparisons and gaps.

The official download index was freshly checked on 30 October. World Eaters
Faction Pack v1.3, dated 30 September, is still the linked current PDF; the fresh
4,019,819-byte capture has SHA-256
`93e29f1b166d2a06fafa37a543890e56ae59c712b73b5a1e26f0a1c1ecf6a8e9`.
Its [official source](https://assets.warhammer-community.com/eng_30-09_wh40k_faction_pack_world_eaters-rxxj1fzeoh-kfx1cectxb.pdf)
matches the earlier retained capture. The July source package/hash remains
historical evidence; it has not been relabelled current.

The user subsequently clarified that [40k.app faction updates](https://www.40k.app/factions/updates)
mirror newer App data and take precedence when they disagree with a faction PDF.
The comparisons below establish agreement with the currently linked official PDF,
conditional on the preferred App-data comparison. They are not final latest-rules
qualification while that comparison is pending. The ordinary attached-unit engine
failure is independently reproduced; source access limits do not erase that defect.

## Selected PDF and consumer comparison

| PDF clause | Existing behavior and result |
|---|---|
| Unbridled Bloodlust, p7 | The existing +1 charge modifier matches the PDF. Canonical attached-unit IDs now reach that modifier without a physical-unit lookup failure. |
| Icon of Khorne, p8 | Existing one-point-per-enemy-unit, extra-D6 and point-spend semantics match the PDF. An attached Leader's kill now finds live Icons in the body's complete rules unit; multiple Icons still earn only one point. Event-time bearer death ordering is retained. |
| Maulerfiend, The Scent of Blood, p8 | Later generic RuleIR source `000002639:3` already implements the two nearby-enemy strength thresholds within 9 inches with mutually exclusive +1/+2 charge modifiers. No semantic change. This consumer is outside the older Phase17F declaration count. |

The official pack supplements a Codex. It does not contain the full underlying
Blessings recipe table. The existing other Blessings are exercised as regression
controls for the shared identity repair; their full current Codex wording is not
newly certified. The Disciple of Khorne FAQ does not turn its blocked enhancement
into supported gameplay.

## Reproduced defect and smallest complete repair

An ordinary canonical fixture musters a Leader and five bodyguards through
`AttachmentDeclaration`, producing `attached-unit:army-alpha:bodyguard`.
Adapter-submitted fight decisions reached the existing Rage-fuelled Invigoration
hook, which called a physical-only unit lookup and raised `GameLifecycleError`.
This occurred even with no active Blessing. The same lookup class also appeared
in charge and melee modifiers, target keyword checks, and Icon credit.

The existing faction owner now consumes shared `RulesUnitView` identity and
present components. Selection effects target the canonical group, Total Carnage
registers living group models, and Icon accounting checks all source components
while retaining its event-time live-bearer predicate. Formation identity remains
canonical after bodyguard casualties in the supported engine path. No speculative
historical fallback was added.

Existing test files cover native attached fight, native Blessings selection,
charge movement witnesses, Icon earn/spend, bearer deaths before/after the kill,
state restoration and exact replay. Canonical analytical profiles isolate the
consumer invariant; they do not certify an official fieldable army roster.
The adapter decision families and payload shapes are unchanged, so the existing
`ADAPTER_DECISION_CONTRACT.md` applies. Regenerated runtime and contract build
identities remain required.

## Inventory and remaining work

The older Phase17F surface declares 156 executable rows (133 generic IR and 23
named handlers) and 1,917 blocked rows (1,889 structured semantics and 28 approved
source gaps). The generated manifest separately records 131 implemented, 69
partial and 221 placeholder rows. World Eaters has one executable army-rule row,
68 structured-semantic blocked rows and one approved source gap on that surface.

Other generated component surfaces record 293 ability rows: 158 descriptor-only,
132 generic IR and three unsupported, despite all carrying the broader
engine-consumed stage. All 59 component datasheets retain partial faction
interaction status; 56 declare full abilities and three blocked abilities.
Eleven mustering declarations are separate. A later generic RuleIR surface has six
shards, 21 source packages and 92 records (Aeldari 42, Daemons 27, Chaos Space
Marines one, Emperor's Children 19, Thousand Sons one and World Eaters two).
World Eaters' second row is Maulerfiend Savage Exaltation `000002639:4`; current
Codex wording remains unqualified. Record presence does not independently prove
execution or current source currency. These overlapping counts must not be
added or interpreted as whole-game playability/current-source certification.

Murdermind's SUPPORT metadata and Butcher Lord's LEADER metadata remain blocked
gameplay entries. Grimnar's Mark has no current LEADER allowance or exact matching
existing execution subrule; no display-name alias was inferred. Of 59 component
datasheet labels, 58 have current MFM candidates. The remaining Vypers source
`000000605` is still VYPERS (1–2 models) in current Aeldari v1.4 PDF pages 20–21,
whereas current MFM uses singular `units-vyper`/`vyper`. This requires stable
source-ID reconciliation; no runtime alias was added. Label matches do not verify
profiles, weapons or semantics.

The prior five bounded clause checks retain their individual scope in
`data/source_audits/mfm_2026_10/bounded-rule-checks.json`. This slice does not
qualify the rest of the Phase17F entries, later component consumers, characteristics,
weapons, unreviewed Codex/book rules or non-executable World Eaters detachments.
Full source access and those discrepancies remain separate bounded follow-ups.

Implementation uses the accepted GPT-6 Astra High selection. The tool environment
does not independently attest runtime effort or expose the requested speed control.
No model performance advantage is asserted. Focused results are distinct from
the mandatory exact-head aggregate, review and hosted CI gates. The 64% full-package
branch-coverage floor, twelve-minute CI goal and 720-second shard cutoff are unchanged.
