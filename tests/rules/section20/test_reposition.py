"""20.02/FAQs40-41: source permission after moving, ongoing status and range."""

from dataclasses import replace

import pytest

from tests.normal_move_occurrence_helpers import reaction_request
from tests.support.ability_presence_fixtures import compiled_ability_rule
from tests.support.section01_fixtures import reserve_unit
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, placement
from tests.support.section09_fixtures import add_unit, attach_mission, propose, unplace
from tests.support.section20_fixtures import LORD, YRIEL, section20_session, submit_ingress
from warhammer40k_core.engine.battle_shock_state import apply_direct_battle_shock_state
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    EffectExpirationBoundary,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.movement_reposition_context import MovementRepositionContext
from warhammer40k_core.engine.movement_source_reposition import (
    movement_reposition_permission_effect,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.reserve_lifetime_boundary import reserve_round_deadline_exempt_ids
from warhammer40k_core.engine.reserves import ReserveUnitPointValue
from warhammer40k_core.engine.rule_aura_resolution import aura_affected_unit_ids
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("decline", [False, True])
def test_moved_native_unit_can_use_explicit_reposition_permission_without_resetting_status(
    section20_definitions: Section02Definitions, decline: bool
) -> None:
    d = section20_definitions
    unit = d.unit(YRIEL)
    aura_source = d.unit(LORD, identity="aura")
    enemy = d.unit(LORD, identity="enemy", army_id="enemy")
    state = native_state(d, unit, (Pose.at(10, 15),), enemy=enemy, enemy_poses=(Pose.at(40, 30),))
    add_unit(state, aura_source, (Pose.at(12, 15),))
    bench = d.unit(LORD, identity="bench")
    add_unit(state, bench, (Pose.at(20, 35),))
    state.replace_battlefield_state(unplace(state, bench))
    reserve_unit(state, bench)
    state.reserve_states[:] = [replace(r, points_contribution=1000) for r in state.reserve_states]
    state.battle_round = 2
    attach_mission(state)
    session = section20_session(
        d,
        state,
        reserve_points=(
            ReserveUnitPointValue(bench.unit_instance_id, 1000, "constructed:s20:bench-price"),
            ReserveUnitPointValue(unit.unit_instance_id, 1, "constructed:s20:subject-price"),
        ),
    )
    assert sum(p.points for p in session.lifecycle.config.reserve_unit_points) == 1001
    context = MovementRepositionContext(
        "constructed:s20:source-permission",
        "s20:permission",
        "s20:occasion",
        2,
        "owner",
        BattlePhase.MOVEMENT,
        unit.unit_instance_id,
    )
    state.record_persisting_effect(
        movement_reposition_permission_effect(context=context, owner_player_id="owner")
    )
    duration = PersistingEffect(
        effect_id="s20:lasting",
        source_rule_id="constructed:s20:lasting-effect",
        owner_player_id="owner",
        target_unit_instance_ids=(unit.unit_instance_id,),
        started_battle_round=2,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_turn(battle_round=2, player_id="owner"),
        effect_payload={"section20": "specified-duration"},
    )
    state.record_persisting_effect(duration)
    apply_direct_battle_shock_state(
        state=state,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        source_result_id="constructed:s20:shock",
        battle_round=2,
    )
    rule = compiled_ability_rule(
        'Aura: while a friendly unit is within 6" of this model, '
        "that unit has the [STEALTH] ability.",
        source_id="constructed:s20:aura",
    )
    clause = rule.clauses[0]

    def affected() -> tuple[str, ...]:
        return aura_affected_unit_ids(
            clause=clause,
            state=state,
            source_unit_instance_id=aura_source.unit_instance_id,
            source_model_instance_id=aura_source.own_model_ids()[0],
        )

    assert unit.unit_instance_id in affected()
    # Real native model, existing generic reactive-normal owner. Its independent
    # source permission supplies the existing post-move continuation seam.
    request = reaction_request(session, unit.unit_instance_id, parameterized=False)
    session.lifecycle.decision_controller.request_decision(request)
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s20:moved",
        option_id=next(
            o.option_id for o in request.options if o.option_id != "decline_triggered_movement"
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_source_reposition"
    movement = tuple(state.normal_move_states)
    assert movement
    assert movement[0].unit_instance_id == unit.unit_instance_id
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="s20:reposition",
        option_id="decline_source_reposition" if decline else "enter_strategic_reserves",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert tuple(state.normal_move_states) == movement
    assert duration in state.persisting_effects_for_unit(unit.unit_instance_id)
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=unit.unit_instance_id)
    assert state.battlefield_state is not None
    if decline:
        assert state.reserve_state_for_unit(unit.unit_instance_id) is None
        assert state.battlefield_state.unit_placement_or_none(unit.unit_instance_id) is not None
        assert unit.unit_instance_id in affected()
        return
    assert state.battlefield_state.unit_placement_or_none(unit.unit_instance_id) is None
    assert unit.unit_instance_id not in affected()
    assert reserve_round_deadline_exempt_ids(state) == frozenset({unit.unit_instance_id})
    # FAQ40/41: removal used no pre-battle points admission. Arbitrarily priced
    # existing reserve records do not prevent the actual source-owned mutation.
    reserve = state.reserve_state_for_unit(unit.unit_instance_id)
    assert reserve is not None
    assert reserve.entered_reserves_battle_round == 2
    assert status.decision_request is not None
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="s20:return-unit",
        option_id=unit.unit_instance_id,
    )
    assert status.decision_request is not None
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="s20:return-ingress",
        option_id="ingress",
    )
    assert status.decision_request is not None
    status = submit_ingress(
        session, status.decision_request, unit, (Pose.at(2, 30),), result_id="s20:returned"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert tuple(state.normal_move_states) == movement
    assert duration in state.persisting_effects_for_unit(unit.unit_instance_id)
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=unit.unit_instance_id)
    assert unit.unit_instance_id not in affected()
    removed = state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary(
            expiration_kind=EffectExpirationKind.END_TURN, battle_round=2, player_id="owner"
        )
    )
    assert duration in removed
    assert duration not in state.persisting_effects_for_unit(unit.unit_instance_id)


@pytest.mark.parametrize("action", ["advance", "fall_back:ordered_retreat", "disembark"])
def test_completed_advance_fallback_and_disembark_keep_their_turn_restrictions_after_return(
    section20_definitions: Section02Definitions, action: str
) -> None:
    from tests.support.section03_fixtures import scenario
    from tests.support.section09_fixtures import choose, movement_case, select, unplace
    from tests.support.section18_fixtures import transport_scene
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
    from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalRequest,
        PlacementProposalPayload,
    )
    from warhammer40k_core.engine.reserves import (
        ReserveKind,
        ReserveState,
        StrategicReserveRule,
        apply_reinforcement_placement_to_battlefield,
        resolve_reserve_arrival,
    )

    if action == "disembark":
        s = transport_scene(section20_definitions)
        state, unit, session = s.state, s.passenger, s.session
        request = select(session, unit)
        request = choose(session, request, "disembark")
        context = MovementProposalRequest.from_decision_request_payload(request.payload)
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="s20:actual-disembark",
            payload=validate_json_value(
                PlacementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=context.proposal_kind,
                    unit_instance_id=unit.unit_instance_id,
                    placement_kind=BattlefieldPlacementKind.DISEMBARK,
                    attempted_placement=s.selection().attempted_placement,
                    transport_unit_instance_id=s.transport.unit_instance_id,
                    disembark_mode=s.selection().disembark_mode,
                    transport_movement_status=s.selection().transport_movement_status,
                ).to_payload()
            ),
        )
        original: tuple[object, ...] = tuple(state.disembarked_unit_states)
    else:
        session, state, unit = movement_case(
            section20_definitions, engaged=action.startswith("fall_back")
        )
        request = choose(session, select(session, unit), action)
        status = propose(
            session,
            request,
            unit,
            (Pose.at(10, 6), Pose.at(12.5, 6))
            if action.startswith("fall_back")
            else (Pose.at(10, 11), Pose.at(12.5, 11)),
        )
        original = (
            tuple(state.advanced_unit_states)
            if action == "advance"
            else tuple(state.fell_back_unit_states)
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert original
    # Explicit already-permitted Core removal/return boundary. Native named
    # ability admission is not inferred from this declared reserve input. The
    # separate reactive case executes accepted source-owned removal itself.
    reserve = ReserveState.entered_during_battle(
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT,
        source_rule_ids=("constructed:s20:history-return",),
    )
    state.record_reserve_state(reserve)
    state.replace_battlefield_state(unplace(state, unit))
    result = resolve_reserve_arrival(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        reserve_state=reserve,
        attempted_placement=placement(
            unit, tuple(Pose.at(2, 30 + i * 2.5) for i in range(len(unit.own_models)))
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        strategic_reserve_rule=StrategicReserveRule(
            earliest_arrival_battle_round=1, ignores_mission_arrival_round_blocks=True
        ),
    )
    assert result.is_valid, result.to_payload()
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        apply_reinforcement_placement_to_battlefield(
            battlefield_state=state.battlefield_state, placement=result
        )
    )
    state.replace_reserve_state(
        reserve.mark_arrived(
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    )
    if action == "disembark":
        assert tuple(state.disembarked_unit_states) == original
        assert (
            state.disembarked_unit_state_for_unit(
                player_id="owner", battle_round=1, unit_instance_id=unit.unit_instance_id
            )
            == original[0]
        )
    else:
        assert (
            tuple(state.advanced_unit_states)
            if action == "advance"
            else tuple(state.fell_back_unit_states)
        ) == original
        assert charge_unit_ineligibility_reason(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            charge_state=ChargePhaseState(1, "owner"),
            ignore_already_selected=False,
        ) == ("charge_unit_advanced" if action == "advance" else "charge_unit_fell_back")
