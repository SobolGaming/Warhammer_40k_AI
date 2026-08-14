# Compatibility policy

The external contract uses semantic versioning. Its current version is
`8.0.0`, declared in `openapi.yaml`, `manifest.json`, and
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
   its current major, currently `compatibility/8.0.0-shape.json`. Breaking
   changes are rejected while the bundle major remains `8`, preserving the
   original clients for the full supported major. The immutable 1.0.0,
   2.0.0, 3.0.0, 4.0.0, 5.0.0, 6.0.0, and 7.0.0 baselines remain committed as
   historical compatibility anchors.
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

The reference server supports one contract major at a time. Contract 8 retains
Contract 7's directed Primary assignments and replaces physical-unit-only
turn-start terrain history with grouped rules-unit position evidence containing
exact component, terrain-area, and objective-marker/model witnesses. The
`battlefield-view-v4-phase17n-step3` family preserves the established geometry
contract while adding the Contract 8 pre-reveal model-state redaction boundary.
The `decision-request-view-v4-phase17n-step3` and
`lifecycle-status-v3-phase17n-step3` families likewise identify the changed
viewer-redaction semantics for unresolved Declare Battle Formations choices.

Deployers upgrading a hosted 7.x service must retain a separately deployed 7.x
adapter through at least 2027-08-13 and one released 8.x minor line, whichever
is later. The retained adapter is a separate deployment pinned to a 7.x build;
the repository's Contract 8 reference server does not provide content
negotiation or parallel 7.x endpoints. Contract 8 clients must regenerate from
the Contract 8 schemas, discard cached Contract 7 projections, event cursors,
replay metadata, and checkpoints, and fetch a fresh projection after
authentication. Contract 7 cursors remain valid only against the retained 7.x
deployment. Prior retention dates remain in force for deployers covered by
earlier migrations. See `migrations/7-to-8.md`, `migrations/6-to-7.md`,
`migrations/5-to-6.md`, `migrations/4-to-5.md`, and
`migrations/3-to-4.md`.

Unknown or mismatched request `schema_version` values fail before engine
mutation with `schema_version_mismatch`. Servers never reinterpret a request
using a nearby schema version.
