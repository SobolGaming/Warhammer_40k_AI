# Order 95 / P04E — optional ranged targets

Violated invariant C04-06: selecting a unit, selecting physical weapons, assigning
targets and making attacks are distinct facts. The declaration contract previously
required a target for every selected weapon and prohibited an empty declaration.

## Source and bounded scope

The retained September 28 audit observation in `data/source_audits/order95/audit.json`
and the September 24 inventory in `data/source_audits/order84/audit.json` bind Core
04.01, 04.02.01, 04.03.04, 10.02, 24.15 and 24.26. The maintained Game Datamissions
[Core Rules](https://game-datamissions.com/11th/rules/core-rules) asset
`/_next/static/chunks/app/11th/rules/core-rules/page-ec6350d45d9ddeb5.js` was retrieved
again on 2026-09-28 and matched retained SHA-256
`6f4d27c5670489e9b6310bb8f43e837d8abaf2d5f7a8c8938f56690190edad0e`.
The retained audit provides the observation timestamp, transcription hashes,
fingerprints and official historical provenance. This is a maintained App-data
mirror, not a newly verified official App release. Existing Hazardous, One Shot,
Action, shooting-type and Firing Deck source packages remain authoritative.

Core 04.02.01 permits declining a ranged target; 04.03.04 does not treat a unit
with no model attacks as having shot. Hazardous counts weapons selected in Select
Weapons, and One Shot limits selection to once per battle. Thus dropping targetless
selections from the executor would lose mandatory selected-weapon consequences.
The explicit empty declaration selects no weapons. Automatic Order 91 completion
when no legal declaration candidates exist keeps its terminal authority; outstanding
selected-unit obligations now use the shared completion path. Twin-linked and the
complete clause evidence inventory remain Orders 96 and 97.

## Authority trace and bug-class search

Existing unit/type DecisionRequests lead to one parameterized declaration validator.
The offered physical inventory and source-instance choices authenticate targetless
entries. A typed TargetlessWeapon preserves the selected source profile separately
from strictly targeted, positive RangedAttackPools. Both ordinary and out-of-phase
hosts record One Shot through the existing engine service and carry these selections
through the shared AttackSequence. All immutable executor copies preserve the
inventory; Hazardous consumes the complete selected-weapon view. Non-Hazardous
completion providers declare whether actual attack pools are required. Source-created
selection obligations, including the already-loaded Dark Pact, remain mandatory.

The bug-class search covered ordinary/out-of-phase declaration validation, Firing
Deck, physical duplicates and Pistol exclusion, random A, target replacement,
immutable executor continuations, Hazardous damage/retention, One Shot, attack
participation, Hidden loss, Action restriction reconstruction and retained cleanup.
Target replacement indexes targeted declarations while preserving original
random-A source ordinals. No named handler, source-name branch, new decision type,
architecture boundary or alternate adapter mutation path was added.

Explicit empty and all-targetless declarations complete the shared shooting
executor with no attack groups and an explicit selected inventory, which may be
empty. Automatic no-candidate terminals remain the authority for their restrictions;
only outstanding selection obligations create a pending completion using that typed
terminal as its origin. No accepted declaration or model attack is fabricated.
Mixed selections retain both inventories. Restore binds these to accepted choices,
offered profiles and selected One Shot expenditure; participation records contain
only actual attacking models. Selected unit/type and cargo restrictions survive
through their existing owners, even when no model has shot.

## Delivery evidence

Contract 42 makes ranged targets nullable and documents empty declarations,
optional targetless source choices and selected-weapon event/executor inventories.
Persistence uses `session-persistence-v34-optional-ranged-targets`, bound to
Contract 42 and exact runtime identity. Generated schemas, examples,
manifest and TypeScript client are regenerated; ordinary empty optional inventories
remain omitted for ordinary targeted executors to preserve unrelated deterministic
decision histories. An explicit empty selected inventory is meaningful.

`tests/unit/test_order95_optional_shooting.py` covers real facade submissions,
attached units, all four ordinary shooting types, all/partially declined targets,
Hazardous and One Shot, Firing Deck with/without contributions, retained cleanup,
source-loaded automatic Hazardous success, duplicate source choices, atomic invalid
submissions, both viewers, authenticated restoration and exact replay. A static
audit requires immutable executor copies to retain the selected inventory.

Performance samples and required validation are retained under
[performance/order95](performance/order95/README.md). These are component/gameplay
slice evidence; no complete head-to-head games or full-game certification is claimed.

Independent review found and repaired two gaps: correlated empty-proposal context
tampering and skipped mandatory selected-unit consequences. Empty declarations now
use the same accepted-declaration authority and completion pipeline as other
proposals. The same-class automatic no-candidate path retains its typed terminal
while using shared completion only for outstanding obligations. Real source-loaded
regressions cover explicit empty, targetless, automatic no-candidate, and combined
Hazardous/Dark Pact sequencing. This preserves the existing faction handler's timing;
no broader faction semantics migration is included.
