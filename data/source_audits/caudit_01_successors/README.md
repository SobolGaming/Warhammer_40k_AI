# CAUDIT-01 Core successor evidence

This audit consolidates 212 reviewed obligations across 16 Core sections on GitHub main
`dec50bca2394c755a0d5fb76e6659882b388c032` (tree
`f58dbb84417cf2f8d5418bd0cbd0df133635aa01`). The
[successor inventory](successor-inventory.json) records bounded assertions and
their limits. Read it beside the archived [Order 135 inventory](../order135/current-inventory-category-migration.json)
and [retained source capture](../order135/retained-current-sources.json).
CAUDIT-01, PFINAL and faction Gate 0 remain open.

| Historical population | Bounded | Partial | Unreachable and open | Unreviewed candidates | Missing evidence | Reproduced gap | Source drift |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 398 rows with a missing test path | 185 | 25 | 1 | 177 | 9 | 1 | 0 |
| All 1,083 rows | 185 | 25 | 1 | 849 | 20 | 1 | 2 |

The 398 rows contain 868 missing references, of which CI69 explicitly retired
866. The first 128 reviews came from the baseline (57), the battle-round and
modifier review (32), and the healing, datasheet and attack review (39).
The six follow-on receipts add 84 distinct reviews. The three ownership
draft bindings were already counted in the baseline. Each reviewed row
identifies source block ordinals and hashes, engine owners, assertion or
diagnostic records, and scope limits. The JUnit entries preserve the exact
passing case IDs and identify the original Windows runs by hash.

## Initial review

| Section | Bounded | Partial | Unreachable and open | Unreviewed candidates |
| --- | ---: | ---: | ---: | ---: |
| 01 Core Concepts | 54 | 0 | 0 | 23 |
| 02 Datasheets | 24 | 1 | 0 | 15 |
| 04 Making Attacks | 24 | 4 | 0 | 3 |
| 07 Battle Round | 13 | 7 | 1 | 0 |

- **Section 01.** The full Section 01 suite passed 527 cases. The ownership
  witness covers two native datasheets in one configured army. The pronoun
  wording uses that controlling-player identity and has no separate resolver.
  Other bindings retain their individual ownership, fixture and consumer limits.
- **Section 02.** The modifier runs passed 104 cases plus 15 consumer cases.
  The follow-on 45 cases cover healing, revival and characteristic contracts.
  The independent objective-control module passed two cases. For dash Movement,
  the reserve validator accepts setup and produces a transition batch. Committed
  reserve placement remains open.
- **Section 04.** The 20 attack-completion cases include SF04-002 and SF04-003.
  Declaration alone earns no shooting status. A model can finish while its unit's
  attack remains in progress. Those three obligation bindings already counted
  in the baseline. The follow-on 134 cases cover shooting, Fight, declaration
  and resolution. The inventory preserves four partials for weapon and target
  selection, downstream single-target use, one melee weapon spanning two
  target pools, and the in-progress nonempty unit-has-fought negative control.
- **Section 07.** The 44 section cases include both preselected first-player
  roles over four turns. The six independent mission consumer cases exercise
  ordinary turn-end scoring. The supported primary mission matrices and pools
  do not reach the two legacy round-end Purge the Foe scoring rows. The actual
  achieved round-end score for `07.03-mission-after` remains open. The inventory
  preserves the assignment and compiler findings alongside the passing boundary
  order assertions.

## Follow-on receipts

| Cohort | Bounded | Partial | Reproduced gap |
| --- | ---: | ---: | ---: |
| Sections 05 and 13, Attack Sequence, visibility, Hidden and terrain membership | 29 | 4 | 0 |
| Section 08, Command | 8 | 1 | 0 |
| Sections 06, 10 and 20, Hazardous, Shooting and Strategic Reserves | 15 | 3 | 0 |
| Sections 12, 14 and 19, Fight ordering, Objectives and Attached Units | 8 | 5 | 0 |
| Sections 15 and 24, Stratagem decisions and Twin-linked | 5 | 0 | 1 |
| Sections 16 and 24, Actions, Devastating Wounds and Melta | 5 | 0 | 0 |

- The Attack Sequence receipt preserves the four partials. They concern a
  downstream suffers-damage consumer, a retained non-Demise destruction
  trigger, a baseless non-vehicle comparison, and continuation through both
  wounded-group orders. Natural Epic Challenge and the Solid threshold are
  local diagnostics with their original fixture limits. Terrain movement
  remains outside the Section 13 review.
- Section 08 proves ordinary Command ordering and an achieved active-player
  mission award after the non-mission rules. The simultaneous two-player
  score remains partial. The two current assignment packs allow Command-end
  primary awards only for the active player.
- The Hazardous, Shooting and Strategic Reserves receipt distinguishes
  requested dice and mixed-unit evaluation from combined native multi-weapon
  damage. The terminal reserve fixture leaves independent same-body
  destruction eligibility and ordinary final-turn progression open.
- The Fight and attached-unit receipt retains the unequal Remaining Combats
  and attack-caused bearer lifetime gaps. The legacy cross-band attempt was
  rejected at collection. The operative Objective Control wording predicates
  range on the unit and positive OC on a member. Order 109 and the current
  checkpoint support that distinction. The archived same-model wording is
  preserved and its row remains partial.
- The Counteroffensive diagnostic used paired native branches from a prepared
  Fight checkpoint. Declining the stratagem offered Normal and Overrun for
  the newly engaged target. Spending 2 CP selected Normal and advanced to
  melee, although the engine classified both types as legal. The inventory
  counts one reproduced gap under `15.12-next-selection` and cross-references
  `12.04-fight-type`. The runtime fix is separate.
- The subsequent Actions and weapon damage receipt verifies atomic exclusion
  and same-turn uniqueness, a normal attack resolving before deferred
  Devastating Wounds, and a declaration-time Melta bonus retained after the
  near target model dies. The native damage diagnostics start from prepared
  Shooting checkpoints. The unadmitted geometry attempt carries no
  gameplay credit.

## Source observations

The reviewed source matches use the timestamped, unversioned Game Datamissions
Core observation. The inventory pins the source observations by capture and
row hashes. The June official PDF corroborates the Armies passage. The retained
and live mirror captures support the separate You paragraph. Newer source
intake, including the separate Fall Back workstream, is outside this review.
The selected Windows suites establish the cited assertions on the audited base.

## Shock Disembark

The selected Section 18 mode cases show immediate charge ineligibility after
Shock Disembark. The selected Section 16 Action case shows the Action lock
through its own boundary. The separate local transport diagnostic used actual
facade decisions on native Wave Serpent, Prince Yriel, Autarch and Lord
Exultant bodies. It starts at a constructed Command checkpoint with explicit
Core permission and embarked cargo. Faction grant admission and normal setup
remain outside its scope.

The diagnostic observed `charge_unit_disembarked` through ordinary and mission
turn-end processing, including resumed handlers after JSON restore at the
genuine Tactical A Tempting Target scoring decision. Both sessions committed the
same single 5 VP transaction. Expiry cleared the restriction before opponent
Command. The second expiry invocation found no remaining state. Exact replay
reproduced 20 decisions and 166 events. The inventory includes the observed
windows, expiry, scoring and replay receipt.

The diagnostic ran in 55.32 seconds including session startup and used
profiler hooks to observe the real handlers. It remains outside the selected
suite. The result supports Core 18.07 and the Shock-specific application of
FAQ62. The broader FAQ62 evidence remains open and the historical counts exclude
this diagnostic.
