"""A paid late Charge option does not change the no-additional-CP flight comparison."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import pytest

from tests.support.faction_batch01 import Scene, anchor, locate, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section11_fixtures import begin, propose, roll, targets
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.ai.charge_flight_admission import (
    ChargeFlightOffer,
    ChargeFlightUnresolved,
    ChargeFlightUnresolvedReason,
    ProvenChargeFlightAdvantage,
    _plain_charge_supported,  # pyright: ignore[reportPrivateUsage]
    choose_proven_charge_flight_mode,
    inspect_charge_flight_offer,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_move_resolution import resolve_charge_move
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import charge_move_violation_code
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    stratagem_window_context_from_request,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

OWNER = "owner"
MOVER = "own:first"
TARGET = "foe:target"
START = Pose.at(10, 20)
BLOODTHIRSTER = "000002582"
WITNESS_BUDGET = 9.0
RNG_LABEL = "charge-flight-late-wall-6"
VIEWER = ViewerContext.for_player(OWNER)
GORE_ID = ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID
GORE_SOURCE = ir.GORE_HUNGRY_ONSLAUGHT_SOURCE_ID


@pytest.fixture(scope="module")
def definitions() -> Section02Definitions:
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    catalog = package.army_catalog
    row = next(r for r in identities.detachment_rows() if r.detachment_id == "blood-legion")
    if not any(d.detachment_id == row.detachment_id for d in catalog.detachments):
        detachment = DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id="chaos-daemons",
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=tuple(s.datasheet_id for s in catalog.datasheets),
            force_disposition_ids=tuple(
                sorted({row.force_disposition_id, "take-and-hold", "purge-the-foe"})
            ),
            source_ids=row.source_ids,
        )
        package = replace(
            package, army_catalog=replace(catalog, detachments=(*catalog.detachments, detachment))
        )
    return Section02Definitions(package, 0.0)


def _wall() -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=13.25,
        center_y_inches=20,
        width_inches=1,
        depth_inches=24,
        display_template_id=None,
    )
    return TerrainFeatureDefinition(
        "charge-barrier",
        TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        13.25,
        20,
        1,
        24,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 13.25, 20, 0, 1, 24, 10.5),),
        classification=TerrainAreaClassification.DENSE,
    )


def _battle(
    definitions: Section02Definitions, cp: int, *, rng: str = RNG_LABEL, other: bool = False
) -> Scene:
    own: tuple[UnitMusterSelection, ...] = (selection(definitions, BLOODTHIRSTER, "first"),)
    if other:
        own += (selection(definitions, BLOODTHIRSTER, "other"),)
    b = scene(
        definitions,
        own,
        (selection(definitions, BLOODTHIRSTER, "target"),),
        phase=BattlePhase.CHARGE,
        detachment_id_by_faction={"chaos-daemons": "blood-legion"},
        seed="gore-hungry-onslaught",
        rng_seed_label=rng,
        terrain_features=(_wall(),),
    )
    locate(b, MOVER, (START,))
    if other:
        locate(b, "own:other", (Pose.at(10, 13.5),))
    locate(b, TARGET, (Pose.at(21, 20),))
    if cp:
        b.state.gain_command_points(
            player_id=OWNER,
            amount=cp,
            source_id="charge-flight-timing:fixture",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    anchor(b)
    return b


def _context(b: Scene) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(b.session.view_for_context(viewer=VIEWER), choice_seed=0)


def _issue_onslaught_option(b: Scene, unit_id: str = MOVER) -> str | None:
    # Only offer decoding is a seam if #744 stops using the ordinary finite
    # Stratagem option encoding. Do not infer eligibility from CP or keywords.
    request = _context(b).request
    matches: list[str] = []
    for row in request["options"]:
        if row["option_id"].startswith(f"use-stratagem:{GORE_ID}:"):
            payload = row["payload"]
            assert isinstance(payload, dict)
            binding = payload["target_binding"]
            assert isinstance(binding, dict)
            if binding["target_unit_instance_id"] == unit_id:
                matches.append(row["option_id"])
    assert len(matches) <= 1, matches
    return matches[0] if matches else None


def _choose(b: Scene, option: str, *, label: str) -> DecisionRequest:
    req = _context(b).request
    status = b.session.submit_viewer_option(
        viewer=VIEWER, request_id=req["request_id"], option_id=option, result_id=label
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert status.decision_request is not None, status
    return status.decision_request


def _offer_and_path(b: Scene) -> tuple[ChargeFlightOffer, PathWitness]:
    context = _context(b)
    assert context.request["decision_type"] == "select_charging_unit"
    offer = inspect_charge_flight_offer(context, unit_id=MOVER, target_id=TARGET).offer
    assert offer is not None
    end = Pose.at(10 + offer.target_filter_distance_inches, 20)
    return offer, PathWitness.for_paths(((offer.model_id, (START, end)),))


def _events(b: Scene) -> tuple[str, ...]:
    return tuple(e.event_type for e in b.session.lifecycle.decision_controller.event_log.records)


def _grant_active(b: Scene) -> bool:
    return any(e.source_rule_id == GORE_SOURCE for e in b.state.persisting_effects_for_unit(MOVER))


def _assert_actual_spend(b: Scene, *, unit_id: str = MOVER, remaining_cp: int = 0) -> None:
    (use,) = tuple(u for u in b.state.stratagem_use_records if u.stratagem_id == GORE_ID)
    assert use.source_id == GORE_SOURCE
    assert use.targeted_unit_instance_ids == (unit_id,)
    assert use.command_point_cost == 1
    assert b.state.command_point_total(OWNER) == remaining_cp
    assert any(
        e.source_rule_id == GORE_SOURCE for e in b.state.persisting_effects_for_unit(unit_id)
    )


def _assert_proof(b: Scene, *, resolves: bool) -> tuple[ChargeFlightOffer, PathWitness]:
    assert "dice_rolled" not in _events(b)
    offer, witness = _offer_and_path(b)
    snapshot = b.session.to_persistence_payload()
    result = choose_proven_charge_flight_mode(
        b.session, _context(b), unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert b.session.to_persistence_payload() == snapshot
    if resolves:
        assert isinstance(result, ProvenChargeFlightAdvantage), result
        assert result.comparison_scope == "no_additional_cp"
        assert (
            result.flight_lower_bound.ordered_outcomes,
            result.ground_upper_bound.ordered_outcomes,
        ) == (10, 3)
    else:
        assert isinstance(result, ChargeFlightUnresolved), result
        assert result.reason is ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT
    return offer, witness


def _native_violation_without_rolling(
    b: Scene, witness: PathWitness, *, budget: float = WITNESS_BUDGET, flies: bool = False
) -> str | None:
    scenario = battlefield_scenario_for_state(state=b.state)
    handler = b.session.lifecycle._charge_phase_handler  # pyright: ignore[reportPrivateUsage]
    ruleset = handler.ruleset_descriptor
    assert ruleset is not None
    result = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_placement=charge_movement_placement(scenario=scenario, unit_instance_id=MOVER),
        selected_target_unit_instance_ids=(TARGET,),
        maximum_distance_inches=budget,
        path_witness=witness,
        unit_persisting_effects=b.state.persisting_effects_for_unit(MOVER),
        ability_index=handler.ability_index_for_player(OWNER),
        take_to_the_skies=flies,
    )
    return charge_move_violation_code(
        resolution=result, ruleset_descriptor=ruleset, maximum_distance_inches=budget
    )


def test_no_cp_keeps_the_wall_proof(definitions: Section02Definitions) -> None:
    b = _battle(definitions, 0)
    assert begin(b.session).decision_type == "select_charging_unit"
    assert b.state.command_point_total(OWNER) == 0
    assert not _grant_active(b)
    _, witness = _assert_proof(b, resolves=True)
    assert _native_violation_without_rolling(b, witness) == "terrain_feature_transit_forbidden"


@pytest.mark.parametrize("spend_early", [True, False], ids=["active-grant", "held-cp"])
def test_early_offer_distinguishes_held_cp_from_a_live_grant(
    definitions: Section02Definitions, *, spend_early: bool
) -> None:
    # This covers the early optional offer, independently of the post-roll choice.
    b = _battle(definitions, 1)
    assert begin(b.session).decision_type == "use_stratagem"
    option = _issue_onslaught_option(b)
    assert option is not None
    opened = _choose(
        b, option if spend_early else DECLINE_STRATAGEM_WINDOW_OPTION_ID, label="rehearse:early"
    )
    assert opened.decision_type == "select_charging_unit"
    if spend_early:
        _assert_actual_spend(b)
    else:
        assert b.state.command_point_total(OWNER) == 1
        assert not _grant_active(b)
    _, witness = _assert_proof(b, resolves=not spend_early)
    expected = None if spend_early else "terrain_feature_transit_forbidden"
    assert _native_violation_without_rolling(b, witness) == expected


def test_other_unit_spend_is_not_a_mover_grant(definitions: Section02Definitions) -> None:
    # This current-draft control exercises the resource/effect admission rule
    # only. The third *physical* model is outside the two-model wall proof.
    b = _battle(definitions, 2, other=True)
    assert begin(b.session).decision_type == "use_stratagem"
    option = _issue_onslaught_option(b, "own:other")
    assert option is not None
    opened = _choose(b, option, label="rehearse:other-grant")
    _assert_actual_spend(b, unit_id="own:other", remaining_cp=1)
    if opened.decision_type == "use_stratagem":
        # The old draft can advance to another native Stratagem in this phase.
        # Crucially, it does not offer a second army-wide Onslaught use.
        assert _issue_onslaught_option(b, MOVER) is None
        assert _issue_onslaught_option(b, "own:other") is None
        opened = _choose(b, DECLINE_STRATAGEM_WINDOW_OPTION_ID, label="rehearse:other-decline")
    assert opened.decision_type == "select_charging_unit"
    assert b.state.command_point_total(OWNER) == 1
    assert not _grant_active(b)
    offer, witness = _offer_and_path(b)
    handler = b.session.lifecycle._charge_phase_handler  # pyright: ignore[reportPrivateUsage]
    assert _plain_charge_supported(
        b.state,
        handler,
        offer,
        OWNER,
        handler.ability_index_for_player(OWNER),
        no_additional_cp=True,
    )
    _choose(b, offer.ground_option_id, label="rehearse:ground")
    _reach_charge_proposal(b, witness, late="absent")
    assert b.state.command_point_total(OWNER) == 1
    assert not _grant_active(b)
    assert roll(b.session).movement_budget.maximum_distance_inches == WITNESS_BUDGET
    status = propose(b.session, MOVER, (TARGET,), witness)
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert "terrain" in str(status.payload)


def test_flight_does_not_gain_distance_or_refund_penalty(
    definitions: Section02Definitions,
) -> None:
    # The early native window supplies a live grant before declaration;
    # no claim is made that a failed flight can open a late movement window.
    for spend in (False, True):
        b = _battle(definitions, int(spend), rng="charge-flight-late-wall-2")
        opened = begin(b.session)
        if spend:
            option = _issue_onslaught_option(b)
            assert option is not None
            opened = _choose(b, option, label="rehearse:live-flight-grant")
            _assert_actual_spend(b)
        assert opened.decision_type == "select_charging_unit"
        offer, witness = _offer_and_path(b)
        assert _grant_active(b) is spend
        assert 6 < offer.target_filter_distance_inches < 7
        assert offer.flight_penalty_inches == 2
        assert (
            _native_violation_without_rolling(b, witness, budget=6, flies=True)
            == "movement_distance_exceeded"
        )
        assert _native_violation_without_rolling(b, witness, budget=7, flies=True) is None
        _choose(b, offer.flight_option_id, label="rehearse:flight")
        result = roll(b.session)
        assert result.request.take_to_the_skies is True
        budget = result.movement_budget.maximum_distance_inches
        assert budget == max(0, result.value - 2)
        assert result.move_available is (budget >= offer.target_filter_distance_inches)
        assert _events(b).index("charging_unit_selected") < _events(b).index("dice_rolled")
        assert _events(b).count("dice_rolled") == 1


def _reach_charge_proposal(
    b: Scene, witness: PathWitness, *, late: Literal["absent", "decline", "spend"]
) -> None:
    saw_offer = False
    selected_target = False
    for _ in range(8):
        req = _context(b).request
        if req["decision_type"] == "select_charge_targets":
            assert not selected_target
            targets(b.session, (TARGET,))
            selected_target = True
        elif req["decision_type"] == "use_stratagem":
            option = _issue_onslaught_option(b)
            if option is not None:
                assert late != "absent"
                assert not saw_offer
                evidence = _events(b)
                native = b.session.lifecycle.pending_decision_request()
                assert native is not None
                timing = stratagem_window_context_from_request(native).timing_window_id
                assert timing is not None
                assert timing.startswith("charge-post-roll:")
                assert "charge_roll_started" in evidence
                assert evidence.count("charge_roll_resolved") == 1
                assert "charge_move_proposal_requested" not in evidence
                assert evidence.index("charging_unit_selected") < evidence.index("dice_rolled")
                assert b.state.command_point_total(OWNER) == 1
                assert not _grant_active(b)
                before = b.session.to_persistence_payload()
                result = choose_proven_charge_flight_mode(
                    b.session, _context(b), unit_id=MOVER, target_id=TARGET, witness=witness
                )
                assert isinstance(result, ChargeFlightUnresolved)
                assert result.reason is ChargeFlightUnresolvedReason.NOT_ORDINARY_CHARGE_OFFER
                assert b.session.to_persistence_payload() == before
                choice = option if late == "spend" else DECLINE_STRATAGEM_WINDOW_OPTION_ID
                _choose(b, choice, label=f"rehearse:late-{late}")
                if late == "spend":
                    _assert_actual_spend(b)
                saw_offer = True
            else:
                # Keep the same rolled dice: decline unrelated optional choices.
                assert any(
                    row["option_id"] == DECLINE_STRATAGEM_WINDOW_OPTION_ID for row in req["options"]
                ), req
                _choose(b, DECLINE_STRATAGEM_WINDOW_OPTION_ID, label="rehearse:decline-other")
        elif req["decision_type"] == "submit_movement_proposal":
            assert selected_target
            assert saw_offer is (late != "absent")
            return
        else:
            pytest.fail(f"Unexpected native step before fixed Charge path: {req['decision_type']}")
    pytest.fail("Native late-offer probe exceeded the bounded decision sequence")


def _reach_unspent_declaration(b: Scene) -> None:
    opened = begin(b.session)
    for index in range(4):
        if opened.decision_type == "select_charging_unit":
            return
        # The revised timing still allows an early use. Decline it explicitly:
        # only the separately issued Charge post-roll offer is under test.
        assert opened.decision_type == "use_stratagem", opened
        assert "dice_rolled" not in _events(b)
        assert any(o.option_id == DECLINE_STRATAGEM_WINDOW_OPTION_ID for o in opened.options)
        opened = _choose(b, DECLINE_STRATAGEM_WINDOW_OPTION_ID, label=f"rehearse:early-{index}")
    pytest.fail("No ordinary Charge declaration in the bounded preparation sequence")


@pytest.mark.parametrize("late", ["absent", "decline", "spend"])
def test_real_late_spend_changes_ground_only_if_authorized(
    definitions: Section02Definitions, *, late: Literal["absent", "decline", "spend"]
) -> None:
    cp = 0 if late == "absent" else 1
    # Fixed real-dice fixtures: the 0-CP and funded pre-roll histories are
    # different. Each label yields the same native ground total of nine.
    b = _battle(definitions, cp, rng="charge-flight-late-wall-7" if cp else RNG_LABEL)
    _reach_unspent_declaration(b)
    assert not b.state.stratagem_use_records
    assert not _grant_active(b)
    assert b.state.command_point_total(OWNER) == cp
    pre_roll_context = _context(b)
    # Same read-only geometry result regardless of a pending resource decision.
    offer, witness = _assert_proof(b, resolves=True)
    _choose(b, offer.ground_option_id, label="rehearse:ground")
    _reach_charge_proposal(b, witness, late=late)
    assert roll(b.session).movement_budget.maximum_distance_inches == WITNESS_BUDGET
    spend = late == "spend"
    assert _grant_active(b) is spend
    assert b.state.command_point_total(OWNER) == cp - int(spend)
    prior = choose_proven_charge_flight_mode(
        b.session, pre_roll_context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(prior, ChargeFlightUnresolved)
    assert prior.reason is ChargeFlightUnresolvedReason.OBSERVATION_DRIFT
    status = propose(b.session, MOVER, (TARGET,), witness)
    if not spend:
        assert status.status_kind is LifecycleStatusKind.INVALID, status
        assert "terrain" in str(status.payload)
        assert not b.state.stratagem_use_records
    else:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        assert "charge_move_completed" in _events(b)
        assert _events(b).count("dice_rolled") == 1
        replay = ReplayRunner.from_payload(
            b.session.replay_artifact(artifact_id="charge-flight:late-onslaught")
        ).run()
        assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("late", ["decline", "spend"])
def test_native_late_grant_leaves_declared_flight_unchanged(
    definitions: Section02Definitions, *, late: Literal["decline", "spend"]
) -> None:
    b = _battle(definitions, 1, rng="charge-flight-late-wall-5")
    _reach_unspent_declaration(b)
    offer, witness = _assert_proof(b, resolves=True)
    _choose(b, offer.flight_option_id, label="rehearse:flight")
    _reach_charge_proposal(b, witness, late=late)
    actual = roll(b.session)
    assert actual.request.take_to_the_skies is True
    assert actual.value == 10
    assert actual.movement_budget.maximum_distance_inches == 8
    assert b.state.command_point_total(OWNER) == int(late == "decline")
    assert _grant_active(b) is (late == "spend")
    assert (
        _native_violation_without_rolling(b, witness, budget=6, flies=True)
        == "movement_distance_exceeded"
    )
    move = propose(b.session, MOVER, (TARGET,), witness)
    assert move.status_kind is not LifecycleStatusKind.INVALID, move
    assert "charge_move_completed" in _events(b)
