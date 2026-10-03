# Order 112 / P24L — mandatory Extra Attacks weapons

Base: `b65099255a85b0b02281b78905ce42754c53b594` (Order 111 / PR 551).

## Source and invariant

The pinned Order 97 source `rule:24:24.11:1` requires every fighting model to
select all its Extra Attacks weapons and one other melee weapon when possible.
The complete row has SHA-256
`2ec2a02a14d9ee132a01b4818bf7317c725b8706db89c779ddee03d1918d646f` in
`data/source_audits/order97/selected-sources.json`. Blocks 1–3 are the operative
selection requirements. The adjacent `rule:24:24.11.01:1` preserves Extra-only
attacks. This uses the selected historical Game Datamissions observation; it
does not claim a fresh official App observation or change historical evidence.

Every eligible equipped physical Extra Attacks weapon must be represented once
in the declaration, alongside the permitted primary choice. Eligibility retains
the shared equipped inventory, rules-present model authority, engagement and
One Shot restrictions. Multiple profiles do not turn one physical weapon into
multiple weapons. An attached unit must retain each component's physical owner.

## Authoritative path and bug-class search

`fight_resolution` supplies equipped physical weapon profiles and the shared
target/retained-model eligibility queries. `fight_weapon_selection` validates
the complete per-component declaration before creating attack pools.
`fight_rules_unit_melee` aggregates canonical attached units and lowers their
declarations through that same validator. `lifecycle_fight_prevalidation` and
`phases/fight_melee` provide the common adapter validation and mutation path.
The attached random-A profile-choice regression exposed component validation
authenticating unchosen alternative profiles against the committed inventory.
The existing top-level physical/profile filter is shared with component lowering,
so a legal selected profile survives that boundary without reintroducing unused
alternatives. This is required for the order's permitted-primary-choice control.

Fixed-A declarations previously required a primary but did not require every
Extra Attacks weapon. Random-A activations additionally exposed `skip_extra`
in `melee_weapon_commitment`. Both selection paths must enforce the requirement.
All random weapon/profile choices still precede dice under Order 92's existing
owner-approved timing convention. Commitment, pool and history owners preserve
physical budgets, typed retries, target replacement, persistence and replay.

The search covers fixed/random A, multiple physical copies and profiles,
Extra-only models, ordinary/attached and retained Fight authority, unengaged
bearers, spent One Shot weapons and shared restore/replay consumers. Shooting,
target replacement's permitted forgoing, and Order 113 are outside this repair.
No new named handler, parsing, state owner or adapter path is required.

The independent complete-play probe reproduced O112-CR-1 on this change and
the exact base: after a primary weapon kills the last target, the next weapon
pool treats the still-placed casualty awaiting deferred destruction as absent.
Mandatory Extra Attacks makes that ordinary multiweapon prerequisite unavoidable.
The owner explicitly approved the bounded shared damage-allocation repair in
PR 552. `damage_allocation_targets` now recognizes a dead physical member whose
placement matches a typed pending destruction on the **currently resolving**
`AttackSequence`, supplied by grouped-pool resolution. The stored phase sequence
can lag inside that loop and is not substituted. Living attached recipients take
priority; an unbacked absent target still fails closed. General battlefield
presence and destruction timing are unchanged: remaining pools cannot allocate
damage to the casualty, and deferred reactions/removal still follow the existing
attacks-resolved boundary exactly once. Fixed/random lethal facade regressions
cover retained Extra Attacks, omission/retry, save/load/fork and exact replay.

## Acceptance and delivery

Regressions must reproduce omission and the random finite skip on the base,
reject omission without consuming the request or rerolling, accept the complete
set, preserve legal primary/profile choices and Extra-only attacks, and exercise
physical ownership, pending/accepted JSON save/load, fork isolation, viewer
projections and exact replay. Eligibility controls must avoid requiring weapons
whose bearers cannot attack or whose One Shot use is spent.

The existing finite and parameterized contract families carry this stricter
selection rule without a schema or payload-shape change. The adapter contract
documents the removed skip and mandatory physical inventory; exact runtime
identity prevents importing obsolete histories. Generated runtime identity and
contract examples must be refreshed before aggregate validation.

Apply `SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`: block reproduced incorrect rules,
normal legal-play failures, engine-generated valid save/load/fork/replay failures,
and required trust boundaries. Keep hypothetical coordinated historical editing
separate. Complete covered behavior (85%), code quality, both type checkers,
lint/import/shards/pre-commit, base-ref/generated contracts, TypeScript tests and
live conformance, installed wheel, CI and two distinct exact-head reviews remain
required. Use the default quiet serial live performance smoke and exact-base
assessment; this is a bounded rule repair, not a performance optimization or
full-game certification.

Update this order's roadmap implementation cell before freezing inputs and carry
that maintenance requirement into the Order 113 handoff. Stop after Order 112.
