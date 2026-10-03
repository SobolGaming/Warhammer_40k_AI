# Order 104 / P04H: independent range and visibility witnesses

## Source and invariant

The selected obligation is
`faq-5553f538-6182-4e72-905a-67855489bb1d-obligation-01` (C04-09).
The literal question in `data/source_audits/order97/selected-sources.json`
asks whether the visible enemy model and the enemy model in weapon range may
be different models in the same unit; the answer is "Yes". The selected source
hash is `5c88c04e13b99a324290f8726e470f1e4fb93152c890c597b9b16906cdd4e3e4`;
answer block 2 hash is
`184fda5c980b9d9cb375f42a528817c6235fbd4f79775a8018fae5afcbdf2a63`.
The original Order 97 report, inventory and observations remain historical.

For one firing model, at least one living placed target model must be in weapon
range, and at least one eligible model of that same canonical target rules unit
must be visible. Those models need not coincide. Independent firing models or
different enemy rules units cannot combine their evidence to grant an attack.
Hidden detection still filters visibility. The documented Indirect Fire exception
still permits a target with no eligible visible models where applicable.

## Owning path and bounded repair

`shooting_targets._target_candidate` supplies the shared ordinary and reaction
declaration validator. Its `_best_line_of_sight_range_evidence` already visits
each observer separately and constructs a complete `LineOfSightWitness` against
all placed living models of the canonical rules unit. Previously it intersected
eligible visible model IDs with in-range IDs and exported that intersection as
both evidence sets, rejecting the legal FAQ case.

The helper now retains separate visible and in-range sets for the same observer.
The visibility witness remains complete, including blocked models and cover
evidence. The detection precheck no longer requires a detectable model to also
be in weapon range. Indirect Fire and Plunging Fire use the corrected visibility
set; attack pools preserve both independent sets for downstream attack consumers.

Bug-class search covered candidate construction, selection and declaration
validation, ordinary and out-of-phase hosts, target replacement, attack-pool and
gathered-group serialization, precision allocation, half-range effects and the
separate unit line-of-sight query. They consume the shared candidate or already
perform separate physical checks; no second local range/visibility intersection
requires a runtime change. Melee engagement and source-specific Stratagem target
restrictions retain their own semantics. No new source interpretation, gameplay
choice, runtime hook, architecture boundary or public field is introduced.

## Acceptance and evidence

`tests/unit/test_order104_range_visibility.py` uses real canonical catalog models,
physical weapon declarations and terrain. It covers disjoint range/visibility
evidence, attached target membership, independent enemy-unit rejection, Indirect
Fire visibility, Hidden detection, required range and invisible half-range
models supplying Rapid Fire, and ordinary/Fire Overwatch submissions. Engine-generated pending and accepted
states round-trip through persistence, continue to attack completion, preserve
both viewer projections/event streams and reproduce exactly through ReplayRunner.
The existing stale proposal boundary rejects without mutation.

Existing retained-model regressions now assert the selected firing model's exact
range evidence separately from complete target visibility, with a nearer-observer
control preserving the retained base's range contribution. Two own-Hazardous-death
fixtures use deterministic game IDs that still reach their original death and
retained-shot assertions after the corrected evidence changes event history.
The original Order 97 pinned shooting-phase test bytes are retained in the fixed
`data/source_audits/order104/historical-inputs.json` mapping; the earlier Order 103
archive already retains the original shooting-declaration test. No historical
manifest hashes are replaced, and live regressions continue in the normal suite.

Contract 44.1 already defines separate `target_visible_model_ids`,
`target_in_range_model_ids` and complete line-of-sight witnesses. Correcting their
contents does not add or remove fields or option families; the adapter contract
documents the clarified semantics without a version bump. Runtime identity and
current generated consumers are regenerated through the existing tooling.

The exact-base performance assessment and existing serial live smoke accompany
the delivery. Complete covered behavior, quality, type, lint, generated/contract
checks, hosted CI and two independent exact-head reviews remain required. This
scope document does not claim those delivery gates have passed, certify Core Rules
as a whole, or start Order 105/PFINAL.
