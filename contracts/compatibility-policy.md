# Compatibility policy

The external contract uses semantic versioning. Its current version is
`10.2.0`, declared in `openapi.yaml`, `manifest.json`, and
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
   its current major, currently `compatibility/10.0.0-shape.json`. Breaking
   changes are rejected while the bundle major remains `10`, preserving the
   original clients for the full supported major. The immutable 1.0.0,
   2.0.0, 3.0.0, 4.0.0, 5.0.0, 6.0.0, 7.0.0, 8.0.0, and 9.0.0 baselines
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

The reference server supports one contract major at a time. Contract 10 retains
Contract 9's directed Primary assignments, grouped historical evidence,
persistent Primary Mission progress, public Primary choices, and viewer-facing
projection families. It adds the required engine-private
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

The registry is exactly inverse-complete over applicable assigned-Primary
rules: every required ordinary or end-of-battle evaluation boundary has one
row even when evaluation awards zero VP, every row maps back to such a
boundary, and every awarded transaction matches deterministic re-evaluation.
Contract 10 therefore rejects removal of transactions together with their
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
`session-persistence-v1-phase18l` schema and normative atomic persistence,
verified recovery, cursor/role restoration, and single-authority transfer
semantics. It adds no public HTTP operation and does not change any existing
client request or response family. Contract 10.1 clients may continue to use
the same Contract 10 operations and payload shapes; only operators that claim
Phase 18L durability consume the new schema and recovery requirements.

Deployers upgrading a hosted 9.x service must retain a separately deployed 9.x
adapter through at least 2027-08-16 and one released 10.x minor line, whichever
is later. The retained adapter is a separate deployment pinned to a 9.x build;
the repository's Contract 10 reference server does not provide content
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
