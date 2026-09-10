# Order 35 / P15G / C15-07 — Rapid Ingress eligibility

Baseline: `42760e107d361f30bdf19b5d9fa6c2cc67fb9c7a`, fetched from current
`origin/main`. Task began approximately 2026-09-10 02:43 UTC. Scoped branch:
`codex/order-35-rapid-ingress`. Independent approval and full CI remain separate gates.

The approved P15D package retains the complete 15.07 statement in
`core_stratagems_2026_08/artifacts/package.json`, source
`gw-11e-core-stratagems:core:rapid-ingress`, transcription SHA256
`2e9028ed2bf0c1fa19d7774ceb7bb81d415097e38b47c78ab67d7cff303955f6`, observation
`42c4328d54aa18d826225dedd0b1e0043f4d8e3fe0f2e09d1ab12db7913314a6`.
The source-authority registry authenticates its immutable 40k.app audit and
historical policy. Historical official artifacts and observation hashes remain unchanged.
The searchable 15.07 mirror agrees on the operative eligibility and cost clauses.
The live 20.04 page was read in the browser on 2026-09-10 after ordinary page
verification completed; the HTTP text reader returned 403. It requires a unit in
Strategic Reserves, excluding embarked cargo, set up wholly within 6 inches of
battlefield edges and more than 8 inches horizontally from enemies; before round
3 it excludes the opponent deployment zone. Other movement is forbidden until
the next Charge phase unless separately permitted. 20.03 ordinarily permits
arrival from round 2. These placement owners and restrictions are preserved.
References: [15.07](https://www.40k.app/rules/15-stratagems),
[20.03–20.04](https://www.40k.app/rules/20-strategic-reserves).

| Source / invariant | Owning API | Live consumers | Regression |
|---|---|---|---|
| 15.07: no first battle round, either turn | Shared Rapid Ingress availability using `GameState.battle_round` | Option/proposal availability, finite and parameterized pre-pop submission, handler apply | Both reacting players; forged claimed round; stale accepted option; unchanged CP/use/queue/reserve/placement |
| 15.07: friendly Strategic Reserve, excluding current AIRCRAFT | Direct reserve query + `rules_unit_view_by_id` model-owned current keywords | Target enumeration, target binding, shared eligibility, pending placement | Empty/only-excluded/mixed inventories; FLY legal; current component/model identity; no reserve-wide scan per candidate |
| 15.07: opponent Movement end, 1 CP and ordinary restrictions | Existing context drift, timing, cost, Battle-shock and use-limit authorities | Facade/lifecycle preflight and engine-owned application | Wrong player/window, insufficient CP, Battle-shock, duplicate use |
| 20.04: real Ingress set-up, canonical rules-unit ownership | Existing placement/reserve arrival/restriction APIs | Placement proposals, geometry rejection/retry, phase-end continuation | Legal placement resumes parent; invalid geometry retains paid CP/use and emits retry |
| Accepted decisions and Ingress origin remain authoritative | Existing decision-event and reserve-arrival use provenance | Standalone restore, persistence, exact replay, both viewers | Retimed/rebound/relabelled pending requests reject; valid target/placement/retry restore |
| Independent first-round Ingress permission | Existing generic Ingress handler and source-backed context | Shared placement helper and continuation | Generic authorized first-round arrival remains valid; override cannot authorize Rapid Ingress |

P09A owns the interleaved Movement selection; P02D owns model keyword/presence and
canonical attached rules-unit queries. No new ledger, handler, decision family,
geometry algorithm or later Order is introduced. Shared canonical Stratagem test
setup is extracted from the existing large test module for reuse, with legal
Strategic Reserve fixtures replacing permissive generic-reserve Rapid Ingress fixtures.

Performance workload (defined before production edits): legal round-2 selection
and target submission, round-1 rejection, AIRCRAFT rejection, and a mixed 16-unit
reserve inventory. Time setup separately from query/selection/submission; profile
work separately, with no coverage or competing workers. Retain baseline results
as cost evidence even where behavior is incorrect. Full-game certification remains
outstanding; no complete legal headless driver is added by this repair.

## Candidate scope audit

The same-class search covered both eligibility paths, finite/parameterized
pre-pop validation, handler dispatch, shared Ingress placement and retry,
reaction continuation, and reserve-arrival restoration. Target binding now uses
a direct canonical reserve query instead of re-enumerating every reserve per
candidate. Existing cost, Battle-shock, use limits, geometry, event emission,
viewer redaction, and generic first-round Ingress owners are unchanged.

Two additional instances were necessary to close this eligibility invariant:
submitted Rapid Ingress contexts must equal the issued context before queue pop;
pending placement/restoration must authenticate the Rapid Ingress origin before
using shared generic placement permissions. The repair reuses the existing
reserve-arrival use-provenance validator. There is no new historical ledger,
handler family, geometry algorithm, or adapter-specific execution path.

The focused matrix passed 57 tests, exit 0 (53.912 seconds including process
supervision), before final typing cleanup. Coverage includes both reacting
players, empty/excluded/mixed inventories, finite and parameterized rejection,
current model keywords while off board, canonical attached reserve IDs, target /
placement / arrived checkpoints, exact replay and both-viewer deltas, corrupted
round/target/origin, placement retries and parent resumption. The existing
source-backed From Beyond the Veil round-one test also passes.

Initial type checks found JSON annotation and extracted-helper export issues;
these are corrected before publication. Aggregate coverage/quality, final type
checks, generated contracts/clients, package/conformance, and final matching
base/head performance evidence remain pending at draft publication. The user's
task-specific early-draft authorization defers their publication timing only.
Source hashes and partial semantic-support classification remain unchanged.

The preimplementation v1 timing/profile results are retained in
`performance/order35/preimplementation-base*.json`. The final v2 workload adds
actual placement and parent continuation because preflight now authenticates
that checkpoint; it will be measured on the same exact base and head with
identical benchmark/fixture hashes. This extends evidence without dropping any
of the originally measured cases.
