# Order 84 — Dice result semantics (P01G / C01-07)

The violated invariant was that a source-assigned dice result must retain the
identity and history of its physical dice, while every downstream rule evaluates
the assigned value. A physical D6 bound must not reject or clamp an assigned seven.
When a rule refers to a tied highest or lowest die, the active player chooses the
physical die through the engine decision authority.

## Source and scope

The reviewed source package `gw-11e-core-dice-results` records complete Core
01.05.07 and 01.05.08 text, plus the exact-six critical-result rows of 05.01 and
05.02. The selected maintained App-data mirror is
[40k.app Core Concepts](https://www.40k.app/rules/01-core-concepts) and
[Attack Sequence](https://www.40k.app/rules/05-attack-sequence), observed on
September 24, 2026. These observations expose no App-data version; neither the
generator nor registry claims co-version equivalence. Historical official GW PDF
provenance is retained separately. The offline generator, byte-pinned typed loader,
transcription hashes and authority registry preserve the distinction between
loading source evidence and executing its declared consumers.

This closes the dice result finding, not the historical audit as a whole.
Orders 85–94, Category 07 revalidation and PFINAL / CAUDIT-01 at Order 95 remain
open. The earlier audit artifacts remain unchanged. No additional faction content,
AI policy, named runtime handler or speculative hook family is introduced.

## Ownership and consumer audit

`DiceRollResult` and reroll results remain bounded physical RNG records.
`DiceRollState` authenticates a positive assigned result against those records.
Its override records the source, decision, prior values and either one physical
component index or an explicit whole-roll assignment. `DiceRollInstance` keeps
physical faces and stable component IDs separately from effective values.
`UnmodifiedRollResult` carries the same assignment through the existing ordered
modifier service and domain limits, including Charge's terminal cap of twelve.
Assignments consume no RNG and cannot be followed by a reroll. The shared reroll
manager rejects assignment before recording or drawing dice; conditional source,
Command Re-roll and Twin-linked owners do not reopen windows after assignment.

The existing generic RuleIR override descriptor and source-bound Hit/Wound
resource decision accept assigned values above six. They no longer suppress a
legal override merely because the original result was successful or critical.
Eligibility, resource spending, stale-context validation and mutation stay in the
existing engine owner. The parser normalizes numeric assignment once at the data
boundary. Existing source permissions still determine which rolls may be changed;
Core 01.05.08 is not itself permission to change any roll arbitrarily.

Hit, Wound, Saving Throw and grouped-save validation share authenticated
single-D6 interpretation. Default critical hits/wounds and ordinary Snap Shooting
require exactly six. Source-granted `4+` or `6+` critical thresholds remain inclusive,
including Anti and generic Wound modifiers. The persisted comparison flags prevent
seven from accidentally becoming a default critical six. Post-roll weapon triggers
consume the assigned result and its resulting success/critical flags.

Hazardous uses the effective component result; movement, Advance, Charge,
Battle-shock and characteristic/damage modifier consumers already use the shared
current-total/modifier stages. Physical injection, reroll-face, D3-source, threshold
and resource-die bounds remain physical/source-specific bounds. They were not
globally loosened. Grouped save ordering compares separate one-D6 attack rolls;
it is not a highest/lowest reference within one multi-die roll.

`request_dice_extremum` owns Core highest/lowest references. A unique extremum
requires no choice; a tie emits `select_dice_extremum`, with options naming all
matching physical components. An explicit source occurrence ID distinguishes a
resumed reference from a later reference to the same roll. Selection belongs to
the effective active player, including existing out-of-turn scopes. Requests bind
the current roll, source, phase, turn and round. Invalid/stale submissions preserve
the pending request and state. Source/reference and selection events authenticate
pending and accepted persistence history. Historical phase/turn anchors and typed
action-scope selections authenticate the chooser even after the phase has ended;
correlated edits to all request copies cannot replace this authority. Scope
openings require earlier accepted source decisions and cannot reopen consumed
selections. Shooting sources prove their actual action permission through existing
Stratagem-use authority, source-provider execution evidence, setup selection, or
retained-destruction selection. Completion matches its opening. Fight
interruptions, out-of-turn shooting and Charge retain their existing owners.
No existing multi-die highest/lowest
gameplay consumer was found; the Core service is exercised through real lifecycle,
facade, viewer, persistence and replay paths without inventing a faction rule.

Interpretation-only metadata and duplicate scope evidence are RNG-history-neutral,
following the existing decision authority policy. Actual assignments and chosen
components remain in RNG history. Retention hashes still bind full canonical
evidence; four seeded casualty fixtures were updated because those hashes changed,
with their behavioral and restore assertions preserved.

Secret references inherit the physical roll's visibility through shared adapter
redaction. A reference requiring another player's secret dice fails explicitly:
the Core rule does not grant disclosure. The source must authorize disclosure
before that reference can be offered.

## Contract and validation

Contract 38 and persistence v30 require the new physical/effective evidence and
comparison fields. Released baselines remain immutable; old payloads are rejected
instead of receiving inferred evidence. The adapter decision contract and migration
describe tied-die options, context, events, redaction and required payload fields.

Regressions extend existing inventoried behavioral files, with a named shared
fixture helper. They cover physical bounds, component and aggregate assignment,
reroll order, critical/trigger distinctions, source-compiled resource decisions,
active-player tie selection, atomic rejection, both viewers and exact checkpoint
and replay. Static audits check source artifacts and the shared interpreter.
Final command results and component performance evidence are recorded under
`docs/performance/order84/`. Full-game performance is not certified by component
measurements.
