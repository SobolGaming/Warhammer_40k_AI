# Order 24 / P01B scope review

Status: expanded scope approved by the user and implemented on
`codex/order-24-unit-splitting`; all required local validation gates pass. The roadmap
implementation record owns final gate and PR evidence. C01-02 closes after
review and merge.

Reviewed base: `b8805911de434f9b53b4c209e896012998e0e95f`, fetched `origin/main`
on 2026-09-06. This includes Order 23 / PR #429. No open PR was returned by
the repository's open-PR listing. P19 and S-MIRRORS are merged prerequisites.

## Required invariant

An authorized split must produce two independently usable rules units while
preserving each existing model's identity, equipment, wounds, original source
ownership, and authenticated history. The controlling player's recorded
membership choice must assign each affected model exactly once. Successor
counts must obey the operative splitting rule, including its attached-model
fallback. The same models cannot be subdivided again.

The Core rule regulates a split authorized by another rule; it does not give
every unit permission to split. Source eligibility must therefore remain
explicit and fail closed.

## Source observations

The complete operative balancing addition is present in the embedded App-data
version 931 change and erratum records returned by
[Game Datamissions](https://game-datamissions.com/11th/rules/changelog?v=931).
The two entries describe the same obligation. The initial rendered page still
shows version 946, so its visible default content alone is insufficient for
this finding.

The indexed [40k.app category 01 page](https://www.40k.app/rules/01-core-concepts)
contains the earlier once-only subdivision and pre-battle Starting Strength
clauses. Its indexed 01.02.06 section does not include the v931 addition, and
no App-data version is asserted for that observation. Direct retrieval returns
HTTP 403. This is not evidence of a co-versioned conflict.

The reviewed clauses are now retained in the registered
`gw-11e-core-unit-splitting` package and
`data/source_audits/maintained_app_mirrors/unit_splitting_2026_09_06.audit.json`.
They preserve provider/version, transcription hashes and observation
fingerprints. The existing official PDF remains historical evidence.

## Discovered ownership constraint

The live representation equates current physical ownership with the unit
prefix embedded in an immutable model identifier:

| Owner | Existing constraint | Consequence for a split |
| --- | --- | --- |
| `engine/unit_factory.py`, `_validate_model_instance_links` | Every model ID must begin with the current `UnitInstance` ID. Models must also match the component's datasheet. | Moving an existing model into a newly identified physical component is rejected. Flattening mixed attached components into one datasheet is also invalid. |
| `engine/battlefield_state.py`, `ModelPlacement` | A placed model's ID must begin with its current placement unit ID. | Successor placement cannot preserve the old model ID under a new physical owner. |
| `engine/phases/movement_model.py`, `DesperateEscapeRequirement` | A model ID must begin with the requirement's unit ID. | Changing only unit construction leaves a later movement consumer unable to represent the successor. |
| `engine/rules_units.py`, current identity queries | A component alias resolves to exactly one current rules unit. | Sharing an unpartitioned physical component between successors produces ambiguous identity. |
| `engine/starting_attached_units.py`, lineage validation | Starting attached formations and their component/strength identities must match the current formation inventory. | Replacing an attached formation requires authenticated historical lineage, not erasing the original record. |

This is a shared representation issue, not only a missing finite decision.
Deleting prefix checks would remove an existing ownership validation without
replacing its authority. Renaming models would break model-bound history.
Leaving both successors pointed at the entire original component would give
them overlapping membership. None is a valid local fix.

The existing `split_unit` materialization path creates models in response to
a model-destruction rule. It does not partition the existing model inventory
and cannot substitute for the generic split requested here.

## Approved complete change in one PR

1. Introduce typed, engine-owned partition lineage that distinguishes immutable
   model/source identity from current physical component and rules-unit
   membership. Authenticate transfers through that lineage; retain strict
   validation of ordinary unsplit units and reject duplicate or unexplained
   ownership. Preserve attached component roles and datasheet provenance.
2. Add the canonical source-authorized split request and submission path.
   Use a linear sequence of finite model-assignment choices, avoiding an
   enumeration of every possible partition. Validate actor, source, timing, current membership, duplicate
   use, successor cardinality and source-specific strength before queue pop
   or mutation. Record the chosen model IDs and whether the generic strength
   fallback was necessary.
3. Apply the partition atomically in the engine. Update current unit and
   physical membership together, preserve model IDs and positions, establish
   the required successor Starting Strength, and retain original attached
   lineage. Trace affected unit-scoped state through the common identity
   owner, including effects, Battle-shock, reserves/cargo, activation history,
   resources and model-bound equipment. A split must not create a second use
   of an already consumed resource or activation.
4. Make placement, movement, damage, healing, historical state, replay and
   adapters consume that same authenticated ownership. Update the closed
   decision/persistence schemas and contract documentation. Keep requests,
   records, projections and event deltas viewer-scoped, including setup
   secrecy. Do not introduce faction-specific lifecycle branches.
5. Add the source package/audit, identity and consumer regressions, static
   ownership audit, generated artifacts and roadmap evidence. Audit the
   final scope before the required aggregate gates. Publish the implementation
   branch and PR only after the required checks and source evidence are ready.

No package import-boundary change, faction-content expansion, new named rule
handler, AI work, permissive fallback or compatibility shim is proposed.
This expands P01B's implementation footprint into shared unit ownership and
history; it does not add separate gameplay features.

## Acceptance evidence

- Even and odd model counts, selected membership distinct from sorted/default
  allocation, two nonempty successors, and equal-as-possible counts.
- Feasible source-specified strengths and impossible strengths caused by
  Leader/Support models, with mixed-component provenance preserved.
- No omitted, repeated, foreign or already-subdivided models; no actor,
  source, phase, membership or request drift accepted before queue pop.
- Successors act and receive damage independently; model identity, wounds,
  equipment, placement and resources survive the split without duplication.
- Historical attached-unit destruction/strength semantics remain valid;
  splitting must not reintroduce automatic separation on bodyguard loss.
- Exact JSON and checkpoint round trips, event/state tamper rejection,
  deterministic replay through `LocalGameSession`, and both viewers' scoped
  projections/event deltas.
- Final behavioral coverage run once, quality suite once, all other AGENTS.md
  gates, active-CI contract/base-ref/client/conformance/wheel checks, and the
  eight-shard inventory check. New behavioral files require a complete JUnit
  profile and regenerated shard inventory.

## Validation performed for this scope review

Using real canonical fixtures from `tests/phase11c_command_phase_helpers.py`,
attempting to construct a successor with unchanged model IDs raises
`UnitFactoryError`; attempting its placement with the unchanged model ID
raises `PlacementError`. Both report the current unit-prefix constraint.

The existing regression
`tests/unit/test_phase9c_mustering.py::test_runtime_payloads_reject_hierarchy_and_source_drift`
passes (`1 passed`, no coverage). It confirms that the current restriction is
intentional and covered, so the new authority must replace its function
rather than simply deleting the check.

Implementation now distinguishes `SplitUnitOrigin`, immutable
`UnitSplitRecord` source history, current `RulesUnitView` membership and the
frozen battle inventory. Original model IDs are unchanged. Physical validators
share the ownership proof; current movement/scoring/destruction consumers no
longer rebuild groups from retired formations. Existing unit effects resolve
through historical aliases, and unit resources retain one original account.

Focused tests cover ordinary and attached setup, deployment, persistence
replay, independent movement and damage, 10/11/12-model balancing, malformed/stale
submissions, source/model/event/checkpoint drift, viewer secrecy and retained
effects/resources. The final behavioral coverage, code-quality suite and
supporting local gates pass; the roadmap records their evidence.

## Recorded scope decision

AGENTS.md's scope discipline requires a pause before a materially broader
solution. The proposed decision is to include the shared ownership/lineage
refactor and its physical/history/adapter consumers in the single Order 24
implementation PR. The user approved this expansion. Approval does not waive
any invariant or final gate.
