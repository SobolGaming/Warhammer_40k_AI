# Compatibility policy

The external contract uses semantic versioning. Its current version is
`2.0.0`, declared in `openapi.yaml`, `manifest.json`, and
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
   its current major, currently `compatibility/2.0.0-shape.json`. Breaking
   changes are rejected while the bundle major remains `2`, preserving the
   original clients for the full supported major. The immutable 1.0.0 baseline
   remains committed as the historical 1.x compatibility anchor.
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

The reference server supports one contract major at a time. Contract 2.0 is a
deliberate breaking security boundary: session creation no longer accepts
client-owned participant assignments, bearer authentication is mandatory,
formal mutations use only the command endpoint, projections and metadata are
role scoped, and event cursors are opaque signed strings instead of integers.

Deployers upgrading a hosted 1.2 service must retain a separately deployed 1.x
adapter through at least 2026-10-17 and one released 2.x minor line, whichever
is later. The repository's reference server does not provide content
negotiation or parallel 1.x endpoints. New 2.x clients must fetch a full
projection after authentication and begin from its issued role-bound cursor;
1.x cursors and participant-assignment bodies are intentionally not migrated.
Future majors must document the same minimum window and delivery mechanism
before enablement.

Unknown or mismatched request `schema_version` values fail before engine
mutation with `schema_version_mismatch`. Servers never reinterpret a request
using a nearby schema version.
