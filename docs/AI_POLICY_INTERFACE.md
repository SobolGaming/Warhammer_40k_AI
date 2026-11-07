# Player policy interface

The maintained [AI implementation and learning plan](AI_IMPLEMENTATION_PLAN.md)
separates the implemented contracts below from proposed candidate generation,
information-safe simulation, experiments and full-game qualification.

Exact player-scoped routing, finite candidate sets, finite training linkage,
named target declarations and Phase 19E provenance/training contracts exist;
autonomous battle policies, training and full-game qualification are not established.
The historical grouped Phase 19/20 row is not an assertion that those foundations
are absent, nor an individual mapping of every 19A-19F subphase.

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

## Finite candidate contract

`ai.finite_candidates.FiniteCandidateSet.from_context(context)` captures every
engine-enumerated finite option in its original order from the actor's detached
observation. Each immutable `FiniteCandidate` owns the complete canonical option
JSON (ID, label and payload), returns detached copies, and exposes a SHA-256
content hash. Candidate IDs are the issued viewer option IDs, used for linkage.

The versioned set payload records schema `finite-candidate-set-v1`, generator
`player-view-finite-options-v1`, validation identity
`engine-enumerated-options-v1`, actor, request, observation hash and ordered
options. Its content hash commits to that complete payload. Loading rejects
unknown or missing fields, unsupported identities, invalid option shapes,
duplicate IDs, malformed bindings and empty sets. The validation identity means
the options came from an engine request; loading alone does not establish current
legality or authenticate an external producer.

Call `candidates.select(context, candidate_id)` to produce the existing
`PolicyAction`. Selection first reconstructs the complete set from the supplied
context and rejects actor/request/observation, option-content or order drift.
The runner still checks a fresh player projection and commits through the
ordinary adapter/engine authority. The existing finite submission contract in
[ADAPTER_DECISION_CONTRACT.md](ADAPTER_DECISION_CONTRACT.md) already covers that
action; no player-facing request, option, wire schema or validation path changes.

Parameterized requests fail explicitly: their submit marker is not a generated
legal proposal. Empty finite requests raise `CandidateExhaustedError` without a
substitute action. `TrainingRow` remains independently versioned; the companion
contract below checks its finite candidate linkage. Candidate hashes and IDs
are linkage metadata, not semantic policy features.

## Finite training candidate linkage

`ai.training_candidates.FiniteTrainingCandidateLink.from_row(row, context=before)`
creates the versioned `finite-training-candidate-link-v1` offline companion for an
existing `TrainingRow` and its historical `PlayerDecisionContext`. It owns the
immutable complete candidate snapshot, a SHA-256 commitment to the full canonical
row payload, and the chosen candidate ID. Serialized records include the candidate
set hash and the derived zero-based chosen index.

The mask has exactly one slot per candidate in the engine's order. Every slot is
`True` because this finite set contains all engine-emitted legal options; a global
action dictionary or policy pruning mask has different semantics. The chosen action
ID must be an issued candidate, and the row's game must match the observation.
Existing rows remain readable under their existing schema; incompatible finite
joins fail explicitly rather than inventing a mapping or changing a mask.

`from_payload(payload, row=row, context=before)` requires both original inputs and
checks the closed schema, both content hashes, slot/index consistency, and the
complete actor/request/observation/option binding. `require_matches(...)` repeats
the row/context join checks for an existing link. It detects later changes to
row features, provenance, targets, record references or mutable diagnostic metadata. The link
retains no mutable row, session, private RNG authority or authoritative state.
Reading its payload returns detached candidate data.

These are offline linkage records, not actor features. Training admission still
requires source/rules compatibility, accepted-transition and viewer/authoritative
identity joins, permitted semantic features, meaningful targets and experiment
provenance. A decision-record reference alone does not prove an accepted outcome.
The existing scalar target keeps its original semantics. This contract introduces
no training run, learner, outcome label or player-facing/wire contract change.

## Semantic finite observations

`ai.semantic_features` defines the independent registry
`finite-semantic-features-v1`, observation
`finite-semantic-observation-v1` and row companion
`finite-training-observation-v1`. The closed initial registry contains the
existing `decision-option-count`: a positive integer, count units, scalar tensor
dimensions `()`, `decision_context` source, and `actor_view` information scope.
It counts the complete ordered engine-emitted finite options in the detached
player context. Parameterized markers and empty sets are rejected. There is no
categorical vocabulary in v1; `vocabulary_version` must be null. Additional
required features/operators need an explicit registry version and encoder.

`SemanticObservation.from_context(context)` derives the value from that view.
Its closed loader requires the original context and recomputes the complete
observation, rejecting changed bindings, definitions, units, dimensions, scope,
vocabulary and values. `model_inputs` exposes only the numeric tuple in registry
order. Actor/request identities and observation hashes are separate linkage
fields; option IDs, labels, payloads, entity/source references, arbitrary names,
choice seeds, raw observations and row diagnostics never enter that tuple.
Actor-view scope includes the actor's own permitted private choices; it does not
certify their option count as public to opponents or authorize sharing the
companion with another viewer. Existing adapter redaction remains authoritative.

`FiniteTrainingObservation.from_link(link, row=row, context=before)` binds the
observation to the full `FiniteTrainingCandidateLink` hash and rechecks the exact
row/context/candidate join. Every legacy input must match the registered
definition, integer value and decision source descriptor; missing, extra,
unregistered or inconsistent features fail explicitly. The closed loader and
`require_matches` repeat those checks. Existing `TrainingRow` bytes, schema,
scalars and readers are unchanged; this is an opt-in companion, with no inferred
conversion or automatic feature filling.

These checks establish a bounded encoding and offline integrity join. They do
not authenticate an external projection, prove accepted transitions, admit a
dataset, provide complete unit/weapon/geometry/scoring semantics, or add a learner.
The ordinary finite adapter submission and wire contract already cover the
unchanged decision path.

## Named training target declarations

`ai.training_targets.NamedTrainingTarget` is the independently versioned
`named-training-target-v1` producer declaration. It carries a versioned target ID,
meaning, player perspective, horizon, episode end, observed/missing validity,
value and units, missing reason, producer version, evidence SHA-256 and reward
profile version. It never infers a label from `TrainingRow.target_value`; that
historical scalar remains unchanged.

The closed v1 meanings are:

- `match_utility`: terminal win 1, draw 0.5 or loss 0 from the stated player's
  perspective, with `unit_interval` units;
- `vp_margin`: own minus opponent terminal VP, an integer in `victory_points`;
- `local_reference`: an externally defined, versioned reference target ID with
  explicit units and a positive horizon measured in accepted engine decision
  records, including accepted automatic selections. Recorded rejected attempts
  do not advance it. Admission must verify that index; this declaration cannot.

All v1 targets are undiscounted. Match targets require the complete-match horizon.
An observed match target requires a declared terminal episode; truncation cannot
supply a fabricated match outcome. Missing targets have `value=null` and a required
reason. Aborted and unsupported episodes require missing targets. A declared local
reference may be observed at its bounded horizon while the episode is truncated;
it does not become match utility. Booleans, non-finite numbers, lossy integer
conversion, unknown meanings/fields and inconsistent units/horizons fail explicitly.

`LinkedTrainingTarget.from_link(link, row=row, context=before, target=target)`
binds the complete declaration to the SHA-256 of an exact
`FiniteTrainingCandidateLink`. Its `named-training-target-link-v1` loader requires
the original link, row and historical context, rechecks their complete join,
requires the same reward profile, and checks that the value perspective names an
actual observation player. That player may differ from the decision actor.
Each named target is independently linked and immutable; payloads are detached.

These are offline integrity/declaration contracts. An evidence hash is a
commitment, not authentication or a loaded evidence validator. Neither a declared
terminal flag nor a syntactically valid target proves an engine outcome, complete
trajectory, accepted transition, correct reference calculation, compatible source
build, permitted features or dataset eligibility. A producer/admission stage must
verify those facts and the local reference definition before learning. No
conversion of old scalars, training data producer, learner, tactical result or
player-facing/wire change is introduced.

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

The local adapter always projects current authoritative state. It reuses only a
viewer identity map derived from complete event history and the full viewer
context, checking a fresh history-content hash on each use. Each consumer gets an
owned copy; pending-request and display aliases cannot change the retained map or
enlarge submission authority. Forks and restored sessions start with no identity
cache. The runner still checks a fresh observation before submission. Immutable
policy observations are canonicalized once; their hashes use those exact bytes.

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
