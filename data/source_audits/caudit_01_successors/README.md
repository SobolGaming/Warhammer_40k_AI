# CAUDIT-01 Core successor evidence

This audit covers Sections 01, 02, 04 and 07 on GitHub main
`dec50bca2394c755a0d5fb76e6659882b388c032` (tree
`f58dbb84417cf2f8d5418bd0cbd0df133635aa01`). The
[successor inventory](successor-inventory.json) records bounded assertions and
their limits. Read it beside the archived [Order 135 inventory](../order135/current-inventory-category-migration.json)
and [retained source capture](../order135/retained-current-sources.json).
CAUDIT-01, PFINAL and faction Gate 0 remain open.

| Historical population | Bounded | Partial | Unreachable and open | Unreviewed candidates | Missing evidence | Source drift |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 398 rows with a missing test path | 115 | 12 | 1 | 261 | 9 | 0 |
| All 1,083 rows | 115 | 12 | 1 | 933 | 20 | 2 |

The 398 rows contain 868 missing references, of which CI69 explicitly retired
866. The 128 reviewed bindings are disjoint across the baseline (57), the
battle-round and modifier review (32), and the healing, datasheet and attack
review (39). The three ownership draft bindings are already in the baseline.
The inventory has one row per historical category and obligation ID. Each
reviewed row identifies source block ordinals and hashes, engine owners,
current assertions, full passing case IDs and scope limits. The JUnit entries
identify the original Windows runs by their hashes and passing counts.

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
