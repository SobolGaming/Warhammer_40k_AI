# Order 62 — Shock Disembark engagement ownership

Status: implemented and locally validated; ready for PR review. C18-07 / P18F only.

## Source resolution

On 2026-09-19 the repository owner resolved the roadmap exception in this task:
passengers may be placed engaged; enemy units now engaged with those passengers
are selected to Fight one at a time if they have not been selected this phase.
They may have been unengaged or engaged with other units beforehand.
The complete 18.07 source retains the mandatory "must select each" wording.
This ruling supersedes P18E's Transport engagement interpretation only.
It does not amend source text, grant inherited passenger engagements, change
P18G eligibility, or resolve P12B's separate consolidation exception.
Embarked passengers have no battlefield starting engagements. The stored start
inventory must be empty; it cannot authorize or limit post-setup enemies.

The retained Game Datamissions App-data 931 row is
`gw-11e-core-rules:transports:shock-disembark-move`, observed
2026-09-02T12:30:09-04:00 at
https://game-datamissions.com/11th/rules/changelog (version selector 931).
Transcription SHA-256:
`d8dae354aabcc30c582b66e70939dd67c010055637f86923292c0c76ffe7252c`.
Observation SHA-256:
`cc8a85d4bcd88e7eb0ec3d9228721e5c1e4d1e4287b57d02a18ae3e8b3523efe`.
The live v931 page was inspected in this task. The owner resolution is a
project interpretation, not a new official-App capture or replacement observation.
The retained source tuple and historical official GW provenance remain unchanged.
Load status and execution status remain separate fields.

## Ownership and scope

Base: `31dd2cb4613a40caa97e6d5d4575b76a561fed1f`; P18D, P18E, P18G and
S-MIRRORS are merged. No other roadmap PR was open at discovery.
The invariant is that the moving passenger rules unit owns Shock's post-placement
engagements and response queue. Transport geometry supplies setup distance only.

Source package -> permission effect -> finite movement action -> typed placement
proposal and live grant validation -> shared component/attached placement owner ->
engine-owned cargo and battlefield mutation -> canonical physical engagement query
-> forced-Fight queue -> opponent finite choices -> ordinary Fight completion ->
Movement resumption. Restore authenticates the post-placement inventory against
physical history, not merely matching copies in events and saved state.

The bug-class search covers single/attached placement, candidate and stale
proposal checks, endpoint permission, active/completed queue restore, source
consumer inventories and replay tests. Combat Disembark's separate Transport
engagement restriction remains in force. Oversized placement stays unengaged
under Order 55. No new named handler, hook family, faction branching,
architecture exception or player choice is needed.

Both revised resolver and queue regressions failed on the base engine before
production changes, establishing the defect.

## Scope and architecture audit

The diff removes Transport-derived start snapshot enforcement from both single
and attached placement. Combat's existing geometry helpers move into the shared
disembark geometry owner; the frozen Transport module shrinks. The new restore
validator consumes the existing authenticated physical-history abstraction and
shared engagement predicate. It validates all retained Shock events, including
those after current-turn disembark state expires. No general history framework,
new named handler or alternative decision path is introduced.

Generated source data changes only its consumer inventory and package identity;
source text and observation hashes are unchanged. Contract 28, replay v22 and
persistence v20 describe the required post-placement event evidence. Historical
compatibility baselines remain immutable. See the [migration](../contracts/migrations/27-to-28.md).

## Validation

The focused Shock and attached-placement subset passed 72 tests. This covers
empty onboard start snapshots, forged Transport lists, newly engaged enemies,
pre-existing engagement with another unit, Transport-only engagements, multiple
opponents, attached leader engagement, oversized restrictions, malformed/stale
proposals, public viewer events, forced Fight completion, exact restore/replay,
and coordinated fabricated skip evidence. Real facade fixtures execute a full
response and resume Movement.

Source and runtime generators and all 11 import contracts pass. The matched
component diagnostic completed seven samples on base and head within its recorded
limits; see [measurement evidence](performance/order62/README.md). Full-game and
complete gameplay-slice performance are unmeasured.

All 8,405 behavioral tests passed with 85.11% coverage; all 532 code-quality
tests passed without coverage. Ruff, formatting, mypy, Pyright, pre-commit, the
exact eight-shard inventory check, source/runtime generation, contract verification
against the exact base, TypeScript generated/type/unit/conformance checks and
installed-wheel smoke passed. Four old static audits were aligned with this
resolved interpretation; no production changes followed the successful coverage
run. [Machine-readable results](performance/order62/validation.json) retain the
counts, report hashes, warnings, benchmark limits and execution qualifications.
