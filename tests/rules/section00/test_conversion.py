"""Literal 00 conversions at the shared candidate and physical setup boundary."""

from dataclasses import replace

import pytest

from tests.support.section00_fixtures import conversion_scene, grant
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section18_fixtures import TransportScene
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.normal_move_history import NormalMoveSourceKind, NormalMoveState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
    MovementPhaseState,
)
from warhammer40k_core.engine.phases.movement_transports import (
    _disembark_candidates_for_movement_unit,
)
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    DisembarkResolution,
    TransportMovementStatus,
    apply_disembark_to_battlefield,
    resolve_disembark,
)
from warhammer40k_core.geometry.pose import Pose

MODES = (DisembarkModeKind.ASSAULT_DISEMBARK, DisembarkModeKind.SHOCK_DISEMBARK)
STATUSES = (
    TransportMovementStatus.NOT_MOVED,
    TransportMovementStatus.NORMAL_MOVE,
    TransportMovementStatus.ADVANCE,
    TransportMovementStatus.FALL_BACK,
)


def carrier_history(scene: TransportScene, status: TransportMovementStatus) -> MovementPhaseState:
    """Typed current-turn premise; full witnessed producer is in test_facade."""
    identity = scene.transport.unit_instance_id
    if status is TransportMovementStatus.NORMAL_MOVE:
        scene.state.record_normal_move_state(
            NormalMoveState(
                player_id="owner",
                turn_player_id="owner",
                battle_round=1,
                phase=BattlePhase.MOVEMENT,
                unit_instance_id=identity,
                source_rule_id="constructed:s00:normal",
                source_kind=NormalMoveSourceKind.MOVEMENT_PHASE_ACTION,
                request_id="s00:move-request",
                result_id="s00:move-result",
            )
        )
    elif status is TransportMovementStatus.ADVANCE:
        request = AdvanceRollRequest.for_unit(
            request_id="s00:advance",
            game_id=scene.state.game_id,
            battle_round=1,
            player_id="owner",
            unit_instance_id=identity,
        )
        roll = DiceRollManager("s00:advance").roll_fixed(request.spec, [3])
        scene.state.record_advanced_unit_state(
            AdvancedUnitState(
                player_id="owner",
                battle_round=1,
                unit_instance_id=identity,
                movement_dice_record=MovementDiceRecord(
                    player_id="owner",
                    battle_round=1,
                    unit_instance_id=identity,
                    movement_phase_action=MovementPhaseActionKind.ADVANCE,
                    advance_roll=AdvanceRollResult.from_roll_state(
                        request=request, roll_state=roll
                    ),
                ),
            )
        )
    elif status is TransportMovementStatus.FALL_BACK:
        scene.state.record_fell_back_unit_state(
            FellBackUnitState(
                player_id="owner",
                battle_round=1,
                unit_instance_id=identity,
            )
        )
    moved = status is not TransportMovementStatus.NOT_MOVED
    return MovementPhaseState(
        battle_round=1,
        active_player_id="owner",
        selected_unit_ids=(identity,) if moved else (),
        moved_unit_ids=(identity,) if moved else (),
    )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("permission", ["eligible", "absent", "different-passenger"])
def test_conversion_requires_the_actual_passenger_grant_and_appropriate_carrier_history(
    section00_definitions: Section02Definitions,
    mode: DisembarkModeKind,
    status: TransportMovementStatus,
    permission: str,
) -> None:
    scene = conversion_scene(section00_definitions)
    movement = carrier_history(scene, status)
    if permission != "absent":
        grant(scene, mode, eligible="owner:spare" if permission == "different-passenger" else None)
    before = scene.state.to_payload()
    candidates = _disembark_candidates_for_movement_unit(
        state=scene.state,
        movement_state=movement,
        unit_instance_id=scene.passenger.unit_instance_id,
        transport_unit_instance_id=scene.transport.unit_instance_id,
        ruleset_descriptor=scene.state.runtime_ruleset_descriptor(),
    )
    expected: set[DisembarkModeKind] = set()
    if status is TransportMovementStatus.NOT_MOVED:
        expected.add(DisembarkModeKind.TACTICAL_DISEMBARK)
    elif status is TransportMovementStatus.NORMAL_MOVE:
        expected.add(DisembarkModeKind.RAPID_DISEMBARK)
    allowed = permission == "eligible" and (
        mode is DisembarkModeKind.SHOCK_DISEMBARK
        or status in {TransportMovementStatus.NOT_MOVED, TransportMovementStatus.NORMAL_MOVE}
    )
    if allowed:
        expected.add(mode)
    assert {c.disembark_mode for c in candidates} == expected
    assert all(c.transport_movement_status is status for c in candidates)
    assert scene.state.to_payload() == before
    for candidate in candidates:
        selection = scene.selection(
            candidate.disembark_mode, status, overrides=candidate.restriction_overrides
        )
        result = resolve_disembark(
            scenario=scene.scenario,
            ruleset_descriptor=scene.state.runtime_ruleset_descriptor(),
            cargo_state=scene.cargo,
            selection=selection,
            unit=scene.passenger,
            transport_placement=scene.carrier_placement,
        )
        assert result.is_valid, result.violations
        outcome = result.disembarked_unit_state
        assert outcome is not None
        assert outcome.disembark_mode is candidate.disembark_mode
        assert outcome.can_declare_charge is (
            candidate.disembark_mode
            in {
                DisembarkModeKind.TACTICAL_DISEMBARK,
                DisembarkModeKind.ASSAULT_DISEMBARK,
            }
        )
        assert outcome.can_move_further is (
            candidate.disembark_mode is DisembarkModeKind.TACTICAL_DISEMBARK
        )
        assert outcome.permission_source_rule_id == (
            f"constructed:s00:permission:{mode.value}" if candidate.disembark_mode is mode else None
        )
        assert outcome.battle_shocked_until is None
        assert result.updated_cargo_state is not None
        assert result.updated_cargo_state.embarked_unit_instance_ids == ()
        board = apply_disembark_to_battlefield(
            battlefield_state=scene.scenario.battlefield_state, disembark=result
        )
        assert (
            board.unit_placement_by_id(scene.passenger.unit_instance_id)
            == selection.attempted_placement
        )
        assert DisembarkResolution.from_payload(result.to_payload()) == result
        assert scene.state.to_payload() == before


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("delta", [-0.001, 0.0, 0.001])
def test_converted_setup_measures_every_part_of_real_passenger_at_three_inches(
    section00_definitions: Section02Definitions,
    mode: DisembarkModeKind,
    delta: float,
) -> None:
    scene = conversion_scene(section00_definitions)
    status = (
        TransportMovementStatus.NORMAL_MOVE
        if mode is DisembarkModeKind.ASSAULT_DISEMBARK
        else TransportMovementStatus.ADVANCE
    )
    movement = carrier_history(scene, status)
    grant(scene, mode)
    candidate = next(
        c
        for c in _disembark_candidates_for_movement_unit(
            state=scene.state,
            movement_state=movement,
            unit_instance_id=scene.passenger.unit_instance_id,
            transport_unit_instance_id=scene.transport.unit_instance_id,
            ruleset_descriptor=scene.state.runtime_ruleset_descriptor(),
        )
        if c.disembark_mode is mode
    )
    rt = scene.transport.own_models[0].geometry.parts[0].radius_x_inches
    rp = scene.passenger.own_models[0].geometry.parts[0].radius_x_inches
    result = resolve_disembark(
        scenario=scene.scenario,
        ruleset_descriptor=scene.state.runtime_ruleset_descriptor(),
        cargo_state=scene.cargo,
        selection=scene.selection(
            mode,
            status,
            poses=(Pose.at(20 + rt + 3 - rp + delta, 20),),
            overrides=candidate.restriction_overrides,
        ),
        unit=scene.passenger,
        transport_placement=scene.carrier_placement,
    )
    assert result.is_valid is (delta <= 0), result.violations
    assert {v.violation_code.value for v in result.violations} == (
        set() if delta <= 0 else {"disembark_distance"}
    )
    assert (result.transition_batch is not None) is (delta <= 0)
    assert (result.updated_cargo_state is not None) is (delta <= 0)


@pytest.mark.parametrize("mode", MODES)
def test_turn_expiry_removes_the_conversion_but_preserves_ordinary_disembark(
    section00_definitions: Section02Definitions,
    mode: DisembarkModeKind,
) -> None:
    scene = conversion_scene(section00_definitions)
    grant(scene, mode)
    scene.state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=1, player_id="owner")
    )
    assert not scene.state.persisting_effects
    candidates = _disembark_candidates_for_movement_unit(
        state=scene.state,
        movement_state=carrier_history(scene, TransportMovementStatus.NORMAL_MOVE),
        unit_instance_id=scene.passenger.unit_instance_id,
        transport_unit_instance_id=scene.transport.unit_instance_id,
        ruleset_descriptor=scene.state.runtime_ruleset_descriptor(),
    )
    assert tuple(c.disembark_mode for c in candidates) == (DisembarkModeKind.RAPID_DISEMBARK,)


def test_shared_definitions_produce_independent_physical_units_and_cargo(
    section00_definitions: Section02Definitions,
) -> None:
    first, second = (conversion_scene(section00_definitions) for _ in range(2))
    assert first.state.to_payload() == second.state.to_payload()
    grant(first, DisembarkModeKind.ASSAULT_DISEMBARK)
    assert not second.state.persisting_effects
    assert first.passenger.own_models[0] is not second.passenger.own_models[0]
    assert first.cargo is not second.cargo
    assert (
        first.session.lifecycle.decision_controller
        is not second.session.lifecycle.decision_controller
    )
    first.state.replace_transport_cargo_state(replace(first.cargo, embarked_unit_instance_ids=()))
    assert second.cargo.embarked_unit_instance_ids == (second.passenger.unit_instance_id,)
