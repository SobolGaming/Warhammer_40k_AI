# Compatibility policy

The external contract uses semantic versioning. Its current version is
`11.1.0`, declared in `openapi.yaml`, `manifest.json`, and
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
   its current major, currently `compatibility/11.0.0-shape.json`. Breaking
   changes are rejected while the bundle major remains `11`, preserving the
   original clients for the full supported major. The immutable 1.0.0,
   2.0.0, 3.0.0, 4.0.0, 5.0.0, 6.0.0, 7.0.0, 8.0.0, 9.0.0, and 10.0.0 baselines
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

The reference server supports one contract major at a time. Contract 11 makes
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
