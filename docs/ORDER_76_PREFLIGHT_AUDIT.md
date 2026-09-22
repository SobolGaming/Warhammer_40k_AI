# Order 76 / P03D — proposal rejection replay repair and preflight

P03D implements the owner-approved C03-04 prerequisite below. PFINAL is now
Order 77. The initial preflight is retained as historical evidence; the
implementation and final validation follow it.

Reviewed main: `f96d235db3de236531a089fa2d95b8c20baaa418`.
Review date: 2026-09-22, America/New_York.
Initial preflight status: **blocked before complete 25-category certification**. CAUDIT-01
remains open. This record is a bounded preflight, not the complete clause/FAQ
inventory or an all-category compliance certificate.

Local and remote main agree. Order 75, PR #495, merged at
`2026-09-22T15:47:33Z`; the remote open-PR inventory was empty. Orders 73–75
are present in main. Historical descriptions of those PRs as unmerged are
stale delivery metadata.

## C03-04 — physical-proposal prevalidation breaks replay and recovery

The required invariant is that malformed or drifted physical proposals return
typed diagnostics before queue consumption and decision recording, while the
authoritative event history remains exactly reproducible and recoverable.
The finding spans movement/placement proposal ingress, including categories
11 and 21. It does not change movement legality or source wording.

The preflight confirmed both observations retained by Order 75 and reproduced
the event-history failure independently through ordinary Charge. The executable
probe uses real canonical domain objects, existing named fixture helpers,
`LocalGameSession` submissions, `ReplayRunner`, and persistence restoration.
It replaces no controller, validator or service and imports no test module.

| Executed case | Immediate result | Replay | Session persistence |
| --- | --- | --- | --- |
| Valid fixed-target Surge control | Accepted | Reproduced | Restored |
| Surge with an invalid proposal-kind token | Typed invalid; pending request and game state unchanged; zero new decisions, one new event | `event_stream_drift` | Rejected for replay lifecycle drift |
| Same malformed Surge, followed by a valid retry | Retry accepted | `event_stream_drift` | Rejected for replay lifecycle drift |
| Surge with an empty object | Escaped `KeyError('proposal_request_id')`; state and request unchanged | Reproduced | Restored |
| Attached Charge with an invalid proposal-kind token | Typed invalid; pending request and game state unchanged; zero new decisions, one new event | `event_stream_drift` | Rejected for replay lifecycle drift |
| Attached Charge with an empty object | Typed invalid; pending request and game state unchanged; zero new decisions, one new event | `event_stream_drift` | Rejected for replay lifecycle drift |

The recorded results, diagnostic payloads, artifact hashes and prerequisite
metadata are in [preflight.json](performance/order76/preflight.json).
The local reproducible probe is `reports/order76/probe_ingress.py`:

```sh
UV_CACHE_DIR=/private/tmp/order76-uv-cache PYTHONPATH=. \
  uv run --no-sync python reports/order76/probe_ingress.py
```

The separate cache path avoids the desktop sandbox's denial of access to the
default uv cache; the command uses the existing environment without syncing.
The probe asserts the observed defects rather than claiming the required
invariant passes. Its local outputs are retained under `reports/order76/`.

## Authoritative path and same-class search

`LocalGameSession.submit_parameterized_payload` -> `ParameterizedSubmission`
-> `DecisionResult` -> `GameLifecycle.submit_decision` -> registered movement
prevalidator -> typed proposal parsing and context validation.

The lifecycle returns an invalid prevalidation status before
`DecisionController.submit_result`, leaving no `DecisionRecord` for that
attempt. However, the Surge and Charge rejection helpers append an event to
the authoritative `EventLog`. Replay captures that event in its expected
tail but re-executes only recorded decisions, so it cannot reproduce the event.
Session recovery correctly rejects the resulting drift; weakening recovery
or omitting hash comparisons would conceal the defect.

The source audit identified these additional instances and controls:

- `engine/triggered_movement.py`: the reproduced Surge rejection appends
  `triggered_movement_proposal_invalid`. Its parser catches only
  `GameLifecycleError`, while `MovementProposalPayload.from_payload` can
  raise `KeyError` for a missing field. JSON shapes and nested witness errors
  need the same typed-boundary treatment as the ordinary movement parser.
- `engine/phases/charge.py`: the reproduced Charge rejection appends
  `charge_move_proposal_invalid`; its missing-field parser already returns a
  typed diagnostic, but that diagnostic's event still breaks replay.
- `engine/phases/movement_handler.py`, `movement_placement_proposals.py` and
  `movement_resolution_flow.py`: ordinary movement and placement
  prevalidators call the shared `_reject_invalid_proposal`, which appends
  an authoritative event. These are source-traced instances; this preflight
  does not claim an independently executed facade reproduction for each mode.
- `engine/physical_proposal_context.py`: stale spatial-context validation
  appends a movement/placement event before recording. This is another
  source-traced instance of the same mechanism.
- `engine/phases/fight.py`: prevalidation returns a diagnostic without
  appending an event. Its separate recorded rule-invalid path appends an
  event and emits a fresh retry request after decision recording. Preserve
  that distinction and use it as regression coverage for the shared contract.

The adapter contract's current Validation and Invalid Results section permits
prevalidation diagnostics to append adapter-visible events without creating a
decision record. That permission is inconsistent with the current replay
capture model when those events enter the authoritative log. A repair must
update this contract explicitly. It must preserve the existing recorded,
well-formed rule-invalid attempt path and its replayable fresh-request retry.

No new maintained-App observation or source interpretation is needed to
establish this adapter/replay defect. The retained Core sources and immutable
observation fingerprints remain unchanged. The fixture's Core Surge semantics
remain linked to `gw-11e-core-surge:surge-move` and its retained mirror audit
`data/source_audits/maintained_app_mirrors/surge_2026_09_16.audit.json`.
This does not select a controlling snapshot for the final all-category audit.

## Approved prerequisite scope

Owner: **P03D**, C03-04. The owner authorized this implementation on
2026-09-22 after reviewing the preflight. P03D is Order 76 and PFINAL is
Order 77; the canonical sequence now records that dependency.

1. Add failing facade regressions for malformed, missing-field, wrong-context
   and stale physical proposals before changing runtime code. Cover Surge,
   Charge, ordinary movement and placement, and the shared spatial rejection
   path; retain Fight as a control and cover attached rules-unit identity.
2. Route prevalidation failures through shared typed diagnostic construction
   without adding unreplayable authoritative events or decision records.
   Preserve pending requests, RNG, game state and valid retry behavior.
   Keep recorded rule-invalid attempts and their existing retry events intact.
3. Normalize malformed JSON shapes and nested witness loader failures at the
   ingress boundary using specific exceptions and typed invalid diagnostics.
   Do not add broad catches, defaults or weakened payload validation.
4. Require exact replay and persistence after each rejection and after a valid
   retry; verify both viewers and the shared local/headless/network path.
   Add a code-quality guard against mutation by physical prevalidation where
   feasible. Update the adapter contract and any affected external artifacts.
5. Audit all callers of the shared rejection helpers, including callers after
   decision recording, before changing their behavior. Keep unrelated
   gameplay semantics, source packages and solver optimization outside scope.
6. Regenerate runtime identity and dependent contract artifacts, assess any
   affected hot-path costs, run the required final gates and CI-specific
   checks and publish the prerequisite PR. PFINAL can resume only after it is
   merged and audited again from main.

A Surge-only edit would leave the reproduced Charge failure and the shared
movement/placement instances intact. This is an engine/adapter implementation
change beyond an audit/certification PR. `AGENTS.md` requires a pause before
materially broadening the requested work, and the roadmap states: "If the
audit discovers any gap, do not open or certify PFINAL."

## Complete-game performance assessment

Repository inspection found the single-decision headless submission adapter
and test helpers, but no representative legal complete-game driver or
committed complete-game recording. The pairing certification helper seeds a
Fight boundary and drives turn-end scoring; it is not an initialization-to-
normal-completion workload. The capability manifest continues to report
`certified_full_game_evidence_missing`.

Complete games attempted/completed: **0/0**. There are no per-game timing
samples, mean or maximum, and the below-60-second mean / at-most-300-second
observed maximum targets remain **uncertified**. Required evidence still
includes a versioned legal workload or recording, rosters/terrain/seeds/policy,
normal completion and replay output, and measurements on declared reference
hardware. The workload must exercise Order 74's continuous terrain solver.
Existing component budgets do not establish full-game compliance. No new
driver, AI or training work was introduced during this preflight.

## Validation and remaining work

Nine focused existing Surge tests passed without coverage in 18.59 seconds,
including all fixed-target cases and the facade retry/restore regression.
The standalone six-case probe reproduced the failures above and passed its
diagnostic assertions. Ruff check and formatting pass for the probe.

No runtime, catalog, contract, generated runtime identity or collected test
inventory changed. The aggregate behavioral/coverage suite, complete quality
suite and PR publishing gates have not run at this preflight pause. They are
required after the prerequisite implementation stabilizes. No PR was opened.

The complete clause/FAQ inventory, chosen snapshot, all 25 category reviews,
v931/v946 and September 10 consumer evidence, cross-category audit and
CAUDIT-01 closure remain outstanding. Existing passing implementation tests
do not certify those unexamined requirements.


## P03D implementation

The shared `engine/physical_proposal_validation.py` owns movement payload parsing,
parse diagnostics and pure proposal-invalid status construction. Ordinary
movement and Surge consume the same typed loader. Charge and movement rejection
helpers now import the common status constructor, and spatial validation uses
that owner directly. A non-object JSON payload and specific missing-field,
type and geometry errors become typed diagnostics; no broad catch or validation
fallback is added. Charge's frozen module loses its duplicate constructor.

The complete caller audit also found Emergency Disembark's corresponding
prevalidation helper. Three additional regressions failed before removing its
unrecorded event write. Its existing passenger-controller and proposal-specific
response fields remain intact. Its recorded placement-failure helper still
records an event and requests a retry. Prebattle, Fight and Rapid Ingress
prevalidators already return diagnostics without writing events; their semantic
owners are unchanged. Post-record defensive payload/context checks share the
pure diagnostic policy. Well-formed path/rules failures continue through their
separate recorded-resolution owners.

The new facade tests cover malformed object shapes, missing fields, wrong kinds,
unit/request drift, nested witnesses, all-authority equality, both viewers,
network and headless producers, attached models, valid retry, JSON persistence,
and exact replay. Spatial-drift tests deliberately change real fixture geometry,
verify rejection adds no history, restore the original fixture context, then
require accepted retry and replay. They do not claim that an out-of-band geometry
change itself is replayable. Fight is the unchanged control. Existing tests that
expected prevalidation events now inspect the returned diagnostic instead.

The external status/proposal schemas remain compatible: invalid-proposal event
emission was optional, and clients have always received a typed status. Contract
34 therefore keeps its schema version, while its documentation removes the
permission to write authoritative events for unrecorded attempts. Event/replay
hash validation is unchanged. Runtime identity and dependent contract examples
are regenerated; no old save or replay is automatically converted.

Scope audit: one pure engine owner, the existing physical prevalidation consumers,
regression/static tests and required source/contract/performance evidence.
No source observation or rules semantic is changed. The invariant's same-class
repair includes Emergency Disembark; solver behavior, faction content, player
choices, full-game drivers and other audit findings remain outside P03D.

Final validation and matched timings are recorded in
`performance/order76/validation.json`. The historical
preflight above remains evidence of the red state, not the final implementation
status. PFINAL and full-game performance remain uncertified.

At the initial PR head (`e47170e4`), the behavioral run passes 8,873 cases
with 85.19% coverage; the separate
code-quality run passes 592 cases. Ruff, mypy, Pyright, import boundaries,
pre-commit, the regenerated eight-shard inventory, source/build/contract checks,
installed-wheel smoke, five TypeScript tests and 342 conformance assertions pass.
All 30 matched P03D submissions and the inherited component budgets pass.

An earlier aggregate attempt found one obsolete Fight spatial-drift assertion
expecting the removed event. That assertion was corrected, with all 12 related
cases passing. Its coverage reporter also failed to open the shared database;
the successful final run used an isolated coverage database. Both attempts used
coverage, and no production change followed the start of aggregate validation.


## Review corrections R76-001 and R76-002

Review of `e47170e4` reproduced two remaining violations of the typed ingress
contract while confirming that authoritative state stayed unchanged. Emergency
Disembark omitted `GeometryError` from its specific parser catches; pose
validation could leak `OverflowError` when converting a JSON integer such as
`10**400` to a float. Both attached and standalone Emergency Disembark placements
now return their existing typed malformed-proposal diagnostic. The shared
`geometry.pose.validate_finite_number` boundary converts only numeric overflow
to `GeometryError`, preserving the original exception as its cause. It rejects
rather than clamps or substitutes the unrepresentable value.

The same-class search traced `PathWitness`, `UnitPlacement`, and attached
rules-unit placements through `Pose.from_payload`, so this numeric repair
applies to every coordinate and facing without separate adapter conversions.
Ordinary movement/placement, Charge, Fight and Surge already normalize geometry
errors. The search also reproduced missing geometry/type normalization at Rapid
Ingress's separate placement prevalidator; that boundary now uses the shared
proposal diagnostic builder before queue consumption. Non-coordinate numeric
configuration validators and unrelated rule validation are outside this repair.

Facade regressions cover malformed and overflowing Emergency Disembark
coordinates, overflowing Surge witnesses, and Rapid Ingress nested geometry.
They require unchanged lifecycle authority and pending requests, accepted valid
retry, JSON persistence, and exact replay before and after retry. Direct pose
regressions cover positive and negative overflow in x/y/z and facing. The static
purity audit includes the Emergency Disembark parser and Rapid Ingress
prevalidator. The existing adapter contract already specifies typed nested
geometry rejection through the same invalid-status/proposal-validation envelope;
no decision, proposal kind, schema, or gameplay semantics is added.

The original validation record above applies to `e47170e4`. Fresh review-fix
validation is recorded in `performance/order76/review-validation.json`.

The review-fix final gates pass 8,893 behavioral tests
with 85.19% coverage and all 592 code-quality tests.
An earlier coverage attempt aborted during worker shutdown when the filesystem
refused a coverage-database rename; it reported no test assertion failure.
A focused 18-worker save probe passed in `/private/tmp`, followed by the clean
complete coverage run there. Both aggregate attempts used coverage. No runtime
change followed the first aggregate run. Contract compatibility, package smoke,
TypeScript checks/conformance, lint, types, architecture, pre-commit, shard
inventory and all matched component budgets pass for the final runtime.
