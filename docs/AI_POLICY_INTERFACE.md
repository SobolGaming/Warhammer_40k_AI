# Player policy interface

`ai.player_policy` and `ai.runner` provide a strict, synchronous foundation for
policies over `AdapterGameSession`. They do not implement autonomous battle play,
training, a strategic hierarchy, an evaluator, or hypothetical search.

## Input and decision authority

The trusted runner selects the pending engine actor, requests that player's
`GameViewPayload`, and gives the policy a `PlayerDecisionContext`. Its canonical
JSON snapshot is immutable; reading `observation` or `request` returns a detached
copy. The context contains an exact route and a policy-only deterministic choice
seed. It contains no session, lifecycle, authoritative state, persistence payload,
opponent-private request, engine RNG seed/state, or raw lifecycle status.

New games generate 256 bits of private entropy independently of `game_id`.
Operators can set `GameConfig.private_rng_seed` explicitly for reproducible runs.
The same seed is copied into authoritative state and retained by persistence and
replay. Dice and tactical-card draws consume that private authority. Tactical
draws also persist an engine-owned occurrence sequence; reusing a caller's result
ID does not reuse a previous card ranking. Public state serialization excludes
both private fields. Public game IDs remain unchanged. Published
smoke fixtures use explicit fixed test seeds and are not competitive game seeds.

This is a cooperative Python API boundary, not an isolation sandbox for hostile
code. Callers must not capture an authoritative session in their policy, reuse
the engine seed as the policy seed, or mutate the session concurrently. A future
search service must separately enforce player information and independent future
chance samples; `LocalGameSession.fork()` is not that service.

Each `PolicyRegistration` binds a versioned policy ID and JSON configuration to
one exact `PolicyRoute`: actor, decision type, setup/battle stage, setup step or
battle phase, and proposal kind (or `None` for finite choices). There are no
wildcards or default registrations. Register both players' routes explicitly.
Configuration describes all policy parameters and artifact identities; mutable
policies must begin in the declared initial state for reproducible execution.

`PlayerPolicy.choose(context)` returns `context.select_option(option_id)` or
`context.propose(payload)`. Both bind actor, request ID and observation hash.
The runner rejects binding drift and rechecks the current player projection
before committing through the viewer-scoped adapter submission methods. The engine
retains all rules validation, mutation, accepted records and replay authority.
The existing [adapter decision contract](ADAPTER_DECISION_CONTRACT.md) and wire
finite and parameterized submission families remain the decision authority.

Player-facing requests, nested proposals and event references use identities
assigned from the viewer's redacted history. Additional hidden opponent choices
do not change these identities or the player observation hash. The trusted host
resolves an issued viewer identity before submitting the original authoritative
request to the engine. Wrong actors, unissued identities and stale bindings fail
before mutation. The host/replay methods `submit_option` and
`submit_parameterized_payload` use authoritative identities; policies and wire
clients use `submit_viewer_option` and `submit_viewer_parameterized_payload`.
There is no automatic acceptance of the other identity namespace.

Missing routes, wrong actors, stale/malformed choices, engine invalid/unsupported
results and `CandidateExhaustedError` stop execution. There is no first-legal,
random, alternative-policy or automatic-pass recovery. A fixture's explicitly
chosen decline/completion option is still an ordinary validated player choice.
Rejected hypothetical candidates belong inside a declared search; a rejected
committed action cannot be reinterpreted as a candidate to retry.

## Running and diagnosing

Construct a fresh `BoundedPolicyRunner(session=..., router=...,
limits=RunLimits(policy_seed=..., max_decisions=..., max_seconds=...))` over a
started session. Call `run()` once. `run(stop_at=RunBoundary("battle", "command"))`
requests a successful stop before choosing at that phase. Terminal engine state
is the other successful stop. A decision/time budget or lack of record/request
progress raises `RunnerError`; reaching a budget is not a completed game. The
decision budget counts policy choices. Engine-owned automatic selections retain
their own records and do not consume additional policy choices. A valid
`ADVANCED` submission advances deterministic engine work to the next boundary.

The time limit is cooperative: checked between synchronous calls and after a
policy returns, before committing. It cannot interrupt a blocking call. Use an
external process deadline when hard cancellation is required.

`RunReport` records the run ID, stop reason, elapsed time and each attempted
policy's actor/route/request/ID, choice and submission durations, and acceptance.
`RunnerError.report` preserves prior progress and the failed attempt's timing.
The operator-only run ID commits to the engine build, initial persistence
checkpoint (including engine RNG identity), session identity, exact routing and
policy configuration, separate policy seed, limits and requested boundary.
Wall-clock timings are diagnostics, not part of deterministic decisions.
Keep the existing session replay artifact as the authoritative execution record.

The local adapter owns at most one cached viewer projection, keyed by a freshly
computed full lifecycle hash and the complete viewer context. Returned payloads
are detached, and forks and restored sessions start with no projection cache.
The runner still checks a fresh observation before submission. Reused submission
identities come from the narrower history/request scope captured before the full
display projection; display-only aliases never enlarge submission authority.

Choice seeds and submitted result IDs use only the separate policy seed and the
player-visible game, actor and pending-request identities. They do not use another
actor's policy-call count or the operator-only run ID.

Contract 46 requires the private seed in operator game-config and saved-state
payloads, and a nonnegative tactical draw sequence in saved state. Old
public-identity-seeded checkpoints/replays require their original
runtime; current loaders reject them explicitly. The engine never invents a seed
for a missing saved value, silently changes an existing game's future draws, or
infers a private seed from a public ID. Fresh Python construction may generate
entropy; restoring an existing game must preserve its recorded seed exactly.

## Exact v995 Daemons mirror inventory

Workload: [the 2,000-point app roster](../data/army_lists/cavalcade-shadow-bloodthirster.json),
independently mustered for each player, using `chaos_daemons_cavalcade_2026_11`,
October MFM points, Cavalcade of Chaos + Shadow Legion and Purge the Foe layout 1.
Each side has Be'lakor, a Bloodthirster, a Lord of Change, Nurglings,
Plaguebearers, three Bloodcrusher units and Seekers: nine units and 39 models.
Malice Made Manifest and the three Soul-shattering Charge assignments remain
part of the exact roster. Seven height records are explicitly provisional;
passing a fixture does not verify those measurements.

The inventory below separates this runner's tested path from engine component
support and unverified matchup continuations. It is a starting inventory, not an
exhaustive reachable-state graph. Source/runtime details remain in the generated
[Daemons support matrix](factions/chaos-daemons.md), selected session support
profile and capability manifest.

| Path / rules obligation | Decision family and context | Evidence and limits |
|---|---|---|
| Strict roster, points, geometry, layout | Engine-owned mustering and configured mission setup | Supported by real admission tests; no policy choice is synthesized. |
| Secret secondary selection | `select_secondary_missions`, setup `select_secondary_missions` | Both player routes exercised; explicit fixed Assassination + Bring It Down; opponent's unresolved selection stays hidden. Tactical mode is unverified here. |
| Reserve declarations | `select_reserve_declaration`, setup `declare_battle_formations` | The full setup recipe completes declarations with all units deploying. A separate real-session isolation regression selects Nurglings for Deep Strike and verifies that the extra hidden choice does not change the opponent's observation or events. Subsequent arrival, attachments and transport branches remain unverified here. |
| Alternate unit selection | `select_deployment_unit`, setup `deploy_armies` | Both actors follow the committed deployment recipe. Other deployment orders are unverified here. |
| Legal model placement / Infiltrators | `submit_deployment_placement`, proposal `deployment_placement`, setup `deploy_armies` | All 78 models use the committed source-layout recipe through engine validation. No general placement solver is supplied. |
| Scouts / prebattle actions | `select_prebattle_action`, setup `resolve_prebattle_actions` | Explicitly decline Scout moves. Actual Scout movement proposals and their path witnesses are unverified here. |
| Command arrival | First pending round-1 Command request | Explicit successful boundary before dispatch; no Command policy is registered by the fixture. |
| Shadow of Chaos; selected detachment/Enhancement rules; unit abilities (including Mischief Makers and Unholy Speed); icon/instrument effects | Subsequent phase hooks, finite windows, proposals, rerolls and allocations depend on live state | Selected engine component support exists; consult its exact source-linked matrix. Full mirror composition, choice reachability, scoring and replay across later rounds remain unverified. |
| Movement, shooting, charge, fight, reactions, casualty allocation, reserves, mission actions and scoring | Exact actor/phase/family/proposal routes must be registered when encountered | Unsupported by the supplied setup recipe. Existing engine interfaces do not establish a tested battle policy or a complete mirror game. |
| Missing/incorrect routes and rejected committed actions | Any context | Supported explicit error behavior; execution stops without substitution. |

`tests/factions/chaos_daemons/integration/test_cavalcade_v995_roster.py` exercises
42 accepted setup decisions through this interface, checkpoint restore and exact
replay, stopping at round-1 Command. It also checks player detachment/redaction,
exact routing, action bindings, rejection without retry, seed/config identity and
bounded stops. The fixture is a reproducible integration workload, not evidence
of competitive AI, delayed credit assignment or completed-game performance.
