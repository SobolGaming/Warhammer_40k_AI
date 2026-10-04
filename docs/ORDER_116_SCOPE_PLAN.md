# Order116 / P06E / C06-05: additional attack mortal Core seam

## Source, invariant and authorized scope

Retained Order97 Core 06.02 requires normal damage before mortal wounds and its
06.02.01 block1 makes additional mortals part of the same originating attack.
Original inventories and captures remain historical. The current pinned July22
Grey Knights PDF, page5, gives a real source example: Radiant Champion inflicts
one additional mortal per successful bearer melee wound while the bearer is
wholly within Hallowed Ground. Its current source row is
`enhancement:grey-knights:warpbane-task-force:000009777003`; PDF SHA256 is
`8df7b54292988edb5ef5a83260dd4c054f658f06ba7cacc2467e3f558a1dd797`.
No fresh live-source observation is claimed.

The owner explicitly chose the Core seam only, following Order114. A provider
must issue an authenticated phase-bound permission after its own source
conditions hold. This Core repair implements that permission's complete attack
consumer; it does not implement Radiant Champion loading, Hallowed Ground,
PRECISION grants or general Grey Knights support. Their named modules remain
load-only scaffolds. Canonical generic permission fixtures exercise both attack
phases; they do not claim the named example grants ranged attacks.

The violated invariant was source-preserving attack semantics: the sole deferred
producer was Devastating Wounds damage replacement and its consumer hardcoded that
source. Shared code must preserve ordinary damage and the attack's true identity.

## Owners and full resolution

`additional_attack_mortal_permissions` validates exact permission shape, amount,
source bearer/component ownership, occasion, phase, actual turn and weapon scope.
Providers use the typed effect factory and the engine records the effect.
`additional_attack_mortals` consumes final successful wound contexts, including
skipped successful wounds and supported generated hits, with one source-linked
entry per permission and originating attack. Source names/text are never gates.

The post-roll owner invokes the producer after Devastating damage-roll choices
finish, on both ordinary and PRECISION continuation paths. Normal contexts retain
ordinary saves/damage; deferred mortal entries retain source permission snapshots.
The extracted `attack_sequence_deferred_mortals` owner keeps the original queue
order and resolves it only after normal damage, using shared finite recipient,
Feel No Pain, allocation priority, attack-attributed destruction and spill routing.
A shared physical-contribution resolver retains each original weapon profile and
instance when equivalent weapons gather, and reuses the existing post-roll
modifier service. Devastating Wounds uses the same provenance repair while its
damage replacement and allocation semantics remain distinct. A shared Feel No
Pain classifier uses typed attack evidence for Psychic-tagged weapon attacks,
including their additional or replacement mortals; non-attack mortals retain
their existing filtering. This does not implement the separate Order120 Psychic
ability-damage classification work. Restore's existing pending-attack boundary
recognizes both source kinds before the attacks-resolved boundary.

Consumer-path regressions cover real facade submissions, actual damage, ordered
identity/source records, pending JSON save/load, isolated continuation, typed
rejected finite options, lethal completion, viewer projections/events and exact
replay. Source scope and malformed permission controls fail closed.

## Delivery and remaining support

Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`: block reproduced incorrect
rules, ordinary legal gameplay, engine-created persistence/replay and required
supported-input boundary failures. Queue unrelated manual-history hardening.
Full covered behavioral inventory (>=85% combined), quality/type/lint/contracts,
generated identity/client/golden checks, source/historical pins, serial smoke,
two distinct exact-head reviews and protected hosted CI remain mandatory.
This is a bounded rules branch, not a performance optimization or full-game
performance certificate. Preserve failed receipts. Refresh the complete JUnit
profile after runtime/test freeze and byte-bind metadata-only successors.

Every order must update its roadmap implementation cell before final freeze and
carry this requirement forward. Stop before Order117 for a fresh session.
