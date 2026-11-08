# Player policy interface

The maintained [AI implementation and learning plan](AI_IMPLEMENTATION_PLAN.md)
separates the implemented contracts below from proposed candidate generation,
information-safe simulation, experiments and full-game qualification.

Exact player-scoped routing, finite candidate sets, finite training linkage,
accepted deployment candidate/row linkage, named targets and Phase 19E contracts exist;
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

## Accepted finite transitions and bounded trajectory linkage

`ai.training_transitions.FiniteAcceptedTransition.from_sessions(...)` is the
operator-only `finite-accepted-transition-v1` companion. Supply the original
finite link, row, historical context, and trusted before/after `LocalGameSession`
checkpoints, plus an explicit trajectory ID and value perspective. It checks the
complete candidate/row join and the before actor observation, then repeats the
chosen ordinary viewer submission on an isolated exact-replay fork. It never
submits to either supplied session or gives the fork to a policy.

A `DecisionRecord` is insufficient: the engine records some rule-invalid attempts
before returning their rejection. The verifier requires a successful submission
and, when it returns `ADVANCED`, successful deterministic advancement to the next
waiting or terminal boundary. Invalid and unsupported outcomes fail explicitly.
The complete reproduced after checkpoint must match, including state, private RNG,
history and configuration. No caller-supplied acceptance flag is trusted. This
also rejects record-only histories, a different selected option, missing records,
unrecorded state changes and mismatched viewer/authoritative identities.

The companion records the candidate-link hash, both checkpoint and same-actor
observation commitments, the submitted authoritative request/option/record/result
identity, and ordered hashes of every reproduced record. Actor, active turn and
value perspective remain separate. Before/after positions retain stage, setup
step, battle phase and round. These identities and hashes are linkage evidence,
not semantic model inputs; keep the companion and checkpoint access operator-only.

`accepted-engine-records-from-origin-v1` starts at zero at the explicitly supplied
slice origin. Every successful reproduced engine record, including automatic
selections, advances the index. It does not reinterpret the global record ordinal
or count rejected attempts before the origin. Passing `previous=` requires the
same trajectory and perspective, an exact preceding after-checkpoint commitment,
and a continuing predecessor. The next start equals that predecessor's stop;
its hash and origin commitment are retained. Missing, reordered, duplicated or
gapped links cannot load as the same trajectory. Returned payloads are detached
and the evidence is immutable.

The closed loader requires the same trusted inputs, explicit trajectory and
perspective, and predecessor; it repeats engine reproduction and compares the
complete canonical evidence. `terminal` means an engine terminal boundary;
`continuing` makes no claim about how an experiment eventually ends. No reward,
winner, future scoring or chance sample is added to actor observations.

This is bounded finite-transition verification from a supplied origin. It does
not authenticate that origin, prove its reachability, classify an entire episode
as truncated/aborted/unsupported, validate target calculations or source-policy
compatibility, or admit a dataset by itself. Admission must combine these checks
with permitted semantic features, target/evidence validation and provenance.
The separate episode/target admission companion below verifies origin reachability,
finite slice continuity and a bounded set of target calculations. Other parameterized
transition families and complete dataset admission remain follow-up work. Legacy rows,
targets, runner behavior, replay and the ordinary adapter/wire decision contract
remain unchanged.

## Episode and target admission

`ai.training_admission` is an opt-in operator-only companion. It does not change
legacy rows, the runner, player observations or the adapter/wire contract.

`VerifiedEpisodeOrigin.from_session(session, config=...)` takes a separately
trusted exact `GameConfig`, creates a fresh ordinary `LocalGameSession`, starts
and advances it, and compares the recorded initial lifecycle to that startup.
It then restores the supplied checkpoint through the existing exact persistence
replay, checking the full lifecycle, decisions, events and private RNG. A hash or
an internally consistent replay rooted at an arbitrary altered state is rejected.
The admitted origin must be a pending decision boundary. Ordinary finite and
parameterized replay may occur in the prefix; this does not admit parameterized
training transitions. Configuration/source correctness and workload support still
need independent qualification. Directly altered fixtures are design inputs.

`FiniteEpisodeAdmission.from_transitions(...)` requires that verified origin, a
nonempty immutable tuple of accepted finite transitions, and the exact final
session. It checks origin/predecessor/checkpoint commitments, ordered record hashes,
trajectory and perspective, and contiguous accepted-record start/stop indices.
Every transition from the origin to the endpoint must be included. The clock is
`accepted-engine-records-from-origin-v1`, including automatic engine selections;
it is independent of actor alternation, elapsed turns and runner timing.

`terminal` requires an actual complete engine state and its validated final-scoring
result. `truncated`, `aborted` and `unsupported` require an explicit nonempty stop
reason and a nonterminal endpoint. Those reasons are operator declarations, not
proof of an infrastructure diagnosis or mechanic support. They retain attempted
episode evidence without inventing terminal results.

`AdmittedTrainingTarget.from_episode(...)` takes the exact linked target, row,
candidate link, historical context, admitted transition/episode, trusted config and
independently supplied experiment `reward_profile_version`. Source/catalog/rules
and engine-version compatibility is strict, with no cross-version override.
The current engine build is pinned separately. Perspective and episode end must
match; the transition must belong to that episode and link exactly to that row.

Observed `match_utility` and `vp_margin` require producer `engine-final-scoring-v1`
and `evidence_hash=payload_digest(episode.to_payload()["final_result"])`. Utility is
checked against the actual engine winners (win 1, draw 0.5, loss 0); VP margin is
own minus opponent terminal capped VP. The match horizon must reach that exact
terminal endpoint. Observed local references use the bounded verified calculator below; arbitrary
producer IDs and hashes do not authenticate a calculation.

Missing targets require producer `episode-boundary-v1`, the episode content hash,
and its exact declared nonterminal stop reason. Their receipt always sets
`eligible_for_learning=false`. Future decision horizons on missing local targets
are declarations of unobserved work, not achieved horizon or value evidence.
Receipts bind the target/row link, transition, episode and actual accepted-record
start/stop. They never reinterpret the original scalar `target_value`.

`VerifiedLocalReference.from_episode(...)` supplies the independently versioned
`verified-local-reference-v1` operator companion. Its only current calculator is
`command-point-balance-v1`, produced by `engine-command-point-balance-v1` with
`command_points` units: the perspective player's remaining CP at the exact
admitted endpoint, read through `GameState.command_point_total`. This is a local
resource observation, not match utility, resource-change attribution or evidence
that saving CP improves tactical results. No reward weight is prescribed.

Supply the admitted episode, its selected transition, exact final session, target
ID and positive integer `horizon_decisions`. The horizon starts at that selected
transition's `accepted_record_start`, including the selected action, and ends at
the episode's `accepted_record_stop`. Accepted automatic selections count even
when CP is unchanged. Rejected attempts cannot extend the accepted finite chain;
prefix records before its origin do not count. This bounded calculator supports
only the supplied episode endpoint. Short/long horizons, including a horizon
inside an atomic transition's automatic records or beyond an early terminal
boundary, fail explicitly. An earlier observable endpoint needs its own admitted
slice; no checkpoint or value is interpolated.

Only terminal and truncated episodes can produce observed local references.
Aborted/unsupported episodes retain missing targets excluded from learning. The
calculator binds the episode/transition/checkpoint hashes, perspective, count
interval, units, producer and value; the episode binds the verified source/build.
It checks the exact checkpoint and source identity before reading the resource.
The closed loader repeats that computation and compares the entire evidence.

To admit an observed local target, use this fixed target ID, producer and units,
its computed value and `evidence_hash=reference.content_hash`, then supply the
same `final_session` to `AdmittedTrainingTarget.from_episode` or its loader. Both
recompute the reference instead of accepting a calculator flag or a numeric hash
claim. Unknown calculators, wrong values/units/producers, incompatible sources,
drifted endpoints and mismatched horizons fail closed. Existing target, row and
admission payload versions are unchanged; the optional endpoint argument is
required only for observed local references. All checkpoint/evidence access stays
operator-only, outside policy inputs and player projections.

All four admission companions are immutable and return detached JSON payloads. Their
closed loaders require the same trusted inputs and repeat verification before
comparing every field. Keep checkpoints, source/build identities, scoring audit
and admission receipts outside model inputs and player projections. This bounded
finite-slice/terminal-and-local-target admission does not qualify a dataset, broader semantic
features, hidden-state planning, a full-game workload or playing strength.

## Bounded parameterized transitions and mixed episodes

`ParameterizedAcceptedTransition.from_sessions(action, ...)` adds the separate
`parameterized-accepted-transition-v1` operator companion. Its only supported
route is `submit_deployment_placement` / `deployment_placement` in setup
`deploy_armies`. Supply the original `PolicyAction`, its historical actor context,
trusted before/after local sessions, trajectory and value perspective. The action
must match the actor, issued viewer request and observation hash exactly. The
complete actor-view proposal is retained as immutable evidence; its identities
are resolved by `submit_viewer_parameterized_payload` on the isolated replay fork.
The existing adapter deployment contract supplies all legality and mutation.

Finite and parameterized verification share one reproduction and continuity
owner. Both require successful engine submission, ordinary advancement, the exact
selected authoritative record and complete after checkpoint. Deployment rejects
rule-invalid placements before recording and preserves the pending request and
checkpoint for a legal retry. Neither those rejected proposals nor recorded
rejections from unsupported families are accepted transitions. Movement's recorded
invalid-attempt/retry path is tested only as an unsupported-family negative
control; it is not certified by this companion. Stale, drifted, malformed, wrong-actor and
wrong-family inputs fail explicitly. The closed loader repeats the complete
ordinary submission and compares every canonical evidence field.

`MixedEpisodeAdmission.from_transitions(...)` uses
`mixed-episode-admission-v1` and accepts finite and supported parameterized
evidence, including finite → placement → finite chains. It shares the existing
ordinary origin, source/config, record, endpoint and end-classification checks.
Finite transition `previous=` may name either concrete verified transition type;
the finite transition payload and chosen finite action retain their v1 meanings.
`FiniteEpisodeAdmission` still rejects parameterized members. Both episode
loaders revalidate the complete chain; payloads are detached and immutable.

`VerifiedLocalReference` also accepts a mixed episode and any of its verified
transitions. Its unchanged `command-point-balance-v1` calculator requires the exact
endpoint and accepted-record horizon, including automatic selections. This proves
bounded endpoint CP evidence. The separate accepted deployment row companion below
now joins that evidence to named/admitted targets; broader proposal families and
candidate-search sets remain unsupported.

Evidence is operator-only: checkpoint commitments, complete proposal payloads,
authoritative identities and source/build information never become model inputs
or player projections. Existing viewer secrecy and wire schemas are unchanged;
the existing [adapter decision contract](ADAPTER_DECISION_CONTRACT.md) already
covers the reused deployment path. The ordinary setup regression certifies this
bounded proposal family, not movement, charge, shooting, fight, reactions, reserves
or other parameterized mechanics. Candidate generation, nonmutating bulk legality,
broader local references, semantic features, search, dataset admission and runner
timing remain follow-ups.

## Accepted deployment candidate and row linkage

`ai.deployment_candidates.DeploymentPlacementCandidate.from_action(action,
context=before)` captures one supplied actor-view placement using
`deployment-placement-candidate-v1`. Its content-derived candidate ID binds the
complete canonical proposal, actor, viewer request and observation. The closed
loader rechecks that context and the complete payload. `select(context)` returns
the existing bound proposal action. Payload reads are detached, and no session,
authoritative identifier, checkpoint, private RNG or outcome enters this snapshot.

This is the submitted candidate, not a generated or ranked set. Capturing it does
not validate placement legality, completeness or the quality of alternatives.
Malformed or rule-invalid proposals cannot acquire an accepted row receipt:
the ordinary engine acceptance verifier remains mandatory.

`ai.parameterized_training.ParameterizedTrainingCandidateLink.from_row(...)`
takes the original row, candidate, actor context and independently reproduced
`ParameterizedAcceptedTransition`. It requires complete viewer-action equality,
the before observation and actor, the exact authoritative decision record,
the row's game and content-derived chosen candidate ID. Its only mask is
`(True,)` and its chosen index is zero: this records the one accepted proposal,
with no unexecuted or rejected alternatives represented as legal slots.
The `parameterized-training-candidate-link-v1` payload commits to the complete
legacy row, candidate and accepted transition. Loading requires the original row,
context and verified transition and checks every serialized field. Mutable row
diagnostics, features, scalar targets, masks and provenance are covered by the row
hash; original row bytes and scalar meanings remain unchanged.

This link is operator-only. Its accepted evidence and authoritative IDs do not
become candidate/model inputs, and its existence does not certify semantic
features or dataset eligibility. The candidate ID is linkage metadata, not an
engine option ID or a semantic feature.

`LinkedTrainingTarget` now accepts the finite or accepted-deployment row
companion. `AdmittedTrainingTarget` accepts those rows in a verified mixed
episode, requires the exact selected transition and preserves strict source,
perspective, reward, endpoint and horizon checks. A parameterized row must use
its verified deployment transition; cross-family joins fail. Finite rows can
also be admitted within a mixed episode. The separate
`mixed-target-admission-v1` receipt binds the mixed episode, selected transition
and linked target; existing finite-only receipts retain their v1 payload.
Observed terminal utility/VP and exact endpoint CP retain their existing
calculators, while explicitly missing targets remain excluded from learning.
Actor and target perspective can differ. The ordinary setup-to-terminal control
proves this plumbing in a compact canonical Command/Fight configuration, not
full-game workload qualification.

This adds no actor-facing or wire shape: ordinary deployment submission,
engine validation, replay and viewer redaction remain governed by
[ADAPTER_DECISION_CONTRACT.md](ADAPTER_DECISION_CONTRACT.md). Multi-candidate
generation/ranking, other proposal families, semantic deployment encoders,
broader references, dataset admission and runner progress accounting remain open.

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
finite or accepted-deployment training candidate link. Its unchanged
`named-training-target-link-v1` loader requires
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
