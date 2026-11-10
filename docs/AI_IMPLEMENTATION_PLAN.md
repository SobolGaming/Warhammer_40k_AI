# CORE V2 AI implementation and learning plan

This is the maintained forward plan for the Phase 19 AI work and its Phase 20 qualification dependencies. It supersedes the November 5 chat proposal's mandatory hierarchy and implementation ordering where stated below. It is not a claim that the planned interfaces, experiments or playing strength already exist.

## Scope and evidence baseline

The original planning revision was documentation only. Later implementation is tracked in the current evidence below and the maintained AI interface. Publishing the original plan did not authorize its implementation stages.

Inspected local branch: `codex/pr2-strict-player-ai`, commit `b2d6fef219dca22d482fe29937914fbdf1415240`. It was clean before this work. GitHub main was independently read as `fc9cd82f4c2f557b4597cd8edffb343404825dea`; both commits have source tree `2dea72d3a12ff0e9225865ae48f153cfd89c145c`. They are different commits with identical tracked contents, not interchangeable provenance IDs. The original documentation was isolated on local branch `docs/ai-plan-20261107`. For publication, the branch is based on the verified main commit. That original revision changed this plan, links/status qualifications in `AI_POLICY_INTERFACE.md` and the required exact-base performance assessment. It left runtime and policy settings unchanged.

Read this plan with [AGENTS.md](../AGENTS.md), [architecture](../ARCHITECTURE_V2.md), [AI interface](AI_POLICY_INTERFACE.md), [adapter decision contract](ADAPTER_DECISION_CONTRACT.md), [performance policy](performance/PERFORMANCE_POLICY.md), [Core roadmap](CORE_RULES_REMEDIATION_ROADMAP.md) and [faction roadmap](FACTION_RULES_REMEDIATION_ROADMAP.md). Their binding rules are preserved. Historical roadmap headlines do not override later scoped implementation evidence or establish certification.

### Verified findings and unresolved claims

| Topic | Verified current evidence | Consequence / remaining uncertainty |
|---|---|---|
| Strict player controller | `ai/player_policy.py`, `ai/runner.py`, and `AI_POLICY_INTERFACE.md` supply detached player snapshots, exact routes, bound choices and explicit failures. | PR2 foundation exists. It is not autonomous battle play, search, training or a full-game opponent. Earlier claims that this boundary still needed initial construction are historical. |
| Finite candidates | `ai/finite_candidates.py` captures immutable ordered option payloads and hashes bound to the actor, request and observation; active regressions are in `tests/infrastructure/adapters/test_finite_candidates.py`. | Finite choices return the existing bound `PolicyAction` and use ordinary engine commits/replay. The independent finite training companion now checks row/mask/selection integrity. The opt-in semantic observation companion pins the existing finite option-count feature with typed units, scalar dimensions and actor-view scope. The finite accepted-transition companion now reproduces ordinary submissions and binds contiguous checkpoint links from a trusted slice origin. The independent episode/target companion now reproduces ordinary origin reachability, checks a contiguous finite slice and strict sources, and admits engine-verified terminal labels or explicitly missing nonterminal targets. The bounded `command-point-balance-v1` local calculator now recomputes endpoint CP with exact accepted-record horizons. The bounded deployment-placement accepted-transition companion now uses ordinary viewer submission reproduction, and mixed finite/proposal episodes share origin/continuity admission and exact-horizon CP evidence. The bounded accepted deployment singleton now binds its actor-view proposal to the full training row and verified transition, and named/admitted targets support exact mixed-episode joins. A separate actor-only deployment generator now produces bounded whole-formation XY translations, deduplicates them and records raw budgets; an operator validator uses a fresh ordinary viewer-submission fork per candidate, with explicit validation/accepted caps, rejection diagnostics and typed exhaustion. A separate validated-set training link now binds the complete generated set and validation receipt, the validated-prefix row mask, an accepted selected slot and the exact reproduced transition/checkpoint; named/admitted targets reuse mixed-episode checks. A separate accepted-only ranking boundary now passes detached actor context and accepted payloads to a caller-supplied scorer, rejects inexact/nonfinite scores, resolves ties by generated order and rechecks the live checkpoint. Its v2 operator receipt now binds typed RANKER provenance, declared deterministic behavior, actor-visible parameters actually supplied to the scorer, current build and live configuration. A separate ranked-row companion joins the complete ranking to identical validation, selected accepted transition, choice seed and full row provenance; checkpoint/rejection evidence stays outside scorer arguments. The separate deployment model-origin registry now encodes candidate model count, unweighted XYZ centroid and XYZ span from detached actor proposals, with pinned dimensions, inch units, world frame and aggregation semantics. Only numeric values enter model inputs; opaque references stay in binding fields. Its exact ranked-training companion checks the selected accepted candidate and the complete row feature values/provenance. Focused controls execute a geometry-based selection through ordinary commit/save/load/replay and preserve hidden-work/private-RNG isolation. The operator-only experiment companion now binds that complete choice/encoder evidence to a verified mixed episode and exact accepted transition with strict source/config/reward/current-build joins; it retains producer-recorded seeds/budgets without inventing whole-run enforcement or artifact authentication. A separate runner/dataset companion now verifies supplied run boundaries and complete attempt accounting, joins accepted deployment experiments and exact targets, and excludes failed-run rows while retaining their denominators. Other parameterized families, tactical/learned rankers, broader local calculators/semantic features and full dataset qualification remain open. |
| Decisions | `GameLifecycle.decision_dispatch_contracts` in `engine/lifecycle.py`: 88 registered contracts, 75 finite and 13 parameterized. `DecisionRequest.decision_type` is a validated string, not a DecisionType enum. `contracts/schemas/proposal-payload.schema.json` has 12 proposal shapes. | Counts have different denominators. The documented nested weapon-ability choice is not a registered top-level contract; see `tests/code_quality/test_ws6_decision_dispatch_registry.py`. Recompute inventory at implementation time. Registry size is not a reachable-policy coverage result. |
| Training contracts | `ai/policy_contracts.py` defines TrainingFeature, TrainingRow, PolicyProvenance and four PolicyArtifactKind roles. `tests/unit/test_phase19_policy_contracts.py` is a historical, explicitly inactive/quarantined module; active bounded ranking/provenance and mixed-episode controls are in `tests/infrastructure/adapters/test_deployment_candidates.py` and `test_training_admission.py`. | Contracts exist; no verified populated training dataset or human replay corpus was found. A role enum does not prescribe four separate neural networks. |
| Replay vs planning | `LocalGameSession.fork()` and persistence in `adapters/local_session.py` preserve authoritative lifecycle/RNG state. Contract 46 keeps private seed and draw authority out of player views. | Exact replay is useful and trusted. Forking alone is not information-safe planning or independent future dice. |
| Full-game driver | `docs/performance/policy-v3/operation-map.json:full_game_profiles` is empty. `scripts/check_performance_policy.py` requires an available registered driver and evidence for `rules_complete`. | A runner, setup smoke or replay helper is not a registered supported full-game training workload. No measured full-game training throughput is established. |
| Daemons | `docs/factions/chaos-daemons.md` and `AI_POLICY_INTERFACE.md`: exact v995 roster, nine units/39 models per side, seven provisional height records; real setup/replay reaches round-1 Command. | This admits the bounded setup and selected components, not FULL_GAME_SUPPORTED, REPLAY_VERIFIED or a ready sacrifice-learning matchup. Do not hand-edit generated faction guides. |
| Core/faction completion | Core roadmap compliance claim requires all relevant implementation orders, S-MIRRORS, PFINAL and a fresh 25-category audit. Faction roadmap Gate 0 is PFINAL; L6 fieldable, L7 full-game/replay, L8 comprehensive certification differ. | No blanket certification is inferred from merged PRs, test totals or loaded rows. Scoped canonical experiments still need trustworthy mechanics; this plan neither bypasses faction gates nor adds a universal two-certified-faction learning prerequisite. |
| Phase identifiers | Architecture retains grouped 19A-19F and 20A-20D rows; contracts explicitly anchor training/provenance to 19E. 17N and 18M-B+ retain relevant mission/conformance work. | Individual 19A/B/C/D/F and 20B/C assignments are not verified from the maintained map. Use grouped IDs and named work packages below, not invented renumbering. Core remediation P19B is unrelated to product Phase 19B. |
| Corpora and fixtures | Replay tests, canonical scoring/charge helpers and conformance examples exist; references below. | Some helpers construct state directly. They are reference fixtures, not automatically valid training checkpoints, complete golden corpora or human demonstrations. Provenance/admission must be established for each selected experiment. |

### Historical performance evidence, not current training throughput

[Issue 590](performance/issue590.md) and `performance/issue590-http.json` are historical, bounded HTTP measurements against base `5657bf5f127466edeecf3259e0a53e29f6a9a352`. Conditions: Windows 11 Pro, Threadripper 3970X, CPython 3.14.5, locked dependencies, noneditable candidate wheel, reference server without SQLite/persistence. Post-setup requests were warm; OS caches were not cleared.

- Inventory rejection: six samples, median 1.932 s, range 1.675-2.310 s; historical prior median 24.019 s.
- Complete long-distance rejection: four samples, 10.461-11.720 s; original attempts were censored at 30 s.
- Corrected legal one-inch movement: two samples, 7.585 and 7.670 s; original attempt timed out.
- Exact accepted-command duplicate: 0.029-0.038 s.

Do not multiply these into a game runtime, infer a completed-baseline speedup from censored timeouts, or combine them with separate native WSL component samples. The historical 64% coverage figure is not current policy.

The standing full-game product requirements remain arithmetic mean below 60 s and no measured game above 300 s on the versioned supported workload and reference hardware. They are neither achieved nor waived. Order 32 deferred its provisional component certification and broader efficiency work pending measurable complete games; deferred evidence is not passing evidence. Current exact-slice profiling and justified repairs remain governed by the performance policy. This plan does not turn the 60-second requirement into an aspiration or a prerequisite for every schema discussion.

## 1. Authority, routing and outcomes

CORE V2 alone owns legality, rules execution, state mutation, dice, scoring and authoritative replay. AI consumes permitted observations and ordinary requests; it returns ordinary bound finite/proposal results. The engine validates and commits. No policy directly updates state or substitutes a learned rules model for legality.

Retain exact actor + decision type + stage + setup step/battle phase + proposal-kind routing. Missing or ambiguous routes, unsupported required semantics, malformed/non-finite model output, incompatible artifacts, stale bindings and invalid committed actions stop with typed diagnostics. No implicit pass, random action, first-legal action or alternative-policy recovery.

An explicitly selected diagnostic/heuristic opponent is a named experiment configuration, not failure recovery. A search may finish its declared budget and return its best evaluated validated candidate when that is its stated algorithm. An empty valid set, failed required evaluation or contract violation is a typed failure, not an emergency switch. The current runner's rejected committed-action behavior is unchanged.

Distinguish episode states:
- **Terminal:** engine-declared ordinary result; initial utility is win 1, draw 0.5, loss 0 from the stated player's perspective.
- **Truncated:** declared experiment/horizon limit before terminal; no fabricated win/loss label. Bootstrap only under a declared justified estimator; retain truncation and uncertainty.
- **Aborted:** infrastructure, budget/watchdog or integrity failure; report and exclude from ordinary outcome targets, not from attempted-game denominators.
- **Unsupported:** required mechanic/route unavailable; quarantine the trajectory for outcome learning and report the capability gap.

Use undiscounted finite-game utility initially. Do not apply 0.99 (or another conventional gamma) once per atomic request. If an alternative time scale is tested, define whether elapsed turns, phases or physical time determines discounting and why. Actor, active turn and value perspective are separate fields; reactions and allocation mean actors do not alternate at every transition. VP margin, future scoring, resource preservation and calibrated combat predictions are auxiliary targets, not replacements for winning. Their weights are experiments.

## 2. Candidate and observation contracts

### Candidate lifecycle

Finite choices select current engine-emitted option IDs. Parameterized choices require a bounded variable-size candidate set, not a fixed global action dictionary. Inventory each supported family using the adapter contract, including deployment/setup poses, movement/charge/fight/reactive paths, attack target/weapon allocations and nested proposal contexts. Do not confuse request families with wire shape counts.

The finite set contract now preserves engine-emitted options and exact view bindings; see [the AI interface](AI_POLICY_INTERFACE.md#finite-candidate-contract). The broader planned trusted candidate service returns:
- opaque candidate ID; actor/request/view binding; state/observation version and relevant rules/config identity;
- full typed ordinary payload, target/entity links, model poses/paths/witnesses required by that family;
- generator version/config/seed, proposal ordering, validation result/diagnostic and cost;
- candidate-set identity, ordered candidates and any ranking-only descriptors.

Opaque references link models, units, targets and records. Their arbitrary values are not learned semantic features. A viewer binding is not permission to expose authoritative hidden revisions.

Keep four stages explicit:
1. **Internal generation and validation:** propose on an isolated trusted validation surface. Reuse exact engine validators with required authority, not duplicated approximate legality. No queue pop, RNG consumption, events, attempt records or other mutation on the live session. Isolated simulation may consume its declared independent planning RNG when required; it never consumes live future chance. The bounded deployment companion now uses a fresh ordinary session fork per proposal and verifies the live checkpoint is unchanged. A generic non-mutating bulk validation API remains proposed work, not an existing facade method.
2. **Selection:** rank only engine-validated candidates for the current binding. The bounded deployment ranker now receives only detached actor context and accepted payloads in generated order; exact finite scores, first-generated tie resolution and pre/post checkpoint checks yield an ordinary bound action. Full-set/validation hashes and reproducibility evidence remain operator-only. This supplies no tactical or learned ranker. Rejected proposals may train legality/proposal objectives with their diagnostics, not executed-transition rewards.
3. **Commit:** submit the selected ordinary payload through the existing player-scoped adapter; revalidate current binding and legality. Unexpected rejection remains an explicit runner failure.
4. **Protocol retry:** only where the actual adapter lifecycle explicitly records a well-formed rule-invalid attempt and emits a fresh request. Follow the family-specific contract and new bindings. Internal rejected proposals do not imply a new live request, and protocol retry is not policy fallback.

Initial experimental ceilings, to be tuned with measurements: 64 raw placement proposals, 32 raw movement proposals, 16 validated candidates per choice, and a recorded geometry-work limit appropriate to the solver. Zero protocol retries in the strict first learning experiment. Broader retry-capable consumers require explicit design and tests; do not restore the earlier blanket eight-live-attempt proposal. Exhaustion reports typed candidate-generation/validation-budget/empty-set errors plus attempted counts, never "no legal action exists" without an engine proof.

Track validity yield, diversity by meaningful geometry/target outcome, reference-alternative coverage, generation/validation cost and ranking quality separately. A screen/preserve/coordinated benchmark fails candidate coverage before any learner is scored if its useful alternatives are absent. Include intentional stationary/decline candidates only when legal and deliberately generated.

### Permitted observation

Use capability and rule semantics: effective profiles/modifiers, weapons, canonical keywords, supported ability operators, resource constraints, temporary effects/expiry, physical model and terrain geometry, attached-unit membership, wounds/presence, objective control and relevant visible action history. Do not learn faction/datasheet names or arbitrary IDs as a shortcut. Structured categorical vocabularies and units are versioned.

Include both players' public primary/secondary scoring semantics: conditions, progress, caps, scoring player, timing, active objectives and remaining opportunities. Mission IDs supplement, never replace, those semantics. The policy-facing projection does not yet establish a complete structured scoring-feature contract; audit existing `GameViewPayload` fields and add only narrowly justified permitted features in future implementation.

Audit visibility per phase and pinned mission pack. The supplied requirement describes Event Companion v1.3 active Tactical cards as face-up and unrevealed deck order as hidden. Current runtime public-card behavior is verified in `GameState.public_secondary_mission_card_states`, `public_tactical_secondary_draws`, and `SecondaryMissionCardState.to_public_payload`; `GameState.to_public_payload` removes private RNG and tactical draw authority. However, `data/source_audits/event_companion_2026_10/README.md` authenticates October layout pages 8-53 only and explicitly leaves July mission/scoring transcriptions under their historical ownership. The October mission-sequence wording comparison is therefore still open; do not claim that layout pin verified it. Qualify this source check before any October-specific visibility certification. Pregame selections and reserve/embarkation assignments remain private until their specified reveal. Public rosters and revealed model positions are not automatically secret because a rule says Hidden or blocks line of sight. Preserve exact game-rule visibility without inventing fog-of-war coordinates.

Maintain decisions on both sides of chance boundaries, including `select_charge_targets` after the Charge roll and before Charge Move, as documented in `DECISION_SUBMISSION_CATALOG.md`. Preserve the distinction between pre-roll information and realized dice; do not attach future outcomes to earlier actor inputs. Verify noninterference by varying hidden-only opponent work and engine future RNG while holding permitted history fixed.

## 3. Trusted simulation and reproducibility

Exact replay forks preserve original authority to reproduce recorded events. Planning simulations are a separate engine-owned service. A new fork token is not isolation: `core/rng.py::RandomSource.fork(token)` retains the seed/draw count while adding a history token; changed derived draws alone prove neither hidden-state isolation nor independence from live authority.

Before search, specify and test:
- input: acting viewer, permitted observation/history and a trusted immutable source checkpoint handle, never raw checkpoint bytes supplied to the policy;
- reconstruction: preserve all public facts and already revealed chance; sample only genuinely unknown deck order or unresolved private choices consistent with rules and observed history;
- independent branch chance: use a separate planning master seed and deterministic branch-path/sample indices. Never derive it from wall-clock time, live future dice, private engine seed, global hidden counters or incidental traversal scheduling;
- isolation: no shared mutable model, request, RNG, cache, event or policy state with live play or siblings; simulation uses the same authoritative rules path;
- outputs: viewer-scoped simulated observations, typed outcomes/costs, no hidden source state leakage;
- replayability: pin engine/source/config, observation encoder/vocabularies, candidate generator, model artifact, search algorithm, work budget, opponent model, branch seed derivation, arithmetic and tie-breaking. Record selected action and candidate-set identities.

For public-information canonical fixtures that do not require hidden hypotheses, a scoped simulation boundary suffices; a general hidden-state constructor is not a prerequisite. Search requiring hidden information cannot proceed until its relevant consistency sampler is qualified. A privileged critic is optional and separately declared for offline training, with distinct actor/critic schemas, storage and leakage tests. It supplies no privileged features to deployed actor or live search.

Use engine-derived analytical combat probabilities when correct and cheaper. Preserve stochastic successor sampling where casualties, thresholds, effects and future choices are nonlinear; a fractional average state is not an ordinary legal successor.

## 4. Learning, provenance and compatibility

### Learner and data strategy

Start with a compact shared entity/candidate encoder, a policy ranking head (and finite-choice head where needed), plus value/auxiliary heads. A small MLP/set encoder is the first size baseline; attention/graphs, persistent goal tokens and learned hierarchy require measured gains. Preserve the existing external route/role interfaces regardless of shared parameters.

Bootstrap only from verified canonical trajectories, explicitly configured heuristic policies and small exact-engine branch comparisons. The existing setup recipe is useful regression data but not demonstrations of tactical skill. No human corpus is assumed. V1 offers hypotheses and algorithms only under AGENTS' tests-first, smallest-reviewed-concept migration process; its old outcomes are not V2 labels.

Initial experiment is staged: offline supervised candidate/reference-value learning, then a bounded online comparison if simulator cost permits. Compare a simple imitation/ranking baseline, value-based or other off-policy reuse where coverage/behavior metadata supports it, and PPO only as a possible on-policy baseline. Decide after pilot throughput and data audit. Unsupported off-policy correction cannot be invented for old deterministic logs. Learning curves report outcome/reference-regret versus accepted transitions, attempted episodes and CPU/GPU-hours, not just epochs.

Proposed research ceiling, not a purchase or hardware allocation: a first profiling/admission pilot capped at 8 CPU-hours; a first learning sweep capped at 64 CPU-hours plus 8 GPU-hours if an available device is explicitly selected. Record actual machine and memory. Stop at the first exhausted budget and report partial evidence, not success. Before substantial full-game self-play, propose a measured costed budget including simulation, candidate rejection, search, inference, training, evaluation, storage and contention. No minimum million-game count or numerical feasibility gap is assumed.

### Schema gap analysis

The remaining extensions below are proposals. Keep existing schema/version semantics and strict loaders until a separately authorized migration. The finite candidate, training-link and named-target contracts are independently versioned; none migrates `TrainingRow`.

| Need | Existing support | Smallest justified extension / rejection rule |
|---|---|---|
| Semantic features and references | TrainingFeature retains its original schema. The independent finite semantic registry/observation and exact row companion in `ai/semantic_features.py` now pin the existing option count: integer, count units, scalar dimensions, actor-view scope and no categorical vocabulary. Only numeric registered values enter `model_inputs`; references remain linkage. The independent `ai/deployment_geometry_features.py` registry supplies proposed model count, unweighted world XYZ origin centroid and axis spans (not physical base/hull bounds), and a separate exact selected-ranked-row geometry join without changing TrainingRow v1. | Broader unit/weapon/physical-geometry/scoring features, categorical vocabularies and dataset source/build admission remain open. This partial geometric representation does not complete selected-workload features or references. Unknown required features/operators fail explicitly. Actor-view information is not automatically public to opponents; preserve adapter disclosure. |
| Candidate linkage | TrainingRow stores legal-action mask and chosen_action_id. The finite candidate set supplies ordered payloads, hashes and actor/request/view binding. `FiniteTrainingCandidateLink` binds the full row hash to that snapshot and checks its complete legal mask and chosen slot. | The separate finite accepted-transition verifier reproduces engine acceptance and checkpoint continuity; candidate integrity alone still does not certify execution. The separate accepted deployment singleton binds its full row and verified accepted action. A distinct bounded deployment translation set and operator fork-validation receipt now capture alternatives and count budgets without changing that singleton row schema. A separate validated-set link now binds the full search evidence, validated-prefix mask and selected accepted slot to the exact transition checkpoint and named/admitted target. Unvalidated candidates have no row mask slot. The separate ranking receipt now selects an accepted action with exact scores, deterministic ties and checkpoint rechecks; the existing link accepts that action without a schema change. The separate ranked-row companion now binds the complete v2 ranking/configuration and exact row provenance to that link. Broader parameterized candidates, tactical/learned ranking and dataset eligibility remain explicit follow-ups. |
| Temporal trajectory | `FiniteAcceptedTransition` reproduces finite engine acceptance, exact before/after checkpoints and actor views, authoritative joins, position metadata and contiguous predecessor hashes. Its accepted-record index starts at an explicit trusted slice origin and includes automatic selections. | The independent episode companion now replays ordinary startup/prefix reachability, checks contiguous finite evidence and classifies terminal or explicitly declared nonterminal boundaries. The bounded deployment-placement companion and mixed episode admission now share these invariants and the endpoint CP calculator. Accepted deployment singleton candidates now have exact row and named/admitted target linkage in mixed episodes. Separate bounded deployment translation generation/validation now exists; the separate multi-candidate link now joins its selected accepted slot to mixed-episode targets; the separate accepted-only ranking boundary can now supply that selected action; add other proposal families, tactical/learned rankers, chance-boundary semantics and complete dataset admission; these bounded receipts are not workload or dataset certification. |
| Targets | The original scalar target_value and reward_profile_version remain unchanged. `ai/training_targets.py` adds strict, independently versioned named declarations and exact finite row linkage: meaning, perspective, horizon, episode end, missingness, units, producer/evidence and reward version. | The independent admission companion now checks actual engine terminal outcomes, exact accepted-record horizons, fixed producers and strict source/reward compatibility. Missing nonterminal targets remain excluded from learning. The verified `command-point-balance-v1` local calculator admits exact endpoint CP balances for terminal/truncated finite slices, measured from the linked transition start and including accepted automatic selections. Unknown calculators, unavailable interior endpoints and early-terminal/overrun horizons fail closed. Accepted deployment row targets now use the same verified terminal and exact-horizon CP calculations in mixed episodes, with missing targets excluded and actor/perspective kept distinct. Broader references and dataset eligibility remain open; no old scalar is repurposed. |
| Behavior and search | The bounded deployment v2 ranking now requires typed RANKER provenance, a deterministic-given-inputs marker and canonical actor-visible parameters supplied to the callback. Its separate ranked-row companion joins exact selected behavior and row provenance; existing receipts retain candidate budgets, choice seed and tie-break. The runner now retains a versioned operator manifest of declared registration/configuration, policy seed and cooperative limits, plus actual route attempts, failure stages and status-qualified submission outcomes. | Stochastic distributions/log-probabilities where required, authenticated model artifacts, hard cancellation and broader dataset qualification remain open. The bounded runner admission now checks complete supplied attempt ledgers against replayed checkpoint/count/context/seed evidence and an optional accepted-prefix episode; deployment dataset admission joins exact experiment/target/registered-ranking evidence and retains failed-run denominators with excluded rows. The separate bounded experiment companion now joins this actual choice evidence to its selected-row encoder and reachable accepted episode. Deterministic scores are not probabilities; declared artifact identity does not authenticate code or weights. Debug metadata is not a validated contract for required learner inputs. |
| Reproducibility / information | PolicyProvenance binds catalog packages/hash, ruleset identity/descriptor, engine version and reward version. Bounded deployment ranking now checks these strictly against the live run, binds the current verified build and live config hash in operator-only v2 evidence, and joins complete row provenance through a separate companion. | The bounded `DeploymentExperimentProvenance` now joins the complete ranked choice, actual generator/validation budgets and choice seed, selected-row model-origin encoder, accepted transition and verified mixed episode under strict config/source/reward/current-build checks. Its content hash covers one accepted choice; ranker identity/behavior and episode stop reasons retain their declaration limits. The bounded runner now retains its exact declared manifest/limits and actual attempted-choice ledger, including unsupported routes and recorded rejections; a separate operator admission now joins these to replayed run boundaries and accepted-prefix episodes. Bounded deployment dataset admission retains all supplied runs and outcomes, joins exact experiment/target/registration commitments and excludes every failed-run row from learning. Producer declarations remain unauthenticated; omitted runs and report-less crashes are outside its denominator. The separate operator-only `DeploymentDatasetSplit` now binds every supplied run occurrence and all its rows to train/validation/test, keeping conservative verified-startup trajectories and declared trajectory IDs, scenario families and geometry groups within one partition. It preserves duplicate occurrences and excluded/zero-row failures with reconciled partition accounting; group labels remain declared and unverified, not authenticated geometry equivalence. The separate bounded deployment workload manifest now joins complete split receipts to exact configuration/route declarations, pinned semantic/reference definitions and actor/operator information access. Broader workload qualification, hard watchdogs, additional encoder/vocab versions and authenticated weights remain open. See the selected Stage 1 reconciliation below. Preserve strict provenance joins and explicit versioned migration; v1 ranking evidence is not silently rewritten as v2. |
| Artifact roles | GENERAL, COMMANDER, RANKER, EVALUATION_FUNCTION exist. | Retain roles and link one shared model artifact to multiple declared interfaces if appropriate. Renaming enums is not needed simply to share weights. |

Migration is explicit, source-to-target versioned and preserves original bytes/metadata. Old rows stay readable by their matching runtime or an audited converter; unexpressible data is rejected/quarantined, not filled with invented features, behavior probabilities or targets. Rejected proposals have a separate diagnostic/proposal-training record and no fake committed transition.

### Patch adaptation by semantic impact

Use structured changes to choose tests, not to certify reuse automatically:
- points: roster legality, budgets, target recalibration and matchup distribution;
- numeric profiles: affected combat/movement/threshold semantics and value calibration;
- keywords: structured eligibility, interactions and observation vocabulary;
- existing mechanic composition: affected interaction/replay fixtures and representation coverage;
- new semantic operator: source/engine implementation and representation work before actor deployment;
- new decision type/proposal: exact routing, generation, schema and conformance work.

For each patch separately decide: weight initialization; old-policy evaluation under new rules; eligibility of historical transitions/labels; re-simulation or explicit migration; deployment. Reuse weights is not reuse labels. Old transitions with changed legality or rewards must be regenerated or excluded. Re-simulation may diverge and creates new labelled data linked to, not overwriting, the original.

Version operator schemas and categorical vocabularies. A novel identifier entirely composed of supported semantics should be representable; unknown required mechanics fail explicitly. Budget source/engine work separately from model adaptation. Do not assume most patches need new engine operators. Broader faction claims remain subject to the faction roadmap.

## 5. Dependency-ordered delivery roadmap

Stage labels below are work-package names within existing phases, not new product-phase IDs. Individual mappings beyond verified 19E are deliberately not invented. Implementation stages require explicit authorization; the original planning revision authorized none.

| Order / existing ownership | Entry | Work and exit evidence |
|---|---|---|
| Contract and evidence audit: 19A-19F, specifically 19E data/provenance; 18D/18M-B+ for changed adapter contracts | Current source/tree, AGENTS and relevant authority paths read | Close the gap analysis for the selected workload; explicit actor/candidate/target/provenance schemas and negatives; no runtime behavior claim. Contracts/documentation can proceed without a full-game driver or universal hidden-state constructor. |
| Scoped workload admission and measurement: 19A-19F; existing core owners | Trustworthy selected rules, ordinary decision/replay path and disclosed fixture limitations | Pin exact canonical fixture, required mechanic/route inventory, source/geometry/scoring and any legacy roster exception; derive actual reachable trace; measure component costs and candidate coverage. Missing support returns to existing remediation owner. |
| Action capability: 19A-19F and 18M-B+ | Accepted fixture inventory and candidate contract | Extend deployment, movement, ranged, charge/fight and reaction choices incrementally through ordinary requests. Prove generated alternatives, legal commits, replay and redaction. Preserve already-landed PR1/PR2 scope rather than rebuild it. |
| First learning experiment: 19A-19F + 19E | Relevant candidate coverage, trusted fixture mechanics, eligible trajectories and bounded compute | Execute the screen/preserve/timing/cooperation experiment below. No two-faction or full-game throughput prerequisite for this bounded experiment. No broad playing-strength claim. |
| Scoped search comparison: 19A-19F | Qualified independent-randomness/isolation boundary for the information actually used, useful candidates and measured branch cost | Compare policy-only and bounded search at stated work budgets. General hidden-state sampling only if needed. Report quality-cost tradeoff; no fixed one-to-two-request horizon rule. |
| Ordinary terminal workload: 17N, 18M-B+, 20A within 20A-20D | All required mechanics/routes/mission branches ready for chosen roster and ordinary continuation | Setup-to-terminal trace with meaningful movement/combat/scoring, exact replay, typed failures, viewer safety and versioned workload registration. Setup smoke is insufficient. Broader faction certification still follows PFINAL/Gate0/FM requirements. |
| Throughput/sample-efficiency decision: 19A-19F; performance policy; 20A-20D | Registered supported full games with honest completion denominators | Representative in-process/transport/search/inference measurements, resource budget and projected cost ranges based on measured distributions. Preserve 60s/300s requirements; explicitly report unmet/deferred targets. Decide whether to optimize, narrow research or scale. |
| Substantial full-game learning/evaluation: 19A-19F + 19E; Phase20 qualification | Measured throughput, stated compute budget, eligible outcomes/data and selected-workload support | Frozen baselines/checkpoints, paired evaluations, learning curves and robust failure accounting. Expand roster/mission/geometry claims only as their gates and held-out evidence close. |
| Patch/league/hierarchy expansion: 19A-19F and 20A-20D | Qualified baseline, semantic-change matrix and reproducible comparison | Test shared-policy vs search vs added hierarchy separately; validate update pathways and broader matchups. 20D/release claims require their existing explicit certification evidence, not a new AI score threshold. |

This replaces the old sequence's "learning only after every full-game stage" with supported local experiments, and brings measurement earlier. It does not relax AGENTS' requirement for trustworthy deterministic core, decision records, replay and movement/shooting/fight slices before AI/training. Full-faction implementation remains governed by Gate 0; unsupported fixture mechanics are not bypassed.

### Selected Stage 1 contract audit and endpoint

The selected workload for this slice is **bounded setup/deployment contract
evidence**, pinned by `DeploymentWorkloadContract` to each supplied exact
configuration and route inventory. Canonical controls use the ordinary setup
fixtures in `tests/shared/ai_training_admission_helpers.py` and
`canonical_setup_prebattle_smoke_config`, including a compact configuration
that reaches terminal after deployment. That terminal boundary validates
plumbing, not a played battle or the delayed-tradeoff experiment. Exact fixture
configurations, source/build identities and origins are committed through the
receipts; a friendly workload name never substitutes for them.

The Stage 1 exit above is a contract/evidence audit: close the selected workload
gap analysis with explicit actor/candidate/target/provenance schemas and negative
controls, without claiming runtime workload qualification. Reconcile merged
evidence and the current scoped addition as follows:

| Required for this selected contract | Owning evidence and negative boundary | Disposition |
|---|---|---|
| Actor and candidate binding | Detached exact routes, finite candidates, bounded deployment generation/validation/ranking; wrong actor, stale binding, unsupported proposal, rejected commit and hidden-work isolation controls | Existing contracts; preserve ordinary engine acceptance and private information boundaries. |
| Required semantic features | Finite option count; deployment model count, unweighted XYZ centroid and XYZ span with exact units/dimensions/frame/provenance; malformed values, unknown definitions and selected-row drift rejected | Existing bounded registries, now pinned by the workload manifest. Physical footprint, weapons, terrain and tactical scoring encoders are not requirements of this origin-summary workload. |
| Target/reference meaning | Named/admitted target and exact endpoint CP calculator; wrong perspective/source/horizon/producer/value rejected; missing failed-episode labels excluded | Existing bounded reference, now required by the workload join; other legitimate reference definitions fail this selected workload instead of inheriting CP meaning. |
| Provenance, complete supplied attempts and split | Current source/config/build, ranked experiment/encoder/episode joins, runner admission, all failure denominators and conservative trajectory/group partitions | Existing receipts retained in full; no omitted-run or report-less-crash completeness claim. |
| Selected workload and information-access reference | Exact configuration set, declared/observed/unobserved route inventory, semantic/reference identities and fixed actor/operator access; incompatible declarations and changed closed payloads rejected | Added in this slice. Operator receipts remain outside actor/scorer arguments; declarations do not authenticate callbacks or prove exhaustive reachability. |

No additional semantic feature or local-reference calculator is required by
this explicitly bounded contract. [PR651](https://github.com/SobolGaming/Warhammer_40k_AI/pull/651)
merged as `0ef1e9ec005566726efb1fb17873f78677b762eb` after passing exact-head
independent review, the parent audit and required delivery gates, including PR
and main CI. The reconciled evidence closes Stage 1 only for this explicitly
bounded setup/deployment contract. This does not close a different workload's
Stage 1 audit. Selecting the proposed screen/preserve workload would require a
new scoped audit of its actual physical, scoring and reference semantics.

Stage 2 separately owns canonical workload admission, the reachable mechanic and
route trace, measured component costs and useful candidate/reference-alternative
coverage. Those are required before claiming that stage complete; they are not
retroactive missing Stage 1 schema requirements. Optional/future work here includes
other proposal families, new tactical features/references, authenticated weights,
hard watchdogs and information-safe search. The Stage 1 contract itself executes no Stage 2
measurement, gameplay extension, ranker learning or training. The first separate
Stage 2 slice below admits one canonical prefix; the remaining stage obligations
retain their separate qualification requirements.

### First Stage 2 canonical prefix admission

`ai.canonical_deployment` now freezes exactly one setup/deployment fixture and
recipe, documented with its full configuration hash and source/geometry/scoring
exceptions in [the canonical admission interface](AI_POLICY_INTERFACE.md#frozen-canonical-deployment-admission).
The ordinary runner accepts eleven decisions over seven exact routes, deploying
four units/14 models and stopping before the first redeploy choice. Admission
compares a supplied session to fresh ordinary reproduction and strict startup,
JSON persistence and replay. The receipt retains the actual ordered accepted
trace, required versus observed routes, pending endpoint and explicit unexercised
continuations. No synthetic checkpoint is treated as engine-generated.

This is scoped fixture/prefix admission, subject to required exact-head delivery
gates, not completion of Stage 2. Useful candidate/reference-alternative coverage
and component costs remain open. The current fixed recipe supplies neither a
training dataset nor new scoring targets, tactical alternatives, exhaustive
reachability or full-game evidence. Its synthetic Core roster, legacy geometry,
July mission/scoring identity and October layout geometry retain their disclosed
limits. The next slice should select one remaining measured coverage/cost
obligation against this frozen fixture, or explicitly review a different fixture.

## 6. First delayed-tradeoff experiment

**Status: proposed, not an existing certified benchmark.** Start from the earliest suitable canonical Core fixture/checkpoint. References: `tests/replay/test_phase18b_replay_runner.py`, `tests/shared/category_migration/primary_boundary_scoring_builders.py`, `tests/shared/category_migration/phase11f_game_end_scoring.py`, and `tests/support/selected_target_charge_fixtures.py`. Use real domain objects and normal engine decisions; do not import test modules into runtime or present a synthetic state alteration as an engine-generated checkpoint.

Admission must reproduce a reachable checkpoint with source/config, accepted decision prefix, current rules identity and exact replay. If a helper uses direct mutations, rebuild its required position through ordinary play or explicitly validate a supported canonical scenario constructor; until then it is design input, not training evidence. No Daemons-specific dependency: select Daemons only after the required screen, movement, charge, attack and scoring mechanics are verified.

Use a screen unit S and a separate exploiter/scorer E against an opponent threat:
1. Screen/sacrifice creates a later scoring or attack opportunity that outweighs immediate material.
2. Matched preservation variant changes value/timing so preserving S is better.
3. Timing variant changes scoring window or opponent reachability while keeping superficial geometry similar.
4. Cooperation variant requires E to follow through; S alone cannot earn the benefit.
5. Held-out geometry, scoring conditions and opponent responses, including declining the apparent bait.

Reference outcomes come from bounded exact-engine enumeration/sampled continuations where tractable, plus review of rules/scoring and uncertainty. Evaluate terminal match utility when a validated terminal continuation exists; otherwise explicitly label the local scoring/reference target and do not relabel it as win probability.

Before learning: verify both useful screen and preserve choices and the necessary E follow-through are generated and engine-valid in every core case. Store reference candidate IDs and outcome confidence. If the generator misses them, fix proposal coverage, not model size.

Proposed pre-registered acceptance:
- zero wrong-actor/hidden-input/invalid-commit/unsupported events in admitted evaluation; all attempts and failures still reported;
- 100% reference-alternative coverage on core hand-reviewed cases; held-out coverage reported separately;
- learner selects screen vs preserve contextually and executes E follow-through, not just a screen-shaped first move;
- beat the declared immediate-material heuristic on held-out paired scenario families, with a 95% interval for the paired benefit excluding zero; report failure to reach statistical resolution as inconclusive;
- report per-variant results, geometry/opponent generalization, candidate budget, decision latency, CPU/GPU cost and learning curve.

Use a proposed initial test design of at least 20 held-out scenario variants per family and 10 paired chance seeds, then a predeclared cap for any extension within the compute ceiling. Split by scenario family/geometry and trajectory, not adjacent rows. Freeze generator, baseline and evaluation set before training. These sample counts are experimental starting points, not a power guarantee or claim of game-wide strength.

## 7. Performance and evaluation before scaling

Measure the actual headless workload, with and without the reference transport under matched conditions:
- process startup, source loading and cache temperature separately from steady state;
- proposal generation, candidate validation, ranking/inference, authoritative commit and actual retries;
- fork/restore/isolation, geometry/pathing/visibility, attack resolution, scoring, serialization and event projection;
- successful operations and costly rejected candidates/commits separately;
- game wall time, CPU-seconds/core-hours, peak memory, GPU-seconds/utilization, batch size, storage and concurrency contention.

Record hardware/OS/runtime/dependency/build identities, workload composition (models, terrain, mission, decisions and candidate budgets), seed protocol, cold/warm conditions, completion rate, sample sizes, median/p95/p99/max and uncertainty. Preserve censored timeouts. Report per-game distributions and total attempted/complete games, not only average successful operations. The standing 60s mean/300s observed-max uses its declared reference workload; finite samples are not a universal bound.

Optimize only measured owners, considering shared exact calculations, batching, caching with full semantic identity and invalidation, and exact early rejection. Retain equivalent accepted/rejected rules behavior, isolation, replay and expensive hard cases. Do not lower fidelity, silently raise budgets or expand broad deferred optimization work on the strength of a planning recommendation.

Evaluation uses frozen heuristic baselines, prior model checkpoints and specialist opponents, paired side-swapped scenarios/chance schedules, held-out rosters/missions/layouts when supported, and matchup confidence intervals. Elo is supplementary; specialist attacks are robustness probes, not formal exploitability estimates. Count attempted/completed games, typed failures, invalid proposals, protocol retries, candidate coverage, decision latency, search work and eligible data volume. Do not suppress failed episodes to improve win rate.

Suspicious self-play goes to the existing Core/faction remediation owner with a minimal replay and source-linked invariant. Quarantine affected outcomes and dependent labels, retain diagnostics, repair under a separately authorized engine task and rerun the affected benchmark. AI must not exploit bugs or compensate by altering rules.

Substantial training and evaluations run outside PR CI. Preserve successful covered-shard approval within 18 minutes (1,080 seconds inclusive), timing-only termination strictly after 30 minutes (1,800 seconds), and complete retained results for late passing workloads, which still fail approval. The supervisor includes source history, index construction, mirror, parallel tests and child report finalization; outer cleanup grace is not an approval allowance. Keep twelve shards, the 67% full-package branch-coverage floor, all existing tests/quality requirements and the separate mirror/performance/quality bounds. A future PR still needs the actual-base assessment and serial smoke required by policy, including a documentation PR; this local planning revision does not claim those gates passed.

## 8. Recommendation disposition and review changes

Dispositions apply to the supplied requirements and identifiable claims in the recovered November 5 plans. The separate external evaluation's full original text was not present in this input; no unseen quote or claim is attributed to it.

| Recommendation / claim | Disposition | Treatment |
|---|---|---|
| Engine authority, strict routes, explicit failure | Accepted | Preserve implemented PR2 boundary and ordinary decision authority. |
| Redesign around shared representation rather than compulsory V1 hierarchy | Accepted | Compact shared baseline; goals/hierarchy are measured extensions. |
| A General/Commander enum forces separate models | Rejected | Artifact roles can share one model through explicit interfaces. |
| Explicit candidate generation and coverage | Accepted | Four-stage lifecycle, validated variable-size sets, typed exhaustion and separate generator/ranker metrics. |
| Each rejected internal candidate needs a new live request | Rejected | Internal validation does not commit; only actual protocol retries follow family lifecycle. |
| Eight authoritative retries as a default policy recovery | Rejected | Current strict runner fails committed rejection; first experiment has no retries. |
| Performance/sample efficiency before large self-play | Accepted with scope | Measure real workload; contract and supported local experiments have narrower prerequisites. |
| HTTP timings prove whole-game infeasibility or millions of games are mandatory | Rejected | Historical component evidence cannot quantify that gap. |
| 60-second target is merely aspirational | Rejected | Standing product requirement, unqualified today; preserved with its actual workload/hardware scope. |
| Full-authority fork is sufficient for AI search | Rejected | Separate independent-randomness, visibility and mutable-state boundary required. |
| Every experiment needs a general hidden-state constructor | Rejected | Require only the information model the declared fixture/search needs. |
| All Tactical cards are hidden, or Hidden means secret coordinates | Rejected | Verify phase/pack disclosure; active face-up cards and hidden deck order differ. |
| Win utility replaced by expected VP margin | Rejected | Match outcome primary; margin/scoring auxiliary. |
| PPO, discount per request, universal shallow search depth | Qualified / not selected | Compare data-compatible methods; undiscounted finite-game baseline and budgeted search selected by evidence. |
| Existing TrainingRow fully specifies modern training/replay metadata | Rejected | Preserve its useful core; version minimal typed linkage/target/behavior/scope extensions. |
| Points-only or known-operator update automatically validates old labels | Rejected | Separate initialization, evaluation, transition reuse, re-simulation and deployment. |
| Two certified factions before every learning experiment | Rejected as blanket addition | Preserve actual Core/faction gates and require broader coverage only for broader claims. |
| Human corpus, full-game Daemons readiness or competitive strength already exist | Unverified / not claimed | Verified fixture inventory and explicit readiness/admission gates only. |
| Old phase numbers/counts can be copied from review | Rejected | Registry and maintained roadmap audited; ambiguous subphase mappings remain explicit. |

Original planning revision: verified post-PR2 state; moved performance/data admission earlier; replaced mandatory hierarchy and live-retry assumptions; added candidate, information-safe simulation, learning/provenance and semantic-change contracts; defined a bounded delayed-tradeoff experiment; retained actual gates and targets. Its updated files were this maintained plan, `AI_POLICY_INTERFACE.md`, and the required `performance/change-assessment.json` for publication. That planning revision changed no code, schema, tests, CI, faction data or generated support files.
