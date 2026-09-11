# S2 — Identity model

[Identity index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Source policy (F00)](../../FACTION_RULES_SOURCE_POLICY.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md) · [T4 army-construction grammar](../taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md) · [Track T taxonomy](../taxonomy/README.md) · [Track U classification](../updates/U_CLASSIFICATION_SYSTEM.md) · [Track U packet schema](../updates/U_PACKET_SCHEMA.md)

This document is Track S item S2 as **FM-pre planning evidence**. It closes the
identity axes FM0 must implement. It does not allocate catalog IDs, rewrite
army lists, amend F00, populate a content set, or change `src/` or packaged
data. FM0 implements the registry and loaders and reconciles them with this
document.

Machine-readable schema: [`s2_identity_model.json`](s2_identity_model.json).

## 1. Purpose and delivery contract

S2 closes how a rules entity is identified, who owns it, who may list it, and
how provider IDs attach as aliases.

An identity is not a display name, an App slug, a Wahapedia abbreviation, a
PDF page, or a 39k.pro path. Lifting any one of those over the others hides
ownership (the T1-001 failure mode applied to identity). Shared URLs, chapter
views, and related-army views are not interchangeable catalog rows
([F-OWN-01](../../FACTION_RULES_REMEDIATION_ROADMAP.md#initial-findings)).

**FM0 implements the registry, typed loaders, and crosswalk rows.** It must
not mint IDs from display names. Existing committed army-list and catalog IDs
stay resolvable unchanged. Slug renames are crosswalk updates, not new
identities.

T4 still owns construction grammar (DP, duplicate-detachment prohibition,
related-army *families*). S2 only names the IDs those families bind. T1–T3,
T5, and T6 still own WHEN, EFFECT, TARGET, ledgers, and decision shape.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Admitted views | **40** (36 primary minus two Titan exclusions, plus six related-army views) |
| Reporting groups | **28** (evidence grouping, not catalog identity) |
| Listing inventory | 982 distinct datasheet URLs; 506 distinct detachment URLs; 1,756 Enhancement/Upgrade listing rows; 2,520 Stratagem listing rows |
| T4 unique detachment listing names | **270** (names, not IDs) |
| Army-list fixtures | `data/army_lists/court-of-slaughter.json`, `anvanth-11th.json`, `cavalcade-shadow-bloodthirster.json` |
| Engine inspection | Read-only: catalog generation, F00 observations, `army_mustering.py`, player army-list schema |

September audits store listing URLs. Exact post-resolution distinct-rule
counts wait on S1 retained pages plus this model's page grouping,
child-entity locators, and proven inherited-alias merge
(`S2-HOLD-DISTINCT-COUNTS`). This document still closes the *axes*.

This document does not copy bulk operative text. Community teasers are not
F00 observations.

## 3. Closed identity axes

### 3.1 Identity layers (do not lift one over another)

| Layer | Owns | Must not |
| --- | --- | --- |
| `catalog_id` | Runtime catalog, army lists, replay, mustering | Change because a page slug or display name moved |
| `source_document_id` | F00 **page** provenance (`faction-app:<view>:<kind>:<slug>`) | Replace `catalog_id`; identify an Enhancement or Stratagem |
| `official_source_id` | Retained GW PDF row, path, and hash | Replace `catalog_id` |
| `execution_id` | Named handlers, RuleIR clause IDs, phase consumers | Gate behaviour by display name |
| `provider_local_ref` | 39k.pro and other secondary lookups | Enter the catalog_id column |

F00 page IDs are provenance identities, not catalog or clause execution IDs.
One source document may bind many catalog entities. One catalog entity may
appear in many listing documents. The join is a `source_entry_binding`
(§5), not a sixth runtime identity layer and not a display-name match.
Track U diffs that same join plus a field path; a page URL is not a diff
row ([U classification](../updates/U_CLASSIFICATION_SYSTEM.md)).

One catalog entity may have many source-document IDs (inherited chapter or
related-army listings of the same **page**). Many source documents never become
catalog rows (withheld, excluded, or `blocked_provenance` staging).

### 3.2 Registry entity kinds

Each row has one `catalog_id`, one `entity_kind`, one `owner_faction_id`
(except a content-set row), and a crosswalk object.

| Kind | Grandfathered ID shape in committed artifacts | Notes |
| --- | --- | --- |
| `faction_view` | App slug (`chaos-daemons`, `emperors-children`) | Wahapedia abbreviations (`CD`) are aliases |
| `overlay` | Chapter slug (`blood-angels`) | Not a second catalog faction for shared detachments |
| `army_rule` | Mixed numeric and consumer IDs | Headings are labels; the rule is the ID |
| `pact` | Construction record, not a datasheet | T4 families bind these IDs |
| `detachment` | App slug in army lists (`shadow-legion`, `corsair-coterie`); Wahapedia numerics in some catalogs | One ID per distinct rule; inherited **pages** are aliases |
| `enhancement` | Mixed slug, numeric, and composite | Grandfather per row; siblings on one detachment page are distinct IDs |
| `stratagem` | Mixed slug composite and numeric | Same as Enhancement |
| `datasheet` | 9-digit zero-padded (`000004083`, `000001148`, `000002770`) | Army lists already use this shape |
| `model_variant` | `<datasheet_id>:<slug>` | Geometry S5 consumes this ID |
| `content_set` | App-data version identifier | Not an entity inside the set |

Clause and ability execution IDs remain on the execution layer. They are not
a second catalog namespace for the same datasheet.

### 3.3 Ownership versus listing versus overlay versus host

| Role | Meaning |
| --- | --- |
| `owner` | Canonical catalog row. One owner per `catalog_id` |
| `listing_view` | An admitted App view that shows the entity. Does not create a second ID |
| `overlay` | Chapter record that *owns* chapter-only rules and *lists* parent-owned shared rules |
| `host_army` | The Army Faction that a pact admits related units *into* | Listing view, owner, and host may all differ |

Khorne Daemonkin is listed on the Blood Legions view, admits BLOOD LEGIONS
units, and is used in a World Eaters host army. Those three facts are three
fields, not one identity.

### 3.4 Splits this model must not flatten

| Flattened token | Published split |
| --- | --- |
| Display name | Label only; never `catalog_id` |
| App path slug | Provenance key; catalog_id only when grandfathered from existing artifacts |
| Wahapedia row ID | Frozen alias |
| 39k.pro path | `provider_local_ref` only |
| Shared URL on two views | One **page** row, two listing memberships; children of that page still need locators |
| F00 `source_document_id` | Page provenance; not an Enhancement or Stratagem identity |
| Enhancement or Stratagem display name on a detachment page | Sibling label; never `catalog_id` and never the source-entry locator |
| URL plus `entity_kind` | Still insufficient when one page has four Enhancements |
| Space Marines chapter view | Overlay, not a duplicate SM catalog faction |
| Grey Knights | Separate catalog faction, not an overlay |
| Related-army view | Listing view plus army-faction gate; not automatic Army Faction |
| Reporting group | Evidence grouping (28); not the 40-view inventory |
| Be'lakor | Datasheet `000001148`, not the display-name gate in `army_mustering.py` |
| Sir Hekhtur | Datasheet `000002770` **and** inclusion of Canis Rex `000001484` |
| Warbuggies | Held identity, not a name-join to excluded historical content |
| Gladius / Stormlance / Ironstorm after a Codex rewrite | Same label is not the same `catalog_id` |
| Oath of Moment (App-data 946 army rule) | Not the announced Combat Doctrines army rule |
| Combat Doctrines as a Gladius (and inherited) detachment heading | Not the announced Combat Doctrines army rule |

## 4. Registry scheme

### 4.1 Grandfathering (existing IDs stay)

A `catalog_id` already used in a committed player army list or a packaged
catalog payload is project-owned from this document onward. FM0 records it
in the registry; it does not mint a replacement.

Precedence when two artifacts disagree for the same entity:

1. Committed `data/army_lists/*.json` IDs for that entity.
2. Else the packaged `catalog.json` entity ID.
3. Else FM0 reviews the App path as a *candidate* and allocates; it does not
   auto-mint from a display name.

Worked examples:

- Lucius remains `000004083`. Model variant
  `000004083:lucius-the-eternal-epic-hero` remains that string.
- Shadow Legion remains `shadow-legion` in army lists. A Wahapedia numeric
  for the same detachment is an alias, not a second detachment.
- Court of Slaughter Enhancements remain the numeric IDs already in that
  list. Corsair Coterie Enhancements remain their slugs (`archraider`,
  `voidstone`). Do not merge those namespaces by normalizing names.

### 4.2 Allocation (new IDs only)

A new entity (no grandfathered ID) receives a registry-allocated
`catalog_id`. Allocation records the `source_entry_binding` (parent source
document plus locator), official provenance, and display label in the
crosswalk. The allocator must not slugify a display name into the ID or
into the locator. Distinct `catalog_id` values without bindings do not
establish which retained source entry each row represents.

New datasheets may keep the 9-digit shape if the registry assigns that
digit string; the digits are then an allocated ID, not a name hash. New
detachments may keep an App path slug only after the registry adopts it
explicitly.

### 4.3 Retirement and slug movement

`retired_in` and `superseded_by` live on the registry row (roadmap design
rule 6). A slug change on 40k.app updates `source_document_id` and
`app_canonical_url`. It does not mint a new `catalog_id`. Child
`source_entry_bindings` stay on that parent page; a later retained
observation rebinds locators by entry transcription hash, not by display
name. A Codex rewrite
that replaces a detachment's rules is a new entity plus a tombstone on the
old ID, never a name-join (`S2-HOLD-SM-CODEX-REWRITE`).

## 5. Crosswalk schema

FM0 `crosswalk.json` (path confirmed in S3a) carries one object per catalog
entity. Planning fields:

```json
{
  "catalog_id": "shadow-legion",
  "entity_kind": "detachment",
  "owner_faction_id": "chaos-daemons",
  "app_source_document_ids": [
    "faction-app:chaos-daemons:detachment:shadow-legion"
  ],
  "app_canonical_url": "https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion",
  "listing_view_ids": ["chaos-daemons"],
  "source_entry_bindings": [
    {
      "parent_source_document_id": "faction-app:chaos-daemons:detachment:shadow-legion",
      "parent_app_canonical_url": "https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion",
      "listing_role": "owner",
      "section_kind": "detachment",
      "ordinal_in_section": 1,
      "entry_transcription_sha256": null,
      "display_label": "Shadow Legion"
    }
  ],
  "wahapedia_source_row_id": null,
  "official_source_ids": [],
  "provider_local_refs": [],
  "overlay_id": null,
  "inclusion_of": null,
  "retired_in": null,
  "superseded_by": null
}
```

`provider_local_refs` may store a 39k.pro URL for lookup. Runtime must not
load 39k.pro content. Official provenance stays `official_source_ids` with
retained hashes, as F00 already requires.

`app_source_document_ids` and `app_canonical_url` remain **page**
identifiers. Inherited Space Marine chapter listings of a shared
detachment add extra page IDs and `listing_view_ids`. They do not duplicate
the detachment row, and they do not by themselves distinguish Enhancements
or Stratagems on that page.

### 5.1 Page versus child cardinality

The crosswalk must support both:

- one source document containing many catalog entities;
- one catalog entity appearing in many listing documents.

A detachment page is the usual many-child case. A datasheet page may still
yield `model_variant` children. An army-rules page may yield more than one
`army_rule` heading. Grouping by URL, or by URL plus `entity_kind`, is not
enough.

### 5.2 Source-entry binding

Every catalog entity extracted from a retained page carries one or more
`source_entry_bindings`. Each binding has:

| Field | Role |
| --- | --- |
| `parent_source_document_id` | F00 page identity of the document that contains the entry |
| `parent_app_canonical_url` | Owning App URL of that page |
| `listing_role` | `owner` on the canonical page; `listing` on an inherited reprint |
| `section_kind` | Section on that page: `detachment`, `enhancement`, `stratagem`, `datasheet`, `army_rule`, `model_variant` |
| `ordinal_in_section` | 1-based order of that entry inside the named section of the retained observation |
| `entry_transcription_sha256` | Hash of that entry's retained operative suffix once S1/S3a split the page; `null` until then |
| `display_label` | Human label only. Never a join key |

The locator is `parent_source_document_id` + `section_kind` +
`ordinal_in_section`, authenticated by `entry_transcription_sha256` when
that hash exists. It is not `catalog_id`. It must not be only a
display-name match, a slugified name, or a Wahapedia numeric used as a
stand-in for the retained entry.

Wahapedia row IDs and mixed MFM slugs remain aliases or grandfathered
`catalog_id` candidates (`S2-HOLD-ENHANCEMENT-ID-COLLISION`). They do not
replace the locator.

Two listing observations name the same child entity only when they share
the owning parent document and the same locator (same section and ordinal
on that observation, or the same entry transcription hash). Same
`display_label` on two pages is not that proof.

Planning locators for this document use the named Enhancement then
Stratagem row order in the September audit block for the owning URL. FM0
rebinds from the retained page.

Child example (no `catalog_id` allocated in this PR). Blade of Saint
Ellynor is Enhancement ordinal 1 on Army of Faith; Divine Aspect is
ordinal 2 on the same page:

```json
{
  "catalog_id": null,
  "entity_kind": "enhancement",
  "owner_faction_id": "adepta-sororitas",
  "app_source_document_ids": [
    "faction-app:adepta-sororitas:detachment:army-of-faith"
  ],
  "app_canonical_url": "https://www.40k.app/factions/adepta-sororitas/detachments/army-of-faith",
  "listing_view_ids": ["adepta-sororitas"],
  "source_entry_bindings": [
    {
      "parent_source_document_id": "faction-app:adepta-sororitas:detachment:army-of-faith",
      "parent_app_canonical_url": "https://www.40k.app/factions/adepta-sororitas/detachments/army-of-faith",
      "listing_role": "owner",
      "section_kind": "enhancement",
      "ordinal_in_section": 2,
      "entry_transcription_sha256": null,
      "display_label": "Divine Aspect"
    }
  ]
}
```

`catalog_id` stays `null` here because FM0 still grandfathers or allocates
it. The binding already says which retained page entry the future row is.

## 6. Space Marines overlay model

Owner decision D5 stands. Grey Knights is outside the overlay.

| View | Registry role |
| --- | --- |
| `space-marines` | Catalog faction; owns shared detachments and the 82 owned datasheets on that view |
| 11 chapter views | Overlay records: Black Templars, Blood Angels, Dark Angels, Deathwatch, Imperial Fists, Iron Hands, Raven Guard, Salamanders, Space Wolves, Ultramarines, White Scars |
| `grey-knights` | Separate catalog faction |

An overlay record owns chapter-only army rules, detachments, and datasheets
(the "owned" side of listed/owned counts). It may list parent-owned shared
detachments and datasheets. Certification of a shared detachment happens
once, on the Space Marines owner row.

Chapter army-rule headings (Templar Vows, The Sons of Sanguinius, The
Unforgiven, Curse of the Wulfen / Sagas, Kill Teams, Heirs of Sigismund)
are overlay-owned `army_rule` rows. `Space Marine Chapters` as a
construction heading stays a pact/rule on the parent, consumed by T4.

Deathwatch datasheets named "Kill Team" are ordinary in-scope datasheets.
The Space Marine Chapters exception that names Kill Team Cassius is
out-of-scope Legends text on an in-scope rule: record the exception, do not
admit a catalog row (T4 / F-SCOPE).

Six chapter views currently lack a separate repository reporting group and
use the Space Marines evidence report as baseline. That is a Q1 reporting
fact, not overlay membership (`S2-HOLD-REPORTING-GROUP-MAP`).

### 6.1 Announced Codex rewrite (not admitted)

Two Warhammer Community previews are not F00 observations and do not
change App-data 946:

- 10 September 2026 [Space Marines rules – First look](https://www.warhammer-community.com/en-gb/articles/ifgezlgu/space-marines-rules-first-look/):
  Combat Doctrines announced as the new army rule in place of Oath of
  Moment; Assault, Devastator, and Tactical doctrines; `Unique: Doctrines`
  on Assault Brethren, Tactical Brethren, and Devastator Brethren.
- 11 September 2026: fifteen Space Marine detachments, further `Unique:`
  listing tags, and stopgap chapter updates that will not mix old chapter
  rules with the new Codex.

S2 constraints when a later retained App version actually carries that
rewrite:

- Oath of Moment (current Space Marines army rule, T5
  `oath_of_moment`) is not Combat Doctrines. Tombstone the Oath army-rule
  row; allocate a new `army_rule` entity. Do not name-join.
- The App-data 946 Gladius Task Force heading Combat Doctrines (T2
  `doctrine_mode`, inherited on chapter overlay listings) is not that
  announced army rule, even though the display name matches. Keep the
  detachment heading on its grandfathered detachment ID until S1 shows
  retirement or rewrite; do not lift it to `owner_faction_id` army-rule
  identity.
- Captain doctrine activation, Guilliman Codex Adept, and doctrine-gated
  character abilities are datasheet or Enhancement rows, not a second
  army rule and not overlay membership.
- Same display names (Gladius Task Force, Stormlance Task Force, Ironstorm
  Spearhead) are not identity. Allocate or tombstone; do not name-join.
- `Unique: Doctrines`, `Unique: Tacticus`, `Unique: Phobos`, and
  `Unique: Gravis` are extra listing tags in the T4 sense, not Core Force
  Dispositions. Mutual exclusion, if retained, is
  `prohibited_other_detachment` (or a tag selector) in FM0, not a P25C
  faction branch.
- Chapter stopgaps that refuse to combine old and new rules match D5:
  overlay records must not merge obsolete chapter supplements into the new
  shared detachments.

## 7. Related-army and shared-page ownership

Six related-army views are listing views: Harlequins, Ynnari, Blood
Legions, Plague Legions, Legions of Excess, Scintillating Legions.

| Listing view | Default owner faction for shared pages | Host army when a pact admits units |
| --- | --- | --- |
| Harlequins | `aeldari` for shared Aeldari pages; Harlequins owns its 8 datasheets | Aeldari (Disparate Paths), or Drukhari via Corsairs |
| Ynnari | `aeldari` for shared pages; Ynnari owns its 11 datasheets | Aeldari (Disparate Paths) |
| Blood Legions | `chaos-daemons` / World Eaters per canonical owner URL | World Eaters (Pact of Blood / Daemonkin) |
| Plague Legions | Death Guard / Chaos Daemons per canonical owner URL | Death Guard |
| Legions of Excess | Emperor's Children / Chaos Daemons per canonical owner URL | Emperor's Children |
| Scintillating Legions | Thousand Sons / Chaos Daemons per canonical owner URL | Thousand Sons |

Canonical owner is the App view that owns the URL in the September audits
("owned" counts). Shared links open that owning audit; S2 forbids a second
datasheet ID for the same URL.

Related views are not Army Faction unless a source-linked
`army_faction_admission_gate` exception says so (T4). Engine
`FORBIDDEN_DEFAULT_ARMY_FACTION_RULE_BY_KEYWORD` already maps the four
daemon-related views; FM0 binds that gate to pact IDs, not keywords in
generic lifecycle code.

Shadow Legion Thralls, Khorne Daemonkin, Tallyband Summoners, Brood
Brothers, Assigned Agents, Freeblades, Dreadblades, Cults of the Dark Gods,
and Corsairs remain T4 families. S2 supplies `catalog_id` and owner fields
those families reference.

Be'lakor remains datasheet `000001148`. Display-name detection in
`army_mustering.py` is F-DEBT-01, retired in FM0 onto these IDs.

## 8. Warbuggies and Sir Hekhtur

### 8.1 Warbuggies — listed unresolved

[F-SCOPE-01](../../FACTION_RULES_REMEDIATION_ROADMAP.md#initial-findings)
stands. The App name overlaps historically excluded content. There is no
admitted URL, no catalog row, and no source-package admission in F00.

S2 does **not** admit Warbuggies. A matching name cannot prove identity.
Resolution requires a retained current App observation, official
provenance, and an explicit scope review in a later PR. Until then the
entity is `held_unresolved` with no `catalog_id`.

### 8.2 Sir Hekhtur — identity resolved

Sir Hekhtur is an in-scope Imperial Knights datasheet:

| Field | Value |
| --- | --- |
| `catalog_id` | `000002770` (grandfathered datasheet ID) |
| App page | [Sir Hekhtur](https://www.40k.app/factions/imperial-knights/units/sir-hekhtur) |
| Owner | `imperial-knights` |
| `inclusion_of` | Canis Rex `000001484` |
| Standalone cost | None. Do not invent 0 pts |

The inclusion edge is identity, not a missing datasheet. Cost and
attachment accounting remain S3a / Track C. Canis Rex stays a separate
datasheet (`000001484`) that lists Sir Hekhtur as an attachment recipient.

## 9. Distinct-rule counting method

Listing URLs and listing names are not denominators. Page grouping avoids
duplicate captures. It does not count the entities extracted from those
pages.

A distinct detachment, datasheet, Enhancement, or Stratagem is one
`catalog_id` after:

1. **Page grouping.** Group observations that share the owning App URL.
   Inherited chapter or related-army captures of the same owning URL are
   duplicate page observations, not yet catalog entities.
2. **Child-entity resolution.** On each remaining owning document, extract
   catalog entities by `source_entry_binding`. One page may yield many
   rows. URL plus `entity_kind` is not enough: Army of Faith's four
   Enhancements are siblings, not one Enhancement.
3. **Inherited alias merge.** Merge a listing observation onto an existing
   child only after its binding is shown to reference that same child
   (owning parent document plus locator, or matching entry transcription
   hash). Display-name agreement is not that proof. Unproven reprints stay
   distinct until S1/S3a binds them.
4. **Exclusion.** Drop withheld, Titan, Legends, and `held_unresolved`
   rows.

### 9.1 Worked example — Army of Faith

Owning page: [Army of Faith](https://www.40k.app/factions/adepta-sororitas/detachments/army-of-faith).
F00 parent (page-level): `faction-app:adepta-sororitas:detachment:army-of-faith`.
September audit block: `docs/factions/audit/adepta-sororitas.md#detachment-army-of-faith`.
Page observation SHA-256
`43aa38dcfa513bc8c08bb14213d715cfbacde5df3be76972b1ea0f6bba220d46`
authenticates the page, not each child.

That single document retains these catalog identities (no `catalog_id`
allocated here):

| `section_kind` | `ordinal_in_section` | `display_label` (not a join key) |
| --- | --- | --- |
| `detachment` | 1 | Army of Faith |
| `enhancement` | 1 | Blade of Saint Ellynor |
| `enhancement` | 2 | Divine Aspect |
| `enhancement` | 3 | Litanies of Faith |
| `enhancement` | 4 | Triptych of the Macharian Crusade |
| `stratagem` | 1 | Shield of Faith |
| `stratagem` | 2 | Light of the Emperor |
| `stratagem` | 3 | Faith and Fury |
| `stratagem` | 4 | Blinding Radiance |
| `stratagem` | 5 | Divine Guidance |
| `stratagem` | 6 | Angelic Descent |

Four Enhancement identities and six Stratagem identities. Blade of Saint
Ellynor and Divine Aspect are siblings. Shield of Faith and Light of the
Emperor are siblings. An inherited listing of the same owning URL would
add `listing` bindings to those rows. It would not add four Enhancements
or six Stratagems.

The same merge step on Gladius Task Force (owned at
[space-marines/gladius-task-force](https://www.40k.app/factions/space-marines/detachments/gladius-task-force)
and listed on all eleven chapter overlays) does not mint twelve Adept of
the Codex rows.

T4's 270 unique *names* is a name count. The September register's 270–300
expectation is a forecast. FM0 records the exact integers after S1
retention (`S2-HOLD-DISTINCT-COUNTS`). Do not publish a fake resolved
histogram in this PR.

## 10. Gap list for FM0

### 10.1 Surfaces that exist and must not be forked

Committed army-list IDs, packaged catalog entity IDs, F00
`source_document_id` values (page-level), and official provenance IDs
already exist. The registry indexes them. Child locators are new
crosswalk fields; they do not rewrite F00 page IDs.

### 10.2 Work that remains FM0 (not this PR)

- Typed registry loader and `crosswalk.json` in the content set
- Replacing Be'lakor-by-name and detachment-id branches in
  `army_mustering.py` (debt item 1)
- Distinct-rule integer publication
- Warbuggies admission or permanent exclusion after source review
- Codex rewrite rows, if and when App-data retains them
- Snapshot-directory label resolution (S3c)

### 10.3 Families S2 must not steal

- WHEN, EFFECT, TARGET, ledgers, and decision kinds remain T1–T3, T5, T6
- Construction families remain T4 / P25C
- F00 page retention remains S1
- Extraction remains S3a

## 11. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| F-SCOPE-01 | Warbuggies identity; no admission | Later source review, not this PR |
| S2-HOLD-DISTINCT-COUNTS | Exact distinct-rule integers after page grouping, child-entity resolution, and proven inherited-alias merge | S1, then FM0 |
| S2-HOLD-ENHANCEMENT-ID-COLLISION | Enhancement/Stratagem IDs are mixed slug, numeric, and composite; grandfather per row | FM0 alias table |
| S2-HOLD-SM-CODEX-REWRITE | Announced Combat Doctrines army rule, SM detachment rewrite, and `Unique:` tags are not App-data 946; Oath and the Gladius Combat Doctrines heading stay distinct IDs | S1 re-observation when retained |
| S2-HOLD-REPORTING-GROUP-MAP | Which six chapter views share the Space Marines evidence report | Q1 |
| S2-HOLD-WAHAPEDIA-SNAPSHOT-LABEL | Frozen snapshot directory label is S3c, not this design | S3c |
| F-OWN-01 | Answered here for the identity axes; listing still must not substitute owner | this survey / FM0 loaders |
| F-DEBT-01 | Name and faction branches in generic mustering | FM0 debt item 1 |

## 12. What "S2 design delivered" means

FM0 registry work may be implemented. It has:

- the closed identity layers and entity kinds;
- page versus child-entity cardinality and source-entry locators;
- grandfather-versus-allocate rules that keep army lists resolvable;
- the crosswalk field list;
- Army of Faith as four Enhancement identities and six Stratagem
  identities on one page, with inherited reprints not increasing those
  counts;
- the Space Marines overlay (11 chapter overlays, Grey Knights separate);
- related-army owner / listing / host split;
- Sir Hekhtur resolved as `000002770` included by `000001484`;
- Warbuggies listed unresolved with no catalog ID;
- the hold that Community teasers are not F00.

S2 does not add registry files under `src/`, change army lists, or emit
`semantic_demand_matrix.json`. FM0 implements those artifacts from retained
pages and reconciles them with this document.
