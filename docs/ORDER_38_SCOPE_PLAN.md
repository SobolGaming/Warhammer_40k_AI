# Order 38 — Core disembark eligibility

Status: implementation and required local validation complete; awaiting PR review and merge.
Finding IDs: C18-08 / P18G (Order 38).

Dependencies and evidence gate: P18D, P18E and S-MIRRORS are merged. The branch
starts at current main `7800eac718c1b77ca1782f162cad2e10a8e3eb35` (Order 37).
The complete retained Core 18.06/18.07 statements supply the required clauses;
no new observation, transcription or source wording is needed. A live 40k.app
fetch returned 403 and is not claimed as new source evidence.

Violated invariant: a permitting source and the Core move's eligibility are
independent. Assault excludes Advance and Fall Back only; Shock adds no movement
restriction. Both require current embarked cargo, a battlefield Transport and no
embark into that Transport this phase. Movement history never supplies a grant.

How it is currently done (before this change): candidate enumeration couples
Normal movement to Assault and Advance to Shock; shared mode validation and the
resolver repeat the restriction. One candidate hides overlapping legal choices.
Placement validates the recorded context without rechecking the live grant.

How it should be done: enumerate ordinary and every independently permitted mode;
share Assault's two excluded statuses across candidate and state validation;
validate current permission, cargo, placement and actual movement status before
recording a result or consuming the request. Source-specific grant restrictions
remain the responsibility of the source-linked RuleIR/hook owner. Existing grants
retain exact passenger, Transport, source identity and expiration restrictions.

Specific authoritative maintained direct App-data mirror rule/statement and
source ID: complete When eligible clauses of Core 18.06 Assault Disembark and
18.07 Shock Disembark, `gw-11e-core-rules:transports:assault-disembark-move` and
`gw-11e-core-rules:transports:shock-disembark-move`.

Provider, URL, App-data version or observation timestamp, transcription SHA-256,
and source-observation fingerprint: Game Datamissions,
<https://game-datamissions.com/11th/rules/changelog>, App data 931, observed
2026-09-02T12:30:09-04:00. Assault transcription:
`93b5d311d7bce309e94f93c6b501a6980a820505786f59e0cb2bbfc6e53e4bee`;
Shock transcription:
`d8dae354aabcc30c582b66e70939dd67c010055637f86923292c0c76ffe7252c`.
Assault observation fingerprint:
`afa51f8bbba769ecf4c34cf7acfa62c02addc247f11b42d830cc91bbded0066b`;
Shock observation fingerprint:
`cc8a85d4bcd88e7eb0ec3d9228721e5c1e4d1e4287b57d02a18ae3e8b3523efe`.
This provider is a non-affiliated maintained App-data mirror under the recorded
owner-approved policy, not an official GW host. Load and execution status remain
separate; this repair certifies eligibility only.

Scope and explicit exclusions: all six movement states, independently selectable
permitted modes, live grant/context validation, same-phase re-embark denial and
source-neutral permission tokens. No faction builder, new generic hook or named
handler is added. Shock engagement ownership and forced-Fight semantics, Rapid
Ingress restriction propagation and other transport findings remain excluded.
The current reserve-arrival driver explicitly rejects embarked Transport cargo
(`reserve_embarked_cargo_unsupported`). Ingress regressions therefore begin at a
typed, restored arrived-Transport snapshot and replay disembarkation from there;
they do not certify the separate P20 carrier-arrival driver.

Owning state/validation/mutation/event/replay path: source-linked persisting grant
-> movement candidate enumeration -> finite action choice -> placement proposal
prevalidation -> grouped Transport resolver -> engine-owned cargo/placement and
disembarked state -> domain events, viewer projections, restore/replay and charge.
Eligibility logic is extracted from the frozen Transport facade before extension.
No adapter mutation path, endpoint-only movement validation or content-name gate
is introduced. Scope/architecture/diff audit completed before aggregate gates:
remaining movement-module edits are mechanical imports of the plural candidate
API; source JSON, build identity and contract examples follow runtime changes.

Decision and viewer-visibility impact: contract 15.1 adds
`disembark:assault_disembark` and `disembark:shock_disembark`, including exact source
commitments, alongside the existing ordinary `disembark` option. No decision type,
proposal kind or visibility class changes. Both players observe these public
choices through the shared redaction owner. Placement rejects live eligibility
drift before queue pop or decision recording. Replay/persistence remains bound
to the exact runtime build; renamed permission tokens have no compatibility aliases.

Regression scenarios and same-bug-class search: the initial 12-case regression
on base produced 8 failures and 4 passes. The final focused run passes 95 cases,
including all six statuses, absent/restricted/expired/replaced grants, movement
drift, malformed or altered permission payloads, battlefield absence, new embark
and re-embark, attached-group placement, JSON records, both-view projections,
restoration and exact replay. Repository searches covered candidate enumeration,
shared mode validation, resolver restrictions, state restoration, charge,
permission effect builders, source consumer inventories and static audits. No
obsolete enum or singular candidate API remains in runtime/tests/generators.
The new live-contract regression verifies source commitments cannot be omitted.
The complete Transport module passes all 203 cases, including combined placement
diagnostics. An absent or stale Transport reports `transport_placement_drift`
before querying unavailable geometry; other invalid placements retain their
combined diagnostics.

Generated artifacts/documentation: Core Transports JSON consumer inventory and
pinned hashes, immutable runtime build manifest, contract schema/version and
examples, TypeScript contract version, adapter contract, architecture, README and
roadmap finding record. No behavioral test file was added, deleted or moved;
the committed eight-shard inventory is unchanged.

Validation results: the final behavioral suite passes all 7,362 tests with
85.03% coverage (85% required), using 18 xdist work-stealing workers and the
required Node PATH. It emitted 10 ResourceWarnings. The complete code-quality
suite then passes all 431 tests without coverage, also using work stealing.
Ruff check/format, mypy (2,944 files), Pyright, all 11 import contracts and
pre-commit pass. The focused acceptance run passes 95 cases; the complete
Transport module passes 203 cases after preserving combined diagnostics.

Core Transports generation, runtime identity, external-contract generation and
base-ref compatibility checks pass against unchanged main `7800eac7`. The exact
eight-shard inventory check passes. Installed-wheel smoke validates 27 schemas
and six request families. TypeScript generation/check/typecheck, all five client
unit tests and the live HTTP scenario pass (342 assertions, exact replay
equivalence). Node 24.19.0 executes the package's script entrypoints directly;
`npm ci` is unavailable because npm is absent on this host. CI will perform the
clean dependency installation. Remote CI is not claimed as passed locally.

The [performance evidence](performance/order38/README.md) retains same-host
base/head slice samples and unchanged numeric budgets: all five cases pass,
with head means 1.817–1.897 ms and observed maximum 2.306 ms. Complete-game
performance certification remains outstanding. The final immutable runtime
fingerprint is `456524fb59fc190d602999e2db97633b1c40dcee311f408e1d961df95ea93b10`.

PR URL and merge commit: pending publication and review; no merge is authorized.
