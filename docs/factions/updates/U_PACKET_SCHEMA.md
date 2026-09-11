# U3 packet schema — draft Track D agent contract

[Update-pipeline index](README.md) · [Classification system](U_CLASSIFICATION_SYSTEM.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [T6 decision-kind taxonomy](../taxonomy/T6_DECISION_KIND_VISIBILITY.md) · [Live agent contract](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This document is the **FM-pre packet schema**: the data-first work-packet
contract U3 will emit and Track C / Track G will reuse. It is the draft
replacement for the "Task Packet Format" section of
[FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md).
It does not rewrite that live contract, edit
[ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md), emit
packets, implement the U3 generator, or change `src/`, catalogs, F00, or
Q1. FM0 generates packets from retained pages and reconciles them with
this document; FM0 rewrites the live agent contract to consume it.

Machine-readable catalog: [`u_packet_schema.json`](u_packet_schema.json).

Owner **D3** (content-set retention: current plus previous after first
certification) is not this document. Track **D** item D3 (adapter contract
plus agent-contract rewrite) is. This PR drafts only the packet half of
Track D D3.

## 1. Purpose and delivery contract

Classification named **what changed** and **which layers go stale**. Packets
name **what work that produces**, **which surfaces may move**, and **what
must not be touched**.

A packet is not a page URL, an update-feed line, a display name, a GitHub
issue, a Python module path, or a whole detachment scaffold. Lifting the
live contract's "Implement Orks / War Horde" Python-file list over S2
`catalog_id` plus `source_entry_binding` plus a classified field path is
the T1-001 failure mode applied to work (S2-001 / U-001 applied to
packets).

**FM0 implements the packet generator and the live agent-contract
rewrite.** It must not emit one packet per page, one packet per scaffold
directory, or a content packet that lists the adapter contract as an
allowed file. Q1 schema, retention, U8, capture tooling, and the S4 tool
remain later.

T1–T3 still own WHEN, EFFECT, and TARGET atoms. T4 still owns construction
families. T5 still owns ledgers. T6 still owns submission kind and
visibility; a packet may *cite* a T6 delta ID, it must not mint
`decision_type` values. S2 still owns identity. U2–U4 still own diff
grain, classes, and layers. This document only contracts **work**.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Classification input | [U_CLASSIFICATION_SYSTEM.md](U_CLASSIFICATION_SYSTEM.md) closed grain, 12 classes, 3 layers, `clause.unattributed` |
| Mapping corpus | Same Orks 931→946 exercise as classification; not the S4 fixture |
| Live packet format being replaced | [FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md) "Task Packet Format" (Python scaffold allowlists) |
| Engine inspection | Read-only: AGENTS.md named-handler rubric, Track G two-consumer rule, T6 adapter-contract *deltas* |

This document does not copy bulk operative text. Community teasers are not
F00 observations. 39k.pro IDs are not `catalog_id`.

## 3. Closed grain

### 3.1 One packet

One packet is one unit of allowed work for one classified change, or one
generic-family gap, or one overlay:

| Field | Role |
| --- | --- |
| `packet_id` | Deterministic ID from §3.3. Not a GitHub number or display name |
| `origin_kind` | `update_classifier`, `certification_slice`, or `generic_family_demand` |
| `packet_kind` | Closed kind from §4 |
| `python_policy` | `none`, `named_handler_justified`, or `generic_family` |
| `source_diff_row` | U2 row when `origin_kind` is `update_classifier`; null for a pure family packet |
| `layers_demoted` | Copied from the class, then restricted by sibling rules in §6 |
| `required_work` | Closed work-item IDs from §5 |
| `forbidden_work` | Work the agent must not claim, including Layer A carry-forward when a sibling `unclassified_clause` exists |
| `allowed_surfaces` | Closed surfaces from §7 |
| `forbidden_surfaces` | Always include the denylist in §7.2 |
| `blocked_on` | Holds that keep the packet unpublished as implementation work |
| `depends_on` | Other `packet_id` values that must complete first |
| `t2_family_ids` / `t1_window_ids` / `t6_delta_ids` | Citations only; do not rename those catalogs |
| `named_handler_justification` | Required iff `python_policy` is `named_handler_justified` |
| `display_label` | Human only; never the join key |

`source_diff_row` is S2 `catalog_id` plus `entity_kind` plus
`source_entry_binding` plus `field_path` plus from/to content set plus
exactly one `impact_class`. Null `catalog_id` is legal only for
`structural_add` before FM0 allocation, keyed by `source_entry_binding`.

A certification-slice packet uses the same identity grain against the
demand matrix row it closes. It is not "implement this faction's Python
tree".

### 3.2 Splits this grain must not flatten

| Flattened token | Published split |
| --- | --- |
| Live "Implement Orks / War Horde" Python list | Many packets: detachment rule clauses, each Enhancement, each Stratagem, constraints |
| Update-feed URL or parent page | Many child packets; page provenance only |
| One GitHub PR | Optional `pr_group` metadata. A PR may contain many packets; it is not a packet |
| `faction_rewrite` | Overlay packet **plus** per-entity packets |
| Points plus "Rules Updated" | `points_only` implementation packet **and** `unclassified_clause` review packet |
| Cost plus composition plus Rules Updated | Three packets (Ghazghkull). Structural work does not erase review |
| Sibling Enhancements on one page | One packet each (`structural_add` does not demote siblings) |
| Inherited listing of the same binding | No extra packet |
| T6 "new decision" | `generic_family` packet citing `t6_delta_id`; content packets do not edit the adapter contract |
| Missing RuleIR template | `generic_family_demand` packet first; content packet `blocked_on` that family |

`pr_group` may help humans batch packets. It does not widen
`allowed_surfaces`. Work on a sibling identity remains out of scope even
when the sibling shares a PR.

### 3.3 `packet_id`

Canonical identity tuple, UTF-8 JSON object with sorted keys, SHA-256 hex
digest, prefixed `pkt_`:

- `origin_kind`
- `packet_kind`
- `from_content_set` / `to_content_set` (nulls allowed for non-update origins)
- `catalog_id` (or the literal `unallocated`)
- `source_entry_binding` object
- `field_path` (or the literal `overlay` / `family`)
- `impact_class` (or the family ID for `generic_family_demand`)

Do not hash display names, URLs, or file paths into `packet_id`.

## 4. Closed kinds and Python policy

| `packet_kind` | Meaning | Default `python_policy` |
| --- | --- | --- |
| `implementation` | Mutate allowed records, tests, and status claims for one classified row | `none` |
| `review` | Record a human classification or equivalence review; no semantic re-implementation | `none` |
| `overlay` | U6 faction-rewrite procedure; does not suppress child packets | `none` |
| `family_gap` | Track G generic family (RuleIR, hook, or decision surface) with a real consumer | `generic_family` |
| `observation_repin` | Re-pin transcription hash; no Layer A demotion | `none` |

`python_policy`:

| Policy | When | Production Python |
| --- | --- | --- |
| `none` | Default for content, review, overlay, and re-pin | Forbidden. Tests are allowed |
| `named_handler_justified` | AGENTS.md bespoke-subsystem rubric is met **and** the packet carries the seven justification fields | Only the named handler module listed on the packet |
| `generic_family` | This packet **is** the Track G family PR | Generic engine modules plus tests; two-consumer rule applies |

Content packets default to `none`. A content packet must not set
`generic_family` to smuggle engine work. A family packet must not bind a
faction catalog ID as its identity.

Named-handler packets must include, in the packet body:

1. bespoke-subsystem justification (unique resource, state machine, setup,
   or engine-level state that will not fit a generic surface);
2. generated source/execution IDs and deterministic handler ID;
3. lifecycle-loading coverage without manual injection;
4. replay/audit payload coverage;
5. unsupported/invalid diagnostics where semantics are partial;
6. handler-identity drift coverage;
7. named-handler budget/classification treatment.

Missing any of the seven makes the packet unpublished.

## 5. Impact class → packet mapping

One classified diff row produces one packet of the kind below. Additional
overlay or family packets are extra rows, not substitutes.

| `impact_class` | `packet_kind` | Default `required_work` | Default `forbidden_work` | Typical `blocked_on` |
| --- | --- | --- | --- | --- |
| `points_only` | `implementation` | `regenerate_cost_records`, `roster_validation`, `layer_a_carry_forward_review`, `layer_c_reattest` | semantic remap; new Python | sibling `unclassified_clause` removes `layer_a_carry_forward_review` from required and adds it to forbidden |
| `text_hash_equal` | `observation_repin` | `repin_observation` | any Layer A/B/C claim change | none |
| `editorial_equivalent` | `review` | `recorded_equivalence_review`, `layer_c_reattest` | automatic carry-forward; semantic remap | named-handler identity confirmation when a handler exists |
| `clause_envelope_changed` | `implementation` | `remap_envelope`, `recertify_l4_l8` | Layer A carry-forward | generic family if T1/T3 has no surface |
| `effect_ir_changed` | `implementation` | `remap_effect_ir`, `recertify_l4_l8` | Layer A carry-forward | generic family if T2 has no template |
| `unclassified_clause` | `review` | `human_attribution_review` | any implementation; any component path guess; Layer A carry-forward | `S3a` / `U-HOLD-RULES-UPDATED` |
| `structural_add` | `implementation` | `admit_or_stage_record`, `ladder_l0_l8` | Python unless a new family is required; demoting siblings | `official_provenance`, `catalog_id_allocation` |
| `structural_remove` | `implementation` | `write_tombstone`, `current_mustering_rejection` | deleting Python still referenced by a packaged version | U5 loaders (FM0) |
| `attachment_or_keyword` | `implementation` | `regenerate_attachment_or_keyword`, `fieldability_regression`, `layer_c_reattest` | Layer A remap | none unless clauses also changed |
| `construction_constraint` | `implementation` | `regenerate_t4_constraints`, `mustering_regression`, `layer_c_reattest` | treating DP as `points_only`; Layer A remap | Core P25C surfaces |
| `composition_or_options` | `implementation` | `regenerate_composition_or_options`, `fieldability_regression`, `layer_c_reattest` | treating size removal as `points_only` | none |
| `faction_rewrite` | `overlay` | `u6_rewrite_procedure` | suppressing per-entity packets | U6 runbook (later design) |

`layer_c_reattest` never silently preserves L7/L8 on a new content-set or
build identity. Until Q1 exists, packets still *require* that work item;
they do not invent the Q1 artifact.

## 6. Sibling, overlay, and family coupling

1. **Union is a Q1/U4 fact, not a packet merge.** Bannernob's A/B/C union
   does not become one packet. Emit `cost_rows`/`points_only` and
   `clause.unattributed`/`unclassified_clause` separately.
2. **Sibling unclassified forbids Layer A carry-forward** on every other
   packet for that `catalog_id` in the same from/to pair. The points or
   composition packet may still regenerate Layer B records.
3. **Known structural change does not erase review.** Ghazghkull keeps
   three packets. Completing composition work must not mark
   `clause.unattributed` done.
4. **`structural_add` does not include siblings.** Boss Boomer's packet
   `allowed_surfaces` must not list Targetin’ Gizmos.
5. **`faction_rewrite` overlay does not replace children.** Orks v946
   still emits More Dakka! `structural_remove`, added-detachment
   `structural_add`, and every classified field-path packet.
6. **Family before content.** If T2/T1/T6 has no executable surface, the
   content packet is `blocked_on` the `family_gap` packet. Do not put
   generic engine files on the content packet.
7. **Staging observations** may appear on packets as planning evidence.
   They cannot require L0 admission. `blocked_provenance` stays on the
   packet until official provenance is registered.
8. **Inherited listings** of the same `source_entry_binding` do not emit
   packets.

## 7. Surfaces

### 7.1 Allowed surfaces (closed)

| `allowed_surfaces` ID | May appear on | Must not |
| --- | --- | --- |
| `content_set_record` | `implementation`, `overlay` | Runtime Python; parsing page text |
| `tombstone_record` | `structural_remove` | Removing Python still referenced by a packaged version |
| `observation_pin` | `observation_repin`, reviews that re-pin hashes | Treating a new hash as Layer A |
| `review_record` | `review` | Inventing a component path |
| `status_claim` | any non-`observation_repin` packet | Writing a live Q1 schema in this PR; asserting `current` while `stale` |
| `focused_test` | all kinds | Importing other `test_*.py` modules; replacing `lifecycle.decision_controller` |
| `named_handler_module` | only `named_handler_justified` | Generic lifecycle branching on faction or display name |
| `generic_family_module` | only `family_gap` | Faction catalog IDs as the packet identity |
| `adapter_contract_delta` | only `family_gap` that cites a T6 delta | Content, review, overlay, or re-pin packets |

Exact content-set paths remain S3a's layout. Packets name **record
kinds** (`cost_rows`, `composition`, `army_construction`, clause
bindings), not speculative file trees.

### 7.2 Forbidden surfaces (every packet)

- `src/` runtime loader, lifecycle, bundle, or manifest machinery
- generic lifecycle modules branched on faction, detachment, Enhancement,
  Stratagem, display name, or source-text tokens
- [ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md)
  except a `family_gap` packet that cites `t6_delta_ids`
- F00 policy text and source-authority registry
- catalog ID minting from display names or App slugs
- army-list ID rewrites (grandfathered IDs stay resolvable)
- raw rule-text parsing in runtime modules
- the live Python scaffold allowlist as a substitute for this schema

The live agent contract's War Horde example lists
`rule.py` / `enhancements.py` / `stratagems.py`. Those paths are **not**
valid `allowed_surfaces` on a data-first packet.

## 8. Draft Track D D3 relationship

| Document | This PR | FM0 |
| --- | --- | --- |
| This schema | Delivered as planning evidence | Packet generator consumes it |
| [FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md) | Unchanged | Rewritten so Task Packet Format is this schema (records and bindings; Python only for a new family or a justified named handler) |
| [ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md) | Unchanged | Still updated in the same PR as any new family or decision kind |
| Owner D3 retention / U7a | Unchanged | Later design, then FM0 contracts |

A content-implementation PR that needs a new `decision_type` is invalid
under this schema. Split a `family_gap` packet first.

## 9. Acceptance fixtures

Implementation tests when the U3 generator and live contract rewrite land.
This PR only defines them.

1. A packet whose `allowed_surfaces` are the live War Horde Python
   scaffold paths is invalid.
2. One Blitz Brigade feed line emits many packets (DP, each Enhancement
   add/remove, each Stratagem add/remove), not one page packet.
3. Bannernob emits two packets. The `points_only` packet forbids
   `layer_a_carry_forward_review` while the `unclassified_clause` packet
   is open.
4. Ghazghkull emits three packets (`cost_rows`, `composition`,
   `clause.unattributed`). Completing the composition packet does not
   close the review packet.
5. Boss Boomer `structural_add` does not list Targetin’ Gizmos.
6. Inherited listings of the same `source_entry_binding` add zero packets.
7. Acts of Faith battle-round → turn start is
   `clause_envelope_changed` on `clause.timing`, not `effect_ir_changed`.
8. Dakkajet "Rules Updated" is a `review` packet on
   `clause.unattributed`. It must not set `field_path` to
   `clause.effect_ir`.
9. A content packet with `adapter_contract_delta` in `allowed_surfaces`
   is invalid.
10. A `family_gap` packet with a faction `catalog_id` as its identity is
    invalid. A content packet with `python_policy: generic_family` is
    invalid.
11. A `named_handler_justified` packet missing any of the seven
    justification fields is unpublished.
12. `faction_rewrite` overlay plus More Dakka! `structural_remove` plus
    Brute Bosses `structural_add` are three identities, not one.

## 10. Mapping exercise (not emitted packets)

Planning examples from the classification Orks 931→946 exercise and
cross-faction samples. FM0 emits the real packets. This PR does not.

| Sample | `packet_kind` | Grain | Notes |
| --- | --- | --- | --- |
| Orks v946 overlay | `overlay` | `faction_view` / `overlay` / `faction_rewrite` | Children still required |
| More Dakka! | `implementation` | `existence` / `structural_remove` | Tombstone; not in the current-URL table |
| Brute Bosses | `implementation` | `existence` / `structural_add` | `blocked_on` provenance and catalog ID |
| Blitz Brigade 2DP → 1DP | `implementation` | `army_construction` / `construction_constraint` | Not points; Layer A not remapped |
| Boss Boomer | `implementation` | `existence` / `structural_add` | Sibling Gizmos out of scope |
| Bannernob | `implementation` + `review` | `cost_rows` and `clause.unattributed` | Two packets; A carry-forward forbidden |
| Ghazghkull | `implementation` + `implementation` + `review` | `cost_rows`, `composition`, `clause.unattributed` | Three packets; union A/B/C is not a merge |
| Dakkajet | `review` | `clause.unattributed` / `unclassified_clause` | No component guess |
| Eldrad 130→120 | `implementation` | `cost_rows` / `points_only` | No sibling unclassified in F-DATA-01 |
| Eldrad Leader list | `implementation` | `leader_support` / `attachment_or_keyword` | |
| Acts of Faith trigger | `implementation` | `clause.timing` / `clause_envelope_changed` | F-ARMY-01 |
| Effect RuleIR with envelope unchanged | `implementation` | `clause.effect_ir` / `effect_ir_changed` | Class illustration, not a named corpus row |
| Live War Horde Python triad | invalid | n/a | Failure mode this schema replaces |

Do not publish a histogram of all 53 datasheet URLs as packets here.

## 11. Gap list for later work

### 11.1 Surfaces that exist and must not be forked

U2–U4 classification, S2 locators, T1–T6 catalogs, the L0–L8 ladder, the
adapter decision contract, and the AGENTS.md named-handler rubric already
exist. Packets index them.

### 11.2 Work that remains later (not this PR)

- U3 packet generator and emission
- Live agent-contract rewrite (Track D D3, FM0)
- Adapter-contract edits (only with a real family consumer)
- Q1 status-artifact schema
- U7 / U7a retention draft
- U8 runbook (U1, U5, U6, Q6)
- S4 tool and Orks 20/73 fixture
- Catalog ID allocation

### 11.3 Families this schema must not steal

- Identity and locators remain S2
- WHEN, EFFECT, TARGET, construction, ledgers, decisions remain T1–T6
- Diff grain, classes, and layers remain U2–U4
- F00 page retention remains S1
- Extraction remains S3a
- Q1 storage remains Q1

## 12. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| U-HOLD-ORKS-S4-COUNTS | Exact 20/73 S4 integers | S1 fixture, then generator golden tests |
| U-HOLD-RULES-UPDATED | Dual-version clauses | S3a, then review packets can become envelope/effect packets |
| U-HOLD-NAME-PUNCTUATION | Punctuation twins are not locators | S2 locators on retained pages |
| Packet generator | Actual emission | FM0 U3 |
| Q1 schema | Where `status_claim` and review records persist | next remaining design after this schema, or with U4 implementation |
| Live agent contract | Rewrite Task Packet Format to this schema | FM0 Track D D3 |
| Owner D3 / U7a | Retention and replay compatibility | later design PR |

## 13. What "packet schema delivered" means

FM0 packet generation may be implemented. It has:

- entity-and-field packet grain on S2 locators plus a classified field
  path;
- five packet kinds and three Python policies;
- a closed class-to-packet map, including sibling unclassified forbidding
  Layer A carry-forward;
- closed allow/deny surfaces that reject the live Python-scaffold packet;
- twelve acceptance fixtures;
- an Orks mapping exercise that does not emit packets.

This survey does not add a generator, live contract rewrite, adapter
contract amendment, Q1, `src/` files, or catalog IDs. FM0 implements those
from retained pages and reconciles them with this document.
