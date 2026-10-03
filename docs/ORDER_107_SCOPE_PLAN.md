# Order 107 / P12D: extra Fight movement distance windows

This order implements C12-06 and the selected
`faq-9657bb5d-72da-4d42-9927-731c9fc0e315-distance-window` obligation.
Unqualified extra Pile In distance applies in the Pile In step of the Fight
phase; extra Consolidation distance applies in its Consolidate step. Overrun
occurs during the Fight step and retains the ordinary three-inch limit.

## Source authority

The controlling complete FAQ is retained in
`data/source_audits/order97/selected-sources.json`, row
`faq:9657bb5d-72da-4d42-9927-731c9fc0e315`, source SHA-256
`cade2b4fcf8c180e7fccd7db3cda6b1d9af1dcf01e2d728abbb3011d7bc286f2`.
Question block 1 describes a rule allowing extra Pile In or Consolidation
distance in the Fight phase. Answer block 2 assigns those permissions to
Pile In (12.02) and Consolidate (12.07), respectively. Core 12.06 permits an
additional Pile In for Overrun but does not extend the extra-distance window.
No new source interpretation or source package is introduced. Original Order 97
gap observations and selected-source bytes remain historical evidence.

## Owner and consumer path

`fight_resolution.py:fight_movement_maximum_distance_inches` previously applied
every matching persistent distance effect without checking the current phase
or step. It now returns the core distance unless the current battle phase is
Fight and the actual `FightPhaseState.current_step` matches the movement kind.
The proposal kind alone cannot establish that permission: an Overrun proposal
has kind Pile In while the actual step remains Fight. An absent Fight state
also grants no extra distance.

The attached-unit distance wrapper applies the same owner to all rules-unit
identities. Request production, accepted-path validation and mandatory-endpoint
reachability consume this shared distance. Existing source IDs, distance
validation, canonical unit identities, target-selection limits, full path
witnesses, rejection/retry and engine-owned mutation remain in force.
No new decision, field, hook, named handler or adapter-visible shape is added;
Contract 44.1 already covers these requests, effects and diagnostics.

The bug-class inventory includes both distance fields and all three producers
of this effect family: generic catalog Consolidation replacement, Aeldari
Sudden Strike and World Eaters Rage-fuelled Invigoration. None of these typed
grants carries an explicit exception to the FAQ window. They share the same
consumer; ability activation timing itself cannot extend that window.
Movement, Charge, reactive Normal Move and Surge use their own movement
budgets and source-bound grants, not this Fight-distance effect. This change
does not reinterpret those independent movement families or add a speculative
exception mechanism. A future explicit out-of-step permission requires its
own source review and typed representation.

## Reproduction and validation

At exact base `1ce35d51f1d5e82eb99e909bb8803a7d54e5a969`, the corrected
`base-red-final.xml` records four failures: ordinary and attached Overrun
requests advertise six inches and the engine accepts full 3.5-inch witnessed
moves after the player legally declines the initial Pile In. Two positive
controls accept the same extended move during Pile In, then restore and replay
after advancing to the Fight step. The attached fixture grants its bonus to
the Leader component and submits the canonical rules-unit identity.
Earlier fixture API/target-identity errors are retained separately and are
not claimed as gameplay defects.

`tests/unit/test_order107_fight_distance_window.py` covers those paths, rejected
Overrun retry at three inches, pending and completed JSON persistence, both
viewer projections and exact replay. Its direct-query matrix covers both
movement kinds, every Fight step and a non-Fight phase containing historical
Fight state. Existing source-distance fixtures now establish their actual
matching step before retaining their original distance and source-drift
assertions. The Aeldari lifecycle test additionally checks that neither bonus
applies in the Fight step and retains its real extended Consolidation path.
Original historical assertion archives and pins are preserved.
`test_order97_secondary_clause_evidence.py` and
`test_phase15d_fight_resolution.py` are retained byte-for-byte from merged
Order 97 commit `19f1c507541321b7c1ed04f80e2c1110a1fa786d`, identical at this
order's base. `data/source_audits/order107/historical-inputs.json` authenticates
them against their unchanged file pins; the existing archive regression also
covers both copies. The Aeldari file has no Order 97 file or changed-assertion
pin and needs no historical copy.

The bounded repair adds a phase/step branch to the existing query and changes
no movement algorithm or cache. The exact-base assessment and serial live
smoke apply; this is not complete-game performance certification. Complete
covered behavior at 85%, quality/type/lint/contract checks, hosted CI and both
clean exact-head reviews remain separate delivery gates. Receipts live in the
sibling `order107-state` directory.

Order 108 starts only in a fresh session after this order merges. Its PR must
update its own **How it is currently done** roadmap cell to describe actual
implemented behavior, and carry that requirement into the following handoff.
Preserve the scoped review policy and queue unsupported hand-edited-history
hardening separately.
