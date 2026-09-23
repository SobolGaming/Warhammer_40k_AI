# Order 78 / P13A — Gone to Ground outside dense terrain

Reviewed main: `f14e288cf9be9830161aa4c71e5d24d64903197e`.
Review date: 2026-09-23, America/New_York.
P13A status: **implemented and locally validated**; final delivery gates are recorded below.
PFINAL status: **blocked before complete 25-category certification**. CAUDIT-01
remains open. This is a bounded preflight finding, not a complete clause/FAQ
inventory or a snapshot-wide compliance certificate.

At preflight, remote main matched the checkout. Order 77, PR #497, merged at
`2026-09-23T14:04:05Z`; the remote open-PR inventory was empty. Orders 73–77
are present in this main. Their earlier unmerged delivery notes are historical.

## Approved implementation

The owner approved this prerequisite on September 23. C13-01 is repaired in the
shared Hidden detection owner. The historical preflight below remains evidence
of the base defect and the required scope pause; its JSON is immutable and does
not claim that the later implementation was already authorized at observation time.

The repair removes the occupancy precondition and selects only causal Dense
**feature** blockers from the continuous visibility witness. An obscuring area
alone cannot establish feature concealment. Ordinary Light/Dense terrain Hidden
eligibility, exact geometry, effect grants, detection bounds and the shared
current/previous-turn shooting history remain their existing owners.

The complete 13.11.01 transcription, including the Designer's Note, is retained in
`core_gone_to_ground_2026_09/artifacts/package.json`. Its typed eager loader pins
the artifact bytes and validates the registered provider/policy/observation tuple.
The source registry records the actual unversioned September 23 observation;
the official PDF remains historical provenance. The offline generator is
`tools/build_core_gone_to_ground_source.py`. No named handler is introduced.

`tests/unit/test_order78_gone_to_ground.py` covers both shared consumers, attached
rules-unit effects, per-model protection, Light-area and granted Hidden, dense
occupancy independence, full visibility, Light-only/area-only/model obstruction,
first/current/previous/old turn shooting history, detection bounds and cache reuse.
Ordinary Shooting and actual phase-end Fire Overwatch enter through the facade,
reject malformed/stale/protected declarations without consuming the pending
request, accept a valid retry, restore JSON persistence for both viewers and event
streams, and exactly replay. Source-granted Hidden is an initialized typed effect;
this does not certify a particular faction's grant. Light-area placement is a
shared-query fixture, not a certification of the mission-layout editor.

The source-to-clause regression map is
[order78-runtime-consumer-proof-v1.json](../data/source_audits/order78-runtime-consumer-proof-v1.json).
The existing adapter contract covers the unchanged finite and parameterized
payloads; its Gone to Ground description now states the corrected condition.
Contract 34 remains current; engine identity and generated examples are refreshed.

Scope audit: two existing gameplay modules, one source package/registry entry,
source generator, focused tests, source proofs, contract artifacts and delivery
evidence. No geometry algorithm, architecture boundary, faction handler or new
player choice changes. Final gate evidence is recorded in
[validation.json](performance/order78/validation.json); matched component results
and their limitations are in [performance notes](performance/order78/README.md).
C13-01's prerequisite can merge independently. CAUDIT-01 and PFINAL remain open.

Final validation: 8,994 behavioral tests pass with 85.20% coverage; 602 code-quality
tests pass. Lint, type checks, import boundaries, source generators, exact-base
contract checks, installed-wheel smoke, TypeScript checks/conformance, the updated
eight-shard inventory and pre-commit all pass. Failed inventory/evidence gate
attempts and their corrections are retained in the validation record. No
production changes followed the first aggregate behavioral run.

## C13-01 — concealment incorrectly requires dense-terrain occupancy

The invariant is that Gone to Ground depends on a model being Hidden, not fully
visible because of intervening dense terrain features, and its unit not having
made ranged attacks in the current or previous turn. Core 13.11.01 does not
add a requirement that the target occupy dense terrain. A qualifying model's
detection range is reduced by three inches.

The shared `hidden_detection._target_model_has_gone_to_ground_against_attacker`
returns false immediately when `model_within_solid_terrain` is false. This
confuses the source's intervening concealment condition with occupancy. It
allows attacks against qualifying Hidden targets between 12 and 15 inches away.

The executable probe uses real one-model canonical units, a physically
intervening dense ruin with an explicit wall and ground floor, normal Core
detection parameters, and the ordinary `LocalGameSession` shooting submission.
The target is 13.04015748031496 inches from the attacking model's base. The
continuous visibility witness proves that it is visible but not fully visible;
the only blockers are the dense ruin and its wall. Neither model occupies that
ruin in the counterexample. No solver timeout or unresolved result occurs.

The fixture establishes Hidden using the existing typed `unit_hidden`
persisting effect before the replay root. It does not certify a faction ability
that grants that effect. It neither substitutes a controller/validator/service
nor imports a test module. Terrain-derived Hidden in a light area is an
additional source-traced affected case, not an independently executed facade
case in this preflight.

| Executed case | Dense occupancy | Hidden | Shared LOS / target accepted |
| --- | --- | --- | --- |
| Intervening dense ruin, target outside | No | Yes | Yes — incorrect; effective detection should be 12 inches |
| Same wall, enlarged dense footprint includes target | Yes | Yes | No — `outside_detection_range` |
| Intervening feature classified Light | No | Yes | Yes — correct control |
| Intervening dense ruin, target not Hidden | No | No | Yes — correct control |

The first case also selects the shooter and Normal Shooting through finite
options, submits its declaration through the parameterized facade, and records
`shooting_declaration_accepted`. JSON persistence restores it, both viewer
projections match after restore, and exact replay reproduces the accepted
attack. These successes authenticate the reproduction; they do not certify
the incorrect rule result. The replay begins at an initialized Shooting-phase
fixture, not at game initialization.

The four-case preflight command, run before the repair, was:

```sh
UV_CACHE_DIR=/private/tmp/order78-uv-cache PYTHONPATH=. \
  uv run --no-sync python reports/order78/probe_gone_to_ground.py
```

The probe and full output remain local under `reports/order78/`. Their hashes,
compact results, and source observation are retained in
[preflight.json](performance/order78/preflight.json). The probe asserts the
observed red state; it is not a passing compliance test.

## Source evidence and audit limits

The complete 13.11.01 body, including its Designer's Note, was read in the
expanded browser section at
[40k.app Terrain](https://www.40k.app/rules/13-terrain) on September 23.
Core 13.09 and 13.09.01 separately establish Light/Dense terrain Hidden and the
first-turn treatment of previous-turn shooting. The non-affiliated provider
exposes no App-data version. The preflight JSON pins the normalized 13.11.01
operative transcription and its observation metadata with separate SHA-256
hashes. It assigns a preflight source identity without registering a runtime
source package or changing historical observations.

The source-policy owner remains
`core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`.
Game Datamissions' changelog exposes v946, dated September 2, with the 18.04.01
addition. That observation does not provide a co-versioned 13.11.01 comparison.
No mirror disagreement or official-App exception was observed. The retained
official Core Rules PDF and its hash remain historical provenance.

Category 07's body and expanded 07.02.01/07.02.02 were also read. No complete
source-to-consumer certification of category 07, category 13, or the other
categories is claimed. No controlling all-category snapshot has been selected.
The full clause/FAQ inventory, v931/v946 and September 10 closure proofs,
cross-category audit, and CAUDIT-01 closure remain outstanding.

## Owning path and same-class audit

`LocalGameSession.submit_parameterized_payload` -> engine Shooting declaration
validation -> `shooting_target_candidate_for_model` -> shared Hidden detection
-> continuous visibility/causal blocker evidence -> accepted attack pools.
The broader `unit_has_line_of_sight_to_target` consumes the same Hidden
detection helper and independently returns the incorrect visible result in
the probe.

- `hidden_detection.py` is the single Gone to Ground decision owner. The
  occupancy helper has no other production caller. Repair the rule at that
  shared owner; changing only Shooting declaration validation would leave the
  common visibility query incorrect.
- `shooting_targets.py` has both consumers of Hidden detection: attack-target
  candidates and the general line-of-sight query. Reaction/Overwatch targeting,
  Stratagem geometry, generic selected-target rules, and mission visibility
  consumers use these shared surfaces. These additional callers are
  source-traced; independent facade execution is established for ordinary
  Shooting only.
- `terrain_hidden.py` separately owns ordinary Hidden eligibility. Its
  Light/Dense occupancy requirement belongs to 13.09 and must remain distinct
  from Gone to Ground. `game_state` owns current/previous-turn ranged history.
- The current causal blocker predicate also accepts classified terrain-area
  records. The repair must audit the source distinction between intervening
  dense **features** and an obscuring **area**; this preflight does not assert
  a separately reproduced area-only false positive.
- Existing regressions cover dense occupancy, full visibility, Light-only
  obstruction and recent shooting. Five focused tests pass, but do not cover
  a qualifying target outside dense terrain. Exact visibility, keyword
  canonicalization, general terrain placement and unrelated faction semantics
  are outside this prerequisite's scope.

## Proposed prerequisite and acceptance

Assign **C13-01 / P13A** as Order 78; PFINAL moves to Order 79. At the preflight pause, runtime
implementation awaited owner approval because it materially expanded the
requested audit/certification PR into gameplay remediation.

1. Retain a reviewed, registered, exact 13.11.01 source row and its complete
   provider/transcription/observation tuple. Preserve existing source artifacts
   and distinguish load support from semantic execution.
2. Add a failing regression before repairing the shared Gone to Ground owner.
   Use the existing typed Hidden source/effect and continuous causal visibility
   surfaces. Do not add a named handler or weaken unresolved geometry handling.
3. Cover outside/inside dense occupancy, terrain-derived and granted Hidden,
   full visibility, Light-only and non-terrain obstruction, the causal
   feature/area distinction, recent shooting despite retained Hidden, first
   turn, and detection bounds. Cover per-model and attached-unit ownership.
4. Prove both shared consumers, ordinary and reaction shooting, finite and
   parameterized facade paths, invalid/retry behavior, deterministic JSON-safe
   records, viewer projections/deltas, persistence, and exact replay. Confirm
   whether the existing adapter contract covers the unchanged payloads.
5. Assess the extra visibility queries on matched base/head workloads, preserve
   cache correctness, regenerate required runtime/contract artifacts and shard
   manifests if test files change, and run the required final and CI gates.

Merge P13A before restarting the complete PFINAL audit from current main.
The original preflight record did not authorize runtime or source-registry
changes. The subsequent owner approval above authorizes this prerequisite; no
source interpretation exception or final compliance claim is made.

## Complete-game performance assessment

The repository search found the single-decision headless adapter and gameplay
slice fixtures, but no representative legal complete-game driver or committed
complete-game recording. Pairing certification starts at a seeded round-two
Fight boundary. The capability manifest still reports
`certified_full_game_evidence_missing`.

Complete games attempted/completed: **0/0**. Per-game samples, arithmetic mean
and maximum are absent. The below-60-second mean / at-most-300-second observed
maximum targets remain **uncertified**. Missing evidence includes a versioned
legal workload with rosters, terrain, seeds and decision policy, normal
initialization-to-completion plus replay output, and Order 74's continuous
terrain solver. Provisional host: Apple M5 Pro, 18 logical CPUs, 64 GiB RAM.
The four probes and five existing regressions are not full-game measurements.
No new driver, AI, training, or solver optimization was introduced.

## Validation at the pause

The four-case probe reproduces the failure and passes its diagnostic assertions.
Five focused existing tests pass in 3.02 seconds without coverage. The final
preflight JSON records the roadmap/source-generator, shard, formatting and
diff checks. No collected behavioral file or runtime identity changed.

The aggregate behavioral/coverage suite, complete code-quality suite, type
checks and publication gates have not run at this preflight pause. No PR was
opened. AGENTS.md requires a pause before material scope expansion, and the
roadmap explicitly says: "If the audit discovers any gap, do not open or certify
PFINAL."
