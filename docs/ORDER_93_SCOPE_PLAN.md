# Order 93 / P02I — general ignore-modifier permissions

Status: implemented and validated for the source-required C02-09 behavior.
The separate PFINAL source/compliance certification remains open.
Base: `d7bcb10b` (Order 92 / PR #514). The owner approved the complete
provider/value refactor after the preimplementation scope checkpoint.

## Invariant and source

A source-authorized player can independently retain or ignore each applicable
modifier. The engine preserves its source, operation, subject and occurrence
until the recorded choice is validated and the value is resolved. Equal and
opposite operations remain separate choices. Permission restrictions,
model/weapon ownership and attached-unit membership survive submission,
restoration and replay.

The roadmap references Core 01.05.04 and 02.02.02. The registered
`gw-11e-core-modifiers:ignore-individual-modifiers` row defines default coverage
of unit rolls and unit/weapon characteristics, with independent positive or
negative subsets. Its transcription SHA-256 remains
`7c1439a4548907e7648e50c665cab0bfb7e0cf9eb3e92d82ccb453fda838a2a0`.
The immutable September 7 source observation and September 24 Order 84 audit
remain historical evidence. This implementation does not claim a fresh complete
source comparison, an App build identity, or final Core Rules certification.
The source artifact's execution consumer now identifies the shared generic
modifier service rather than only the previously implemented Psychic consumer.
Source wording and observation hashes are unchanged.

## Why the approved refactor was necessary

Previously, fixed S4 with +2 then -2 became a fresh S4 value with no operations.
Fixed Attacks/Damage were similarly collapsed; random count modifiers were
folded into intrinsic dice expressions. Wound/Damage providers returned sums,
and save providers returned changed numbers. An ignore flag applied after those
transformations could not reconstruct the player's available choices.

The old Movement/Advance/Charge path also expanded every subset into action
options, imposed a ten-modifier limit, and persisted a phase-wide unit selection.
That representation could not safely serve repeated attacks, individual models,
defensive rolls, reaction activations or scoring occurrences.

## Shared representation and authority

`CharacteristicModifierTrace` retains the original numeric characteristic,
source-linked operations, bounds policy and chosen IDs. Fixed Range and
fixed/random Attacks and Damage retain equivalent evidence. Intrinsic dice
expressions remain distinct from modifier operations. Providers preserve
opposing effects, replacements and characteristic arithmetic until the owning
consumer applies the selected inventory and existing core bounds.

`ModifierEvaluationSubject` identifies the canonical rules unit, relevant
physical model and weapon, and characteristic/roll family. Permission queries
use loaded catalog authority and active persisted grants, including explicit
source scope and conditions. A model-only grant does not authorize another
model or a multi-model unit's roll. Weapon grants require the currently equipped
physical bearer. Runtime and generic providers retain per-model source scope.

`select_modifier_ignores` is an engine-enumerated finite decision. Its linear
cursor offers keep/ignore for the next operation and keep/ignore for all
remaining operations, with at most four options. It has no exponential subset
list or arbitrary modifier-count ceiling. Any subset remains expressible.
Requests bind the complete operation and permission inventories to an owning
occurrence and continuation. Wrong actors, malformed options and stale source
inventories are rejected before queue pop or authoritative mutation.

Evaluated random profiles also retain `evaluation_raw`, independently of a
symbolic dash/star result. All descriptor resets clear the complete occurrence
triplet, and restore compares the evaluated descriptor against its authenticated
physical roll. Ignoring a replacement recovers the actual rolled value.
Per-model generic activations remain distinct before subject filtering;
unit-scoped deduplication retains its existing semantics.

An immutable lifecycle origin precedes the first accepted input or automatic
advancement. Restoration
and live submission reconstruct source decisions and events from that origin,
including sources that have expired or models that have been removed. A
self-consistent forged current snapshot cannot authenticate its own choices.
The same `GameLifecycle` dispatch serves local, network, headless and replay
submissions. Queries and projections do not silently choose modifiers.

## Evaluation owners

The detailed owner/producer inventory is maintained in
[Order 93 owner inventory](ORDER_93_OWNER_INVENTORY.md). The implementation
connects the shared service to these existing owners:

- Movement characteristics per model, Advance and Charge rolls, with choices
  confined to the active activation, including interrupted Charges.
- Weapon Range/Attacks before declaration or random melee commitment, physical
  weapon splits and reaction retargeting. A changed source inventory reenters
  selection before current/replacement legality is evaluated.
- BS/WS and Hit, attacker Strength, defender Toughness before the attached-unit
  maximum, and Wound modifiers. Psychic retains its source-defined skill/Hit
  permission rather than receiving a broader free permission.
- Defender save characteristics and rolls, attacker AP, incoming AP/cover,
  Damage profile/roll/allocation operations, and source-backed failed-save
  Damage-to-zero replacement timing.
- Leadership/Battle-shock and Objective Control at their engine-owned test,
  phase, turn, mission-action and scoring continuations.
- Desperate Escape rolls and the source-backed Soulstealer healing trigger at
  their existing movement and attack-completion owners.

No named faction handler, speculative hook family, dependency boundary, AI
system or out-of-scope catalog support is introduced. Existing faction providers
change only where they otherwise discarded operations required by this invariant.
Ability availability, intrinsic dice offsets, source-defined thresholds and
other rules that are not modifiers are not automatically made ignorable.

## Adapters and evidence

[Adapter contract 41](ADAPTER_DECISION_CONTRACT.md) and its migration record
version the finite family and changed profile/save/persistence/replay payloads.
Pending modifier evidence and decision records are owner-scoped through the
shared redaction module. Internal source snapshots are hidden from public event
streams; resolved gameplay save values remain visible. Trusted replay retains
complete source evidence.

Focused regressions cover positive/negative/all/none/arbitrary selections,
more than ten operations, source/bearer scope, fixed/random profiles,
Movement/Advance/Charge, shooting/fight, saves/Damage, retargeting, malformed
and drifted inputs, JSON serialization, restored pending/completed choices,
viewer isolation and exact replay. Regression claims and final validation
counts must match completed runs, not this list of acceptance requirements.

## Validation and publication

The final runtime is `6ba430dc82d3bda374b14daf4cd488144a7f653b7de12d7ef3dcf160f3a403f3`.
The complete behavioral suite passed 9,729 tests with 85.20% branch-inclusive
coverage, followed by all 704 code-quality tests without coverage. Both used
18 work-stealing workers. The eight-shard inventory was regenerated from that
successful behavioral profile and passed the exact inventory check.

Ruff, formatting, mypy, pyright, import contracts and pre-commit pass. Source and
runtime identity generation, Contract 41 compatibility against exact base
`d7bcb10b`, generated TypeScript, five client unit tests, 342 HTTP conformance
assertions and installed-wheel smoke pass. Machine-readable commands, hashes
and aggregate results are in [validation](performance/order93/validation.json).

[Performance evidence](performance/order93/README.md) retains the matched
Shooting/Fight comparisons, bounded thirteen-operation choice diagnostic and
25 refreshed inherited reports. An independently reviewed measurement correction
makes the preexisting Order 34 geometry gate cold-cache deterministic, retaining
its original evidence and every non-geometry limit. No full games were measured;
the mean below 60 seconds and observed maximum below 300 seconds remain
uncertified. The matched base was measured after implementation began; that
chronological policy limitation is explicitly retained.

Independent review identified and drove repairs to Leadership source operations,
random raw-value authority, atomic source-local limits and fixture evidence.
The final publication review is recorded in the validation artifact. The branch
is pushed only after explicit approval with no outstanding findings. The separate
PFINAL audit remains required after this and subsequent roadmap orders merge.
