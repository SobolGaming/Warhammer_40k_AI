# Order 98 / PSOURCERECON — source reconciliation

Order 98 repairs eight runtime source rows identified by the Order 97 inventory.
It is source governance. It does not change movement, deployment, visibility,
Battle-shock, Scouts, or attached-unit gameplay, and it does not certify Core
Rules compliance. CAUDIT-01 and PFINAL stay open.

## Repaired rows

| Source ID | Repair |
|---|---|
| `gw-11e-core-rules:command-phase:start-of-command-phase` | Controlling text is the complete selected 08.01 sentence. |
| `gw-11e-core-rules:command-phase:gain-core-cp` | Controlling text is the complete selected 08.02 sentence. |
| `gw-11e-core-rules:command-phase:battle-shock` | Controlling text is the complete selected 08.03 row, including examples. |
| `gw-11e-core-large-model-setup:large-model-setup` | Controlling text is the complete selected 03.02.02 record. |
| `gw-11e-core-rules:movement-phase:move-units-step` | Controlling text is the complete selected 09.02 row. |
| `gw-11e-core-rules:other-concepts:visibility-classifications` | Locator is 06.01. The transcription stays the 06.01 visibility definitions. |
| `gw-11e-core-abilities:faq:alternating-scout-moves` | Live consumer is `prebattle_integrity.validate_prebattle_alternation_restore`. |
| `gw-11e-core-rules:attached-units:bodyguard-unit-destroyed` | Live consumer is `starting_attached_unit_records_for_army`. |

Each previous heading, excerpt, locator, or consumer ID remains loaded with
semantic execution status `not_certified`. Current rows keep their previous
load status and semantic execution status. Battle-shock stays
`partial_engine_runtime`.

## Provenance

The 2026-08-26 search-index observation remains heading-only. Its observation
fingerprint is unchanged. Command and Move Units mirror evidence that the
legacy 40k.app policy authorizes keeps that immutable observation, including
the historical heading or excerpt transcription. Project-reviewed evidence
carries the complete selected transcription and must match the controlling
source row. The official Command PDF remains corroboration; the Battle-shock
PDF excerpt stays shorter than the selected row because the selected row
includes examples.

The large-model ellipsis that joined a deployment fragment to the Strategic
Reserves AIRCRAFT exception is superseded. Deployment, Strategic Reserves, and
disembark clauses stay separate in the selected text. This row does not newly
certify disembark or reserve consumers owned by other packages. `setup_policy`
is unchanged.

The visibility transcription is the 06.01 definitions. The repair does not add
the 06.01.01 default-observer sentence and does not prove that clause.

Move Units wording differences from the superseded excerpt do not by themselves
establish a gameplay defect. Selection consumers were revalidated.

## Authority and non-goals

No decision type, finite option family, proposal kind, or adapter-visible
payload changes. The existing adapter decision contract remains sufficient.
No named handler, generic hook family, or faction content is added. Orders 84
and 95 are unchanged. Later gameplay orders, including C03-12 / P03L and the
06.01.01 default-observer requirement, stay scheduled.

There is no hot-path or algorithm change. Full-game performance remains
deferred under Order 32. Runtime identity changed with the source packages, so
the existing runtime-bound head reports were remeasured on this host. Historical
baselines, fixture proofs, and numeric budgets are unchanged. Commands and
hashes are in [the refresh record](performance/order98/inherited-refresh.json).
