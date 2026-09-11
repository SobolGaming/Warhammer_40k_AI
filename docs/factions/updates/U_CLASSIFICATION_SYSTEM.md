# U2 / U3 / U4 — Classification system

[Update-pipeline index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [T4 army-construction grammar](../taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This document is Track U items U2 (diff grain), U3 (impact classes), and U4
(layer demotion) as **FM-pre planning evidence**. It closes the classification
system FM0 must implement. It does not implement the S4 diff tool, the
classifier, status invalidation, task packets, Q1, U7a, or any `src/` or
catalog change. FM0 implements those artifacts from retained pages and
reconciles them with this document.

Machine-readable catalog: [`u_classification_system.json`](u_classification_system.json).

## 1. Purpose and delivery contract

U2, U3, and U4 are one system. A diff row names **what changed**. A class
names **what that means**. A layer names **which evidence is demoted**.
Splitting them forces Q1 to guess tuples.

A diff row is not a page URL, an update-feed line, a display name, or a
faction view. Lifting any of those over S2 `catalog_id` plus
`source_entry_binding` hides sibling Enhancements on one detachment page
(the T1-001 failure mode applied to updates; S2-001).

**FM0 implements the S4 tool, the classifier, and U4 invalidation.** It
must not classify by display name, emit one class per page, treat a new
transcription hash as a Layer A demotion, or carry Layer A forward without
a recorded equivalence review. Packets, Q1 schema, capture tooling, and
retention remain later design PRs.

T1–T3 still own WHEN, EFFECT, and TARGET atoms used inside the semantic
fingerprint. T4 still owns construction families this grain binds as
`construction_constraint`. T5 still owns ledgers. T6 still owns decision
shape. S2 still owns identity. This document only classifies **change**.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Mapping corpus | [Orks audit update reconciliation](../audit/orks.md#update-reconciliation): in-scope 946 changed URLs (15 current detachment pages, 53 current datasheet pages) plus More Dakka! as a removed detachment named by [F-ORK-01](../../FACTION_RULES_REMEDIATION_ROADMAP.md#initial-findings) |
| S4 fixture target | 20 detachment and 73 unit changes on the Orks 931→946 pair (not recounted here; `U-HOLD-ORKS-S4-COUNTS`) |
| Cross-faction class samples | Acts of Faith (F-ARMY-01); Eldrad, Bloodcrushers, Exorcist (F-DATA-01) |
| Engine inspection | Read-only: F00 provenance, S2 locators, status ladder L0–L8 |

September update lines are feed summaries. They are not retained dual-version
clause text. Per-clause assignment of "Rules Updated" rows waits on S1/S3a
(`U-HOLD-RULES-UPDATED`). This document still closes the *axes*.

This document does not copy bulk operative text. Community teasers are not
F00 observations.

## 3. Closed grain (U2)

### 3.1 One diff row

One diff row is one change to one catalog entity at one field path:

| Field | Role |
| --- | --- |
| `catalog_id` | S2 runtime identity. Null only for a `structural_add` that FM0 has not yet allocated |
| `entity_kind` | S2 kind |
| `source_entry_binding` | Parent F00 page plus `section_kind` and `ordinal_in_section` (S2 §5.2) |
| `field_path` | Closed path from §3.3 |
| `from_content_set` / `to_content_set` | App-data versions being compared |
| `impact_class` | Exactly one class from §5 for this field path |

A page observation, an update-feed URL, or `entity_kind` plus URL is not a
row. Army of Faith's four Enhancements are four identities on one page; a
Blitz Brigade feed line is many rows (DP, each Enhancement add/remove, each
Stratagem add/remove). Inherited chapter listings of the same child do not
emit extra rows.

`display_label` may be stored for humans. It is never the join key. Punctuation
twins (War Horde "Headwoppa's Killchoppa" added 15 pts and removed 20 pts;
Green Tide "Ferocious Show Off" / "Ferocious Show-off") are not identity.

### 3.2 Splits this grain must not flatten

| Flattened token | Published split |
| --- | --- |
| Update-feed URL | Many child entities; page provenance only |
| `Rules Updated` | Unclassified until retained clauses exist |
| New transcription hash | Provenance pin, not Layer A |
| Display name | Label only |
| Faction view | Overlay of `faction_rewrite` plus per-entity rows |
| DP change | `construction_constraint` on the detachment, not `points_only` |
| Points plus "Rules Updated" | Two field paths; union demotion; not `points_only` alone |

### 3.3 Closed field paths

| `field_path` | Typical class | Layer B evidence (U4) |
| --- | --- | --- |
| `provenance.transcription_sha256` | `text_hash_equal` or a clause/editorial class | not Layer B |
| `cost_rows` | `points_only` | cost rows hash |
| `composition` | `composition_or_options` | composition hash |
| `wargear_options` | `composition_or_options` | wargear/options hash |
| `keywords` | `attachment_or_keyword` | keywords hash |
| `leader_support` | `attachment_or_keyword` | Leader/Support and attachment hash |
| `army_construction` | `construction_constraint` | army-construction constraint hash (T4) |
| `geometry` | `composition_or_options` until S5 says otherwise | geometry evidence IDs |
| `clause.timing` | `clause_envelope_changed` | not Layer B |
| `clause.target` | `clause_envelope_changed` | not Layer B |
| `clause.restriction` | `clause_envelope_changed` | not Layer B |
| `clause.bearer` | `clause_envelope_changed` | not Layer B |
| `clause.effect_ir` | `effect_ir_changed` | not Layer B |
| `handler_identity` | `effect_ir_changed` or `editorial_equivalent` review | not Layer B |
| `existence` | `structural_add` / `structural_remove` | n/a for add; C for remove |

`army_construction` includes DP, force disposition, Enhancement-count caps,
duplicate-detachment, and required/prohibited selectors. It does not include
unit points.

## 4. Closed layers (U4)

Layer A separates **immutable source provenance** from the **semantic
fingerprint**. The transcription hash authenticates retained operative text
under F00, including points rows. A new hash is not a Layer A demotion.

| Layer | Claims | Evidence | Demoted when |
| --- | --- | --- | --- |
| A: semantic execution | L4, L5 | Provenance pins: source ID and current transcription hash. Fingerprint: effect RuleIR hash; timing/window descriptor; target grammar; restriction grammar; bearer grammar; binding IDs and parameters; handler identity for named-handler-backed clauses | Fingerprint changes, or a transcription change cannot be classified or carried forward |
| B: roster legality | L6 | cost rows hash; composition hash; wargear/options hash; keywords hash; Leader/Support and attachment hash; army-construction constraint hash; geometry evidence IDs | Any of those elements change |
| C: certification | L7, L8 | Current Layer A and B of every entity in the certified rosters and interactions, plus content-set version and packaged build identity | Any contributing Layer A or B change, or content-set/build identity change without re-attestation |

Provenance is not a fourth layer. Q1 will store these tuples; this document
does not design that artifact.

**Carry-forward.** A changed transcription requires classification first.
Layer A may move to the new observation only through a recorded equivalence
review linking old and new hashes and proving the fingerprint (and named
handler identity, when present) is unchanged. Unclassified changes stay
`stale`. Equality of effect RuleIR alone never proves equivalence.

**Points live in provenance text, not in the fingerprint.** `points_only`
preserves Layer A through that review and demotes Layer B.

**Layer C re-attestation.** Carry-forward of Layer A, or preservation of
Layer A while refreshing Layer B, never silently keeps L7/L8 on a new
content-set or build identity. Until Q1 records re-attestation, L7/L8 are
`stale` even when Layer A remains current.

**Union.** An entity with several field-path classes takes the union of
demoted layers. `unclassified_clause` on any clause path demotes A and C
regardless of a sibling `points_only` row.

**`faction_rewrite`** demotes A, B, and C for every owned or inherited
entity of that faction view. It does not suppress per-entity rows.

## 5. Closed impact classes (U3)

Stable IDs below. Display names in the roadmap table are labels.

| ID | Roadmap label | Layers demoted | Required work (implementation, not this PR) |
| --- | --- | --- | --- |
| `points_only` | Points only | B (affected rosters); C until re-attested | Regenerate cost records; roster validation; carry Layer A with a hash-link review; re-attest C |
| `text_hash_equal` | Text hash equal | none | Re-pin observation; operative suffix already matches |
| `editorial_equivalent` | Editorial equivalent | C until re-attested | Record the equivalence review; carry Layer A; re-attest C; named handlers need handler-identity confirmation |
| `clause_envelope_changed` | Timing, target, restriction or bearer changed, effect IR equal | A, C | `stale`; re-map and re-certify L4–L8 |
| `effect_ir_changed` | Effect IR changed | A, C | `stale`; re-certify L4–L8 |
| `unclassified_clause` | Unclassified clause change | A, C | `stale` pending review; no automatic carry-forward |
| `structural_add` | Structural add | none of A/B/C on a sibling | Staging until official provenance; then L0–L8 from scratch; no Python unless a new family is needed |
| `structural_remove` | Structural remove | C for rosters using it | Tombstone `retired_in`; current-version mustering rejection; Python removed only when no packaged version references it |
| `attachment_or_keyword` | Attachment or keyword change | B, C | Regenerate attachment/keyword records; fieldability regressions |
| `construction_constraint` | (closed here; T4 DP/FD/caps) | B, C | Regenerate T4 constraint records; mustering regressions |
| `composition_or_options` | (closed here; composition tiers and wargear options) | B, C | Regenerate composition/option records; fieldability regressions |
| `faction_rewrite` | Faction rewrite | A, B, C for the faction | U6 procedure; still emit per-entity rows |

`construction_constraint` and `composition_or_options` are not optional
subtypes of `points_only`. Orks DP 2→1 and Ghazghkull's removed 2-model
size would be mis-classified as points or as unclassified Layer A without
them.

### 5.1 Classifier rules

1. Assign one class per field path. Never one class per page.
2. If the field path cannot be attributed from retained text, use
   `unclassified_clause` (clause paths) or leave the row unpublished (no
   invented class).
3. Do not mint a class from a display name or from "Rules Updated".
4. `text_hash_equal` requires equal retained operative suffixes, not equal
   feed blurbs.
5. `editorial_equivalent` is never automatic.
6. `structural_add` does not demote siblings on the same parent page.
7. `faction_rewrite` is an overlay, not a substitute for child rows.
8. Do not emit packets here. Packet schema is the next FM-pre PR.

### 5.2 Acceptance fixtures (U3/U4)

Implementation tests when U3/U4 land. This PR only defines them.

1. Changed timing with unchanged effect IR and a new transcription hash
   demotes A and C (`clause_envelope_changed`).
2. A reviewed editorial-only change uses different old and new
   transcription hashes, carries Layer A, and re-attests C
   (`editorial_equivalent`).
3. A points-only change uses different hashes, preserves Layer A through
   carry-forward, demotes B, and re-attests C after roster validation
   (`points_only`).
4. Detachment DP 2→1 with unchanged clauses demotes B and C, not A
   (`construction_constraint`).
5. A "Rules Updated" feed line without retained dual-version clauses is
   `unclassified_clause`, even when the same line lists a points delta.
6. Adding Boss Boomer on Blitz Brigade does not demote Targetin’ Gizmos
   (`structural_add` is per child locator).
7. Inherited listings of the same `source_entry_binding` do not add rows.

## 6. Orks 931→946 mapping exercise

This is planning evidence from the September Orks audit, not the S4 fixture.
S4 must still reproduce 20 detachment and 73 unit changes including
removals. The audit's current-URL table omits removed detachments; More
Dakka! is added from F-ORK-01.

Overlay: Orks v946 is `faction_rewrite` (F-ORK-01). Waaagh! stays `stale`
until re-certified. Per-entity rows below still apply.

| Sample | Grain | Class | Notes |
| --- | --- | --- | --- |
| Orks faction view | `faction_view` / army-rules page | `faction_rewrite` | Overlay; U6 later |
| More Dakka! | `detachment` / `existence` | `structural_remove` | Not in the current-URL table; implemented baseline must tombstone |
| Brute Bosses, Flyboyz, Madcap Meks, Runt Swarm, Shoota Boyz, Wreckas, Wurrband | `detachment` / `existence` | `structural_add` | The seven added detachments |
| Nazdreg, Runtherd, Wartrakks, Gunwagon, Rukkatrukk Squigbuggies | `datasheet` / `existence` | `structural_add` | Wartrakks remains in-scope per the observation register |
| Blitz Brigade 2DP → 1DP; Green Tide 3DP → 1DP | `detachment` / `army_construction` | `construction_constraint` | Not `points_only` |
| Blitzkaptin removed; Boss Boomer added | `enhancement` / `existence` on the Blitz Brigade page | `structural_remove` / `structural_add` | Siblings; two rows |
| Glory Hog 30 → 25 pts | `enhancement` / `cost_rows` | `points_only` candidate | Only if retained clauses match; else also `unclassified_clause` |
| Bannernob 50 → 35 pts plus Rules Updated | `datasheet` / `cost_rows` and clause paths | `points_only` **and** `unclassified_clause` | Union demotes A, B, C |
| Ghazghkull new 1-model 300 pts; 2-model size removed | `datasheet` / `cost_rows` and `composition` | `points_only` and `composition_or_options` | Not points alone |
| Dakkajet, Weirdboy, Big’Ed Bossbunka "Rules Updated" | `datasheet` / clause paths | `unclassified_clause` | No points delta in the feed line |
| Follow Me Ladz 25 → 20 pts | `enhancement` / `cost_rows` | `points_only` candidate | Same name is not proof it is the same locator |
| Headwoppa's Killchoppa added 15 / removed 20 | two `enhancement` locators or one locator plus cost | `structural_add`/`structural_remove` or `points_only` | Do not name-join; S3a binds locators |

Cross-faction samples (not Orks, prove the class set is not rewrite-only):

| Sample | Class |
| --- | --- |
| Eldrad 130→120 | `points_only` |
| Bloodcrushers surcharge 20→40 | `points_only` |
| Exorcist surcharge | `points_only` |
| Eldrad narrowed Leader list | `attachment_or_keyword` |
| Acts of Faith battle-round → turn start | `effect_ir_changed` |

Do not publish a resolved histogram of all 53 datasheet URLs in this PR.

## 7. Gap list for later Track U / Q1

### 7.1 Surfaces that exist and must not be forked

F00 transcription hashes, S2 `catalog_id` and `source_entry_binding`, T4
constraint families, and the L0–L8 ladder already exist. Classification
indexes them.

### 7.2 Work that remains later (not this PR)

- S4 version ledger and dual-run diff tool (U2 implementation)
- Classifier and generated packets (U3 implementation; packet *schema* is
  the next FM-pre PR)
- Status invalidation and Q1 artifact (U4 implementation + Q1 design)
- U1 capture, U5 tombstone loaders, U6 rewrite runbook, U7/U7a, U8, Q6
- Orks 20/73 fixture reproduction
- Catalog ID allocation for new Orks entities

### 7.3 Families this survey must not steal

- Identity and child locators remain S2
- WHEN, EFFECT, TARGET, ledgers, decisions remain T1–T3, T5, T6
- Construction families remain T4; this survey only names the class those
  field paths use
- F00 page retention remains S1
- Extraction remains S3a

## 8. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| U-HOLD-ORKS-S4-COUNTS | Exact 20 detachment / 73 unit S4 integers, including removals | S1 versioned-path fixture, then S4 |
| U-HOLD-RULES-UPDATED | App "Rules Updated" lines have no retained dual-version clauses | S3a, then FM0 classifier |
| U-HOLD-NAME-PUNCTUATION | Feed punctuation twins are not locators | S2 locators on retained pages |
| F-ORK-01 | Waaagh! / Da Boss / "riled up" may be new tokens as well as a rewrite | FM0.5 after this classification |
| Packet schema | Data-first work packets | next FM-pre PR |
| Q1 schema | Where U4 tuples are stored | after packets or with U4 implementation design |

## 9. What "U2/U3/U4 classification delivered" means

FM0 classifier work may be implemented. It has:

- entity-and-field grain on S2 `catalog_id` plus `source_entry_binding`;
- twelve closed impact classes and three layers;
- union demotion and carry-forward rules;
- the three original U3/U4 fixtures plus DP, Rules Updated, sibling-add,
  and inherited-listing fixtures;
- an Orks 931→946 mapping exercise that does not claim S4 counts.

This survey does not add S4, packets, Q1, `src/` files, or catalog IDs.
FM0 implements those from retained pages and reconciles them with this
document.
