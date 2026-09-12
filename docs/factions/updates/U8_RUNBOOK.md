# U8 — Update-pipeline runbook

[Update-pipeline index](README.md) · [Classification system](U_CLASSIFICATION_SYSTEM.md) · [Packet schema](U_PACKET_SCHEMA.md) · [Retention](U7_RETENTION.md) · [Q1 status artifact](../status/Q1_STATUS_ARTIFACT.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This document is Track U item **U8** (release cadence) plus the FM-pre
contracts for **U1** (offline capture), **U5** (tombstones in that
cadence), **U6** (rewrite procedure), and **Q6** (freshness CI) as
**FM-pre planning evidence**. It closes the ordered stages, roles, review
points, and freshness gate FM0 must run on each App-data release.

It does not implement the capture tool, S4 diff, classifier, packet
generator, tombstone loaders, rewrite runner, Q1 generator, guide
generator, changelog generator, or CI workflow. It does not amend F00,
edit `contracts/` or
[ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md),
rewrite
[FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md),
or change `src/`, catalogs, or packaged content.

Machine-readable catalog: [`u8_runbook.json`](u8_runbook.json).

U2–U4 still own grain, classes, and demotion. Packets still own work. Q1
still stores claims. U7 / U7a still own packaging windows and
cross-build replay. D1 still owns guide generation. D2 still owns
changelogs. This document only contracts **order, roles, and the
freshness gate**.

## 1. Purpose and delivery contract

Classification named **what changed**. Packets named **what work that
produces**. Q1 named **where claims persist**. Retention named **which
versions a build may load**. This document names **in what order that
work happens**, **who may do each step**, and **when CI may pass**.

One App-data release is one cadence. Calendar sprints are not a release.
A page URL is not a release. An update-feed line is not a packet.

**FM0 implements the tools and the CI gate.** It must not capture without
a human trigger, treat a staging audit as runtime input, treat a missing
feed line as equivalence when the package is older than the observation,
publish one PR per page, regenerate guides from anything but Q1, or let
a Q6 acknowledgement write Layer A `current`. Live contract rewrites
remain the Track D D3 FM0 PRs.

T1–T3 still own WHEN, EFFECT, and TARGET atoms. T4 still owns
construction. T5 still owns ledgers. T6 still owns decision shape. S2
still owns identity. S1 / F00 still own page-observation retention.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Re-audit policy | Roadmap: capture → diff → classify → packets → implement → regenerate status and guides |
| Q6 | Packaged current version versus latest retained observation; stale certified claims fail unless acknowledged |
| Orks pilot | FM0.5 uses the 931→946 pair as an S1 / S4 tooling fixture, not loadable N−1 |

This document does not copy bulk operative text. Community teasers are
not F00 observations. 39k.pro IDs are not `catalog_id` and are not
`owner_faction_id`.

## 3. Closed grain

### 3.1 One cadence per observed App-data version

A cadence starts when a human records a new retained observation of the
current App-data version (U1). It ends when:

- every published packet for that observation is closed or explicitly
  blocked;
- Q1, guides, and the changelog have been regenerated;
- Q6 passes, either because packaged current equals the observation or
  because a valid acknowledgement names the lag.

Two App-data versions are two cadences. Mixing their packets is invalid.

### 3.2 Stages are ordered

Closed stage IDs, in order:

| Stage | Owner | Output |
| --- | --- | --- |
| `trigger_observation` | Human | Decision that a new App-data version was observed |
| `u1_capture` | U1 tool | Staging audit of the feed and changed pages |
| `staging_review` | Human reviewer | Admitted observations or `blocked_provenance` |
| `u2_diff` | S4 tool | Classifiable rows on S2 locators plus field path |
| `u3_classify_and_packets` | U3 | Published packets |
| `u4_invalidate` | U4 | Layer demotion to `stale` where required |
| `implement_prs` | Packet consumers | Reviews, tombstones, remaps, family modules |
| `u7_package` | U7 | New current, and N−1 only when U7 allows |
| `regenerate_artifacts` | Q1 / D1 / D2 | Live `content_status`, guides, changelog |
| `q6_freshness` | Q6 CI | Pass, or fail, or acknowledgement of version lag |

U5 tombstones and U6 rewrite *implementation* run **inside**
`implement_prs` for `structural_remove` and `faction_rewrite` packets.
They consume packets U3 already published. They are not a licence to
emit children, publish packaging slots, or regenerate early.

U7a envelope re-verification runs on every claiming engine build. It is
not a U8 stage and does not replace `q6_freshness`.

### 3.3 Splits this grain must not flatten

| Flattened token | Published split |
| --- | --- |
| Update-feed line | Trigger hint; not a diff row and not a packet |
| U1 staging audit | Review input; never runtime input; not L0 |
| Missing feed line | Not equivalence when packaged current is older than the observation |
| One page URL | Many packets; many PRs if the packets require it |
| U5 tombstone | Current-version mustering only |
| U6 overlay | Coordinates a rewrite; does not emit children or skip publish-before-implement |
| U6 prepared version | Content prepared for the new App-data version; not the U7 packaged-current slot |
| D1 guide / D2 changelog | Derived; they do not write Q1 |
| Q6 acknowledgement | Version-lag waiver only; not Layer A `current` |
| U7a `certified` | Producer-specific envelope; not a U8 stage |

## 4. Pipeline

### 4.1 `trigger_observation`

A human records that App-data N was observed. The 40k.app update feed
may identify the snapshot. Navigation indexes, search results, teasers,
and other providers cannot start a cadence.

The absence of a feed entry is not proof that packaged content equals
the observation.

### 4.2 `u1_capture`

U1 is an **offline** tool. A human supplies the snapshot of the update
feed and the changed pages. The tool writes a staging audit for review.

Capture must follow F00: reviewed JSON, complete operative suffix
including points/DP and disposition, official provenance IDs, and
immutable fingerprints. This document does not amend F00.

U1 must not:

- run as a runtime loader or game-start hook;
- admit rows;
- mint `catalog_id`;
- treat a versioned-path historical URL as current-package input
  (those remain S1 / S4 fixtures);
- classify impact or emit packets.

### 4.3 `staging_review`

Each captured page is either:

- admitted after registered official provenance (S3a / F00); or
- held as Q1 `blocked_provenance` staging.

Staging never becomes L0 by default. Brute Bosses-class adds stay here
until provenance and catalog ID exist.

### 4.4 `u2_diff`

S4 diffs the packaged current content set against the staged admitted
observations. Rows are S2 `catalog_id` plus `source_entry_binding` plus
field path. Removals are inspected as carefully as modifications.

A page URL is not a row. Inherited listings of the same
`source_entry_binding` add zero rows. The Orks 931→946 fixture remains
the S4 golden; it is not loadable N−1.

### 4.5 `u3_classify_and_packets`

U3 assigns one closed impact class per field path and emits one packet
per classified row (packet schema). `faction_rewrite` is an overlay
plus children. Sibling `unclassified_clause` forbids Layer A
carry-forward on the sibling points or composition packet.

Packets must be published before implementation PRs start. An
implementer inventing a field path or a display-name packet is invalid.

### 4.6 `u4_invalidate`

U4 demotes the layers the class requires. A new transcription hash is
not Layer A `current`. Guides must not assert `current` while Q1 is
`stale`. That guide fail is **not** Q6-acknowledgeable.

### 4.7 `implement_prs`

Work units are published packets. Batching is allowed by
`owner_faction_id` or by a `family_gap` that several content packets
share. Forbidden batching: one PR per page URL; mixing two App-data
cadences; a content packet that lists the adapter contract.

A `family_gap` PR lands before the content PRs that require the new
family. Content packets must not edit
`ADAPTER_DECISION_CONTRACT.md`. A family or decision-kind
implementation PR still updates that contract in the same PR as the new
family or decision kind. That packet-path rule does not exclude the
separately owned FM0 U7a amendment of the same contract (record,
verification, fail-closed behaviour, and conformance). U7a remains
outside the U8 stage list.

U5 and U6 implementation run here when their packets say so (§5 and
§6).

### 4.8 `u7_package`

When U6 (or ordinary packet work) has prepared a new admitted
content-set version, U7 publishes the packaging slots. U7 writes
current. N−1 is packaged only for an owner whose
`first_certified_at_content_set` is already set and for whom this is a
later transition. Orks at FM0.5 stay current-only. U6 does not write
those slots.

Packaging does not write Q1 `certified` producer coverage (U7a).

### 4.9 `regenerate_artifacts`

One closing regenerate, after `u7_package` has published the slots this
cadence claims. Q1 reads that **updated** packaging inventory:

| Artifact | Reads | Must not |
| --- | --- | --- |
| Q1 `content_status` | Reviews, U4 demotion, packaging inventory | Hand-edited status |
| Guides and audits (D1) | Q1 only | Assert `current` while Q1 is `stale` |
| Changelog (D2) | U2 / U3 rows and packets | Feed prose as the changelog body |

Shipping implementation PRs without this regenerate is unpublished.

### 4.10 `q6_freshness`

See §7. Q6 is the last stage. It does not invent packets or package
content.

## 5. U5 tombstones in the cadence

`structural_remove` packets require `write_tombstone` and
`current_mustering_rejection` in the same implementation PR.

| Fact | Owner |
| --- | --- |
| `retired_in` / `superseded_by` | U5 record |
| Current-version mustering rejection | U5 + roster tests |
| Historical execution on a packaged previous version | U7 window |
| Python deletion | Q2 union of packaged versions |

More Dakka! at 946 is a current-version mustering blocker. The tombstone
does not package 931 and does not skip the regenerate step.

## 6. U6 rewrite procedure

`u6_rewrite_procedure` is a **stage-aligned path** through §3.2. It is
not a second pipeline. The `faction_rewrite` overlay coordinates the
rewrite; it does not create an exception to publishing children before
their implementation.

1. **`u3_classify_and_packets`.** U3 publishes the overlay and every
   per-entity child packet (adds, removals, costs, clauses). The
   overlay must not suppress those children and must not emit them
   later.
2. **`u4_invalidate`.** Layers demote as the classes require.
3. **`implement_prs`.** Implement the already-published overlay and
   children. Prepare the new content-set version (same L0–L8 tooling
   over every owned or inherited entity). Write U5 tombstones for every
   removed entity. Do not emit packets, do not publish packaging slots,
   and do not regenerate Q1, guides, or the changelog here.
4. **Implementation review** (review point 3): packets consumed, no
   unpublished children.
5. **`u7_package`.** U7 owns the packaged-current transition.
   `first_certified_at_content_set` does not reset. If already
   certified, the prepared version becomes current and the old current
   becomes previous.
6. **`regenerate_artifacts`.** Q1, the D1 guide, and the D2 changelog
   run only after that U7 transition and **read the updated inventory**.

Orks v946 is the uncertified mapping example: overlay plus More Dakka!
remove plus Brute Bosses add plus per-entity cost/clause packets, all
published before implementation. Orks is not certified there, so U7
packages current-only.

Chaos Daemons 946→960 after `-b` is the certified order fixture: see
fixture 21.

## 7. Q6 freshness gate

Q6 is CI. It has two checks.

### 7.1 Version lag

For each S2 `owner_faction_id`, compare:

- `packaged` current `content_set_version` (U7 inventory);
- latest retained F00 / S1 observation version for that owner.

If packaged current is older than the observation, CI fails unless a
ledger acknowledgement names that exact pair.

A missing update-feed line does not satisfy this check.

### 7.2 Stale certified claims

A Q1 claim that is `stale` while a derived guide, audit, or
capability-manifest dimension asserts `current` / `certified` /
`FULL_GAME_SUPPORTED` fails. **No acknowledgement waives this check.**
That is the U4 / Q1 guide fixture; Q6 enforces it in CI.

### 7.3 Acknowledgement ledger

The ledger is not Q1 and not a changelog. One entry waives **version
lag only** for one owner and one packaged/observed pair.

Closed `acknowledgement_kind` values:

| Kind | Meaning |
| --- | --- |
| `capture_in_progress` | U1 / staging review not finished |
| `packets_open` | Published packets are not all closed |
| `blocked_provenance` | Admission still waiting on official provenance |
| `implementation_open` | Packets are closed as published; implementation PRs remain |

Kinds that are invalid: `no_feed_so_equivalent`, `treat_as_current`,
`carry_forward_without_review`.

Identity object (every key present):

| Key | Value |
| --- | --- |
| `owner_faction_id` | S2 owner key |
| `packaged_content_set_version` | Packaged current |
| `observed_content_set_version` | Latest retained observation |
| `acknowledgement_kind` | Closed kind above |

`ack_id` is `q6ack_` plus the lowercase hex SHA-256 digest of the Q1 /
packet canonical-bytes recipe (RFC 8785 JCS; UTF-8; `sort_keys=True`
restricted ASCII shape).

Worked fixture. Canonical UTF-8:

```text
{"acknowledgement_kind":"packets_open","observed_content_set_version":"960","owner_faction_id":"orks","packaged_content_set_version":"946"}
```

`ack_id`: `q6ack_555c6f0d4c804c21528e3efa82af839346477ba1152c4d5f414d3004555541bd`

Changing only a `display_label` or a reviewer name must not change that
digest. A later observation 970 requires a new acknowledgement; the 960
entry does not cover it.

The acknowledgement must not write Q1 layer `current`, must not write
U7a `certified`, and must not admit staging.

## 8. Roles and review points

| Role | May | Must not |
| --- | --- | --- |
| Snapshot operator | Start `trigger_observation` and supply U1 bytes | Classify, admit, write Q1, publish packets |
| Staging reviewer | Admit after F00 or keep `blocked_provenance` | Treat a feed line as a diff row |
| Classifier | Emit packets from S4 rows | Implement packets or write Layer A `current` |
| Implementer | Consume published packets | Invent grain; list the adapter contract on a content packet |
| Status / guide / changelog generator | Emit derived artifacts | Hand-edit Q1 or assert `current` while stale |
| Q6 | Fail CI or accept a valid version-lag acknowledgement | Write Q1 `current`; treat no-feed as equivalent |

Required review points (cannot skip):

1. After `u1_capture` before any row is treated as admitted.
2. After `u3_classify_and_packets` before `implement_prs`.
3. After `implement_prs` before `u7_package` claims a new current.
4. After `regenerate_artifacts` before Q6 is allowed to pass without a
   version-lag acknowledgement.

The snapshot operator cannot publish packets. The implementer cannot
start before packets exist.

## 9. Writers and precedence

| Writer | May write | Must not |
| --- | --- | --- |
| U1 | Staging audit | Runtime records; Q1 entity rows |
| Staging review | Admission or `blocked_provenance` | L0 by default |
| U3 | Packets | Q1 `current` |
| U4 | Layer `stale` | Invent a carry-forward review |
| U5 | Tombstone; current mustering rejection | Unpackage a retained previous version |
| U6 procedure | Prepare the new content-set version; implement published overlay/children; retire removals via U5 | Emit child packets; publish packaging slots; regenerate before U7; suppress children; reset `first_certified` |
| U7 | Packaging slots (current / previous) | Q1 `certified` producer entries |
| D1 / D2 | Guides and changelog from Q1 / U2 / U3 | Write Q1 |
| Q6 ledger | Version-lag acknowledgement | Layer A `current`; U7a `certified` |

Precedence:

1. Missing packaged version still fails load (U7), even mid-cadence.
2. Guide `current` while Q1 is `stale` always fails; Q6 cannot waive it.
3. No-feed is not equivalence when packaged current is older than the
   observation.
4. U4 demotion still wins over a packet `status_claim` (Q1 §8.2).
5. A `family_gap` must land before content packets that require it.
6. A rewrite overlay does not exempt children from
   publish-before-implement and does not let U6 package or regenerate.

## 10. Acceptance fixtures

Implementation tests when the tools and CI land. This PR only defines
them.

1. A capture without a human-triggered snapshot is invalid. A scheduled
   runtime scrape is invalid.
2. A U1 staging audit never appears as a runtime input or as an L0
   count.
3. An update-feed line without a captured page is not a diff row and
   not a packet.
4. Packaged Orks 946 with a retained observation 960 and no
   acknowledgement fails Q6 even if the feed is empty.
5. One Blitz Brigade feed line still produces many packets (DP, each
   Enhancement add/remove, each Stratagem add/remove), not one page PR.
6. More Dakka! writes a tombstone and a current-version rejection in
   the same PR. 931 is not packaged.
7. The Orks v946 overlay does not suppress the More Dakka! or Brute
   Bosses child packets.
8. After a certified Chaos Daemons 946, a later rewrite to 960: U7
   packages 960 current and 946 previous. `first_certified` stays 946.
   U6 does not write those slots.
9. Guides regenerate from Q1 only. A hand-edited guide asserting
   `current` while Q1 is `stale` fails; a Q6 acknowledgement does not
   save it.
10. The D2 changelog is generated from U2 / U3 rows, not from feed
    prose.
11. The worked `ack_id` matches the published canonical bytes. Changing
    only `display_label` leaves it unchanged.
12. Acknowledgement `q6ack_555c6f0d…` waives Orks 946-versus-960 version
    lag while packets are open. Q1 rows stay `stale`. Observation 970
    is not covered.
13. `acknowledgement_kind: no_feed_so_equivalent` is rejected.
14. A `family_gap` PR is unpublished if content PRs that need the family
    already merged.
15. A content packet listing `ADAPTER_DECISION_CONTRACT.md` is invalid.
    A family or decision-kind PR still updates that contract in the
    same PR. That packet-path rule does not exclude the separately
    owned FM0 U7a amendment.
16. Deleting Python still referenced by packaged previous 946 is
    invalid.
17. A versioned-path 931 capture remains an S1 / S4 fixture. It does
    not start a current-package cadence and does not admit 931.
18. The snapshot operator cannot publish packets. Implementation PRs
    before `u3_classify_and_packets` are unpublished.
19. A disappeared current page with no `structural_remove` packet fails
    the cadence; removals are not optional.
20. Implementation PRs that skip `regenerate_artifacts` are unpublished.
21. A certified Chaos Daemons rewrite 946→960 publishes the overlay and
    every child packet in `u3_classify_and_packets` before any rewrite
    implementation starts. `implement_prs` consumes those packets and
    writes U5 tombstones; it does not emit children or package.
    `u7_package` then establishes current 960 and previous 946.
    `regenerate_artifacts` runs after that transition and reads the
    updated inventory. Regenerating before packaging, or emitting
    children inside `implement_prs`, is unpublished.

## 11. Mapping exercise (not a live cadence)

Planning examples. FM0 runs the real pipeline. This PR does not.

| Sample | U8 fact | Notes |
| --- | --- | --- |
| Orks 931→946 tooling | S1 / S4 fixture; not a loadable previous | U1 must not treat versioned-path as current |
| Orks v946 rewrite | Overlay plus children; U5 on More Dakka! | Fixture 7; first-certified null |
| Blitz Brigade DP 2→1 | One field-path packet inside `implement_prs` | Not a page PR |
| Brute Bosses | Stays `blocked_provenance` until provenance | Staging review, not L0 |
| Eldrad 130→120 | Points packet; Q1 review; D1 regenerates | Guide cannot stay hand-current |
| Acts of Faith remap | Envelope packet; U4 stale until recertify | Q6 cannot waive guide-current |
| Orks packaged 946 / observed 960 | Q6 fail, or `packets_open` ack `q6ack_555c6f0d…` | Fixture 4 / 12 |
| Chaos Daemons certified rewrite | Children published first; U7 then 960/946; regenerate reads that inventory | Fixtures 8 and 21 |
| Autarch `overall: Playable` | Not a Q1 write and not a changelog row | Q1 fixture 6 |

Do not publish a histogram of all 40 admitted views as cadence rows
here.

## 12. Gap list for later work

### 12.1 Surfaces that exist and must not be forked

F00 capture rules, S2 locators, U2–U4 classification, the packet
schema, Q1 collections, U7 packaging, U7a envelopes, D1 / D2
generation, and the L0–L8 ladder already exist. This document indexes
them.

### 12.2 Work that remains later (not this PR)

- U1 capture tool
- S4 diff tool and Orks 20/73 fixture
- U3 classifier and packet emission
- U4 runtime invalidation
- U5 tombstone loaders
- U6 rewrite runner
- Q1 / D1 / D2 generators
- Q6 CI workflow and live ledger
- U7 inventory and U7a contracts
- Live adapter-contract or agent-contract edits
- Catalog ID allocation

### 12.3 Families this runbook must not steal

- Identity and locators remain S2
- WHEN, EFFECT, TARGET, construction, ledgers, decisions remain T1–T6
- Diff grain, classes, and layers remain U2–U4
- Packet identity and surfaces remain the packet schema
- Status rows, reviews, and coverage labels remain Q1
- Packaging and cross-build replay remain U7 / U7a
- F00 page retention remains S1
- Extraction remains S3a
- Guide and changelog generation remain D1 / D2

## 13. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| U1 capture | Offline tool and staging audit | Cadence start |
| S4 / U3 / U4 | Diff, packets, invalidation | `implement_prs` |
| U5 / U6 runners | Tombstones and rewrite execution | FM0.5 Orks pilot |
| Q6 CI | Version-lag gate and ledger | Freshness enforcement |
| U-HOLD-ORKS-S4-COUNTS | Exact 20/73 S4 integers | S1 fixture, then S4 |
| Live Track D D3 | Adapter and agent contract rewrites | FM0 binding contracts |

## 14. What "U8 runbook delivered" means

FM0 cadence work may be implemented. It has:

- one cadence per observed App-data version;
- ten ordered stages with U5 / U6 *implementation* inside
  `implement_prs`;
- U1 offline-only capture that cannot admit or classify;
- rewrite overlays that cannot suppress children or emit them during
  implementation;
- U6 preparing the new content version and U7 publishing the slots;
- tombstones that cannot unpackage historical N−1;
- regenerate of Q1, D1, and D2 after the packaging transition;
- Q6 version-lag acknowledgements with published `ack_id` bytes;
- a guide-current-while-stale fail that no acknowledgement waives;
- twenty-one acceptance fixtures;
- a mapping exercise that does not run a cadence.

This survey does not add a tool, CI workflow, live ledger, `src/`
files, or catalog IDs. FM0 implements those from retained pages and
reconciles them with this document.
