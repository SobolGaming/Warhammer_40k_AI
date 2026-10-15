from __future__ import annotations

from dataclasses import replace

import pytest
from tests.phase10p_reserves_helpers import (
    battle_state_with_reserve,
    single_model_reserve_placement,
)
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, BattlefieldScenario
from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.reserves import (
    BattlefieldEdge,
    LargeModelReservePlacementException,
    apply_reinforcement_placement_to_battlefield,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_eligibility_state import shooting_state_restriction_reason
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("aircraft", [False, True])
def test_oversized_arrival_locks_every_prohibited_activity_and_preserves_aircraft(
    aircraft: bool,
) -> None:
    state, scenario, reserve, unit = battle_state_with_reserve()
    if aircraft:
        unit = with_unit_keywords(unit, keywords=(*unit.keywords, "AIRCRAFT", "FLY"))
        state.army_definitions[:] = [
            replace(
                army,
                units=tuple(
                    unit if u.unit_instance_id == unit.unit_instance_id else u for u in army.units
                ),
            )
            for army in state.army_definitions
        ]
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=scenario.battlefield_state
        )
    state.battle_round = 3
    placement = single_model_reserve_placement(reserve_unit=unit, pose=Pose.at(15, 200 / 25.4 / 2))
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        reserve_state=reserve,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )
    assert result.is_valid
    assert result.large_model_exception_used
    assert bool(result.post_arrival_restrictions) is not aircraft
    assert bool(result.aircraft_exception_model_ids) is aircraft
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.large_model_restrictions import (
        validate_arrival_restriction_evidence,
    )
    from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind

    submitted = PlacementProposalPayload(
        proposal_request_id="order54-arrival",
        proposal_kind=ProposalKind.STRATEGIC_RESERVES,
        unit_instance_id=unit.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=placement,
        large_model_exceptions=result.candidate.large_model_exceptions,
    )
    evidence: dict[str, JsonValue] = {
        "large_model_exception_used": True,
        "post_arrival_restrictions": [r.value for r in result.post_arrival_restrictions],
    }
    validate_arrival_restriction_evidence(state=state, submitted=submitted, payload=evidence)
    with pytest.raises(GameLifecycleError, match="restriction evidence drifted"):
        validate_arrival_restriction_evidence(
            state=state,
            submitted=submitted,
            payload={**evidence, "large_model_exception_used": False},
        )
    with pytest.raises(GameLifecycleError, match="restriction evidence drifted"):
        validate_arrival_restriction_evidence(
            state=state,
            submitted=submitted,
            payload={**evidence, "post_arrival_restrictions": ["invented"]},
        )
    foreign_model = state.army_definitions[1].units[0].own_models[0]
    for model_id in ("order54:unknown-model", foreign_model.model_instance_id):
        with pytest.raises(GameLifecycleError, match="lost model identity"):
            validate_arrival_restriction_evidence(
                state=state,
                submitted=replace(
                    submitted,
                    large_model_exceptions=(
                        LargeModelReservePlacementException(
                            model_instance_id=model_id,
                            battlefield_edge=BattlefieldEdge.SOUTH,
                        ),
                    ),
                ),
                payload=evidence,
            )
    state.replace_reserve_state(result.arrived_reserve_state())
    state.replace_battlefield_state(
        apply_reinforcement_placement_to_battlefield(
            battlefield_state=scenario.battlefield_state, placement=result
        )
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    expected = None if aircraft else "large_model_setup_turn_restriction"
    for phase in (
        BattlePhase.MOVEMENT,
        BattlePhase.SHOOTING,
        BattlePhase.CHARGE,
        BattlePhase.FIGHT,
    ):
        state.battle_phase_index = state.battle_phase_sequence.index(phase)
        for activity in ("normal", "advance", "fall_back", "charge", "ranged_attacks"):
            assert large_model_activity_reason(state, unit.unit_instance_id, activity) == expected
        for activity in ("remain_stationary", "pile_in", "consolidate", "surge", "melee_attacks"):
            assert large_model_activity_reason(state, unit.unit_instance_id, activity) is None
        assert (
            shooting_state_restriction_reason(state=state, rules_unit=view, player_id="player-a")
            == expected
        )
    if not aircraft:
        assert (
            charge_unit_ineligibility_reason(
                state=state,
                charge_state=ChargePhaseState(battle_round=3, active_player_id="player-a"),
                ignore_already_selected=False,
                unit_instance_id=unit.unit_instance_id,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
            )
            == expected
        )
        witness = PathWitness.for_straight_line_endpoints(
            tuple(
                (p.model_instance_id, p.pose, Pose.at(p.pose.position.x + 1, p.pose.position.y))
                for p in placement.model_placements
            )
        )
        assert state.battlefield_state is not None
        moved = resolve_normal_move(
            scenario=BattlefieldScenario(
                armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
            ),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_placement=replace(
                placement,
                model_placements=tuple(
                    replace(p, pose=Pose.at(p.pose.position.x + 1, p.pose.position.y))
                    for p in placement.model_placements
                ),
            ),
            state=state,
            path_witness=witness,
        )
        assert not moved.is_valid
        assert any(
            v.violation_code == expected
            for p in moved.path_validation_results
            for v in p.violations
        )
        from warhammer40k_core.engine.decision_controller import DecisionController
        from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
        from warhammer40k_core.engine.decision_result import DecisionResult
        from warhammer40k_core.engine.event_log import validate_json_value
        from warhammer40k_core.engine.movement_proposals import (
            MOVEMENT_PROPOSAL_DECISION_TYPE,
            MovementProposalPayload,
            MovementProposalRequest,
        )
        from warhammer40k_core.engine.setup_turn_prevalidation import invalid_setup_turn_activity

        for kind, mode, blocked in (
            (ProposalKind.NORMAL_MOVE, MovementMode.NORMAL, True),
            (ProposalKind.ADVANCE, MovementMode.ADVANCE, True),
            (ProposalKind.FALL_BACK, MovementMode.FALL_BACK, True),
            (ProposalKind.CHARGE_MOVE, MovementMode.CHARGE, True),
            (ProposalKind.PILE_IN, MovementMode.PILE_IN, False),
            (ProposalKind.CONSOLIDATE, MovementMode.CONSOLIDATE, False),
            (ProposalKind.SURGE_MOVE, MovementMode.NORMAL, False),
        ):
            proposal = MovementProposalRequest(
                request_id=f"order54-{kind.value}",
                decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
                actor_id="player-a",
                game_id=state.game_id,
                battle_round=state.battle_round,
                phase="fight",
                unit_instance_id=unit.unit_instance_id,
                proposal_kind=kind,
                source_decision_request_id="order54-source",
                source_decision_result_id="order54-result",
                spatial_context_hash=state.physical_proposal_context_hash(),
                movement_phase_action=kind.value,
            )
            pending = proposal.to_decision_request()
            choice = DecisionResult(
                result_id=f"order54-{kind.value}-result",
                request_id=pending.request_id,
                decision_type=pending.decision_type,
                actor_id=pending.actor_id,
                selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                payload=validate_json_value(
                    MovementProposalPayload(
                        proposal_request_id=pending.request_id,
                        proposal_kind=kind,
                        unit_instance_id=unit.unit_instance_id,
                        movement_phase_action=kind.value,
                        movement_mode=mode.value,
                        witness=witness,
                    ).to_payload()
                ),
            )
            invalid = invalid_setup_turn_activity(
                state=state, decisions=DecisionController(), request=pending, result=choice
            )
            assert (invalid is not None) is blocked
        for mode in (MovementMode.NORMAL, MovementMode.ADVANCE, MovementMode.FALL_BACK):
            descriptor = TriggeredMovementDescriptor(
                movement_kind=TriggeredMovementKind.TRIGGERED,
                source_rule_id="order54:reactive-move",
                trigger_timing=ReactionWindow(
                    phase=BattlePhase.FIGHT,
                    window_kind=ReactionWindowKind.RULE_TRIGGER,
                    source_step=None,
                    source_event_id=None,
                ),
                max_distance_inches=3,
                movement_mode=mode,
            )
            if mode is MovementMode.NORMAL:
                from warhammer40k_core.engine.decision_controller import DecisionController
                from warhammer40k_core.engine.decision_result import DecisionResult
                from warhammer40k_core.engine.setup_turn_prevalidation import (
                    invalid_setup_turn_activity,
                )

                locked = state.reserve_states[0]
                state.replace_reserve_state(
                    replace(locked, post_arrival_restrictions=(), restriction_battle_round=None)
                )
                pending = TriggeredMovementHandler(
                    ruleset_descriptor=state.runtime_ruleset_descriptor()
                ).request_from_state(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    descriptor=descriptor,
                    candidate_witnesses=(witness,),
                )
                state.replace_reserve_state(locked)
                controller = DecisionController()
                controller.request_decision(pending)
                selected = next(
                    o
                    for o in pending.options
                    if isinstance(o.payload, dict) and o.payload.get("declined") is not True
                )
                choice = DecisionResult.for_request(
                    result_id="order54-stale-move",
                    request=pending,
                    selected_option_id=selected.option_id,
                )
                before = controller.to_payload(), state.to_payload()
                invalid = invalid_setup_turn_activity(
                    state=state, decisions=controller, request=pending, result=choice
                )
                assert invalid is not None
                assert invalid.payload == {"invalid_reason": expected}
                assert (controller.to_payload(), state.to_payload()) == before
            with pytest.raises(GameLifecycleError, match=expected):
                TriggeredMovementHandler(
                    ruleset_descriptor=state.runtime_ruleset_descriptor()
                ).request_from_state(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    descriptor=descriptor,
                    candidate_witnesses=(witness,),
                )
    state.replace_reserve_state(
        state.reserve_states[0].clear_expired_post_arrival_restrictions(
            player_id="player-a", battle_round=3
        )
    )
    assert large_model_activity_reason(state, unit.unit_instance_id, "ranged_attacks") is None


def test_oversized_strip_proof_considers_rotation_and_full_battlefield_extent() -> None:
    from warhammer40k_core.engine.large_model_setup import base_fits_edge_band
    from warhammer40k_core.geometry.base import OvalBase, RectangularBase
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    for base in (OvalBase(8, 2), RectangularBase(8, 2)):
        model = Model(
            model_id="rotatable",
            pose=Pose.at(4, 4, facing_degrees=90),
            base=base,
            volume=ModelVolume(height=2),
        )
        assert base_fits_edge_band(
            model,
            edge=BattlefieldEdge.SOUTH,
            distance_inches=3,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
        )
        assert not base_fits_edge_band(
            model,
            edge=BattlefieldEdge.SOUTH,
            distance_inches=3,
            battlefield_width_inches=1,
            battlefield_depth_inches=44,
        )


def test_oversized_deployment_requires_explicit_correct_edge_authority() -> None:
    from tests.large_model_setup_helpers import oversized_deployment_case

    from warhammer40k_core.engine.deployment import resolve_deployment_placement

    for attacker, defender, reason in (
        (None, None, "large_model_player_edge_unsupported"),
        ("east", "west", "large_model_edge_contact_missing"),
    ):
        state, request, proposal = oversized_deployment_case()
        assert state.mission_setup is not None
        state.mission_setup = replace(
            state.mission_setup,
            attacker_battlefield_edge=attacker,
            defender_battlefield_edge=defender,
        )
        result = resolve_deployment_placement(
            state=state,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            request=request,
            proposal=proposal,
        )
        assert not result.is_valid
        assert reason in {v.violation_code.value for v in result.violations}


@pytest.mark.parametrize(
    ("edge", "x", "y", "valid"),
    [
        ("north_west_corner", 200 / 25.4 / 2, 30.0, True),
        ("north_west_corner", 15.0, 44 - 200 / 25.4 / 2, True),
        ("north_west_corner", 60 - 200 / 25.4 / 2, 30.0, False),
    ],
)
def test_oversized_deployment_source_corner_has_two_own_edges(
    edge: str,
    x: float,
    y: float,
    valid: bool,
) -> None:
    from tests.large_model_setup_helpers import oversized_deployment_case

    from warhammer40k_core.engine.deployment import resolve_deployment_placement

    state, request, proposal = oversized_deployment_case(x=x)
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        attacker_battlefield_edge=edge,
        defender_battlefield_edge="south_east_corner",
    )
    proposal = replace(
        proposal,
        model_placements=tuple(replace(p, pose=Pose.at(x, y)) for p in proposal.model_placements),
    )
    result = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
    )
    assert result.is_valid is valid
