# Order 92 / P04D — random melee attack allocation

Status: implemented and independently approved under the owner-approved provisional convention.
Validation: [performance and delivery evidence](performance/order92/README.md).
Base: `ad096b7f238bd623c7c1c17c0cd42d70564e87d8` (Order 91 / PR #513).

## Invariant and source boundary

Each selected physical melee weapon generates its own attack total exactly once.
The controlling player's recorded allocation must conserve that total and assign
at least one attack to every selected target. Invalid submissions, restoration,
target replacement and attached-unit lowering must not regenerate the total,
change the committed weapon, or make an unrecorded player choice.

The retained Order 84 evidence identifies these source rows:

| Row | Complete row SHA-256 |
|---|---|
| `rule:02:02.02.03:1` | `5e03456e767c79c7a9e156ca6f841fd27cd9fc9f66d692f9efdf54e5799cf607` |
| `rule:04:04.03.02:1` | `49e9dfc1d181a24c7f074ca95e396f364c88cb335fb98f4c6aad1b51b6659dee` |

On September 27, the exact [GDM page asset](https://game-datamissions.com/_next/static/chunks/app/11th/rules/core-rules/page-ec6350d45d9ddeb5.js)
was retrieved and its SHA-256 verified as
`6f4d27c5670489e9b6310bb8f43e837d8abaf2d5f7a8c8938f56690190edad0e`,
matching `data/source_audits/order84/audit.json`. The existing literal-only
extractor was used; no downloaded code was executed. No random-A/split timing
clarification was found in that capture's FAQ inventory. This revalidation does
not change the historical September 24 observation or invent an App-data version.

The live 40k.app [02.02.03](https://www.40k.app/rules/02-datasheets#02.02.03)
and [04.03.02](https://www.40k.app/rules/04-making-attacks#04.03.02) accordions
were also read on September 27 and contain the same timing conflict:

- 02.02.03 determines random A while generating attacks in Resolve Attacks.
- 04.03.02 requires exact per-target split counts while selecting targets,
  and Gather Attack Dice subsequently consumes those declared counts.
- 04.02 also limits the number of targets to the weapon's A characteristic.

The existing `core_random_profiles_2026_09` package preserves the first clause.
Neither source supplies an explicit exception reconciling these requirements.
Order 84's C04-05 closure instruction specifically prohibits inventing timing.

On September 27 the owner explicitly approved this **provisional engine convention**,
not an official FAQ: commit every physical melee weapon and profile, generate each
selected random A once, then choose targets and declare exact attack splits. The
complete unit declaration validates atomically before selected-target effects and
attack resolution. Invalid retries preserve both choices and random results.
Shooting timing is unchanged. The immutable physical result is separate from
current profile modifiers and single-target Cleave. Cleave's additional attacks
cannot be distributed across split targets. Runtime convention ID:
`core-rules-owner-convention:order92:random-melee-pretarget:2026-09-27`.

`select_melee_weapon` offers a model's primary weapon/profile, followed by each
optional physical Extra Attacks weapon. All finite choices precede dice. The
recorded `melee_weapons_committed` event owns raw results; pending requests project
that authority. The existing parameterized declaration carries physical weapon
IDs and exact positive counts, and lowering never rerolls a committed weapon.
For these committed activations, replacement under 04.03.03 offers a new destination or explicit forgoing for each
invalid unresolved allocation. It preserves its count, selected weapon/profile,
and accepted ability choices. Attack resolution retains its ordinary modifier
services. No new named handler, faction rule, or hidden-information exception is
introduced.

## Authoritative path and same-class search

- `phases/fight.py` emits the melee request after activation hooks and applies
  accepted declarations for ordinary and forced/retained Fight hosts.
- `fight_rules_unit_melee.py` owns canonical attached-unit aggregation, component
  lowering and target identity translation.
- `fight_weapon_selection.py` owns weapon inventory, selection validation and
  lowering to shared attack pools. Committed activations consume the stored
  physical budget; uncommitted paths retain their existing timing.
- `melee_attack_counts.py` now owns count validation extracted from the oversized
  `fight_resolution.py`; the unsupported random-split shortcut has been removed.
- `attack_sequence` owns target/group ordering and hit/wound/damage resolution.
  `target_replacement` is the shared replacement decision surface; its
  consumers now include committed Melee alongside Shooting and Charge, preserving
  the selected allocation counts.
- `lifecycle_fight_prevalidation` validates before queue pop. Dispatch metadata,
  interaction metadata, proposal schemas and `ADAPTER_DECISION_CONTRACT.md` must
  cover any additional commitment/allocation stage.
- Accepted events feed `model_attack_history`, Fight continuation checkpoints,
  random-profile authentication, projections and replay. Commitment alone must
  not prematurely claim that the unit has made attacks.

The search includes fixed/random A, single/split targets, physical weapon copies,
Extra Attacks, Cleave, One Shot, duplicate ability selections, attached source and
target components, retained Fight on Death, forced fights, stale proposals and
restore authentication. No faction-specific handler or alternate adapter path is
needed.

## Planned acceptance and delivery gates

Facade regressions must demonstrate weapon commitment, individual random rolls,
recorded splits, exact total conservation, single-target Cleave, split exclusion
of Cleave, Extra Attacks, physical ownership, attached/retained hosts, target
replacement, malformed/stale/drifted rejection without reroll, both viewer
projections, JSON round-trips, pending/completed restore and exact replay.
Tampered totals, physical IDs, source decisions and dice evidence must fail closed.
Static audits should prevent the unsupported shortcut or fresh rolls during retry.

Measure a versioned matched base/head component workload;
retain setup/query timing, work counts, dependencies and hardware. Full-game
performance certification remains separate and unmeasured.

The active CI workflow and generator documentation were inspected. After focused
tests and scope/diff audit, delivery requires the AGENTS.md coverage suite and
code-quality suite, type/lint/import checks, shard inventory, engine identity,
external contract against the exact base, TypeScript generation/check/unit tests,
HTTP conformance, installed-wheel smoke and all-file pre-commit checks. New test
files require a complete representative JUnit profile and regenerated eight-shard
inventory. Final independent subagent review and repair/review repetition must
approve the completed implementation before the first push or remote PR creation.

The initial pytest diagnostic was discovered to use an editable installation from
another checkout. It is not used as baseline evidence. The editable installation
was corrected before all reported implementation tests. Matched component
measurements explicitly select their source tree through `PYTHONPATH`.

## Scope audit and independent review

The change is confined to the Fight declaration boundary, physical weapon identity,
committed-pool authority, and the existing shared replacement decision. Large Fight
modules lose their declaration/count responsibilities to small typed modules. No
new package boundary, faction-specific branch, rule-text parser, or named semantic
handler was introduced. Contract version 40.1 adds the finite commitment choice,
optional physical declaration ID and immutable target facts; persistence remains
40.0 with exact runtime identity. Fixed-only melee and shooting retain their
existing event and RNG history.

The first independent review found that single-target omitted attack counts and
accepted pool identities were not fully authenticated on restore. The repair
binds every pool to the chosen pre-target weapon selection context and physical
budget. Target model/keyword facts are frozen with that inventory, so Cleave is
re-derived correctly even after casualties. Eight tampering regressions cover
single-target counts, physical model/wargear and profile changes with and without
Cleave. Completed Cleave and split sequences round-trip and replay.

The second review identified a fixed/random attached-unit eligibility mismatch.
A shared `requires_melee_commitment` predicate now gates both source inventory
recording and commitment. A regression equips the engaged bodyguard with fixed
melee attacks while its random-A Leader is outside engagement. The independent
reviewer reproduced the repaired path and explicitly approved the implementation
with no remaining concrete findings. Required aggregate gates remain separate
from that implementation review.
