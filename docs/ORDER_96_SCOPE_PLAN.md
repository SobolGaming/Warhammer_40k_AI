# Order 96 / P24K — optional Twin-linked wound rerolls

C24-11 violated the player-choice invariant: intrinsic Twin-linked invented its
own DecisionResult, automatically rerolled failed wounds and excluded successes.
The repair removes that automatic resolver. Every eligible physical wound now
uses the existing optional source-backed reroll request and accepted result.

## Source and scope

The retained September 28 Order 95 audit and September 24 Order 84 inventory pin
Core 24.38 and 01.05.02. The maintained Game Datamissions
[Core Rules observation](https://game-datamissions.com/11th/rules/core-rules)
asset `/_next/static/chunks/app/11th/rules/core-rules/page-ec6350d45d9ddeb5.js`
was retrieved during implementation and matched SHA-256
`6f4d27c5670489e9b6310bb8f43e837d8abaf2d5f7a8c8938f56690190edad0e`.
The literal-only audit extractor verified the complete relevant entries:

| Clause | Retained row fingerprint | Obligation |
|---|---|---|
| 24.38 | `ab43cff6799c3d92fbae433866c1b8116884e4c1cc0f63dc92e28609cfe058df` | Optional wound reroll on each Twin-linked attack, without a failed-roll condition. |
| 01.05.02 | `4eeb118aeab3f6bafa654ca257f88346ee31712d18019819279475b2f859f343` | Reroll the whole roll where required, at most once per die, before modifiers; the replacement can trigger ordinary roll effects. |

This uses the existing stable `weapon-ability:twin-linked` intrinsic identity,
canonical WeaponKeyword and catalog profile provenance. Runtime does not parse
text or infer behavior from display names. No new catalog content, named rule
handler, generic hook family or source package is introduced. The mirror remains
an unversioned maintained observation; it is not a new official App capture.
Historical negative audits remain unchanged, and Orders 97–98 remain open.
The Order 95 checker explicitly maps its retired automatic helper reference to
both current permission/request owners. It rejects missing successors and a
reintroduced automatic helper; the pinned observation and report are unchanged.

## Authority trace

Catalog keyword/source IDs and selected physical profile → intrinsic wound
RerollPermission → shared source candidate selection → `select_dice_reroll`
(`decline` / `reroll:0`) → before-pop validation → DecisionRecord →
DiceRollManager → existing dice event history → shared wound resolver/resume.

Intrinsic and granted permissions enter the same deterministic strongest-permission
selection. Equivalent overlapping sources yield one choice, not extra rerolls.
Declining that choice still permits an eligible Command Re-roll. Accepting either
source exhausts the die. Assigned results and forbidden rerolls do not reopen the
window. The resumed wound recomputes success and critical status from the chosen
physical result through the normal Strength, Toughness and modifier authority.

The shared request builder is reused read-only for live and pending-restore
validation. It binds the last physical wound to the unresolved current attack
pool, current source permission, actor, game, round, phase, target, weapon,
selected ability instances and dice state. Grouped resolution can retain its pool
cursor at zero; the event-backed physical wound identifies the unresolved frontier.
Changed options, payloads, dice, sources and context cannot consume the queue.
Routing consults the original issued request, pending payload and preceding
physical roll. Retyping both request copies cannot reclassify a wound as an
Advance roll and evade validation.

Dice dispatch now identifies the active attack host through the existing shared
state query, rather than assuming the current battlefield phase owns the roll.
Ordinary Shooting/Fight, retained casualties and out-of-phase Shooting therefore
use the same accepted-result applier and lifecycle continuation. Non-attack rerolls
keep their existing Movement, Charge, Battle-shock and Stratagem dispatch.
Actual Fight interrupt and out-of-phase Shooting frames advance to each new
pending request and resume their parent after completion, including restoration
between choices.

The new wound pauses also re-enter hit resolution. Sustained Hits D3 therefore
uses the shared dice-history owner to reuse exactly one matching physical D6 and
derived D3 pair for its attack identity. Missing, duplicate or inconsistent pairs
fail closed. Final hit critical status still determines whether generated hits
apply. Both phases and both wound choices preserve unique hit contexts, one D3
per critical hit, checkpoint equality and exact replay. The direct-D3 caller
search found this resumable attack call; other calls belong to selected grant,
Stratagem, destruction, phase-end activation or faction completion operations.
Those operations are outside this wound-resume repair.

## Automatic-caller audit

All eight remaining engine `resolve_reroll` call sites were inspected:

| Owner | Submitted authorization |
|---|---|
| `attack_sequence_dice_rerolls.apply_source_backed_attack_dice_reroll_decision` | `record_for_result`, canonical attack request/result and source validation. |
| `battle_shock_resolution.apply_battle_shock_reroll_resolution_decision` | Recorded optional Battle-shock choice and source/test context. |
| `charge_roll_flow._apply_charge_roll_reroll_decision` | Recorded Charge choice, owning selection and complete roll. |
| `phases/movement_resolution_flow._apply_advance_roll_reroll_decision` | Recorded Advance choice and active movement selection. |
| `triggered_movement_selection.apply_triggered_movement_distance_reroll_decision` | Recorded distance choice and granting descriptor. |
| `surge_authority._validate_surge_granted_descriptor` | Historical accepted distance reroll, reconstructed in an isolated event log with ordering and exact event checks. |
| `stratagems_core_handlers.apply_command_reroll_decision` | Submitted component choice after accepted Stratagem use. |
| `stratagems_core_handlers._apply_command_reroll_handler` | Accepted Command Re-roll use/CP choice; its sole legal component selection is deterministic. Multiple component choices still emit a request. |

The last row is the only remaining synthetic component result. Its owning player
has already committed to rerolling. A static AST inventory rejects new unaudited
callers and synthetic attack choices. The retired Twin-linked helper, exports and
fan-out imports are removed; prior tests now explicitly submit their choices.

## Evidence and contract

`tests/unit/test_order96_twin_linked.py` exercises successful/failed rolls, both
choices, overlapping sources, Command Re-roll, invalid results and drifted
requests, pending and completed persistence, both viewers, retained Shooting/Fight,
out-of-phase Fire Overwatch and exact replay. The existing Order 84 assignment
regression now calls the shared wound permission path; assigned dice cannot
reopen intrinsic or conditional rerolls. Order 88's absent-Strength consumer now
submits optional rerolls through the facade and checks ordinary reroll events.
The source-backed Aspect Shrine assignment fixture also submits both Twin-linked
choices, restores the subsequent assignment, and verifies exact replay without
reopening the assigned die. Its alternate value seven is an existing generic
descriptor test fixture, not a claim about the real rule's assigned six.
The aggregate run exposed two older Drukhari fixtures that pre-recorded a future
wound before their pending hit-reroll choice. The runtime cannot produce that
order. Those fixtures now let the engine roll wounds normally, using deterministic
positive-path seeds and retaining every original assertion. Independent review
confirmed the fixture repair; production validation remains unchanged. The
same-class test search found no other pending-hit fixture with both pre-recorded
physical dice; the remaining Corsair example already offers a wound choice.

The existing finite dice decision and JSON-safe source payload cover this change.
No external schema or persistence version changes. Exact runtime identity rejects
old automatic-choice saves/replays rather than converting their histories.
The adapter contract documents the new intrinsic producer and ordering.

The pre-gate scope audit keeps the change within wound permission production,
the existing reroll dispatcher, pending-request integrity and the dice history
needed to resume the same attack without rerolling its generated hits. The large lifecycle
module delegates this responsibility to a small typed module; its existing
non-attack paths remain delegated to their owners. No other roadmap remediation
is included. Runtime-bound historical benchmark heads and contract examples are
regenerated evidence, not additional gameplay changes.

Validation and matched slice performance are recorded in
[performance/order96](performance/order96/README.md). Full-game performance and
complete Core certification remain unverified.
