# U7 / U7a — Retention and replay compatibility

[Update-pipeline index](README.md) · [Classification system](U_CLASSIFICATION_SYSTEM.md) · [Packet schema](U_PACKET_SCHEMA.md) · [Runbook](U8_RUNBOOK.md) · [Q1 status artifact](../status/Q1_STATUS_ARTIFACT.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md) · [Adapter decision contract](../../ADAPTER_DECISION_CONTRACT.md)

This document is Track U items **U7** (packaging coexistence) and **U7a**
(replay compatibility) plus owner **D3** (content-set retention) as
**FM-pre planning evidence**. It closes when a previous content-set version
may be packaged as loadable content and how a newer engine build may
reproduce an older artifact without ignoring `engine_build_id`.

It does not package content, emit a live inventory or compatibility record,
amend `contracts/` or
[ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md), rewrite
[FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md),
implement U4 invalidation, generate Q1, or change `src/`, catalogs, or F00.

Machine-readable catalog: [`u7_retention.json`](u7_retention.json).

Owner **D3** is content-set retention. Track **D** item D3 (live adapter
contract plus agent-contract rewrite) is not this document. Q1 already
stores the certification event and the coverage *labels* `certified` /
`exact_build_only`. This document owns packaging activation and the
compatibility *mechanism* those labels cite.

## 1. Purpose and delivery contract

Classification named **what changed**. Packets named **what work that
produces**. Q1 named **where claims persist**. This document names **which
content-set versions a build may load** and **when a different
`engine_build_id` may still replay**.

One owner faction has at most:

- the current packaged content-set version, always;
- one previous packaged version, and only after that faction's first
  full-support certification and the next content-set transition;
- handlers required by the union of those packaged versions.

**FM0 implements the packaging inventory, version-aware loaders, the
hashed compatibility record, contract amendments, and the golden-artifact
fixture.** It must not package N−1 because `first_certified_at_content_set`
was written, claim `certified` from packaging alone, ignore
`engine_build_id`, treat an S1 historical observation as loadable content,
or apply U7a to Phase 18L operator recovery. U1 capture, U5 loaders, and
U6 runners remain FM0. Cadence is designed in
[U8_RUNBOOK.md](U8_RUNBOOK.md).

T1–T3 still own WHEN, EFFECT, and TARGET atoms. T4 still owns construction
families. T5 still owns ledgers. T6 still owns decision shape. S2 still
owns identity. S1 still owns page-observation retention. U2–U4 still own
grain, classes, and demotion. Packets still own work. Q1 still stores
claims. This document only contracts **packaging and cross-build replay**.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Owner decision | Roadmap D3: current plus one previous, per faction, after first `-b` certification |
| Status labels | [Q1](../status/Q1_STATUS_ARTIFACT.md) `first_certified_at_content_set`, `packaged`, `certified`, `exact_build_only` |
| Build identity | Existing `engine_build_id` (`warhammer40k-core-v2:runtime-tree-sha256-v1:<sha256>`) |
| S3c dependency | Catalog-generation switch waits on the FM0 U7a implementation, not this design |

This document does not copy bulk operative text. Community teasers are not
F00 observations. 39k.pro IDs are not `catalog_id` and are not
`owner_faction_id`.

## 3. Closed grain

### 3.1 Two D3 names

| Name | Owns | Does not own |
| --- | --- | --- |
| Owner D3 | When N−1 may be packaged; handler union; fail-closed missing version | Live adapter or agent contracts |
| Track D D3 | Live `ADAPTER_DECISION_CONTRACT.md` updates with a real family; live agent-contract rewrite | Packaging windows |

A PR that rewrites the live agent contract under this filename is invalid.

### 3.2 Owner-faction packaging window

Retention is keyed by S2 `owner_faction_id`. Reporting groups, chapter
views, update-feed lines, and display names are not windows.

Related-army *listing* of a shared page uses that page's owner window.
Harlequins or Ynnari listing an Aeldari-owned page does not create a
second Aeldari package. Datasheets those related views actually own use
their own `owner_faction_id` window.

Space Marines shared detachments use the `space-marines` window. Chapter
overlays are not a second packaged version. Grey Knights is outside that
overlay and has its own window.

FM0 binds `owner_faction_id` to the owner-faction `catalog_id` when that
ID is allocated. This document does not mint catalog IDs.

### 3.3 Certification event is not packaging

Q1's `first_certified_at_content_set` records the `-b` close: every owned
or inherited entity L8 and `current` at the packaged version, zero open
blockers, Q3 and Q4 green for that faction.

Writing that field:

- does not package N−1;
- does not write `replay_compatibility: certified`;
- does not create a U7a record.

An open blocker at `-b` leaves the field JSON `null`. Previous-version
retention does not activate.

### 3.4 N−1 activates on the next content set

Reconciles D3 ("from that event onward") with the sequence rule ("from
the next content set onward") and with Q1 fixtures 7–8:

1. The *policy* becomes eligible when `first_certified_at_content_set` is
   non-null.
2. The *first previous package* appears on the next content-set transition
   after that event.
3. "Previous" is the immediately prior *packaged current* of that owner
   faction, not an S1 versioned-path snapshot and not an arbitrary older
   App-data number.

Chaos Daemons certified at 946 therefore keeps only 946 packaged at the
certification event. 931 does not become loadable because `-b` closed.
When a later 960 is packaged, 946 becomes the previous version.

Orks at FM0.5 keep `first_certified_at_content_set` null. The 931→946
pair remains an S1 / S4 tooling fixture. No previous Orks version is
loadable content.

### 3.5 Current plus exactly one previous

After activation, the package for that owner faction is:

| Slot | Meaning |
| --- | --- |
| Current | Always packaged; always the latest admitted content-set version of that owner |
| Previous | The immediately prior current, packaged while it is N−1 |
| Dropped | N−2 and older are absent from the package |

A third live packaged version is invalid. Dropped content remains in the
git history. The packaging inventory records the repository tag that last
had it so a fail-closed load can name that tag.

U6 rewrite after certification is a new current version. `first_certified`
does not reset. The old current becomes previous; the old previous is
dropped.

### 3.6 Game and replay identity

Game configuration and replay artifacts carry:

| Field | Role |
| --- | --- |
| `engine_build_id` | The producing or recovering build; existing SHA over the packaged runtime tree |
| `participating_factions` | Every participating `owner_faction_id` plus that faction's `content_set_version` |

`current` is not a version. Omitting a participating owner faction is
invalid. Inferring a version from another faction or from the consuming
build's current package is invalid.

Same-`engine_build_id` replay keeps today's exact-build path and still
requires every named version to be packaged. U7a applies only when the
consuming `engine_build_id` differs from the producing build.

### 3.7 Splits this grain must not flatten

| Flattened token | Published split |
| --- | --- |
| S1 retained observation / versioned-path fixture | Not loadable content |
| Q1 `first_certified_at_content_set` | Event only; not an N−1 package |
| Q1 `certified` / `exact_build_only` | Labels; the mechanism lives here |
| Packaged previous version | Loadable N−1, not "any older snapshot" |
| U5 tombstone | Current-version mustering only |
| Track D D3 | Live contracts, not packaging |
| Phase 18L recovery | Exact `engine_build_id`; U7a does not apply |
| Selected-game `REPLAY_VERIFIED` | Q1 / Phase 17O bound; not cross-build `certified` |

## 4. Packaging inventory (U7)

### 4.1 Inventory artifact

FM0 emits one generated packaging inventory, distinct from Q1. Q1 remains
the publishable status denominator. The inventory is the loader's package
map.

One owner-faction entry:

| Field | Role |
| --- | --- |
| `owner_faction_id` | S2 owner key |
| `current_content_set_version` | Always present |
| `previous_content_set_version` | App-data version or JSON `null` |
| `first_certified_at_content_set` | Citation of the Q1 field; this inventory must not write Q1 |
| `dropped_versions` | `{content_set_version, available_at_git_tag}` for versions this package no longer loads |

`available_at_git_tag` is the tag FM0 recorded when that version last left
the package. This document does not mint a tag-name scheme.

Staging observations never appear here. They are not L0 and they are not
packaged.

### 4.2 Activation rules

| Condition | Current | Previous |
| --- | --- | --- |
| `first_certified_at_content_set` is JSON `null` | Packaged | Must be JSON `null` |
| Certified, no later content set yet | Packaged (the certified version) | Must be JSON `null` |
| Certified, at least one later content set | Latest packaged version | Immediately prior current |
| Later transition after that | New latest | Prior latest; older previous dropped |

A U7a record cannot make an uncertified faction's older snapshot loadable.
Orks 931 stays a tooling fixture until Orks is certified *and* a later
content set activates N−1, at which point the previous slot is the then
prior current (not every historical App-data number).

### 4.3 Fail-closed missing version

Loading a game or replay that names an `owner_faction_id` plus
`content_set_version` absent from `{current, previous}` fails closed with a
typed domain error that names:

- the `owner_faction_id`;
- the requested `content_set_version`;
- the producing `engine_build_id` when the load is a replay;
- the `available_at_git_tag` for that version when the inventory has one.

Returning an empty roster, substituting current content, or silently
skipping the faction is forbidden.

### 4.4 Related-army and overlays

| Case | Window |
| --- | --- |
| Shared Aeldari page listed by Ynnari | `aeldari` |
| Ynnari-owned datasheet | `ynnari` |
| Shared Space Marines detachment under a chapter view | `space-marines` |
| Grey Knights entity | `grey-knights` |
| Blood Legions listing of a Chaos Daemons URL | `chaos-daemons` |

Host-army pacts (T4) do not create a second packaging window. They name
the host `owner_faction_id` already on the game configuration.

## 5. Handler and Python retention

Q2 parity is evaluated against the **union** of packaged versions for
every owner faction, not the current version alone.

Every generic handler and every justified named handler required by any
packaged version is retained until no packaged version references it.
Packet `structural_remove` still forbids deleting Python referenced by a
packaged version.

When N−2 is dropped and only that version referenced a handler, Q2 may
delete the unreferenced module. Tombstones do not keep handlers alive;
packaged versions do.

Dated runtime module names remain forbidden. This document does not add
Python.

## 6. Tombstones versus historical availability

U5 `retired_in` / `superseded_by` govern **current-version mustering
only**.

A roster built against a content-set version at or after `retired_in` is
rejected with a typed reason. A game or replay that declares an earlier
*packaged* version still loads and executes that record.

More Dakka! at 946 is `freshness: retired` on the current Orks row. That
is a current-version mustering blocker. It is not a licence to package
931, and it is not a licence to execute More Dakka! in a 946 roster.

U6 rewrite emits a new current version and explicit retirement of every
removed entity. Historical availability still depends on the U7 window,
not on the tombstone.

## 7. Replay compatibility record (U7a)

Today replay and persistence require the exact `engine_build_id`.
Packaging a new content set changes that SHA even when the original
faction content is still packaged. Ignoring the mismatch is forbidden.
Retention is meaningful only with an explicit compatibility mechanism.

### 7.1 Certified pair grain

A newer consuming build may reproduce an artifact exported by an older
producing build only when a verified envelope exists for **each**
participating owner faction.

Closed pair identity (every key present):

| Key | Value |
| --- | --- |
| `producing_engine_build_id` | Exact producing `engine_build_id` |
| `owner_faction_id` | S2 owner key |
| `content_set_version` | App-data version named by the artifact |

A corpus-wide `(build, version)` pair is too coarse: certifying Orks 946
must not certify Chaos Daemons 946. A whole-tree snapshot hash is too
coarse: one faction update would recertify every other owner.

### 7.2 Identity projection

Canonical bytes follow the Q1 / packet recipe: RFC 8785 JCS; UTF-8; no
BOM; no insignificant whitespace; object keys sorted by the lexicographic
order of their names compared as UTF-16 code units (RFC 8785 §3.2.3);
JSON `null` for nulls; integers in shortest decimal form; no trailing
newline. Equivalent Python for this restricted ASCII identity shape
(Basic Multilingual Plane code points match UTF-16 code units):

```text
json.dumps(identity, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False).encode('utf-8')
```

Pretty-printed JSON, spaced separators, omitted null keys, or hashing a
display label are not this recipe.

**Excluded from pair identity:** `display_label`, file paths, GitHub
numbers, golden-artifact bytes, capability-manifest dimensions, and the
consuming `engine_build_id`.

`pair_id` is `u7a_` plus the lowercase hex SHA-256 digest.

Worked fixture (planning pins, not a live build). Canonical UTF-8:

```text
{"content_set_version":"946","owner_faction_id":"chaos-daemons","producing_engine_build_id":"warhammer40k-core-v2:runtime-tree-sha256-v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

`pair_id`: `u7a_8efecd9dfdc697e40abfc69c95bd2878f1ba22861e28658384602e3332c08676`

Changing only a carried `display_label` must not change that digest.
Changing `content_set_version` or `owner_faction_id` must.

### 7.3 Verification envelope

The pair is not coverage. Coverage is a verification envelope regenerated
and re-verified on **every consuming build that claims it**. A failed or
absent envelope is not covered. Each envelope covers **one** pair (one
producing build, one owner, one content-set version) on one consuming
build. Two producing builds of the same owner/version are two envelopes
and two Q1 `producer_coverage` entries (Q1 §5.1.1).

Envelope identity (every key present):

| Key | Value |
| --- | --- |
| `pair_id` | Pair digest from §7.2 |
| `consuming_engine_build_id` | The claiming build |
| `result` | Literal `certified` |
| `golden_artifacts` | Sorted content bindings of the goldens actually replayed |

Each `golden_artifacts` element (every key present), sorted by
`artifact_id`:

| Key | Value |
| --- | --- |
| `artifact_id` | Human-readable retained-artifact name; not a content digest |
| `artifact_sha256` | 64 lowercase hex SHA-256 of the retained golden bytes |
| `exported_by_engine_build_id` | The producing `engine_build_id` that exported those bytes |

`artifact_id` alone is not a content binding. Replacing retained bytes
while keeping the same `artifact_id` must change `artifact_sha256` and
therefore the envelope citation. `display_label` is excluded from
envelope identity.

`u7a_record_citation` (the value one Q1 `producer_coverage` entry stores)
is `u7aenv_` plus the lowercase hex SHA-256 digest of that envelope. It
is not a version-level scalar.

Worked fixture. Canonical UTF-8:

```text
{"consuming_engine_build_id":"warhammer40k-core-v2:runtime-tree-sha256-v1:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","golden_artifacts":[{"artifact_id":"golden_chaos-daemons_946_retired_handler","artifact_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","exported_by_engine_build_id":"warhammer40k-core-v2:runtime-tree-sha256-v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],"pair_id":"u7a_8efecd9dfdc697e40abfc69c95bd2878f1ba22861e28658384602e3332c08676","result":"certified"}
```

`u7a_record_citation`: `u7aenv_8df530c606630106c66d2b02c40248574ad791bf3ff3a33ea997837cecb26913`

The `aaaa…` / `bbbb…` / `cccc…` pins are fixture bytes. FM0 uses real
`engine_build_id` values and goldens actually exported by the producing
build. Storing `result: certified` without those bindings is invalid.

An envelope may exist only when the named `content_set_version` is
packaged on the consuming build as current or previous for that owner.
Certification of an unpackaged version is invalid.

### 7.4 Golden artifact requirements

Certification is established by replaying retained golden artifacts
**actually exported by the producing build** under the consuming build
with exact equality of:

- decision records;
- event log;
- RNG state;
- viewer-scoped checkpoints for both players and the operator;
- final state hash.

Before comparing those results the verifier must:

1. resolve each `artifact_id` to retained bytes;
2. reject the envelope when `sha256(bytes)` is not the cited
   `artifact_sha256`;
3. reject the envelope when `exported_by_engine_build_id` is not the
   pair's `producing_engine_build_id`;
4. only then replay and compare.

A symbolic ID with drifted bytes is not this evidence.

Acceptance evidence for the FM0 U7a implementation, and for every later
transition that packages a new content set:

1. A golden exported by the actual V build, containing a rule retired at
   V+1 (a justified named handler where one exists), reproduces exactly
   under the V+1 build.
2. The retired content executes in that V replay.
3. The same content is rejected with a typed reason in a new V+1
   current-version roster.
4. A deliberately uncovered `(producing_engine_build_id, owner_faction_id,
   content_set_version)` triple fails closed.

Synthesizing the golden on the consuming build is not this evidence.

### 7.5 Fail-closed fallback

A replay whose participating triples are not all covered fails with a
typed error naming the producing `engine_build_id`, each missing
`(owner_faction_id, content_set_version)`, and the repository tag that
has the exact producing build. The exact-build deployment is the only
route for that artifact.

Q1 records that miss on the **producer** entry: omit the producer, or
store `replay_compatibility: exact_build_only` and
`u7a_record_citation: null` for that `producing_engine_build_id` only.
Sibling `producer_coverage` entries for other producing builds stay.
The version-level summary stays `certified` when any other producer
entry is `certified`; it becomes `exact_build_only` only when no
producer entry is `certified`. Packaging alone must not write
`certified` on a producer entry or on the summary.

Until the FM0 U7a implementation merges, every packaged previous version
is `exact_build_only` and no previous-version replayability is claimed.
S3c must not switch catalog generation before that implementation.

### 7.6 Phase 18L unchanged

Operator persistence recovery keeps its exact `engine_build_id`
requirement. U7a applies to historical replay only. A Phase 18L snapshot
from another build is rejected even when a U7a envelope exists for the
same content-set versions.

### 7.7 Cross-build coverage check

A consuming build may load a historical replay when **all** of the
following hold:

1. Every named `content_set_version` is packaged for that owner (U7).
2. Every participating pair has a `certified` envelope on this consuming
   `engine_build_id` (U7a).
3. Q1 stores a `producer_coverage` entry for that exact
   `producing_engine_build_id` with `replay_compatibility: certified`
   and that envelope's citation. The version-level summary must not
   substitute for this lookup.
4. The load is not Phase 18L recovery.

Same-build replay skips (2) and (3) and still requires (1) and (4).

## 8. Writers and precedence

| Writer | May write | Must not |
| --- | --- | --- |
| Certification event (`-b` close) | Q1 `first_certified_at_content_set` | Package N−1; write `certified`; write an envelope |
| U7 packaging (FM0) | Inventory current / previous / dropped tag | Write Q1 labels; load staging; package N−1 while first-certified is null |
| U7a verification (FM0) | Envelope; one Q1 `producer_coverage` entry plus the derived version summary | Ignore `producing_engine_build_id`; certify an unpackaged version; certify without content-bound goldens; collapse two producers into one citation |
| U5 tombstone | Current-version mustering rejection | Unpackage a still-retained previous version; delete referenced Python |
| U4 / packets / Q1 status claims | Layer tuples and reviews | Package content; write envelopes |
| Guides, audits, capability manifest | nothing | Any packaging slot or U7a result |

Precedence:

1. Missing packaged version always fails, even if an envelope exists.
2. Cross-build replay without a verified envelope always fails, even if
   the version is packaged.
3. `first_certified_at_content_set` JSON `null` forbids a previous slot,
   even if someone writes an envelope.
4. U4 demotion still wins over a Q1 `status_claim` (Q1 §8.2). U7a does
   not restore Layer A or C.
5. Phase 18L exact-build rejection wins over a U7a envelope.

## 9. Contract change (FM0, not this PR)

The FM0 U7a implementation amends `contracts/` and
`ADAPTER_DECISION_CONTRACT.md` in the same PR as the record, verification,
fail-closed behaviour, and conformance scenarios. That PR is a
prerequisite of S3c.

This design PR does not edit those live files. A content packet still must
not list the adapter contract as an allowed file (packet schema §6).

Track D D3's live agent-contract rewrite remains a separate FM0 PR. It
consumes the packet schema; it does not consume this inventory.

## 10. Acceptance fixtures

Implementation tests when packaging, loaders, and the U7a contract land.
This PR only defines them.

1. Orks at FM0.5 keep `first_certified_at_content_set` null. Packaged
   Orks content is 946 only. 931 is absent from `{current, previous}`.
2. Writing `first_certified_at_content_set` for Chaos Daemons at 946
   leaves `previous_content_set_version` JSON `null`. 931 is not packaged.
3. After a later Chaos Daemons 960 transition, current is 960 and
   previous is 946. Q1 `producer_coverage` is empty and the version
   summary is `exact_build_only` until a producer entry exists.
4. After a later 970 transition, current is 970 and previous is 960.
   946 is dropped. A replay naming Chaos Daemons 946 fails closed and
   names `available_at_git_tag`.
5. A mixed game naming Aeldari 946 and Orks 960 is valid only when each
   named version is in that owner's window. Orks still cannot name 931.
6. Ynnari listing of a shared Aeldari page does not create a Ynnari
   previous slot for that page. A Ynnari-owned datasheet uses the
   `ynnari` window.
7. A Space Marines chapter overlay does not add a second packaged
   version. Grey Knights stays on its own window.
8. A handler referenced only by packaged previous 946 is retained. After
   946 is dropped and no remaining packaged version references it, Q2
   may delete it.
9. More Dakka! is rejected from a current 946 roster and still executes
   in a packaged previous-version replay once such a window exists. The
   tombstone does not package 931 by itself.
10. Packaging 946 as previous without a verified envelope must not write
    a `certified` producer entry or a `certified` version summary.
11. The worked `pair_id` and `u7a_record_citation` must match across
    implementations of the published canonical bytes. Changing only
    `display_label` leaves both digests unchanged.
12. An envelope that omits `artifact_sha256`, names an unpackaged
    version, stores `certified` after a failed replay, or cites
    `exported_by_engine_build_id` other than the pair's producer is
    rejected.
13. A V golden containing a rule retired at V+1 reproduces under the V+1
    build; the V+1 current roster rejects that rule with a typed reason.
14. A deliberately uncovered triple fails closed naming the producing
    build and the tag that has it. That miss must not erase or borrow a
    sibling producer entry.
15. Phase 18L recovery of a snapshot from producing build `aaaa…` on
    consuming build `bbbb…` is rejected even when fixture 13's envelope
    exists.
16. S3c catalog-generation switch is unpublished while the FM0 U7a
    implementation is unmerged. Committed replays stay exact-build or
    use a recorded per-fixture justification.
17. An open `missing_geometry` blocker prevents `-b` close. The
    inventory previous slot stays JSON `null`.
18. Staging `blocked_provenance` never appears in the packaging
    inventory and never becomes a participating `content_set_version`.
19. On consuming build `bbbb…`, Chaos Daemons 946 has certified
    envelopes for producers `aaaa…` (`u7a_8efecd9d…` /
    `u7aenv_8df530c6…`) and `eeee…` (`u7a_f0e6e4e4…` /
    `u7aenv_3029542e…`). Producer `9999…` has no entry. Loads from
    `aaaa…` and `eeee…` succeed by those citations. A load from
    `9999…` fails closed. Both certified entries remain. The version
    summary is `certified` and must not authorize the `9999…` load.
20. Replacing the retained bytes of
    `golden_chaos-daemons_946_retired_handler` so the digest becomes
    `dddd…` while the `artifact_id` is unchanged yields citation
    `u7aenv_559afc6b…`, not `u7aenv_8df530c6…`. The verifier rejects
    the original envelope against the new bytes. Changing only
    `display_label` leaves both published citations unchanged.

## 11. Mapping exercise (not packaged content)

Planning examples. FM0 emits the real inventory and envelopes. This PR
does not.

| Sample | U7 / U7a fact | Notes |
| --- | --- | --- |
| Orks @ FM0.5 | Current 946; previous null; first-certified null | 931 is S1 / S4 tooling, not loadable |
| Chaos Daemons @ FM1-b | Current 946; previous null; first-certified 946 | Event is not N−1 |
| Chaos Daemons after 960 | Current 960; previous 946; empty `producer_coverage`; summary `exact_build_only` | A later envelope writes one producer entry |
| Chaos Daemons 946 two producers | Entries for `aaaa…` and `eeee…`; `9999…` absent | Fixture 19; summary `certified` is not a load key |
| Chaos Daemons after 970 | Current 970; previous 960; 946 dropped | Fail-closed names the 946 tag |
| Mixed Aeldari 946 + Orks 960 | Both versions named on the config | Cannot infer Orks from Aeldari |
| Ynnari shared page | `aeldari` window | Listing view is not the window |
| Space Marines chapter overlay | One `space-marines` window | Overlay is not a second package |
| More Dakka! @ 946 | Current mustering blocker | Historical execution waits on a real previous slot |
| Named handler retired at V+1 | Retained while V is packaged | Q2 union; fixture 13 |
| Phase 18L snapshot | Exact build | U7a does not apply |
| Autarch `overall: Playable` | Not a packaged version | Q1 fixture 6; not this inventory |

Do not publish a histogram of all 40 admitted views as inventory rows
here.

## 12. Gap list for later work

### 12.1 Surfaces that exist and must not be forked

S2 `owner_faction_id`, Q1 certification and coverage labels, U5
tombstone semantics, Q2 parity, the existing `engine_build_id`, Phase
18L exact-build recovery, and the L0–L8 ladder already exist. This
document indexes them.

### 12.2 Work that remains later (not this PR)

- Packaging inventory generator and loaders
- U7a hashed record, contract amendments, conformance scenarios, and
  golden-artifact fixture
- S3c catalog-generation switch (blocked on that U7a implementation)
- Q1 generator and live artifact (schema already delivered)
- U4 runtime invalidation
- U1 capture, U5 tombstone loaders, U6 rewrite runner, Q6 CI
  (cadence delivered in [U8_RUNBOOK.md](U8_RUNBOOK.md))
- Live adapter-contract or agent-contract edits
- Catalog ID allocation

### 12.3 Families this design must not steal

- Identity and locators remain S2
- WHEN, EFFECT, TARGET, construction, ledgers, decisions remain T1–T6
- Diff grain, classes, and layers remain U2–U4
- Packet identity and surfaces remain the packet schema
- Status rows, reviews, and coverage *labels* remain Q1
- F00 page retention remains S1
- Extraction remains S3a
- Viewer redaction remains the shared adapters module
- Phase 18L recovery remains exact-build persistence

## 13. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| U7 packaging | Inventory generator and version-aware loader | Loadable N−1 after the first post-certification transition |
| U7a implementation | Record, contracts, goldens, conformance | Q1 `certified`; S3c |
| U-HOLD-ORKS-S4-COUNTS | Exact 20/73 S4 integers | S1 fixture, then S4; still not a loadable 931 package |
| U8 runbook | Capture → diff → classify → packets → regenerate | delivered in [U8_RUNBOOK.md](U8_RUNBOOK.md); tools remain FM0 |
| D1 / Q6 | Generated guides and freshness CI | F-DOC-01 implementation |

## 14. What "U7 / U7a design delivered" means

FM0 packaging and compatibility work may be implemented. It has:

- per-`owner_faction_id` current-plus-one-previous windows;
- certification event distinct from N−1 packaging;
- N−1 activation on the next content-set transition;
- game/replay identity as `engine_build_id` plus per-owner versions;
- fail-closed missing version naming the git tag;
- Q2 handler union over packaged versions;
- tombstones limited to current-version mustering;
- pair and envelope identity projections with published canonical bytes;
- Q1 `certified` only via per-producer envelope citations;
- golden bindings pin retained bytes, not symbolic IDs alone;
- Phase 18L kept on exact `engine_build_id`;
- twenty acceptance fixtures;
- a mapping exercise that does not package content.

This survey does not add a loader, live inventory, live compatibility
record, contract amendment, `src/` files, or catalog IDs. FM0 implements
those from retained pages and reconciles them with this document.
