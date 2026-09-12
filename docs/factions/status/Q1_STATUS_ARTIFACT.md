# Q1 status-artifact schema

[Status index](README.md) · [Classification system](../updates/U_CLASSIFICATION_SYSTEM.md) · [Packet schema](../updates/U_PACKET_SCHEMA.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md) · [Phase 17O capability manifest](../../ADAPTER_DECISION_CONTRACT.md#phase-17o-capability-manifest)

This document is Track Q item Q1 as **FM-pre planning evidence**. It closes
the generated `content_status` schema FM0 must emit. It does not generate
that artifact, rewrite guides or audits, edit the live capability-manifest
schema, implement U4 invalidation, emit packets, or change `src/`, catalogs,
F00, or live adapter/agent contracts.

Machine-readable catalog: [`q1_status_artifact.json`](q1_status_artifact.json).

Owner **D3** (content-set retention) and **U7a** (replay mechanism) are not
this document. Q1 stores the certification event and the coverage *labels*
those later designs consume.

## 1. Purpose and delivery contract

Classification named **what changed** and **which layers go stale**. Packets
named **what work that produces**. This document names **where the resulting
claims persist**.

One generated artifact is the only denominator for:

- the L0–L8 ladder and orthogonal freshness;
- per-layer U4 evidence tuples;
- `blocked_provenance` staging observations, kept off admitted rows;
- per-faction `first_certified_at_content_set`;
- replay-compatibility coverage of every packaged version (`certified` or
  `exact_build_only`).

Guides, audits, and the Phase 17O capability manifest **derive** from it.
They do not write it. Hand-maintained status and mixed coverage labels are
the F-EVID-01 / F-DOC-01 failure mode.

**FM0 implements the generator, typed loader, and U4 invalidation.** It must
not treat a new transcription hash as Layer A current, assert `current`
while a layer is `stale`, count a staging observation as L0, copy a
historical `Playable` component label into L7, or mint `catalog_id` from a
display name. Retention packaging, the U7a record, U8 cadence, and Q6 CI
remain later.

T1–T3 still own WHEN, EFFECT, and TARGET atoms cited inside a Layer A
fingerprint. T4 still owns construction families cited by Layer B. T5 still
owns ledgers. T6 still owns decision shape. S2 still owns identity. U2–U4
still own grain, classes, and demotion. Packets still own work. This
document only stores **claims**.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Ladder | [Content model and status ladder](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates) L0–L8 plus Staging |
| Layer tuples | [U4](../updates/U_CLASSIFICATION_SYSTEM.md#4-closed-layers-u4) A/B/C |
| Packet writers | [U3 packet schema](../updates/U_PACKET_SCHEMA.md) `status_claim` and `review_record` |
| Four coverage inputs | [Repository evidence](../../FACTION_AUDIT_SOURCES.md#repository-evidence) |

This document does not copy bulk operative text. Community teasers are not
F00 observations. 39k.pro IDs are not `catalog_id`.

## 3. Closed grain

### 3.1 One artifact

One repository has one generated `content_status` document at a time. It is
not a guide, an audit, a module-status rollup, a selected-game capability
manifest, or a Python scaffold list.

FM0 emits it as a versioned data artifact plus a typed fail-fast loader. This
PR does not choose the final packaged path and does not add a loader.

### 3.2 One admitted entity row

One admitted row is one S2 catalog entity at one content-set version:

| Field | Role |
| --- | --- |
| `row_id` | Deterministic ID from §4.1 |
| `catalog_id` | S2 runtime identity. Never `unallocated` on an admitted row |
| `entity_kind` | S2 kind |
| `content_set_version` | App-data version of this row |
| `attained_level` | Highest ladder level whose prerequisites are all current (§6) |
| `freshness` | `current`, `stale`, or `retired` |
| `layers` | U4 A/B/C tuples (§7) |
| `open_blockers` | Typed blocker IDs, not display names |
| `contributing_packet_ids` | Packet citations only |

A page URL, update-feed line, display name, reporting group, Python module
path, or historical `overall: Playable` cell is not a row. Army of Faith's
four Enhancements are four rows once allocated. Eldrad at 931 and Eldrad at
946 are two rows.

`display_label` may be stored for humans. It is never the join key.

### 3.3 Staging is not a row

An observation without registered official provenance is a
`blocked_provenance` staging record (§5.2). It:

- never appears in `entity_rows`;
- never receives L0 or any higher level;
- never counts toward per-level totals;
- may inform packets and the demand matrix as planning evidence.

Admission requires the F00 official-artifact registration already required
by S3a. A staging marker never becomes evidence by default.

### 3.4 Splits this grain must not flatten

| Flattened token | Published split |
| --- | --- |
| Historical `Playable` / `E` / `Source` / module `implemented` | Separate input facts; only Q1 ladder + freshness are publishable claims |
| One faction guide | Many entity rows plus one `faction_index` entry |
| Selected-game capability manifest | Derived, viewer-scoped projection; not this artifact |
| Union A/B/C demotion | One row with three layer tuples, not one merged packet |
| `faction_rewrite` | Overlay freshness on the faction index **plus** per-entity rows |
| Packaged previous version | A second `content_set_version` of the same `catalog_id` |
| `certified` replay coverage | U7a record citation; default remains `exact_build_only` |

## 4. Identity projections

Q1 hashes **identity projections**, not display bindings and not the full
row body. Canonical bytes follow the packet-schema recipe: RFC 8785 JCS;
UTF-8; no BOM; no insignificant whitespace; object keys sorted by the
lexicographic order of their names compared as UTF-16 code units (RFC 8785
§3.2.3); JSON `null` for nulls; integers in shortest decimal form; no
trailing newline. Equivalent Python for this restricted ASCII identity
shape (Basic Multilingual Plane code points match UTF-16 code units):

```text
json.dumps(identity, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False).encode('utf-8')
```

Pretty-printed JSON, spaced separators, omitted null keys, or hashing a
display label are not this recipe.

**Excluded from every Q1 identity object:** `display_label`,
`parent_app_canonical_url`, `listing_role`, file paths, GitHub numbers,
historical coverage labels, and capability-manifest dimensions.

### 4.1 `row_id`

Identity object (every key present):

| Key | Value |
| --- | --- |
| `catalog_id` | S2 `catalog_id` |
| `entity_kind` | S2 kind |
| `content_set_version` | App-data version string |

`row_id` is `row_` plus the lowercase hex SHA-256 digest.

Worked fixture (grandfathered Eldrad datasheet `000000568` at content-set
946; planning locator, not an allocation PR). Canonical UTF-8:

```text
{"catalog_id":"000000568","content_set_version":"946","entity_kind":"datasheet"}
```

`row_id`: `row_f3250e6e9c7c833315474ee8add92facd629910a922cf9c50848977eddadabb7`

Changing the carried `display_label` from `Eldrad Ulthran` to
`ELDRAD ULTHRAN` must not change that digest. Changing `content_set_version`
must.

### 4.2 `review_id`

A `review_record` persists here. An implementation packet may write the
specific kinds its remaining `required_work` authorizes (packet schema
§5 / §7.1), including Layer C re-attestation and Layer A recertification.
A `status_claim` is not a substitute.

Identity object (every key present):

| Key | Value |
| --- | --- |
| `packet_id` | Packet-schema `packet_id` |
| `review_kind` | Closed kind from §5.3 |
| `catalog_id` | S2 `catalog_id`, or the literal `unallocated` only for pre-admission reviews |
| `source_entry_locator` | `{parent_source_document_id, section_kind, ordinal_in_section}`, or JSON `null` when the review is faction-index scoped |
| `old_transcription_sha256` | 64 lowercase hex chars, or JSON `null` when the kind has no old hash |
| `new_transcription_sha256` | 64 lowercase hex chars, or JSON `null` when the kind has no new hash |

`ordinal_in_section` is a JSON number. Authentication hashes, URLs, and
labels are stored on the record; they are not identity.

`review_id` is `rev_` plus the lowercase hex SHA-256 digest.

Worked fixture (Eldrad `points_only` Layer A equivalence; synthetic
transcription pins; planning packet computed from the published packet
recipe). Packet canonical UTF-8:

```text
{"catalog_id":"000000568","field_path":"cost_rows","from_content_set":"931","impact_class":"points_only","origin_kind":"update_classifier","packet_kind":"implementation","source_entry_locator":{"ordinal_in_section":1,"parent_source_document_id":"faction-app:aeldari:datasheet:eldrad-ulthran","section_kind":"datasheet"},"to_content_set":"946"}
```

`packet_id`: `pkt_8c8f0a3a436b71a0c8800da378fef5d0c4c3e53c57e853044c736171896961c7`

Review canonical UTF-8:

```text
{"catalog_id":"000000568","new_transcription_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","old_transcription_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","packet_id":"pkt_8c8f0a3a436b71a0c8800da378fef5d0c4c3e53c57e853044c736171896961c7","review_kind":"layer_a_equivalence","source_entry_locator":{"ordinal_in_section":1,"parent_source_document_id":"faction-app:aeldari:datasheet:eldrad-ulthran","section_kind":"datasheet"}}
```

`review_id`: `rev_77074d425e6d6b87e6862a47457d3006d1025b9d1146fd0c1fec550a9615a38f`

The `aaaa…` / `bbbb…` pins are fixture bytes. FM0 uses retained F00
suffix hashes. Changing only `display_label` must not change `review_id`.

## 5. Closed collections

### 5.1 `faction_index`

One entry per S2 owner faction (reporting groups are not entries):

| Field | Role |
| --- | --- |
| `catalog_id` | Owner faction `catalog_id` |
| `first_certified_at_content_set` | App-data version string at the faction's `-b` close, or JSON `null` |
| `packaged_versions` | Every packaged content-set version of that faction |

Each packaged version carries:

| Field | Role |
| --- | --- |
| `content_set_version` | App-data version |
| `packaged` | Whether that version is in the current package |
| `replay_compatibility` | `certified` or `exact_build_only` |
| `u7a_record_citation` | Hash of the U7a record when `certified`; JSON `null` otherwise |

Writing `first_certified_at_content_set` records the certification event. It
does not package N−1 and does not create a U7a record. Until U7a certifies
a pair, every packaged previous version is `exact_build_only`.

### 5.2 `staging_observations`

| Field | Role |
| --- | --- |
| `source_entry_locator` | S2 locator; identity of the staging record |
| `display_label` | Human only |
| `blocker` | Literal `blocked_provenance` |
| `informs_packet_ids` | Optional packet citations |

No `attained_level`. No freshness other than the blocker.

### 5.3 `review_records`

Closed `review_kind` values:

| Kind | Written by | Stores |
| --- | --- | --- |
| `layer_a_equivalence` | Implementation packet with `layer_a_carry_forward_review`, or `editorial_equivalent` review packet | Old/new transcription pins and fingerprint-**unchanged** result |
| `recorded_equivalence` | `editorial_equivalent` review packet | Same pins as `layer_a_equivalence` when the class is editorial |
| `handler_identity_confirmation` | Same packets when a named handler exists | Handler ID equality |
| `layer_a_recertification` | Implementation packet whose remaining `required_work` includes `remap_envelope`, `remap_effect_ir`, or `recertify_l4_l8` | New transcription pin, **changed** fingerprint citations, mapping citation, and execution-evidence citation |
| `layer_c_reattest` | Packet whose remaining `required_work` includes `layer_c_reattest` or `recertify_l4_l8` | New content-set/build pins plus authorizing review or roster-validation citation |
| `human_attribution` | `unclassified_clause` review packet | Attribution result; may unblock a later class, never auto-carries Layer A |

**Two Layer A authorization routes** after a transcription change:

| Route | Review | Authorizes Layer A `current` when |
| --- | --- | --- |
| Carry-forward | `layer_a_equivalence` or `recorded_equivalence` with result `equivalent` | The semantic fingerprint is unchanged (points-only or editorial) |
| Re-certification | `layer_a_recertification` with result `recertified` | Fresh mapping and execution evidence establish the **changed** fingerprint at the new source/build context |

Re-certification must not claim fingerprint-unchanged and must not be
written as `layer_a_equivalence`. Carry-forward must not be used when the
classified class is `clause_envelope_changed` or `effect_ir_changed`.
Sibling `unclassified_clause` still forbids carry-forward kinds on the
points or composition packet (Bannernob). It also keeps Layer A `stale` on
that `catalog_id` until the unclassified packet is resolved; a sibling
points packet cannot recertify A to bypass that blocker.

Result values: `equivalent`, `not_equivalent`, `unclassified`,
`recertified`. Layer A `current` after a hash change requires `equivalent`
(carry-forward) or `recertified` (new fingerprint). A `status_claim` is
not either result.

### 5.4 `status_claims`

A claim is an audit of a requested layer or freshness transition. It is
not the tuple.

| Field | Role |
| --- | --- |
| `packet_id` | Writer |
| `catalog_id` / `content_set_version` | Target row |
| `layer` | `A`, `B`, `C`, or `freshness` |
| `from_state` / `to_state` | `current`, `stale`, `none`, `retired` |
| `authorizing_review_id` | Required when moving Layer A to `current` after a hash change; the cited review must be an `equivalent` carry-forward or a `recertified` new fingerprint |

Invalid claims (stale→current without an authorizing review; current while
U4 says stale; `equivalent` after a classified envelope or effect change;
L7 current from a historical `Playable` label) are rejected and do not
mutate the row.

### 5.5 `entity_rows`

Admitted rows only. Open blocker IDs are closed:

| ID | Meaning |
| --- | --- |
| `layer_a_stale` | Fingerprint change without recertification, unclassified clause, or missing carry-forward |
| `layer_b_stale` | Roster-legality element changed |
| `layer_c_stale` | Missing re-attestation on a new content-set or build identity |
| `unsupported_clause` | Typed unsupported at L4 |
| `missing_geometry` | L3 incomplete |
| `official_provenance` | Cannot admit (belongs on staging, not here) |
| `catalog_id_allocation` | Structural add not yet allocated |
| `family_gap` | Cited `family_gap` `packet_id`; Q1 does not mint T-family IDs |
| `retired_current_mustering` | Tombstone governs current-version mustering |

## 6. Ladder, freshness, and attained level

The ladder names in the roadmap are unchanged. Q1 does not add a ninth
level and does not rename Staging to L0.

| Level | Stored as | Requires |
| --- | --- | --- |
| Staging | `staging_observations` only | No official provenance |
| L0 | admitted row | Retained page, hashes, resolved identity, registered official provenance |
| L1 | admitted row | L0 plus typed loader acceptance |
| L2 | admitted row | L1 plus structured fields for that `entity_kind` |
| L3 | admitted row | L2 plus accepted geometry; non-datasheet kinds treat L3 as not applicable and skip it |
| L4 | admitted row | Prior plus Layer A mapped (`current` or explicitly `unsupported` per clause) |
| L5 | admitted row | L4 plus Layer A executable and `current` |
| L6 | admitted row | L5 plus Layer B `current` and the L6 roster evidence |
| L7 | admitted row | L6 plus Layer C `current` and one qualifying full game |
| L8 | admitted row | L7 plus complete variant/interaction coverage at this version |

Freshness is orthogonal to attained level:

| `freshness` | When |
| --- | --- |
| `current` | No required layer is `stale`, and the observation pin is the current admitted observation |
| `stale` | Any required layer is `stale`, or the observation drifted and is not yet classified |
| `retired` | Tombstone `retired_in` applies at this content-set version |

**Attained-level algorithm** (close it here; do not re-derive in guides):

1. Staging records do not enter the algorithm.
2. Compute the highest level whose own evidence exists.
3. If Layer A is `stale` or `none` when L4+ is claimed, cap at L3 (or L2
   when L3 is not applicable).
4. If Layer B is `stale`, cap at L5.
5. If Layer C is `stale`, cap at L6.
6. `retired` freshness does not keep L6–L8 `current` for current-version
   mustering. Historical packaged versions keep their own rows.

A faction is fully supported at version V only when every non-retired
entity it owns or inherits is L8 and `current` at V. Reports show counts
per level and freshness. No single percentage is published.

## 7. Layer tuples

Q1 stores the U4 tuples. It does not redefine demotion. Provenance pins
are not a fourth layer.

### 7.1 Layer A

Provenance pins: source ID and the current observation's transcription
hash.

Semantic fingerprint citations (values owned elsewhere):

- effect RuleIR hash (T2);
- timing/window descriptor ID (T1);
- target, restriction, and bearer grammar IDs (T3);
- binding IDs and parameters;
- handler identity when a named handler exists.

`claim_state`: `current`, `stale`, or `none`.
`carry_forward_review_id`: a carry-forward `review_id`, or JSON `null`.
`recertification_review_id`: a `layer_a_recertification` `review_id`, or
JSON `null`. At most one of those two IDs authorizes a given transition.

A new transcription hash leaves Layer A `stale` until **one** of the §5.3
routes authorizes it: an `equivalent` carry-forward of the unchanged
fingerprint, or a `recertified` new fingerprint with mapping and execution
evidence. Equality of effect RuleIR alone never proves equivalence. An
`equivalent` result is invalid when the classified class changed the
fingerprint (`clause_envelope_changed`, `effect_ir_changed`).

### 7.2 Layer B

Citations: cost-rows hash; composition hash; wargear/options hash;
keywords hash; Leader/Support hash; army-construction constraint hash
(T4); geometry evidence IDs.

`points_only` refreshes the cost-rows hash and sets Layer B `stale` until
roster validation; Layer A may stay `current` only with the review in
§7.1.

### 7.3 Layer C

Citations: digest of the current A and B tuples of every entity in the
certified rosters and interactions; `content_set_version`;
`engine_build_id`; `reattest_review_id`.

Carry-forward of A, preservation of A while refreshing B, or
re-certification of A never keeps L7/L8 `current` on a new content-set or
build identity until a `layer_c_reattest` review exists. Writing that
review does not make Layer C `current` while Layer A or B is `stale`. The
writer is the packet whose remaining `required_work` includes
`layer_c_reattest` or `recertify_l4_l8` (packet schema §5).

## 8. Writers and precedence

### 8.1 Who may write

| Writer | May write | Must not |
| --- | --- | --- |
| U4 invalidation (engine, FM0) | Layer demotion to `stale`; freshness `stale` | Invent a carry-forward review; assert `current` |
| Packet `review_record` | The review kinds mapped from that packet's remaining `required_work` (carry-forward, recertification, Layer C re-attest, attribution) | Write Layer A current by status claim alone; write carry-forward when a sibling `unclassified_clause` forbids it; write `layer_a_equivalence` after a classified fingerprint change |
| Packet `status_claim` | A transition authorized by U4 plus any required review | Assert `current` while the tuple is `stale`; write Q1 schema; write `first_certified_at_content_set` |
| Certification event (`-b` close) | `first_certified_at_content_set` | Package N−1; write `replay_compatibility: certified` |
| U7a (later design) | `replay_compatibility: certified` plus a citation | Ignore `engine_build_id`; claim replayability from packaging alone |
| Guides, audits, capability manifest | nothing | Any Q1 field |
| The four coverage artifacts | nothing as authority | L7/L8 `current`; Layer A `current` |

### 8.2 Precedence

1. U4 demotion always wins over a packet `status_claim`.
2. A Layer A `current` claim after a transcription change requires an
   authorizing review on the same locator: `equivalent` carry-forward **or**
   `recertified` new fingerprint. Missing authorization is rejected.
   `equivalent` after `clause_envelope_changed` or `effect_ir_changed` is
   rejected.
3. Sibling `unclassified_clause` removes carry-forward permission; Q1
   rejects that `layer_a_equivalence` write. It does not let a sibling
   points or composition packet recertify Layer A, and it does not make
   Layer C `current` while A is `stale`.
4. Historical coverage labels never win over a Q1 tuple.
5. A derived capability-manifest dimension must not be true when the
   corresponding Q1 claim is `stale` or absent.
6. `blocked_provenance` never appears on `entity_rows`.

## 9. Four coverage artifacts

Named in [FACTION_AUDIT_SOURCES.md](../../FACTION_AUDIT_SOURCES.md):

| Artifact | Input fact | Retired as |
| --- | --- | --- |
| `data/generated/ability_coverage/datasheet_support_rows.json` | Historical component rollup, including `overall: Playable` | Authority for L6–L8 or fieldable/playable |
| `data/generated/ability_coverage/ability_coverage_rows.json` | Per-ability consumers and stages | Authority for Layer A `current` or L5 |
| `data/generated/ability_coverage/runtime_content_semantic_coverage.json` | Module/execution classification (debt item 7) | Authority for entity ladder or freshness |
| `data/source_manifests/faction_pack_datasheet_review_v1.json` | Reviewed official PDF scope | Execution or certification |

`faction_coverage_2026_27.coverage_rows()` remains a fifth input stream that
already separates execution classification from source
`runtime_support_status`. It is not a sixth publishable denominator.

F-EVID-01 on paper: module status, source labels, execution classifications,
and component labels stay distinct input columns. Only Q1's ladder,
freshness, and layer tuples are publishable claims.

## 10. Derived outputs

D1 still owns guide generation. This schema only locks the read model.

| Output | May read | Must not |
| --- | --- | --- |
| Guides and audits | `attained_level`, `freshness`, blockers, review citations | Assert `current` when Q1 is `stale`; mix `E`/`Playable` as L7 |
| Phase 17O capability manifest | Q1 as an upper bound for the selected game's entities | Write Q1; exceed a stale or absent claim; treat Q1 as viewer-scoped game state |

Q1 is omniscient repository status. Viewer-scoped redaction stays in the
existing adapters module. Q1 must not store hidden opponent game state.

Manifest dimensions this schema bounds (it does not rewrite the live
schema):

| Dimension | Q1 upper bound |
| --- | --- |
| `LOADABLE` | L1 `current` |
| `MUSTERABLE` | L6 `current` |
| `PHYSICALLY_PLAYABLE` | L3 satisfied and L6 `current` |
| `SEMANTICALLY_EXECUTABLE` | L5 `current` |
| `FULL_GAME_SUPPORTED` | L7 `current` |
| `REPLAY_VERIFIED` | L7 `current` plus replay evidence at this build |

`DISPLAYABLE` and `NETWORK_SAFE` remain Phase 17O-owned. They may read Q1
blockers; Q1 does not redefine them. Selected-game `REPLAY_VERIFIED` is not
U7a cross-build `certified`.

## 11. Acceptance fixtures

Implementation tests when the Q1 generator and U4 invalidation land. This
PR only defines them.

1. A `blocked_provenance` observation appears only in
   `staging_observations`. It is absent from `entity_rows` and from L0
   counts.
2. Eldrad `points_only` stores a `layer_a_equivalence` `review_record` on
   the implementation packet, keeps Layer A `current`, sets Layer B `stale`
   until roster validation, and leaves Layer C `stale` until
   `layer_c_reattest`. A `status_claim` alone must not set Layer A or C
   `current`.
3. Bannernob's points packet cannot write `layer_a_equivalence` while the
   sibling `unclassified_clause` packet is open. Layers A and C stay
   `stale`.
4. Acts of Faith `clause_envelope_changed` on `clause.timing` sets Layer A
   and C `stale` and caps `attained_level` at L2 (army-rule row; L3 is
   not applicable). Layer B is unchanged.
5. A guide or audit asserting `current` while the row is `stale` is
   invalid.
6. `overall: Playable` on `datasheet_support_rows.json` must not write L7
   or `FULL_GAME_SUPPORTED`.
7. Orks at FM0.5 keep `first_certified_at_content_set` null. No previous
   Orks version is listed as packaged loadable content.
8. A packaged previous version without a U7a citation is
   `exact_build_only`. Packaging alone must not write `certified`.
9. Changing only `display_label` leaves `row_id` and `review_id`
   unchanged. The Eldrad worked-fixture digests must match across
   implementations of the published canonical bytes.
10. A capability-manifest dimension that is true while the bounding Q1
    claim is `stale` is invalid. The manifest still does not write Q1.
11. Ghazghkull keeps one row with A, B, and C `stale` (union). Completing
    composition work must not clear the unclassified Layer A blocker.
12. `faction_rewrite` on Orks v946 stale-marks owned and inherited entities
    without deleting per-entity rows.
13. A `status_claim` of Layer A `current` after a transcription change
    without an authorizing review is rejected. An `equivalent` carry-forward
    that asserts fingerprint-unchanged after `clause_envelope_changed` or
    `effect_ir_changed` is also rejected. Either authorized route in §5.3
    may succeed.
14. Pre-allocation structural adds stay on staging or carry
    `catalog_id_allocation`; they must not appear as admitted rows with a
    display-name `catalog_id`.
15. Acts of Faith after remapping to turn-start: a `layer_a_recertification`
    review cites the changed timing fingerprint plus mapping and execution
    evidence. Layer A becomes `current`. Layer C stays `stale` until its
    own `layer_c_reattest`. The review must not store a fingerprint-unchanged
    result.
16. A `construction_constraint` packet (Blitz Brigade DP 2→1) writes
    `layer_c_reattest` after mustering validation. Layer A stays `current`
    without a carry-forward review. That write is not Layer A
    recertification and does not restore carry-forward on a Bannernob
    sibling.
17. A datasheet row whose Layer A is `stale` caps `attained_level` at L3
    even when earlier L4–L8 evidence exists (Eldrad without an authorizing
    A review). This is the datasheet counterpart of fixture 4.

## 12. Mapping exercise (not a generated artifact)

Planning examples. FM0 emits the real `content_status`. This PR does not.

| Sample | Q1 fact | Notes |
| --- | --- | --- |
| Eldrad 130→120 | Admitted row `000000568` @ 946; Layer A current only with `rev_77074d42…`; B/C stale until validation and re-attest | Coverage artifact `chaos-daemons-bridge-catalog` / `Playable` is input, not the row |
| Eldrad Leader list | Same `catalog_id`, different field path on a **packet**; same Q1 row refreshes Layer B | Attachment is Layer B; packet may write `layer_c_reattest` |
| Bannernob | One row; A+B+C stale; no points-packet carry-forward | Union, not a merge; C review cannot make C current while A is stale |
| Ghazghkull | One row; composition does not clear unclassified A | Three packets, one row |
| Acts of Faith trigger | Army-rule row; A+C stale; cap L2 | F-ARMY-01; later `layer_a_recertification` restores A only |
| Blitz Brigade DP 2→1 | Layer A current; B then C after validation and `layer_c_reattest` | `construction_constraint`; no A remap |
| Brute Bosses | Staging until official provenance and catalog ID | Not L0 |
| More Dakka! @ 946 | `freshness: retired`; current-version mustering blocker | Historical 931 row is a different `content_set_version` |
| Orks faction index @ FM0.5 | `first_certified_at_content_set: null` | Rewrite overlay does not certify |
| Chaos Daemons heights | Open `missing_geometry` blockers | Known FM1-a→FM1-b obligations stay on the row |
| Autarch `overall: Playable` | Not written into Q1 | Fixture 6 |

Do not publish a histogram of all 982 datasheet URLs as status rows here.

## 13. Gap list for later work

### 13.1 Surfaces that exist and must not be forked

The L0–L8 ladder, U4 tuples, S2 locators, packet `status_claim` /
`review_record`, F00 official provenance, and the Phase 17O manifest
already exist. Q1 indexes them.

### 13.2 Work that remains later (not this PR)

- Q1 generator, loader, and live artifact
- U4 runtime invalidation
- D1 guide generation from Q1
- Q6 freshness CI
- Owner D3 / U7 / U7a retention and replay mechanism
- U8 runbook
- Live adapter-contract or agent-contract edits
- Catalog ID allocation

### 13.3 Families this schema must not steal

- Identity and locators remain S2
- WHEN, EFFECT, TARGET, construction, ledgers, decisions remain T1–T6
- Diff grain, classes, and layers remain U2–U4
- Packet identity and surfaces remain the packet schema
- F00 page retention remains S1
- Extraction remains S3a
- Replay compatibility mechanism remains U7a
- Viewer redaction remains the shared adapters module

## 14. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| Q1 generator | Actual emission and loader | FM0 Q1 |
| U4 invalidation | Engine writer of demotion | FM0 U4 |
| U-HOLD-ORKS-S4-COUNTS | Exact 20/73 S4 integers | Per-entity Orks golden rows |
| U-HOLD-RULES-UPDATED | Dual-version clauses | Attribution reviews becoming envelope/effect claims |
| Owner D3 / U7a | Packaging N−1 and the compatibility record | `certified` coverage and previous-version rows as loadable content |
| D1 / Q6 | Generated guides and freshness CI | F-DOC-01 implementation |

## 15. What "Q1 schema delivered" means

FM0 status generation may be implemented. It has:

- one artifact and one admitted row per `catalog_id` plus content-set
  version;
- staging kept off the ladder;
- locator-only `row_id` / `review_id` projections and canonical bytes;
- stored U4 tuples with packet-written reviews;
- two Layer A routes (carry-forward vs recertification);
- writer precedence that rejects stale→current without authorization;
- the four coverage artifacts named as inputs, not authorities;
- derived-output bounds for guides and the capability manifest;
- seventeen acceptance fixtures;
- a mapping exercise that does not emit `content_status`.

This survey does not add a generator, live artifact, guide rewrite,
manifest schema change, `src/` files, or catalog IDs. FM0 implements those
from retained pages and reconciles them with this document.
