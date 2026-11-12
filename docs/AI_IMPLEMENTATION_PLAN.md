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
gates, not completion of Stage 2. Its synthetic Core roster, legacy geometry,
July mission/scoring identity and October layout geometry retain their disclosed
limits. The fixed recipe supplies no training dataset, scoring target or full-game
evidence.

### Bounded Stage 2 candidate/reference measurement

The separate `CanonicalDeploymentCoverage` operator report now reconstructs
all eleven exact prefix states and validates alternatives on independent ordinary
viewer-submission forks. It measures eighteen current finite options across seven
occurrences (all accepted), and a thirteen-offset placement generator across four
occurrences (forty-six accepted of fifty-two). The independently fixed reference
list uses zero, ±1/±2-inch axis translations and one far invalid probe per placement.
Thirty-two of forty reference probes are engine-accepted and now all thirty-two
are generated and accepted. The eight invalid references remain outside the legal
denominator. The predecessor five-offset default missed thirteen accepted
second-ring translations; adding ±2-inch X/Y proposals addresses that demonstrated
class while preserving the original ordered five-candidate prefix and
raw/accepted ceilings.
The coverage interface qualifies every missing direction's geometry and the
terrain, prior-model overlap and edge/zone rejections. These are distinct feasible
wider spatial alternatives; their tactical usefulness remains unmeasured.
Canonical recipe choices
remain positive controls. Closed report reproduction, endpoint rejection and a
nonrecipe accepted placement's persistence/exact replay have focused controls.

These are distinct feasible finite/geometry alternatives, not tactical-value
references. The [coverage interface](AI_POLICY_INTERFACE.md#canonical-candidate-and-reference-alternative-coverage)
defines exact denominators, per-occurrence results, limits and operator-only
evidence. This closes the demonstrated second-cardinal-ring coverage gap; it does
not qualify exhaustive legal placement, the proposed
screen/preserve experiment, ranking quality, redeploy/Scouts, battle or full-game
learning. Original admission and workload/training contracts remain unchanged.

### Bounded Stage 2 component-cost measurement

The standalone `scripts/measure_canonical_deployment_costs.py` measures complete
`CanonicalDeploymentCoverage.measure` and closed `from_payload` reproduction
first, using the frozen canonical endpoint and current authoritative report.
A separate
prepared component pass calls the existing startup, prefix/admission, candidate,
fresh-fork validation, persistence and replay owners; it checks its candidate sets
and validation receipts against the complete report. No timing field enters an
actor view, authoritative state, replay, admission or coverage report. The
[operator procedure](performance/CANONICAL_DEPLOYMENT_COSTS.md) defines exact
timing boundaries, evidence, repetition/cache semantics and hard campaign limits.

These costs qualify only the disclosed frozen setup/deployment fixture and
provisional measurement environment. They neither certify the serial performance
gate nor establish a full-game throughput, tactical-quality or learning result.
Stage 2 remains open for broader useful reference qualification. The retained
five- and nine-offset campaigns are historical; current thirteen-offset measurements retain
their own runtime/workload identities. Further generator expansion or tactical
reference work needs a separately scoped decision and fresh coverage measurement.
The separately pinned order/diagonal suite below broadens feasibility evidence.

### Broader Stage 2 deployment reference suite

The separate `DeploymentReferenceSuite` freezes three ordinary deployment
orders on the same canonical configuration before measuring any outcome. Player
B's scouts remain first; player A uses Deep Strike/scouts/vehicle,
vehicle/scouts/Deep Strike, or scouts/Deep Strike/vehicle. All recipes retain the
same exact formation origins, secondary/reserve choices, source exceptions and
before-redeploy endpoint. The independently declared ten-offset reference list
contains zero, the four two-inch cardinal translations, four one-inch XY
diagonals, and one far invalid control. It is not derived from generated or
accepted candidates.

The suite measures actual occupied-prefix constraints and diagonal geometry
through the shared ordinary submission, fresh-fork and strict replay owners.
Its definition hash, complete accepted traces, per-occurrence candidate/reference
receipts, rejection diagnostics and source/build identities are operator-only.
The [suite interface](AI_POLICY_INTERFACE.md#deployment-order-and-diagonal-reference-suite)
records measured coverage and the precise scope; the existing serial cost
harness's `--reference-suite` mode records complete measurement/reload and
per-case prepared component costs.

The version-two suite accepts 54/54 finite choices and 138/156 generated placements;
it covers all 93 legal placement references, including the 42 previously missed diagonals, with
27 invalid reference probes excluded. All three cases have equal totals, but
scout/Deep Strike order swaps which two-inch Y translation fails friendly
occupancy. The shared generator appends `(1,1), (-1,1), (1,-1), (-1,-1)`
after its original nine offsets, preserving every smaller-budget prefix. The suite
versions its generated budget while retaining the exact reference geometry and
orders. Historical version-one evidence remains unchanged. Three fixed orders in one synthetic fixture are not
representative sampling, tactical usefulness, continuous placement coverage or
Stage 2 completion. Ranking, screen/preserve/follow-through references and
broader workload qualification remain open. No dataset or learning eligibility
changes.

### First reachable preservation prefix

The separate `PreserveScenarioAdmission` extends the unchanged canonical
deployment recipe through ordinary viewer submissions: both players decline
redeploy and Scouts, then player A selects S and Remains Stationary. Seventeen
accepted decisions cover thirteen exact routes and end at the next first-round
Movement unit selection. S is `army-alpha:scout-redeploy-unit`; the separate E
candidate is `army-alpha:deep-strike-unit`, and the opponent candidate is
`army-beta:scout-redeploy-unit`. These are declared design roles, not demonstrated
screening, exploitation or threat reachability.

The pinned definition/configuration, complete accepted trace, engine-enumerated
finite candidates, consumed S activation, unchanged battlefield placement,
automatic Command boundary, strict JSON persistence and exact replay qualify one
reachable preservation **feasibility** prefix. The operator receipt reconciles
required/observed prefix routes separately from missing tactical mechanics and
minimum continuation route obligations. Declining redeploy/Scouts does not
exercise either movement mechanic. The canonical synthetic roster, legacy
geometry, July mission/October layout and fixed public test-seed limits persist.

Useful-reference qualification returns `scoped_gap`, with no target and no
learning eligibility. A witnessed screen/exposure alternative, actual opponent
threat and attack continuation, E follow-through, and matched later scoring or
attack outcomes with a declared horizon remain unmeasured. Missing evidence is
not an engine-unsupported verdict. No tactical advantage, screen/preserve pair,
candidate continuation coverage, component-cost qualification or Stage 2
completion follows from selecting a legal Remain Stationary option. The
[preservation admission interface](AI_POLICY_INTERFACE.md#reachable-preservation-prefix-admission)
defines this boundary; no ranker, learner or training schema is added.

### First witnessed Normal Move alternative

The separate `NormalMoveScenarioAdmission` branches from the preservation
fixture's exact fifteen-decision checkpoint before selecting S. It reuses the
ordinary eleven-decision deployment and four redeploy/Scouts declines, then
selects S, selects Normal Move, and submits a `PathWitness` translating all five
models one inch in negative X with unchanged height and facing. Eighteen accepted
decisions cover fourteen routes and stop at the next Movement unit choice.

The closed operator receipt retains the pinned definition/configuration,
common-prefix checkpoint commitment, complete accepted trace, actual witness and
engine activation evidence, required/observed routes and mechanics, current
source/build identity and strict JSON persistence/exact replay. The original
preservation definition and receipt are unchanged. The existing `normal_move`
adapter family owns validation and mutation; no engine mechanic or training
schema is added.

This demonstrates one legal movement alternative. It does not demonstrate
screening, exposure, tactical value, opponent threat or attacks, E follow-through,
or later comparative outcomes. Those requirements remain `scoped_gap`, with no
reference target or learning eligibility. Missing evidence is not an
engine-unsupported verdict. Candidate continuation coverage, component costs,
broader qualification and Stage 2 completion remain open. See the
[movement admission interface](AI_POLICY_INTERFACE.md#witnessed-normal-move-prefix-admission).

### Paired E movement and first opposing shot probe

`FollowthroughPairAdmission` continues the unchanged stationary and Normal Move
prefixes through five ordinary player-A decisions each. E moves all three models
one inch in negative X using full straight-line `PathWitness` paths; the remaining
vehicle stays stationary. The two traces end after 22 and 23 accepted records at
player B's end-of-Movement Fire Overwatch target-binding request. Ordinary
startup and exact replay verify both branches; their first fifteen records are
identical, under the same configuration, build and seed. This is a matched
movement continuation, not E exploiting an opposing response.

The operator receipt independently forks each endpoint and submits the nominated
B unit as the Overwatch shooter through the existing viewer proposal path.
The engine returns `fire_overwatch_no_legal_shooting_declaration`, with the entire
checkpoint, records and events unchanged. The offered reaction window therefore
does not establish an executable shot. This negative evidence applies to one
shooter at this exact window; it does not establish general threat unreachability
or unsupported shooting mechanics. A control declines the reaction through the
ordinary proposal path and reaches player A's Shooting unit selection.

The [paired interface](AI_POLICY_INTERFACE.md#paired-followthrough-and-opposing-shot-probe)
retains the synthetic roster, provisional geometry, mission/layout and public-seed
limitations. `scoped_gap`, a null target and no learning eligibility remain.
An ordinary approach or a separately admitted geometry that enables a real enemy
attack must precede the opponent-response/E-benefit comparison. Screening,
attack resolution, E's benefit after that response, declared-horizon outcomes,
timing/cooperation controls, useful candidate coverage and scenario costs remain
open. The unchanged original admissions keep their narrower meanings; Stage 2
is not complete.

Canonical coverage receipt loading now rejects totals that contradict its own
row counts through shared pure aggregation before repeating engine work. Every
internally consistent receipt still requires complete fresh reproduction and
exact equality; coordinated false rows/totals remain rejected. This bounded
operator-boundary optimization preserves the original full coverage regression
and adds a separate real reproduction control. It does not qualify Stage 2,
scenario costs or hosted timing; matched actual-base evidence is recorded
separately from final CI approval.

### Opposing shooter diagnosis and one reachable attack

The separate `OpposingShooterQualification` compares both original 22/23-record
endpoints to fresh ordinary reproduction. Shared shooter eligibility, complete
equipped weapon profiles, per-model target candidates and independent living-model
range/visibility queries explain the negative Overwatch result: B is eligible,
all A targets are outside its rifles' 24-inch range, and E is visible at both
endpoints. Range-short-circuited candidate payloads are not negative LOS evidence.

A fixed stationary-branch continuation now supplies one ordinary opposing attack
witness. B approaches via three fully witnessed Normal Moves, then uses model
`:003`'s rifle against E in round-three Normal shooting. A Remains Stationary,
skips shooting and declines reactions; both players decline their Command
Re-Rolls, and A selects E model `:001` at the damage-allocation request. The 65-record
endpoint includes two engine-generated target/group selections. The immutable
operator report retains accepted records, observation commitments, actual attack
events and current source/build-bound startup/persistence/replay evidence, leaving
both original supplied checkpoints unchanged. The report supports JSON export,
not serialized-evidence admission or a learning consumer.

This closes one attack-feasibility gap, not the paired opponent-response/E-benefit
experiment. The historical FollowthroughPairAdmission remains unchanged. Tactical
screening/exposure, comparative outcomes, timing/cooperation controls, useful
candidate coverage and scenario costs remain open, with the inherited synthetic
roster/geometry/mission/points/seed limitations. Stage 2 remains incomplete,
`reference_target` remains null and learning remains excluded. See the
[qualification interface](AI_POLICY_INTERFACE.md#opposing-shooter-qualification).

### Matched opposing attack at a common local horizon

`MatchedAttackComparison` now extends both exact followthrough endpoints with the
unchanged opposing-shooter approach and attack recipe. Fresh ordinary reproduction
rejects configuration, endpoint and record-count drift before continuation, and
leaves both caller sessions unchanged. The stationary and moved branches reach
65 and 66 accepted records respectively, at the same round-four player-A Movement
unit-selection boundary. Both final prefixes retain verified ordinary startup,
strict persistence and exact replay evidence in a separate export-only report.

The report compares actual semantic choices and movement paths across branches,
including six A Remain Stationary choices, five skipped Shooting phases, six
declined movement reaction windows, four B hit/wound Command Re-Roll declines,
one A armour-save Command Re-Roll decline and the same E model allocation. B
approaches in rounds one through three and attacks with the same rifle in round
three. Before/attack/final boundaries and the full accepted traces expose those
cooperation and timing controls; they do not constitute adversarial or alternative
timing policies.

E has identical positions and three surviving models with two wounds each in both
branches before and after the attack. The measured wound loss and matched outcome
differences are zero. This closes one bounded matched-response/horizon evidence
gap, without demonstrating screening, exposure or a useful E benefit. Alternative
timing/cooperation policies, useful candidate coverage and scenario costs remain
open. Historical followthrough and single-branch qualification definitions,
implementations and tests retain their meanings. The inherited synthetic fixture
exceptions, `scoped_gap`, null target, learning exclusion and incomplete Stage 2
status remain. See the [comparison interface](AI_POLICY_INTERFACE.md#matched-opposing-attack-comparison).

### Bounded E attack and no-follow-through control

A bounded operator experiment starts at the unchanged matched comparison's exact
65/66-record round-four player-A Movement endpoints. A stationary E attempt
reaches no shooting declaration with its equipped 18-inch drop carbine. That
negative opportunity is retained before the attack experiment; it is not an
attack loss or evidence that E can never attack.

The revised continuation is declared before resolving any E attack: all three E
models make the same six-inch negative-Y Normal Move with full straight-line
`PathWitness` paths and unchanged height/facing. S and the vehicle Remain
Stationary, and B declines the movement reaction. The follow-through arm uses E
model `:001`'s equipped drop carbine in round-four Normal shooting against B's
unit; the control completes A's Shooting phase without an attack after the same
movement. All Command Re-Rolls are declined; B allocates to the first living model
offered by the engine. The stopping boundary is round-four player-B Movement's
`select_movement_unit`, before B moves. Outcomes are E/B wounds, living models,
positions, actual attack events and the victory-point ledgers at that horizon.
The original public fixture seed is fixed, with no seed search or outcome filter.

Both E attacks are legal and complete. All four final prefixes pass ordinary
startup, strict persistence and exact replay at the declared horizon:

| Historical S branch | E follow-through records | Omission records | B wounds lost, attack / omission |
|---|---:|---:|---:|
| Stationary | 85 | 74 | 1 / 0 |
| Normal Move | 87 | 75 | 0 / 0 |

E retains three living models and six wounds in every arm; B retains five models,
with nine wounds in the stationary follow-through arm and ten in the other three.
All E models finish six inches in negative Y, with matched poses across the arms;
B's poses are unchanged. A remains at zero VP and B goes from three to seven VP
in every arm, so the attack-versus-omission VP difference is zero. Each attack arm
adds one completed attack sequence; omission adds none. Wound and living-model
differences include the moved branch's zero result and the stationary branch's
one B wound loss. The historical branches have different starting RNG states
despite the common configured seed. Their damage difference cannot be attributed
to S or described as screening benefit; each omission control starts from its
own unchanged matched endpoint.

This is an operator experiment outside the packaged runtime and admission APIs.
Its retained harness and raw reports remain separate from the historical
admissions. The [operator evidence contract](AI_POLICY_INTERFACE.md#bounded-e-attack-operator-evidence)
keeps startup, persistence, replay and visibility checks, explicit incomplete
results and the inherited fixture limits. Screening, adversarial timing and
cooperation, useful candidate coverage, scenario costs, held-out outcomes,
Stage 2 completion and learning remain unqualified. `scoped_gap`, a null reference
target and learning exclusion remain mandatory.

### Rule-grounded edge-column access contrast

A separate operator experiment, `stage2-edge-column-access-v4`, keeps
`canonical_deployment_config()` and its original seed unchanged. It changes only
the ordinary deployment proposals for S and B: five-model columns at X=1 inch,
with Y=45+1.8i for S and Y=3+1.8i for B, for i=0 through 4. E and the vehicle
retain their canonical placements. The eleven setup choices and four
redeploy/prebattle declines reach a common fifteen-record checkpoint. These
placements do not change or extend any historical canonical admission.

The screen arm moves S six inches in negative Y in each of A's first three
Movement phases; preservation leaves S stationary. E and the vehicle remain
stationary. B moves six inches in positive Y in rounds one and two. Both sides
skip Shooting, complete offered Charge phases without charging and decline
offered movement/Heroic Intervention reactions. All moves use full straight-line
`PathWitness` paths from observed poses, front models first in the direction of
travel, with unchanged height and facing. At round-three B Movement, independent
forks attempt the same six-inch and two-inch positive-Y paths. The main arms
instead attempt the same one-inch response and stop before A's subsequent
Movement reaction choice.

The final declaration's byte SHA-256 is
`784db3767e55766ddb1c0c280f8cdf27d91f508711b4cba1ab116e069ab36aec`,
pinned before the first access probe. Earlier attempts are retained: a rear-first
B witness was rejected for friendly endpoint overlap; explicit Charge and Heroic
Intervention requests stopped later harness assumptions before any access probe.
The final recipe reuses the strictly restored ordinary prefix. Source review,
before probing access, retained the originally intended two-inch response as a
probe and declared a one-inch matched response because this fixture uses a
two-inch Engagement Range. An operator assertion expecting a raw source ID in a
viewer capability field also stopped before a decline; correcting it changed no
geometry, seed, authoritative state or declared choice.

The retained source obligations are sequential model movement (03.01),
Engagement Range (03.04), and Normal Move start/end eligibility and distance
(09.05), with the same maintained-mirror provenance limitations as their source
ledgers. This is not a new official-source certification. The shared movement
validator owns every acceptance or typed rejection; a transit diagnostic alone
is not substituted for the retained Normal Move endpoint obligation.

The same six-inch and two-inch B witnesses are accepted in preservation and
rejected against the screen. The screen diagnostics are respectively
`enemy_engagement_range_transit_forbidden` and
`enemy_engagement_range_end_forbidden`. The six-inch endpoint would also
overlap/engage S; the two-inch endpoint has a computed 1.540157-inch opposing
base-edge gap, inside this fixture's two-inch Engagement Range. Thus the access
finding does not depend solely on a transit restriction.

Both one-inch main responses are accepted, reaching the declared round-three B
Movement reaction boundary after 58 screen-arm records and 52 preservation-arm
records. The same B witness ends at Y=16 through 23.2 inches in both arms; its
nearest opposing base-edge gap in the screen arm is 2.540157 inches. All six
complete histories pass ordinary-startup verification, strict persistence, exact
replay and both-viewer persistence equality, including the rejected attempts and
their fresh retry requests. Probes leave their original main checkpoints
unchanged. S and B each retain five models/ten wounds, E three/six, and the
vehicle one/twelve; neither arm loses material. Both VP ledgers remain zero.
Natural RNG-state hashes differ between arms and are retained without replacement;
no matched future-chance schedule or stochastic benefit is inferred. The final
operator execution took 779.33 seconds including repeated startup, restoration
and replay; this is not gameplay throughput or scenario-cost certification.

This qualifies one specific path-access question, not exhaustive route denial,
a useful sacrifice, E follow-through, tactical superiority or an outcome target.
That experiment leaves charges, intervention, detours, alternative timings/opponents
and held-out geometry unmeasured; the bounded response extension below adds one
detour and declaration-eligibility observations. Historical preservation, Normal Move,
followthrough, opposing attack and bounded E-attack evidence retain their
original meanings. The synthetic roster, provisional geometry, mixed mission/
layout, partial points and public seed limitations remain. Operator diagnostics
stay outside actor/scorer inputs, with `scoped_gap`, a null reference target and
no learning eligibility. Stage 2 remains open.

### Bounded opposing responses to the edge-column screen

`stage2-bounded-screen-responses-v1` preserves the edge-column setup, original canonical
configuration/seed and ordinary round-three B Movement origins. Before probing, it declares the
existing six-, two-and one-inch positive-Y controls, one rightward detour and one approach
toward S. The detour moves every B model four inches in positive X, then two inches in positive
Y; the approach moves every B model 1.4 inches in positive Y. All five models use complete
interpolated `PathWitness` legs, descending initial Y, unchanged height/facing and no more than
their native six-inch movement allowance. Each response uses an independent ordinary-session
fork and leaves its origin unchanged. The declaration-byte SHA-256 is
`6ed8aca07220e509948c5d0953d2d9cd06fa9689cbec2ece22ed5c3097ffb16c`.

| Identical B witness in each position | Screen | Preservation |
|---|---|---|
| Six inches forward, retained control | Transit Engagement Range rejection | Accepted |
| Two inches forward, retained control | Endpoint Engagement Range rejection | Accepted |
| One inch forward, retained control | Accepted | Accepted |
| Four inches right, then two forward | Accepted | Accepted |
| 1.4 inches toward S | Accepted | Accepted |

The detour reaches X=5, Y=17 through 24.2 inches; its nearest S base-edge gap is 3.622780 inches
in the screen position. It gains the same Y depth as the rejected two-inch direct path but does
not pass the entire S column. The straight approach reaches X=1, Y=16.4 through 23.6, leaving a
2.140157-inch gap. Both remain outside the retained two-inch Engagement Range; neither is an
engagement or charge move.

The one-inch control, detour and approach continue by declining A's movement reaction, skipping
B's Shooting and observing actual charge-declaration options. Charges and offered Heroic
Intervention windows are then declined. All six continuations stop at round-four A Movement's
`select_movement_unit`, after 62/54 records in screen/preservation. The shared charge owner
reports S within twelve inches in each screen continuation and B is actually offered as a
charging unit. E and the vehicle are out of declaration range. In preservation all three
opposing units are out of range and B is not offered a charge. This qualifies declaration
eligibility only: no Charge roll, target selection, charge-move witness, successful engagement
or Fight is tested.

The detour's turn-end objective observation is retained: B receives three VP after the detour in
both positions for the same new-objective turn-end Primary rule; A remains at zero. The one-inch
control and 1.4-inch approach leave both ledgers at zero in both positions. The paired screen-minus-preservation VP difference is zero for all three responses. These local observations do
not attribute an advantage to S or qualify a useful sacrifice. No model or wound is lost: S/B
retain five models/ten wounds each, E three/six and the vehicle one/twelve. B's response
witnesses and resulting poses match between screen/preservation for every accepted paired
response. Natural RNG hashes remain unmodified and differ between positions; no shared future-chance schedule or stochastic attribution is claimed.

All ten complete response histories retain ordinary-startup verification, strict persistence,
exact replay and both-viewer projection/event round trips, including the two rejected attempts
and their retry requests. An initial operator harness stopped after an accepted one-inch move
and reaction decline because it referenced a nonexistent lifecycle registry attribute. The
correction reads the engine's loaded charge-restriction registry; its failed attempt is retained
and the two already verified controls are reused. The declaration, engine, seed, geometry and
authoritative checkpoints were not changed to obtain a result.

Sequential movement (03.01), Engagement Range (03.04), Normal Move (09.05) and charge-declaration eligibility (11.02) use their retained maintained mirror source ledgers, with no new
official-App certification. Charge-move obligations (11.04) remain unqualified here. The
inherited synthetic roster, provisional geometry, mixed mission/layout, partial points and
public seed limitations remain. This is a finite response set, not exhaustive denial, a best
response or tactical benefit. Historical admissions retain their meanings; useful-reference
status remains `scoped_gap`, the reference target is null, learning is excluded and Stage 2 is
open.

### Bounded natural charge attempt against the edge-column screen

`stage2-bounded-screen-charge-v1` reproduces the unchanged configuration/seed and
ordinary 1.4-inch approach above. The screen arm reaches B's round-three
`select_charging_unit` after 60 records, with S at a 2.140157-inch base-edge gap.
The comparison forks this same checkpoint before choosing B versus completing
Charge. Preservation is a separate no-charge-eligibility control; it does not
invent a declaration when the engine offers none. Declaration-byte SHA-256 is
`61bdb6e681cf0a94e248c3ffd78865a8205ebc10c18dadf5e9bccb7b5848a5dc`.

The declaration fixes declines for optional reactions and rerolls. The ordinary
sequence selects B, rolls physical 2D6, declines the offered Command Re-roll,
selects S alone from the post-roll target request, then reaches the movement
proposal. The natural dice are 6 and 3, giving nine inches without modifiers or
rerolls. The saved 63-record checkpoint is an ordinary reachable post-roll,
selected-target state; it is not a completed Charge Move.

The bounded witness procedure starts with a full 1.640157-inch positive-Y path
for every B model, front to back, leaving a half-inch nearest gap if accepted.
It permits at most six pure native evaluations and replaces only the first
execution-ordered model path with a native preferred-distance or engagement
alternative when available. The first evaluation returns
`charge_reachability_unresolved`: the front model satisfies both endpoint goals,
but preferred-distance queries for the other four models remain unresolved.
An unresolved mandatory query is not an impossibility proof or an exemption.

The operator's second composition incorrectly used `PathWitness.model_ids()`,
the sorted inventory, instead of `model_paths`, the physical execution order.
Its `end_on_model_overlap` results and subsequent accepted optional no-move
history at 65 records are retained as harness diagnostics, not the declared
procedure's result. A corrected fork restores the same 63-record checkpoint,
reuses the completed first evaluation and counts the faulty second call against
the six-call ceiling. Its third evaluation preserves descending-Y order but
does not finish within the original experiment allowance. The diagnostic watchdog stops the process
at its reconstructed original deadline with checkpoint, query input and diagnostics retained.
WSL reset its uptime between processes; the continuing deadline is reconstructed
from the retained first exit receipt and wall time. This is diagnostic timing,
with polling/timestamp uncertainty, not a certified monotonic performance gate.

No corrected charge witness is submitted or accepted. The qualified endpoint
remains the 63-record pending proposal, with no engagement, displacement, Fights
First grant or Fight. The direct-decline branch and preservation control reach
round-four A Movement after 62 and 54 records. The pending charge and both
controls pass ordinary-startup verification, strict persistence, exact replay,
and both-viewer projection/event equality; private RNG seed data is absent from
those views and streams. No authoritative checkpoint or RNG state is patched.
All retain S/B at five models and ten wounds, E at three/six and the vehicle at
one/twelve. The unresolved charge and completed controls are different horizons,
so they do not supply a common-horizon tactical outcome label.

This qualifies roll/target ordering and a persistent pending-charge boundary,
plus the specific witness prerequisites above. It does not establish that a
legal charge is impossible, a best response, a useful screen, sacrifice value,
E benefit, full-game performance or learning eligibility. The retained 03.01,
03.04, 09.05, 11.02 and 11.04 source obligations keep their maintained-mirror
provenance limits; successful 11.04 execution in this experiment remains open.
The inherited synthetic roster, provisional geometry, mixed mission/layout,
partial points and public seed limitations remain. Historical admissions retain
their meanings; `scoped_gap`, null reference target, learning exclusion and open
Stage 2 status are unchanged.

### Charge reachability diagnosis and next optimization boundary

The retained #668 diagnostics reproduce the exact 63-record post-roll/selected-S
checkpoint and corrected third witness. Only model 004 changes using evaluation
one's native alternative; physical execution remains 005, 004, 003, 002, 001.
The saved checkpoint's canonical digest remains
`8b44eb8572d1d8cb433784a062fa22da95c36326b7a0f801cb422d83fbba9c7f`;
the corrected witness digest is
`1eae6ce43b769b61a2875092c0b3aea95fc9c0dedf867448301468af41ea42cc`.
Original completed evaluation one, faulty ordering evaluation two and the
original censored evaluation three retain their meanings and bytes. Their
overall experiment allowance never measured a single query's duration.

The operator-only `profile_charge.py` retained with the local diagnostics accepts
`--inputs`, `--output` and optional `--profile`; run it from the unchanged
repository with locked CPython 3.14.5 and `PYTHONPATH=src`. Inputs are the saved
checkpoint, corrected progress, both earlier candidate records and the pending
replay/result, copied from the retained archive. It reconstructs and compares the
exact witness, restores without patching authority, replays ordinarily, then
calls the native resolver once. A fresh supervisor monotonic clock covers the
whole observation and terminates its owned process group only beyond 1,800
seconds. Thirty-second progress/self-stack records and optional in-process
`cProfile` stay outside engine records and player observations. No elevated
inspection or failed #668 profiler retry occurs.

This single instrumented observation uses the unchanged runtime build, geometry,
seed, nine-inch budget and selected target. Imports take 5.306 seconds, strict
restore 43.770 seconds and separate replay 24.940 seconds. Restore itself also
verifies history; neither preparatory stage is witness-evaluation time. Replay
reproduces 63 decisions and 641 events. The native evaluation starts at elapsed
74.195 seconds. Its searched mandatory queries are individually delimited:

| Model / goal | Instrumented query seconds | Native result |
|---|---:|---|
| 001 preferred distance | 54.454 | `unresolved`, 20 explored nodes |
| 001 engagement | 153.476 | `reachable`, 25 explored nodes |
| 002 preferred distance | at least 260.511 observed | operator-censored; no answer |

After sufficient owner evidence, the operator stops the observation at 544.147
supervisor seconds. Exit 143, no timeout and clean process-group cleanup are
retained. This is an intentional early stop, not execution-limit exhaustion or a
completed witness result. The evaluation has 469.073 observed seconds; remaining
mandatory queries are unmeasured. Completed query answers cannot resolve the
whole witness. No movement is submitted. Saved input bytes remain unchanged;
post-interruption equality of the in-memory session was not measured.

The profile attributes 459.077 inclusive seconds to 24,881 `_validated_witness`
calls. `TerrainPathLegalityContext.validate` accounts for 345.274 inclusive
seconds across 12,227 calls, including 244.579 seconds in 1,733,059 terrain-volume
segment checks. Inclusive times overlap and must not be added. Navigation graph
construction takes only 0.095 seconds for three graphs, with 1,850/1,850/2,230
poses. Progress counters and CPU time continue increasing. Three distinct full
query keys start; two complete and enter the bounded cache with zero hits. This
is observed combinatorial edge/path validation and repeated terrain/sample work,
not evidence of repeated identical full queries or a stalled solver. The graph
owner revalidates complete growing prefixes for outgoing candidates; this code
path identifies repeated work but does not measure an exact duplicate-path rate.

The next focused optimization belongs to `geometry/movement_reachability.py`
and `geometry/pathing.py`, especially terrain validation of search paths. Assess
prepared immutable terrain/footprint data and conservative candidate pruning or
prefix reuse against these same inputs. Preserve full path, physical order,
body/terrain/support/coherency/endpoint obligations, bounded caches and typed
unresolved results; require matched base/head work counts, semantic equivalence,
cache isolation and the existing delivery gates. No runtime fix is established
by this profile, and no budget increase or smaller search replaces legality.

The shared terrain owner now prepares feature volumes once per validation and
extracts sampled model footprints into `geometry/terrain_path_preparation.py`.
Footprints and their actual geometry bounds are prepared lazily once per sample;
strictly separated bounds avoid an intersection call, while touching bounds still
run the original predicate. The object lives only for that complete validation.
Growing prefixes, physical execution order, dense-floor/body/climbing/support and
mandatory endpoint checks, the 128-node search ceiling and full-query cache keys
remain unchanged. New differential, boundary, work-count and context-isolation
controls compare complete results with direct intersections.

On the same provisional Threadripper host and locked CPython 3.14.5, the frozen
first query pair from the unchanged checkpoint/corrected witness has three serial
samples per arm, without coverage, profiling or competing test workers. Only the
geometry/reachability caches named by the retained operator harness are cleared
before each sample; imports, restore and replay are outside query timing.

| Query | Base seconds | Prepared seconds | Base / prepared median | Base / prepared mean |
|---|---|---|---|---|
| 001 preferred | 40.911 / 19.203 / 19.230 | 32.730 / 11.877 / 11.862 | 19.230 / 11.877 | 26.448 / 18.823 |
| 001 engagement | 76.650 / 67.122 / 67.109 | 45.339 / 36.104 / 35.836 | 67.122 / 36.104 | 70.294 / 39.093 |

All preferred results remain unresolved at 20 explored nodes. All engagement
results remain reachable at 25 nodes with the exact same complete witness, which
is revalidated outside timing. Every sample, including the higher first samples,
is retained. Exact saved-checkpoint restoration, ordinary replay of 63 decisions
and 641 events, original physical witness order and post-query checkpoint equality
also hold in both arms. No movement is submitted. These finite component results
leave the remaining mandatory queries, a completed legal charge, tactical benefit,
Stage 2 admission and complete-game throughput unqualified. The task-retained
`measure_saved_queries.py` and `benchmark_pair.py` reproduce these distinct timing
and restore/replay boundaries; the original instrumented profile remains history.

These are one profiled local observation's costs, not uninstrumented latency,
a speedup, a full-game throughput measurement or a tactical outcome. The legal
Charge Move, common horizon and Stage 2 useful-reference qualification remain
open; `scoped_gap`, null target, learning exclusion and source/roster/provisional
geometry/mission/points/public-seed limits persist. Preserve the original local
archive without deleting or uploading it. Optimize this measured owner before
extending the tactical scenario.

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

Substantial training and evaluations run outside PR CI. Preserve successful covered-shard approval within 27 minutes (1,620 seconds inclusive), timing-only termination strictly after 30 minutes (1,800 seconds), and complete retained results for late passing workloads, which still fail approval. The supervisor includes source history, index construction, mirror, parallel tests and child report finalization; outer cleanup grace is not an approval allowance. Keep twelve shards, the 67% full-package branch-coverage floor, all existing tests/quality requirements and the separate mirror/performance/quality bounds. A future PR still needs the actual-base assessment and serial smoke required by policy, including a documentation PR; this local planning revision does not claim those gates passed.

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
