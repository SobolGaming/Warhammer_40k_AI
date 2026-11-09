# Player policy interface

The maintained [AI implementation and learning plan](AI_IMPLEMENTATION_PLAN.md)
separates the implemented contracts below from broader proposed candidate generation,
information-safe simulation, experiments and full-game qualification.

Exact player-scoped routing, finite candidate sets, finite training linkage,
bounded deployment translations, fork validation and accepted-only ranking,
deployment candidate/row linkage (singleton and validated set), named targets
and Phase 19E contracts exist;
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
now joins that evidence to named/admitted targets. The validated-set companion
below adds exact multi-candidate joins; broader proposal families remain unsupported.

Evidence is operator-only: checkpoint commitments, complete proposal payloads,
authoritative identities and source/build information never become model inputs
or player projections. Existing viewer secrecy and wire schemas are unchanged;
the existing [adapter decision contract](ADAPTER_DECISION_CONTRACT.md) already
covers the reused deployment path. The ordinary setup regression certifies this
bounded proposal family, not movement, charge, shooting, fight, reactions, reserves
or other parameterized mechanics. The bounded deployment generator/validator below
adds formation alternatives; general bulk legality, broader local references,
semantic features, search, dataset admission and runner timing remain follow-ups.

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
[ADAPTER_DECISION_CONTRACT.md](ADAPTER_DECISION_CONTRACT.md). Candidate
tactical/learned ranking, other proposal families, semantic deployment encoders,
broader references, dataset admission and runner progress accounting remain open.

## Bounded deployment alternatives and validation

`ai.deployment_candidate_search.DeploymentCandidateSet.generate(seed, context=...)`
creates `deployment-translation-set-v1` from an existing actor-bound singleton.
The versioned `actor-formation-xy-translations-v1` generator translates every
supplied model by the same XY offset in inches, retaining relative formation,
height, facing and proposal context. Its default ordered offsets are the original
formation, +X, -X, +Y and -Y by one inch. Explicit ordered offsets are supported,
up to 64 pairs. This supplies real alternative positions, not a general placement
solver or a guarantee of valid, useful or complete tactical coverage.

Generation receives only the detached player context, seed and public configuration.
It does not receive a session, hidden opponent state, RNG or validation receipts.
The immutable set retains ordered singleton candidates, the seed, offsets, raw
budget, attempted count, duplicate count and completion reason. Canonical numeric
positions collapse repeated resulting proposals to their first occurrence;
duplicates still consume raw budget. Loading regenerates and compares the complete
payload against the supplied actor context. Candidate IDs retain the existing
singleton meaning and are not engine option IDs or learned semantic features.

`ai.deployment_candidate_validation.ValidatedDeploymentCandidates.validate(...)`
is a separate **operator-only** service. It verifies the live actor observation,
binds the authoritative persistence checkpoint and submits each unique candidate
through `LocalGameSession.submit_viewer_parameterized_payload` on a fresh fork of
that same checkpoint. Accepted and ordinary invalid results are recorded. An
unsupported result or engine error stops validation. No proposal is submitted to
the live session; internal failures create no live retry request, record, event,
placement or RNG change. The supplied deployment validator remains the only rules
authority; this adds no engine method or wire contract.

The raw proposal cap is 64, validation-attempt cap is 64 and accepted-candidate
cap is 16; callers may lower each to zero. These bound proposal/submission counts,
not wall time or individual geometry-solver work. Results stop at the first reached
limit and record attempted, accepted, rejected and unvalidated counts, plus
`complete`, `validation_budget` or `accepted_limit`. Generation separately records
`complete` or `raw_budget`. A partial nonempty accepted set is a deliberate result.
An empty generated or accepted set raises `DeploymentCandidateExhaustedError` with
the stop reason, raw attempts, duplicates and validation attempts. Exhaustion
never proves that no legal placement exists.

Validation receipts include authoritative checkpoint commitments and diagnostics;
they must never be supplied as player/model observations. `from_payload` repeats
engine validation and compares the complete receipt. `select(context, candidate_id,
session=...)` permits only accepted IDs and requires the same current checkpoint;
it returns the ordinary bound `PolicyAction`. The eventual live commit still uses
the ordinary viewer adapter and revalidates legality. Validation alone proves no
executed live transition or training eligibility. The existing accepted-singleton
row contract, `(True,)` mask, slot zero and legacy `TrainingRow` are unchanged.
The separate validated-set training companion below binds these alternatives to
accepted evidence. Accepted-only ranking is described below; other proposal families
and a generic information-safe simulation API remain follow-ups.

The ordinary compact setup regressions in
`tests/infrastructure/adapters/test_deployment_candidates.py` exercise distinct
accepted positions, internal invalid proposals, drift, budgets, duplicates,
hidden-history/private-RNG isolation, immutable roundtrips and actual selection/commit/save/load/
replay. They establish this bounded deployment path, not faction or full-game
qualification.

## Accepted-only deployment ranking

`ai.deployment_candidate_ranking.RankedDeploymentCandidates.rank(...)` is the
operator entry point for a caller-supplied `DeploymentCandidateRanker`. It takes
a typed validation receipt, actor context, current local session,
`DeploymentRankerConfiguration` and explicit run reward-profile version. The
configuration requires `PolicyProvenance` with the RANKER role, canonical JSON
object parameters and `DeploymentRankingBehavior.DETERMINISTIC`: deterministic
given the actor inputs, choice seed and parameters. Before invoking the ranker it
strictly matches catalog packages, ruleset/descriptor, current semantic engine
version and the run reward version, with no cross-version override. It also
checks the receipt's actor binding and exact live checkpoint. The ranker receives only a newly detached
`PlayerDecisionContext` and a tuple of accepted `DeploymentCandidatePayload`
objects in their original generated order, plus a detached `parameters` object
through a required keyword argument. Parameters are explicitly actor-visible
operator declarations; callers must not place private run evidence in them.
Rejected and unvalidated proposals,
generator budgets, the full generated-set hash, validation receipt/diagnostics,
checkpoint commitments, policy provenance, engine/build and game-configuration
commitments, and the session never enter its arguments.

The accepted subset is the deliberate engine-validation trust boundary; its
membership can reveal legality. This API does not claim to hide differences in
legality from a player choosing a legal action. With the same actor context and
accepted payloads, hidden-only work and private future RNG cannot change ranking
inputs. Candidate IDs remain opaque bindings rather than semantic features. As
with `PlayerPolicy`, this is a cooperative Python interface, not a sandbox against
code that independently captures authority in a closure.

A ranker returns a tuple of `DeploymentCandidateScore(candidate_id, value)` entries
covering every accepted ID exactly once. Only finite integer/float values are
accepted; booleans, nonfinite values, overflow and malformed/missing/extraneous/
duplicate scores fail explicitly. Integer scores retain their exact value for
comparison and JSON evidence; the existing finite float-conversion check remains
the admission range bound. Mixed integer/float comparisons do not coerce integer
scores to floats. Higher scores win. Equal scores select the
first accepted candidate in original generated order, independent of returned
score ordering, under `first-generated-accepted-v1`. No fallback choice is made.
The live checkpoint is checked again after the callback and when `select` returns
the ordinary bound `PolicyAction`; selection also requires the original choice
seed. The caller still commits through the ordinary viewer submission, with engine
validation and mutation. The ranking operation itself submits no live action.

The independent **operator-only** `deployment-candidate-ranking-v2` result retains
the validation receipt, hashes of that receipt and complete generated set, a hash
of the actual actor inputs (including parameters), choice seed, typed configuration,
verified current engine-build ID, exact live game-configuration hash, scores
normalized into generated order, selected ID and tie rule. Its returned payloads
are detached. `from_payload` requires the same typed validation evidence and
reruns the supplied ranker against the current checkpoint, then compares every
field, including the supplied run reward version's strict provenance join. Loading
a serialized validation receipt remains the existing separate engine-reproduction
step. Artifact identity and the deterministic behavior marker are caller
declarations, not authentication of Python code or model weights; changed output
fails reproduction. Scores are neither probabilities nor logged action
probabilities. The v2 contract intentionally replaces the v1 callback and receipt;
old v1 evidence retains meaning under its matching runtime and is not silently
rewritten or admitted as v2. The result certifies a bounded ranking, not an executed
transition, useful tactical alternatives or a learned policy.

Focused tests exercise a genuine non-first accepted selection and ordinary commit,
save/load and exact replay; tie ordering; malformed scores and evidence drift;
detached input mutation; hidden-work/private-RNG noninterference; and checkpoint
drift before and during callbacks. Existing validated-set training linkage accepts
the resulting chosen action through its unchanged exact transition checks. No
legacy training schema, runner route, proposal payload or adapter wire contract changes:
[ADAPTER_DECISION_CONTRACT.md](ADAPTER_DECISION_CONTRACT.md) already covers this
same deployment proposal and ordinary submission path. Tactical/learned rankers,
other proposal families, broader references and dataset admission remain follow-ups.

## Deployment model-origin semantic features

`ai.deployment_geometry_features.DeploymentGeometryObservation.from_candidate(...)`
derives an independently versioned `deployment-model-origin-observation-v1` from
one bound actor-view deployment candidate and its `PlayerDecisionContext`. The
closed `deployment-model-origin-features-v1` registry pins these ordered values:

| Feature | Type and dimensions | Units and meaning |
|---|---|---|
| `deployment-model-count` | Integer scalar `[]` | Count of distinct proposed model references, each once across component units. |
| `deployment-origin-centroid` | Real vector `[3]` | Unweighted arithmetic mean of proposed model-origin X, Y, Z in inches. |
| `deployment-origin-span` | Real vector `[3]` | Maximum minus minimum model-origin X, Y, Z in inches. |

The frame is the ordinary proposal's absolute battlefield-world XYZ frame, with
no actor-relative rotation or normalization. Origins are pose positions, not
physical footprint edges, base/hull extents, facing, terrain distances, objective
control or coherency. A singleton has zero span. All definitions declare
`decision_context` source, `actor_view` information scope, exact aggregation and
no categorical vocabulary. Numerical reduction uses geometry ordering so model
reference names and proposal ordering do not affect the seven flattened numeric
`model_inputs`. Actor/request/view/candidate IDs and candidate content hash remain
separate linkage fields, never model inputs. Source descriptors identify the
versioned encoder, not a new rule or official source obligation.

This pure encoder reads only the supplied proposal and actor context. It rejects
empty or duplicate model references, malformed XYZ origins, booleans, nonnumeric
coordinates and nonfinite/overflowing summaries. It does not validate placement
legality or certify the model set against authoritative state. Actual ranking
uses the existing accepted-only boundary and ordinary engine commit. Its exact
loader rederives values and compares all fields, registry definitions and full
candidate/context binding; geometry-equivalent renamed candidates have equal
numeric inputs but distinct evidence. Returned payloads are detached.

`training_features()` emits the corresponding three existing `TrainingFeature`
values, with `encoder:deployment-model-origin-features-v1` provenance. The
separate operator-only `DeploymentTrainingGeometry.from_link(...)` requires an
existing `RankedDeploymentTrainingLink`, complete row and historical context. It
rechecks that link's ranking, selection, accepted transition and full row, derives
geometry for exactly its selected candidate, and requires the complete ordered
row feature definitions, values, shapes and source descriptors to match. The
`deployment-training-geometry-v1` receipt binds the complete ranked-link hash and
derived observation. Its loader redoes these checks; unrelated accepted-candidate
geometry and unsupported extra features fail. Existing rows are not rewritten;
finite features, TrainingRow v1 and target admission retain their semantics.

Focused regressions exercise a non-first geometry-ranked legal alternative,
ordinary commit/save/load/exact replay, exact selected-row joins, definition and
value drift, translation and reference-renaming invariance, and hidden-only work
and private RNG noninterference. This is a partial geometric representation for
the bounded deployment fixture, not a tactical ranker, reference-value calculator,
complete deployment representation, dataset admission or Stage 1 completion.
Other geometry/scoring semantics and the proposed screen/preserve experiment
remain open. No adapter proposal/wire shape changes: the existing
[deployment contract](ADAPTER_DECISION_CONTRACT.md) remains the submission owner.

## Validated deployment-set training linkage

`ai.parameterized_training.DeploymentTrainingCandidateLink.from_row(...)` takes
an existing `TrainingRow`, typed `ValidatedDeploymentCandidates`, historical actor
context and reproduced `ParameterizedAcceptedTransition`. Its independent
`deployment-set-training-candidate-link-v1` payload owns the complete generated
candidate set and operator validation receipt, their hashes, the full row hash,
selected candidate ID/index and accepted-transition hash.

The row mask covers exactly the ordered **validated prefix** of the generated
set. Accepted slots are `True`; rejected slots are `False`. Unvalidated candidates
have no mask slot, so incomplete validation never invents a legality result. The
full generated set and receipt retain their geometry, unvalidated count, budgets,
duplicate/raw counts and stop reasons. Because validation preserves generation
order, the selected index is both its generated-set and validated-prefix slot.
Only an accepted slot can be selected. This says nothing about candidate quality,
coverage of all legal placements or rewards for rejected alternatives.

The link checks the selected ordinary viewer action byte-for-byte, including its
actor/request/view/proposal binding, against the reproduced accepted transition.
The row's authoritative decision record must match. The validation checkpoint
must equal the transition's before checkpoint: identical permitted observations
with different hidden history or private RNG authority cannot be substituted.
The shared singleton verifier enforces the same accepted-action join without
changing the singleton's v1 payload, `(True,)` mask or slot-zero semantics.

`from_payload(..., session=before, transition=...)` regenerates the actor-only set,
reruns the recorded validation budget on ordinary fresh session forks and compares
the complete receipt and row linkage. `require_matches` checks the full row and
historical context against the retained immutable verified evidence. All returned
payloads are detached. This companion is operator-only; checkpoint commitments,
validation diagnostics and authoritative records never enter actor features.

`LinkedTrainingTarget` and `AdmittedTrainingTarget` accept this separate link in
mixed episodes using the same strict source, perspective, transition and exact
endpoint-horizon checks as singleton deployment rows. Only the executed selected
transition receives its target. The separate ranking boundary above can select
that action; this link adds no learner, dataset eligibility, new local reference
calculator or runner accounting. Existing
adapter decisions, wire schemas and engine mutation/replay remain covered by
[ADAPTER_DECISION_CONTRACT.md](ADAPTER_DECISION_CONTRACT.md).

The focused deployment regressions cover rejected and unvalidated selections,
nonzero/nonseed accepted slots, validation and accepted-count budget stops,
row/receipt/context drift, same-view/different-checkpoint rejection, detached
roundtrips with fresh validation, ordinary save/load and reproduced transition,
and named/admitted endpoint CP targets. These are bounded plumbing controls, not
full-game or faction qualification.

## Ranked deployment behavior and row provenance

`ai.parameterized_training.RankedDeploymentTrainingLink.from_row(...)` composes a
reproduced `RankedDeploymentCandidates` with an existing
`DeploymentTrainingCandidateLink` and its complete `TrainingRow`. The independent
`ranked-deployment-training-link-v1` operator payload retains both full receipts
and their hashes plus the row hash. It requires exactly the same validated set,
selected accepted candidate, historical choice seed, current engine build and
complete `PolicyProvenance`, including artifact ID and role. The existing child
link still verifies the row mask, ordinary accepted action, authoritative record
and exact before checkpoint. An accepted action selected by another ranking or
at another checkpoint cannot be relabeled as this behavior.

`from_payload` compares every field against the supplied typed, verified ranking
and candidate link; their existing loaders perform score/engine reproduction.
`require_matches` rejects any full-row or context drift. Returned payloads are
detached. Named/admitted targets continue using `candidate_link`, preserving
existing mixed-episode source/perspective/horizon checks and TrainingRow v1.
This companion supplies deterministic behavior provenance only; it does not
invent stochastic probabilities, authenticate arbitrary model weights, admit a
dataset, add runner attempt accounting or complete Stage 1. The bounded experiment companion below joins this choice to its encoder and
verified episode. Broader run manifests, selected-workload semantic features/references,
other proposal families and tactical/learned rankers remain open.

## Bounded deployment experiment provenance

`ai.deployment_experiment.DeploymentExperimentProvenance.from_episode(...)` joins
one `RankedDeploymentTrainingLink`, its complete row and actor context to a typed
`MixedEpisodeAdmission` and separately supplied trusted game config/reward version.
The independently versioned `deployment-choice-experiment-provenance-v1` receipt
has explicit `single-accepted-deployment-choice` scope. Its content hash identifies
these exact evidence bytes; it is not an authenticated whole-run identifier.

The factory rederives the selected-row geometry, rechecks the complete ranked row,
requires strict source/reward compatibility, and joins both ranking and ordinary
startup/replay origin to the current build and exact config commitment. The exact
accepted transition must occur in the verified episode with the same origin,
trajectory and perspective. An unrelated episode or a config with different
private RNG authority cannot be substituted even when actor observations agree.
The existing admission owner verifies origin reachability and contiguous ordinary
accepted transitions; callers cannot supply a bare episode digest as evidence.

The receipt retains full episode, accepted transition, ranked-row and geometry
payloads. Existing producer receipts preserve the formation seed proposal,
generator version/ordered translations, actual raw and validation/accepted-count
budgets, attempted/rejected/unvalidated counts, choice seed, ranking parameters,
behavior/tie rule and current encoder definitions/values. The translation generator
is deterministic and has no random generation seed. Private engine RNG remains
bound by config/checkpoint commitments and is not published as an actor seed.
The exact loader recomposes all fields from the supplied typed verified receipts;
their own loaders remain responsible for engine and scorer reproduction.

Ranker artifact identity and deterministic behavior are declarations, not
authentication of arbitrary code/weights. Geometry is verified for the selected
training row; this does not prove an arbitrary scorer used that encoder internally.
Episode stop reasons are declarations, not proof of runner limit enforcement.
All receipt data is operator-only and never added to scorer/encoder inputs. The
focused consumer uses geometry to select a non-first accepted placement through
ordinary commit/save/load/replay, then joins its reachable mixed episode.

This is partial experiment provenance. Whole-run routing, limits, attempted/failed
choice accounting, data splits/dataset admission, artifact authentication, broader
information-access/feature vocabularies and Stage 1 completion remain open. Existing
TrainingRow, finite/target schemas and adapter wire shapes are unchanged; the
[deployment adapter contract](ADAPTER_DECISION_CONTRACT.md) still owns execution.

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

`RunReport` now retains an immutable operator-only `RunManifest` as well as
its deterministic run ID. The `bounded-player-policy-run-v3` manifest preserves
the engine build, initial checkpoint commitment (including private RNG authority),
initial decision-record count,
session/source identity, complete exact route registrations and declared policy
configuration, separate policy seed, decision/time limits and requested boundary.
The registry ID is derived from those retained declarations. Policy identifiers
and configurations are **declared-unverified**: the runner neither authenticates
arbitrary callback code/weights nor proves that the callback used its declaration.
Configurations remain registration metadata; they are not new callback arguments.

The detached JSON-safe `bounded-player-policy-report-v3` export records stop and
failure reasons, elapsed time, final checkpoint commitment and final decision-record
count, plus an ordered attempt for every dispatched route,
including missing routes with no policy ID and zero choice/submission durations.
Each attempt binds authoritative and viewer request IDs, actor/route, observation
hash and the actual actor-only choice seed, with failure stage and measured call
durations. `recorded_decisions` counts all records added during submission and
ordinary advancement, including automatic selections and recorded rejections;
it is not an accepted-choice count. `accepted` requires a successful ordinary
submission status plus new records. Typed `INVALID` submissions are `rejected`,
even when a rule-invalid movement attempt was recorded. Other failed statuses or
submission exceptions retain `unverified` rather than claiming acceptance or
rollback. Pre-submission failures are `not_submitted`. An accepted submission
followed by an advancement failure remains accepted with a progress failure stage.

`RunnerError.report` preserves prior progress and the failed attempt. Decision and
time exhaustion retain explicit reasons; a limit reached before dispatch or a
requested boundary creates no invented attempt. Initialization failure before the
manifest is constructed has `manifest=None` and run ID `unstarted`. Unexpected
arbitrary Python callback exceptions still propagate; this is not a durable
all-process crash ledger or a hard watchdog. Cooperative time checks can observe
an overrun only after a synchronous call returns. Reaching a limit is an error,
not a terminal outcome or a training target.

The manifest and report stay entirely outside actor inputs and external wire
payloads. The manifest hash commits to producer declarations, not authenticated artifacts
or a verified whole-game result. Wall-clock diagnostics do not participate in
deterministic decisions. Use the existing session replay artifact for authoritative
execution; the report does not perform independent episode/experiment admission.
The bounded operator admission below joins supplied run evidence to episodes and
deployment rows. Broader workload manifests, hard cancellation, dataset splits,
other feature/target families and Stage 1 completion remain open.

## Runner and bounded deployment dataset admission

`ai.runner_admission.RunnerAdmission.from_report(...)` joins a v3 report to a
`VerifiedEpisodeOrigin`, exact initial/final `LocalGameSession` checkpoints and
an ordered tuple of trusted snapshots immediately before every dispatch. The
origin is the runner's actual starting checkpoint, including any normally
replayed prefix; it need not be the beginning of the game. This bounded entry
requires the runner to start at the verified pending decision boundary: the caller
must ordinarily advance startup before invoking it. A runner started before that
advance, or from a terminal state, is outside this admission factory. The verifier checks
current build/config/session identity, the initial count, final commitment/count,
every snapshot's ordinary persistence replay and complete record-prefix identity.
It reconstructs each actor context and choice-seed derivation, and checks exact
authoritative/viewer requests, route, observation hash, declared registration and
record deltas. Automatic records and recorded rejections remain separate from
accepted choices. Omitted dispatches, shifted origins, changed endpoints, mismatched
contexts and incompatible classification fail closed.

An optional tuple of independently reproduced accepted transitions must be a
contiguous prefix of those attempts, with exact checkpoints, result IDs, ordered
record hashes, accepted-record intervals and predecessor commitments. An optional
finite/mixed episode must cover precisely that prefix. At the final run endpoint,
terminal, requested-boundary, unsupported and other error reports require terminal,
truncated, unsupported and aborted episode classifications respectively. Nonterminal
reasons match the report. If a failed suffix changed the endpoint, the admitted
prefix instead requires `truncated` with
`accepted-prefix-before-runner-failure`; the complete failed suffix remains in the
receipt. A successful submission followed by a progress failure supplies no
verified accepted transition by itself. Runs with no accepted evidence remain
admissible for accounting, including zero-dispatch cooperative time failures.

`DeploymentDatasetAdmission.from_runs(runs, choices=...)` accepts an explicit
nonempty tuple of these run receipts and zero or more four-part choice entries:
run occurrence index, `DeploymentExperimentProvenance`, `LinkedTrainingTarget`
and `AdmittedTrainingTarget`. Every choice must join the same episode and accepted
transition, complete ranked-row/candidate link, exact target hash, actor context
and actual choice seed. To admit a ranked deployment, that attempt's declared
registration configuration must contain `deployment_ranking_hash` equal to the
complete ranking receipt's content hash. The wrapper policy ID is separate from
the ranker artifact ID. A trusted producer can prepare the ranking and its action
before dispatch, then register that commitment and return the action from an
ordinary context-bound callback. No session is captured by or passed to the policy.
This proves consistency with the declared ranking, not execution of arbitrary
callback internals, authenticity of model weights or causality of a scorer call.

The dataset retains every supplied run/report and all submission outcomes, then
derives attempted/failed run counts, attempted choices, accepted/rejected/unverified/
not-submitted counts, admitted rows and eligible rows. Repeated deterministic run
IDs are distinct tuple occurrences. A choice cannot appear twice within an
occurrence. Missing targets and every row from an error report are excluded from
learning; an accepted prefix cannot convert a failed run into a successful outcome.
Successful terminal rows can retain the existing exact endpoint CP target without
inventing match utility. Closed loaders rebuild both receipts from their typed
inputs and reject changed or extra payload data; returned payloads are detached.

All snapshots, registration declarations, attempts, source/build identifiers and
dataset evidence remain operator-only. Player contexts, scorer inputs, semantic
model tensors and adapter/wire contracts are unchanged. This is a bounded supplied-
inventory boundary, not certification of a full dataset or supported full-game
workload. It cannot count omitted external runs, manifest-less initialization
failures or arbitrary callback/process crashes that produced no report. Timing and
failure diagnoses remain producer evidence; wall-clock limits stay cooperative.
Data splits, artifact authentication, other proposal/feature/target families,
training and Stage 1 qualification remain open.

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
