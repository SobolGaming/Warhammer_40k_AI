# Order 105 / P06D: all-model Hazard wound count

This order implements C06-04 and selected `06.03-obligation-04`. A failed
Hazard roll causes three mortal wounds only when every model currently supplying
rules authority in the affected unit is a MONSTER or VEHICLE. A MOUNTED model
and a VEHICLE model in one unit therefore cause one mortal wound per failure.

## Source authority

The complete controlling blocks remain in
`data/source_audits/order97/selected-sources.json`:

- `rule:06:06.03:1`, source SHA-256
  `0edce95045a10290c9b6f2f514bbcb7ba5b6ba35cb0585ff3bc0019f19d6b7fa`,
  blocks 1-4: D6 fails on 1-2, ordinary consequence is one mortal wound,
  three instead if each model is MONSTER/VEHICLE, with multiple rolls simultaneous.
- `rule:06:06.03.01:1`: Hazardous test means the same operation as Hazard roll.
- `faq:5928ab6e-7113-42c8-9085-4291faddae09`: combined Infantry and
  MONSTER/VEHICLE units suffer one mortal wound per failure. The FAQ is a mixed
  model example of the general all-model condition, not an alternative union-keyword rule.

Model keywords are already canonical source-owned tokens. Existing rules-unit
presence authority excludes removed casualties and includes a destroyed model
retained for its rules. This repair consumes that authority; it introduces no
new casualty or retention timing.

## Owner and complete consumer path

`engine/hazard.py:hazard_mortal_wounds_per_failed_roll` owns the count for both
physical units and `RulesUnitView`. It examines each rules-present model's own
keywords. It does not infer every-model eligibility from the union of unit
keywords. Empty units retain the ordinary count and cannot vacuously qualify.

The shared owner serves:

1. `attack_sequence_hazardous.py`: one canonical attacking rules unit after
   attacks, including attached components and retained models.
2. `emergency_disembark.py`: the complete cargo rules unit. Different component
   kinds no longer cause a disagreement exception.
3. `transports.py`: ordinary physical-unit Combat Disembark.
4. `phases/movement_rules_unit_disembark.py`: each attached Combat Disembark
   roll carries the same count calculated from the entire group, rather than
   an independent component count.

Existing simultaneous-roll records freeze the count before allocation. The
shared mortal-wound decisions, casualties, Feel No Pain, transport placement,
viewer projections, persistence and replay retain their current owners.
There are no new choices, fields, handlers or contract versions. Contract 44.1
already expresses the count and its event/persistence payloads; only the source
predicate producing that value changes. Current runtime identity and generated
contract examples are regenerated with existing tools.

## Reproductions and validation scope

`tests/unit/test_order105_hazard.py` covers MOUNTED/VEHICLE and the separate
INFANTRY/VEHICLE FAQ case, MONSTER/VEHICLE positive controls, removed and retained
model membership, attached Combat and Emergency Disembark, and ordinary/attached
Hazardous declarations through `LocalGameSession`, restoration and exact replay.
The transport cases use complete cargo inventories and legal coherent Combat
placements. Failed-roll and wound-count assertions remain explicit.

The earlier Hazardous FAQ parametrizations represented every model as both
Infantry and a large model. Their fixtures now represent distinct model kinds,
preserving the original one-wound assertions. A separate control proves that
each model having a large-model keyword still qualifies even if it also carries
another keyword. Original Order 97 pinned bytes of the edited shooting test are
already authenticated by `data/source_audits/order103/historical-inputs.json`;
historical pins and archives remain unchanged.

The base reproduction and final gate receipts are retained outside the worktree
in the sibling `order105-state` directory. Failed fixture setup attempts are not
legal gameplay reproductions or passing delivery gates. The exact-base
performance assessment selects the existing serial live smoke for this bounded
rule predicate change; no deliberate performance change is included.

The corrected consumer regressions reproduce eight failures and six passing
controls against the unchanged base runtime at
`5c3de70b20089c9adbede4326a74155f892de1ff` (`base-red.xml`). All base `src/`
bytes were checked against that Git revision before running them. Failures cover
the shared mixed-model count, both attached Combat distributions, ordinary and
attached Emergency cargo, and both ordinary and attached Hazardous facade paths.
The attached Infantry/Vehicle Emergency case reaches the former component-count
disagreement exception. The other failures reach the incorrect three-wound
consequence. Current focused tests retain the actual failed-roll, applied damage,
restoration and replay assertions.

Full covered exact behavioral inventory at 85%, all quality/type/lint/import,
generated/contract/client/package checks, hosted CI and both independent clean
exact-head reviews remain required. This scope record does not itself certify
those gates, the complete Core Rules, full-game performance or PFINAL. Order 106
must start in a fresh session after this order is merged.
