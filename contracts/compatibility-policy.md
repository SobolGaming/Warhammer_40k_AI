# Compatibility policy

The external contract uses semantic versioning. Its current version is
`9.0.0`, declared in `openapi.yaml`, `manifest.json`, and
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
   its current major, currently `compatibility/9.0.0-shape.json`. Breaking
   changes are rejected while the bundle major remains `9`, preserving the
   original clients for the full supported major. The immutable 1.0.0,
   2.0.0, 3.0.0, 4.0.0, 5.0.0, 6.0.0, 7.0.0, and 8.0.0 baselines remain
   committed as historical compatibility anchors.
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

The reference server supports one contract major at a time. Contract 9 retains
Contract 8's directed Primary assignments and grouped historical evidence and
adds the required public `primary_mission_progress_state`. That state records
persistent/tombstoned mission markers, historical Punishment condemned
selections, and active/consumed Consecrate designations with source and event
provenance. `select_primary_mission_choice` requests and results are public
finite choices. The `battlefield-view-v4-phase17n-step3` family is unchanged;
Step 4 changes mission state, decision, lifecycle, event, session, and replay
families without changing authoritative battlefield coordinates or geometry
hash semantics.

Deployers upgrading a hosted 8.x service must retain a separately deployed 8.x
adapter through at least 2027-08-14 and one released 9.x minor line, whichever
is later. The retained adapter is a separate deployment pinned to an 8.x build;
the repository's Contract 9 reference server does not provide content
negotiation or parallel 8.x endpoints. Contract 9 clients must regenerate from
the Contract 9 schemas, discard cached Contract 8 projections, event cursors,
replay metadata, and checkpoints, and fetch a fresh projection after
authentication. Contract 8 cursors remain valid only against the retained 8.x
deployment. Prior retention dates remain in force for deployers covered by
earlier migrations. See `migrations/8-to-9.md`, `migrations/7-to-8.md`,
`migrations/6-to-7.md`, `migrations/5-to-6.md`,
`migrations/4-to-5.md`, and `migrations/3-to-4.md`.

Unknown or mismatched request `schema_version` values fail before engine
mutation with `schema_version_mismatch`. Servers never reinterpret a request
using a nearby schema version.
