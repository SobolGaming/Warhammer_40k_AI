# D3 — Draft Track D contract rewrites

[Contracts index](README.md) · [Packet schema](../updates/U_PACKET_SCHEMA.md) · [Retention](../updates/U7_RETENTION.md) · [Runbook](../updates/U8_RUNBOOK.md) · [Q1 status artifact](../status/Q1_STATUS_ARTIFACT.md) · [T6 decision-kind taxonomy](../taxonomy/T6_DECISION_KIND_VISIBILITY.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [Live agent contract](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md) · [Live adapter contract](../../ADAPTER_DECISION_CONTRACT.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This document is Track **D** item **D3** (live adapter-contract updates
and the live agent-contract rewrite) as **FM-pre planning evidence**. It
closes how FM0 rewrites
[FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md)
onto published packets, and which writers may amend
[ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md).

It does not rewrite those live files, amend `contracts/`, apply a T6
delta, implement U7a, emit packets, or change `src/`, catalogs, or F00.
The packet grain remains [U_PACKET_SCHEMA.md](../updates/U_PACKET_SCHEMA.md).
Owner **D3** packaging and the U7a mechanism remain
[U7_RETENTION.md](../updates/U7_RETENTION.md). FM0 applies this draft to
the live files and reconciles them with this document.

Machine-readable catalog: [`d3_contract_rewrites.json`](d3_contract_rewrites.json).

This is the last FM-pre design item listed in the roadmap. Gate 0 and
FM0 implementation remain.

## 1. Purpose and delivery contract

Classification named **what changed**. Packets named **what work that
produces**. Q1 named **where claims persist**. Retention named **which
versions a build may load**. The runbook named **in what order that work
happens**. This document names **how an agent is bound to those packets**
and **who may move the adapter contract**.

The live agent contract still describes a Python scaffold triad (the War
Horde `rule.py` / `enhancements.py` / `stratagems.py` allowlist). Lifting
that list over S2 `catalog_id` plus `source_entry_binding` plus a
classified field path is the packet-schema failure mode. The live adapter
contract still names families as they shipped. It does not yet state the
closed writer set that U8 and the packet schema already require.

**FM0 applies this draft.** It must not copy these sections over the live
files in this PR, apply a T6 delta without a real consumer, implement
U7a in the same PR as the agent rewrite, or let a content packet edit
either live contract. Family PRs, the U7a implementation, and the later
live application remain separate FM0 work.

T1–T3 still own WHEN, EFFECT, and TARGET atoms. T4 still owns
construction. T5 still owns ledgers. T6 still owns submission kind,
visibility, and the *demand* list of adapter deltas. S2 still owns
identity. Packets still own work. U7 still owns packaging and the U7a
record. This document only contracts **live-file rewrites**.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Packet half already delivered | [U_PACKET_SCHEMA.md](../updates/U_PACKET_SCHEMA.md) |
| Live packet format being replaced | [FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](../../FACTION_AGENT_IMPLEMENTATION_CONTRACT.md) Scope and Task Packet Format |
| Adapter demand list | [T6 §7.2](../taxonomy/T6_DECISION_KIND_VISIBILITY.md) contract deltas |
| U7a amendment owner | [U7_RETENTION.md](../updates/U7_RETENTION.md) §9 |
| Engine inspection | Read-only: AGENTS.md named-handler rubric, packet allow/deny surfaces, U8 §4.7 |

This document does not copy bulk operative text. Community teasers are
not F00 observations. 39k.pro IDs are not `catalog_id`.

## 3. Closed grain

### 3.1 Two D3 names

| Name | Owns | Does not own |
| --- | --- | --- |
| Owner D3 | When N−1 may be packaged; handler union; fail-closed missing version | Live adapter or agent contracts |
| Track D D3 | Live agent-contract rewrite; adapter-contract writer policy | Packaging windows; U7a envelopes; T6 family implementation |

A packaging PR that rewrites the live agent contract is invalid. An
agent-contract rewrite that packages content is invalid.

### 3.2 Draft versus live file

| Object | This PR | FM0 Track D D3 apply PR |
| --- | --- | --- |
| This draft | Binding as planning evidence | Source text FM0 copies from |
| Live agent contract | Unchanged | Scope, Task Packet Format, Python policy, and the shared-surface escape hatch |
| Live adapter contract | Unchanged | Writer-policy section only |
| `contracts/` | Unchanged | Unchanged by Track D D3 |
| T6 delta rows | Cited as demand | Not applied here |
| U7a record | Unchanged | Unchanged; U7 owns that FM0 PR |

Copying this draft over a live file before that apply PR is unpublished.

### 3.3 Three adapter-contract writers

Closed writers of
[ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md):

| Writer ID | When | Same PR must include | Must not |
| --- | --- | --- | --- |
| `family_or_decision_kind` | New `decision_type`, finite option family, `proposal_kind`, visibility class, or nested-allowlist entry | The real family or decision kind, a `family_gap` packet that cites `t6_delta_ids` when the work is packet-driven, conformance, and tests | Speculative families; content-packet work |
| `u7a_compatibility` | FM0 U7a implementation | Record, verification, fail-closed behaviour, and conformance | A new gameplay family; packaging slots; Q1 `certified` invented by packaging |
| `d3_writer_policy_binding` | FM0 application of §5.1 | This draft's writer-policy section and the agent-contract rewrite | T6 deltas; U7a mechanism; new payloads |

No other writer exists. A content, review, overlay, or
`observation_repin` packet is not a writer. Citing a `t6_delta_id` on a
content packet does not authorize an edit. U8 §4.7 is this packet-path
rule; it does not exclude `u7a_compatibility` or
`d3_writer_policy_binding`.

### 3.4 Splits this grain must not flatten

| Flattened token | Published split |
| --- | --- |
| "Rewrite the contracts" | Agent rewrite **and** adapter writer policy; not owner D3; not U7a |
| "Update the adapter contract" | One of the three writers above, each with its same-PR obligation |
| Live War Horde Python triad | Many packets; never a data-first `allowed_surfaces` list |
| T6 delta ID | Demand citation; not an applied contract section |
| "Ordinary PR may add a runtime surface if it updates this contract" | `family_gap` plus `runtime_integration` only |
| Live file | Unchanged until the FM0 apply PR |

## 4. Agent-contract rewrite

FM0 replaces the live Scope and Task Packet Format with §4.2–§4.4. It
keeps the live Runtime Surfaces inventory, Decision And Mutation, and
Required Tests, except it deletes the shared-surface escape hatch in
§4.5.

### 4.1 What FM0 replaces

| Live section | FM0 action |
| --- | --- |
| Scope (scaffold-directory assignment) | Replace with §4.2 |
| Task Packet Format (War Horde Python list) | Replace with §4.3 |
| *(none)* | Insert §4.4 Python policy |
| Runtime Surfaces | Keep the existing approved inventory; delete the sentence that lets an ordinary PR introduce a shared surface by updating this contract |
| Decision And Mutation | Keep |
| Required Tests | Keep; map assertions onto packet `required_work` |

The rewrite must not add a hook family, decision type, or visibility
class.

Relative links in §4.2–§4.3 are written for this draft folder. The
apply PR rewrites them for
`docs/FACTION_AGENT_IMPLEMENTATION_CONTRACT.md` (`FACTION_SUPPORT.md`,
`factions/updates/U_PACKET_SCHEMA.md`, and so on). It does not change
the normative sentences.

### 4.2 Draft replacement: Scope

FM0 applies this text to the live agent contract, marked binding:

This contract applies to agent-authored faction-content work after FM0
binds this rewrite.

Before selecting work, read the [faction support guide](../../FACTION_SUPPORT.md),
the assigned faction's detailed audit, the
[Faction Rules Remediation Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md),
the published packet, and `AGENTS.md`. Those documents identify source
obligations. The packet names the allowed work. `AGENTS.md` still
controls named handlers and fail-closed implementation.

Each agent PR consumes one or more **published packets** from
[U_PACKET_SCHEMA.md](../updates/U_PACKET_SCHEMA.md). A PR may batch
packets only as [U8](../updates/U8_RUNBOOK.md) allows: by
`owner_faction_id`, or behind a `family_gap` that several content
packets share. Forbidden batching: one PR per page URL; mixing two
App-data cadences; a content packet that lists the adapter contract.

Ordinary content PRs implement `implementation`, `review`, `overlay`,
and `observation_repin` packets. They modify only that packet's
`allowed_surfaces`. Runtime loader, lifecycle, bundle, and manifest
machinery stay out of scope for those packets.

A `family_gap` packet is a different PR. It may use
`runtime_integration` and, when it cites `t6_delta_ids`,
`adapter_contract_delta`. It must carry a real source-backed consumer
in the same PR.

Do not parse raw rule text or import source-mirror, HTML sanitizer,
parser, or compiler tooling from runtime faction-content modules.

### 4.3 Draft replacement: Task Packet Format

FM0 applies this text in place of the live War Horde allowlist:

Work unit: one published packet. The packet's `packet_id`,
`packet_kind`, `python_policy`, `required_work`, `forbidden_work`,
`allowed_surfaces`, `forbidden_surfaces`, and `blocked_on` are the
task.

The agent may modify only `allowed_surfaces`. The agent must not
modify `forbidden_surfaces` or claim `forbidden_work`.

Required:

- Consume the published packet. Do not invent a field path, a
  display-name packet, or a Python-module allowlist.
- Use source IDs from generated records and execution rows.
- Follow `python_policy` in §4.4.
- Return typed unsupported results with source-linked reasons for
  unsupported semantics.
- Add replay and audit assertions for state-changing behaviour.
- Write only the Q1 `review_record` / `status_claim` kinds the packet
  authorizes.
- Do not edit runtime loader, lifecycle, bundle, or manifest
  machinery from a content, review, overlay, or re-pin packet.

The historical Task Packet Format that lists
`orks/detachments/war_horde/rule.py`, `enhancements.py`,
`stratagems.py`, and a single test module is **not** a valid packet.
Those paths are not `allowed_surfaces`.

### 4.4 Draft replacement: Python policy

| Policy | When | Production Python |
| --- | --- | --- |
| `none` | Default for content, review, overlay, and re-pin | Forbidden. Tests are allowed |
| `named_handler_justified` | `AGENTS.md` bespoke-subsystem rubric is met **and** the packet carries the seven justification fields | Only the named handler module listed on the packet |
| `generic_family` | This packet **is** the Track G family PR | Generic engine modules, the packet's `runtime_integration` surface, plus tests; two-consumer rule applies |

A content packet must not set `generic_family`. A family packet must
not bind a faction `catalog_id` as its identity. Missing any of the
seven named-handler fields leaves the packet unpublished.

If the family adds an approved runtime contribution surface, that
`family_gap` PR updates the live agent-contract Runtime Surfaces
inventory in the same change. If it also adds a decision family, it
uses writer `family_or_decision_kind` on the adapter contract. Those
are still not content-packet rights.

### 4.5 Runtime surfaces

The approved inventory remains the surfaces already named in the live
agent contract. This draft does not copy that inventory and does not
add a surface.

FM0 deletes this live sentence:

> A PR that explicitly introduces a shared runtime surface must update
> this contract, lifecycle/bundle tests, and integration-plan
> documentation in the same change.

and replaces it with:

> A new shared runtime surface is a `family_gap` packet. It updates
> this inventory, lifecycle/bundle tests, and integration-plan
> documentation in that family PR. Content, review, overlay, and
> re-pin packets cannot introduce a surface by editing this contract.

### 4.6 Decision and mutation

Unchanged. UI, CLI, headless, network, AI, replay, and tests may
choose decisions differently. They must not validate or mutate through
a separate path.

### 4.7 Required tests

Keep the live required-test list. Map each assertion onto the packet's
`required_work` (replay/audit, handler-identity drift, unsupported
diagnostics, mustering or fieldability regressions). Tests use real
domain objects or canonical fixtures. Do not replace
`lifecycle.decision_controller`. Do not import from other `test_*.py`
modules.

### 4.8 Transitional scaffold files

FM0 debt item 3 removes the scaffold generator, the implemented-ID
map, generated manifests, and placeholder detachment modules.
Runtime contributions then load from content-set bindings plus the
remaining justified Python handlers.

Until that debt closes:

- ordinary packets still must not edit `manifest.py`;
- if a packet still lands on a remaining placeholder file, remove the
  placeholder marker only when that file implements source-backed
  semantics for the packet's field path;
- that transitional edit does not revive the War Horde triad as a
  packet and does not authorize sibling files on the same page.

### 4.9 What the rewrite must not add

- a new hook family, RuleIR family, or decision type;
- a T6 delta body;
- an U7a envelope or `contracts/` schema;
- catalog ID allocation;
- F00 or source-authority edits;
- generic lifecycle branching on faction, detachment, Enhancement,
  Stratagem, display name, or source-text tokens.

## 5. Adapter-contract rewrite

Track D D3 does not replace the live adapter contract. It inserts the
writer-policy section in §5.1. T6 deltas stay demand. U7a stays U7.

### 5.1 Draft section to insert

FM0 inserts this section into
[ADAPTER_DECISION_CONTRACT.md](../../ADAPTER_DECISION_CONTRACT.md).
The insert adds no family, payload shape, visibility class, or nested
allowlist entry.

**Faction-content and family amendments**

Content, review, overlay, and `observation_repin` packets must not
edit this file.

A new `decision_type`, finite option family, `proposal_kind`,
visibility class, or nested-allowlist entry updates this file in the
same implementation PR as the real family or decision kind. Packet-
driven family work uses a `family_gap` packet that cites
`t6_delta_ids` and includes `adapter_contract_delta`.

The FM0 U7a implementation amends this file for the compatibility
record, verification, fail-closed behaviour, and conformance
scenarios. That amendment does not require a new gameplay family and
is not a U8 stage.

The FM0 Track D D3 apply PR may insert this writer-policy section
together with the agent-contract rewrite. That insert is not a
gameplay-family change.

T6 delta IDs are demand citations. They do not by themselves
authorize an edit.

### 5.2 T6 deltas stay demand

[T6 §7.2](../taxonomy/T6_DECISION_KIND_VISIBILITY.md) lists
`T6-DELTA-NEW-FAMILY`, hidden Stratagem/CP, hidden healing, hidden
setup beyond existing `owner_secret` rows, unbounded spend, and
nested-allowlist growth.

Those rows authorize a later Track G PR that has a real consumer.
They do not authorize the Track D D3 apply PR to add those families
now. Battle Focus manoeuvre remains `finite_mode_pick` on an existing
window unless that window cannot carry the choice; it is not
automatically a new `decision_type`.

### 5.3 U7a remains U7-owned

[U7_RETENTION.md](../updates/U7_RETENTION.md) §9 still owns the FM0
U7a amendment of `contracts/` and the adapter contract. Writer
`u7a_compatibility` is that PR. Track D D3 must not implement the
record, hash the goldens, or certify a producer.

### 5.4 What the rewrite must not apply

- any T6 delta body;
- a new hidden visibility class;
- a quantity `decision_type`;
- a second nested-allowlist entry;
- Q1 `certified` invented by packaging;
- Phase 18L exact-build recovery changes.

## 6. Writers and precedence

| Writer | May write | Must not |
| --- | --- | --- |
| This draft | Planning evidence | Live files; `contracts/`; packets |
| FM0 Track D D3 apply PR | Live agent Scope / Task Packet / Python policy; adapter §5.1 | T6 deltas; U7a; `src/` runtime families |
| `family_gap` implementer | Agent Runtime Surfaces inventory when adding a surface; adapter contract when adding a decision family | Content-packet work in the same surfaces |
| U7a implementer | Adapter compatibility section; `contracts/` record | Agent Task Packet Format; packaging slots |
| Content / review / overlay / re-pin implementer | Packet `allowed_surfaces` only | Either live contract |
| Owner D3 / U7 packager | Packaging slots | Either live contract |

Precedence:

1. The unconditional packet denylist still wins (packet schema §7.3).
2. A rewrite overlay does not exempt children from
   publish-before-implement and does not authorize a contract edit.
3. Guide `current` while Q1 is `stale` still fails; no contract rewrite
   waives it.
4. Missing packaged version still fails load (U7), even mid-cadence.
5. A `family_gap` must land before content packets that require it.
6. U7a may amend the adapter contract without a new gameplay family.
7. Citing `t6_delta_id` on a content packet is not writer
   `family_or_decision_kind`.

## 7. Acceptance fixtures

Implementation tests when the live apply PR and later family PRs land.
This PR only defines them.

1. Copying this draft over
   `FACTION_AGENT_IMPLEMENTATION_CONTRACT.md` or
   `ADAPTER_DECISION_CONTRACT.md` before the FM0 apply PR is
   unpublished.
2. A content, review, overlay, or `observation_repin` packet that
   lists `ADAPTER_DECISION_CONTRACT.md` is invalid.
3. A `family_gap` PR that adds a `decision_type` or `proposal_kind`
   without updating the adapter contract in that PR is unpublished.
4. A `family_gap` PR that updates the adapter contract without a real
   source-backed consumer in the same PR is unpublished.
5. The U7a FM0 PR may amend the adapter contract without adding a
   gameplay family. It must still carry the record, verification,
   fail-closed behaviour, and conformance.
6. After the apply PR, a War Horde Python-triad task packet is
   invalid. Those paths are not `allowed_surfaces`.
7. The Track D D3 apply PR must not apply `T6-DELTA-HIDDEN-STRATAGEM`,
   `T6-DELTA-HIDDEN-HEALING`, `T6-DELTA-HIDDEN-SETUP`,
   `T6-DELTA-UNBOUNDED-SPEND`, or `T6-DELTA-NESTED-ALLOWLIST`.
8. A content packet that introduces a shared runtime surface by
   editing the agent contract is unpublished. That work is
   `family_gap` only.
9. A U6 overlay or rewrite implementation PR must not rewrite either
   live contract.
10. An owner-D3 packaging PR that rewrites the live agent contract is
    unpublished.
11. The Track D D3 apply PR must not implement U7a. Those remain
    separate FM0 PRs.
12. The draft, and the apply PR, must not add a runtime hook family
    that no real consumer in the same PR requires.
13. An apply PR that keeps the live War Horde Task Packet Format is
    unpublished.
14. Inserting §5.1 must not add a decision family, payload, or
    visibility class.
15. Citing a `t6_delta_id` on a content packet does not authorize an
    adapter-contract edit.

## 8. Mapping exercise (not a live rewrite)

Planning examples. FM0 applies the real files. This PR does not.

| Sample | D3 fact | Notes |
| --- | --- | --- |
| Live War Horde Python triad | Invalid packet after apply | Packet schema fixture 1 |
| Blitz Brigade DP 2→1 | Content packet; no adapter edit | `construction_constraint` |
| Orks v946 overlay | Overlay plus children; no contract rewrite | U8 rewrite path |
| Acts of Faith remap | Envelope packet; adapter unchanged unless a new family is required | F-ARMY-01 |
| T6 hidden Stratagem / hidden CP | Demand row only | Later Track G; not the apply PR |
| Battle Focus manoeuvre | Existing `finite_mode_pick` unless the window cannot carry it | Not automatically a new `decision_type` |
| U7a producer envelope | Writer `u7a_compatibility` | U7 §9; not this apply PR |
| Real new decision family | Writer `family_or_decision_kind` | Same PR as the family |

Do not publish a histogram of T6 deltas as applied contract sections
here.

## 9. Gap list for later work

### 9.1 Surfaces that exist and must not be forked

The packet schema, T6 delta list, U7a amendment recipe, U8 packet-path
rule, AGENTS.md named-handler rubric, and the live Runtime Surfaces
inventory already exist. This document indexes them.

### 9.2 Work that remains later (not this PR)

- FM0 apply PR that rewrites the live agent contract and inserts §5.1
- U3 packet generator and emission
- U7a record, `contracts/` amendment, and golden fixture
- Track G PRs that apply individual T6 deltas with real consumers
- Scaffold-generator removal (FM0 debt item 3)
- Catalog ID allocation

### 9.3 Families this draft must not steal

- Identity and locators remain S2
- WHEN, EFFECT, TARGET, construction, ledgers, decisions remain T1–T6
- Diff grain, classes, and layers remain U2–U4
- Packet identity and surfaces remain the packet schema
- Status rows, reviews, and coverage labels remain Q1
- Packaging and cross-build replay remain U7 / U7a
- Cadence, capture, tombstones, and Q6 remain U8
- F00 page retention remains S1
- Extraction remains S3a
- Guide and changelog generation remain D1 / D2

## 10. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| Live agent-contract apply | FM0 copies §4.2–§4.5 onto the live file | Binding agent packets |
| Live adapter writer-policy apply | FM0 inserts §5.1 | Binding writer table |
| U7a contract amendment | Record, verification, fail-closed, conformance | S3c; writer `u7a_compatibility` |
| T6 deltas | Real Track G consumer per delta | Hidden / spend / nested families |
| Packet generator | Actual emission | FM0 U3 |
| Scaffold removal | FM0 debt item 3 | Binding-only contributions |
| U-HOLD-ORKS-S4-COUNTS | Exact 20/73 S4 integers | S1 fixture, then generator tests |

## 11. What "Track D D3 draft delivered" means

FM0 may apply the live rewrites. It has:

- a packet-scoped agent contract that retires the War Horde Python
  triad as a task format;
- a closed Python policy matching the packet schema;
- a closed three-writer adapter-contract table that keeps content
  packets off that file without excluding U7a;
- an apply recipe that inserts writer policy and does not apply T6
  deltas;
- fifteen acceptance fixtures;
- a mapping exercise that does not edit live files.

This survey does not add a live contract rewrite, `src/` files, a
decision family, or catalog IDs. FM0 implements those from retained
pages and reconciles them with this document.

FM-pre documentation listed in the roadmap is now complete. Remaining
faction work before runtime changes is Gate 0, then FM0.
