# Compatibility policy

The external contract uses semantic versioning. Its current version is
`1.0.0`, declared in `openapi.yaml`, `manifest.json`, and
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

The contract audit compares the canonical schemas with the oldest committed
baseline for the current major, currently `compatibility/1.0.0-shape.json`.
Breaking changes are rejected while the bundle major remains `1`.

Released baselines are immutable, remain committed when later majors are
introduced, and are included in `manifest.json` hashes. Pull-request CI compares
every baseline present on the base commit with the proposed tree and rejects a
changed or removed baseline. `--write-baseline` only creates the baseline named
for a new `EXTERNAL_CONTRACT_VERSION` major; it refuses an existing path or a
version whose major is not newer than every committed baseline. The new major,
payload-family version changes, migration notes, and old-client support window
must be reviewed in the same change.

## Support window

The reference server supports the current major only until a hosted service
policy is implemented in Phase 18E-18H. Before a new major is enabled, the PR
must document an old-client window of at least one released minor line or 90
days, whichever is longer, and must state whether compatibility is provided by
parallel endpoints, content negotiation, or a separately deployed adapter.

Unknown or mismatched request `schema_version` values fail before engine
mutation with `schema_version_mismatch`. Servers never reinterpret a request
using a nearby schema version.
