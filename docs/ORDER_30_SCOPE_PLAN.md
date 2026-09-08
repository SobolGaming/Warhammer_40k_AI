# Order 30 / P05B implementation review

Finding: `C05-02`. Base: `8668a87a1b45e0cc58a05e07802771fcb2dad06f`.
The user approved the shared destruction-lifecycle expansion on 2026-09-07.
The user subsequently approved including executable Shoot On Death and a
source-authorized shoot-or-fight alternative in this same PR. Both actions
execute through the shared destruction lifecycle and ordinary attack executors.

The expanded invariant is one retained destruction entitlement and one physical
completion, regardless of the selected attack action. Shooting uses the shared
out-of-phase declaration/attack executor with authority restricted to the
destroyed model. Fighting uses the unit's ordinary Fight activation under the
05.04.05 timing override. Alternative actions consume one source selection;
they cannot grant two attacks or activate unrelated living models.

The concrete shooting consumers are the maintained App-mirror observations of
Hellblaster Squad's For the Chapter! and Hallowed Conclave's Unending Fidelity.
The former includes its own Hazardous death, permits prior shooting, and
automatically passes Hazardous tests for the resulting attacks. The latter
requires that the model has neither shot nor fought this phase. Source-specific
permissions, trigger conditions and exceptions belong to structured descriptors.
This extension does not imply complete Space Marines or Grey Knights coverage.
The browser-rendered faction pages and update page were observed at
`2026-09-08T01:39:45+00:00`; the update page identifies App-data version 946,
released 2026-09-02. The offline `tools/build_retained_attack_sources.py`
generator preserves these observations, historical official faction-pack hashes,
source authority, RuleIR and separate semantic-execution/fieldability statuses in
the pinned `retained_attack_sources_2026_09` data package.

## Invariant and source

An accepted Fight On Death model retains its exact original battlefield
placement until its unit has attacked or the phase ends. It remains present
for all rules purposes. At that boundary, its other destruction-triggered rules
resolve before physical removal. Logical death, retained presence and physical
removal are distinct authenticated states, with one original cause and one
physical completion.

The offline `tools/build_core_fight_on_death_source.py` generator preserves the
complete 05.04.05 observation and v931 retained-presence FAQ in the typed,
hash-pinned `core_fight_on_death_2026_09` package. The maintained-mirror audit is
`data/source_audits/maintained_app_mirrors/fight_on_death_2026_09_07.audit.json`.
40k.app's indexed complete text was observed at `2026-09-07T21:35:45Z`; direct
fetching returned HTTP 403, so no App version or co-version equivalence is
inferred. Game Datamissions identifies App-data v931, dated 2026-08-26. These
are the non-affiliated mirrors authorized by S-MIRRORS. Historical official
PDF provenance remains preserved; neither provider is described as GW hosting.

## Shared owners

| Responsibility | Owner |
| --- | --- |
| Typed retained stage, cause, original pose and immutable continuation | `retained_destruction_state` |
| Finite grant selection before removal; source/condition drift checks | `retained_destruction_selection` |
| Unit attack / phase-end cleanup, suspension and exact-once completion | `retained_destruction_cleanup` |
| Original attack, collateral and rule-source resumption | `retained_destruction_attack`, `retained_destruction_rule`, `retained_destruction_dispatch` |
| Final physical removal | `destruction_removal` |
| Historical cause, source, dice, decision, placement and completion validation | `retained_destruction_history`, `retained_destruction_trigger_history` and existing cause validators |
| Living / retained ability and physical presence | `ability_presence`, `battlefield_presence`, `rules_unit_geometry`, `rules_units` |
| One Fight activation completion despite nested cleanup decisions | `fight_activation_completion` |
| Static catalog and timed RuleIR attack grants | `retained_attack_grants` |
| Destroyed-model shooting, nested executor suspension and Hazardous exceptions | `retained_shooting`, `retained_shooting_history` |
| Prior shooting/fighting applicability and authenticated participation | `model_attack_history` |
| Own-Hazardous casualties, including Feel No Pain | `hazardous_retention`, existing applied-mortal-wound destruction service |
| Hazardous casualties waiting for an individual cause | `hazardous_retention_history` |
| Both-viewer event and context redaction | `adapters.redaction` |

The former remove/re-add functions and continuation modules are removed.
Existing large phase/lifecycle modules delegate to extracted owners rather
than acquiring a second destruction implementation. Generic consumers remain
content-neutral; faction consumers use the same presence services. No named
handler, generic hook family or architecture dependency boundary is added.

Presence consumers cover measurement and visibility in both directions,
datasheet abilities, Stratagem targeting, Charge and attack targets, enemy
Engagement, Pile In and Consolidation constraints, and current retained
component keyword contribution. Movement actors and damage recipients still
require living models; retained bases remain fixed collision geometry.
Nonlethal mortal-wound history is reconstructed so nested cleanup checkpoints
preserve original wounds and transport presence without duplicate application.

## Contract and validation

Contract 12 reuses `select_destruction_reaction` finite submissions and records
the new retention context, public selection/completion events, private source
authority, selected action, nested shooting execution, and
`present_model_instance_ids` target witness. Replay and operator
persistence continue requiring the exact engine build. Old remove/re-add
histories fail closed. See `ADAPTER_DECISION_CONTRACT.md` and
`../contracts/migrations/11-to-12.md`.

The original three facade regressions failed on the unmodified engine at the
intended assertions: pending premature removal, lost accepted abilities, and
Deadly Demise resolving before the grant choice. Current focused coverage uses
real canonical objects and LocalGameSession decisions for Shooting/Fight,
acceptance/decline/failed grants, multiple grants, fixed attacks, nested damage,
collateral retention, destroyed transports, both viewers and restore at pending
and completed boundaries. Existing phase consumer and historical forgery tests
are migrated to uninterrupted retained presence. The catalog RuleIR integration
also exercises a real rule producer pausing for Feel No Pain during cleanup.
The source-consumer regressions execute For the Chapter! (including own-Hazardous
death, Feel No Pain and automatic Hazardous success), both alternatives of
Unending Fidelity, prior-action ineligibility, destroyed-model-only shooting,
nested retaliatory shooting and execution-history forgery rejection. Checkpoints
are restored at decision boundaries and both viewers' authority redaction is
checked through the facade.
Checkpoint regressions reject impossible retention stages, source/action and
effect-ownership drift. Completed shooting history also authenticates declaration
and attack completion, automatic Hazardous authority, exact-once cleanup and
model participation. The original faction audit generator validates its own
audit/package inventory while the retained-attack generator validates its separate
source package; sharing the faction scope no longer implies sharing an audit.
The weaponless retained-shooting regression exposed an impossible proposal in
the shared out-of-phase request builder. It now uses ordinary executor completion
when no legal shot exists, before enqueueing a proposal. This also prevents the
same deadlock for other out-of-phase shooting consumers; no empty declaration or
new adapter decision is introduced.
The final presence audit also covers the attacking side of restricted-range
queries and their scenario construction. Catalog range checks, generic targeting
restrictions, Lone Operative and visibility consumers use the shared retained
presence view; explicit living-model mission-action queries retain their own
policy. A facade regression executes a retained shot through a persisted range
restriction and checks the same model's ability and Lone Operative measurements.
Retained effect replacements use the existing GameState removal/record mutators
after constructing and authenticating the replacement, with no intervening
decision or event boundary. Source-authority JSON uses LF bytes and a matching
reviewed pin so Windows and Linux authenticate the same committed artifact.

Final gate results are recorded with the pull request. The required validation
includes Ruff, both type checkers, import contracts, one complete behavioral
coverage run, the separate code-quality suite, regenerated eight-shard inventory,
source/build/contract artifact checks against the base, TypeScript client and
conformance checks, installed-wheel smoke and pre-commit.

## PR #434 review corrections

The retained-shooting executor now serializes its parent cause and reconstructs
one validated root-to-child chain. Completion, parent resumption and historical
validation use this same authority instead of treating globally sorted effects
as a stack. Facade regressions explicitly exercise both lexical parent/child ID
orders, pending-child restoration, exact replay, child-before-parent cleanup and
exactly-once physical removal. Missing, self-referential, branching or cyclic
parent links and disagreement with start history fail closed.

Persisted retained grants now use the existing rules-unit effect application
owner, including canonical attached identities, physical components, split
predecessors and effect-instance deduplication. The real Unending Fidelity
regression exposed the preceding selected-target comparison as another instance
of the identity mismatch: Stratagem options name components while attack context
names the rules unit. That comparison now resolves the current rules-unit view;
the existing option IDs and generic canonical effect targets remain intact.
Both attached-unit attack alternatives, restore boundaries and exactly-once
cleanup are covered, along with split-predecessor and duplicate-alias discovery.

## Explicit boundaries

P02D's per-model keyword schema and P05C's post-removal former-footprint
measurement remain separate roadmap items. Additional faction coverage beyond
the two approved source-backed attack consumers remains separate. This PR adds
no bespoke named handler, movement rule or out-of-scope catalog material.
