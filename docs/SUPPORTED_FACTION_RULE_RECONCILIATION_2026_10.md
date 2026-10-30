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

The user clarified that [40k.app faction updates](https://www.40k.app/factions/updates)
mirror newer App data and take precedence when they disagree with a faction PDF.
40k.app is a non-affiliated mirror, not an official Games Workshop site. The
selected versioned pages below were verified in an ordinary background browser
on 30 October. Research-web retrieval returned HTTP 403; ordinary curl returned
HTTP 429 and was not retried. Browser content was readable without credentials,
special headers or bypass. No raw mirror HTML/JSON payload hash is claimed.

The inspected index lists v995 (16 October), v981 (14 October), v972 (2 October)
and v963 (30 September). The v995 delta concerns one Genestealer Cults unit,
outside this slice. The latest listed World Eaters, Aeldari, Chaos Daemons,
Chaos Space Marines and Thousand Sons faction changes are v963; Emperor's
Children's are v981. Absence of a later listed faction delta is an index-based
inference, not raw official API attestation or a complete faction audit.

## Selected preferred-mirror and consumer comparison

| Selected clause and source | Existing behavior and result |
|---|---|
| [Blessings of Khorne, v963, 30 September](https://www.40k.app/963/factions/world-eaters/army-rules) | Full table verified: eight D6, up to two blessings, each once per round, unused dice discarded, duration through round end. All six effect/recipe definitions match the existing implementation. Canonical attached-unit consumers are repaired. |
| [Icon of Khorne, v963, 30 September](https://www.40k.app/963/factions/world-eaters/units/khorne-berzerkers) | One point when the bearer's unit with one or more Icons destroys an enemy unit; one extra D6 per point at the next Blessings roll, then all points lost. The repaired attached-unit lookup finds bodyguard Icons for a Leader's kill, with one point per destroyed unit and event-time bearer ordering retained. |
| [Maulerfiend, The Scent of Blood, v963, 30 September](https://www.40k.app/963/factions/world-eaters/units/maulerfiend) | Source `000002639:3` already implements the nearby-enemy strength thresholds within 9 inches, with exclusive +1/+2 charge modifiers. No selected discrepancy or runtime change. This later consumer is outside the older Phase17F declaration count. |

The six verified recipes are any double; double 2+; double 3+; double 4+ or any
triple; double 5+ or triple 2+; and double 6 or triple 3+, in the existing
Unbridled Bloodlust, Rage-fuelled Invigoration, Total Carnage, Martial Excellence,
Warp Blades and Decapitating Strikes order. Their effects match the existing +1
charge, 6-inch Pile-in/Consolidation, 4+ melee fight-on-death, Sustained Hits 1,
Lethal Hits and Infantry-target Devastating Wounds consumers. The previous
full-table access gap is resolved for this selected mirror comparison. It does
not certify all World Eaters rules, a complete Codex or blocked detachments.

The earlier PR599 five selected PDF clauses also match the preferred mirror:

| Earlier selected clause | Preferred version and confirming scope |
|---|---|
| [Rangers: Path of the Outcast](https://www.40k.app/963/factions/aeldari/units/rangers) | v963, 30 September: opponent's Movement ending within 8 inches; unengaged Rangers may make a D6-inch Normal move. |
| [Daemonic Manifestation](https://www.40k.app/963/factions/chaos-daemons/army-rules) | v963, 30 September: +1 Battle-shock in Shadow of Chaos; success heals D3 or returns D3 non-Character Battleline models. |
| [Defiler: Daemonforge](https://www.40k.app/963/factions/chaos-space-marines/units/defiler) | v963, 30 September: Dark Pact permits wound-roll re-rolls of 1 through phase end. |
| [Exalted Patron](https://www.40k.app/981/factions/emperors-children/detachments/court-of-the-phoenician) | v981, 14 October: Lord Exultant bearer gains +1 inch Move; 15 points. The Lord Exultant/Sorcerer update listing was observed, but their entire datasheets were not audited. |
| [Defiler: Destroyer of Futures](https://www.40k.app/963/factions/thousand-sons/units/defiler) | v963, 30 September: once per phase per unit, Counteroffensive costs 1 CP less and permits other uses. |

These are new, bounded mirror confirmations. The original PR599 PDF-only source
record remains byte-identical and keeps its historical meaning; the separate
official interactive MFM reconciliation is not invalidated. The earlier limited
Custodes and Space Marines PDF lookups are not requalified as current App-data
audits. The Disciple of Khorne FAQ adds no blocked enhancement support here.

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
World Eaters' second row is Maulerfiend Savage Exaltation `000002639:4`; it remains
outside the selected mirror comparison. Record presence does not independently prove
execution or current source currency. These overlapping counts must not be
added or interpreted as whole-game playability/current-source certification.

Murdermind's SUPPORT metadata and Butcher Lord's LEADER metadata remain blocked
gameplay entries. Grimnar's Mark has no current LEADER allowance or exact matching
existing execution subrule; no display-name alias was inferred. The Vyper follow-up now resolves the former catalog/MFM title discrepancy through
one source-hashed `Datasheets` update at stable ID `000000605`. The preferred
[v963 mirror](https://www.40k.app/963/factions/aeldari/units/vyper) supplies singular
`Vyper`; the current v1.4 PDF pages 20–21 retains plural `VYPERS`. Exact matching
model characteristics, all seven weapon lines, composition, wargear and
Harassment Fire establish continuity with the existing sheet. The original row
preimage hash binds the update; no plural-name alias is installed in the resolver.
The 105x70 mm base is a mirror-only observation; PDF base dimensions were not
verified. This comparison does not certify a complete geometry or profile audit.

The plural model ID `000000605:vypers`, 1–2 composition, explicit keyword rows
(including `VYPERS`), weapon IDs and RuleIR remain intact. The derived name keyword
becomes `VYPER` with the current title. Ordinary component pricing previously
raised `ArmyPointsError`; after the source correction, one/two models resolve to
the current MFM `units-vyper` / `vyper` records and 75/140 points. Catalog JSON
roundtrip and the shared attachment-overlay path are covered. These component
requests do not certify a complete fieldable army.

Current support reports show `Vyper` while retaining the historical semantic/PDF
title `Vypers`; their identity guard validates the exact source preimage and title
transition. Historical source packages and RuleIR labels retain their provenance.
The bounded same-invariant scan now finds one current MFM label candidate for all
59 existing component rows; that is not profile, identity or semantic certification
for the other rows. See [binding evidence](../data/source_audits/supported_rules_2026_10/vyper-binding.json).
The mirror update history lists v867 (19 June, addition at 75 points) and v931
(26 August, Deadly Demise update). v963 is the selected faction snapshot, not a
claimed Vyper change date; 30 October is the observation date. Latest-faction
qualification remains an updates-index inference. No raw mirror payload hash is
claimed.

The prior five bounded PDF checks retain their original scope in
`data/source_audits/mfm_2026_10/bounded-rule-checks.json`; their separate mirror
confirmations are recorded above and in the new compact audit. This slice does
not qualify other Phase17F entries, later component consumers, characteristics,
weapons, whole faction books or non-executable World Eaters detachments. Those
unreviewed sources and the remaining identity discrepancies are separate bounded
follow-ups.

Implementation uses the accepted GPT-6 Astra High selection. The tool environment
does not independently attest runtime effort or expose the requested speed control.
No model performance advantage is asserted. Focused results are distinct from
the mandatory exact-head aggregate, review and hosted CI gates. The 64% full-package
branch-coverage floor, twelve-minute CI goal and 720-second shard cutoff are unchanged.

The existing generic overlay application rebuilds touched-row text metadata: raw text/HTML no longer retains historical bold tags and converted tags is empty, while sanitized/normalized text, tokens and stable source-text IDs are preserved. Original snapshot/PDF bytes remain retained; the title operation does not change gameplay descriptors.


The first authorized exact-base checker repair retained a fresh `tool-input-roles-v4`
comparison from measured head `c58420d729320d01cc28418e74f402676c7474c1` against
`bc9acd8419e7b97a2c1260c7e932d2cb9c3fc370`. The three original testcase samples were
134.063, 137.133, 138.313 seconds on base and
133.876, 135.626, 138.554 seconds on head
(means 136.503/136.019 seconds).
The unchanged relative-budget validator passed. This is a bounded source-workload
comparison on the recorded local host, not full-game or hosted-CI certification.

The campaign retained original command rejection controls, cleanup controls,
six source scanner checks, the 24-case cheap family, six arm-local runtime import
proofs, owned process supervision, per-command resource/terminal receipts,
the attempt journal, and input/dependency checks before and after commands.
All six generated contract trees matched their own arm's complete bound tree.
The success marker follows final source/dependency checks and budget validation.
The [original comparison](performance/evidence/vyper-source-c58420d7-comparison.json) and
[producer receipts](performance/evidence/vyper-source-c58420d7-producer.json)
retain the measured commit; later evidence-only commits require independent
equality of every selected byte. Historical v1/v2/v3 evidence and all limits are
unchanged. That measurement checkpoint contained 1,938 active quality cases and the same 260
historical deferrals; PR600's whole-module scheduling remains intact.

A separate normal checkout without local info/attributes overrides reproduced 35 historical test-metadata JSON paths reported dirty by Git, despite exact equality of their working bytes to the retained CRLF Git blobs. Exact per-path `-text` attributes preserve those current-head bytes and clean checkout status; no JSON content is rewritten and no baseline-only path is inferred. The five existing audit-file preservation entries remain unchanged. A second independent checkout verifies the committed repair and all selected/runtime input equality to measured c58420d7.

The complete local covered behavioral run passed all 4,927 cases at `5d3385f17d77c721bd180ac6b7633cf1cdff8e8a` with 65.49% combined line-and-branch coverage across the full package against the active 64% floor. The twelve-shard duration profile is refreshed from that actual JUnit run and explicitly labeled local WSL timing. The [independent checkout proof](performance/evidence/vyper-source-checkout-proof.json) retains both the reproduced 35-path dirty-status failure and the clean successor result. At that metadata checkpoint the source comparison identified measured c58420d7; later quality exposed the compatibility issue described below.

The subsequent complete quality run at `5c548482` did not pass: 1,931 cases passed, two failed and five had setup errors. Its original result is retained. Six category-migration outcomes were caused by the local shared-environment symlink; moving only that link outside the checkout restored all 34 active migration controls without changing their source or the existing deferrals. The remaining failure classified four authenticated historical-provenance references as active edition identities.

The narrow guard repair keeps the existing v2 report byte pin and permits only authenticated provenance at exact document locations: the pinned Vyper overlay's base package version, the pinned behavioral test's single source-membership assertion, the pinned role specification's five dependency paths, and the closed 22-file historical snapshot inventories in the exact current comparison. All other fields and adjacent strings remain scanned for active retired-edition identities; duplicate members, path/hash changes and other documents fail or remain visible to the guard. Source packages, overlay bytes, runtime behavior and behavioral tests are unchanged. Thirty-five new positive/negative controls bring the active quality inventory to 1,973, with the same 260 historical deferrals and existing whole-module assignments.

The [original c584 comparison](performance/evidence/vyper-source-c58420d7-comparison.json) retains its exact raw bytes and actual measured head. Changing the quality/control inputs requires a fresh six-sample comparison; the original samples do not qualify the new selected input set. The covered behavioral result retains its actual `5d3385f1` identity. A separate protected-input proof distinguishes unchanged runtime, behavioral tests, fixtures, dependencies and source/report tools from the four named quality/control changes; it does not claim equality of the complete new comparison inventory. Exact-final hosted covered behavior and every other required gate remain mandatory.

The required replacement campaign passed at measured `c918319f02e1da5f221eb54a589e48fe55d5d194` against the same actual base. Its three serial original-testcase samples were 131.015, 129.749, 130.914 seconds on base and 130.512, 130.207, 130.467 seconds on head (means 130.559/130.395 seconds). All inherited preflights, six arm-local import proofs, twenty owned-command receipts, six complete generated trees, final source/dependency checks and unchanged relative budgets passed. The [current comparison](performance/current/vyper-source-bc9-v4.json) and [new producer receipts](performance/evidence/vyper-source-c918319f-producer.json) retain that actual measurement identity. Later metadata requires equality of every selected input and the runtime-input digest to c918319f.

The retained covered run is still the actual 4,927-case run at 5d3385f1. Independent raw-hash/Git-blob comparison preserves 5,964 selected files, including all packaged runtime, all behavioral tests and fixtures, dependencies, and source/report tools. The only four changed selected controls are the edition guard, v4 classifier, v4 role specification and operation map. A bounded real execution of the sole conservative behavioral consumer observed ten migration predecessor paths, all outside the historical-category branch, and no reads/imports of those changed controls. This supports the reviewed production/behavior-input-equivalent carry; it does not claim the full comparison inventory or all possible dynamic calls are unchanged. Exact-final hosted covered behavior remains required, alongside all active quality, serial performance, static gates and both reviews.

The first c918 attempt stopped when the execution environment restarted after one completed base sample. Its partial receipts remain preserved and unqualified. The successful replacement used a new directory, repeated every preflight and all six original samples from zero, and did not reuse the interrupted sample.

The exact 47b0e3de quality run subsequently passed 1,969 active cases and failed four category-preservation controls. Their old edition-maintenance reader had not authenticated the new provenance guard as a successor. The repair preserves the raw d67b860d guard preimage separately, authenticates the current guard and a closed set of 22 additive AST nodes plus one routing statement, and requires the reconstructed whole-module AST to equal that predecessor. It then runs the original archive/hash, single-call and original-assertion AST checks unchanged. Recomputed live pins cannot hide an original assertion change or an unreviewed added control. Seven new preservation controls bring the active quality inventory to 1,980 with the same 260 historical deferrals.

This repair changes a shared behavioral preservation helper. The earlier covered-input carry is no longer current acceptance evidence: a fresh complete covered run and full active quality validation are required before another measurement campaign. The successful c918 comparison, its interrupted precursor, and both failed complete quality runs remain historical records with their actual outcomes. No source package, runtime engine, behavioral testcase or historical evidence bytes are rewritten.

The fresh complete covered run after the preservation-helper repair passed all 4,927 cases at `c2c3d6ab5e4adee42fc6514623aa244d3f51b5a0` in 860.272 seconds, with 65.49418006% combined line-and-branch coverage across the complete package. Its actual JUnit report refreshes the twelve-shard duration profile and is labeled local WSL timing. This supersedes the earlier bounded carry for current qualification. A metadata-only measurement successor must preserve all 5,969 selected raw hashes and Git blobs plus the runtime-input digest; fresh six-sample measurement and every exact-final gate remain required.
