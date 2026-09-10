# September 10 Core Rules roadmap review

Reviewed main `b41e44323f66f494399b763d8c7c23f981d9239f` against the supplied
independent audit. The browser exposed the relevant complete category bodies
and expanded 01.03.02, 02.02.01, 14.02.01 and 20.01.02 on 2026-09-10, with the
last source check at `2026-09-10T13:59:57.629Z`. 40k.app exposed no App-data
version in these observations. Direct web fetches returned 403; the normal
browser pages were readable. Game Datamissions was not fetched in this review;
its v931 claims were compared with the committed transcriptions. No fresh
official-App comparison or co-version equivalence is claimed.

This is a targeted planning review, not a repeat of the reviewer's asserted
25-page exhaustive audit, a runtime source package, or a full-game certification.
The summaries below are paraphrases. Each semantic implementation still needs
the exact operative transcription and complete source tuple required by
[the source policy](CORE_RULES_SOURCE_POLICY.md). The historical August audit,
source registry, packaged source observations and their hashes are preserved.

The violated planning invariant is that every substantiated Core obligation
must have a unique remediation or certification owner before PFINAL, and source
load/merged implementation must not be presented as resolved semantics. The
same-class search covered the entire canonical sequence, category comparison,
implementation-record index, completion counts, dependency milestone and final
certification text. The comparison now derives PR membership from the canonical
table, with fail-closed inventory tests, instead of maintaining a second stale
planning list inside the historical audit.

## Substantiated gaps and qualified source conflicts

| Reviewer item | Source and repository evidence | Disposition and required acceptance |
|---|---|---|
| A1: forced Fight mode | [12.08](https://www.40k.app/rules/12-fight-phase) puts forced opponent selection under Engaging; Ongoing preserves prior model engagements. `core_fight_2026_09/artifacts/package.json` retains this body plus `gw-11e-core-fight:ongoing-consolidation-erratum`, which labels the extra clause Ongoing. P12 queues both. | C12-04/P12B reopens mode-specific source certification. A union is not a policy-approved resolution. Neither an actual co-versioned mirror mismatch nor the correct final mode can be established from an unversioned body and older erratum. Resolve the selected-version body/erratum through the exception workflow; PFINAL checks that resolution and supersession scope. |
| A2: Assault/Shock eligibility | [18.06–18.07](https://www.40k.app/rules/18-transports) impose the on-battlefield Transport and no-embark-this-phase conditions. Assault additionally excludes Advance/Fall Back; Shock has no Core Transport-movement gate. `transport_disembark_state.py`, `transport_disembark_permissions.py`, `assault_disembark.py` and `shock_disembark.py` constrain the shipped modes to Normal/Advance respectively. | New C18-08/P18G aligns Core eligibility without pausing for interpretation. The permitting rule must still authorize the move and may add restrictions. Existing C18-07/P18F retains only the ambiguous prior-engagement owner and its forced-fight consequences; it cannot inherit the Transport's engagements by assumption. |
| B1: reserve policy | [20.02–20.04](https://www.40k.app/rules/20-strategic-reserves) state BR2+ arrival, BR3-end destruction of never-ingressed reserves, the ingressed-Transport cargo and repositioned exemptions, and the next-Charge movement lock. `ReserveDestructionTimingPolicy.core_rules_default` uses final-turn timing; the BR3 constructor/source is Chapter Approved. `MissionPolicyDescriptor` also defaults to final-turn destruction and no blocked arrival rounds. | New C20-02/P20B, after P20. Preserve the separate 20.01.02 final-turn cleanup; BR3 is an additional Core boundary, not a replacement for it. Audit all repositioning/history/effect clauses, exemptions and source-authorized overrides. Existing repositioning history is partial support, not wholly missing. |
| B2: Charge population | [11.04](https://www.40k.app/rules/11-charge-phase) makes closer, within-1-inch-if-possible and engaged-if-possible obligations per model. `phases/charge.py` stores target-unit distances in `ChargeEndpointWitness`; `_charge_ended_closer_to_any_selected_target` and `_charge_preferred_distance_possible` aggregate them. | New C11-04/P11B after P11A; share P12's physical search where applicable, with actual PathWitness validation and typed unresolved results. Preserve unit-level target requirements alongside model obligations. |
| B3: Fights First | [24.13](https://www.40k.app/rules/24-core-abilities) requires every model to have the ability. `_fights_first_effect_for_unit` in `catalog_rule_consumption.py` creates component effects; `FightsFirstRegistry.from_state` promotes each to the current rules unit. | New C24-10/P24J. Distinguish intrinsic population from an explicit unit-wide grant under [01.02](https://www.40k.app/rules/01-core-concepts), including existing conditional Leader and Charge paths. Cover living/retained membership, removal, revival and source scope. |
| B4: Aircraft scope | [23.01–23.04](https://www.40k.app/rules/23-aircraft) includes all movement, targeting and attack exceptions. The reviewer labels part of this 23.01–23.03, but Charge/Fight is 23.04. `AircraftMovementPolicy` removes AIRCRAFT under `HoverModeState`; [24.17](https://www.40k.app/rules/24-core-abilities) only removes the Take-to-the-Skies distance penalty. | Expand C23-01/P23 to every clause. Coordinate 21.03 FLY/FLYING model versus unit authority with P21A. Audit transit, closest-target selection, engagement-only-with-Aircraft movement eligibility, Plunging Fire in both directions, all Charge/melee restrictions, and retire obsolete Hover decisions/persistence with a contract migration. |
| B5: CLOSE-QUARTERS exemption | [10.06](https://www.40k.app/rules/10-shooting-phase) and [17.03](https://www.40k.app/rules/17-monsters-and-vehicles) require both the weapon ability and engagement with the selected target. `shooting_targets.py` exempts the weapon unconditionally in both branches and records `big_guns_never_tire`. | New C17-01/P17 owns both branches and downstream modifier/source identity. The 10.06 penalty has attacking-model scope; 17.03 has target-unit scope. Certify shared attack hosts and overlapping causes before final hit-modifier bounds. Category 17 is no longer REVALIDATE-only. |
| B6: Heavy/FLY | [21.03](https://www.40k.app/rules/21-flying-and-surging) ignores vertical distance only when Take to the Skies is chosen, for FLYING models. [24.16](https://www.40k.app/rules/24-core-abilities) tests every model's movement over the turn. | Expand P21A to committed choice and full-turn per-model movement history. The reviewer's helper name is stale: Order 33 already split `_rules_unit_remained_stationary` from `_rules_unit_within_heavy_movement_allowance`. The latter still uses FLY alone and returns eligible when temporary Movement state is absent. The Order 33 scope record already identifies that lifetime gap. Do not revive the unsupported historical combined clarification. |
| B7: Embark | [18.02](https://www.40k.app/rules/18-transports) excludes units set up this turn. `transports.resolve_embark` checks same-phase disembark in a particular Transport cargo record; that is narrower than all setup this turn. | New C18-09/P18H: shared setup authority, other-Transport disembark, Ingress/reposition, ordinary/reactive paths, explicit overrides and turn expiry. |
| B7: CP cap | Expanded [02.02.01](https://www.40k.app/rules/02-datasheets) bounds final Stratagem cost at zero and no more than one above its base. `StratagemCostModifierRegistry.modified_command_point_cost_with_sources` applies `max(0, raw_modified)` per binding and no upper limit. | New C02-05/P02E: correct ordered arithmetic and final bounds through affordability, spending, failed increased-cost use and source-linked history. |
| B7: sequencing | Expanded [01.03.02](https://www.40k.app/rules/01-core-concepts) orders active mandatory/optional then opposing mandatory/optional, deferring new triggers until the batch finishes. `SequencingParticipant` has no tier; `create_sequencing_decision_request` offers permutations, including cross-owner post-shoot groups. | New C01-04/P01D. Generic tier/actor authority and consumer audit, including active-player switching under 01.03 and round-boundary roll-off assumptions; no content-specific branching. |

## Existing behavior and acceptance omissions

| Reviewer item | Evidence and qualification | Certification owner |
|---|---|---|
| B7: one Normal Move | [09.05.01](https://www.40k.app/rules/09-movement-phase) states the limit. `movement_validation._unit_already_made_normal_move_this_phase` and normal-move records already enforce it. `test_phase10b_movement.py` rejects stale duplicate submissions; `test_phase10s_triggered_movement.py` covers reactive/ordinary sharing and other phases. | PFINAL records the clause and complete facade/lineage/lifetime coverage. The claim of no implementation is not substantiated. |
| B7: objective control first | Expanded [14.02.01](https://www.40k.app/rules/14-objectives) requires control determination before other phase/turn-end rules. `battle_round_flow.py` determines and emits its record before end timing windows; `test_phase11b_objective_control.py::test_end_boundary_control_is_fixed_before_later_end_of_phase_mutation` protects the frozen result. | PFINAL certifies both phase and turn boundaries, reactions, sticky control and scoring. This is existing behavior, with broader facade certification still required. |
| C: Surge | [21.02](https://www.40k.app/rules/21-flying-and-surging) requires its source trigger, no Battle-shock, no engagement and no prior move that phase. | Add every eligibility condition to P21B's acceptance, including stale-request checks. |
| C: Heroic Intervention | [15.11](https://www.40k.app/rules/15-stratagems) restricts VEHICLE users to CHARACTER/WALKER, and Leap to Defend targets to enemies that charged this phase. The engine already has the vehicle check. | Add both clauses to P15C; retain correct existing behavior. |
| C: duplicate Scouts | [24.02](https://www.40k.app/rules/24-core-abilities) has a Scouts exception to ordinary instance choice, including mixed 6/8-inch and universally shared 6/8-inch examples. | P24C2 certifies the lowest non-shared value and still-selectable universally shared values. |
| C: mustering | [25.04](https://www.40k.app/rules/25-muster-armies) permits non-CHARACTER Upgrades, three copies with second/third excluded from Enhancement count, requires Support attachment, and gives Warlord prohibition precedence. `army_mustering.py` already validates Upgrades and required Support attachment. | P25A owns counting/points, P25B bearer eligibility and Warlord precedence, P25C Support attachment certification. Do not report every omission as missing runtime. |
| C: Action interruption | [16.01](https://www.40k.app/rules/16-actions) bars completion after movement except pile-in/consolidation, or leaving the battlefield. `primary_mission_action_interruptions.py` consumes ordinary and reactive move completion events and battlefield departures; `actions.mission_action_interruption_reason_for_displacement` keeps the exceptions. | PFINAL explicitly certifies out-of-phase moves, embark, reserve departure, all Action families, restore/replay and both viewers. Order 34's existing matrix certifies shooting/charge restriction lifetimes, not every Action clause. No new runtime defect was demonstrated by the matrix omission alone. |

## Bookkeeping and delivery scope

Orders 32 and 33 lacked roadmap implementation-index entries. The supplied audit
also predates the merges of Orders 34 and 35. The roadmap now links all four
scope/review records and their verified merge commits. Historical validation
results remain attributed to their original heads.

Nine new PRs are inserted after the completed Orders 1–35 without changing
their published numbering. Later unstarted rows are renumbered, dependency
order is checked, and T-TRANSPORT includes the new eligibility and setup owners.
PFINAL now follows 71 implementation PRs and S-MIRRORS. Only categories 07 and
13 remain without standalone implementation owners.

The generated comparison obtains current category PR membership from the
canonical roadmap. It labels its August source comparisons as historical,
links this refreshed review, and corrects the current Objective Consolidation
assessment without changing an immutable old observation or source registry.

No engine behavior, source-loader identity, adapter-visible choice or schema,
catalog support, named handler or architecture boundary changes in this PR.
The existing adapter contract therefore remains applicable. New gameplay
owners must satisfy its source, regression, replay and viewer-visibility gates
in their implementation PRs. Runtime performance assessment is not applicable
to this documentation/reporting correction.

## Validation for this review PR

The final behavioral suite ran once with coverage and xdist work stealing:
**6,982 passed**, with **85.05% coverage** against the required 85% gate
(829.10 seconds). The bundled Node.js directory was prefixed to `PATH` for
viewer-renderer tests. The suite was not repeated without coverage.
The complete code-quality suite then ran once without coverage, also with
xdist work stealing: **422 passed** (352.86 seconds).

Ruff lint/format, mypy (2,826 files), Pyright, all 11 import contracts,
pre-commit, the exact eight-shard inventory check, the comparison generator
check, engine identity and the relevant Core source-generator checks passed.
The installed-wheel smoke validated 2,638 resources, 27 schemas and six request
families. The TypeScript generated-client/type check, five client unit tests
and live conformance (342 assertions) passed. No runtime identity changed.

The raw external-contract generation gate
`uv run --no-sync python scripts/build_external_contract.py --check --base-ref b41e44323f66f494399b763d8c7c23f981d9239f`
**failed on Windows**: the existing exporters write platform-default CRLF,
whereas the committed JSON examples use LF. Isolated regeneration completed;
all 18 reported differences were line endings only. The exporter scripts are
unchanged from the reviewed base. Separately, committed schemas, manifest,
examples and released-baseline/base-ref compatibility validation passed.
No contract artifact or exporter fix is included in this focused PR, and the
raw regeneration check is not claimed as passed.
