# Compatibility policy

The external contract uses semantic versioning. Its current version is
`38.0.0`, declared in `openapi.yaml`, `manifest.json`, and
`warhammer40k_core.adapters.external_contract`.

Payload families also carry an explicit `schema_version`. A payload-family
version changes only when that family changes; the bundle version changes when
any public family, operation, or normative semantic changes.

## Version rules

- Patch: prose clarification, corrected example, or tooling change with no
  accepted or emitted payload-shape change.
- Minor: backwards-compatible additions, such as an optional property, a new
  operation, a new decision family, or a new proposal kind that old clients can
  safely ignore.
- Major: removed or renamed operations/properties, newly required properties,
  type or enum narrowing, changed identifiers/units/coordinate semantics,
  changed redaction or mutation semantics, or any other old-client break.

The pull-request contract audit performs three independent checks:

1. The proposed canonical schemas and OpenAPI operation set are compared with
   the exact contract on the pull-request base commit. Any change requires a
   version increase, and removing or narrowing anything accepted by that base
   contract requires a major increase. This preserves compatible additions
   made anywhere in the current major line.
2. The proposed contract is compared with the oldest committed baseline for
   its current major, currently `compatibility/38.0.0-shape.json`. Breaking
   changes are rejected while the bundle major remains `38`, preserving the
   original clients for the full supported major. The immutable 1.0.0,
   2.0.0, 3.0.0, 4.0.0, 5.0.0, 6.0.0, 7.0.0, 8.0.0, 9.0.0, 10.0.0, 11.0.0, 12.0.0,
   13.0.0, 14.0.0, 15.0.0, 16.0.0, 17.0.0, 18.0.0, 19.0.0 and 20.0.0 baselines
   remain committed as historical compatibility anchors.
3. Every released baseline present on the base commit must retain the exact
   decoded UTF-8 text after line-ending normalization.

Released baselines are immutable, remain committed when later majors are
introduced, and are included in `manifest.json` hashes. Pull-request CI compares
every baseline present on the base commit with the proposed tree and rejects a
changed or removed baseline. `--write-baseline` only creates the baseline named
for a new `EXTERNAL_CONTRACT_VERSION` major. A baseline absent from the base
commit may be refreshed while that release is still under review; once it is
present on the base commit, the command refuses to overwrite it. The new major,
payload-family version changes, migration notes, and old-client support window
must be reviewed in the same change.

## Support window

Contract 38 requires explicit dice override component scope and assignment
evidence in interpreted roll views. Retain 37.x through at least 2027-09-24 and
one released 38.x minor line, whichever is later. Old checkpoints and replays
require their original engine build; no missing dice history is inferred.
See [migration 37 to 38](migrations/37-to-38.md).

Contract 36 applies revival engagement to canonical enemy rules units at the
pre-return physical boundary and authenticates that scope on restore. Retain
35.x through at least 2027-09-24 and one released 36.x minor line, whichever
is later. See [migration 35 to 36](migrations/35-to-36.md).

Contract 35 requires the turn owner in Normal Move history and explicit movement
mode in reactive completion evidence. Retain 34.x through at least 2027-09-23
and one released 35.x minor line, whichever is later. See
[migration 34 to 35](migrations/34-to-35.md).

Contract 34 requires explicit canonical detachment identity and construction records.
Retain 33.x through at least 2027-09-21 and one released 34.x minor line, whichever
is later. See [migration 33 to 34](migrations/33-to-34.md).

Contract 33 requires explicit Warlord and Enhancement model selections. Retain
32.x through at least 2027-09-20 and one released 33.x minor line, whichever is
later. See [migration 32 to 33](migrations/32-to-33.md).

Contract 32 implements ingress-only Aircraft and mandatory opponent-turn-end
returns. Retain 31.x through at least 2027-09-20 and one released 32.x minor
line, whichever is later; see [31-to-32.md](migrations/31-to-32.md).

Contract 31 implements all-cargo Firing Deck snapshots and turn-long shooting
restrictions. Retain 30.x through at least 2027-09-20 and one released 31.x minor
line, whichever is later; see [30-to-31.md](migrations/30-to-31.md).

Contract 27 introduced authenticated setup kinds in phase movement history. See [26-to-27.md](migrations/26-to-27.md); retain 26.x through
at least 2027-09-19 and one released 27.x minor line, whichever is later.

Contract 26 implemented controlling-player ability-instance selection. See [25-to-26.md](migrations/25-to-26.md); retain 25.x through
at least 2027-09-17 and one released 26.x minor line, whichever is later.

Contract 25 introduced oversized setup and required mission edge identity. See [24-to-25.md](migrations/24-to-25.md); retain 24.x through
at least 2027-09-17 and one released 25.x minor line, whichever is later.
Earlier deployment retention obligations remain.

Contract 21 shares Heroic Intervention with ordinary Charge authority. It supports
major 21 only; see [20-to-21.md](migrations/20-to-21.md). Keep the preceding 20.x
deployment available through at least 2027-09-15 and one released 21.x minor line,
whichever is later. Earlier deployment retention obligations remain in force.

Contract 20 implements whole Charge rerolls and canonical Command Re-roll
unit targeting. It supports major 20 only; see [19-to-20.md](migrations/19-to-20.md).
Earlier deployment retention obligations remain in force.

Contract 19 implements canonical attached Charge actors and required per-model
endpoint evidence. It supports major 19 only; see [18-to-19.md](migrations/18-to-19.md).
Earlier deployment retention obligations below remain in force.


The reference server supports one contract major at a time. Contract 17 changes
Fire Overwatch to one opponent Movement phase-end opportunity with an independent
single-enemy Snap Shooting choice as documented in
[16-to-17.md](migrations/16-to-17.md). Metadata and command response families
advance to v17, operator persistence to v9 and replay to v11. Old movement-trigger
checkpoints require their matching deployment; no trigger-to-phase-end conversion
is inferred.

Contract 16 adds
required hit-threshold provenance and changes critical-hit evaluation as documented
in [15-to-16.md](migrations/15-to-16.md). Old hit records cannot supply that
authority and require their original deployment.

Contract 15 changes
rule ordering, temporary active-player authority and persisted source/batch
history as documented in [14-to-15.md](migrations/14-to-15.md). Metadata and command
response families advance to v15, replay to v9 and operator persistence to v7.
Old sessions require their original deployment; missing history is never inferred.

Contract 14 changes
the engine-owned nested visibility evidence contract as documented in
[13-to-14.md](migrations/13-to-14.md). Metadata and command response families
advance to v14 and operator persistence to v6. Existing open-JSON request,
projection and event envelopes keep their shapes. Old sampled witnesses cannot
be converted into continuous evidence; no checkpoint migration is provided.

Contract 13 adds source-linked
model keyword ownership and current rules-unit keyword projections as documented in
[12-to-13.md](migrations/12-to-13.md). Metadata and command response families advance
to v13, game views to v12, session projections to v8, and operator persistence to v5.
New model display fields are required. Existing proposal and decision families remain
unchanged. Old checkpoints cannot supply missing model ownership and are rejected;
no model-keyword inference from legacy runtime unit payloads is supported.

Contract 12 changes
Fight On Death retention, deferred destruction and target presence as documented
in [11-to-12.md](migrations/11-to-12.md). Metadata and command response families
advance to v12, and operator persistence advances to v4. It retains Contract 11's
proposal families and weapon-instance requirements. Contract 11 made
`weapon_instance_id` mandatory for every equipped ranged-weapon copy exposed or
submitted through the shooting-declaration contract. Availability rows,
declarations, attack pools, accepted decisions/events, persistence, and replay
retain the same deterministic identity. Distinct physical copies remain
independently targetable, and an exact physical-copy/profile/Firing-Deck-source
declaration key may appear only once. Catalog-defined independently selectable
multi-profile groups such as C'tan Powers may expose distinct legal profiles
with the same physical-copy ID, subject to the engine-emitted selection limits.
Contract 10 payloads without that identifier are not inferred as copy one and
are not accepted by the Contract 11 proposal or command-envelope schemas.

Contract 11 otherwise retains Contract 10's directed Primary assignments,
grouped historical evidence, persistent Primary Mission progress, public
Primary choices, and viewer-facing projection families. It retains the required
engine-private
`objective_control_record_authorities`,
`primary_scoring_state_evidence_records`, and
`primary_scoring_boundary_lifecycles` replay state. Objective-control
authorities bind each persisted record to a closed, content-addressed physical
boundary checkpoint plus retained sticky-control provenance. Each closed,
content-addressed row freezes the objective-control boundary, boundary kind,
Primary progress, qualifying Primary Action/departure history, and current
group-aware physical memberships plus the per-player spatial-condition evidence
consumed by the Primary rules evaluation, including a zero-award result. The
`game-view-v11-phase17n-step4`, `session-projection-v7-phase17n-step4`, and
`battlefield-view-v4-phase17n-step3` families are unchanged because this
authoritative registry is replay/audit state and is deliberately omitted from
viewer projections.

Contract 11.1 adds the optional `source_rule_id`, `unit_location`, and
`component_unit_instance_ids` fields to the live movement decision-family
schema and admits the `disembark` and `ingress` movement-action option variants.
The engine emits these fields for the unified Move Units loop, while Contract
11.0 movement responses remain valid under the widened schema. The closed v3
operator persistence family retains its original
`external_contract_version: "11.0.0"` identity.

The registry is exactly inverse-complete over applicable assigned-Primary
rules: every required ordinary or end-of-battle evaluation boundary has one
row even when evaluation awards zero VP, every row maps back to such a
boundary, and every awarded transaction matches deterministic re-evaluation.
Contract 11 therefore rejects removal of transactions together with their
evidence when the underlying applicable Objective Control boundary remains.

Contract 10.1 adds the optional `active_secondary_mission_card_jsons`,
`completed_mission_action_state_jsons`, `primary_unit_destruction_state_jsons`,
and `starting_strength_record_jsons` witnesses to the Primary mission boundary
checkpoint schema. Newly emitted Objective Control checkpoints include the
complete active-card, completed Mission Action, Primary destruction, and
Starting Strength snapshots used to authenticate Secondary scoring. Contract
10.0 checkpoints remain loadable with their original content hash when those
optional witnesses are absent, but missing witnesses cannot authenticate
restored Secondary scoring evidence.

Contract 10.2 adds the closed, backend-private
`session-persistence-v2-phase18l` schema and normative explicit initialization,
atomic persistence, revision-chain verification, cursor/role restoration, and
single-authority transfer semantics. The supported runtime does not reinterpret
or migrate a v1 persistence artifact: a schema mismatch fails before session
registration. This adds no public HTTP operation and does not change any
existing client request or response family. Contract 10.1 clients may continue
to use the same Contract 10 operations and payload shapes; only operators that
claim Phase 18L durability consume the new schema and recovery requirements.

The v2 artifact's canonical hashes and build fingerprint detect accidental
corruption, internally inconsistent history, and runtime-resource drift. They
do not authenticate storage against a malicious writer and cannot detect
replacement by an older, internally valid artifact without an external trusted
anchor.

Contract 11 advances the proposal payload, parameterized-submission,
session-command-envelope, interaction-conformance, session metadata/result/
outcome, and persistence families. The closed
`session-persistence-v3-weapon-instances` artifact binds the v2 command envelope,
v11 outcome/metadata, and `external_contract_version: "11.0.0"`; recovery does
not load or rewrite a v2 artifact. HTTP clients upgrading from Contract 10 must
regenerate their models, copy engine-emitted weapon instance IDs into every
shooting declaration, and discard cached Contract 10 request, command, session,
and interaction-conformance payloads.

Deployers upgrading a hosted 10.x service must retain a separately deployed
10.x adapter through at least 2027-08-23 and one released 11.x minor line,
whichever is later. The Contract 11 reference server does not provide content
negotiation or parallel Contract 10 endpoints. Contract 10 persistence and
shooting-declaration artifacts remain valid only against that retained 10.x
deployment. See `migrations/10-to-11.md`.

Deployers upgrading a hosted 9.x service must retain a separately deployed 9.x
adapter through at least 2027-08-16 and one released 10.x minor line, whichever
is later. The retained adapter is a separate deployment pinned to a 9.x build;
the retained Contract 10 server does not provide content
negotiation or parallel 9.x endpoints. Contract 10 clients must regenerate from
the Contract 10 schemas, discard cached Contract 9 session metadata, command
results/outcomes, replay metadata, and replay checkpoints, and fetch fresh
session metadata after authentication. Contract 9 replay artifacts remain
valid only against the retained 9.x deployment; their missing
objective-control-authority and scoring-state registries are never inferred as
empty. Prior retention dates remain in force for
deployers covered by earlier migrations. See `migrations/9-to-10.md`,
`migrations/8-to-9.md`, `migrations/7-to-8.md`,
`migrations/6-to-7.md`, `migrations/5-to-6.md`,
`migrations/4-to-5.md`, and `migrations/3-to-4.md`.

Unknown or mismatched request `schema_version` values fail before engine
mutation with `schema_version_mismatch`. Servers never reinterpret a request
using a nearby schema version.

Order 62 supports major 28. Retain the major 27 deployment through at least
2027-09-19 and one released 28.x minor line, whichever is later. Earlier
retention obligations and immutable baselines remain in force. See
[migration 27 to 28](migrations/27-to-28.md).


Order 63 supports major 29. Retain the major 28 deployment through at least
2027-09-19 and one released 29.x minor line, whichever is later. Earlier
retention obligations and immutable baselines remain in force. See
[migration 28 to 29](migrations/28-to-29.md).

Order 64 supports major 30. Retain the major 29 deployment through at least
2027-09-19 and one released 30.x minor line, whichever is later. Earlier
retention obligations remain in force. See [migration 29 to 30](migrations/29-to-30.md).

Contract 37 requires authenticated phase-start revival membership on battlefield
placement requests and events. Retain 36.x through at least 2027-09-24 and one
released 37.x minor line, whichever is later. See
[migration 36 to 37](migrations/36-to-37.md).
