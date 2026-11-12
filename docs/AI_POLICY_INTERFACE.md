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
The versioned `actor-formation-xy-translations-v2` generator translates every
supplied model by the same XY offset in inches, retaining relative formation,
height, facing and proposal context. Its default ordered offsets are the original
formation, +X, -X, +Y and -Y by one inch, followed by the same four directions
by two inches, then `(1,1), (-1,1), (1,-1), (-1,-1)`. Both original five- and
nine-candidate prefixes are preserved for smaller raw budgets. The translation
algorithm and version-one set wire schema are unchanged; closed loading rejects
predecessor generator identities. Explicit ordered offsets are supported,
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

This is partial experiment provenance. The separate runner admission and dataset
partition contracts below retain supplied run/choice accounting and split groups.
Artifact authentication, broader information-access/feature vocabularies and
Stage 1 completion remain open. Existing
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
deployment rows; the separate split contract partitions that admitted inventory.
Broader workload manifests, hard cancellation, other feature/target families and
Stage 1 completion remain open.

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
The separate bounded split contract below partitions this supplied inventory.
Artifact authentication, other proposal/feature/target families, training and
Stage 1 qualification remain open.

## Bounded deployment dataset partitions

`ai.deployment_dataset_split.DeploymentDatasetSplit.from_datasets(...)` accepts
a nonempty tuple of existing `DeploymentDatasetAdmission` receipts and a tuple
of `DeploymentSplitAssignment` declarations. Each assignment names exactly one
`(dataset_occurrence, run_occurrence)`, a `DeploymentDatasetPartition` (`train`,
`validation` or `test`), a nonempty scenario-family label and a nonempty geometry-
group label. Missing, duplicate, conflicting or unknown occurrence assignments
fail closed. Empty partitions are explicit; no split ratio or random assignment
is inferred.

Every run occurrence, including an excluded or zero-row failed run, belongs to
one partition with all its rows. A conservative trajectory commitment binds the
verified startup checkpoint, source identity and build: alternate replayed
prefixes, branches and player perspectives from that same startup stay together.
This uses the original startup, not the run's potentially later slice origin,
runner ID, row ID or accepted-transition hash. Existing declared trajectory IDs
also bind supplied slices together, even across distinct startup commitments.
Repeated trajectory identities must have identical scenario-family and geometry-
group declarations. Each trajectory, declared family and declared geometry group
must belong to a single partition across all supplied datasets. Namespaces for
family and geometry labels are separate; labels are exact and case-sensitive.

The versioned `deployment-dataset-split-v1` receipt retains every complete source
dataset, its hash and every dataset/run/choice occurrence. Duplicate datasets and
deterministic runs within a partition remain separate counted occurrences. Each
partition references complete runs and rows and derives attempted/failed runs,
attempted choices, every submission outcome, admitted/eligible rows and excluded
rows. These counts reconcile with the global inventory, including empty partitions
and zero-dispatch failures. A split never promotes a previously excluded row.
The exact loader rebuilds the receipt from typed admitted datasets and assignments;
altered sources, memberships, declarations or counts fail, and payloads are detached.

Group evidence is explicitly `declared-unverified`. The contract enforces supplied
labels and startup identity; it does not independently authenticate equivalent
geometry, discover undeclared scenario relationships, prove statistical independence,
or identify all equivalent trajectories across changed configurations/builds.
Operators must declare those relationships consistently before freezing a split.
It cannot account for omitted external runs or report-less failures. This is an
operator-only inventory contract with no new policy/scorer inputs, adapter wire
shapes, learner or Stage 1 qualification claim. The existing deployment adapter
contract still owns every executed choice.

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

## Bounded deployment workload contract

`ai.deployment_workload.DeploymentWorkloadContract.from_split(...)` supplies
the operator-only `deployment-workload-contract-v1` reference manifest. The
selected contract workload is setup finite routing plus bounded deployment
placement, model-origin summaries and endpoint CP observation. It is deliberately
different from the proposed screen/preserve delayed-tradeoff experiment and the
v995 Daemons setup recipe below.

Supply a typed `DeploymentDatasetSplit`, the exact distinct `GameConfig` values
used by its complete run inventory, and distinct exact required `PolicyRoute`
declarations. Configuration hashes cover roster, mission, geometry/source inputs,
rules, private seed and all other serialized configuration fields; the receipt
stores hashes rather than duplicating raw configuration/private seeds. Every run,
including duplicate and zero-row failed occurrences, must match that inventory.
Missing, extra or repeated configuration declarations fail. The retained complete
split binds verified source/build/startup/episode evidence, experiment generation
and validation budgets, run seeds/limits, partition membership and every failure
denominator; the manifest never reclassifies excluded rows.

The bounded route declarations permit setup finite contexts and deployment
placement proposals only. Every actual attempted route and declared runner
registration must be included. Observed and unobserved required routes remain
separate: declarations are not an exhaustive reachable-state graph, and an
unobserved route is not certified support. A supplied unsupported-route attempt
can remain recorded without a policy registration. No callback or gameplay is
executed by this constructor.

The manifest pins the complete existing finite-option-count and deployment
model-origin feature definitions, including registry versions, units, dimensions,
aggregation and information scope. Admitted deployment rows already rederive the
selected geometry through their experiment receipts; supporting finite episode
transitions are not thereby promoted into a populated semantic training dataset.
The selected target reference is `command-point-balance-v1`, with its existing
exact accepted-record endpoint, `command_points` units and verified calculator.
Missing labels retain the existing episode-boundary producer and exclusions.
A dataset can legitimately contain other missing reference definitions; this
narrow workload rejects them rather than silently assigning CP semantics.

Its fixed information-access declaration matches the existing cooperative APIs:
generation receives detached actor context and supplied formation; ranking
receives detached actor context, accepted proposals and declared parameters;
semantic model inputs contain only versioned numeric values. Opaque references
remain bindings. Checkpoints, private RNG authority, rejected-proposal diagnostics,
source/build/config commitments, targets and run/split receipts are operator-only.
This neither authenticates arbitrary callback code/weights nor establishes a
Python security sandbox or independent-future-chance planning. The constructor
adds no field or receipt to any player context, scorer argument or adapter view.
The existing adapter decision contract remains unchanged.

The immutable receipt returns detached JSON. Its closed loader reconstructs from
the same typed split/configurations/routes and compares all fields; altered
schema, semantics, information access, split contents or accounting fail.
Active controls in `test_runner_accounting.py` and
`test_deployment_experiment.py` retain empty partitions, failed zero-row runs,
duplicate occurrences, ordinarily accepted geometry-ranked deployment, observed
or missing CP labels and save/load/replay controls.

This completes the workload reference/access join for the selected Stage 1
contract audit, subject to final exact-head review and delivery gates. It does
not qualify Stage 2 workload admission, reachable mechanic coverage, useful
reference alternatives, component costs, full-game performance or learning.
See the maintained plan's bounded Stage 1 reconciliation for the endpoint.

## Frozen canonical deployment admission

`ai.canonical_deployment` supplies the first bounded Stage 2 admission slice.
`canonical_deployment_config()` reconstructs the unchanged
`canonical_setup_prebattle_smoke_config(game_id="canonical-deployment-v1")` and
requires its full configuration SHA-256 to equal
`adfdb1ee885d9de34ddbe6ef7fe1be64c728f86d3529dc2e82b7523132926409`.
This includes the roster, complete executable mission/layout geometry, rules,
source identities and fixed test private seed (`f0` repeated 32 times). A change
requires explicit fixture review/versioning; a friendly ID alone cannot admit it.
The seed is public test data, unsuitable for competitive games.

`reproduce_canonical_deployment()` uses the existing `BoundedPolicyRunner`, exact
route registrations, detached actor contexts and ordinary viewer submissions.
Its declared fixed recipe selects Assassination + Bring It Down for both players,
completes player A's reserve declarations with every unit deploying, and places
all four units/14 models. No player B reserve request is emitted in this recipe.
The policy seed is 7; the cooperative runner limit is 11 decisions/120 seconds.
This is an explicit recipe with no candidate search, alternate-policy recovery
or inferred legal action. The time limit is a progress guard, not a cost result.

| Accepted indices (zero based) | Required exact route | Observed count |
|---|---|---|
| 0 / 1 | `player-a` / `player-b`, `select_secondary_missions`, setup `select_secondary_missions`, finite | 1 each |
| 2 | `player-a`, `select_reserve_declaration`, setup `declare_battle_formations`, finite | 1 |
| 3 / 5, 7, 9 | `player-b` / `player-a`, `select_deployment_unit`, setup `deploy_armies`, finite | 1 / 3 |
| 4 / 6, 8, 10 | `player-b` / `player-a`, `submit_deployment_placement`, setup `deploy_armies`, proposal `deployment_placement` | 1 / 3 |

All seven distinct declared routes are observed; no required route is unobserved.
The exact actor/order/accepted-record count is checked, not inferred from registry
size. Model positions are inches in the configured world frame, z=0. For each
formation, model index `i` adds `(1.8*(i//3), 1.8*(i%3))` to its origin:
player B's five scouts `(3,3)`, player A's three Deep Strike models `(3,45)`,
five scouts `(3,51)`, and one vehicle `(7,57)`. Facing is 180 degrees for B and
0 degrees for A. Unit/model IDs come from the exact fixture and actor proposal.
Each formation passes normal deployment/coherency/occupancy/terrain validation.
The endpoint is the first pending setup `redeploy_units` request, before making
that choice. It is a truncated prefix, not completed setup, Command or a battle.

`CanonicalDeploymentAdmission.from_session(session)` first requires the frozen
configuration, reproduces the complete recipe, compares the exact checkpoint,
and verifies ordinary startup plus strict persistence/replay through
`VerifiedEpisodeOrigin`. Its immutable operator-only receipt retains the full
configuration and recipe, source/build/checkpoint identity, ordered accepted
records with actor observation hashes, required/observed/unobserved routes,
pending endpoint route, replay commitment, fixture exceptions and remaining
Stage 2 obligations. The closed loader rederives all evidence; changed fields,
ordinary alternate configurations and incomplete prefixes fail. It does not
mutate the supplied session. No receipt/private checkpoint is added to actor
views. The existing adapter contract already covers every finite/proposal choice;
this adds no player-facing route or wire payload.

Source and fixture limits are part of this admission:

- The synthetic `phase9a-canonical` catalog, setup-smoke REDEPLOY/SCOUTS overlay,
  and `allow_legacy_non_strict_rosters=True` remain explicit test exceptions.
  The 32mm infantry/Deep Strike bases and 120mm vehicle base are canonical test
  profiles. Model volumes use the existing legacy keyword-derived heights,
  not source-measured model geometry. Only one 300-point reserve value is
  configured; this is not a complete official points roster or faction admission.
- Mission/scoring ownership remains Event Companion v1.1 July, source
  `gw-11e-warhammer-event-companion-v1-1-2026-07`, reviewed import hash
  `4832f73e470caa4d0906fef06af3f05f53b00a68bbfdbb3d2c639eec6e323fb0`
  in `rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py`.
  The retained [July extraction](../data/source_audits/event_companion_2026_06/phase17n_event_companion_battlefields_pages_9_53_extraction.json)
  identifies `eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf`,
  SHA-256 `97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20`;
  that layout extraction is not fresh mission/scoring-wording validation.
- The actual 44x60 battlefield, Take and Hold versus Purge the Foe layout 3,
  uses the [current October layout owner](../data/source_audits/event_companion_2026_10/README.md),
  page 14 of official `eng_14-10_wh40k_event_companion-rdwnqprl4c-nj8oqogadv.pdf`,
  SHA-256 `187253a9b6ea377f5e44d1148454bd042b165b03bb5c45c51a5880762bf56dc2`.
  Its [runtime artifact](../src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/event_companion_layouts_2026_06/artifacts/event-companion-battlefields.json)
  has package hash `be19e97db9124271cae2dba2cdc8ef76992526b67c11505cf7c10c00435d36a7`.
  Retained module/mission names do not change that geometry provenance. The
  owner's physical component models, quantization and deployment templates remain
  project assumptions; official layout artwork does not certify model heights.
- Primary assignments are Immovable Object for A and Unstoppable Force for B.
  This prefix validates fixed-secondary selection, not scoring windows, victory
  points, terminal utility or a new training target. July mission/scoring clauses
  have not thereby been authenticated as October wording.

The receipt records redeploy/Scouts, reserve arrivals, Tactical draws,
attachments/transports and battle movement/combat/reactions/scoring as unsupported
**by this recipe**; it makes no claim that the engine lacks those mechanics.
The pending redeploy route is distinct from the seven accepted routes. Other
choices, orders, geometries, seeds and reachable states remain unexercised.
The separate coverage measurement below reports bounded candidate/reference
alternatives and their gaps. Separate operator component-cost measurements are described below. This admission neither creates a dataset nor changes
`DeploymentWorkloadContract` or training eligibility. It claims no exhaustive
reachability, full-game support, learning, tactical quality or cost certification.


## Canonical candidate and reference-alternative coverage

`ai.canonical_deployment_coverage.CanonicalDeploymentCoverage.measure(session=...)`
is a separate operator-only measurement for the exact admitted endpoint above.
It preserves the original admission receipt and its schema. Reconstruct the
endpoint with `reproduce_canonical_deployment()`, measure it, and serialize
`report.to_payload()`. The closed loader first derives aggregate counts from the
receipt rows and rejects internally inconsistent totals without engine work.
This pure preflight authenticates no row or claimed legality: every internally
consistent `from_payload(payload, session=session)` still repeats the complete
experiment and requires exact closed equality. The report's content hash
binds the nested admission/source/build identity, exact prefix/checkpoint and
actor-observation hashes, candidate payloads, validation results and denominators.
No caller-supplied policy, alternate fixture, mutable checkpoint or budget is
admitted by this version.

The canonical owner reconstructs all eleven before-choice states from ordinary
startup using the existing replay adapter and exact accepted records. It checks
each route/actor view against the original runner and the complete endpoint
against the reproduced checkpoint before returning prefixes. Each finite or
placement alternative is submitted through the ordinary viewer adapter on its
own fresh fork. Probes cannot change the canonical continuation, the supplied
endpoint, live requests or RNG. The seven finite occurrences and four placement
occurrences cover the same seven exact routes, four units and fourteen models;
they stop before redeploy. Acceptance means the engine accepts this single
choice, not that a branch's later continuation was played.

References and denominators are defined independently of the measured generator:

- Finite references are all current engine-enumerated options in each original
  actor request, retained separately from the generated finite set. Every option
  is actually submitted; its result is shared when the identical generated choice
  is evaluated. The total finite-attempt ceiling is 512, with an explicit error
  if the frozen inventory exceeds it, never a silently shortened denominator.
- Placement generation uses thirteen whole-formation offsets: zero, ±1 inch along
  X/Y, then ±2 inches along X/Y, followed by `(1,1), (-1,1), (1,-1), (-1,-1)`.
  Generator identity `actor-formation-xy-translations-v2` versions this expansion;
  the set wire schema stays `deployment-translation-set-v1`. Closed loading rejects
  predecessor generator identities. The original nine-candidate prefix remains exact.
  The separately fixed reference list is zero, ±1 and ±2 inches along X or Y,
  plus the deliberately invalid `(100,100)` offset. The same translation owner
  constructs both sets from the original actor-bound recipe formation, but the
  reference list is never selected from generated or accepted outputs.
- Each placement set is fully validated: thirteen generated and ten reference
  attempts per occurrence, accepted cap sixteen. Raw/duplicate counts, actual
  budgets and complete stop reasons remain in the nested receipts. No candidate
  is unvalidated. Identical candidates appearing in both lists are independently
  submitted on fresh forks.
- The legal-reference denominator contains only distinct engine-accepted
  reference candidates at that exact occurrence. The numerator contains those
  references also generated **and accepted**. Invalid reference probes and
  rejected generated candidates remain separate counts with engine diagnostics.
  Summation counts occurrences, including repeated routes; it is not a count of
  distinct routes, a fraction of continuous deployment space, or a win-rate label.
  Zero translation deliberately retains the canonical recipe as a positive
  control. "Useful" here means distinct feasible choices or placements only.

The frozen experiment currently yields:

| Decision occurrence / placement | Generated accepted / attempted | Legal references / probes | Covered legal references | Missing legal references |
|---|---:|---:|---:|---:|
| Seven finite occurrences | 18 / 18 | 18 / 18 | 18 / 18 | 0 |
| Index 4: player B five-model unit | 13 / 13 | 9 / 10 | 9 / 9 | 0 |
| Index 6: player A three-model unit | 12 / 13 | 8 / 10 | 8 / 8 | 0 |
| Index 8: player A five-model unit | 12 / 13 | 8 / 10 | 8 / 8 | 0 |
| Index 10: player A vehicle | 9 / 13 | 7 / 10 | 7 / 7 | 0 |
| Four placement occurrences combined | 46 / 52 | 32 / 40 | 32 / 32 | 0 |

Finite option counts in canonical order are 4, 4, 3, 1, 3, 2 and 1.
The 88.462% generated-placement validity yield (46/52) and 100% bounded legal
reference coverage (32/32) answer different questions. Eight rejected reference
probes remain outside 32; four of them also occur among generated rejections.
The two positive-Y vehicle diagonals add two further generated rejections. All eleven
original recipe choices remain generated and accepted. The unchanged reference
list was fixed before this expansion; it is never derived from the new defaults.

The predecessor five-offset default covered 19/32 legal references (59.375%),
with validity yield 19/20 (95%). All thirteen misses formed one demonstrated gap
class: cardinal translations at two inches. Adding this second ring addresses
the entire observed missing class with four additional proposals per occurrence.
That expansion addressed its then-demonstrated gap; the broader suite below
subsequently qualified four diagonal offsets. This is a bounded search
configuration expansion, not a gameplay legality fix or tactical optimization.

Each missing alternative moves every model and the unweighted model-origin
centroid exactly two inches in the listed direction. All preserve relative
formation, XYZ spans, height, facing, model ownership and proposal context.
Coordinates and spans below are model origins in world-frame inches, not physical
footprints; displayed decimal values round binary floating-point coordinates.

| Occurrence | Seed centroid XYZ | Seed XYZ span / facing | Previously missed engine-accepted directions | New rejection in the second ring |
|---|---|---|---|---|
| 4: B five-model unit | (3.72, 4.44, 0) | (1.8, 3.6, 0) / 180° | +X, −X, +Y, −Y: four alternatives | None |
| 6: A three-model unit | (3, 46.8, 0) | (0, 3.6, 0) / 0° | −X, +Y, −Y: three alternatives | +X intersects layout-3 terrain-area-01 component-01 long/short Solid arms (`terrain_endpoint_illegal`) |
| 8: A five-model unit | (3.72, 52.44, 0) | (1.8, 3.6, 0) / 0° | +X, −X, +Y: three alternatives | −Y overlaps A's already deployed third Deep Strike model (`model_overlap`) |
| 10: A vehicle | (7, 57, 0) | (0, 0, 0) / 0° | +X, −X, −Y: three alternatives | +Y crosses battlefield/deployment-zone edge (`battlefield_edge_crossed`, `deployment_zone_violation`) |

The vehicle's pre-existing +1 Y rejection has those same edge/zone codes. The
four `(100,100)` probes also produce edge/zone violations and remain explicit
invalid references. Terrain/model blockers and per-model violations remain in
the complete receipts. None of the forty reference attempts returns unsupported;
an unsupported status or engine error aborts measurement explicitly, never counts
as a legal alternative or ordinary rejection. Unsupported/unmeasured proposal
families remain outside this experiment's denominator.

These thirteen alternatives qualify as distinct feasible wider spatial choices
at their original prefixes. They do not demonstrate a screen, preservation,
follow-through, objective-control, line-of-sight or scoring advantage. The same
synthetic fixture supplies all four occurrences, two players, 32mm infantry and
one provisional 120mm vehicle; this is not representative sampling across
factions, layouts, unit sizes or alternate branch continuations. Rotations,
reshaping, other distances, deployment orders, seeds and continuous placement
space remain unmeasured. No tactical diversity, utility, ranking quality,
learning, redeploy, Scouts, battle or full-game qualification follows.

Focused controls preserve a nonrecipe +2 X placement through ordinary acceptance,
JSON restore and exact replay, reject incompatible/incomplete endpoint inputs,
reproduce the closed report and reject a fabricated reference denominator.
Reports and authoritative rejection/checkpoint evidence remain outside player
views and model inputs. The existing adapter decision contract covers these
unchanged submissions; no player-facing contract or gameplay semantics change.

## Canonical component-cost diagnostics

The standalone operator harness
`scripts/measure_canonical_deployment_costs.py` measures this exact report and its
closed loader without changing their algorithms or acceptance semantics. It runs
serial fresh interpreter processes, retaining each process's first iteration and
optional within-process repeats separately. Each iteration reconstructs the
endpoint, times full `measure`, converts the report through JSON, and times full
`from_payload`. The loader sample is already warmed by measurement and conversion;
it is never labeled an independently cold loader. Process launch-to-exit and
runtime import are separate costs; OS caches are uncontrolled.

An optional prepared component pass executes after the complete repetitions. It
times configuration/startup, admission, prefix reconstruction, finite/placement
generation, fresh-fork validation, persistence encoding/restore and exact replay.
It calls the current owners, including coverage's finite-probe helper, and checks
its sets/results against the authoritative report. Whole-method inclusive costs
and separately timed extra forks overlap semantically and must not be added to
reconstruct the headline full-report cost. No profiler or runtime monkeypatching
is used. The [procedure and evidence](performance/CANONICAL_DEPLOYMENT_COSTS.md)
define the boundaries, environment, ordered failures, budgets and uncertainty.

The authoritative coverage/admission schemas retain their historical
`pending_stage2_evidence` fields: external timing evidence does not rewrite those
deterministic receipts or grant broader admission. This report has no component
timers, creates no dataset and leaves training eligibility unchanged. Component
measurements apply only to this fixture on the recorded provisional host. Broader
useful references, tactical quality, later gameplay and full-game throughput
remain unqualified; Stage 2 remains open.

## Deployment-order and diagonal reference suite

`ai.deployment_reference_suite.DeploymentReferenceSuite.measure()` reconstructs
the entire fixed suite. `from_payload(payload)` first rejects declaration drift,
then rederives every case and requires exact complete equality. The immutable
receipt is operator-only: it neither enters actor observations/scorers nor grants
training admission. `reproduce_reference_case(case_id)` and
`measure_reference_case(case_id)` accept only the three declared IDs. Original
canonical admission/coverage schemas and their accepted recipe remain unchanged.

The current pre-measurement definition is `deployment-order-diagonal-reference-suite-v2`,
SHA-256 `7f8b9428acb03cfdce6b86396c520f487bc38369aacd90ce9d4d377dd9e8fa00`.
Version two changes the generated budget from nine to thirteen; cases, references,
origins and exclusions retain their version-one definitions. The historical
version-one definition, report and cost evidence remain unchanged.
Its complete recipes, reference coordinates, intended constraints, budgets and
exclusions are serialized in each receipt. Definition drift fails closed. This
pin preceded the first engine run; no measured acceptance selected the cases or
reference coordinates.

All cases use the exact [canonical configuration](#frozen-canonical-deployment-admission),
including its seed, synthetic roster, provisional model geometry and July
mission/October layout sources. Player B's five scouts always deploy first at
(3,3). Player A's fixed Deep Strike/scout/vehicle origins remain (3,45), (3,51)
and (7,57), with the same formation spacing, Z and facing as the canonical recipe.

| Case ID | Player A's ordered placements | Distinct prefix constraint |
|---|---|---|
| `deep-scout-vehicle` | Deep Strike, scouts, vehicle | Original Deep Strike models occupy the space before scouts are probed. |
| `vehicle-scout-deep` | Vehicle, scouts, Deep Strike | Vehicle is already present for scout probes; scouts are already present for Deep Strike probes. |
| `scout-deep-vehicle` | Scouts, Deep Strike, vehicle | Scouts are probed before either other A unit; they then constrain Deep Strike probes. |

Each case accepts eleven ordinary decisions and independently reconstructs all
eleven before-choice states by replay. Startup/save/load/replay admission binds
each case's complete accepted records and endpoint. This yields 33 decision
occurrences, 21 finite and 12 placement occurrences, with seven distinct routes.
Repeated cases/routes/geometries are counted per occurrence, not as independent
samples or unique reachable states. Candidate probes do not play subsequent
continuations.

Each placement independently references `(0,0), (2,0), (-2,0), (0,2), (0,-2),
(1,1), (-1,1), (1,-1), (-1,-1), (100,100)` inches relative to its recipe seed.
The four diagonal offsets translate every model by a Euclidean distance of
sqrt(2) inches while retaining formation, model identity, facing and height.
These now follow the generator's original nine cardinal/zero defaults.
All finite options, all thirteen generated placements and all ten reference probes
are submitted on separate ordinary engine forks, with acceptance cap sixteen
and no unvalidated tail. Finite generated/reference copies share the identical
submission result as in the original coverage owner. Only engine-accepted
references enter the denominator; covered means also generated and accepted
at that exact occurrence. Invalid probes retain exact engine diagnostics.

The [complete receipt](performance/deployment-reference-suite-v2/suite-report.json)
records these observed results; the definition was not changed after observation:

| Case | Finite accepted / attempts | Generated placements accepted / attempts | Covered / legal placement references | Invalid reference probes | Feasible misses |
|---|---:|---:|---:|---:|---:|
| `deep-scout-vehicle` | 18 / 18 | 46 / 52 | 31 / 31 | 9 | 0 |
| `vehicle-scout-deep` | 18 / 18 | 46 / 52 | 31 / 31 | 9 | 0 |
| `scout-deep-vehicle` | 18 / 18 | 46 / 52 | 31 / 31 | 9 | 0 |
| Occurrence-weighted total | 54 / 54 | 138 / 156 | 93 / 93 | 27 | 0 |

The placement reference denominator is 93 accepted probes out of 120, excluding
27 rejected probes. The default covers 93/93 (100%); generated validity is
138/156 (88.46%). The 42 formerly missing accepted diagonals are now covered: four for each
B scout, A scout and Deep Strike occurrence, and the two negative-Y diagonals for
each vehicle occurrence. The six positive-Y vehicle diagonals are rejected,
remain outside the denominator, and are not feasible misses. Finite coverage is
54/54. All 330 finite/generated/reference validation submissions complete; none
is unsupported or unvalidated.

Identical per-case totals conceal an actual occupancy-dependent swap:

| Unit and reference offset | Deep Strike before scouts | Scouts before Deep Strike |
|---|---|---|
| A scouts `(0,-2)` | Rejected: `model_overlap` with already placed Deep Strike models (index 8). | Accepted (index 8 in vehicle-first; index 6 in scouts-first). |
| A Deep Strike `(0,2)` | Accepted (index 6). | Rejected: `model_overlap` with already placed scouts (index 10 in vehicle-first; index 8 in scouts-first). |

All three cases also reject Deep Strike `(2,0)` against terrain
(`terrain_endpoint_illegal`). Every vehicle rejects `(0,2)`, `(1,1)` and
`(-1,1)` with both `battlefield_edge_crossed` and
`deployment_zone_violation`; the twelve far controls have those same codes.
These account for all 27 reference rejections. Vehicle-first changes prefix
occupancy but introduces no additional rejection within these particular
references. The suite therefore demonstrates one infantry occupancy swap,
diagonal feasibility and the retained terrain/edge constraints, rather than
three independent tactical situations. A post-scout Deep Strike diagonal also
has an ordinary-submit, JSON restore, exact replay and both-viewer regression.

The four demonstrated diagonal offsets now have complete finite feasibility
coverage in this suite. No claimed screen, preservation, follow-through, range,
visibility, objective or scoring benefit follows from a feasible diagonal.
Three of six A-unit orders are selected; the B-first side/seed, layout, formation
origins and roster are fixed. Rotations, reshaping, other distances, other
configurations/layouts/rosters/seeds/opponent responses and continuous placement
space remain excluded. Redeploy, Scouts, reserve arrival, attachments,
transports, battle and scoring remain unexercised by these recipes. Tactical
utility, ranking quality, learning, full games and representative coverage remain
unqualified, so Stage 2 stays open.

The existing adapter contract covers every unchanged finite/proposal submission.
The suite adds no player-facing route, wire payload, rule mutation or alternate
legality path. The [cost procedure](performance/CANONICAL_DEPLOYMENT_COSTS.md)
records the separate serial observation, its exact source/runtime identities and
limitations.

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

## Reachable preservation prefix admission

`ai.preserve_scenario` provides `reproduce_preserve_scenario()` and the closed
operator-only `PreserveScenarioAdmission.from_session(...)` /
`from_payload(..., session=...)` receipt. This is one prerequisite admission
slice for the proposed screen/preserve experiment; useful-reference status is
explicitly `scoped_gap`.

The independently pinned `canonical-preserve-prefix-v1` definition binds the
unchanged `canonical-deployment-v1` configuration hash
`adfdb1ee885d9de34ddbe6ef7fe1be64c728f86d3529dc2e82b7523132926409`, its eleven
deployment choices, and six fixed ordinary viewer submissions. A/B each choose
`complete_redeploys`, then A/B each choose `complete_prebattle_actions`; A selects
`army-alpha:scout-redeploy-unit` and `remain_stationary`. The seventeen-record
checkpoint stops at round-one player-A Movement's next `select_movement_unit`.
The design-role E is the separate `army-alpha:deep-strike-unit`; the opponent
candidate is `army-beta:scout-redeploy-unit`. Their tactical roles remain unproved.

Admission requires exact fresh reproduction, strict startup/save/load replay,
unchanged battlefield placement through the continuation and a consumed S
activation. The receipt retains the full configuration, current origin/build/source
identity, ordered accepted records and actor observation hashes, thirteen required
and observed prefix routes, pending endpoint, boundary/activation events, and
replay commitment. Each continuation occurrence records the complete
`FiniteCandidateSet` and selected ID. S's action options are `advance`,
`normal_move`, and `remain_stationary`; only the last is executed here. Selecting
a movement category is not evidence of an accepted path or beneficial outcome.

Required prefix mechanics are reconciled separately from the proposed useful
reference's unobserved requirements: witnessed screen/exposure movement, enemy
reachability and attack resolution, E follow-through, later scoring/attack benefit,
and matched continuations with a local target and declared horizon. The definition
retains minimum unit-specific pending movement and opponent Shooting routes plus
the later scoring-boundary obligation; this is not an exhaustive battle plan.
No positive benefit, threat, attack or later scoring result is invented. The
scoped gap means missing experiment evidence, not that the engine lacks those
mechanics. `reference_target` is null and `eligible_for_learning` is false.

The inherited synthetic Core roster, legacy model volumes, provisional geometry,
July mission/scoring and October layout identities, partial points and public
test seed remain disclosed. Redeploy and Scouts decline choices are exercised;
their placement/path mechanics are not. The ordinary first Command boundary
does not supply a delayed tactical outcome. All admission metadata stays outside
actor/scorer views. Existing adapter choices and submission contracts are reused
without modification; no new player choice, observation field or training schema
is introduced. Incomplete prefixes, changed configurations, extra ordinary
decisions and changed closed receipts fail admission. This does not certify
continuous placement coverage, tactical usefulness, full games, performance,
learning or Stage 2 completion.

## Witnessed Normal Move prefix admission

`ai.normal_move_scenario` supplies `reproduce_normal_move_scenario()` and the
closed operator-only `NormalMoveScenarioAdmission.from_session(...)` /
`from_payload(..., session=...)` receipt. Its `canonical-witnessed-normal-move-v1`
definition hash is
`12c50a37c861dbf138e8e89e90fbdd1931283d31ccff3442872582846eaa7c81`.
It retains the canonical configuration hash above and binds the original
preservation definition hash. Both execute the same first fifteen ordinary
choices, ending before S selection; the receipt commits to that full checkpoint,
and regression controls compare its persistence payload and ordered records
with an ordinary reconstruction of preservation's prefix.

The alternative selects `army-alpha:scout-redeploy-unit`, selects `normal_move`,
and submits one typed `MovementProposalPayload` with an actual `PathWitness`.
The fixed recipe reads all five S model poses from player A's view, preserves
height and facing, and supplies straight-line paths one inch in negative X in
observed model order. It submits through `submit_viewer_parameterized_payload`;
the existing engine validates the complete paths, collision/coherency and movement
constraints before mutation. There is no endpoint-only acceptance or direct
placement edit. The old preservation definition and seventeen-record receipt
retain their exact meaning.

The authoritative path is viewer submission / `ParameterizedSubmission`,
`GameLifecycle.submit_decision`, movement proposal preflight, the shared
`movement_resolution_flow._apply_movement_proposal_decision` and
`movement_rules_units.resolve_rules_unit_normal_move`, then engine placement
replacement and `movement_activation_completed`. The existing
[Movement contract](ADAPTER_DECISION_CONTRACT.md) already specifies the finite
`normal_move` selection, movement mode and follow-up `submit_movement_proposal`
with a `PathWitness`. No decision type, proposal family, wire shape or visibility
behavior changes in this slice.

Admission compares the entire eighteen-record endpoint with fresh ordinary
reproduction and verifies startup, JSON persistence and exact replay through
`VerifiedEpisodeOrigin`. It retains fourteen required/observed routes, complete
accepted records and observation hashes, finite choice inventories, the submitted
witness, Command/Movement boundary events, consumed S activation and the next
Movement unit request with E still available. The pinned definition inventories
required prefix mechanics separately from unobserved tactical requirements. S's
Normal Move route is observed; E's movement and the opponent's Shooting route
remain minimum continuation obligations, not a complete battle plan.

A legal path does not establish screening, exposure, tactical usefulness, an
opponent threat, E follow-through or any later scoring/attack outcome. All five
original tactical obligations remain unobserved, including the tactical meaning
of screen/exposure movement. `useful_reference_status` is `scoped_gap`,
`reference_target` is null and `eligible_for_learning` is false. Missing evidence
is not engine-unsupported. The inherited synthetic roster, legacy/provisional
geometry, July mission/scoring, October layout, partial points and public seed
exceptions remain. Candidate/reference continuation coverage, scenario costs,
full-game qualification and Stage 2 completion remain open. Metadata stays outside
actor/scorer inputs. Controls retain preservation, genuine invalid-distance
rejection and replay, strict closed receipt rejection, and incomplete/extra-prefix
exclusion.

## Paired followthrough and opposing shot probe

`ai.followthrough_scenario` supplies `reproduce_followthrough_pair()` and the
closed, operator-only `FollowthroughPairAdmission.from_sessions(stationary, moved)`
and `from_payload(payload, stationary, moved)` receipt. The pinned
`canonical-paired-followthrough-v1` definition binds the unchanged canonical
configuration and both original scenario definition hashes, the exact five-choice
continuation, the opposing endpoint route and one independently submitted shot
probe. Neither original admission is extended or relabelled.

Each branch selects E, selects Normal Move and submits straight-line paths moving
all three observed model poses one inch in negative X with unchanged height and
facing. It then selects the remaining vehicle and Remains Stationary. The endpoint
has 22 stationary-branch records or 23 movement-branch records. The full first
fifteen accepted records are equal, and ordinary-startup verification plus exact
replay binds their common history. The receipt includes complete accepted
records/traces and observation commitments, required/observed accepted routes,
actual movement activation events, endpoint origins and replay-artifact hashes.

Both endpoints are the **opponent's** `submit_stratagem_target_proposal` request
for Fire Overwatch at the end of A's Movement phase. The active player remains A;
the requesting actor is B. The fixed diagnostic submits B's nominated unit as
the friendly shooter on a separate ordinary fork. Engine prevalidation rejects
it with `fire_overwatch_no_legal_shooting_declaration`. The receipt binds the
actual request and submitted payload, typed status/message/reason, before/after
checkpoint hashes and zero record/event deltas. The rejected attempt stays
outside each accepted trace. No actor receives this operator receipt or a
counterfactual outcome. Declining the offered reaction is a distinct accepted
proposal that can continue to A's Shooting phase; it is not attack evidence.

The authoritative owners remain the existing finite Movement choices,
`MovementProposalPayload`/`PathWitness` validation and movement activation
mutation, end-Movement reaction routing, `invalid_stratagem_target_proposal_status`
and `_fire_overwatch_target_binding_error`, and shared session persistence/replay.
The existing [adapter contract](ADAPTER_DECISION_CONTRACT.md) already specifies
Normal Move and `stratagem_target_binding`, including the `proposal` envelope and
decline payload. No decision family, wire shape, viewer policy, game rule,
generator, ranker or training schema changes.

This establishes paired legal E movement and a negative shot feasibility result
for one exact shooter/window. It establishes neither tactical exploitation nor
global threat impossibility, and does not diagnose an engine-unsupported path.
The same synthetic Core roster, legacy non-strict flag, provisional model volumes,
July mission/scoring plus October layout, partial points and public test seed
remain disclosed. Actual enemy attack resolution, E's subsequent benefit,
matched later outcomes/horizon, screening, timing/cooperation controls, useful
candidate coverage and scenario costs remain open. The receipt returns
`useful_reference_status: scoped_gap`, `reference_target: null` and
`eligible_for_learning: false`; it cannot certify Stage 2 completion, full games
or throughput.


## Opposing shooter qualification

`ai.opposing_shooter_scenario.OpposingShooterQualification.from_sessions(stationary,
moved)` adds a separate operator-only, immutable report. It requires the exact
22/23-record endpoints reproduced by `reproduce_followthrough_pair()` under the
current runtime and canonical configuration. The original followthrough definition
and admission retain their historical scope and bytes. Serialized report exports
are evidence for inspection; this report has no serialized-evidence importer or
training consumer. It cannot admit a caller-edited export as a qualified result.

At both endpoints, the shared Fire Overwatch shooter check returns no ineligibility
reason for B's five living infantry. Every model carries `core-bolt-rifle`, whose
complete equipped profile is retained: 24-inch range, two attacks, BS 3+, Strength
4, AP -1, Damage 1, Assault and Rapid Fire 1. All fifteen model/target candidates
are rejected as out of range. Separate living-model LOS queries use the actual
terrain features and terrain areas: E is visible, while S and the vehicle are not.
Range-short-circuited target candidates supply no visibility finding. This explains
the original negative shot without claiming shooter ineligibility, universal
occlusion, unsupported shooting or global threat impossibility.

The report independently reproduces the stationary branch and continues it through
ordinary viewer decisions. A skips Shooting and Remains Stationary in rounds two
and three; both players decline offered movement reaction windows. B's complete
Normal Move witnesses translate all models by (-2,+5) inches in round one and
(0,+6) in round two. In round three, models in the x=1 column move six inches in
positive Y and those in x=2.8 move three inches, with paths ordered front to back
(descending initial Y, stable ties). Height and facing stay unchanged. The path
avoids the ruin and model-overlap rejections encountered by simpler proposals;
those rejections do not establish unreachability or an engine defect.

B skips Shooting in rounds one and two, selects Normal shooting in round three,
and declares only model `:003`'s equipped rifle against E using the observed weapon
identity and current proposal context. The fixed resolution declines Command
Re-roll opportunities and allocates to the lowest offered model ID when required.
The horizon ends after this attack sequence completes, at the next ordinary
pending decision. Complete accepted continuation records, observation commitments,
actual attack events and a replay artifact bind the witness. Strict ordinary-startup
persistence/replay verification covers the attack branch and the unchanged moved
endpoint. Both caller-owned checkpoints remain byte-equivalent and the operator
report stays outside viewer/policy inputs.

The existing [adapter contract](ADAPTER_DECISION_CONTRACT.md) covers the finite
movement/shooting choices, witnessed movement, stratagem decline, shooting
declaration and attack-resolution choices. No decision family, wire shape, visibility
policy or engine rule changes. The owning queries remain `fire_overwatch`,
`shooting_selection_range`, `shooting_targets` and the shared shooting/attack
lifecycle; the new module only composes their existing public behavior.

This is a single cooperative attack-feasibility witness on the stationary branch,
not a matched response or evidence that either initial S choice is better. Screening,
exposure, E's benefit, matched later outcomes, timing/cooperation controls, useful
candidate coverage and scenario costs remain open. The synthetic Core roster,
non-strict roster flag, provisional model geometry, July mission/October layout,
partial points and public test-seed exceptions remain. `useful_reference_status`
is `scoped_gap`, `reference_target` is null and `eligible_for_learning` is false.
Stage 2, full-game qualification and throughput certification remain incomplete.

## Matched opposing attack comparison

`ai.matched_attack_scenario.MatchedAttackComparison.from_sessions(stationary,
moved)` supplies a separate immutable operator report from the exact 22/23-record
followthrough endpoints. It rejects wrong configurations, unreached or advanced
prefixes and same-count checkpoint drift against fresh ordinary reproduction.
It extends the reproduced pair, preserving both caller-owned sessions. The
historical `FollowthroughPairAdmission` and `OpposingShooterQualification`, their
definitions and tests retain their original scope. The new report supports JSON
export and a content hash, with no serialized-evidence importer or training
consumer; edited exports cannot admit evidence.

Both branches use the unchanged `_approach` and `_finish_attack` helpers from
the opposing shooter module. B performs the same three witnessed approaches in
rounds one through three, skips Shooting in rounds one and two, then declares
model `:003`'s rifle against E in round-three Normal shooting. A skips its three
Shooting phases and chooses Remain Stationary for all three units in rounds two
and three. Both players decline all six offered movement reaction windows; B
declines four hit/wound Command Re-Rolls, A declines its armour-save Command
Re-Roll and allocates to E model `:001`. The report requires identical actual
route/option sequences, movement witnesses and weapon/target/round declarations,
excluding branch-specific proposal linkage from that semantic comparison while
retaining complete accepted records and observation hashes in each trace.

The initial, before-attack and final round/active-player/pending-route boundaries
must match across branches. Both branches stop at round-four player-A Movement's
`select_movement_unit`, after exactly one completed attack sequence each. They
contain 65 and 66 accepted records respectively, including the two engine-generated
target/group selections. `VerifiedEpisodeOrigin` independently verifies ordinary
startup and strict persistence replay for each complete prefix. Each branch
exports its source/build-bound origin, full continuation trace, actual attack
events, replay artifact/hash and E model identities, health, survival and poses
at the initial, before-attack and final checkpoints. Poses are null only for
models absent from the battlefield placement inventory.

The fixed-seed result is equal: all three E models remain alive at two wounds
each, six total, with unchanged and identical E poses. Neither branch loses
wounds. The computed moved-minus-stationary wound and living-model differences
are zero. This is one bounded cooperative comparison; it does not show that
either initial S choice is better or that S screened/exposed E. Shared controls
record the recipe's timing and cooperation; adversarial responses and alternate
timings remain unmeasured. Useful candidate coverage and scenario costs remain
open, along with the inherited synthetic roster, geometry, mission/layout,
partial points and public seed limitations. The report retains `scoped_gap`, a
null reference target and no learning eligibility. Stage 2, full-game and
throughput qualification remain incomplete.

All choices use the existing adapter contract and shared engine movement,
shooting, attack, persistence and replay owners. This adds no engine rule,
player-facing route, proposal family, wire contract, policy or learner. Report
metadata stays outside actor views and scorer inputs.

## Bounded E attack operator evidence

The bounded follow-through experiment starts from fresh ordinary reproduction of
the matched comparison's exact 65/66-record endpoints. Supplied checkpoints are
compared in full with that reproduction before four independent continuations:
follow-through and omission for each historical S branch. Caller-owned endpoints
remain unchanged. This is retained operator evidence; no packaged report factory,
serialized-evidence admission, reference target or learning consumer is added.

The continuation, local outcomes and round-four player-B Movement horizon are
declared before the first E attack. Each arm uses the same witnessed six-inch
negative-Y E movement, S/vehicle stationary choices and declined B reaction. Only
the follow-through arm declares E model `:001`'s equipped drop carbine against B;
the omission arm completes Shooting without attacking. Optional Command Re-Rolls
are declined and damage allocation uses the first living engine-offered option.
The legal candidate, in-range model IDs, visible model IDs and actual LOS witness
are retained from A's viewer-scoped shooting proposal. Accepted requests/results,
full movement paths, observations, events and checkpoint commitments remain in
the report. Operator comparisons are excluded from player views and scorer inputs.

Each complete prefix must start from the unchanged canonical configuration and
pass strict persistence restoration and exact replay. Every final arm exports
its source/build-bound origin and replay artifact/hash. A failed or unplanned
continuation retains its attempted choice, actual accepted records/events,
checkpoint and diagnostic as `scoped_gap`; it supplies no completed comparison.
Successful comparisons retain wound losses and zero or negative differences.
No seed search, favorable-result replacement or direct state alteration is used
to construct the experiment. Manually drifted endpoint tests are separate
trust-boundary controls and are never admitted as ordinary play.

The reproduced follow-through prefixes contain 85 stationary-S and 87 moved-S
records; their omission controls contain 74 and 75. Each follow-through adds one
completed attack and each omission adds none. At the common horizon E has three
models/six wounds in every arm. B has five models/nine wounds after stationary-S
follow-through, and five models/ten wounds in the moved-S follow-through and both
omission arms. A's VP remains zero and B's rises from three to seven in all four
arms; the local VP difference is zero. E's three witnessed displacements are
identical across the arms and B does not move. The initial RNG-state hashes differ
between historical S branches. This single configured seed therefore does not
establish a shared subsequent chance schedule or attribute one-versus-zero damage
to S. These are retained local observations, with no screening-benefit claim.

The earlier stationary-E probe is retained separately: selecting E and Normal
shooting reaches no legal declaration and returns to A's Shooting unit selection.
It does not resolve an attack or establish general unreachability. Historical
admissions, runtime identity, exact test inventory and CI calibration retain their
original meanings. The synthetic roster, provisional geometry, mixed mission/layout,
partial points, public fixed seed and cooperative opponent remain limitations.
Screening/exposure, adversarial alternatives, useful candidate coverage, scenario
costs, held-out evidence, Stage 2 completion and learning remain open.

## Edge-column path-access operator evidence

`stage2-edge-column-access-v4` is separate operator evidence under the unchanged
canonical configuration hash
`adfdb1ee885d9de34ddbe6ef7fe1be64c728f86d3529dc2e82b7523132926409`.
Its ordinary deployment proposals place B and S in five-model single columns at
X=1, Y=3+1.8i and Y=45+1.8i inches respectively, i=0 through 4; E and the vehicle
keep their canonical placements. Both arms share the resulting fifteen-record
setup/prebattle prefix. No historical receipt is relabelled, imported as this
geometry or extended by this experiment.

Before any access measurement, the final declaration pins S's three six-inch
negative-Y Normal Moves versus three Remain Stationary choices, the same two
six-inch positive-Y B approaches, stationary E/vehicle, skipped Shooting and
explicit Charge/reaction declines. It pins independent six-inch and two-inch
positive-Y B probes and a one-inch matched main response. Its declaration-byte
SHA-256 is `784db3767e55766ddb1c0c280f8cdf27d91f508711b4cba1ab116e069ab36aec`.
Every movement uses observed model poses, unchanged Z/facing and a complete
straight-line witness in front-to-back execution order. Probes fork before B's
unit/action selection and leave each original main checkpoint unchanged. Their
records, rejected attempts and retry requests remain in their own artifacts;
main and probe traces are separate histories.

Retained source ledgers `tests/rules/section03/coverage.json` and
`tests/rules/section09/coverage.json` ground sequential movement (03.01), the
two-inch horizontal/five-inch vertical Engagement Range (03.04), and Normal Move
start/end eligibility and distance (09.05). Their maintained-mirror provenance
and lack of fresh official-App certification remain explicit. The shared engine
path validator owns legality. Its first transit diagnostic is reported as such;
endpoint engagement/overlap is assessed separately against the retained source.

The measured finite access contrast is:

| B's identical submitted path | Screen arm | Preservation arm |
|---|---|---|
| Six inches in positive Y | Rejected: `enemy_engagement_range_transit_forbidden` | Accepted |
| Two inches in positive Y | Rejected: `enemy_engagement_range_end_forbidden` | Accepted |
| One-inch matched main response | Accepted, 58 records | Accepted, 52 records |

S ends at Y=27 through 34.2 inches in the screen arm and remains at Y=45 through
52.2 in preservation. B starts these probes at Y=15 through 22.2 in both arms.
The six-inch endpoint overlaps/engages S; the two-inch endpoint's computed
1.540157-inch base-edge gap is within the retained two-inch Engagement Range.
The one-inch matched response leaves a 2.540157-inch gap and B at Y=16 through
23.2 in both arms. These are fixed model-footprint observations, not exhaustive
path searches.

All six full histories retain ordinary-startup, strict JSON persistence, exact
replay and both-viewer round-trip checks. Rejected histories retain the invalid
record and fresh pending proposal; they are not accepted movement histories.
The main horizons are the same round-three player-B end-of-Movement request for
player A's reaction, before A chooses. B, E and vehicle poses match across the
main arms. No model or wound is lost: S/B retain five models/ten wounds each,
E three/six and the vehicle one/twelve. Both VP ledgers remain zero. Complete
records, witnesses, diagnostics, checkpoints, replay artifacts and natural RNG
hashes remain operator evidence. The RNG hashes differ across arms; no overwrite,
matched future-chance schedule or stochastic-benefit attribution is claimed.

The original rear-first B attempt remains an `end_on_model_overlap` rejection
with a verified 27-record prefix. Later incomplete harness attempts retain newly
reachable Charge and Heroic Intervention requests before the access probes.
Source review revised the matched distance from two inches to one before those
probes; both distances remain measured. The viewer-ID assertion correction also
preceded probing and changed no declared action. No geometry/seed search,
authoritative state patch or RNG replacement occurred. This diagnostic harness
is outside packaged runtime/admission APIs and adds no decision family, wire
payload, policy, target calculator or training consumer. Existing finite,
movement, reaction, viewer and replay contracts already cover its submissions.

The contrast does not certify a globally blocked path, best response, useful
screen, sacrifice value, E benefit, full game, throughput or learning. Wider charge/intervention
continuations, detours, timing, geometry and opponents remain open; the bounded
extension below measures only its declared paths and declaration eligibility. The
inherited synthetic roster, provisional geometry, mixed mission/layout, partial
points and public fixed seed remain limitations. `useful_reference_status` stays
`scoped_gap`, `reference_target` is null and `eligible_for_learning` is false.
Historical controls retain their original meanings and Stage 2 remains incomplete.

## Bounded opposing-response operator evidence

`stage2-bounded-screen-responses-v1` extends the edge-column access question with five
predeclared independent B paths per position. The original canonical configuration and fixed
public seed, fifteen-record common setup, three S moves versus preservation and two common B
approaches remain unchanged. The six-, two-and one-inch forward witnesses remain explicit
controls. The added detour has four inches positive X followed by two positive Y; the added
approach has 1.4 inches positive Y. Every leg uses the existing Normal Move proposal and full
`PathWitness`, all five observed models in descending initial Y, unchanged height/facing and an
inclusive native-M distance check. Declaration-byte SHA-256:
`6ed8aca07220e509948c5d0953d2d9cd06fa9689cbec2ece22ed5c3097ffb16c`.

The six-/two-inch controls retain screen transit/endpoint Engagement Range rejections and
preservation acceptances. The one-inch control, detour and approach are accepted in both
positions. The detour's screen gap to S is 3.622780 inches; the approach's is 2.140157. They
remain unengaged under the retained two-inch threshold. The detour advances two inches in Y at
X=5; it is not a complete passage beyond S. Every accepted paired response has identical B
witness and endpoint poses in screen/preservation.

The one-inch, detour and approach continuations decline A's movement reaction, skip B Shooting
and retain charge target-query diagnostics together with the actual pending viewer request. In
the screen position S is within twelve-inch declaration range and B is offered as a charging
unit; E/vehicle are out of range. In preservation all three targets are out of range and B is
not offered a charge. The query uses the lifecycle's loaded charge-target restriction registry,
and the ordinary request confirms full declaration eligibility. No Charge roll or charge target
selection occurs; eligibility does not establish a legal charge endpoint, a successful
engagement or a Fight. Offered Charge and Heroic Intervention choices are explicitly declined,
reaching the common round-four A Movement unit-selection horizon at 62/54 records.

At that horizon B receives three VP after the detour in both positions for the same new-objective turn-end Primary rule; A remains at zero. The one-inch control and 1.4-inch approach
leave both ledgers at zero in both positions. The paired screen-minus-preservation VP difference
is zero for all three responses. No wounds/models are lost, and all ten histories retain full
records, observed views, movement witnesses, rejection/retry diagnostics, checkpoint/replay
artifacts and unmodified natural RNG commitments. Both viewers' projections and event streams
are equal after strict persistence restoration. Ordinary-startup verification and exact
`ReplayRunner` reproduction apply to each complete history; each original response origin
remains unchanged. The positions' RNG hashes differ. No independent future-chance service or
matched stochastic benefit is inferred.

The first operator attempt stopped on a nonexistent registry attribute after the one-inch
movement and reaction decline. Its checkpoint/progress and original harness remain retained.
Reading the existing loaded registry corrects the harness without changing
engine/source/configuration, declaration, paths or RNG; the completed invalid-control evidence
is reused. Operator evidence stays outside actor/scorer inputs. No runtime/admission factory,
player decision family, wire payload, policy, target calculator or learning consumer is added.
Existing finite, movement, charge, reaction, viewer and replay adapter contracts cover all
choices.

Source obligations are retained 03.01, 03.04, 09.05 and 11.02 with their maintained mirror
provenance limits; no fresh official-App certification is asserted. Charge movement (11.04),
attacks, alternative timings/cooperation, wider routes, held-out opponents/geometry, useful E
follow-through and scenario/full-game costs remain unqualified. The synthetic roster,
provisional geometry, mixed mission/layout, partial points and public-seed caveats persist.
These finite observations establish neither exhaustive denial nor a best response, useful
sacrifice or tactical superiority. `useful_reference_status` remains `scoped_gap`,
`reference_target` is null and `eligible_for_learning` is false; Stage 2 is open.

## Natural charge and bounded witness operator evidence

`stage2-bounded-screen-charge-v1` retains the canonical configuration/seed and
the ordinary edge-column 1.4-inch approach. Its declaration-byte SHA-256 is
`61bdb6e681cf0a94e248c3ffd78865a8205ebc10c18dadf5e9bccb7b5848a5dc`. Screen's 60-record Charge checkpoint is forked before choosing
B versus declining. Preservation supplies only the actual no-charge eligibility
control. Both forks share the screen checkpoint and its natural RNG authority;
preservation's different history is not given an invented matching RNG state.

The existing authority performs charging-unit selection, a physical 2D6 roll,
the offered Command Re-roll decline, finite selection of S alone, then the
parameterized Charge Move request. Natural values 6 and 3 produce a nine-inch
maximum, with no reroll or modifier. S's observed base-edge gap is 2.140157
inches. The 63-record selected-target checkpoint retains that realized roll and
remains pending; target eligibility and a sufficient roll do not certify a path.

The fixed initial witness moves all five B models 1.640157 inches positive Y
with complete paths, unchanged height/facing and descending initial Y. The
declared procedure allows at most six native pure evaluations, changing only
the first physical-order model path for which native preferred-distance or
engagement alternative evidence is available. Evaluation one is invalid with
`charge_reachability_unresolved`; four model preferred-distance queries remain
unresolved. This result never authorizes treating an unproved goal as impossible.

Evaluation two is an operator ordering failure: composition used sorted
`model_ids()` rather than the retained physical `model_paths` order. Its
endpoint-overlap diagnostics and the subsequent optional no-move history are
kept separately. They do not qualify the declared front-to-back procedure.
The corrected fork reuses evaluation one, counts the faulty second call within
the same six-call ceiling and resumes the same saved roll/target checkpoint.
Evaluation three retains physical order but is interrupted at the original
experiment allowance before returning. No corrected movement submission occurs.
Available query/progress, the saved checkpoint and all earlier results remain
diagnostics. The cross-process deadline uses a wall-time reconstruction after
WSL's uptime reset, with explicit polling/timestamp uncertainty; it is not the
exact monotonic covered-suite gate or a component/full-game speed measurement.

The pending 63-record charge, 62-record direct decline and 54-record preservation
control each retain ordinary-startup, strict JSON persistence, exact
`ReplayRunner` reproduction and both players' projection/event-stream equality.
Both viewer streams exclude the private seed. The controls end at round-four A
Movement; the corrected charge remains pending in round-three B Charge. No
comparison silently replaces that missing common horizon. Current engagement is
empty, all original models/wounds remain and no Charge Move, displacement,
Fights First or Fight is qualified. No geometry/seed search, authoritative state
patch, future-chance overwrite or favorable-outcome replacement occurs.

Prebattle option/reaction handling and a preservation-horizon overshoot also
remain operator diagnostics. The retained overshoot is not the control: its
54-record boundary is reconstructed through ordinary replay and independently
verified. Existing finite, reaction, charge, movement, viewer and replay adapter
contracts cover all actual submissions; this adds no runtime policy, decision
family, admission factory, target calculator or learning consumer.

The missing prerequisite is a complete legal witnessed Charge Move satisfying
the retained per-model endpoint obligations. Neither the unresolved first query,
the bad ordering nor the incomplete corrected query proves no such move exists.
Retained 03.01/03.04/09.05/11.02/11.04 ledgers keep their provenance limits and no
fresh official-App certification is asserted. The inherited roster, geometry,
mission/layout, points and public-seed exceptions remain. Best response,
successful engagement, sacrifice/E benefit, matched tactical outcome, throughput,
Stage 2 completion and learning stay open; useful-reference status is
`scoped_gap`, `reference_target` is null and `eligible_for_learning` is false.

## Charge reachability operator profiling boundary

The [maintained charge diagnosis](AI_IMPLEMENTATION_PLAN.md#charge-reachability-diagnosis-and-next-optimization-boundary)
separates checkpoint restore, ordinary replay, the corrected witness evaluation
and each searched mandatory endpoint query. The retained local operator helper
reconstructs #668's exact descending-Y witness from evaluation one's native
alternative and compares it with the saved corrected progress before resolving.
It does not generate another candidate, alter geometry/seed, submit a movement,
change a gate or expose profiling data to an actor/scorer. Existing contracts
cover restore/replay and the pure resolver; no decision family or wire change is
introduced. Completed earlier candidates and original censored evidence persist.

One in-process profile with a fresh 1,800-second monotonic supervisor is stopped
by the operator at 544.147 seconds after identifying the hot owner. It is neither
a timeout nor a completed witness. Model 001's preferred query returns unresolved
in 54.454 seconds and its engagement query reachable in 153.476 seconds; model
002's preferred query is censored after at least 260.511 observed seconds.
Unobserved remaining obligations stay unqualified. The input checkpoint restores
exactly and its ordinary replay reproduces 63 decisions/641 events. No final
in-memory checkpoint equality is claimed after interruption.

Increasing counters show combinatorial full-path validation, dominated by terrain
legality and its terrain-volume/sample checks, with distinct complete-query keys
and no observed full-query cache hits. The focused follow-up assesses immutable
preparation/conservative reuse in the shared reachability/pathing owners with
matched semantics and work evidence. This profile establishes no optimization,
successful charge, impossibility, tactical label or game throughput. Timing stays
operator-only; Stage 2 remains open, `useful_reference_status` is `scoped_gap`,
`reference_target` is null and `eligible_for_learning` is false.

## Complete corrected charge-witness operator boundary

The [complete optimized-main evaluation](AI_IMPLEMENTATION_PLAN.md#complete-corrected-charge-witness-evaluation-on-optimized-main)
restores the identical 63-record checkpoint and reproduces 63 decisions/641
events through separate ordinary replay. The corrected physical 005→001 witness,
geometry, seed, search budgets and endpoint obligations remain unchanged. One
serial unprofiled resolver invocation returns in 556.705 seconds; its fresh
whole-worker supervisor observes 633.069 seconds under the original 1,800-second
experiment ceiling. Restore/replay, query bookkeeping, witness revalidation and
the separate slowest-query profile have distinct recorded boundaries. No primary
timing run is repeated to confirm a deadline.

All five models' ten obligations are evaluated: seven searches return, while
three are already satisfied. Six searches remain unresolved and model 001 has a
reachable engagement alternative. The completed resolution is invalid with
`charge_reachability_unresolved`; full candidate path/terrain/coherency checks do
not excuse its mandatory endpoints. Exact post-evaluation checkpoint equality
holds and no movement is submitted. The complete returned alternative is checked
against its original full path, terrain and endpoint context outside timing.

Model 003 and model 002 engagement account for 46.5% of resolver wall time; the
seven distinct full-query keys produce no cache hits. A separate 307.836-second
cProfile query preserves the model-003 unresolved/57-node result; 23,248 complete
witness validations include 13,108 terrain validations and 1,729,628 terrain
footprint constructions. Its cold-cache/profiled boundary is separate from
primary timing and does not isolate profiler overhead. All diagnosis finishes
within the original allowance. The next bounded geometry-owner experiment is
reuse of immutable terrain geometry across complete-prefix validations, preserving
all path, endpoint, cache/isolation and search obligations. This evidence identifies
remaining mandatory endpoint-search cost without admitting an operator result
to an actor, scorer, useful-reference factory or learning consumer. Historical
censored evidence remains censored. Existing restore/replay/resolver contracts
cover this diagnostic; no runtime/schema/decision change is introduced. A legal
Charge Move, tactical benefit, common horizon, Stage 2 and full-game throughput
remain open, with `scoped_gap`, null target, learning exclusion and the inherited
source/roster/provisional geometry/mission/points/public-seed limits intact.
