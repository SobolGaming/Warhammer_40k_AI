# Section05 Deadly Demise plus Fight on Death decision

Status: approved specification implemented by the focused task11 checkpoint; independent review pending. The historical decision and source conflict below remain retained. See [focused repair evidence and qualifications](FOCUSED_DEFECT_CHECKPOINT.md).

## Approved interaction

Finish the retained model's Fight on Death, or reach its expiry. Remove that retained model from the battlefield, then resolve its Deadly Demise. Preserve the applicable measurement reference from before destruction. Enemy casualties with their own Fight on Death retain their independent protection until their own completion or expiry; do not remove them prematurely to advance this model's cleanup.

This is a specific interpretation of Deadly Demise plus Fight on Death. It does not impose after-removal timing on every destruction-triggered rule or establish a universal priority for mutually retained models.

## Source and user-decision provenance

On 2026-10-17 at 12:06 UTC the user answered "yes" to adopting the FAQ-specific after-removal interpretation for the corpus and queuing the engine correction for a future fix, leaving the engine unchanged. Message: Sentinel_dc71bb89df0c81919b2fa581fc5d346e. Parent relay: 01a0efa7-1ce0-70b0-a637-75c1615f80ef. The full proposal and decision are recorded in `tests/rules/section05/future-fixes.json`.

This explicit decision supersedes the user's prior approved last-step-before-removal interpretation for this interaction only. It is not a claim that a newly published FAQ superseded an older rule.

Retained FAQ20 is `faq:ab92e97b-be2b-4125-9ded-fcfa6abe092e`; row SHA-256 `6c0d66fac9785c64b585ccf535fece6c50738787459f61ccff18d7b4d54f22fc`, answer block SHA-256 `43ed24dd1a6c03286c5c8661c341b329114af0552f5e4ffbc9bb9b8c15890355`. Its answer puts Deadly Demise after fighting/phase end and removal of the relevant models. The phase-end alternative need not have enemy casualties, so the retained models are the stronger referent. This reasoning supports the user-adopted interpretation; it is not a new official App verification. The retained unversioned mirror and capture details remain in the coverage map and finding register.

Preserve the conflicting Core05.04.05 block2 wording as provenance: it resolves destruction-triggered rules before removing the destroyed models. Source `rule:05:05.04.05:1`, row SHA-256 `35c651d4f6a14010b1818be0d94b55ecfe4949b08b92afa3d56793a8fe89f21d`, block2 SHA-256 `f9202c2f99ed760cbc4ce3afd0f0bb17c3183c599506ae07396bf50f34f798d2`. Original source blocks are unchanged; this decision adopts the FAQ-specific interpretation for the named interaction.

Core05.04.06 refers to the position before destruction, not silently the last position before removal. Source `rule:05:05.04.06:1`, row SHA-256 `a51a2b4256e29a12c9fb20d937903185c9fbcf9cc1a2e766024c464aa4f867b9`, block1 SHA-256 `81159d37af22e539e3ba18b3647eba739d6888a34f5260d068b9902c4d93a979`. Apply its base/model/Vehicle/Walker measurement qualifications and its last-destroyed-model rule where applicable; do not replace the source with a generic last-location rule.

## Current evidence and future coverage

The unchanged enabled test `tests/rules/section05/test_reaction_boundaries.py::test_faq20_deadly_demise_resolves_after_retained_model_removed` expects the retained casualty to be removed when its destruction reaction resolves. It currently observes otherwise. Its existing failure is now a future-fix semantic finding, not an unresolved authority conflict.

The additional requirements below are not established by that removal observer or newly covered by this documentation update:

- Add a combined interaction test that distinguishes the pre-destruction measurement reference from a later retained-model or removal position. Verify the preserved applicable geometry when Deadly Demise resolves after removal.
- Add a combined interaction test with an enemy casualty having its own Fight on Death retention. Prove that the original model's cleanup and Deadly Demise do not prematurely remove that independently retained casualty. Do not infer universal mutual-retention priority from a simpler control.

Historical complete Windows and Linux runs each recorded 1,075 cases, 1,064 passes and 11 failures. Those outcomes are unchanged historical receipts; the eleven failures now belong to six future-fix semantic groups. No test or runtime code changed and no suite was rerun. Section05 metadata records 79 asserted obligations and three visible semantic-failure obligations. Historical validation.json and raw reports remain unchanged and are superseded only in authority/finding classification by this decision.

## Focused implementation checkpoint

Task11 enforces the adopted ordering in both attack and rule casualty owners, with exact cause/removal reuse on interruption. The historical observations above describe the pre-repair source. Current observer, real retained-melee and independent-retained controls are validation targets; the relocated-position distinction remains qualified by the fixed-placement guard. See the focused checkpoint and its external receipts for exact outcomes.
