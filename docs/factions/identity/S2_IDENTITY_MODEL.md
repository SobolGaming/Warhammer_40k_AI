# S2 — Identity model

[Identity index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Source policy (F00)](../../FACTION_RULES_SOURCE_POLICY.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md) · [T4 army-construction grammar](../taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md) · [Track T taxonomy](../taxonomy/README.md)

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
counts wait on S1 retained pages plus this model's owner-versus-alias pass
(`S2-HOLD-DISTINCT-COUNTS`). This document still closes the *axes*.

This document does not copy bulk operative text. Community teasers are not
F00 observations.

## 3. Closed identity axes

### 3.1 Identity layers (do not lift one over another)

| Layer | Owns | Must not |
| --- | --- | --- |
| `catalog_id` | Runtime catalog, army lists, replay, mustering | Change because a page slug or display name moved |
| `source_document_id` | F00 page provenance (`faction-app:<view>:<kind>:<slug>`) | Replace `catalog_id` |
| `official_source_id` | Retained GW PDF row, path, and hash | Replace `catalog_id` |
| `execution_id` | Named handlers, RuleIR clause IDs, phase consumers | Gate behaviour by display name |
| `provider_local_ref` | 39k.pro and other secondary lookups | Enter the catalog_id column |

One catalog entity may have many source-document IDs (inherited chapter or
related-army listings of the same page). Many source documents never become
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
| `detachment` | App slug in army lists (`shadow-legion`, `corsair-coterie`); Wahapedia numerics in some catalogs | One ID per distinct rule; inherited URLs are aliases |
| `enhancement` | Mixed slug, numeric, and composite | Grandfather per row; do not unify by name |
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
| Shared URL on two views | One catalog row, two listing memberships |
| Space Marines chapter view | Overlay, not a duplicate SM catalog faction |
| Grey Knights | Separate catalog faction, not an overlay |
| Related-army view | Listing view plus army-faction gate; not automatic Army Faction |
| Reporting group | Evidence grouping (28); not the 40-view inventory |
| Be'lakor | Datasheet `000001148`, not the display-name gate in `army_mustering.py` |
| Sir Hekhtur | Datasheet `000002770` **and** inclusion of Canis Rex `000001484` |
| Warbuggies | Held identity, not a name-join to excluded historical content |
| Gladius / Stormlance / Ironstorm after a Codex rewrite | Same label is not the same `catalog_id` |

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
`catalog_id`. Allocation records the App path, official provenance, and
display label in the crosswalk. The allocator must not slugify a display
name into the ID.

New datasheets may keep the 9-digit shape if the registry assigns that
digit string; the digits are then an allocated ID, not a name hash. New
detachments may keep an App path slug only after the registry adopts it
explicitly.

### 4.3 Retirement and slug movement

`retired_in` and `superseded_by` live on the registry row (roadmap design
rule 6). A slug change on 40k.app updates `source_document_id` and
`app_canonical_url`. It does not mint a new `catalog_id`. A Codex rewrite
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

Inherited Space Marine chapter listings of a shared detachment add extra
`app_source_document_ids` and `listing_view_ids`. They do not duplicate the
row.

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

A Warhammer Community preview dated 11 September 2026 describes fifteen
Space Marine detachments, `Unique:` listing tags, and stopgap chapter
updates that will not mix old chapter rules with the new Codex. That
article is not an F00 observation and does not change App-data 946.

S2 constraints when a later retained App version actually carries that
rewrite:

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

Listing URLs and listing names are not denominators.

A distinct detachment (or datasheet, Enhancement, Stratagem) is one
`catalog_id` after:

1. grouping observations that share the owning App URL;
2. treating inherited chapter/related listings as aliases;
3. excluding withheld, Titan, Legends, and `held_unresolved` rows.

T4's 270 unique *names* is a name count. The September register's 270–300
expectation is a forecast. FM0 records the exact integers after S1
retention (`S2-HOLD-DISTINCT-COUNTS`). Do not publish a fake resolved
histogram in this PR.

## 10. Gap list for FM0

### 10.1 Surfaces that exist and must not be forked

Committed army-list IDs, packaged catalog entity IDs, F00
`source_document_id` values, and official provenance IDs already exist.
The registry indexes them.

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
| S2-HOLD-DISTINCT-COUNTS | Exact distinct-rule integers after owner-versus-alias grouping | S1, then FM0 |
| S2-HOLD-ENHANCEMENT-ID-COLLISION | Enhancement/Stratagem IDs are mixed slug, numeric, and composite; grandfather per row | FM0 alias table |
| S2-HOLD-SM-CODEX-REWRITE | Announced SM detachment rewrite and `Unique:` tags are not App-data 946 | S1 re-observation when retained |
| S2-HOLD-REPORTING-GROUP-MAP | Which six chapter views share the Space Marines evidence report | Q1 |
| S2-HOLD-WAHAPEDIA-SNAPSHOT-LABEL | Frozen snapshot directory label is S3c, not this design | S3c |
| F-OWN-01 | Answered here for the identity axes; listing still must not substitute owner | this survey / FM0 loaders |
| F-DEBT-01 | Name and faction branches in generic mustering | FM0 debt item 1 |

## 12. What "S2 design delivered" means

FM0 registry work may be implemented. It has:

- the closed identity layers and entity kinds;
- grandfather-versus-allocate rules that keep army lists resolvable;
- the crosswalk field list;
- the Space Marines overlay (11 chapter overlays, Grey Knights separate);
- related-army owner / listing / host split;
- Sir Hekhtur resolved as `000002770` included by `000001484`;
- Warbuggies listed unresolved with no catalog ID;
- the hold that Community teasers are not F00.

S2 does not add registry files under `src/`, change army lists, or emit
`semantic_demand_matrix.json`. FM0 implements those artifacts from retained
pages and reconciles them with this document.
