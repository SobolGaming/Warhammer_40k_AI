# Current Aeldari loadout and charge-completion correction

The [authenticated source review](AELDARI_CURRENT_SOURCE_REVIEW.md) supplies two
bounded corrections against base `5e26b4b4791d0c25579faebc28394ec25bb38b24`.
Voidscarred specialist default close-combat weapons flow through the unchanged
loadout parser and native constructor. Sudden Strike moves from selected-to-fight
to the existing captured charge-completion lifecycle and expires at actual turn
end. Neither correction adds a datasheet, geometry, battle size or faction.

The content-neutral `move_completion_effects` service composes a finite use/decline
decision with the existing completion registry, trigger history and sequencing.
Its Aeldari provider requires the loaded Battle Focus ability, available token,
same-unit phase eligibility and same-manoeuvre phase quota. Only accepted use
records the six-inch effect and source spend; existing conditional refund logic
runs afterward. Decline and rejected submissions consume nothing. Captured source
participants remain stable when mutable resources change. Ordinary and interrupted
charges use their effective action actor, while expiry and phase accounting retain
the actual turn owner. The interrupted-charge restore registry recognizes the new
shared completion decision under its existing frame restrictions.

Native attached charge testing reproduced a prerequisite in Flitting Shadows:
generated `select_charging_unit` passed `attached-unit:own:body`, but the old
charge-declaration provider looked only in physical army units and raised an
unknown-unit error. That provider now resolves the canonical rules-unit view and
uses shared ID-based spend/quota/refund accounting. Its source predicates, trigger,
effects and expiry remain unchanged. Movement/setup Flitting and other manoeuvres
are outside this prerequisite. Lone and attached real declaration paths remain
covered; accepting attached Flitting suppresses Sudden Strike for that unit.

Focused regressions construct source-backed component units and submit real
facade actions and physical witnesses. They cover legal eight/ten-model and
illegal eleven-model specialist loadouts, specialist melee choices, charge-time
use/decline, repeated and invalid submissions, public views, multiple chargers,
attached canonical IDs, Wayleaper refund success/failure, a move longer than three
inches under the six-inch permission, actual turn-end expiry, and native opponent
charge followed by generated Heroic Intervention. Pending and accepted states
round-trip and replay, including acceptance after restoring the Heroic choice.

These component checkpoints do not certify full rosters or earlier setup/play.
Attached casualty premises use existing engine mortal-wound records and an explicit
replay root after those prior casualties. Resource-exhaustion and last-token cases
start from declared prior accounting. Descriptor absence is an intentionally
incomplete provider-input negative, not legal native source construction. Current
native admission remains sixty units across packages; the regenerated Court
package retains its exact twenty-seven IDs. The separate ninety-three later-IR
inventory and complete-faction/geometry claims remain unchanged.

All final local/hosted gates, matched performance qualification and both exact-head
independent reviews remain required. Focused tests alone are not final delivery.
